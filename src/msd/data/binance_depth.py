"""Verified Binance USD-M bookDepth archives and timestamped depth snapshots."""
from __future__ import annotations

import argparse
import csv
import hashlib
import math
import os
import zipfile
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from msd.data.archive_download import HEADERS, remote_size, stream_archive

MAIN = Path("/Users/bfhach/Projects/market-signal-desk")
RAW = MAIN / "data/raw/binance/bookDepth"
OUT = MAIN / "data/aux/binance_depth"
BASE = "https://data.binance.vision/data/futures/um/daily/bookDepth"
SYMBOLS = ("BTCUSDT", "ETHUSDT")
START = date(2023, 1, 1)
MISSING = MAIN / "data/logs/missing_bookdepth.csv"
REQUIRED_BANDS = (-5, -4, -3, -2, -1, 1, 2, 3, 4, 5)
OPTIONAL_BANDS = (-0.2, 0.2)


def log_missing(symbol: str, day_or_month: str, scope: str, reason: str) -> None:
    MISSING.parent.mkdir(parents=True, exist_ok=True)
    with MISSING.open("a", newline="") as stream:
        writer = csv.writer(stream)
        if stream.tell() == 0:
            writer.writerow(["symbol", "date_or_month", "scope", "reason"])
        writer.writerow([symbol, day_or_month, scope, reason])
    print(f"FAILED {symbol} {day_or_month} ({scope}): {reason}", flush=True)


def url(symbol: str, day: date) -> str:
    return f"{BASE}/{symbol}/{symbol}-bookDepth-{day:%Y-%m-%d}.zip"


def checksum(url_: str) -> str | None:
    try:
        with urlopen(Request(url_ + ".CHECKSUM", headers=HEADERS), timeout=60) as response:
            digest = response.read().decode("ascii").split()[0].lower()
    except HTTPError as error:
        if error.code == 404:
            return None
        raise
    if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise ValueError("invalid Binance CHECKSUM")
    return digest


def parse_depth_rows(rows: list[dict[str, str]]) -> pd.DataFrame:
    snapshots: dict[pd.Timestamp, dict[str, float]] = defaultdict(dict)
    for row in rows:
        if not {"timestamp", "percentage", "depth", "notional"} <= row.keys():
            raise ValueError("bookDepth schema missing required columns")
        ts = pd.to_datetime(row["timestamp"], utc=True)
        pct = float(row["percentage"])
        depth, notional = float(row["depth"]), float(row["notional"])
        if not all(map(math.isfinite, (pct, depth, notional))) or pct not in (*REQUIRED_BANDS, *OPTIONAL_BANDS) or depth < 0 or notional < 0:
            raise ValueError("invalid bookDepth band or value")
        side = "bid" if pct < 0 else "ask"
        band = "0p2" if abs(pct) == 0.2 else str(int(abs(pct)))
        key = f"{side}_{band}pct"
        record = snapshots[ts]
        if f"depth_{key}" in record:
            raise ValueError(f"duplicate bookDepth band: {ts} {pct}")
        record[f"depth_{key}"] = depth
        record[f"notional_{key}"] = notional
    result = []
    for ts, values in sorted(snapshots.items()):
        required = [f"{kind}_{side}_{abs(band)}pct" for band in REQUIRED_BANDS
                    for kind in ("depth", "notional") for side in (("bid",) if band < 0 else ("ask",))]
        if not all(key in values for key in required):
            raise ValueError(f"incomplete bookDepth snapshot {ts}: missing required bands")
        optional = [f"{kind}_{side}_0p2pct" for kind in ("depth", "notional") for side in ("bid", "ask")]
        if sum(key in values for key in optional) not in (0, 4):
            raise ValueError(f"incomplete optional 0.2% band at {ts}")
        record = {"ts": ts, "known_at": ts, **values}
        for band in range(1, 6):
            bid, ask = values[f"depth_bid_{band}pct"], values[f"depth_ask_{band}pct"]
            record[f"depth_imbalance_{band}pct"] = (bid - ask) / (bid + ask) if bid + ask else float("nan")
            bid_n, ask_n = values[f"notional_bid_{band}pct"], values[f"notional_ask_{band}pct"]
            record[f"notional_imbalance_{band}pct"] = (bid_n - ask_n) / (bid_n + ask_n) if bid_n + ask_n else float("nan")
        result.append(record)
    return pd.DataFrame.from_records(result)


