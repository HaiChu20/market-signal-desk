"""Dukascopy hourly quote ticks, causal flow summaries, and one-second bars.

The BI5 layout and zero-based URL month are documented by Dukascopy. Quote
sizes are top-of-book quantities, not executed trade volume. OFI uses the
best-quote event formula of Cont, Kukanov, and Stoikov (2014).
"""
from __future__ import annotations

import argparse
import calendar
import csv
import hashlib
import http.client
import lzma
import os
import random
import shutil
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from msd.data.archive_download import MIN_FREE_BYTES
from msd.data.dukascopy import SCALES, RANGES

MAIN = Path("/Users/bfhach/Projects/market-signal-desk")
RAW = MAIN / "data/raw/dukascopy_ticks"
FLOW = MAIN / "data/bars/dukascopy_flow"
SECONDS = MAIN / "data/bars/dukascopy_1s"
REFERENCE = MAIN / "data/bars/dukascopy"
MISSING = MAIN / "data/logs/missing_dukascopy_ticks.csv"
QUARANTINE = MAIN / "data/logs/quarantine_dukascopy_ticks.csv"
START = {"USATECHIDXUSD": date(2018, 12, 16),
         "USA500IDXUSD": date(2018, 12, 16), "XAUUSD": date(2008, 1, 1)}
DTYPE = np.dtype([("ms", ">u4"), ("ask", ">u4"), ("bid", ">u4"),
                  ("ask_size", ">f4"), ("bid_size", ">f4")])
HOST = "datafeed.dukascopy.com"
REDIRECT_WAIT = 65
_LOCAL = threading.local()


def _connection() -> http.client.HTTPConnection:
    conn = getattr(_LOCAL, "conn", None)
    if conn is None:
        # The working public HTTPS URL redirects to this HTTP datafeed host.
        # Direct HTTPS datafeed timed out in a 60-second single-connection test.
        conn = http.client.HTTPConnection(HOST, timeout=20)
        _LOCAL.conn = conn
    return conn


def _disconnect() -> None:
    conn = getattr(_LOCAL, "conn", None)
    _LOCAL.conn = None
    if conn is not None:
        try:
            conn.close()
        except OSError:
            pass


def tick_workers() -> int:
    return max(1, min(4, int(os.environ.get("MSD_TICK_WORKERS", "2"))))


def url(symbol: str, hour: datetime) -> str:
    return (f"https://datafeed.dukascopy.com/datafeed/{symbol}/{hour:%Y}/"
            f"{hour.month - 1:02d}/{hour:%d}/{hour:%H}h_ticks.bi5")


def raw_path(symbol: str, hour: datetime) -> Path:
    return RAW / symbol / f"{hour:%Y/%m/%d/%H}h_ticks.bi5"


def decode_ticks(raw: bytes, symbol: str, hour: datetime) -> pd.DataFrame:
    payload = lzma.decompress(raw)
    if len(payload) % DTYPE.itemsize:
        raise ValueError("BI5 tick payload is not divisible by 20 bytes")
    values = np.frombuffer(payload, dtype=DTYPE)
    if not len(values):
        raise ValueError("empty BI5 tick archive")
    offsets = values["ms"].astype(np.int64)
    ask = values["ask"].astype(np.float64) / SCALES[symbol]
    bid = values["bid"].astype(np.float64) / SCALES[symbol]
    ask_size = values["ask_size"].astype(np.float64)
    bid_size = values["bid_size"].astype(np.float64)
    lo, hi = RANGES[symbol]
    if (offsets >= 3_600_000).any() or (bid <= 0).any() or (ask < bid).any():
        raise ValueError("invalid tick offset or crossed/nonpositive quote")
    if (bid < lo).any() or (ask > hi).any():
        raise ValueError(f"tick price outside calibrated {symbol} range [{lo}, {hi}]")
    if not np.isfinite(ask_size).all() or not np.isfinite(bid_size).all() or (ask_size < 0).any() or (bid_size < 0).any():
        raise ValueError("invalid quote size")
    base = pd.Timestamp(hour, tz="UTC") if hour.tzinfo is None else pd.Timestamp(hour).tz_convert("UTC")
    frame = pd.DataFrame({"ts": base + pd.to_timedelta(offsets, unit="ms"),
                          "bid": bid, "ask": ask,
                          "bid_size": bid_size, "ask_size": ask_size})
    return frame.sort_values("ts", kind="stable").reset_index(drop=True)


