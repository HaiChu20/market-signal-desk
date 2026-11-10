"""Full-column Binance spot and USD-M kline archives with checksums."""
from __future__ import annotations

import csv
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import random
import shutil
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import zipfile

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

FUTURE = {"BTCUSDT": date(2019, 9, 1), "ETHUSDT": date(2019, 9, 1)}
SPOT = {"BTCUSDT": date(2017, 8, 1), "ETHUSDT": date(2017, 8, 1)}
KLINE_COLUMNS = ["ts", "bid_o", "bid_h", "bid_l", "bid_c", "ask_o", "ask_h", "ask_l", "ask_c", "volume", "quote_volume", "trades", "taker_buy_base", "taker_buy_quote"]
MIN_FREE_BYTES = 15 * 1024**3  # user: keep >=10 GB free; 15 GiB leaves system headroom


def ensure_disk_space() -> None:
    free = shutil.disk_usage(".").free
    if free < MIN_FREE_BYTES:
        raise OSError(f"Stopping data downloads: only {free / 1024**3:.1f} GiB free (15 GiB minimum)")


def parse_kline_rows(rows: list[list[str]]) -> pd.DataFrame:
    if rows and rows[0] and rows[0][0].lower() in {"open_time", "open time"}:
        rows = rows[1:]
    if not rows:
        return pd.DataFrame(columns=KLINE_COLUMNS)
    if any(len(row) < 12 for row in rows):
        raise ValueError("Binance kline row has fewer than 12 columns")
    stamps = np.asarray([int(row[0]) for row in rows], dtype=np.int64)
    ts = pd.to_datetime(stamps, unit="us" if stamps[0] >= 10**15 else "ms", utc=True).astype("datetime64[ns, UTC]")
    prices = np.asarray([[float(row[i]) for i in (1, 2, 3, 4)] for row in rows], dtype=float)
    volume = np.asarray([float(row[5]) for row in rows], dtype=float)
    quote = np.asarray([float(row[7]) for row in rows], dtype=float)
    trades = np.asarray([int(row[8]) for row in rows], dtype=np.int64)
    taker_base = np.asarray([float(row[9]) for row in rows], dtype=float)
    taker_quote = np.asarray([float(row[10]) for row in rows], dtype=float)
    if not np.isfinite(prices).all() or (prices <= 0).any() or (volume < 0).any():
        raise ValueError("Implausible Binance kline values")
    data = {"ts": ts, "volume": volume, "quote_volume": quote, "trades": trades, "taker_buy_base": taker_base, "taker_buy_quote": taker_quote}
    for j, field in enumerate("ohlc"):
        data[f"bid_{field}"] = prices[:, j]
        data[f"ask_{field}"] = prices[:, j]
    return pd.DataFrame(data)[KLINE_COLUMNS]


def decode_kline_zip(raw: bytes) -> pd.DataFrame:
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        names = [name for name in archive.namelist() if name.lower().endswith(".csv")]
        if len(names) != 1:
            raise ValueError(f"Expected one kline CSV, got {names}")
        with archive.open(names[0]) as stream:
            rows = list(csv.reader(io.TextIOWrapper(stream, encoding="utf-8")))
    return parse_kline_rows(rows)


def parse_funding_csv(raw: bytes, symbol: str = "") -> pd.DataFrame:
    rows = list(csv.reader(io.StringIO(raw.decode("utf-8-sig"))))
    header = [cell.strip().lower() for cell in rows[0]] if rows else []
    if header and header[0] in {"symbol", "calc_time", "calc time"}:
        rows = rows[1:]
    result = []
    for row in rows:
        if not row:
            continue
        # Funding archives use calc_time,funding_interval_hours,last_funding_rate.
        # Accept the older symbol,fundingTime,fundingRate,markPrice layout too.
        if header and header[0] in {"calc_time", "calc time"} or len(row) == 3:
            result.append((symbol, pd.to_datetime(int(row[0]), unit="ms", utc=True),
                           float(row[2]), float(row[1]), np.nan))
        else:
            result.append((row[0], pd.to_datetime(int(row[1]), unit="ms", utc=True),
                           float(row[2]), np.nan, float(row[3]) if len(row) > 3 else np.nan))
    return pd.DataFrame(result, columns=["symbol", "ts", "funding_rate", "funding_interval_hours", "mark_price"])


def parse_metrics_csv(raw: bytes) -> pd.DataFrame:
    return pd.read_csv(io.BytesIO(raw))


def _get(url: str, retries: int = 5) -> bytes | None:
    for attempt in range(retries):
        try:
            with urlopen(Request(url, headers={"User-Agent": "MarketSignalDesk data archive downloader"}), timeout=90) as response:
                return response.read()
        except HTTPError as exc:
            if exc.code == 404:
                return None
            if attempt + 1 == retries:
                raise
        except (URLError, TimeoutError, OSError):
            if attempt + 1 == retries:
                raise
        time.sleep(min(2 ** (attempt + 1), 30) + random.random())
    raise AssertionError("unreachable")


