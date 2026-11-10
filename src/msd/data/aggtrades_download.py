"""Stream Binance monthly aggTrades archives to disk with SHA256 verification.

Raw zips are kept immutable under data/raw/binance/aggTrades/{spot,um}/{SYMBOL}/.
Month list and expected sizes come from the HEAD inventory in
data/tmp/aggtrades_head_sizes.json. A month is complete when its zip and
`.sha256` sidecar exist; failures are logged and retried on the next run.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import shutil
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path("data/raw/binance/aggTrades")
INVENTORY = Path("data/tmp/aggtrades_head_sizes.json")
MISSING = Path("data/logs/missing_aggtrades.csv")
MIN_FREE_BYTES = 65 * 1024**3
BASE = {"spot": "https://data.binance.vision/data/spot/monthly/aggTrades",
        "um": "https://data.binance.vision/data/futures/um/monthly/aggTrades"}
CHUNK = 8 * 1024**2
UA = {"User-Agent": "MarketSignalDesk/0.1"}


def _url(market: str, symbol: str, month: str) -> str:
    return f"{BASE[market]}/{symbol}/{symbol}-aggTrades-{month}.zip"


def _read(url: str, timeout: int = 120) -> bytes:
    with urlopen(Request(url, headers=UA), timeout=timeout) as response:
        return response.read()


def download_one(market: str, symbol: str, month: str, expected_bytes: int, retries: int = 6) -> str:
    target = ROOT / market / symbol / f"{symbol}-aggTrades-{month}.zip"
    sidecar = target.with_suffix(".zip.sha256")
    if target.exists() and sidecar.exists():
        return f"skip {market} {symbol} {month}"
    target.parent.mkdir(parents=True, exist_ok=True)
    url = _url(market, symbol, month)
    for attempt in range(retries):
        tmp = target.with_suffix(f".zip.part{os.getpid()}")
        try:
            if shutil.disk_usage(".").free - expected_bytes < MIN_FREE_BYTES:
                raise OSError("free disk would drop below 65 GiB")
            expected_sha = _read(url + ".CHECKSUM", 60).decode("ascii").split()[0].lower()
            digest, size = hashlib.sha256(), 0
            with urlopen(Request(url, headers=UA), timeout=120) as response, tmp.open("wb") as out:
                while chunk := response.read(CHUNK):
                    digest.update(chunk)
                    out.write(chunk)
                    size += len(chunk)
            if digest.hexdigest() != expected_sha:
                raise ValueError(f"SHA256 mismatch ({digest.hexdigest()[:12]} != {expected_sha[:12]})")
            if expected_bytes and size != expected_bytes:
                raise ValueError(f"size {size} != expected {expected_bytes}")
            os.replace(tmp, target)
            sidecar.write_text(f"{expected_sha}  {target.name}\n")
            return f"verified {market} {symbol} {month}: {size / 1024**3:.2f} GiB"
        except Exception as error:  # transport, truncated read, checksum or size mismatch
            if isinstance(error, OSError) and "free disk" in str(error):
                raise
            last = error
        finally:
            if tmp.exists():
                tmp.unlink()
        time.sleep(min(600, 30 * 2**attempt) + random.uniform(0, 5))
    raise RuntimeError(f"FAILED {market} {symbol} {month}: {type(last).__name__}: {last}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--market", choices=("spot", "um", "all"), default="all")
    args = parser.parse_args()
    jobs = [r for r in json.loads(INVENTORY.read_text()) if r.get("status") == 200
            and (args.market == "all" or r["market"] == args.market)]
    jobs.sort(key=lambda r: (r["month"], r["market"], r["symbol"]), reverse=True)  # newest first
    total = sum(r["bytes"] for r in jobs)
    print(f"START aggTrades: {len(jobs)} archives, {total / 1024**3:.1f} GiB expected", flush=True)
    failures = []
    with ThreadPoolExecutor(max_workers=max(1, min(args.workers, 2))) as pool:
        futures = {pool.submit(download_one, r["market"], r["symbol"], r["month"], r["bytes"]): r for r in jobs}
        for future in as_completed(futures):
            r = futures[future]
            try:
                print(future.result(), flush=True)
            except OSError as error:
                print(f"STOP disk guard: {error}", flush=True)
                pool.shutdown(cancel_futures=True)
                raise
            except Exception as error:  # keep going; report at the end
                failures.append(f"{r['market']} {r['symbol']} {r['month']}")
                print(error, flush=True)
                with MISSING.open("a") as log:
                    log.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')},{r['market']},{r['symbol']},{r['month']},{str(error).replace(',', ';')}\n")
    print(f"DONE aggTrades: {len(jobs) - len(failures)} ok, {len(failures)} failed {failures}", flush=True)


if __name__ == "__main__":
    main()
