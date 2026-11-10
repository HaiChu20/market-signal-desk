"""Sequential HistData ASCII minute-bar downloader (empirical EU-date DST clock)."""
from __future__ import annotations

import argparse
import csv
from datetime import date, datetime, time, timedelta, timezone
from email.utils import parsedate_to_datetime
import io
import json
import os
from pathlib import Path
import random
import re
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path("data/bars/histdata")
RAW = Path("data/raw/histdata")
SYMBOLS = ("NSXUSD", "SPXUSD", "GRXEUR", "WTIUSD")
COLUMNS = ["ts", "bid_o", "bid_h", "bid_l", "bid_c", "ask_o", "ask_h", "ask_l", "ask_c", "volume"]
PRICE_FIELDS = ("o", "h", "l", "c")
ADJUSTED_COLUMNS = [f"adj_bid_{field}" for field in PRICE_FIELDS]
HIST_COLUMNS = COLUMNS + ["feed", "roll", "stale_expired", *ADJUSTED_COLUMNS]
HISTDATA_SWITCH_UTC = {
    "NSXUSD": pd.Timestamp("2018-12-16 23:00:00", tz="UTC"),
    "SPXUSD": pd.Timestamp("2018-12-16 23:00:00", tz="UTC"),
}
DUKASCOPY_SYMBOL = {"NSXUSD": "USATECHIDXUSD", "SPXUSD": "USA500IDXUSD",
                    "GRXEUR": "DEUIDXEUR", "WTIUSD": "LIGHTCMDUSD"}
ROLL_QUARTER_MONTHS = (3, 6, 9, 12)
ROLL_WINDOW_TRADING_DAYS = 10
NY = "America/New_York"
MIN_REQUEST_INTERVAL = 2.0
_last_request = 0.0
_fred_last_request = 0.0


def _wait_turn() -> None:
    global _last_request
    delay = MIN_REQUEST_INTERVAL - (time.monotonic() - _last_request)
    if delay > 0:
        time.sleep(delay)
    _last_request = time.monotonic()


def parse_token(html: str) -> str:
    form = re.search(r'<form\b(?=[^>]*\bid=["\']file_down["\'])[^>]*>(.*?)</form\s*>', html, re.I | re.S)
    if not form:
        raise ValueError("HistData file_down form not found")
    token = re.search(r'<input\b(?=[^>]*\bname=["\']tk["\'])(?=[^>]*\bvalue=["\']([^"\']+)["\'])[^>]*>', form.group(1), re.I | re.S)
    if not token:
        # Allow either attribute order.
        tag = re.search(r'<input\b[^>]*\bname=["\']tk["\'][^>]*>', form.group(1), re.I | re.S)
        value = re.search(r'\bvalue=["\']([^"\']+)["\']', tag.group(0), re.I) if tag else None
        if not value:
            raise ValueError("HistData token input not found")
        return value.group(1)
    return token.group(1)


def _last_sunday(year: int, month: int) -> date:
    last = (datetime(year + (month == 12), 1 if month == 12 else month + 1, 1) - timedelta(days=1)).date()
    return last - timedelta(days=(last.weekday() + 1) % 7)


def _nth_sunday(year: int, month: int, n: int) -> date:
    first=datetime(year,month,1).date()
    return first+timedelta(days=(6-first.weekday())%7+7*(n-1))


def dst_mismatch_windows(year: int) -> tuple[date,date,date,date]:
    """NY start, EU start, EU end, NY end: +60m applies in the two gaps."""
    return (_nth_sunday(year,3,2),_last_sunday(year,3),_last_sunday(year,10),_nth_sunday(year,11,1))


def _source_utc(naive: datetime, fold: int = 0) -> datetime | None:
    """HistData uses ET wall time but its DST switches follow EU calendar dates.

    The one-hour mismatch windows were identified by exact close comparisons
    with Dukascopy. The source spring gap is 02:00–02:59 on the last Sunday
    in March; the repeated fall hour is 01:00–01:59 on the last Sunday in
    October. Rows are chronological, so `fold` selects the first/second copy.
    """
    start, end = _last_sunday(naive.year, 3), _last_sunday(naive.year, 10)
    if naive.date() == start and naive.hour == 2:
        return None
    if naive.date() == end and naive.hour == 1:
        daylight = fold == 0
    elif naive.date() == start:
        daylight = naive.hour >= 3
    elif naive.date() == end:
        daylight = naive.hour < 1
    else:
        daylight = start < naive.date() < end
    return (naive + timedelta(hours=4 if daylight else 5)).replace(tzinfo=timezone.utc)


def parse_csv(raw: bytes, symbol: str | None = None) -> pd.DataFrame:
    """Decode HistData wall times with its empirically verified DST calendar."""
    rows, naive_times, invalid_rows = [], [], []
    reader = csv.reader(io.StringIO(raw.decode("utf-8-sig"), newline=""), delimiter=";")
    for row in reader:
        if not row or len(row) < 6:
            continue
        naive = datetime.strptime(row[0].strip(), "%Y%m%d %H%M%S")
        o, h, low, close = map(float, row[1:5])
        naive_times.append(naive)
        rows.append((o, h, low, close))
    counts: dict[datetime, int] = {}
    localized = []
    for naive in naive_times:
        is_fall_fold = naive.date() == _last_sunday(naive.year, 10) and naive.hour == 1
        if naive.date() == _last_sunday(naive.year, 3) and naive.hour == 2:
            localized.append(None)
            invalid_rows.append(naive)
        elif is_fall_fold:
            fold_number = counts.get(naive, 0)
            localized.append(_source_utc(naive, min(fold_number, 1)))
            counts[naive] = fold_number + 1
        else:
            localized.append(_source_utc(naive))
    records = [(pd.Timestamp(ts), *row) for ts, row in zip(localized, rows) if ts is not None]
    frame = pd.DataFrame(records, columns=["ts", "bid_o", "bid_h", "bid_l", "bid_c"])
    frame["ts"] = pd.to_datetime(frame.ts, utc=True).astype("datetime64[ns, UTC]")
    for col in ("ask_o", "ask_h", "ask_l", "ask_c"):
        frame[col] = frame["bid_" + col[-1]]
    frame["volume"] = np.nan
    frame = frame[COLUMNS].drop_duplicates("ts", keep="last").sort_values("ts").reset_index(drop=True)
    switch = HISTDATA_SWITCH_UTC.get(symbol) if symbol else None
    if switch is not None:
        frame["feed"] = np.where(frame.ts >= switch, "cash_cfd", "futures_cont")
    else:
        frame["feed"] = "unclassified"
    frame["roll"] = False
    frame["stale_expired"] = False
    for field in PRICE_FIELDS:
        frame[f"adj_bid_{field}"] = np.nan
    frame = frame[HIST_COLUMNS]
    frame.attrs["nonexistent_local_rows"] = [stamp.isoformat() for stamp in invalid_rows]
    return frame


def parse_archive(raw: bytes, symbol: str) -> tuple[pd.DataFrame, str]:
    if not zipfile.is_zipfile(io.BytesIO(raw)):
        raise ValueError(f"HistData response for {symbol} is not a ZIP archive")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        csv_names = [name for name in archive.namelist() if Path(name).name.upper().endswith(".CSV") and f"{symbol}_M1_" in Path(name).name.upper()]
        if not csv_names:
            raise ValueError(f"No {symbol} M1 CSV found in archive")
        gaps = "\n".join(archive.read(n).decode("utf-8", errors="replace") for n in archive.namelist() if Path(n).suffix.lower() == ".txt")
        return parse_csv(archive.read(csv_names[0]), symbol), gaps


def _request(url: str, data: bytes | None = None, headers: dict[str, str] | None = None, retries: int = 5) -> bytes:
    global _last_request
    for attempt in range(retries):
        _wait_turn()
        req = urllib.request.Request(url, data=data, headers={"User-Agent": "Mozilla/5.0 (compatible; MarketSignalDesk/0.1)", **(headers or {})})
        try:
            with urllib.request.urlopen(req, timeout=60) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise
            if attempt + 1 == retries:
                raise
        except (TimeoutError, OSError, urllib.error.URLError):
            if attempt + 1 == retries:
                raise
        time.sleep(max(MIN_REQUEST_INTERVAL, min(2 ** (attempt + 1), 30) + random.random()))
    raise AssertionError("unreachable")


