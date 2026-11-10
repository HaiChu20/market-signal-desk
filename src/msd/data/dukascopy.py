"""Download Dukascopy UTC minute candles into monthly Parquet files."""
from __future__ import annotations

import argparse
import csv
import http.client
import random
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
import lzma
import os
from pathlib import Path
import shutil
import struct
import tempfile
import time

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

SCALES = {"USA500IDXUSD": 1000, "USATECHIDXUSD": 1000, "BTCUSD": 10, "XAUUSD": 1000}
CRYPTO_SYMBOLS = frozenset({"BTCUSD", "ETHUSD"})
RANGES = {"USA500IDXUSD": (100, 100000), "USATECHIDXUSD": (100, 1000000), "BTCUSD": (1, 10000000), "XAUUSD": (200, 10000)}
# Plausibility bands are calibration constraints, not assumed point scales.
PRICE_BANDS = {
    "USA30IDXUSD": (5000, 100000), "DEUIDXEUR": (3000, 50000), "XAUUSD": (200, 10000),
    "XAGUSD": (3, 200), "EURUSD": (0.5, 3.0), "USDJPY": (50, 300), "GBPUSD": (0.5, 3.0),
    "LIGHTCMDUSD": (-60, 300), "BRENTCMDUSD": (10, 300), "GBRIDXGBP": (1000, 50000),
    "JPNIDXJPY": (5000, 100000), "ETHUSD": (10, 20000),
}
ROOT = Path("data/bars/dukascopy")
RECORD = struct.Struct(">5if")
_HOST = "datafeed.dukascopy.com"
_LOCAL = threading.local()
_COUNT_LOCK = threading.Lock()
_HTTP_503_COUNTS: Counter[str] = Counter()
_ERROR_COUNTS: Counter[tuple[str, str]] = Counter()
EXTENDED_RETRY_SECONDS = (60, 120, 300, 600)
COLUMNS = ["ts", "bid_o", "bid_h", "bid_l", "bid_c", "ask_o", "ask_h", "ask_l", "ask_c", "volume"]
DUKA_COLUMNS = COLUMNS + ["bad_tick"]


class PlausibilityError(ValueError):
    def __init__(self, symbol: str, day: date, side: str, reason: str,
                 raw_min: float = float("nan"), raw_max: float = float("nan")):
        super().__init__(f"Implausible {symbol} {day} {side}: {reason}; raw_min={raw_min:g}, raw_max={raw_max:g}")
        self.symbol, self.day, self.side, self.reason = symbol, day, side, reason
        self.raw_min, self.raw_max = raw_min, raw_max


def _empty_frame() -> pd.DataFrame:
    """Typed empty bar frame so monthly concat and ``.dt`` remain safe."""
    return pd.DataFrame({"ts": pd.Series(dtype="datetime64[ns, UTC]"),
                         **{column: pd.Series(dtype="float64") for column in COLUMNS[1:]},
                         "bad_tick": pd.Series(dtype="bool")})[DUKA_COLUMNS]


def decode(raw: bytes, symbol: str, day: date, side: str) -> pd.DataFrame:
    if not raw:
        return _empty_frame()
    payload = lzma.decompress(raw)
    if len(payload) % RECORD.size:
        raise ValueError(f"Bad BI5 length for {symbol} {day} {side}")
    values = np.frombuffer(payload, dtype=np.dtype([("sec", ">i4"), ("o", ">i4"), ("c", ">i4"), ("l", ">i4"), ("h", ">i4"), ("volume", ">f4")]))
    values = values[values["volume"] > 0]
    if len(values) == 0:
        return _empty_frame()
    scale = SCALES[symbol]
    prices = np.column_stack([values[x].astype(float) / scale for x in ("o", "h", "l", "c")])
    lo, hi = RANGES[symbol]
    raw_min=float(np.min(prices)) if prices.size else float("nan")
    raw_max=float(np.max(prices)) if prices.size else float("nan")
    if (prices < lo).any() or (prices > hi).any():
        raise PlausibilityError(symbol,day,side,f"scaled prices outside [{lo}, {hi}]",raw_min,raw_max)
    if (values["sec"] < 0).any() or (values["sec"] >= 86400).any():
        raise PlausibilityError(symbol,day,side,"seconds outside UTC day",raw_min,raw_max)
    frame = pd.DataFrame(prices, columns=[f"{side.lower()}_{x}" for x in "ohlc"])
    frame.insert(0, "ts", pd.to_datetime(day, utc=True) + pd.to_timedelta(values["sec"].astype(int), unit="s"))
    frame["volume"] = values["volume"].astype(float)
    frame["bad_tick"] = False
    return frame[["ts",*(f"{side.lower()}_{x}" for x in "ohlc"),"volume","bad_tick"]]