def aggregate_ticks(ticks: pd.DataFrame, previous: tuple | None = None) -> tuple[pd.DataFrame, pd.DataFrame, tuple]:
    if ticks.empty:
        raise ValueError("cannot aggregate empty tick frame")
    frame = ticks.copy()
    bid, ask = frame.bid.to_numpy(), frame.ask.to_numpy()
    bsize, asize = frame.bid_size.to_numpy(), frame.ask_size.to_numpy()
    if previous is None:
        prev_bid, prev_ask, prev_bsize, prev_asize = bid[0], ask[0], bsize[0], asize[0]
    else:
        prev_bid, prev_ask, prev_bsize, prev_asize = previous
    pbid = np.r_[prev_bid, bid[:-1]]
    pask = np.r_[prev_ask, ask[:-1]]
    pbsize = np.r_[prev_bsize, bsize[:-1]]
    pasize = np.r_[prev_asize, asize[:-1]]
    ofi = (np.where(bid >= pbid, bsize, 0) - np.where(bid <= pbid, pbsize, 0)
           - np.where(ask <= pask, asize, 0) + np.where(ask >= pask, pasize, 0))
    if previous is None:
        ofi[0] = 0
    frame["ofi"] = ofi
    frame["spread"] = ask - bid
    frame["mid"] = (ask + bid) / 2
    frame["minute"] = frame.ts.dt.floor("min")
    frame["second"] = frame.ts.dt.floor("s")
    frame["ms_in_minute"] = ((frame.ts - frame.minute).dt.total_seconds() * 1000).astype("int32")
    minute = frame.groupby("minute", sort=True).agg(
        tick_count=("mid", "size"), mean_spread=("spread", "mean"),
        max_spread=("spread", "max"), bid_size_sum=("bid_size", "sum"),
        ask_size_sum=("ask_size", "sum"), ofi=("ofi", "sum"),
        bid_o=("bid", "first"), bid_h=("bid", "max"), bid_l=("bid", "min"), bid_c=("bid", "last"),
        ask_o=("ask", "first"), ask_h=("ask", "max"), ask_l=("ask", "min"), ask_c=("ask", "last"))
    minute["size_imbalance"] = ((minute.bid_size_sum - minute.ask_size_sum) /
                                 (minute.bid_size_sum + minute.ask_size_sum).replace(0, np.nan))
    minute["mid_high_ms"] = frame.loc[frame.groupby("minute").mid.idxmax()].set_index("minute").ms_in_minute
    minute["mid_low_ms"] = frame.loc[frame.groupby("minute").mid.idxmin()].set_index("minute").ms_in_minute
    minute = minute.reset_index().rename(columns={"minute": "ts"})
    minute.insert(1, "known_at", minute.ts + pd.Timedelta(minutes=1))
    second = frame.groupby("second", sort=True).agg(
        bid_o=("bid", "first"), bid_h=("bid", "max"), bid_l=("bid", "min"), bid_c=("bid", "last"),
        ask_o=("ask", "first"), ask_h=("ask", "max"), ask_l=("ask", "min"), ask_c=("ask", "last"),
        tick_count=("bid", "size")).reset_index().rename(columns={"second": "ts"})
    second.insert(1, "known_at", second.ts + pd.Timedelta(seconds=1))
    return minute, second, (bid[-1], ask[-1], bsize[-1], asize[-1])