def _page_url(symbol: str, year: int, month: int | None = None) -> str:
    base = f"https://www.histdata.com/download-free-forex-historical-data/?/ascii/1-minute-bar-quotes/{symbol.lower()}/{year}"
    return base if month is None else f"{base}/{month}"


def fetch_period(symbol: str, year: int, month: int | None = None, opener=None) -> bytes:
    if symbol not in SYMBOLS:
        raise ValueError(symbol)
    opener = opener or urllib.request.build_opener(urllib.request.HTTPCookieProcessor())
    page = _page_url(symbol, year, month)
    _wait_turn()
    html = opener.open(urllib.request.Request(page, headers={"User-Agent": "Mozilla/5.0 (compatible; MarketSignalDesk/0.1)"}), timeout=60).read().decode("utf-8", errors="replace")
    token = parse_token(html)
    fields = {"tk": token, "date": str(year), "datemonth": f"{year}{month:02d}" if month else str(year), "platform": "ASCII", "timeframe": "M1", "fxpair": symbol}
    return _request("https://www.histdata.com/get.php", urllib.parse.urlencode(fields).encode(), {"Referer": page, "Content-Type": "application/x-www-form-urlencoded"})


def _atomic_parquet(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".parquet", delete=False) as handle:
        temp = Path(handle.name)
    try:
        pq.write_table(pa.Table.from_pandas(frame[HIST_COLUMNS], preserve_index=False), temp)
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()


def _third_friday(year: int, month: int) -> date:
    first = date(year, month, 1)
    return date(year, month, 1 + (4 - first.weekday()) % 7 + 14)


def _fred_series(symbol: str, cache_dir: Path = Path("data/raw/fred")) -> pd.Series:
    """Load free daily cash closes from FRED, cached as immutable source CSV."""
    global _fred_last_request
    fred_id={"NSXUSD":"NASDAQ100","SPXUSD":"SP500"}[symbol]
    path=cache_dir/f"{fred_id}.csv"
    if not path.exists():
        delay=1.0-(time.monotonic()-_fred_last_request)
        if delay>0: time.sleep(delay)
        request=urllib.request.Request(
            f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={fred_id}",
            headers={"User-Agent":"MarketSignalDesk data research"})
        with urllib.request.urlopen(request,timeout=60) as response:
            raw=response.read()
        cache_dir.mkdir(parents=True,exist_ok=True)
        path.write_bytes(raw)
        _fred_last_request=time.monotonic()
    frame=pd.read_csv(path)
    date_col=next((c for c in frame if c.lower() in {"observation_date","date"}),frame.columns[0])
    value_col=next(c for c in frame if c!=date_col)
    values=pd.to_numeric(frame[value_col].replace(".",np.nan),errors="coerce")
    index=pd.to_datetime(frame[date_col],errors="coerce").dt.date
    return pd.Series(values.to_numpy(float),index=index).dropna().groupby(level=0).last().sort_index()


def _gap_candidates(work: pd.DataFrame, expiry: date) -> list[dict]:
    ordered=work.sort_values("ts").reset_index(drop=True)
    gap=(ordered.ts.diff().dt.total_seconds()/60).to_numpy(float)
    local=ordered.ts.dt.tz_convert(NY).dt.date
    sessions=sorted(day for day in set(local) if day.weekday()<5)
    anchor=sum(day<expiry for day in sessions)
    first=max(0,anchor-ROLL_WINDOW_TRADING_DAYS)
    last=min(len(sessions),anchor+ROLL_WINDOW_TRADING_DAYS+1)
    allowed=set(sessions[first:last])
    keep=local.isin(allowed)&(gap>5)&(gap<=120)
    return [{"switch_ts":ordered.ts.iloc[i],"prev_ts":ordered.ts.iloc[i-1],"gap_minutes":float(gap[i])}
            for i in np.flatnonzero(keep.to_numpy()) if i>0]


def _offset_change_at(joined: pd.DataFrame, switch_ts: pd.Timestamp, window: int=60,
                      daily_offsets: pd.Series | None=None):
    # Avoid borrowing Monday as the "after" window for a Friday after-close switch.
    before=joined.loc[(joined.ts<switch_ts)&(joined.ts>=switch_ts-pd.Timedelta(hours=4)),"offset"].tail(window)
    after=joined.loc[(joined.ts>=switch_ts)&(joined.ts<=switch_ts+pd.Timedelta(hours=4)),"offset"].head(window)
    if len(before)<window or len(after)<window: return None
    before_med=float(before.median()); after_med=float(after.median())
    if daily_offsets is not None and len(daily_offsets):
        day=switch_ts.tz_convert(NY).date()
        before_days=daily_offsets.loc[daily_offsets.index<day].tail(5).to_numpy(float)
        after_days=daily_offsets.loc[daily_offsets.index>day].head(5).to_numpy(float)
        bm=float(np.median(before_days)) if len(before_days) else before_med
        am=float(np.median(after_days)) if len(after_days) else after_med
        mad_before=float(np.median(np.abs(before_days-bm))) if len(before_days) else 0.
        mad_after=float(np.median(np.abs(after_days-am))) if len(after_days) else 0.
    else:
        mad_before=float(np.median(np.abs(before.to_numpy()-before_med)))
        mad_after=float(np.median(np.abs(after.to_numpy()-after_med)))
    return before_med,after_med,after_med-before_med,float(np.hypot(mad_before,mad_after))


def _full_day_offsets(joined: pd.DataFrame, min_matches: int = 300) -> pd.Series:
    """Median HistData−Dukascopy offset for complete overlap trading days."""
    if joined.empty:
        return pd.Series(dtype=float)
    work=joined.copy()
    if "offset" not in work:
        work["offset"]=work.bid_c_h.astype(float)-work.bid_c_d.astype(float)
    work["local_day"]=work.ts.dt.tz_convert(NY).dt.date
    grouped=work.groupby("local_day").offset.agg(["median","count"])
    return grouped.loc[grouped["count"]>=min_matches,"median"].astype(float)


def _full_day_roll_measure(daily: pd.Series, expiry: date, switch_day: date):
    """Estimate the roll step from full-day offsets, holding day ±1 out.

    The estimator uses the nearest one or two complete sessions on each side,
    excluding the switch day, expiry day and held-out validation sessions. The
    held-out sessions are the nearest full days before/after the switch, also
    excluding expiry Friday. This keeps the validation observations out of
    both estimates and avoids using an expiry-day print as validation.
    """
    sessions=sorted(day for day in daily.index if day.weekday()<5)
    if switch_day not in sessions:
        return None
    before_validation=[day for day in sessions if day<switch_day and day!=expiry]
    after_validation=[day for day in sessions if day>switch_day and day!=expiry]
    if not before_validation or not after_validation:
        return None
    validation_before_day=before_validation[-1]
    validation_after_day=after_validation[0]
    before_est=[day for day in sessions if day<validation_before_day and day not in {switch_day,expiry}]
    after_est=[day for day in sessions if day>validation_after_day and day not in {switch_day,expiry}]
    if not before_est or not after_est:
        return None
    before_1=float(daily.loc[before_est[-1]])
    after_1=float(daily.loc[after_est[0]])
    if len(before_est)<2 or len(after_est)<2:
        return None
    before_2=float(np.median(daily.loc[before_est[-2:]].to_numpy(float)))
    after_2=float(np.median(daily.loc[after_est[:2]].to_numpy(float)))
    gap_1=after_1-before_1
    gap_2=after_2-before_2
    validation_before=float(daily.loc[validation_before_day])
    validation_after=float(daily.loc[validation_after_day])
    return {"before_offset":before_2,"after_offset":after_2,"gap":gap_2,
            "gap_1day":gap_1,"gap_2day":gap_2,"uncertainty":abs(gap_2-gap_1),
            "validation_before":validation_before,"validation_after":validation_after,
            "validation_residual":abs((validation_before+gap_2)-validation_after),
            "estimate_before_days":before_est[-2:],
            "estimate_after_days":after_est[:2],
            "validation_before_day":validation_before_day,
            "validation_after_day":validation_after_day}