def mark_bad_ticks(frame: pd.DataFrame, multiple: float = 20.0) -> pd.DataFrame:
    """Flag implausible one-minute ranges/jumps without removing source rows."""
    out=frame.copy()
    if out.empty:
        out["bad_tick"]=pd.Series(dtype="bool")
        return out
    mid_hi=(out.bid_h.to_numpy(float)+out.ask_h.to_numpy(float))/2
    mid_lo=(out.bid_l.to_numpy(float)+out.ask_l.to_numpy(float))/2
    mid_close=(out.bid_c.to_numpy(float)+out.ask_c.to_numpy(float))/2
    ranges=np.maximum(mid_hi-mid_lo,0)
    finite=ranges[np.isfinite(ranges)&(ranges>0)]
    typical=float(np.median(finite)) if len(finite) else 0.0
    bad=(out["bad_tick"].fillna(False).to_numpy(dtype=bool,copy=True)
         if "bad_tick" in out else np.zeros(len(out),dtype=bool))
    if typical>0:
        bad |= ranges > multiple*typical
        if "ts" in out:
            adjacent=pd.to_datetime(out.ts,utc=True).diff().eq(pd.Timedelta(minutes=1)).to_numpy()
            jumps=np.r_[0.0,np.abs(np.diff(mid_close))]
            bad |= adjacent & (jumps > multiple*typical)
    out["bad_tick"]=bad
    return out


def infer_price_scale(raw: bytes, symbol: str, reference_price: float | None = None) -> int:
    """Infer decimal scale from an actual BI5 sample and a source/reference band."""
    payload = lzma.decompress(raw)
    values = np.frombuffer(payload, dtype=np.dtype([("sec", ">i4"), ("o", ">i4"), ("c", ">i4"), ("l", ">i4"), ("h", ">i4"), ("volume", ">f4")]))
    prices = values["o"][values["volume"] > 0].astype(float)
    if not len(prices):
        raise ValueError(f"No prices available to infer point scale for {symbol}")
    median = float(np.median(prices))
    if reference_price is None and symbol in SCALES:
        scale = SCALES[symbol]
        low, high = PRICE_BANDS.get(symbol, RANGES.get(symbol, (0, float("inf"))))
        if not low <= median / scale <= high:
            raise ValueError(f"Recorded point scale for {symbol} is implausible: {median / scale}")
        return scale
    if reference_price is not None:
        candidates = [(abs(np.log((median / 10**power) / reference_price)), 10**power) for power in range(0, 8)]
        error, scale = min(candidates)
        if error > np.log(1.02):
            raise ValueError(f"No point scale for {symbol} matches reference within 2%")
        return int(scale)
    if symbol not in PRICE_BANDS:
        raise ValueError(f"No calibrated range configured for {symbol}")
    low, high = PRICE_BANDS[symbol]
    matches = [10**power for power in range(0, 8) if low <= median / 10**power <= high]
    if len(matches) != 1:
        raise ValueError(f"Point scale for {symbol} is ambiguous or implausible: sample median={median}, candidates={matches}")
    return matches[0]


