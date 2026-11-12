"""Inventory exact DEV source/derived input files without reading their contents."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq
from msd.research.sequence_coverage import anchor_coverage

SOURCES = {"USATECHIDXUSD": "dukascopy", "USA500IDXUSD": "dukascopy",
           "XAUUSD": "dukascopy", "BTCUSDT": "binance_spot", "ETHUSDT": "binance_spot"}


def _flow_coverage(paths: list[Path], columns: list[str]) -> dict[str, float]:
    total = 0
    present = {column: 0 for column in columns}
    for path in paths:
        parquet = pq.ParquetFile(path)
        total += parquet.metadata.num_rows
        names = parquet.schema.names
        for column in columns:
            if column not in names:
                continue
            index = names.index(column)
            for group in range(parquet.metadata.num_row_groups):
                metadata = parquet.metadata.row_group(group)
                statistics = metadata.column(index).statistics
                if statistics is None or statistics.null_count is None:
                    frame = pd.read_parquet(path, columns=[column])
                    present[column] += int(frame[column].notna().sum())
                    break
                present[column] += metadata.num_rows - statistics.null_count
    return {column: (count / total if total else 0.) for column, count in present.items()}


def make_bundle(data_root: Path, config_path: Path, output: Path, symbols=None):
    config = json.loads(config_path.read_text())
    if config["period"] != "dev" or pd.Timestamp(config["end_exclusive"]) > pd.Timestamp("2023-01-01"):
        raise ValueError("DEV-only bundle")
    entries, missing, stale, coverage = [], [], [], []
    end = pd.Timestamp(config["end_exclusive"])
    chosen = config["symbols"] if symbols is None else symbols
    if not set(chosen) <= set(config["symbols"]):
        raise ValueError("Requested symbols must be in the config")
    for symbol in chosen:
        override = config.get("venue_overrides", {}).get(symbol, {})
        done = data_root / "tmp" / f"stage9p4_{symbol}_year_chain_done.json"
        if not done.exists():
            raise RuntimeError(f"Missing production4 completion marker: {done}")
        complete = json.loads(done.read_text())
        if complete.get("symbol") != symbol or complete.get("end_year", 0) < 2022:
            raise RuntimeError(f"Incomplete production4 marker: {done}")
        start = pd.Timestamp(config["starts"][symbol])
        warm = max(start - pd.Timedelta(days=12), pd.Timestamp("2008-01-01") if symbol == "XAUUSD" else
                   pd.Timestamp("2018-12-16") if symbol in {"USATECHIDXUSD", "USA500IDXUSD"} else
                   pd.Timestamp("2017-01-01"))
        months = pd.period_range(warm.to_period("M"), (end - pd.Timedelta(nanoseconds=1)).to_period("M"), freq="M")
        label_months = set(pd.period_range(start.to_period("M"), (end - pd.Timedelta(nanoseconds=1)).to_period("M"), freq="M"))
        flow_columns = config.get("flow_features", {}).get(symbol, [])
        flow_paths = []
        for month in months:
            stem = f"{month}.parquet"
            paths = [Path(override.get("bars_1m", Path("bars") / SOURCES[symbol] / symbol)) / stem,
                     *(Path("derived") / f"bars_{tf}" / symbol / stem for tf in ("15m", "1h", "4h")),
                     Path("features") / symbol / stem]
            if month in label_months:
                paths.append(Path(override.get("labels", Path("labels") / symbol)) / stem)
                if override.get("features_overlay"):
                    paths.append(Path(override["features_overlay"]) / stem)
            if flow_columns:
                paths.append(Path("features_flow") / symbol / stem)
            for relative in paths:
                path = data_root / relative
                if path.exists():
                    entries.append((relative.as_posix(), path.stat().st_size))
                    if relative.parts[0] == "features_flow":
                        flow_paths.append(path)
                        if path.stat().st_mtime_ns < done.stat().st_mtime_ns:
                            stale.append(f"{relative}: predates production4 completion")
                    if relative.parts[0] in {"derived", "features", "labels"} and month.year >= start.year:
                        year_marker = data_root / "tmp" / f"stage9p4_{symbol}_{month.year}.json"
                        if not year_marker.exists():
                            stale.append(f"{relative}: missing year marker")
                        else:
                            run = json.loads(year_marker.read_text())
                            # The year result marker is written *after* bars and
                            # labels, so compare with its inferred run start.
                            run_start_ns = year_marker.stat().st_mtime_ns - int((float(run["runtime_seconds"]) + 60) * 1e9)
                            if path.stat().st_mtime_ns < run_start_ns:
                                stale.append(relative.as_posix())
                else:
                    missing.append(relative.as_posix())
                    if month >= start.to_period("M"):
                        stale.append(f"{relative}: missing DEV input")
        if flow_columns:
            dev_flow_paths = [path for path in flow_paths if start.year <= int(path.stem[:4]) < end.year]
            minimum = float(config["flow_min_non_nan_coverage"])
            for column, value in _flow_coverage(dev_flow_paths, flow_columns).items():
                if value < minimum:
                    stale.append(f"{symbol}/{column}: flow coverage {value:.1%}")
        for year in range(start.year, end.year):
            result = anchor_coverage(data_root, symbol, year)
            coverage.append(result)
            if result["anchors"] == 0 or result["coverage"] < .8:
                stale.append(f"{symbol}/{year}: anchor coverage {result['coverage']:.1%}")
        if symbol == "ETHUSDT" and override.get("venue") != "binance_perp":
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
                    stale.append(f"{relative}: missing ETH spread reference")
    entries = sorted(set(entries))
    output.mkdir(parents=True, exist_ok=True)
    (output / "files.txt").write_text("\n".join(path for path, _ in entries) + "\n")
    (output / "manifest.tsv").write_text("path\tbytes\n" + "\n".join(f"{path}\t{size}" for path, size in entries) + "\n")
    (output / "missing.txt").write_text("\n".join(sorted(set(missing))) + ("\n" if missing else ""))
    (output / "coverage.json").write_text(json.dumps(coverage, indent=2) + "\n")
    (output / "stale.txt").write_text("\n".join(stale) + ("\n" if stale else ""))
    total = sum(size for _, size in entries)
    print(f"{len(entries)} files, {total} bytes ({total / 1024**3:.2f} GiB); {len(missing)} missing")
    minimum_coverage = min((row["coverage"] for row in coverage), default=float("nan"))
    print(f"coverage years: {len(coverage)}, minimum: {minimum_coverage:.1%}; stale/failed: {len(stale)}")
    print(f"rsync file list: {output / 'files.txt'}")
    if stale:
        raise RuntimeError(f"Refusing stale or low-coverage inputs; inspect {output / 'stale.txt'}")
    return total, missing


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--config", type=Path, default=Path("hpc/roihu/sequence/configs/dev_v3.json"))
    parser.add_argument("--output", type=Path, default=Path("hpc/roihu/sequence/bundle"))
    parser.add_argument("--symbols", help="comma-separated subset; default is all five")
    args = parser.parse_args()
    make_bundle(args.data_root, args.config, args.output,
                args.symbols.split(",") if args.symbols else None)


if __name__ == "__main__":
    main()