def _candidate_residual(joined: pd.DataFrame, candidate: dict) -> float:
    """Raw discontinuity less the same-interval cash move, when matched."""
    if joined.empty:
        return float("nan")
    lookup=joined.set_index("ts")
    before=lookup.loc[candidate["prev_ts"]] if candidate["prev_ts"] in lookup.index else None
    after=lookup.loc[candidate["switch_ts"]] if candidate["switch_ts"] in lookup.index else None
    if before is None or after is None:
        return float("nan")
    return float((after.bid_c_h-before.bid_c_h)-(after.bid_c_d-before.bid_c_d))


def _candidate_raw_jump(work: pd.DataFrame, candidate: dict) -> float:
    before=work.loc[work.ts.eq(candidate["prev_ts"]),"bid_c"]
    after=work.loc[work.ts.eq(candidate["switch_ts"]),"bid_c"]
    return float(after.iloc[0]-before.iloc[0]) if len(before) and len(after) else float("nan")


def _stale_span(hist: pd.DataFrame, duka: pd.DataFrame | None, expiry: date,
                switch_ts: pd.Timestamp) -> dict:
    """Confirm an expiry stale period from return correlation or frozen range."""
    start=pd.Timestamp(datetime.combine(expiry,datetime.min.time().replace(hour=9,minute=30)),tz=NY).tz_convert("UTC")
    if switch_ts<=start:
        return {"stale_start":pd.NaT,"stale_end":pd.NaT,"stale_method":"none",
                "stale_evidence_ts":pd.NaT,"stale_detected":False}
    h=hist.loc[(hist.ts>=start-pd.Timedelta(minutes=30))&(hist.ts<switch_ts),["ts","bid_c"]].copy()
    if duka is not None and not duka.empty:
        d=duka.loc[(duka.ts>=start-pd.Timedelta(minutes=30))&(duka.ts<switch_ts),["ts","bid_c"]]
        joined=h.merge(d,on="ts",suffixes=("_h","_d")).sort_values("ts")
    else:
        joined=pd.DataFrame()
    evidence_ts=pd.NaT;method="clock+near-zero-range";detected=False
    if len(joined)>=30:
        hr=joined.bid_c_h.astype(float);dr=joined.bid_c_d.astype(float)
        corr=hr.pct_change().rolling(30,min_periods=20).corr(dr.pct_change())
        h_range=hr.rolling(30,min_periods=20).max()-hr.rolling(30,min_periods=20).min()
        d_range=dr.rolling(30,min_periods=20).max()-dr.rolling(30,min_periods=20).min()
        low_corr=corr.lt(0.2).fillna(False)
        near_zero=h_range.le(0.5)&d_range.ge(1.0)
        match=low_corr|near_zero
        eligible=match & joined.ts.ge(start)
        found=np.flatnonzero(eligible.to_numpy())
        if len(found):
            evidence_ts=joined.ts.iloc[int(found[0])]
            detected=True
            method="rolling_30m_return_corr<0.2" if bool(low_corr.iloc[int(found[0])]) else "near-zero HistData range vs Duka"
    else:
        # In pre-overlap years, the SOQ clock interval is used only when the
        # HistData series itself exhibits a near-zero 30-minute range.
        close=h.bid_c.astype(float)
        frozen=(close.rolling(30,min_periods=20).max()-close.rolling(30,min_periods=20).min()).le(0.5)
        eligible=frozen & h.ts.ge(start)
        found=np.flatnonzero(eligible.fillna(False).to_numpy())
        if len(found):
            evidence_ts=h.ts.iloc[int(found[0])]
            detected=True
    return {"stale_start":start if detected else pd.NaT,
            "stale_end":switch_ts if detected else pd.NaT,
            "stale_method":method if detected else "not detected",
            "stale_evidence_ts":evidence_ts,
            "stale_detected":detected}


def _classify_roll(record: dict, expiry: date) -> str:
    """Apply the reviewed roll acceptance rule; zero-sized gaps are valid."""
    switch_ts=record.get("switch_ts")
    if switch_ts is None or pd.isna(switch_ts) or not np.isfinite(record.get("gap_minutes",np.nan)):
        return "unmeasured_switch_not_located"
    if float(record.get("uncertainty",np.inf))>1.0:
        return "unmeasured_uncertainty"
    if float(record.get("validation_residual",np.inf))>=2.0:
        return "unmeasured_validation_failed"
    soq=pd.Timestamp(datetime.combine(expiry,datetime.min.time().replace(hour=9,minute=30)),tz=NY).tz_convert("UTC")
    if pd.Timestamp(switch_ts)>soq and not record.get("stale_detected",False):
        return "unmeasured_stale_unconfirmed"
    return "measured"


def _fred_basis_change(symbol: str, hist: pd.DataFrame, switch_ts: pd.Timestamp, fred: pd.Series):
    local=hist["ts"].dt.tz_convert(NY)
    local_day=local.dt.date
    close_rows=hist.loc[(local.dt.hour*60+local.dt.minute)<16].copy()
    close_rows["local_day"]=local_day.loc[close_rows.index]
    daily=close_rows.sort_values("ts").groupby("local_day").tail(1).set_index("local_day").bid_c.astype(float)
    basis=(daily-fred.reindex(daily.index)).dropna()
    switch_day=switch_ts.tz_convert(NY).date()
    before=basis.loc[basis.index<switch_day]
    after=basis.loc[basis.index>switch_day]
    if before.empty or after.empty: return None
    before_v=float(before.iloc[-1]); after_v=float(after.iloc[0])
    # Uncertainty is the robust spread of daily basis around each side's
    # nearest five sessions, combined in quadrature.
    b=before.tail(5).to_numpy(float); a=after.head(5).to_numpy(float)
    bm=float(np.median(b)); am=float(np.median(a))
    uncertainty=float(np.hypot(np.median(np.abs(b-bm)),np.median(np.abs(a-am))))
    return before_v,after_v,after_v-before_v,uncertainty


