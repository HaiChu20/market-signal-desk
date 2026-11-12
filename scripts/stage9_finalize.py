#!/usr/bin/env python3
"""Summarize the completed Stage 9 production batch from local artifacts."""
from __future__ import annotations

import ast
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from msd.processing.pipeline import _feature_label_bars, _history_start, write_pipeline_report
from msd.processing.timeframes import BAR_COLUMNS, TIMEFRAMES, build_timeframe

SYMBOLS = ("USA30IDXUSD", "DEUIDXEUR", "XAGUSD", "EURUSD", "USDJPY",
           "GBPUSD", "LIGHTCMDUSD", "BRENTCMDUSD")
LOGS = Path("data/tmp/fe242257/stage9_logs")


def parse_log(symbol: str) -> tuple[dict, float, float, list[dict]]:
    lines = (LOGS / f"{symbol}.log").read_text().splitlines()
    results, audits = [], []
    for line in lines:
        if line.startswith("{'symbol':"):
            try:
                row = ast.literal_eval(line)
            except (ValueError, SyntaxError):
                continue
            if "runtime_seconds" in row:
                results.append(row)
            if row.get("phase") == "oil_quote_audit":
                audits.append(row)
    real = float(re.findall(r"^\s*([0-9.]+) real", "\n".join(lines), re.M)[-1])
    rss = int(re.findall(r"^\s*([0-9]+)  maximum resident set size", "\n".join(lines), re.M)[-1]) / 1024**3
    return results[-1], real, rss, audits


def output_size(symbol: str) -> int:
    paths = [Path("data/features") / symbol, Path("data/labels") / symbol,
             Path("data/events") / symbol, Path("data/levels/touches") / symbol,
             Path("data/state/pipeline") / symbol]
    paths += [path / symbol for path in Path("data/derived").glob("bars_*")]
    single = Path("data/levels") / f"{symbol}.parquet"
    total = single.stat().st_size if single.exists() else 0
    for root in paths:
        if root.exists():
            total += sum(path.stat().st_size for path in root.rglob("*") if path.is_file())
    return total


def executable_source_rows(symbol: str) -> int:
    total = 0
    start, end = _history_start(symbol), pd.Timestamp("2027-01-01", tz="UTC")
    for path in sorted((Path("data/bars/dukascopy") / symbol).glob("*.parquet")):
        schema = pq.ParquetFile(path).schema_arrow.names
        columns = ["ts", *[name for name in ("bad_tick", "stale_expired") if name in schema]]
        if symbol in {"LIGHTCMDUSD", "BRENTCMDUSD"}:
            columns += [f"{side}_{field}" for side in ("bid", "ask") for field in "ohlc"]
        frame = pd.read_parquet(path, columns=columns)
        frame.ts = pd.to_datetime(frame.ts, utc=True)
        frame = frame[(frame.ts >= start) & (frame.ts < end)]
        frame = _feature_label_bars(frame)
        if symbol in {"LIGHTCMDUSD", "BRENTCMDUSD"} and len(frame):
            bid = frame[[f"bid_{field}" for field in "ohlc"]].to_numpy(float)
            ask = frame[[f"ask_{field}" for field in "ohlc"]].to_numpy(float)
            valid = np.isfinite(bid).all(1) & np.isfinite(ask).all(1) & (ask > bid).all(1)
            frame = frame.loc[valid]
        total += len(frame)
    return total


def feature_stats(symbol: str) -> tuple[int, pd.Timestamp, pd.Timestamp]:
    files = sorted((Path("data/features") / symbol).glob("*.parquet"))
    rows = sum(pq.ParquetFile(path).metadata.num_rows for path in files)
    first = pd.read_parquet(files[0], columns=["ts"]).ts.min()
    last = pd.read_parquet(files[-1], columns=["ts"]).ts.max()
    return rows, first, last


def truncation_check(symbol: str) -> str:
    path = Path("data/bars/dukascopy") / symbol / "2024-09.parquet"
    frame = pd.read_parquet(path, columns=BAR_COLUMNS).sort_values("ts").reset_index(drop=True)
    frame.ts = pd.to_datetime(frame.ts, utc=True)
    cut = frame.ts.iloc[len(frame) // 2].floor("h")
    truncated = frame[frame.ts < cut]
    for timeframe in TIMEFRAMES:
        full = build_timeframe(frame, symbol, timeframe)
        short = build_timeframe(truncated, symbol, timeframe)
        expected = full[pd.to_datetime(full.known_at, utc=True) <= cut].reset_index(drop=True)
        pd.testing.assert_frame_equal(short.reset_index(drop=True), expected, check_exact=True)
    return f"PASS (all {len(TIMEFRAMES)} HTFs unchanged through {cut.isoformat()})"


def main() -> None:
    results, rows, oil_audits = [], [], []
    for symbol in SYMBOLS:
        result, real, rss, audits = parse_log(symbol)
        result["peak_rss_gib"] = rss
        results.append(result)
        features, first, last = feature_stats(symbol)
        source = executable_source_rows(symbol)
        rows.append((symbol, real, rss, output_size(symbol), features, source,
                     100 * features / source if source else float("nan"), first, last,
                     truncation_check(symbol)))
        oil_audits.extend(audits)
    write_pipeline_report(results)

    lines = ["# Stage 9 production audit", "",
             "All builds used the preregistered financing addendum, nice priority, atomic verified monthly writes, and the 15 GiB free-space guard.", "",
             "| Market | Wall time | Peak RSS | Output size | Feature/source coverage | Feature range | Truncation |",
             "|---|---:|---:|---:|---:|---|---|"]
    for symbol, real, rss, size, features, source, coverage, first, last, check in rows:
        lines.append(f"| {symbol} | {real/3600:.2f} h | {rss:.2f} GiB | {size/1024**3:.2f} GiB | {features:,}/{source:,} ({coverage:.4f}%) | {first} – {last} | {check} |")
    lines += ["", "Wall time includes operator-requested pauses for EURUSD, USDJPY and GBPUSD.", "",
              "## Oil quote exclusion audit", "",
              "Invalid observed quotes were removed before features, events, or labels; no spread was filled or invented.", "",
              "| Market | Excluded | Non-finite | Zero spread | Crossed | First affected month | Last affected month |",
              "|---|---:|---:|---:|---:|---|---|"]
    for symbol in ("LIGHTCMDUSD", "BRENTCMDUSD"):
        audit = [row for row in oil_audits if row["symbol"] == symbol]
        affected = [row for row in audit if row["excluded"]]
        lines.append(f"| {symbol} | {sum(r['excluded'] for r in audit):,} | {sum(r['nonfinite'] for r in audit):,} | {sum(r['zero_spread'] for r in audit):,} | {sum(r['crossed'] for r in audit):,} | {affected[0]['month']} | {affected[-1]['month']} |")
    lines += ["", "The raw-source diagnostic found 430,984 WTI and 276,645 Brent invalid quote rows; the build audit above is slightly lower because the standard bad-tick/stale filter runs first.",
              "The invalid oil regime predates the April 2020 WTI shock; April 2020 had zero invalid and zero negative-price quote rows in both local CFD feeds.", ""]
    target = Path("reports/data/stage9_production.md")
    target.write_text("\n".join(lines))
    print(target)


if __name__ == "__main__":
    main()