def _atomic_bytes(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
        handle.write(raw)
        temp = Path(handle.name)
    os.replace(temp, path)


def fetch_kline_month(market: str, symbol: str, month: date) -> tuple[pd.DataFrame | None, bytes | None, str | None]:
    name = f"{symbol}-1m-{month:%Y-%m}.zip"
    base = f"https://data.binance.vision/data/futures/um/monthly/klines/{symbol}/1m" if market == "um" else f"https://data.binance.vision/data/spot/monthly/klines/{symbol}/1m"
    checksum = _get(f"{base}/{name}.CHECKSUM")
    if checksum is None:
        return None, None, None
    expected = checksum.decode("ascii").split()[0].lower()
    raw = _get(f"{base}/{name}")
    if raw is None:
        raise ValueError(f"Missing archive although checksum exists: {name}")
    actual = hashlib.sha256(raw).hexdigest()
    if actual != expected:
        raise ValueError(f"SHA256 mismatch for {name}")
    return decode_kline_zip(raw), raw, actual


def _manifest(root: Path, source: str, symbol: str, frame: pd.DataFrame) -> None:
    path = root / symbol / "manifest.json"
    prior = json.loads(path.read_text()) if path.exists() else {}
    months = dict(prior.get("months", {}))
    months[str(frame.ts.dt.strftime("%Y-%m").iloc[0])] = {"first_ts": str(frame.ts.min()), "last_ts": str(frame.ts.max()), "bars": int(len(frame))}
    first = min(pd.Timestamp(value["first_ts"]) for value in months.values())
    last = max(pd.Timestamp(value["last_ts"]) for value in months.values())
    count = sum(int(value["bars"]) for value in months.values())
    payload = {"source": source, "symbol": symbol, "first_ts": str(first) if count else None,
               "last_ts": str(last) if count else None, "bars": int(count),
               "columns": KLINE_COLUMNS, "price_type": "trade", "volume_type": "real", "months": months}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")


def _verified_output_rows(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        return int(pq.read_metadata(path).num_rows)
    except (OSError, pa.ArrowException):
        return 0


def download_klines(market: str, symbols: tuple[str, ...] = ("BTCUSDT", "ETHUSDT"), end: date | None = None) -> None:
    end = end or datetime.now(timezone.utc).date()
    jobs = []
    for symbol in symbols:
        start = (SPOT if market == "spot" else FUTURE)[symbol]
        month = start.replace(day=1)
        while month <= end:
            jobs.append((symbol, month))
            month = (month.replace(day=28) + timedelta(days=4)).replace(day=1)
    verified_months = {symbol: 0 for symbol in symbols}
    missing_months = {symbol: 0 for symbol in symbols}
    for symbol, month in jobs:
        ensure_disk_space()
        root = Path("data/bars/binance_spot" if market == "spot" else "data/bars/binance_um")
        out = root / symbol / f"{month:%Y-%m}.parquet"
        raw_path = Path("data/raw/binance") / market / "klines" / symbol / f"{month:%Y-%m}.zip"
        checksum_path = raw_path.with_suffix(".CHECKSUM")
        if raw_path.exists() and checksum_path.exists():
            expected = checksum_path.read_text().split()[0].lower()
            raw = raw_path.read_bytes()
            digest = hashlib.sha256(raw).hexdigest()
            if digest != expected:
                raise ValueError(f"Retained raw archive checksum mismatch: {raw_path}")
            frame = decode_kline_zip(raw)
        else:
            frame, raw, digest = fetch_kline_month("um" if market == "um" else "spot", symbol, month)
            if frame is None:
                missing_months[symbol] += 1
                print(f"MISSING {market} {symbol} {month:%Y-%m}: archive/checksum unavailable", flush=True)
                continue
            _atomic_bytes(checksum_path, f"{digest}  {raw_path.name}\n".encode())
            _atomic_bytes(raw_path, raw)
        if out.exists():
            metadata = pq.read_metadata(out).metadata or {}
            if metadata.get(b"sha256", b"").decode() == digest and _verified_output_rows(out) > 0:
                verified_months[symbol] += 1
                continue
        if frame.empty:
            missing_months[symbol] += 1
            print(f"MISSING {market} {symbol} {month:%Y-%m}: verified archive has no rows", flush=True)
            continue
        out.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=out.parent, suffix=".parquet", delete=False) as handle:
            temp = Path(handle.name)
        table = pa.Table.from_pandas(frame, preserve_index=False)
        md = dict(table.schema.metadata or {}); md[b"sha256"] = digest.encode(); md[b"sha256_verified"] = b"1"
        pq.write_table(table.replace_schema_metadata(md), temp); os.replace(temp, out)
        written_rows = _verified_output_rows(out)
        if written_rows != len(frame) or written_rows == 0:
            raise ValueError(f"Parquet output verification failed: {out} rows={written_rows}")
        _manifest(root, f"binance_{market}", symbol, frame)
        verified_months[symbol] += 1
        print(f"verified {market} {symbol} {month:%Y-%m}: {written_rows} bars", flush=True)
    for symbol in symbols:
        if verified_months[symbol] == 0:
            raise RuntimeError(f"{market} download produced no non-empty verified months for {symbol} ({missing_months[symbol]} missing)")
        print(f"DONE {market} {symbol}: verified_months={verified_months[symbol]} missing_months={missing_months[symbol]}", flush=True)


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--market", required=True, choices=("spot", "um"))
    parser.add_argument("--symbol", choices=("BTCUSDT", "ETHUSDT"))
    args = parser.parse_args()
    download_klines(args.market, (args.symbol,) if args.symbol else ("BTCUSDT", "ETHUSDT"))


if __name__ == "__main__":
    main()