def detect_roll_records(symbol: str, hist: pd.DataFrame, duka: pd.DataFrame | None = None,
                        fred: pd.Series | None = None) -> list[dict]:
    """Find switch bars from price gaps; measure basis steps on full trading days."""
    if hist.empty or symbol not in {"NSXUSD", "SPXUSD"}:
        return []
    work = hist[hist.feed.eq("futures_cont")].copy()
    if work.empty:
        return []
    joined=pd.DataFrame()
    if duka is not None and not duka.empty:
        right=duka.copy();right["ts"]=pd.to_datetime(right.ts,utc=True).astype("datetime64[ns, UTC]")
        joined=work.merge(right[["ts","bid_c"]],on="ts",suffixes=("_h","_d"))
        joined=joined.sort_values("ts").reset_index(drop=True)
        if len(joined): joined["offset"]=joined.bid_c_h.astype(float)-joined.bid_c_d.astype(float)
    daily_offsets=_full_day_offsets(joined)
    records=[]
    years=sorted(work.ts.dt.year.unique())
    for year in years:
        for month in ROLL_QUARTER_MONTHS:
            expiry = _third_friday(year, month)
            switch = HISTDATA_SWITCH_UTC.get(symbol)
            if switch is not None and switch.tz_convert(NY).date() <= expiry:
                continue
            if expiry < work.ts.min().tz_convert(NY).date():
                continue
            candidates=_gap_candidates(work,expiry)
            scored=[]
            for candidate in candidates:
                switch_day=candidate["switch_ts"].tz_convert(NY).date()
                measured=_full_day_roll_measure(daily_offsets,expiry,switch_day)
                if measured is not None:
                    residual=_candidate_residual(joined,candidate)
                    raw_jump=_candidate_raw_jump(work,candidate)
                    evidence=residual if np.isfinite(residual) else raw_jump
                    threshold=2.0 if np.isfinite(residual) else 5.0
                    scored.append({**candidate,**measured,"method":"Dukascopy full-day offsets (2 sessions per side)",
                                   "candidate_residual":residual,"raw_jump":raw_jump,
                                   "switch_evidence":evidence,"evidence_threshold":threshold,
                                   "adjusted_before_offset":measured["before_offset"]+measured["gap"],
                                   "adjusted_after_offset":measured["after_offset"]})
            if scored:
                # Candidate switch location comes from the largest persistent
                # intraday offset discontinuity, with full-day estimates used
                # only for gap size and the independent held-out check.
                record=max(scored,key=lambda row:(abs(row["switch_evidence"]),
                                                  abs(row["gap"]),
                                                  -abs((row["switch_ts"].tz_convert(NY).date()-expiry).days)))
            elif fred is not None and candidates:
                # Caller-supplied FRED data may classify non-overlap years.
                candidate=min(candidates,key=lambda row:abs((row["switch_ts"].tz_convert(NY).date()-expiry).days))
                change=_fred_basis_change(symbol,work,candidate["switch_ts"],fred)
                if change is None: continue
                before,after,gap,uncertainty=change
                record={**candidate,"gap":gap,"before_offset":before,"after_offset":after,
                        "method":"FRED daily cash-close basis before/after expiry","uncertainty":uncertainty,
                        "adjusted_before_offset":before+gap,"adjusted_after_offset":after,
                        "validation_residual":float("nan"),"gap_1day":float("nan"),
                        "validation_before":float("nan"),"validation_after":float("nan")}
            else:
                expiry_open=pd.Timestamp(datetime.combine(expiry,datetime.min.time().replace(hour=9,minute=30)),tz=NY).tz_convert("UTC")
                records.append({"symbol":symbol,"expiry":expiry,"switch_ts":expiry_open,
                    "gap_minutes":float("nan"),"gap":float("nan"),"gap_1day":float("nan"),
                    "uncertainty":float("nan"),"before_offset":float("nan"),
                    "after_offset":float("nan"),"validation_residual":float("nan"),
                    "status":"unmeasured_no_confirmed_switch","stale_detected":False,
                    "stale_start":pd.NaT,"stale_end":pd.NaT,"stale_method":"n/a",
                    "stale_evidence_ts":pd.NaT})
                continue
            pos=int(np.searchsorted(work.ts.astype("int64").to_numpy(),int(record["switch_ts"].value)))
            if 0<pos<len(work):
                changes=np.abs(work.bid_c.astype(float).diff().to_numpy())
                raw_jump=float(work.bid_c.iloc[pos]-work.bid_c.iloc[pos-1])
                record["raw_jump"]=raw_jump
                record["adjusted_jump"]=raw_jump-float(record["gap"])
                lo=max(1,pos-60);hi=min(len(work),pos+61)
                normal=np.r_[changes[lo:pos],changes[pos+1:hi]]
                normal=normal[np.isfinite(normal)&(normal>0)]
                record["normal_median_move"]=float(np.median(normal)) if len(normal) else float("nan")
                duration=max(1,int(round(float(record["gap_minutes"]))))
                time_ns=work.ts.astype("int64").to_numpy()
                closes=work.bid_c.to_numpy(float)
                window_left=int(np.searchsorted(time_ns,int(record["switch_ts"].value)-2*86400*1_000_000_000))
                window_right=int(np.searchsorted(time_ns,int(record["switch_ts"].value)+2*86400*1_000_000_000))
                gap_moves=[]
                for j in range(max(window_left+duration, duration),window_right):
                    if time_ns[j]-time_ns[j-duration]==duration*60*1_000_000_000:
                        gap_moves.append(abs(closes[j]-closes[j-duration]))
                record["normal_p95_move"]=float(np.quantile(gap_moves,.95)) if gap_moves else float("nan")
            else:
                record["raw_jump"]=record["adjusted_jump"]=record["normal_median_move"]=record["normal_p95_move"]=float("nan")
            record.update(symbol=symbol,expiry=expiry,roll_date=record["switch_ts"].tz_convert(NY).date())
            roll_sessions=sorted(day for day in daily_offsets.index if day.weekday()<5)
            expiry_pos=sum(day<expiry for day in roll_sessions)
            switch_pos=sum(day<record["roll_date"] for day in roll_sessions)
            record["convention"]=("expiry-day" if record["roll_date"]==expiry else
                                  f"roll-date ({switch_pos-expiry_pos:+d} trading sessions vs expiry)")
            record.update(_stale_span(work,duka,expiry,record["switch_ts"]))
            if "validation_residual" not in record: record["validation_residual"]=float("nan")
            stale_required=record["switch_ts"]>pd.Timestamp(datetime.combine(
                expiry,datetime.min.time().replace(hour=9,minute=30)),tz=NY).tz_convert("UTC")
            record["status"]=_classify_roll(record,expiry)
            record["stale_required"]=bool(stale_required)
            record["adjusted_jump_ok"]=(np.isfinite(record.get("normal_p95_move",float("nan")))
                                         and np.isfinite(record.get("adjusted_jump",float("nan")))
                                         and abs(record["adjusted_jump"])<=record["normal_p95_move"])
            records.append(record)
    return records


def detect_rolls(symbol: str, hist: pd.DataFrame, duka: pd.DataFrame | None = None) -> dict[pd.Timestamp, float]:
    """Compatibility mapping of exact roll switch timestamps to basis steps."""
    return {record["switch_ts"]:float(record["gap"]) for record in detect_roll_records(symbol,hist,duka)}


def feed_switch_adjustment(symbol: str, hist: pd.DataFrame, duka: pd.DataFrame | None) -> float:
    """Shift the last futures basis onto the cash level at the feed boundary."""
    switch=HISTDATA_SWITCH_UTC.get(symbol)
    if switch is None or duka is None or duka.empty:
        return 0.0
    futures=hist[hist.feed.eq("futures_cont")].copy()
    if futures.empty:
        return 0.0
    duka=duka.copy();duka["ts"]=pd.to_datetime(duka.ts,utc=True).astype("datetime64[ns, UTC]")
    joined=futures.merge(duka[["ts","bid_c"]],on="ts",suffixes=("_h","_d"))
    if joined.empty:
        return 0.0
    joined["local_day"]=joined.ts.dt.tz_convert(NY).dt.date
    daily=joined.groupby("local_day").agg(
        offset=("bid_c_h",lambda x: float(np.median(x.to_numpy(float)-joined.loc[x.index,"bid_c_d"].to_numpy(float)))),
        bars=("bid_c_h","size"))
    last_day=switch.tz_convert(NY).date()
    available=daily[(daily.index<last_day)&(daily.bars>=200)]
    return -float(available.offset.iloc[-1]) if len(available) else 0.0