def _log(path: Path, fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", newline="") as handle:
        csv.writer(handle).writerow([datetime.now(timezone.utc).isoformat(), *fields])


def fetch_hour(symbol: str, hour: datetime) -> tuple[datetime, Path | None, str]:
    target = raw_path(symbol, hour)
    sidecar = Path(str(target) + ".sha256")
    if target.exists() and sidecar.exists():
        raw = target.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if digest == sidecar.read_text().split()[0]:
            try:
                decode_ticks(raw, symbol, hour)
            except Exception as error:
                raise ValueError(f"retained raw decode failed: {error}") from error
            return hour, target, "resume verified"
        raise ValueError(f"retained raw SHA256 mismatch: {target}")
    path = urlsplit(url(symbol, hour)).path
    last: Exception | None = None
    for attempt in range(5):
        try:
            if shutil.disk_usage(MAIN).free < MIN_FREE_BYTES:
                raise OSError("free disk below 15 GiB")
            conn = _connection()
            conn.request("GET", path, headers={"User-Agent": "Mozilla/5.0 (compatible; MarketSignalDesk/0.1)",
                                                       "Connection": "keep-alive"})
            response = conn.getresponse()
            expected = response.getheader("Content-Length")
            raw = response.read()
            if response.status == 404:
                return hour, None, "HTTP 404"
            if response.status in (429, 503):
                raise OSError(f"HTTP {response.status} for {path}")
            if response.status != 200:
                raise OSError(f"HTTP {response.status} for {path}")
            if expected and len(raw) != int(expected):
                raise OSError("BI5 Content-Length mismatch")
            if not raw:
                return hour, None, "empty archive"
            decode_ticks(raw, symbol, hour)
            digest = hashlib.sha256(raw).hexdigest()
            target.parent.mkdir(parents=True, exist_ok=True)
            scratch = Path("data/tmp/dukascopy_ticks")
            scratch.mkdir(parents=True, exist_ok=True)
            tmp = scratch / f"{symbol}-{hour:%Y%m%d%H}.part.{os.getpid()}"
            tmp.write_bytes(raw)
            os.replace(tmp, target)
            side_tmp = scratch / f"{symbol}-{hour:%Y%m%d%H}.sha256.part.{os.getpid()}"
            side_tmp.write_text(f"{digest}  {target.name}\n")
            os.replace(side_tmp, sidecar)
            return hour, target, f"{len(raw)} bytes SHA256 {digest[:12]}"
        except (http.client.RemoteDisconnected, ConnectionResetError, http.client.BadStatusLine) as error:
            _disconnect()
            last = error
        except OSError as error:
            if "15 GiB" in str(error):
                raise
            _disconnect()
            last = error
        except ValueError:
            raise
        except Exception as error:
            last = error
        if attempt < 4:
            # A 301 means DNS gave the HTTPS-only cloud proxy (60 s TTL); wait for the HTTP origin.
            redirected = isinstance(last, OSError) and str(last).startswith("HTTP 301")
            time.sleep((REDIRECT_WAIT if redirected else min(60, 2 ** (attempt + 1))) + random.random())
    raise RuntimeError(f"{symbol} {hour}: {type(last).__name__}: {last}")


def _write_parquet(frame: pd.DataFrame, target: Path, through: date, complete: bool) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    scratch = Path("data/tmp/dukascopy_ticks")
    scratch.mkdir(parents=True, exist_ok=True)
    tmp = scratch / f"{target.parent.name}-{target.stem}-{target.parent.parent.name}.part.{os.getpid()}"
    try:
        table = pa.Table.from_pandas(frame, preserve_index=False)
        metadata = dict(table.schema.metadata or {})
        metadata.update({b"through_day": through.isoformat().encode(), b"complete": b"1" if complete else b"0"})
        pq.write_table(table.replace_schema_metadata(metadata), tmp)
        if pq.read_metadata(tmp).num_rows != len(frame):
            raise ValueError("Parquet row count mismatch")
        os.replace(tmp, target)
    finally:
        tmp.unlink(missing_ok=True)


def _complete(path: Path, through: date) -> bool:
    if not path.exists():
        return False
    metadata = pq.read_metadata(path).metadata or {}
    return metadata.get(b"complete") == b"1" and metadata.get(b"through_day", b"").decode() >= through.isoformat()


def ohlc_match_rate(symbol: str, month: str, flow: pd.DataFrame) -> tuple[int, int]:
    reference = REFERENCE / symbol / f"{month}.parquet"
    if not reference.exists():
        return 0, 0
    candles = pd.read_parquet(reference, columns=["ts", "bid_o", "bid_h", "bid_l", "bid_c",
                                                   "ask_o", "ask_h", "ask_l", "ask_c"])
    aligned = flow.merge(candles, on="ts", suffixes=("_tick", "_stored"))
    if len(aligned):
        ratio = float(np.median(aligned.bid_c_tick) / np.median(aligned.bid_c_stored))
        if not 0.98 <= ratio <= 1.02:
            raise ValueError(f"{symbol} {month} tick point scale disagrees with stored 1m bars: ratio={ratio:g}")
    columns = [f"{side}_{field}" for side in ("bid", "ask") for field in "ohlc"]
    matches = np.ones(len(aligned), dtype=bool)
    for column in columns:
        matches &= np.isclose(aligned[f"{column}_tick"], aligned[f"{column}_stored"], rtol=0, atol=1e-6)
    return int(matches.sum()), len(aligned)


def process_month(symbol: str, month: str, hours: list[datetime], through: date) -> None:
    print(f"START ticks {symbol} {month}: {len(hours)} candidate hours", flush=True)
    flow_target = FLOW / symbol / f"{month}.parquet"
    second_target = SECONDS / symbol / f"{month}.parquet"
    if _complete(flow_target, through) and _complete(second_target, through):
        print(f"skip complete {symbol} {month}", flush=True)
        return
    found: dict[datetime, Path] = {}
    failed = False
    with ThreadPoolExecutor(max_workers=tick_workers()) as pool:
        futures = {pool.submit(fetch_hour, symbol, hour): hour for hour in hours}
        for future in as_completed(futures):
            hour = futures[future]
            try:
                _, path, message = future.result()
                if path is None:
                    _log(MISSING, [symbol, hour.isoformat(), message])
                else:
                    found[hour] = path
                    print(f"verified {symbol} {hour:%Y-%m-%d %H}: {message}", flush=True)
            except OSError as error:
                if "15 GiB" in str(error):
                    pool.shutdown(cancel_futures=True)
                    raise
                failed = True
                _log(MISSING, [symbol, hour.isoformat(), str(error)])
            except ValueError as error:
                failed = True
                _log(QUARANTINE, [symbol, hour.isoformat(), str(error)])
            except Exception as error:
                failed = True
                _log(MISSING, [symbol, hour.isoformat(), str(error)])
    flow_parts, second_parts = [], []
    previous = None
    last_hour = None
    for hour, path in sorted(found.items()):
        try:
            ticks = decode_ticks(path.read_bytes(), symbol, hour)
            if last_hour is None or hour - last_hour > timedelta(hours=1):
                previous = None
            flow, second, previous = aggregate_ticks(ticks, previous)
            flow_parts.append(flow)
            second_parts.append(second)
            last_hour = hour
        except Exception as error:
            failed = True
            _log(QUARANTINE, [symbol, hour.isoformat(), str(error)])
    if not flow_parts:
        print(f"EMPTY {symbol} {month}; no parquet written", flush=True)
        return
    flow = pd.concat(flow_parts, ignore_index=True).sort_values("ts")
    second = pd.concat(second_parts, ignore_index=True).sort_values("ts")
    try:
        matches, compared = ohlc_match_rate(symbol, month, flow)
    except ValueError as error:
        _log(QUARANTINE, [symbol, month, str(error)])
        print(f"QUARANTINE {symbol} {month}: {error}", flush=True)
        return
    print(f"OHLC MATCH {symbol} {month}: {matches}/{compared} = {matches/compared:.2%}" if compared
          else f"OHLC MATCH {symbol} {month}: no stored overlapping minute bars", flush=True)
    _write_parquet(flow, flow_target, through, not failed)
    _write_parquet(second, second_target, through, not failed)
    print(f"wrote {symbol} {month}: {len(flow)} minutes, {len(second)} seconds, complete={not failed}", flush=True)


def run(end: date | None = None) -> None:
    end = end or datetime.now(timezone.utc).date() - timedelta(days=1)
    jobs: dict[tuple[str, str], list[datetime]] = defaultdict(list)
    for symbol, start in START.items():
        day = start
        while day <= end:
            if day.weekday() != 5:
                for hour in range(24):
                    jobs[(day.strftime("%Y-%m"), symbol)].append(
                        datetime(day.year, day.month, day.day, hour, tzinfo=timezone.utc))
            day += timedelta(days=1)
    for (month, symbol), hours in sorted(jobs.items(), reverse=True):
        year, month_number = map(int, month.split("-"))
        through = min(end, date(year, month_number, calendar.monthrange(year, month_number)[1]))
        process_month(symbol, month, hours, through)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--end", type=date.fromisoformat)
    args = parser.parse_args()
    run(args.end)
