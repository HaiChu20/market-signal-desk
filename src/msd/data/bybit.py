"""Verified Bybit public trades and causal minute taker-flow bars."""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import os
import random
import re
import shutil
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from msd.data.archive_download import HEADERS, MIN_FREE_BYTES, remote_size, stream_archive

MAIN = Path("/Users/bfhach/Projects/market-signal-desk")
RAW = MAIN / "data/raw/bybit"
OUT = MAIN / "data/bars/bybit_flow"
MISSING = MAIN / "data/logs/missing_bybit.csv"
BASE = "https://public.bybit.com/trading"
# MSD_BYBIT_SYMBOLS lets BTC and ETH run as separate processes (one CPU core each).
SYMBOLS = tuple(os.environ.get("MSD_BYBIT_SYMBOLS", "BTCUSDT,ETHUSDT").split(","))
START = date(2020, 3, 25)
# Parallel day downloads per process; one stream reaches only ~3 MB/s from public.bybit.com.
THREADS = int(os.environ.get("MSD_BYBIT_THREADS", "2"))


def url(symbol: str, day: date) -> str:
    return f"{BASE}/{symbol}/{symbol}{day:%Y-%m-%d}.csv.gz"


def listed_days(symbol: str) -> set[date]:
    with urlopen(Request(f"{BASE}/{symbol}/", headers=HEADERS), timeout=60) as response:
        listing = response.read().decode("utf-8")
    return {date.fromisoformat(value) for value in re.findall(rf'{symbol}(\d{{4}}-\d{{2}}-\d{{2}})\.csv\.gz', listing)}


REQUIRED = ("timestamp", "side", "size", "price")
COLUMNS = ["ts", "known_at", "buy_taker_volume", "sell_taker_volume", "delta",
           "buy_trade_count", "sell_trade_count", "vwap_buy", "vwap_sell",
           "max_trade", "trade_count"]


def _read_trades(source, name: str) -> pd.DataFrame:
    """Parse one gzip CSV archive in C; per-row Python parsing took ~30 s per BTC day."""
    with gzip.open(source, "rt", newline="") as handle:
        header = next(csv.reader(handle), [])
    if not set(REQUIRED) <= set(header):
        raise ValueError(f"Bybit schema mismatch: {name}")
    if isinstance(source, io.BytesIO):
        source.seek(0)
    return pd.read_csv(source, compression="gzip", engine="pyarrow", usecols=list(REQUIRED),
                       dtype={"timestamp": "float64", "side": "str", "size": "float64", "price": "float64"})