def _binance_daily_reference(symbol: str, day: date) -> float:
    """Median Binance spot close for the UTC day, used to calibrate crypto CFDs."""
    spot_symbol = symbol.removesuffix("USD") + "USDT"
    path = Path("data/bars/binance_spot") / spot_symbol / f"{day:%Y-%m}.parquet"
    if not path.exists():
        raise FileNotFoundError(f"Missing Binance calibration month for {symbol}: {path}")
    frame = pd.read_parquet(path, columns=["ts", "bid_c"])
    mask = frame.ts.dt.strftime("%Y-%m-%d").eq(day.isoformat())
    prices = frame.loc[mask, "bid_c"].to_numpy(dtype=float)
    if not len(prices) or not np.isfinite(prices).all():
        raise ValueError(f"No valid Binance spot closes for {spot_symbol} on {day}")
    return float(np.median(prices))


def _reference_source_path(symbol: str) -> Path:
    aliases={"USATECHIDXUSD":"NSXUSD","USA500IDXUSD":"SPXUSD",
             "DEUIDXEUR":"GRXEUR","LIGHTCMDUSD":"WTIUSD"}
    return Path("data/bars/histdata")/aliases.get(symbol,symbol)


def _existing_daily_reference(symbol: str, day: date) -> float | None:
    """Use a local independent HistData close when one exists for this epic."""
    path=_reference_source_path(symbol)/f"{day:%Y-%m}.parquet"
    if not path.exists():
        return None
    frame=pd.read_parquet(path,columns=["ts","bid_c"])
    mask=frame.ts.dt.strftime("%Y-%m-%d").eq(day.isoformat())
    values=frame.loc[mask,"bid_c"].to_numpy(dtype=float)
    values=values[np.isfinite(values)]
    return float(np.median(values)) if len(values) else None


def _calibration_reference_price(symbol: str, day: date) -> float | None:
    if symbol in CRYPTO_SYMBOLS:
        return _binance_daily_reference(symbol,day)
    return _existing_daily_reference(symbol,day)


def _download_days(symbol: str, month: date, last: date, start: date) -> list[date]:
    return [month + timedelta(days=i) for i in range((last - month).days + 1)
            if month + timedelta(days=i) >= start
            and (symbol in CRYPTO_SYMBOLS or (month + timedelta(days=i)).weekday() != 5)]


