"""Fetch the local bar window required by the daily S1/S2/S3 swing replay."""
from __future__ import annotations

import argparse
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from msd.live import swing_shadow
from msd.live.binance import BinanceSpotFeed


def _next_month(day: date) -> date:
    return (day.replace(day=28) + timedelta(days=4)).replace(day=1)


def _bootstrap_binance(data_root: Path, start: date, end: date) -> None:
    directory = data_root / "bars/binance_spot/BTCUSDT"
    month = start.replace(day=1)
    final_exclusive = pd.Timestamp(end + timedelta(days=1), tz="UTC")
    feed = BinanceSpotFeed("BTCUSDT")
    while month <= end:
        month_next = _next_month(month)
        chunk_start = max(pd.Timestamp(month, tz="UTC"),
                          pd.Timestamp(start, tz="UTC"))
        chunk_end = min(pd.Timestamp(month_next, tz="UTC"), final_exclusive)
        path = directory / f"{month:%Y-%m}.parquet"
        latest = (pd.to_datetime(pd.read_parquet(path, columns=["ts"]).ts, utc=True).max()
                  if path.exists() else None)
        last_expected = chunk_end - pd.Timedelta(minutes=1)
        if latest is not None and latest >= last_expected:
            print(f"Skip BTCUSDT {month:%Y-%m}: local month is complete", flush=True)
        else:
            after = latest if latest is not None else chunk_start - pd.Timedelta(minutes=1)
            print(f"Fetching BTCUSDT {chunk_start} through {chunk_end} (exclusive)", flush=True)
            rows = feed.backfill(after, now=chunk_end)
            swing_shadow._write_binance_backfill(data_root, rows)
            print(f"Saved BTCUSDT {month:%Y-%m}: {len(rows)} bars", flush=True)
        month = month_next


def bootstrap(data_root: Path = Path("data"), *, now: pd.Timestamp | None = None) -> None:
    stamp = pd.Timestamp.now(tz="UTC") if now is None else pd.Timestamp(now)
    stamp = stamp.tz_localize("UTC") if stamp.tzinfo is None else stamp.tz_convert("UTC")
    start = (stamp - pd.Timedelta(days=swing_shadow.DATA_WINDOW_DAYS)).date()
    end = (stamp - pd.Timedelta(days=1)).date()
    for market in swing_shadow.MARKETS:
        print(f"Bootstrapping {market}: {start} through {end}", flush=True)
        if market == "BTCUSDT":
            _bootstrap_binance(data_root, start, end)
        else:
            swing_shadow.refresh_market(
                data_root, market, stamp, lookback_days=swing_shadow.DATA_WINDOW_DAYS
            )
        print(f"Finished {market}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    args = parser.parse_args()
    bootstrap(args.data_root)


if __name__ == "__main__":
    main()
