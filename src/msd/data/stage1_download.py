"""Download full-day Dukascopy index bars; reports are separate commands."""
from __future__ import annotations
import argparse
from datetime import date, datetime, timezone
import time
from msd.data.dukascopy import download, load

SYMBOLS = ("USATECHIDXUSD", "USA500IDXUSD")


def _download(symbol: str, start: date, end: date, workers: int) -> None:
    delay = 10
    while True:
        try:
            download(symbol, start, end, workers=workers)
            verified=load(symbol,start,end)
            if verified.empty:
                raise RuntimeError(f"Dukascopy produced no non-empty verified output for {symbol} {start}..{end}")
            return
        except OSError as exc:
            print(f"retry {symbol} after {delay}s: {exc}", flush=True)
            time.sleep(delay)
            delay = min(delay * 2, 300)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--start", default="2018-01-01")
    args = parser.parse_args()
    start, today = date.fromisoformat(args.start), datetime.now(timezone.utc).date()
    for symbol in SYMBOLS:
        print(f"DOWNLOAD {symbol} {start}..{today}", flush=True)
        _download(symbol, start, today, min(8, max(1, args.workers)))
    print("DOWNLOAD COMPLETE", flush=True)


if __name__ == "__main__":
    main()