def calibrate_scale(symbol: str, sample_day: date = date(2024, 6, 12)) -> int:
    """Fetch BID samples with transport retries; a bad sample day doesn't block the symbol."""
    has_existing_reference=(symbol not in CRYPTO_SYMBOLS and _reference_source_path(symbol).exists())
    if symbol in SCALES and symbol not in CRYPTO_SYMBOLS and not has_existing_reference:
        return SCALES[symbol]
    if symbol not in PRICE_BANDS and symbol not in SCALES:
        raise ValueError(f"No calibration band configured for {symbol}")
    raw = None
    failures = []
    for offset in (0, 1, -1, 2, -2):
        day = sample_day + timedelta(days=offset)
        path = f"/datafeed/{symbol}/{day:%Y}/{day.month - 1:02d}/{day:%d}/BID_candles_min_1.bi5"
        for attempt in range(8 + len(EXTENDED_RETRY_SECONDS)):
            try:
                conn = _connection()
                conn.request("GET", path, headers={"User-Agent": "Mozilla/5.0 (compatible; MarketSignalDesk/0.1)", "Connection": "keep-alive"})
                response = conn.getresponse()
                payload = response.read()
                if response.status == 404:
                    raise FileNotFoundError(f"HTTP 404 for calibration day {day}")
                if response.status != 200:
                    if response.status == 503:
                        with _COUNT_LOCK:
                            _HTTP_503_COUNTS[symbol] += 1
                    raise OSError(f"HTTP {response.status} for {path}")
                if not payload:
                    raise OSError(f"Empty calibration response for {day}")
                raw = payload
                break
            except FileNotFoundError as error:
                _disconnect()
                failures.append(error)
                with _COUNT_LOCK:
                    _ERROR_COUNTS[(symbol, type(error).__name__)] += 1
                break
            except Exception as error:
                _disconnect()
                failures.append(error)
                with _COUNT_LOCK:
                    _ERROR_COUNTS[(symbol, type(error).__name__)] += 1
                if attempt == 11:
                    _record_missing(symbol, DailyFetchError(symbol, day, "BID", error))
                    break
                if attempt < 7:
                    delay = min(2 ** (attempt + 1), 60) + random.uniform(0, 1)
                else:
                    delay = EXTENDED_RETRY_SECONDS[attempt - 7]
                    print(f"retrying {symbol} calibration {day} BID after extended backoff {delay}s", flush=True)
                time.sleep(delay)
        if raw:
            if day != sample_day:
                print(f"calibration sample shifted from {sample_day} to {day} after transport/missing-day failures", flush=True)
            break
    if not raw:
        detail = failures[-1] if failures else "no calibration data"
        raise OSError(f"Point-scale calibration failed for {symbol} after alternate sample days: {detail}")
    reference_price = _calibration_reference_price(symbol,day)
    scale = infer_price_scale(raw, symbol, reference_price=reference_price)
    if symbol in SCALES and SCALES[symbol] != scale:
        raise ValueError(f"Cross-source calibration for {symbol} disagrees with configured scale {SCALES[symbol]}: inferred {scale}")
    SCALES[symbol] = scale
    lo, hi = PRICE_BANDS.get(symbol,RANGES.get(symbol,(float("-inf"),float("inf"))))
    RANGES[symbol] = (lo, hi)
    import json
    path = Path("data/aux/point_scales.json")
    current = json.loads(path.read_text()) if path.exists() else {}
    sample_values = np.frombuffer(lzma.decompress(raw), dtype=np.dtype([("sec", ">i4"), ("o", ">i4"), ("c", ">i4"), ("l", ">i4"), ("h", ">i4"), ("volume", ">f4")]))
    sample_prices = sample_values["o"][sample_values["volume"] > 0]
    current[symbol] = {"scale": scale, "sample_day": day.isoformat(),
                       "median_price": float(np.median(sample_prices)) / scale, "price_band": [lo, hi]}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(current, indent=2) + "\n")
    print(f"calibrated {symbol} point scale {scale} from {sample_day}", flush=True)
    return scale


def _connection() -> http.client.HTTPSConnection:
    conn = getattr(_LOCAL, "conn", None)
    if conn is None:
        conn = http.client.HTTPSConnection(_HOST, timeout=30)
        _LOCAL.conn = conn
    return conn


def _disconnect() -> None:
    conn = getattr(_LOCAL, "conn", None)
    _LOCAL.conn = None
    if conn is not None:
        try:
            conn.close()
        except Exception:
            pass


