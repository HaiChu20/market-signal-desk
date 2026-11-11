"""Inventory exact DEV source/derived input files without reading their contents."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

SOURCES = {"USATECHIDXUSD": "dukascopy", "USA500IDXUSD": "dukascopy",
           "XAUUSD": "dukascopy", "BTCUSDT": "binance_spot", "ETHUSDT": "binance_spot"}


def make_bundle(data_root: Path, config_path: Path, output: Path, symbols=None):
    config = json.loads(config_path.read_text())
    if config["period"] != "dev" or pd.Timestamp(config["end_exclusive"]) > pd.Timestamp("2023-01-01"):
        raise ValueError("DEV-only bundle")
    entries, missing = [], []
    end = pd.Timestamp(config["end_exclusive"])
    chosen = config["symbols"] if symbols is None else symbols
    if not set(chosen) <= set(config["symbols"]):
        raise ValueError("Requested symbols must be in the config")
    for symbol in chosen:
        start = pd.Timestamp(config["starts"][symbol])
        warm = max(start - pd.Timedelta(days=12), pd.Timestamp("2008-01-01") if symbol == "XAUUSD" else
                   pd.Timestamp("2018-12-16") if symbol in {"USATECHIDXUSD", "USA500IDXUSD"} else
                   pd.Timestamp("2017-01-01"))
        months = pd.period_range(warm.to_period("M"), (end - pd.Timedelta(nanoseconds=1)).to_period("M"), freq="M")
        label_months = set(pd.period_range(start.to_period("M"), (end - pd.Timedelta(nanoseconds=1)).to_period("M"), freq="M"))
        for month in months:
            stem = f"{month}.parquet"
            paths = [Path("bars") / SOURCES[symbol] / symbol / stem,
                     *(Path("derived") / f"bars_{tf}" / symbol / stem for tf in ("15m", "1h", "4h")),
                     Path("features") / symbol / stem]
            if month in label_months:
                paths.append(Path("labels") / symbol / stem)
            for relative in paths:
                path = data_root / relative
                if path.exists():
                    entries.append((relative.as_posix(), path.stat().st_size))
                else:
                    missing.append(relative.as_posix())
        if symbol == "ETHUSDT":
            # Stage 9's executable ETH spread is calibrated from June 12-14
            # Dukascopy ETHUSD quotes; its loader scans this entire range.
            reference_months = pd.period_range("2018-06", (end - pd.Timedelta(nanoseconds=1)).to_period("M"), freq="M")
            for month in reference_months:
                relative = Path("bars/dukascopy/ETHUSD") / f"{month}.parquet"
                path = data_root / relative
                if path.exists():
                    entries.append((relative.as_posix(), path.stat().st_size))
                else:
                    missing.append(relative.as_posix())
    entries = sorted(set(entries))
    output.mkdir(parents=True, exist_ok=True)
    (output / "files.txt").write_text("\n".join(path for path, _ in entries) + "\n")
    (output / "manifest.tsv").write_text("path\tbytes\n" + "\n".join(f"{path}\t{size}" for path, size in entries) + "\n")
    (output / "missing.txt").write_text("\n".join(sorted(set(missing))) + ("\n" if missing else ""))
    total = sum(size for _, size in entries)
    print(f"{len(entries)} files, {total} bytes ({total / 1024**3:.2f} GiB); {len(missing)} missing")
    print(f"rsync file list: {output / 'files.txt'}")
    return total, missing


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--config", type=Path, default=Path("hpc/roihu/sequence/configs/dev_v1.json"))
    parser.add_argument("--output", type=Path, default=Path("hpc/roihu/sequence/bundle"))
    parser.add_argument("--symbols", help="comma-separated subset; default is all five")
    args = parser.parse_args()
    make_bundle(args.data_root, args.config, args.output,
                args.symbols.split(",") if args.symbols else None)


if __name__ == "__main__":
    main()