def parse_zip(path: Path) -> pd.DataFrame:
    with zipfile.ZipFile(path) as archive:
        names = [name for name in archive.namelist() if name.endswith(".csv")]
        if len(names) != 1:
            raise ValueError(f"expected one bookDepth CSV, got {names}")
        with archive.open(names[0]) as stream:
            import io
            return parse_depth_rows(list(csv.DictReader(io.TextIOWrapper(stream, encoding="utf-8"))))


def fetch_day(symbol: str, day: date) -> tuple[date, Path | None, str]:
    source = url(symbol, day)
    size = remote_size(source)
    if size is None:
        return day, None, "HTTP 404"
    expected_sha = checksum(source)
    if expected_sha is None:
        return day, None, "CHECKSUM 404"
    target = RAW / symbol / f"{symbol}-bookDepth-{day:%Y-%m-%d}.zip"
    digest = stream_archive(source, target, size, expected_sha)
    return day, target if digest else None, f"{size} bytes SHA256 {expected_sha[:12]}"


def write_month(symbol: str, month: str, paths: list[Path]) -> int:
    frames = []
    for path in paths:
        try:
            frames.append(parse_zip(path))
        except Exception as error:
            log_missing(symbol, path.stem[-10:], "parse_day", f"{type(error).__name__}: {error}")
    if not frames:
        raise ValueError("no valid daily bookDepth archives")
    frame = pd.concat(frames, ignore_index=True).sort_values("ts")
    if frame.ts.duplicated().any() or (frame.ts.dt.strftime("%Y-%m") != month).any():
        raise ValueError(f"duplicate or out-of-month bookDepth timestamp in {month}")
    target = OUT / symbol / f"{month}.parquet"
    target.parent.mkdir(parents=True, exist_ok=True)
    scratch = Path("data/tmp/free_downloaders")
    scratch.mkdir(parents=True, exist_ok=True)
    tmp = scratch / f"depth-{symbol}-{month}.parquet.part.{os.getpid()}"
    try:
        table = pa.Table.from_pandas(frame, preserve_index=False)
        metadata = dict(table.schema.metadata or {})
        metadata[b"source_days"] = ",".join(path.name for path in paths).encode()
        pq.write_table(table.replace_schema_metadata(metadata), tmp)
        if pq.read_metadata(tmp).num_rows != len(frame):
            raise ValueError("Parquet row count mismatch")
        os.replace(tmp, target)
    finally:
        tmp.unlink(missing_ok=True)
    return len(frame)


def run(end: date | None = None, btc_start: date = START) -> None:
    end = end or datetime.now(timezone.utc).date() - timedelta(days=1)
    for symbol in SYMBOLS:
        first = btc_start if symbol == "BTCUSDT" else START
        months: dict[str, list[date]] = defaultdict(list)
        for offset in range((end - first).days + 1):
            day = first + timedelta(days=offset)
            months[day.strftime("%Y-%m")].append(day)
        for month, days in sorted(months.items()):
            paths = []
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = {pool.submit(fetch_day, symbol, day): day for day in days}
                for future in as_completed(futures):
                    day = futures[future]
                    try:
                        _, path, message = future.result()
                        if path:
                            paths.append(path)
                            print(f"verified {symbol} {day}: {message}", flush=True)
                        else:
                            log_missing(symbol, day.isoformat(), "fetch_day", message)
                    except OSError as error:
                        if "15 GiB" in str(error):
                            pool.shutdown(cancel_futures=True)
                            raise
                        log_missing(symbol, day.isoformat(), "fetch_day", f"{type(error).__name__}: {error}")
                    except Exception as error:
                        log_missing(symbol, day.isoformat(), "fetch_day", f"{type(error).__name__}: {error}")
            if paths:
                try:
                    print(f"aggregated {symbol} {month}: {write_month(symbol, month, sorted(paths))} snapshots", flush=True)
                except OSError as error:
                    if "15 GiB" in str(error):
                        raise
                    log_missing(symbol, month, "aggregate_month", f"{type(error).__name__}: {error}")
                except Exception as error:
                    log_missing(symbol, month, "aggregate_month", f"{type(error).__name__}: {error}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--end", type=date.fromisoformat)
    parser.add_argument("--btc-start", type=date.fromisoformat, default=START)
    args = parser.parse_args()
    run(args.end, args.btc_start)