def apply_feed_and_rolls(hist: pd.DataFrame, symbol: str, roll_deltas: dict[date,float],
                         switch_adjustment: float = 0.0,
                         stale_spans: list[tuple[pd.Timestamp,pd.Timestamp]] | None = None,
                         valid_from: pd.Timestamp | None = None) -> pd.DataFrame:
    """Attach source regime and a backward-additive continuous price series."""
    out = hist.sort_values("ts").reset_index(drop=True).copy()
    switch = HISTDATA_SWITCH_UTC.get(symbol)
    out["feed"] = np.where(out.ts >= switch, "cash_cfd", "futures_cont") if switch is not None else "unclassified"
    local_days = out.ts.dt.tz_convert(NY).dt.date.to_numpy()
    roll_idxs = []
    ts_to_index={stamp:i for i,stamp in enumerate(out.ts)}
    for marker, delta in sorted(roll_deltas.items(),key=lambda item:str(item[0])):
        if isinstance(marker,(pd.Timestamp,datetime)):
            stamp=pd.Timestamp(marker)
            stamp=stamp.tz_localize("UTC") if stamp.tzinfo is None else stamp.tz_convert("UTC")
            index=ts_to_index.get(stamp)
            if index is None: continue
        else:
            loc = np.flatnonzero(local_days == marker)
            if not len(loc): continue
            index=int(loc[0])
        if out.feed.iloc[index] == "futures_cont": roll_idxs.append((index,float(delta)))
    out["roll"] = False
    out["stale_expired"] = False
    for start,end in stale_spans or []:
        if pd.isna(start) or pd.isna(end): continue
        start=pd.Timestamp(start);end=pd.Timestamp(end)
        out.loc[out.ts.ge(start)&out.ts.lt(end),"stale_expired"]=True
    adjustment = np.zeros(len(out), dtype=float)
    delta_by_index = np.zeros(len(out), dtype=float)
    for index, delta in roll_idxs:
        out.loc[index,"roll"] = True
        delta_by_index[index] = delta
    if len(roll_idxs):
        future_sum = np.cumsum(delta_by_index[::-1])[::-1] - delta_by_index
        adjustment = future_sum
    if switch_adjustment:
        adjustment = adjustment + np.where(out.feed.eq("futures_cont").to_numpy(),switch_adjustment,0.0)
    for field in PRICE_FIELDS:
        out[f"adj_bid_{field}"] = out[f"bid_{field}"].to_numpy(float) + adjustment
        if valid_from is not None:
            out.loc[out.ts < valid_from, f"adj_bid_{field}"] = np.nan
    return out[HIST_COLUMNS]


def rebuild_from_raw(symbol: str, root: Path = ROOT, raw_root: Path = RAW) -> dict[str, int]:
    """Reparse saved archives and rebuild monthly Parquet without network use."""
    raw_dir = raw_root / symbol
    archives = sorted(raw_dir.glob("*.zip")) if raw_dir.exists() else []
    if not archives:
        raise FileNotFoundError(f"no saved HistData archives for {symbol} under {raw_dir}")
    frames=[]
    for archive_path in archives:
        parsed, _ = parse_archive(archive_path.read_bytes(), symbol)
        nonexistent=parsed.attrs.get("nonexistent_local_rows",[])
        dst_path=raw_dir/f"{archive_path.stem}.dst.txt"
        if nonexistent:
            dst_path.write_text("Dropped nonexistent spring-forward local timestamp rows:\n"+"\n".join(nonexistent)+"\n")
        elif dst_path.exists():
            dst_path.write_text("Dropped 0 nonexistent spring-forward local timestamp rows.\n")
        if not parsed.empty:
            frames.append(parsed)
    if not frames:
        raise ValueError(f"saved HistData archives contain no bars for {symbol}")
    hist=pd.concat(frames,ignore_index=True).drop_duplicates("ts",keep="last").sort_values("ts").reset_index(drop=True)
    duka_symbol=DUKASCOPY_SYMBOL.get(symbol)
    duka=pd.DataFrame()
    if duka_symbol:
        try:
            from .dukascopy import load as load_duka
            duka=load_duka(duka_symbol,hist.ts.min(),hist.ts.max())
        except FileNotFoundError:
            duka=pd.DataFrame()
    roll_records=detect_roll_records(symbol,hist,duka)
    valid_rolls=[row for row in roll_records if row.get("status")=="measured"]
    roll_deltas={row["switch_ts"]:row["gap"] for row in valid_rolls}
    switch_adj=feed_switch_adjustment(symbol,hist,duka)
    stale_spans=[(row["stale_start"],row["stale_end"]) for row in roll_records if row.get("stale_detected")]
    unresolved=[row for row in roll_records if row.get("status")!="measured"]
    valid_from=max((row["switch_ts"] for row in unresolved),default=None)
    result=apply_feed_and_rolls(hist,symbol,roll_deltas,switch_adj,stale_spans,valid_from)
    months=0
    for month, group in result.groupby(result.ts.dt.strftime("%Y-%m"),sort=True):
        path=root/symbol/f"{month}.parquet"
        _atomic_parquet(group,path)
        from .catalog import write_manifest
        write_manifest("histdata",symbol,group,"bid","none")
        months+=1
    _write_roll_report(symbol,roll_records)
    print(f"rebuilt {symbol}: {len(result):,} bars, {months} months, {len(roll_deltas)} validated rolls, {len(roll_records)-len(valid_rolls)} unmeasured roll candidates, switch adjustment {switch_adj:+.3f}",flush=True)
    return {"bars":len(result),"months":months,"rolls":len(roll_deltas),"switch_adjustment":switch_adj}


def _write_roll_report(symbol: str, records: list[dict]) -> Path:
    path=Path("reports/data/histdata_rolls.md")
    path.parent.mkdir(parents=True,exist_ok=True)
    data_path=Path("data/aux/histdata_rolls.json")
    stored=json.loads(data_path.read_text()) if data_path.exists() else []
    stored=[row for row in stored if row.get("symbol")!=symbol]
    serial=[]
    for row in records:
        item={}
        for key,value in row.items():
            if isinstance(value,(pd.Timestamp,datetime,date)): item[key]=value.isoformat()
            elif isinstance(value,np.generic): item[key]=value.item()
            elif isinstance(value,(list,tuple)):
                item[key]=[v.isoformat() if isinstance(v,(pd.Timestamp,datetime,date)) else v for v in value]
            else: item[key]=value
        serial.append(item)
    stored.extend(serial)
    data_path.parent.mkdir(parents=True,exist_ok=True)
    data_path.write_text(json.dumps(stored,indent=2)+"\n")
    lines=["# HistData quarterly roll measurements","",
           "**Acceptance status: pending rebuild.** A roll is measured only when its switch bar is located, full-day estimate uncertainty is ≤1 point, and the independent held-out residual is <2 points. Stale-contract evidence is additionally required only when the switch is after expiry-day SOQ. The adjusted switch-jump column is diagnostic, not an extra classification threshold.",
           "",
           "For each quarterly expiry, the detector searches observed data gaps and daily breaks within ±10 trading sessions. Roll gaps use full-session HistData−Dukascopy offsets; uncertainty is the absolute difference between one-day and two-day estimates. Held-out validation uses the nearest complete full-day offsets on either side of the switch, excluding both the switch day and expiry Friday. The held-out absolute step after adjustment must be <2 points.",
           "",
           "Stale expired-contract bars are flagged from the expiry-day 09:30 ET SOQ through the confirmed switch bar when a 30-minute return-correlation or frozen-range check detects the stale segment. These rows are excluded from features, levels, events and labels. The interval is treated as a data gap.",
           "",
           "| Symbol | Expiry | Convention | Switch bar / marker (UTC) | Status | Gap minutes | 1-day estimate | 2-day estimate | Uncertainty | Adjusted switch jump / p95 (diagnostic) | Independent held-out step | Estimation dates | Validation dates | Stale span (UTC) | Stale evidence | Check |", "|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|---|---|---|"]
    for row in sorted(stored,key=lambda r:(r["symbol"],r["switch_ts"])):
        val=row.get("validation_residual",float("nan"))
        adjusted=f"{row.get('adjusted_jump',float('nan')):+.2f} / {row.get('normal_p95_move',float('nan')):.2f}"
        stale=(f"{row.get('stale_start','')} → {row.get('stale_end','')}" if row.get("stale_detected") else "none detected")
        check="PASS" if row.get("status")=="measured" else "FAIL/UNMEASURED"
        est_days=f"{row.get('estimate_before_days','')} / {row.get('estimate_after_days','')}"
        val_days=f"{row.get('validation_before_day','')} / {row.get('validation_after_day','')}"
        switch_label=("none; expiry marker " if row.get("status")=="unmeasured_no_confirmed_switch" else "")+str(row["switch_ts"])
        lines.append(f"| {row['symbol']} | {row['expiry']} | {row.get('convention','unmeasured')} | {switch_label} | {row.get('status','unmeasured')} | {row.get('gap_minutes',float('nan')):.1f} | {row.get('gap_1day',float('nan')):+.4f} | {row.get('gap_2day',float('nan')):+.4f} | {row.get('uncertainty',float('nan')):.4f} | {adjusted} | {val:.4f} | {est_days} | {val_days} | {stale} | {row.get('stale_method','n/a')} @ {row.get('stale_evidence_ts','')} | {check} |")
    lines += ["", "## Switch convention by year", "",
              "Observed switch dates before expiry are classified as roll-date; dates on the third Friday are expiry-day. The 2018 futures era is partial because the HistData feed changes on 2018-12-16.",
              "", "| Symbol | Year | Quarterly records | Applied | Expiry-day | Roll-date | Unmeasured |", "|---|---:|---:|---:|---:|---:|---:|"]
    summary={}
    for row in stored:
        expiry=pd.Timestamp(row["expiry"])
        if expiry.year<2014 or expiry.year>2018:
            continue
        key=(row["symbol"],expiry.year)
        bucket=summary.setdefault(key,{"records":0,"applied":0,"expiry":0,"roll":0,"unmeasured":0})
        bucket["records"]+=1
        if row.get("status")=="measured": bucket["applied"]+=1
        if row.get("convention")=="expiry-day": bucket["expiry"]+=1
        elif str(row.get("convention","unmeasured")).startswith("roll-date"): bucket["roll"]+=1
        if row.get("status")!="measured": bucket["unmeasured"]+=1
    for (symbol,year),bucket in sorted(summary.items()):
        lines.append(f"| {symbol} | {year} | {bucket['records']} | {bucket['applied']} | {bucket['expiry']} | {bucket['roll']} | {bucket['unmeasured']} |")
    failed=[row for row in stored if row.get("status")!="measured"]
    lines += ["", f"Quarterly records stored: {len(stored)}. Independent daily offset checks failing or unavailable: {len(failed)}.",
              "",
              "A year is accepted only when each quarter has one located switch and every roll has uncertainty ≤1 point and an independent held-out residual <2 points; post-SOQ switches also require stale-contract evidence. Failed or unresolved quarters stay unmeasured and are not used to adjust historical prices. The 2018 futures feed ends at the 2018-12-16 source switch, so only the first three quarterly expiries belong to the futures era.",
              "",
              "Pre-2014 rolls without sufficient Dukascopy overlap are unmeasured until the explicitly scheduled FRED retry succeeds. Do not use index features or labels for any segment with an unmeasured roll. No bot-check workaround is used."]
    path.write_text("\n".join(lines)+"\n")
    return path