def fetch(symbol: str, day: date, side: str, retries: int = 8, raw_root: Path | None = None) -> pd.DataFrame:
    raw_path = raw_root / symbol / f"{day:%Y-%m-%d}_{side}.bi5" if raw_root else None
    if raw_path is not None and raw_path.exists():
        return decode(raw_path.read_bytes(), symbol, day, side)
    path = f"/datafeed/{symbol}/{day:%Y}/{day.month - 1:02d}/{day:%d}/{side}_candles_min_1.bi5"
    total_attempts = retries + len(EXTENDED_RETRY_SECONDS)
    for attempt in range(total_attempts):
        try:
            conn = _connection()
            conn.request("GET", path, headers={"User-Agent": "Mozilla/5.0 (compatible; MarketSignalDesk/0.1)", "Connection": "keep-alive"})
            response = conn.getresponse()
            raw = response.read()
            if response.status == 404:
                return _empty_frame()
            if response.status != 200:
                if response.status == 503:
                    with _COUNT_LOCK:
                        _HTTP_503_COUNTS[symbol] += 1
                raise OSError(f"HTTP {response.status} for {path}")
            if raw_path is not None and raw:
                raw_path.parent.mkdir(parents=True, exist_ok=True)
                with tempfile.NamedTemporaryFile(dir=raw_path.parent, suffix=".bi5", delete=False) as handle:
                    temp = Path(handle.name)
                    handle.write(raw)
                os.replace(temp, raw_path)
            return decode(raw, symbol, day, side)
        except PlausibilityError:
            _disconnect()
            raise
        except Exception as error:
            _disconnect()
            with _COUNT_LOCK:
                _ERROR_COUNTS[(symbol, type(error).__name__)] += 1
            if attempt == total_attempts - 1:
                raise
            if attempt < retries - 1:
                delay = min(2 ** (attempt + 1), 60) + random.uniform(0, 1)
            else:
                extended_index = attempt - (retries - 1)
                delay = EXTENDED_RETRY_SECONDS[extended_index]
                print(f"retrying {symbol} {day} {side} after extended backoff {delay}s", flush=True)
            time.sleep(delay)
    raise AssertionError("unreachable")


class DailyFetchError(OSError):
    def __init__(self, symbol: str, day: date, side: str, error: Exception):
        super().__init__(f"{symbol} {day} {side}: {type(error).__name__}: {error}")
        self.symbol, self.day, self.side, self.error = symbol, day, side, error


def fetch_day(symbol: str, day: date, raw_root: Path | None = None) -> pd.DataFrame:
    try:
        bid = fetch(symbol, day, "BID", raw_root=raw_root)
    except PlausibilityError:
        raise
    except Exception as error:
        raise DailyFetchError(symbol, day, "BID", error) from error
    try:
        ask = fetch(symbol, day, "ASK", raw_root=raw_root)
    except PlausibilityError:
        raise
    except Exception as error:
        raise DailyFetchError(symbol, day, "ASK", error) from error
    if bid.empty or ask.empty:
        return _empty_frame()
    merged = bid.merge(ask, on="ts", suffixes=("_bid", "_ask"), validate="one_to_one")
    merged["volume"] = (merged.pop("volume_bid") + merged.pop("volume_ask")) / 2
    merged["bad_tick"] = False
    return mark_bad_ticks(merged[DUKA_COLUMNS])


def _record_quarantine(symbol: str, error: PlausibilityError) -> None:
    path=Path("data/logs")/f"quarantine_{symbol}.csv"
    path.parent.mkdir(parents=True,exist_ok=True)
    exists=path.exists()
    with path.open("a",newline="") as stream:
        writer=csv.DictWriter(stream,fieldnames=("date","side","reason","raw_min","raw_max"))
        if not exists: writer.writeheader()
        writer.writerow({"date":error.day.isoformat(),"side":error.side,"reason":error.reason,
                         "raw_min":error.raw_min,"raw_max":error.raw_max})


def _quarantine_count(symbol: str, year: int) -> int:
    path=Path("data/logs")/f"quarantine_{symbol}.csv"
    if not path.exists(): return 0
    try:
        frame=pd.read_csv(path,parse_dates=["date"])
        dates=pd.to_datetime(frame.date)
        return int(frame.loc[dates.dt.year.eq(year),"date"].nunique())
    except (ValueError,KeyError):
        return 0


def _missing_path(symbol: str) -> Path:
    return Path("data/logs") / f"missing_{symbol}.csv"


def _read_missing(symbol: str) -> list[dict[str, str]]:
    path = _missing_path(symbol)
    if not path.exists():
        return []
    with path.open(newline="") as stream:
        return list(csv.DictReader(stream))


def _write_missing(symbol: str, rows: list[dict[str, str]]) -> None:
    path = _missing_path(symbol)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=("date", "side", "error"))
        writer.writeheader()
        writer.writerows(rows)


