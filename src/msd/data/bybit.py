"""Verified Bybit public trades and causal minute taker-flow bars."""
from __future__ import annotations

import argparse
import csv
import gzip
import os
import re
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.request import Request, urlopen

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from msd.data.archive_download import HEADERS, remote_size, stream_archive

MAIN = Path("/Users/bfhach/Projects/market-signal-desk")
RAW = MAIN / "data/raw/bybit"
OUT = MAIN / "data/bars/bybit_flow"
MISSING = Path("data/logs/missing_bybit.csv")
BASE = "https://public.bybit.com/trading"
SYMBOLS = ("BTCUSDT", "ETHUSDT")
START = date(2020, 3, 25)


def url(symbol: str, day: date) -> str:
    return f"{BASE}/{symbol}/{symbol}{day:%Y-%m-%d}.csv.gz"


def listed_days(symbol: str) -> set[date]:
    with urlopen(Request(f"{BASE}/{symbol}/", headers=HEADERS), timeout=60) as response:
        listing = response.read().decode("utf-8")
    return {date.fromisoformat(value) for value in re.findall(rf'{symbol}(\d{{4}}-\d{{2}}-\d{{2}})\.csv\.gz', listing)}


def parse_trade(row: dict[str, str]) -> tuple[pd.Timestamp, bool, float, float]:
    if not {"timestamp", "side", "size", "price"} <= row.keys():
        raise ValueError("Bybit trade schema missing required columns")
    stamp = pd.to_datetime(float(row["timestamp"]), unit="s", utc=True)
    side = row["side"].lower()
    if side not in {"buy", "sell"}:
        raise ValueError(f"invalid taker side: {side}")
    size, price = float(row["size"]), float(row["price"])
    if not 0 < size < float("inf") or not 0 < price < float("inf"):
        raise ValueError("invalid size or price")
    return stamp, side == "buy", size, price


def aggregate_files(paths: list[Path], month: str) -> pd.DataFrame:
    acc: dict[pd.Timestamp, list[float]] = defaultdict(lambda: [0.0] * 8)
    for path in paths:
        with gzip.open(path, "rt", newline="") as handle:
            rows = csv.DictReader(handle)
            if not rows.fieldnames or not {"timestamp", "side", "size", "price"} <= set(rows.fieldnames):
                raise ValueError(f"Bybit schema mismatch: {path}")
            for row in rows:
                stamp, buy, size, price = parse_trade(row)
                minute = stamp.floor("min")
                if minute.strftime("%Y-%m") != month:
                    raise ValueError(f"trade outside archive month: {path}")
                values = acc[minute]
                side = 0 if buy else 1
                values[side] += size
                values[side + 2] += 1
                values[side + 4] += size * price
                values[6] = max(values[6], size)
                values[7] += 1
    records = []
    for ts, v in sorted(acc.items()):
        records.append({"ts": ts, "known_at": ts + pd.Timedelta(minutes=1),
                        "buy_taker_volume": v[0], "sell_taker_volume": v[1],
                        "delta": v[0] - v[1], "buy_trade_count": int(v[2]),
                        "sell_trade_count": int(v[3]),
                        "vwap_buy": v[4] / v[0] if v[0] else float("nan"),
                        "vwap_sell": v[5] / v[1] if v[1] else float("nan"),
                        "max_trade": v[6], "trade_count": int(v[7])})
    return pd.DataFrame.from_records(records)


def write_month(symbol: str, month: str, paths: list[Path]) -> int:
    frame = aggregate_files(paths, month)
    if frame.empty:
        return 0
    target = OUT / symbol / f"{month}.parquet"
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


def fetch_day(symbol: str, day: date) -> tuple[date, Path | None, str]:
    target = RAW / symbol / f"{symbol}{day:%Y-%m-%d}.csv.gz"
    expected = remote_size(url(symbol, day))
    if expected is None:
        return day, None, "HTTP 404"
    digest = stream_archive(url(symbol, day), target, expected)
    return day, target if digest else None, f"{expected} bytes"


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
            with ThreadPoolExecutor(max_workers=2) as pool:
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
                        if "65 GiB" in str(error):
                            pool.shutdown(cancel_futures=True)
                            raise
                        log_missing(symbol, day, str(error))
                    except Exception as error:
                        log_missing(symbol, day, str(error))
            if paths:
                rows = write_month(symbol, month, sorted(paths))
                print(f"aggregated {symbol} {month}: {rows} minutes", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--end", type=date.fromisoformat)
    args = parser.parse_args()
    run(args.end)
