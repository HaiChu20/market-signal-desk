"""Checksum-verified Binance monthly BTCUSDT minute klines."""
from __future__ import annotations

import argparse
import csv
from datetime import date, datetime, timedelta, timezone
import hashlib
import io
import os
from pathlib import Path
import tempfile
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import time
import random
import zipfile

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from msd.data.dukascopy import COLUMNS

ROOT = Path("data/bars/binance_spot")
BASE = "https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/1m"
BTC_SPREAD = {  # USD; Dukascopy BTCUSD median ask-bid, June 12–14 each year
    2018: 130.0, 2019: 115.1, 2020: 112.6, 2021: 91.8, 2022: 81.7,
    2023: 63.6, 2024: 64.7, 2025: 50.0, 2026: 50.0,
}


def _get(url: str, retries: int = 5) -> bytes | None:
    for attempt in range(retries):
        try:
            with urlopen(Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; MarketSignalDesk/0.1)"}), timeout=60) as response:
                return response.read()
        except HTTPError as exc:
            if exc.code == 404:
                return None
            if attempt == retries - 1:
                raise
        except (URLError, TimeoutError, OSError):
            if attempt == retries - 1:
                raise
        time.sleep(min(2 ** (attempt + 1), 60) + random.uniform(0, 1))
    raise AssertionError("unreachable")


def decode_zip(raw: bytes) -> pd.DataFrame:
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        names = [name for name in archive.namelist() if name.endswith(".csv")]
        if len(names) != 1:
            raise ValueError(f"Expected one CSV in ZIP, got {names}")
        with archive.open(names[0]) as stream:
            rows = list(csv.reader(io.TextIOWrapper(stream, encoding="utf-8")))
    if rows and rows[0][0] == "open_time":
        rows = rows[1:]
    if not rows:
        return pd.DataFrame(columns=COLUMNS)
    timestamps = np.array([int(row[0]) for row in rows], dtype=np.int64)
    unit = "us" if timestamps[0] >= 10**15 else "ms"
    ts = pd.to_datetime(timestamps, unit=unit, utc=True)
    prices = np.array([[float(row[i]) for i in (1, 2, 3, 4)] for row in rows], dtype=float)
    volume = np.array([float(row[5]) for row in rows], dtype=float)
    if (prices <= 0).any() or (prices > 10_000_000).any() or (volume < 0).any():
        raise ValueError("Implausible Binance kline values")
    frame = pd.DataFrame({"ts": ts, "volume": volume})
    for prefix in ("bid", "ask"):
        for j, field in enumerate("ohlc"):
            frame[f"{prefix}_{field}"] = prices[:, j]
    return frame[COLUMNS]


def fetch_month(month: date) -> pd.DataFrame | None:
    name = f"BTCUSDT-1m-{month:%Y-%m}.zip"
    url = f"{BASE}/{name}"
    checksum = _get(url + ".CHECKSUM")
    if checksum is None:
        return None
    expected = checksum.decode("ascii").split()[0].lower()
    if len(expected) != 64 or any(c not in "0123456789abcdef" for c in expected):
        raise ValueError(f"Malformed SHA256 checksum for {name}")
    raw = _get(url)
    if raw is None:
        raise ValueError(f"Missing ZIP with checksum: {name}")
    actual = hashlib.sha256(raw).hexdigest()
    if actual != expected:
        raise ValueError(f"SHA256 mismatch for {name}: {actual} != {expected}")
    return decode_zip(raw)


def download(start: date, end: date, root: Path = ROOT) -> None:
    if root == ROOT:
        from .binance_lake import download_klines
        download_klines("spot", ("BTCUSDT",), end=end)
        return
    month = start.replace(day=1)
    today = datetime.now(timezone.utc).date()
    end = min(end, today)
    while month <= end:
        next_month = (month.replace(day=28) + timedelta(days=4)).replace(day=1)
        path = root / "BTCUSDT" / f"{month:%Y-%m}.parquet"
        if path.exists() and pq.read_metadata(path).metadata.get(b"sha256_verified") == b"1":
            print(f"skip {path}", flush=True)
        else:
            print(f"fetch Binance {month:%Y-%m}", flush=True)
            frame = fetch_month(month)
            if frame is None:
                print(f"MISSING Binance {month:%Y-%m}: archive/checksum unavailable", flush=True)
            else:
                if frame.empty:
                    print(f"MISSING Binance {month:%Y-%m}: verified archive has no bars", flush=True)
                    month = next_month
                    continue
                path.parent.mkdir(parents=True, exist_ok=True)
                with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".parquet", delete=False) as tmp:
                    temp = Path(tmp.name)
                table = pa.Table.from_pandas(frame, preserve_index=False)
                metadata = dict(table.schema.metadata or {})
                metadata[b"sha256_verified"] = b"1"
                pq.write_table(table.replace_schema_metadata(metadata), temp)
                os.replace(temp, path)
                rows=pq.read_metadata(path).num_rows
                if rows!=len(frame) or rows==0:
                    raise ValueError(f"Binance output verification failed for {path}")
                print(f"verified {path}: {rows} bars", flush=True)
        month = next_month


def load(symbol: str, start: date | str, end: date | str, root: Path = ROOT, *, raw: bool = False) -> pd.DataFrame:
    if symbol != "BTCUSDT":
        raise ValueError(symbol)
    first, last = pd.Timestamp(start), pd.Timestamp(end)
    first = first.tz_localize("UTC") if first.tzinfo is None else first.tz_convert("UTC")
    last = last.tz_localize("UTC") if last.tzinfo is None else last.tz_convert("UTC")
    paths = sorted((root / symbol).glob("[0-9][0-9][0-9][0-9]-[0-9][0-9].parquet"))
    frames = [pd.read_parquet(path) for path in paths if first.strftime("%Y-%m") <= path.stem <= last.strftime("%Y-%m")]
    if not frames:
        return pd.DataFrame(columns=COLUMNS)
    result = pd.concat(frames, ignore_index=True)
    result = result[(result.ts >= first) & (result.ts < last + pd.Timedelta(days=1))].sort_values("ts").reset_index(drop=True)
    if not raw:
        years = result.ts.dt.year.clip(lower=min(BTC_SPREAD), upper=max(BTC_SPREAD))
        half_spread = years.map(BTC_SPREAD).to_numpy(dtype=float) / 2
        for field in "ohlc":
            price = (result[f"bid_{field}"].to_numpy(dtype=float) + result[f"ask_{field}"].to_numpy(dtype=float)) / 2
            result[f"bid_{field}"] = price - half_spread
            result[f"ask_{field}"] = price + half_spread
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=date.fromisoformat, default=date(2017, 8, 1))
    parser.add_argument("--end", type=date.fromisoformat, default=datetime.now(timezone.utc).date())
    args = parser.parse_args()
    download(args.start, args.end)


if __name__ == "__main__":
    main()