def _record_missing(symbol: str, error: DailyFetchError) -> None:
    rows = _read_missing(symbol)
    record = {"date": error.day.isoformat(), "side": error.side, "error": str(error.error)}
    rows = [row for row in rows if not (row.get("date") == record["date"] and row.get("side") == record["side"])]
    rows.append(record)
    _write_missing(symbol, rows)


def _atomic_month(frame: pd.DataFrame, path: Path, complete: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".parquet", delete=False) as tmp:
        temp = Path(tmp.name)
    table = pa.Table.from_pandas(frame, preserve_index=False)
    metadata = dict(table.schema.metadata or {})
    metadata[b"msd_complete"] = b"1" if complete else b"0"
    pq.write_table(table.replace_schema_metadata(metadata), temp)
    os.replace(temp, path)
    if pq.read_metadata(path).num_rows != len(frame) or not len(frame):
        raise ValueError(f"Dukascopy Parquet verification failed for {path}")


def _set_month_complete(path: Path, complete: bool) -> None:
    if not path.exists():
        return
    table=pq.read_table(path)
    metadata=dict(table.schema.metadata or {})
    metadata[b"msd_complete"] = b"1" if complete else b"0"
    with tempfile.NamedTemporaryFile(dir=path.parent,suffix=".parquet",delete=False) as tmp:
        temp=Path(tmp.name)
    pq.write_table(table.replace_schema_metadata(metadata),temp)
    os.replace(temp,path)
    if pq.read_metadata(path).num_rows != table.num_rows:
        raise ValueError(f"Dukascopy month metadata verification failed for {path}")


def _final_missing_pass(symbol: str, root: Path, start: date, end: date) -> int:
    rows = _read_missing(symbol)
    if not rows:
        return 0
    pending: dict[tuple[date, str], dict[str, str]] = {}
    retry_frames: dict[str, list[pd.DataFrame]] = {}
    by_day: dict[date, list[dict[str, str]]] = {}
    for row in rows:
        by_day.setdefault(date.fromisoformat(row["date"]), []).append(row)
    for day, day_rows in sorted(by_day.items()):
        try:
            frame = fetch_day(symbol, day, Path("data/raw/dukascopy"))
        except PlausibilityError as error:
            _record_quarantine(symbol, error)
            for row in day_rows:
                pending[(day, row["side"])] = row
        except DailyFetchError as error:
            for row in day_rows:
                pending[(day, row["side"])] = row
            pending[(day, error.side)] = {"date": day.isoformat(), "side": error.side,
                                          "error": str(error.error)}
        else:
            if not frame.empty:
                month = frame.ts.iloc[0].strftime("%Y-%m")
                retry_frames.setdefault(month, []).append(frame)
    for month, frames in retry_frames.items():
        path = root / symbol / f"{month}.parquet"
        prior = pd.read_parquet(path) if path.exists() else _empty_frame()
        combined = pd.concat([prior, *frames], ignore_index=True).drop_duplicates("ts", keep="last").sort_values("ts")
        month_start = date.fromisoformat(month + "-01")
        next_month = (month_start.replace(day=28) + timedelta(days=4)).replace(day=1)
        month_missing = any(date.fromisoformat(item[0]).strftime("%Y-%m") == month for item in pending)
        complete = start <= month_start and end >= next_month - timedelta(days=1) and next_month <= datetime.now(timezone.utc).date() and not month_missing
        _atomic_month(combined, path, complete)
        from msd.data.catalog import write_manifest
        write_manifest("dukascopy", symbol, combined, "bidask", "tick")
        print(f"final retry wrote {path}: {len(combined)} bars; complete={complete}", flush=True)
    retried_months={day.strftime("%Y-%m") for day in by_day}
    pending_months={day.strftime("%Y-%m") for day, _side in pending}
    for month in sorted(retried_months - pending_months - set(retry_frames)):
        month_start=date.fromisoformat(month+"-01")
        next_month=(month_start.replace(day=28)+timedelta(days=4)).replace(day=1)
        path=root/symbol/f"{month}.parquet"
        if start <= month_start and end >= next_month-timedelta(days=1) and next_month <= datetime.now(timezone.utc).date() and path.exists():
            table=pq.read_table(path)
            metadata=dict(table.schema.metadata or {});metadata[b"msd_complete"]=b"1"
            with tempfile.NamedTemporaryFile(dir=path.parent,suffix=".parquet",delete=False) as tmp:
                temp=Path(tmp.name)
            pq.write_table(table.replace_schema_metadata(metadata),temp);os.replace(temp,path)
            print(f"final retry marked {path} complete after all missing sides resolved",flush=True)
    _write_missing(symbol, list(pending.values()))
    for month in sorted(pending_months):
        _set_month_complete(root / symbol / f"{month}.parquet", False)
        print(f"marked {symbol} {month} incomplete: transport failures remain", flush=True)
    if pending:
        print(f"MISSING DAYS remain for {symbol}: {len(pending)} side failures", flush=True)
    else:
        print(f"final missing-day pass resolved all recorded days for {symbol}", flush=True)
    return len(pending)


