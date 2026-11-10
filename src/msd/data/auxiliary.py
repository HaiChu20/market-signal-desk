"""Parsers and polite public-source downloaders for non-bar datasets."""
from __future__ import annotations

import argparse
import csv
import gzip
from datetime import date, datetime, time, timedelta, timezone
import io
import json
import os
from pathlib import Path
import random
import shutil
import tempfile
import time as clock
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo
import zipfile

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from .binance_lake import MIN_FREE_BYTES, _atomic_bytes, _get, ensure_disk_space

CBOE_URLS = {
    "VIX": "https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv",
    "VIX3M": "https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX3M_History.csv",
    "VIX9D": "https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX9D_History.csv",
}
_last_official_request = 0.0


def _write_verified_parquet(frame: pd.DataFrame, path: Path) -> int:
    """Atomically store a non-empty frame and verify its row count on disk."""
    if frame.empty:
        raise ValueError(f"refusing to report success for empty output: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".parquet", delete=False) as handle:
        temp = Path(handle.name)
    pq.write_table(pa.Table.from_pandas(frame, preserve_index=False), temp)
    count = pq.read_metadata(temp).num_rows
    if count != len(frame) or count == 0:
        raise ValueError(f"Parquet verification failed for {path}: rows={count}, expected={len(frame)}")
    os.replace(temp, path)
    if pq.read_metadata(path).num_rows != count:
        raise ValueError(f"Parquet verification failed after replace: {path}")
    return count


def _verified_rows(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        return int(pq.read_metadata(path).num_rows)
    except (OSError, pa.ArrowException):
        return 0


def parse_cboe_csv(raw: bytes) -> pd.DataFrame:
    frame = pd.read_csv(io.BytesIO(raw))
    frame.columns = [column.strip().lower().replace(" ", "_") for column in frame.columns]
    date_column = next((column for column in frame if column in {"date", "trade_date"}), None)
    close_column = next((column for column in frame if column in {"close", "close_price"}), None)
    if date_column is None or close_column is None:
        raise ValueError("Unrecognized Cboe daily-price CSV columns")
    frame["date"] = pd.to_datetime(frame[date_column], errors="coerce")
    frame = frame.dropna(subset=["date"])
    return frame


def et_to_utc(day: date, hour: int, minute: int = 0, fold: int = 0) -> datetime:
    local = datetime.combine(day, time(hour, minute)).replace(tzinfo=ZoneInfo("America/New_York"), fold=fold)
    back = local.astimezone(timezone.utc).astimezone(ZoneInfo("America/New_York")).replace(tzinfo=None)
    if back != local.replace(tzinfo=None):
        raise ValueError(f"nonexistent Eastern time {day} {hour:02d}:{minute:02d}")
    return local.astimezone(timezone.utc)


def _polite_official_get(url: str, headers: dict[str, str] | None = None) -> bytes:
    global _last_official_request
    delay = 1.0 - (clock.monotonic() - _last_official_request)
    if delay > 0:
        clock.sleep(delay)
    _last_official_request = clock.monotonic()
    with urlopen(Request(url, headers=headers or {"User-Agent": "MarketSignalDesk public data research"}), timeout=60) as response:
        return response.read()


def download_cboe() -> None:
    total = 0
    for symbol, url in CBOE_URLS.items():
        ensure_disk_space()
        path = Path("data/aux/vix") / f"{symbol}_History.csv"
        raw_path = Path("data/raw/cboe") / f"{symbol}_History.csv"
        output = path.with_suffix(".parquet")
        if _verified_rows(output):
            total += 1
            continue
        raw = raw_path.read_bytes() if raw_path.exists() else _polite_official_get(url)
        if not raw:
            print(f"MISSING Cboe {symbol}: empty response", flush=True)
            continue
        if not raw_path.exists():
            _atomic_bytes(raw_path, raw)
        frame = parse_cboe_csv(raw)
        if frame.empty:
            print(f"MISSING Cboe {symbol}: parsed no rows", flush=True)
            continue
        count = _write_verified_parquet(frame, output)
        total += 1
        print(f"Cboe {symbol}: verified {count} daily rows at {output}", flush=True)
    if total == 0:
        raise RuntimeError("Cboe download produced no non-empty verified outputs")


def _save_raw_with_sha(path: Path, raw: bytes) -> None:
    """Keep an immutable raw response and an adjacent SHA256 for Allas upload."""
    import hashlib
    if path.exists():
        digest=hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != hashlib.sha256(raw).hexdigest():
            raise ValueError(f"refusing to overwrite differing raw archive: {path}")
        checksum=path.with_suffix(path.suffix + ".sha256")
        if not checksum.exists(): _atomic_bytes(checksum,(digest+"  "+path.name+"\n").encode())
        return
    _atomic_bytes(path, raw)
    _atomic_bytes(path.with_suffix(path.suffix + ".sha256"), (hashlib.sha256(raw).hexdigest()+"  "+path.name+"\n").encode())


def parse_squeezemetrics_csv(raw: bytes) -> pd.DataFrame:
    frame=pd.read_csv(io.BytesIO(raw))
    frame.columns=[str(c).strip().lower() for c in frame.columns]
    if not {"date","dix","gex"}.issubset(frame.columns):
        raise ValueError(f"unexpected SqueezeMetrics columns: {list(frame.columns)}")
    frame["date"]=pd.to_datetime(frame.date,errors="coerce").dt.normalize()
    for column in ("dix","gex"):
        frame[column]=pd.to_numeric(frame[column],errors="coerce")
    frame=frame.dropna(subset=["date","dix","gex"]).sort_values("date").drop_duplicates("date",keep="last")
    if frame.empty: raise ValueError("SqueezeMetrics parsed no usable rows")
    # DIX/GEX are published after the NY close; only expose them from the next
    # local calendar day onward.
    local=(frame.date+pd.Timedelta(days=1)).dt.tz_localize("America/New_York",ambiguous="NaT",nonexistent="shift_forward")
    frame["known_at"]=local.dt.tz_convert("UTC").astype("datetime64[ns, UTC]")
    return frame[["date","known_at","price","dix","gex"] if "price" in frame else ["date","known_at","dix","gex"]].reset_index(drop=True)


def download_squeezemetrics() -> int:
    ensure_disk_space()
    raw_path=Path("data/raw/squeezemetrics/DIX.csv")
    raw=raw_path.read_bytes() if raw_path.exists() else _polite_official_get("https://squeezemetrics.com/monitor/static/DIX.csv")
    if not raw: raise RuntimeError("SqueezeMetrics returned empty DIX CSV")
    _save_raw_with_sha(raw_path,raw)
    frame=parse_squeezemetrics_csv(raw)
    count=_write_verified_parquet(frame,Path("data/aux/squeezemetrics/DIX.parquet"))
    print(f"verified SqueezeMetrics DIX/GEX: rows={count} bytes={len(raw)} range={frame.date.min().date()}..{frame.date.max().date()}",flush=True)
    return count


def parse_deribit_dvol_response(raw: bytes, currency: str, month: date, resolution_seconds: int = 3600) -> pd.DataFrame:
    payload=json.loads(raw)
    if payload.get("error") or not isinstance(payload.get("result",{}).get("data"),list):
        raise ValueError(f"Deribit DVOL response schema error for {currency} {month:%Y-%m}")
    rows=[]
    for item in payload["result"]["data"]:
        if not isinstance(item,(list,tuple)) or len(item)<2: continue
        stamp=pd.to_datetime(item[0],unit="ms",utc=True)
        if stamp.year==month.year and stamp.month==month.month:
            rows.append({"ts":stamp,"known_at":stamp+pd.Timedelta(seconds=resolution_seconds),
                         "resolution_seconds":int(resolution_seconds),"close":float(item[-1])})
    return pd.DataFrame(rows,columns=["ts","known_at","resolution_seconds","close"]).sort_values("ts").drop_duplicates("ts",keep="last").reset_index(drop=True)


def download_deribit_dvol() -> int:
    """Fetch hourly public DVOL in monthly chunks (one request/sec)."""
    total=0
    now=datetime.now(timezone.utc)
    for currency in ("BTC","ETH"):
        month=date(2021,1,1)
        while month<=now.date():
            ensure_disk_space()
            next_month=(month.replace(day=28)+timedelta(days=4)).replace(day=1)
            out=Path("data/aux/dvol")/currency/f"{month:%Y-%m}.parquet"
            raw_path=Path("data/raw/deribit/dvol")/currency/f"{month:%Y-%m}.json"
            if _verified_rows(out) and raw_path.exists():
                _save_raw_with_sha(raw_path,raw_path.read_bytes())
                total+=_verified_rows(out)
                month=next_month
                continue
            start=datetime(month.year,month.month,1,tzinfo=timezone.utc)
            end=min(datetime(next_month.year,next_month.month,1,tzinfo=timezone.utc),now)
            if raw_path.exists(): raw=raw_path.read_bytes()
            else:
                import urllib.parse
                params=urllib.parse.urlencode({"currency":currency,"start_timestamp":int(start.timestamp()*1000),
                                              "end_timestamp":int(end.timestamp()*1000),"resolution":"3600"})
                raw=_polite_official_get(f"https://www.deribit.com/api/v2/public/get_volatility_index_data?{params}")
                if not raw: raise RuntimeError(f"Deribit {currency} {month:%Y-%m}: empty response")
                _save_raw_with_sha(raw_path,raw)
            # API points are [timestamp, open, high, low, close].
            frame=parse_deribit_dvol_response(raw,currency,month)
            if frame.empty:
                print(f"MISSING Deribit DVOL {currency} {month:%Y-%m}: no hourly points",flush=True)
            else:
                count=_write_verified_parquet(frame, out)
                total+=count
                print(f"verified Deribit DVOL {currency} {month:%Y-%m}: rows={count} raw_bytes={len(raw)}",flush=True)
            month=next_month
    if total==0: raise RuntimeError("Deribit DVOL returned no verified observations")
    return total


def _download_funding_month(symbol: str, month: date) -> int | None:
    name = f"{symbol}-fundingRate-{month:%Y-%m}.zip"
    base = f"https://data.binance.vision/data/futures/um/monthly/fundingRate/{symbol}"
    import hashlib
    raw_path = Path("data/raw/binance/funding") / symbol / name
    checksum_path = raw_path.with_suffix(raw_path.suffix + ".CHECKSUM")
    if raw_path.exists():
        checksum = checksum_path.read_bytes() if checksum_path.exists() else _get(f"{base}/{name}.CHECKSUM")
        if checksum is None:
            print(f"MISSING Binance funding {symbol} {month:%Y-%m}: checksum unavailable for retained ZIP", flush=True)
            return None
        if not checksum_path.exists():
            _atomic_bytes(checksum_path, checksum)
        raw = raw_path.read_bytes()
    else:
        checksum = _get(f"{base}/{name}.CHECKSUM")
        if checksum is None:
            print(f"MISSING Binance funding {symbol} {month:%Y-%m}: checksum/archive unavailable", flush=True)
            return None
        raw = _get(f"{base}/{name}")
        if raw is None:
            print(f"MISSING Binance funding {symbol} {month:%Y-%m}: checksum exists but ZIP is missing", flush=True)
            return None
        _atomic_bytes(checksum_path, checksum)
        _atomic_bytes(raw_path, raw)
    expected = checksum.decode().split()[0].lower()
    if len(expected) != 64 or any(c not in "0123456789abcdef" for c in expected):
        raise ValueError(f"Malformed funding SHA256 checksum for {name}")
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError(f"Funding ZIP missing or checksum mismatch: {symbol} {month:%Y-%m}")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        names = [member for member in archive.namelist() if member.endswith(".csv")]
        if len(names) != 1:
            raise ValueError(f"unexpected funding archive contents: {names}")
        frame = __import__("msd.data.binance_lake", fromlist=["parse_funding_csv"]).parse_funding_csv(archive.read(names[0]), symbol)
    if frame.empty:
        raise ValueError(f"Funding archive parsed no rows: {symbol} {month:%Y-%m}")
    base_path = Path("data/aux/funding") / symbol
    base_path.mkdir(parents=True, exist_ok=True)
    count = _write_verified_parquet(frame, base_path / f"{month:%Y-%m}.parquet")
    print(f"verified Binance funding {symbol} {month:%Y-%m}: {count} rows", flush=True)
    return count


def download_funding() -> None:
    for symbol in ("BTCUSDT", "ETHUSDT"):
        month = date(2019, 9, 1)
        now = datetime.now(timezone.utc).date()
        verified_months = missing_months = total_rows = 0
        while month <= now:
            ensure_disk_space()
            output = Path("data/aux/funding") / symbol / f"{month:%Y-%m}.parquet"
            existing = 0
            if output.exists():
                try:
                    saved = pd.read_parquet(output)
                    ts = pd.to_datetime(saved["ts"], utc=True)
                    valid = (not saved.empty and {"ts", "funding_rate", "funding_interval_hours"}.issubset(saved.columns)
                             and ts.dt.year.eq(month.year).all() and ts.dt.month.eq(month.month).all()
                             and pd.to_numeric(saved.funding_rate, errors="coerce").notna().all())
                    if valid:
                        existing = len(saved)
                except (OSError, KeyError, ValueError, TypeError):
                    existing = 0
            if existing:
                verified_months += 1
                total_rows += existing
                month = (month.replace(day=28) + timedelta(days=4)).replace(day=1)
                continue
            if output.exists():
                print(f"REBUILD Binance funding {symbol} {month:%Y-%m}: invalid existing parquet", flush=True)
            count = _download_funding_month(symbol, month)
            if count is None:
                missing_months += 1
            else:
                verified_months += 1
                total_rows += count
            month = (month.replace(day=28) + timedelta(days=4)).replace(day=1)
        if verified_months == 0:
            raise RuntimeError(f"Funding run failed for {symbol}: every month missing or empty ({missing_months} missing)")
        print(f"DONE funding {symbol}: verified_months={verified_months} missing_months={missing_months} rows={total_rows}", flush=True)


def _download_metric_day(symbol: str, day: date) -> int:
    name = f"{symbol}-metrics-{day:%Y-%m-%d}.zip"
    url = f"https://data.binance.vision/data/futures/um/daily/metrics/{symbol}/{name}"
    checksum = _get(f"{url}.CHECKSUM")
    if checksum is None:
        print(f"MISSING Binance metrics {symbol} {day}: checksum/archive unavailable", flush=True)
        return 0
    import hashlib
    expected=checksum.decode("ascii").split()[0].lower()
    if len(expected)!=64 or any(c not in "0123456789abcdef" for c in expected):
        raise ValueError(f"Malformed metrics SHA256 checksum for {name}")
    raw = _get(url)
    if raw is None:
        print(f"MISSING Binance metrics {symbol} {day}: checksum exists but ZIP is missing", flush=True)
        return 0
    if hashlib.sha256(raw).hexdigest()!=expected:
        raise ValueError(f"Metrics SHA256 mismatch: {name}")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        names = [member for member in archive.namelist() if member.endswith(".csv")]
        if len(names) != 1:
            raise ValueError(f"unexpected metrics archive contents: {names}")
        frame = __import__("msd.data.binance_lake", fromlist=["parse_metrics_csv"]).parse_metrics_csv(archive.read(names[0]))
    if frame.empty:
        raise ValueError(f"Metrics archive parsed no rows: {symbol} {day}")
    root = Path("data/aux/metrics") / symbol
    root.mkdir(parents=True, exist_ok=True)
    _atomic_bytes(Path("data/raw/binance/metrics") / symbol / name, raw)
    count=_write_verified_parquet(frame,root / f"{day:%Y-%m-%d}.parquet")
    print(f"verified Binance metrics {symbol} {day}: {count} rows",flush=True)
    return count


def download_metrics() -> None:
    start = date(2019, 9, 1)
    end = datetime.now(timezone.utc).date()
    for symbol in ("BTCUSDT", "ETHUSDT"):
        day = start
        verified_days = missing_days = 0
        while day <= end:
            ensure_disk_space()
            out = Path("data/aux/metrics") / symbol / f"{day:%Y-%m-%d}.parquet"
            rows = _verified_rows(out)
            if rows:
                verified_days += 1
            else:
                rows = _download_metric_day(symbol, day)
                if rows:
                    verified_days += 1
                else:
                    missing_days += 1
            day += timedelta(days=1)
        if verified_days == 0:
            raise RuntimeError(f"Metrics run failed for {symbol}: all {missing_days} days missing or empty")
        print(f"DONE metrics {symbol}: verified_days={verified_days} missing_days={missing_days}", flush=True)


def parse_edgar_submissions(payload: dict, ticker: str) -> pd.DataFrame:
    """Extract 8-K item 2.02 rows from a SEC submissions JSON block."""
    filings=payload.get("filings",{}).get("recent",payload)
    forms=filings.get("form",[])
    items=filings.get("items",[""]*len(forms))
    rows=[]
    for index,form in enumerate(forms):
        if form!="8-K" or index>=len(items) or "2.02" not in str(items[index]):
            continue
        acceptance=(filings.get("acceptanceDateTime") or [""]*len(forms))[index]
        filing_date=(filings.get("filingDate") or [""]*len(forms))[index]
        if not filing_date or str(filing_date)<"2010-01-01": continue
        accession=(filings.get("accessionNumber") or [""]*len(forms))[index]
        document=(filings.get("primaryDocument") or [""]*len(forms))[index]
        rows.append({"ticker":ticker,"form":form,"acceptanceDateTime":acceptance,"filingDate":filing_date,
                     "datetime_utc":acceptance,"accessionNumber":accession,"primaryDocument":document,
                     "items":str(items[index]),"event":f"earnings_{ticker.lower()}"})
    return pd.DataFrame(rows,columns=["ticker","form","acceptanceDateTime","filingDate","datetime_utc",
                                     "accessionNumber","primaryDocument","items","event"])


def download_edgar() -> str:
    agent = os.environ.get("SEC_USER_AGENT", "")
    if not agent:
        return "SEC earnings skipped: SEC_USER_AGENT is not set"
    ciks = {"AAPL": "0000320193", "MSFT": "0000789019", "NVDA": "0001045810", "AMZN": "0001018724", "GOOGL": "0001652044", "META": "0001326801", "TSLA": "0001318605", "AVGO": "0001730168", "COST": "0000909832", "NFLX": "0001065280"}
    # Submission metadata includes the 8-K item list, so individual filing
    # documents are unnecessary and would multiply requests substantially.
    events=[]
    for ticker, cik in ciks.items():
        root=Path("data/raw/sec/submissions");root.mkdir(parents=True,exist_ok=True)
        recent_path=root/f"CIK{cik}.json"
        raw=recent_path.read_bytes() if recent_path.exists() else _polite_official_get(
            f"https://data.sec.gov/submissions/CIK{cik}.json",{"User-Agent":agent,"Accept-Encoding":"gzip, deflate"})
        if not raw: raise RuntimeError(f"SEC EDGAR returned empty submissions metadata for {ticker}")
        _save_raw_with_sha(recent_path,raw)
        decoded = gzip.decompress(raw) if raw.startswith(b"\x1f\x8b") else raw
        data=json.loads(decoded)
        ticker_rows=[parse_edgar_submissions(data,ticker)]
        for old in data.get("filings",{}).get("files",[]):
            name=old.get("name")
            if not name or not name.endswith(".json"): continue
            old_path=root/name
            old_raw=old_path.read_bytes() if old_path.exists() else _polite_official_get(
                f"https://data.sec.gov/submissions/{name}",{"User-Agent":agent,"Accept-Encoding":"gzip, deflate"})
            if not old_raw: continue
            _save_raw_with_sha(old_path,old_raw)
            decoded_old = gzip.decompress(old_raw) if old_raw.startswith(b"\x1f\x8b") else old_raw
            ticker_rows.append(parse_edgar_submissions(json.loads(decoded_old),ticker))
        events.append(pd.concat(ticker_rows,ignore_index=True))
    result=pd.concat(events,ignore_index=True).drop_duplicates(["ticker","accessionNumber"],keep="last")
    result=result[result.acceptanceDateTime.astype(str).str.len().gt(0)].sort_values("acceptanceDateTime")
    path = Path("data/aux/earnings/sec_8k_item_2_02.csv"); path.parent.mkdir(parents=True, exist_ok=True)
    if result.empty: raise RuntimeError("SEC EDGAR returned no historical 8-K item 2.02 events")
    with tempfile.NamedTemporaryFile(mode="w",newline="",dir=path.parent,suffix=".csv",delete=False) as handle:
        temp=Path(handle.name); result.to_csv(handle,index=False)
    os.replace(temp,path)
    if not path.exists() or path.stat().st_size == 0 or pd.read_csv(path).empty:
        raise RuntimeError("SEC EDGAR output verification failed")
    raw_bytes=sum(item.stat().st_size for item in Path("data/raw/sec/submissions").glob("*.json"))
    return f"SEC earnings verified: rows={len(result)} raw_json_bytes={raw_bytes} at {path}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cboe", action="store_true")
    parser.add_argument("--funding", action="store_true")
    parser.add_argument("--metrics", action="store_true")
    parser.add_argument("--edgar", action="store_true")
    parser.add_argument("--squeezemetrics", action="store_true")
    parser.add_argument("--dvol", action="store_true")
    args = parser.parse_args()
    if args.cboe: download_cboe()
    if args.funding: download_funding()
    if args.metrics: download_metrics()
    if args.edgar: print(download_edgar())
    if args.squeezemetrics: download_squeezemetrics()
    if args.dvol: download_deribit_dvol()


if __name__ == "__main__":
    main()