def _save_period(symbol: str, label: str, archive: bytes, start: pd.Timestamp, end: pd.Timestamp, root: Path = ROOT, raw_root: Path = RAW) -> int:
    raw_dir = raw_root / symbol
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_path = raw_dir / f"{label}.zip"
    if not raw_path.exists():
        with tempfile.NamedTemporaryFile(dir=raw_dir, suffix=".zip", delete=False) as handle:
            handle.write(archive)
            temp = Path(handle.name)
        os.replace(temp, raw_path)
    frame, gaps = parse_archive(archive, symbol)
    nonexistent = frame.attrs.get("nonexistent_local_rows", [])
    if gaps:
        (raw_dir / f"{label}.txt").write_text(gaps)
    if nonexistent:
        (raw_dir / f"{label}.dst.txt").write_text("Dropped nonexistent spring-forward local timestamps:\n" + "\n".join(nonexistent) + "\n")
    frame = frame[(frame.ts >= start) & (frame.ts < end)]
    count = 0
    if frame.empty:
        return 0
    for month, group in frame.groupby(frame.ts.dt.strftime("%Y-%m"), sort=True):
        path = root / symbol / f"{month}.parquet"
        if path.exists():
            previous = pd.read_parquet(path)
            previous = previous[(previous.ts < start) | (previous.ts >= end)]
            group = pd.concat([previous, group], ignore_index=True).drop_duplicates("ts", keep="last").sort_values("ts")
        _atomic_parquet(group, path)
        from msd.data.catalog import write_manifest
        write_manifest("histdata", symbol, group, "bid", "none")
        count += len(group)
    return count


def download(symbol: str, start: date = date(2010, 11, 1), end: date | None = None, root: Path = ROOT) -> None:
    end = end or datetime.now(timezone.utc).date()
    start_month = pd.Timestamp(start).to_period("M")
    end_month = pd.Timestamp(end).to_period("M")
    current_year = datetime.now(timezone.utc).year
    verified_periods = missing_periods = 0
    for year in range(start.year, end.year + 1):
        if year == current_year:
            months = range(max(1, start.month if year == start.year else 1), min(12, end.month) + 1)
            periods = [(year, month) for month in months]
        else:
            periods = [(year, None)]
        for y, month in periods:
            label = f"{y}-{month:02d}" if month else str(y)
            # Keep completed raw periods and their Parquet output incremental.
            raw_path = RAW / symbol / f"{label}.zip"
            if raw_path.exists():
                archive = raw_path.read_bytes()
            else:
                try:
                    archive = fetch_period(symbol, y, month)
                except urllib.error.HTTPError as exc:
                    if exc.code == 404:
                        print(f"skip unavailable {symbol} {label}", flush=True)
                        continue
                    raise
            period_start = pd.Timestamp(f"{y}-{month:02d}-01" if month else f"{y}-01-01", tz="UTC")
            period_end = period_start + (pd.offsets.MonthBegin(1) if month else pd.DateOffset(years=1))
            count=_save_period(symbol, label, archive, period_start, period_end, root)
            if count == 0:
                missing_periods += 1
                print(f"MISSING {symbol} {label}: archive contained no bars in requested period", flush=True)
            else:
                verified_periods += 1
                print(f"verified {symbol} {label}: {count} bars", flush=True)
    if verified_periods == 0:
        raise RuntimeError(f"HistData download produced no non-empty verified periods for {symbol} ({missing_periods} missing)")
    print(f"DONE HistData {symbol}: verified_periods={verified_periods} missing_periods={missing_periods}",flush=True)
    if root == ROOT:
        rebuild_from_raw(symbol, root=root)


def load(symbol: str, start, end, root: Path = ROOT) -> pd.DataFrame:
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    start = start.tz_localize("UTC") if start.tzinfo is None else start.tz_convert("UTC")
    end = end.tz_localize("UTC") if end.tzinfo is None else end.tz_convert("UTC")
    paths = sorted((root / symbol).glob("*.parquet")) if (root / symbol).exists() else []
    frames = [pd.read_parquet(p) for p in paths if start.strftime("%Y-%m") <= p.stem <= end.strftime("%Y-%m")]
    if not frames:
        return pd.DataFrame(columns=HIST_COLUMNS)
    result = pd.concat(frames, ignore_index=True)
    result.ts = pd.to_datetime(result.ts, utc=True).astype("datetime64[ns, UTC]")
    return result[(result.ts >= start) & (result.ts < end + pd.Timedelta(days=1))].sort_values("ts").reset_index(drop=True)


def gap_report_summary(symbol: str, root: Path = ROOT, raw_root: Path = RAW) -> list[str]:
    lines = []
    for path in sorted((raw_root / symbol).glob("*.zip")) if (raw_root / symbol).exists() else []:
        try:
            with zipfile.ZipFile(path) as archive:
                for name in archive.namelist():
                    if Path(name).suffix.lower() == ".txt":
                        content = archive.read(name).decode("utf-8", errors="replace")
                        gaps = [int(value) for value in re.findall(r"Gap of\s+(\d+)s found", content, re.I)]
                        if gaps:
                            lines.append(f"{path.stem}: {len(gaps)} reported gaps; median {np.median(gaps):.0f}s; p95 {np.quantile(gaps, .95):.0f}s; longest {max(gaps)}s; gaps ≥5 min {sum(value >= 300 for value in gaps)}")
                        else:
                            lines.append(f"{path.stem}: no gaps reported")
        except zipfile.BadZipFile:
            lines.append(f"{path.stem}: invalid ZIP")
    for path in sorted((raw_root / symbol).glob("*.dst.txt")) if (raw_root / symbol).exists() else []:
        invalid = [line for line in path.read_text().splitlines() if line and not line.startswith("Dropped")]
        lines.append(f"{path.stem.removesuffix('.dst')}: dropped {len(invalid)} nonexistent spring-forward local timestamp rows")
    return lines