def download(symbol: str, start: date, end: date, root: Path = ROOT, workers: int = 2) -> None:
    if symbol not in SCALES and symbol not in PRICE_BANDS:
        raise ValueError(symbol)
    with _COUNT_LOCK:
        _HTTP_503_COUNTS[symbol] = 0
        for key in [key for key in _ERROR_COUNTS if key[0] == symbol]:
            del _ERROR_COUNTS[key]
    if symbol not in SCALES or symbol in CRYPTO_SYMBOLS or _reference_source_path(symbol).exists():
        try:
            calibrate_scale(symbol)
        except Exception:
            with _COUNT_LOCK:
                calibration_503 = _HTTP_503_COUNTS[symbol]
                errors = {kind: count for (sym, kind), count in _ERROR_COUNTS.items() if sym == symbol}
            print(f"Dukascopy summary {symbol}: missing_side_failures={len(_read_missing(symbol))} HTTP_503={calibration_503} errors={errors}",flush=True)
            raise
    if not 1 <= workers <= 8:
        raise ValueError("workers must be between 1 and 8")
    today = datetime.now(timezone.utc).date()
    end = min(end, today)
    month = start.replace(day=1)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        while month <= end:
            if shutil.disk_usage(".").free < 65 * 1024**3:
                raise OSError("Stopping Dukascopy download: less than 65 GiB free")
            next_month = (month.replace(day=28) + timedelta(days=4)).replace(day=1)
            last = min(end, next_month - timedelta(days=1))
            path = root / symbol / f"{month:%Y-%m}.parquet"
            month_missing = any(row["date"].startswith(f"{month:%Y-%m}") for row in _read_missing(symbol))
            complete = (path.exists() and pq.read_metadata(path).metadata.get(b"msd_complete") == b"1"
                        and pq.read_metadata(path).num_rows > 0 and not month_missing)
            if complete and next_month <= today:
                print(f"skip {path}", flush=True)
            else:
                days = _download_days(symbol, month, last, start)
                print(f"fetch {symbol} {month:%Y-%m} ({len(days)} days)", flush=True)
                frames = []
                quarantined_this_year={}
                missing_days=set()
                futures = {pool.submit(fetch_day, symbol, day, Path("data/raw/dukascopy")): day for day in days}
                for n, future in enumerate(as_completed(futures), 1):
                    day=futures[future]
                    try:
                        frames.append(future.result())
                    except PlausibilityError as error:
                        _record_quarantine(symbol,error)
                        quarantined_this_year[day.year]=quarantined_this_year.get(day.year,0)+1
                        day_count=366 if (date(day.year+1,1,1)-date(day.year,1,1)).days==366 else 365
                        if _quarantine_count(symbol,day.year)>0.01*day_count:
                            raise RuntimeError(f"Aborting {symbol}: more than 1% of {day.year} days quarantined") from error
                    except DailyFetchError as error:
                        _record_missing(symbol,error)
                        missing_days.add(day)
                        print(f"MISSING DAY {symbol} {day} {error.side}: {error.error}",flush=True)
                    if n % 10 == 0 or n == len(futures):
                        print(f"{symbol} {month:%Y-%m}: {n}/{len(futures)} days; quarantined={sum(quarantined_this_year.values())}", flush=True)
                frame = pd.concat(frames, ignore_index=True).sort_values("ts") if frames else _empty_frame()
                if frame.empty:
                    if missing_days:
                        print(f"MISSING {symbol} {month:%Y-%m}: {len(missing_days)} days have transport failures; month remains incomplete", flush=True)
                    else:
                        print(f"MISSING {symbol} {month:%Y-%m}: no non-empty daily bars", flush=True)
                    month = next_month
                    continue
                if path.exists() and (month == today.replace(day=1) or start > month or end < next_month - timedelta(days=1)):
                    old = pd.read_parquet(path)
                    if "bad_tick" not in old: old["bad_tick"]=False
                    frame = pd.concat([old, frame], ignore_index=True).drop_duplicates("ts", keep="last").sort_values("ts")
                path.parent.mkdir(parents=True, exist_ok=True)
                month_missing = any(row["date"].startswith(f"{month:%Y-%m}") for row in _read_missing(symbol))
                complete = start <= month and end >= next_month - timedelta(days=1) and next_month <= today and not month_missing
                _atomic_month(frame,path,complete)
                stored_rows=pq.read_metadata(path).num_rows
                if stored_rows!=len(frame) or stored_rows==0:
                    raise ValueError(f"Dukascopy Parquet verification failed for {path}")
                from msd.data.catalog import write_manifest
                write_manifest("dukascopy", symbol, frame, "bidask", "tick")
                print(f"verified {path}: {stored_rows} bars", flush=True)
            month = next_month
    missing_count = _final_missing_pass(symbol,root,start,end)
    with _COUNT_LOCK:
        count_503 = _HTTP_503_COUNTS[symbol]
        errors = {kind: count for (sym, kind), count in _ERROR_COUNTS.items() if sym == symbol}
    print(f"Dukascopy summary {symbol}: missing_side_failures={missing_count} HTTP_503={count_503} errors={errors}",flush=True)