def _accumulate(trades: pd.DataFrame, month: str, source: str, acc: np.ndarray) -> None:
    """Add trades to the month's per-minute sums, in file row order like a row loop."""
    side = trades["side"].str.lower()
    bad = ~side.isin(("buy", "sell"))
    if bad.any():
        raise ValueError(f"invalid taker side: {side[bad].iloc[0]}")
    size = trades["size"].to_numpy(dtype=float)
    price = trades["price"].to_numpy(dtype=float)
    # Historical Bybit files contain genuine zero-size dust trades; retain
    # their trade counts while they contribute zero to volume and VWAP.
    if not (((0 <= size) & (size < np.inf)).all() and ((0 < price) & (price < np.inf)).all()):
        raise ValueError("invalid size or price")
    stamps = pd.to_datetime(trades["timestamp"].to_numpy(dtype=float), unit="s", utc=True)
    if stamps.isna().any():
        raise ValueError(f"invalid timestamp: {source}")
    minute = ((stamps.floor("min") - pd.Timestamp(f"{month}-01", tz="UTC"))
              // pd.Timedelta(minutes=1)).to_numpy(dtype=np.int64)
    if ((minute < 0) | (minute >= acc.shape[1])).any():
        raise ValueError(f"trade outside archive month: {source}")
    buy = side.eq("buy").to_numpy(dtype=bool)
    # ufunc.at adds unbuffered in index order, so float sums match sequential accumulation.
    for column, mask in ((0, buy), (1, ~buy)):
        np.add.at(acc[column], minute[mask], size[mask])
        np.add.at(acc[column + 2], minute[mask], 1.0)
        np.add.at(acc[column + 4], minute[mask], size[mask] * price[mask])
    np.maximum.at(acc[6], minute, size)
    np.add.at(acc[7], minute, 1.0)


def _month_acc(month: str) -> np.ndarray:
    return np.zeros((8, pd.Period(month, "M").days_in_month * 1440))


def _to_frame(acc: np.ndarray, month: str) -> pd.DataFrame:
    present = np.flatnonzero(acc[7])
    if not len(present):
        return pd.DataFrame.from_records([], columns=COLUMNS)
    v = acc[:, present]
    start = pd.Timestamp(f"{month}-01", tz="UTC").as_unit("ns")
    ts = pd.DatetimeIndex(start + pd.to_timedelta(present, unit="min")).as_unit("ns")
    with np.errstate(divide="ignore", invalid="ignore"):
        vwap_buy = np.where(v[0] != 0, v[4] / v[0], np.nan)
        vwap_sell = np.where(v[1] != 0, v[5] / v[1], np.nan)
    return pd.DataFrame({"ts": ts, "known_at": ts + pd.Timedelta(minutes=1),
                         "buy_taker_volume": v[0], "sell_taker_volume": v[1], "delta": v[0] - v[1],
                         "buy_trade_count": v[2].astype(np.int64), "sell_trade_count": v[3].astype(np.int64),
                         "vwap_buy": vwap_buy, "vwap_sell": vwap_sell, "max_trade": v[6],
                         "trade_count": v[7].astype(np.int64)}, columns=COLUMNS)


def aggregate_bytes(raw: bytes, month: str) -> pd.DataFrame:
    acc = _month_acc(month)
    _accumulate(_read_trades(io.BytesIO(raw), "memory archive"), month, "memory archive", acc)
    return _to_frame(acc, month)


def aggregate_files(paths: list[Path], month: str) -> pd.DataFrame:
    acc = _month_acc(month)
    for path in paths:
        _accumulate(_read_trades(path, str(path)), month, str(path), acc)
    return _to_frame(acc, month)


def write_month(symbol: str, month: str, paths: list[Path]) -> int:
    frame = aggregate_files(paths, month)
    if frame.empty:
        return 0
    target = OUT / symbol / f"{month}.parquet"
    manifest_path = OUT / symbol / "manifest.json"
    if target.exists():
        stored = pq.read_table(target).to_pandas().sort_values("ts").reset_index(drop=True)
        verified_days = (json.loads(manifest_path.read_text()).get("days", {})
                         if manifest_path.exists() else {})
        for day in sorted({p.name[-17:-7] for p in paths} & verified_days.keys()):
            old_day = stored[stored.ts.dt.strftime("%Y-%m-%d").eq(day)].reset_index(drop=True)
            new_day = frame[frame.ts.dt.strftime("%Y-%m-%d").eq(day)].reset_index(drop=True)
            try:
                pd.testing.assert_frame_equal(old_day, new_day)
            except AssertionError as error:
                print(f"MISMATCH raw versus memory summary {symbol} {day}: {str(error).splitlines()[0]}", flush=True)
        try:
            pd.testing.assert_frame_equal(stored, frame.reset_index(drop=True))
            print(f"MATCH raw versus stored parquet {symbol} {month}; skipping rewrite", flush=True)
            return len(frame)
        except AssertionError:
            print(f"UPDATE raw month differs from stored parquet {symbol} {month}", flush=True)
    target.parent.mkdir(parents=True, exist_ok=True)
    scratch = Path("data/tmp/free_downloaders")
    scratch.mkdir(parents=True, exist_ok=True)
    tmp = scratch / f"bybit-{symbol}-{month}.parquet.part.{os.getpid()}"
    try:
        table = pa.Table.from_pandas(frame, preserve_index=False)
        metadata = dict(table.schema.metadata or {})
        metadata[b"source_days"] = ",".join(p.name for p in paths).encode()
        pq.write_table(table.replace_schema_metadata(metadata), tmp)
        if pq.read_metadata(tmp).num_rows != len(frame):
            raise ValueError("Parquet row count mismatch")
        os.replace(tmp, target)
    finally:
        tmp.unlink(missing_ok=True)
    return len(frame)


def log_missing(symbol: str, day: date, reason: str) -> None:
    MISSING.parent.mkdir(parents=True, exist_ok=True)
    new = not MISSING.exists()
    with MISSING.open("a", newline="") as handle:
        writer = csv.writer(handle)
        if new:
            writer.writerow(["logged_at", "symbol", "date", "reason"])
        writer.writerow([datetime.now(timezone.utc).isoformat(), symbol, day.isoformat(), reason])


# Back off on CDN rate limiting instead of marking days missing: on 2026-11-11 a 403 burst
# (after raising concurrency) lasted ~7 minutes and the short archive retries gave up.
BLOCK_WAITS = (60, 120, 300, 600, 900)


def fetch_day(symbol: str, day: date) -> tuple[date, Path | None, str]:
    target = RAW / symbol / f"{symbol}{day:%Y-%m-%d}.csv.gz"
    for wait in (*BLOCK_WAITS, None):
        try:
            expected = remote_size(url(symbol, day))
            if expected is None:
                return day, None, "HTTP 404"
            digest = stream_archive(url(symbol, day), target, expected)
            return day, target if digest else None, f"{expected} bytes"
        except Exception as error:
            if wait is None or not any(code in str(error) for code in ("HTTP Error 403", "HTTP Error 429")):
                raise
            print(f"rate-limited on {symbol} {day} ({error}); retrying in {wait}s", flush=True)
            time.sleep(wait)


def fetch_no_raw_day(symbol: str, day: date) -> tuple[date, pd.DataFrame | None, dict | None, str]:
    source = url(symbol, day)
    expected = remote_size(source)
    if expected is None:
        return day, None, None, "HTTP 404"
    for attempt in range(5):
        try:
            if shutil.disk_usage(MAIN).free < MIN_FREE_BYTES:
                raise OSError("free disk below 15 GiB")
            with urlopen(Request(source, headers=HEADERS), timeout=120) as response:
                length = response.headers.get("Content-Length")
                if length and int(length) != expected:
                    raise ValueError("HEAD size differs from Content-Length")
                raw = response.read(expected + 1)
            if len(raw) != expected:
                raise ValueError(f"downloaded size {len(raw)} != expected {expected}")
            digest = hashlib.sha256(raw).hexdigest()
            frame = aggregate_bytes(raw, day.strftime("%Y-%m"))
            del raw
            if frame.empty:
                raise ValueError("empty trade archive")
            info = {"date": day.isoformat(), "bytes": expected, "sha256": digest,
                    "row_count": int(frame.trade_count.sum()), "minute_count": len(frame)}
            return day, frame, info, f"{expected} bytes SHA256 {digest[:12]}"
        except OSError as error:
            if "15 GiB" in str(error):
                raise
            last = error
        except Exception as error:
            last = error
        if attempt < 4:
            time.sleep(min(60, 2**attempt) + random.random())
    raise RuntimeError(f"{symbol} {day}: {type(last).__name__}: {last}")


def _write_no_raw_month(symbol: str, month: str, frames: list[pd.DataFrame],
                        completed: list[date], updates: dict[str, dict],
                        manifest: dict[str, dict]) -> int:
    target = OUT / symbol / f"{month}.parquet"
    if target.exists():
        prior = pq.read_table(target).to_pandas()
        prior = prior[~prior.ts.dt.date.isin(completed)]
        frames.insert(0, prior)
    frame = pd.concat(frames, ignore_index=True).sort_values("ts")
    if frame.ts.duplicated().any():
        raise ValueError(f"duplicate minute in {symbol} {month}")
    target.parent.mkdir(parents=True, exist_ok=True)
    scratch = Path("data/tmp/free_downloaders")
    scratch.mkdir(parents=True, exist_ok=True)
    tmp = scratch / f"bybit-memory-{symbol}-{month}.parquet.part.{os.getpid()}"
    try:
        pq.write_table(pa.Table.from_pandas(frame, preserve_index=False), tmp)
        if pq.read_metadata(tmp).num_rows != len(frame):
            raise ValueError("Parquet row count mismatch")
        os.replace(tmp, target)
    finally:
        tmp.unlink(missing_ok=True)
    manifest.update(updates)
    manifest_path = OUT / symbol / "manifest.json"
    manifest_tmp = scratch / f"bybit-manifest-{symbol}.part.{os.getpid()}"
    manifest_tmp.write_text(json.dumps({"days": manifest}, sort_keys=True) + "\n")
    os.replace(manifest_tmp, manifest_path)
    return len(frame)


def run_no_raw(end: date | None = None) -> None:
    end = end or datetime.now(timezone.utc).date() - timedelta(days=1)
    for symbol in SYMBOLS:
        available = listed_days(symbol)
        manifest_path = OUT / symbol / "manifest.json"
        manifest = json.loads(manifest_path.read_text()).get("days", {}) if manifest_path.exists() else {}
        months: dict[str, list[date]] = defaultdict(list)
        for i in range((end - START).days + 1):
            day = START + timedelta(days=i)
            months[day.strftime("%Y-%m")].append(day)
        for month, days in sorted(months.items()):
            out = OUT / symbol / f"{month}.parquet"
            pending = [day for day in days if day in available and (day.isoformat() not in manifest or not out.exists())]
            for day in days:
                if day not in available:
                    log_missing(symbol, day, "absent from listing")
            if not pending:
                continue
            frames, updates = [], {}
            with ThreadPoolExecutor(max_workers=THREADS) as pool:
                futures = {pool.submit(fetch_no_raw_day, symbol, day): day for day in pending}
                for future in as_completed(futures):
                    day = futures[future]
                    try:
                        _, frame, info, message = future.result()
                        if frame is None:
                            log_missing(symbol, day, message)
                        else:
                            frames.append(frame)
                            updates[day.isoformat()] = info
                            print(f"verified in memory {symbol} {day}: {message}", flush=True)
                    except OSError as error:
                        if "15 GiB" in str(error):
                            pool.shutdown(cancel_futures=True)
                            raise
                        log_missing(symbol, day, str(error))
                    except Exception as error:
                        log_missing(symbol, day, str(error))
            if frames:
                count = _write_no_raw_month(symbol, month, frames,
                                            [date.fromisoformat(day) for day in updates], updates, manifest)
                print(f"aggregated {symbol} {month}: {count} minutes; {len(updates)} days recorded", flush=True)


def run(end: date | None = None) -> None:
    end = end or datetime.now(timezone.utc).date() - timedelta(days=1)
    for symbol in SYMBOLS:
        available = listed_days(symbol)
        days = [START + timedelta(days=i) for i in range((end - START).days + 1)]
        months: dict[str, list[date]] = defaultdict(list)
        for day in days:
            months[day.strftime("%Y-%m")].append(day)
        for month, month_days in sorted(months.items()):
            paths = []
            jobs = [day for day in month_days if day in available]
            for day in month_days:
                if day not in available:
                    log_missing(symbol, day, "absent from listing")
            with ThreadPoolExecutor(max_workers=THREADS) as pool:
                futures = {pool.submit(fetch_day, symbol, day): day for day in jobs}
                for future in as_completed(futures):
                    day = futures[future]
                    try:
                        _, path, result = future.result()
                        if path is None:
                            log_missing(symbol, day, result)
                        else:
                            paths.append(path)
                            print(f"verified {symbol} {day}: {result}", flush=True)
                    except OSError as error:
                        if "15 GiB" in str(error):
                            pool.shutdown(cancel_futures=True)
                            raise
                        log_missing(symbol, day, str(error))
                    except Exception as error:
                        log_missing(symbol, day, str(error))
            if paths and len(paths) == len(jobs):
                rows = write_month(symbol, month, sorted(paths))
                print(f"aggregated {symbol} {month}: {rows} minutes", flush=True)
            elif paths:
                print(f"INCOMPLETE {symbol} {month}: {len(paths)}/{len(jobs)} archives; parquet not rewritten", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--end", type=date.fromisoformat)
    parser.add_argument("--no-raw", action="store_true")
    args = parser.parse_args()
    (run_no_raw if args.no_raw else run)(args.end)