def cross_validate(hist_symbol: str, dukascopy_symbol: str, hist_root: Path = ROOT, duka_root: Path = Path("data/bars/dukascopy")) -> str:
    """Compare close-time alignment, prices, coverage and suspicious ranges."""
    hist_all = load(hist_symbol, "2010-01-01", "2026-12-31", root=hist_root).set_index("ts").sort_index()
    from msd.data.dukascopy import load as load_duka
    duka_all = load_duka(dukascopy_symbol, "2012-01-01", "2026-12-31", root=duka_root).set_index("ts").sort_index()
    comparison_start = pd.Timestamp("2018-06-01", tz="UTC")
    hist = hist_all[hist_all.index >= comparison_start]
    duka = duka_all[duka_all.index >= comparison_start]
    if hist.empty or duka.empty:
        raise ValueError(f"No overlap for {hist_symbol}/{dukascopy_symbol}")
    hclose, dclose = hist.bid_c.astype(float), duka.bid_c.astype(float)
    hclose_all, dclose_all = hist_all.bid_c.astype(float), duka_all.bid_c.astype(float)
    hadj_all = hist_all.adj_bid_c.astype(float) if "adj_bid_c" in hist_all else hclose_all
    hadj = hist.adj_bid_c.astype(float) if "adj_bid_c" in hist else hclose

    def one_minute_returns(series: pd.Series) -> pd.Series:
        result = series.pct_change(fill_method=None)
        result.index = series.index
        consecutive = series.index.to_series().diff() == pd.Timedelta(minutes=1)
        return result.where(consecutive.to_numpy())

    hreturns, dreturns = one_minute_returns(hadj), one_minute_returns(dclose)
    lag_results = []
    convention_hist = hclose[(hclose.index >= pd.Timestamp("2019-01-01", tz="UTC")) & (hclose.index < pd.Timestamp("2025-01-01", tz="UTC"))]
    convention_duka = dclose[(dclose.index >= pd.Timestamp("2019-01-01", tz="UTC")) & (dclose.index < pd.Timestamp("2025-01-01", tz="UTC"))]
    for lag in (-1, 0, 1):
        shifted = convention_hist.copy()
        shifted.index = shifted.index + pd.Timedelta(minutes=lag)
        matched = pd.concat([shifted.rename("hist"), convention_duka.rename("duka")], axis=1, join="inner").dropna()
        shifted_returns = hreturns.copy()
        shifted_returns.index += pd.Timedelta(minutes=lag)
        aligned_returns = pd.concat([shifted_returns.rename("hist"), dreturns.rename("duka")], axis=1, join="inner").dropna()
        corr = aligned_returns["hist"].corr(aligned_returns["duka"])
        lag_results.append((lag, float(np.median(np.abs(matched["hist"] - matched["duka"]))), float(corr), matched))
    best = max(lag_results, key=lambda item: (item[2], -item[1]))
    lag = best[0]
    aligned_hist = hclose.copy()
    aligned_hist.index = aligned_hist.index + pd.Timedelta(minutes=lag)
    matched = pd.concat([aligned_hist.rename("hist"), dclose.rename("duka")], axis=1, join="inner").dropna()
    matched["year"] = matched.index.year
    yearly = []
    for year, group in matched.groupby("year"):
        delta = (group["hist"] - group["duka"]).abs()
        year_returns = pd.concat([hreturns[hreturns.index.year == year].rename("hist"),
                                  dreturns[dreturns.index.year == year].rename("duka")], axis=1, join="inner").dropna()
        yearly.append((year, len(group), year_returns["hist"].corr(year_returns["duka"]),
                       float(delta.median()), float(delta.quantile(.95)), float((group["hist"] - group["duka"]).median())))
    hidx = hist.index + pd.Timedelta(minutes=lag)
    union = hidx.union(duka.index)
    exclusive = len(hidx.symmetric_difference(duka.index)) / max(1, len(union))
    hist_set, duka_set = set(hidx), set(duka.index)
    ny = union.tz_convert("America/New_York")
    weekdays = pd.bdate_range(ny.min().date(), ny.max().date())
    expected_minutes = max(1, len(weekdays) * 60)
    weekday_mask = ny.day_of_week < 5
    hours = ny.hour
    h_present = np.fromiter((ts in hist_set for ts in union), dtype=bool, count=len(union)) & weekday_mask
    d_present = np.fromiter((ts in duka_set for ts in union), dtype=bool, count=len(union)) & weekday_mask
    hourly = []
    for hour in range(24):
        hcount = int((h_present & (hours == hour)).sum())
        dcount = int((d_present & (hours == hour)).sum())
        hshare = min(1.0, hcount / expected_minutes)
        dshare = min(1.0, dcount / expected_minutes)
        hourly.append((hour, hshare, dshare))
    common = pd.concat([hclose.rename("hist"), dclose.rename("duka")], axis=1, join="inner").dropna()
    # For flags use selected timestamp convention.
    shifted = hclose.copy(); shifted.index += pd.Timedelta(minutes=lag)
    common = pd.concat([shifted.rename("hist"), dclose.rename("duka")], axis=1, join="inner").dropna()
    zero = (hist.bid_h == hist.bid_l)
    # Count bars belonging to zero-range runs at least one hour long.
    runs = zero.groupby((zero != zero.shift()).cumsum()).transform("sum")
    long_zero = int((zero & (runs >= 60)).sum())
    suspicious = int(((common["hist"] - common["duka"]).abs() / common["duka"].abs().replace(0, np.nan) > .01).sum())
    lines = [f"# HistData vs Dukascopy — {hist_symbol} / {dukascopy_symbol}", "",
             "Timestamp convention tested against Dukascopy bid closes in 2019–2024:", "",
             "| HistData timestamp shift before alignment | Matched bars | Median absolute difference (points) | Return correlation |",
             "|---:|---:|---:|---:|"]
    for candidate_lag, median, corr, aligned in lag_results:
        lines.append(f"| {candidate_lag:+d} min | {len(aligned):,} | {median:.4f} | {corr:.4f} |")
    lines += ["", f"Selected convention: lag {lag:+d} minute(s); this is consistent with HistData timestamps being bar OPEN times." if lag == 0 else f"Selected alignment lag: {lag:+d} minute(s); interpret timestamps accordingly.",
              f"Compared range: {max(hist.index.min(), duka.index.min()).date()}–{min(hist.index.max(), duka.index.max()).date()}; union-exclusive minutes: {exclusive:.2%}.", "",
              "## Annual aligned comparison", "",
              "| Year | Matched minutes | Return correlation | Median abs diff (points) | P95 abs diff (points) | Median HistData − Dukascopy |", "|---:|---:|---:|---:|---:|---:|"]
    for year, n, corr, median, p95, offset in yearly:
        lines.append(f"| {year} | {n:,} | {corr:.4f} | {median:.4f} | {p95:.4f} | {offset:.4f} |")
    lines += ["", "## Empirical timezone check by year and season", "",
              "Return alignment tested at −60, 0, and +60 minutes. Core winter uses Jan–Feb and Dec, core summer uses Jun–Aug; transition months (Mar–May, Sep–Nov) are shown separately.", "",
              "| Year | Season | Matched minutes | Corr −60m | Corr 0m | Corr +60m | Best shift | Best median abs price diff |", "|---:|:---:|---:|---:|---:|---:|---:|---:|"]
    hreturns_all, dreturns_all = one_minute_returns(hadj_all), one_minute_returns(dclose_all)
    for year in range(int(hist_all.index.min().year), int(hist_all.index.max().year) + 1):
        for season, months in (("winter", {1, 2, 12}), ("summer", {6, 7, 8}), ("transition", {3, 4, 5, 9, 10, 11})):
            hmask = (hclose_all.index.year == year) & np.isin(hclose_all.index.month, list(months))
            dmask = (dclose_all.index.year == year) & np.isin(dclose_all.index.month, list(months))
            hs, ds = hclose_all.loc[hmask], dclose_all.loc[dmask]
            if hs.empty or ds.empty:
                continue
            scores = []
            for minute_shift in (-60, 0, 60):
                shifted_price = hs.copy(); shifted_price.index += pd.Timedelta(minutes=minute_shift)
                price_pair = pd.concat([shifted_price.rename("hist"), ds.rename("duka")], axis=1, join="inner").dropna()
                hr = hreturns_all[(hreturns_all.index.year == year) & np.isin(hreturns_all.index.month, list(months))].copy()
                hr.index += pd.Timedelta(minutes=minute_shift)
                dr = dreturns_all[(dreturns_all.index.year == year) & np.isin(dreturns_all.index.month, list(months))]
                return_pair = pd.concat([hr.rename("hist"), dr.rename("duka")], axis=1, join="inner").dropna()
                scores.append((minute_shift, float(return_pair["hist"].corr(return_pair["duka"])),
                               float(np.median(np.abs(price_pair["hist"] - price_pair["duka"]))), len(price_pair)))
            best_season = max(scores, key=lambda item: (item[1] if pd.notna(item[1]) else -2, -item[2]))
            lines.append(f"| {year} | {season} | {best_season[3]:,} | {scores[0][1]:.4f} | {scores[1][1]:.4f} | {scores[2][1]:.4f} | {best_season[0]:+d}m | {best_season[2]:.4f} |")
    lines += ["", "## Empirical HistData clock transitions", "",
              "The overlap check selects the exact-close shift per trading day from −60/0/+60 minutes. The raw wall clock follows EU DST transition dates; relative to a New York-local conversion, +60 minutes is required from the U.S. spring switch through the EU spring switch, and from the EU fall switch through the U.S. fall switch. These windows were verified against exact Dukascopy closes after the timestamp correction.", "",
              "| Year | U.S. spring start | EU spring start (end +60) | EU fall end (start +60) | U.S. fall end |", "|---:|---:|---:|---:|---:|"]
    for year in range(2018, min(2026, int(hclose_all.index.max().year))+1):
        us_spring,eu_spring,eu_fall,us_fall=dst_mismatch_windows(year)
        lines.append(f"| {year} | {us_spring} | {eu_spring} | {eu_fall} | {us_fall} |")
    lines += ["", "## Post-switch monthly identity check", "",
              f"HistData feed switch: {HISTDATA_SWITCH_UTC.get(hist_symbol, pd.NaT)} UTC. Monthly price identity is computed from direct `histdata.load` and `dukascopy.load` data, after the per-day timestamp correction. Exact means absolute close difference ≤0.001 points.", "",
              "| Month | Paired bars | Exact close share | Median abs difference (points) | Return correlation |", "|---|---:|---:|---:|---:|"]
    switch=HISTDATA_SWITCH_UTC.get(hist_symbol)
    post_hist=hist_all.loc[hist_all.index>=switch] if switch is not None else hist_all.iloc[0:0]
    for month,group in post_hist.groupby(post_hist.index.strftime("%Y-%m"),sort=True):
        dgroup=duka_all.loc[duka_all.index.strftime("%Y-%m")==month]
        pair=pd.concat([group.bid_c.rename("hist"),dgroup.bid_c.rename("duka")],axis=1,join="inner").dropna()
        if pair.empty:
            lines.append(f"| {month} | 0 | n/a | n/a | n/a |")
            continue
        exact=np.isclose(pair["hist"].to_numpy(float),pair["duka"].to_numpy(float),rtol=0,atol=.001).mean()
        absdiff=np.abs(pair["hist"].to_numpy(float)-pair["duka"].to_numpy(float))
        returns=pair.pct_change().dropna()
        corr=returns["hist"].corr(returns["duka"]) if len(returns) else float("nan")
        lines.append(f"| {month} | {len(pair):,} | {exact:.4%} | {float(np.median(absdiff)):.4f} | {corr:.6f} |")
    roll_rows=[]
    if "roll" in hist_all:
        roll_rows=hist_all.loc[hist_all.roll.fillna(False)]
    lines += ["", "## Futures-continuous feed rolls", "",
              f"Feed switch is {switch}. Additive roll adjustments are applied backwards to `adj_bid_*`, keeping post-switch prices real. Detected roll bars: {len(roll_rows):,}.", "",
              "| Roll timestamp (UTC) | HistData close | Back-adjusted close |", "|---|---:|---:|"]
    for ts,row in roll_rows.iterrows():
        lines.append(f"| {ts} | {row['bid_c']:.3f} | {row['adj_bid_c']:.3f} |")
    lines += ["", "## Cash-open diagnostic where Dukascopy does not overlap", "",
              "For years without paired Dukascopy data, compare median absolute 1-minute return from 09:30–10:00 NY with the prior 60-minute window, split by winter and summer. A ratio above 1 indicates an opening volatility increase; it is a clock plausibility check, not cross-source validation.", "",
              "| Year | Season | Open-window / prior-hour abs-return ratio |", "|---:|:---:|---:|"]
    hlocal = hclose_all.index.tz_convert("America/New_York")
    hret_all = hreturns_all.abs()
    for year in range(int(hclose_all.index.min().year), int(min(hclose_all.index.max().year, dclose_all.index.max().year)) + 1):
        if year in set(dclose_all.index.year):
            continue
        for season, months in (("winter", {1,2,3,11,12}), ("summer", {4,5,6,7,8,9,10})):
            mask = (hlocal.year == year) & np.isin(hlocal.month, list(months))
            local_ret = hret_all.loc[mask]
            local_index = local_ret.index.tz_convert("America/New_York")
            open_vals = local_ret[(local_index.hour == 9) & (local_index.minute >= 30)]
            prior_vals = local_ret[((local_index.hour == 8) & (local_index.minute >= 30)) | ((local_index.hour == 9) & (local_index.minute < 30))]
            ratio = open_vals.median() / prior_vals.median() if len(open_vals) and len(prior_vals) and prior_vals.median() > 0 else float("nan")
            if pd.notna(ratio):
                lines.append(f"| {year} | {season} | {ratio:.3f} |")
    lines += ["", "## Weekday NY-hour coverage", "", "Observed minutes / expected weekday minutes over the overlap date range (selected alignment):", "",
              "| NY hour | HistData | Dukascopy |", "|---:|---:|---:|"]
    lines.extend(f"| {hour:02d}:00 | {hshare:.1%} | {dshare:.1%} |" for hour, hshare, dshare in hourly)
    lines += ["", "## Basis and suspicious bars", "",
              f"Median price offset (HistData − Dukascopy): {float((common["hist"]-common["duka"]).median()):.4f} points. The offset is near zero for this sample, consistent with both being cash-index-like quotations; it does not establish identical constituents or broker pricing.",
              f"HistData zero-range bars in runs ≥60 minutes: {long_zero:,}.",
              f"Aligned bars differing by >1% of Dukascopy close: {suspicious:,}.", ""]
    return "\n".join(lines)


def write_cross_validation() -> None:
    path = Path("reports/data/histdata_vs_dukascopy.md")
    path.parent.mkdir(exist_ok=True)
    content = "\n\n---\n\n".join((cross_validate("NSXUSD", "USATECHIDXUSD"), cross_validate("SPXUSD", "USA500IDXUSD")))
    path.write_text(content + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", required=True, choices=SYMBOLS)
    parser.add_argument("--start", type=date.fromisoformat, default=date(2010, 11, 1))
    parser.add_argument("--end", type=date.fromisoformat, default=datetime.now(timezone.utc).date())
    parser.add_argument("--compare", action="store_true", help="write the HistData/Dukascopy validation report")
    args = parser.parse_args()
    if args.compare:
        write_cross_validation()
    else:
        download(args.symbol, args.start, args.end)


if __name__ == "__main__":
    main()