def load(symbol: str, start: date | str, end: date | str, root: Path = ROOT) -> pd.DataFrame:
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    start = start.tz_localize("UTC") if start.tzinfo is None else start.tz_convert("UTC")
    end = end.tz_localize("UTC") if end.tzinfo is None else end.tz_convert("UTC")
    paths = sorted((root / symbol).glob("*.parquet"))
    frames = [pd.read_parquet(p) for p in paths if start.strftime("%Y-%m") <= p.stem <= end.strftime("%Y-%m")]
    if not frames:
        return _empty_frame()
    # Normalize parquet timestamp units before concat (pandas 3 otherwise
    # promotes mixed ns/us UTC timestamps to object dtype).
    for frame in frames:
        frame["ts"] = pd.to_datetime(frame.ts, utc=True).astype("datetime64[ns, UTC]")
        for column in COLUMNS[1:]:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    result = pd.concat(frames, ignore_index=True)
    if result.empty:
        return _empty_frame()
    result=mark_bad_ticks(result)
    return result[(result.ts >= start) & (result.ts < end + pd.Timedelta(days=1))].sort_values("ts").reset_index(drop=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", required=True, choices=tuple(sorted(set(SCALES) | set(PRICE_BANDS))))
    parser.add_argument("--start", required=True, type=date.fromisoformat)
    parser.add_argument("--end", type=date.fromisoformat, default=datetime.now(timezone.utc).date())
    parser.add_argument("--workers", type=int, default=2)
    args = parser.parse_args()
    download(args.symbol, args.start, args.end, workers=args.workers)


if __name__ == "__main__":
    main()
