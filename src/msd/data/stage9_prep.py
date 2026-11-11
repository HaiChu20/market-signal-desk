"""Measure Stage 9 quote windows/costs and run isolated HTF dry builds."""
from __future__ import annotations

import argparse
import csv
import json
import os
import resource
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from msd.processing.instruments import STAGE9_INSTRUMENTS
from msd.processing.timeframes import build_all_timeframes

ROOT = Path("/Users/bfhach/Projects/market-signal-desk")
REPORT = Path("reports/data/stage9_market_prep.md")
SPREAD_CSV = Path("reports/data/stage9_spread_by_local_hour.csv")
DAY_NAMES = ("Mon", "Tue", "Wed", "Thu", "Fri")


def complete_paths(root: Path, symbol: str, count: int = 12) -> list[Path]:
    paths = sorted((root / "data/bars/dukascopy" / symbol).glob("????-??.parquet"))
    complete = [path for path in paths if (pq.read_metadata(path).metadata or {}).get(b"msd_complete") == b"1"]
    return complete[-count:]


def read_paths(paths: list[Path], columns: list[str]) -> pd.DataFrame:
    return pd.concat([pq.read_table(path, columns=columns).to_pandas() for path in paths], ignore_index=True)


def _runs(mask: np.ndarray) -> list[tuple[int, int]]:
    result, start = [], None
    for index, value in enumerate(np.r_[mask, False]):
        if value and start is None:
            start = index
        if not value and start is not None:
            result.append((start, index)); start = None
    return result


def _clock(minute: int) -> str:
    return "24:00" if minute == 1440 else f"{minute // 60:02d}:{minute % 60:02d}"


def measure_symbol(root: Path, symbol: str) -> tuple[dict, list[dict]]:
    spec = STAGE9_INSTRUMENTS[symbol]
    paths = complete_paths(root, symbol)
    if not paths:
        return {"symbol": symbol, "status": "pending local data"}, []
    frame = read_paths(paths, ["ts", "bid_o", "ask_o"])
    frame["ts"] = pd.to_datetime(frame.ts, utc=True)
    local = frame.ts.dt.tz_convert(spec.timezone)
    spread = pd.to_numeric(frame.ask_o, errors="coerce") - pd.to_numeric(frame.bid_o, errors="coerce")
    valid = np.isfinite(spread) & (spread > 0)
    hourly = []
    for hour in range(24):
        values = spread[valid & local.dt.hour.eq(hour)]
        hourly.append({"symbol": symbol, "timezone": spec.timezone, "local_hour": hour,
                       "median_spread": float(values.median()) if len(values) else np.nan,
                       "p95_spread": float(values.quantile(.95)) if len(values) else np.nan,
                       "rows": len(values)})
    windows = []
    minute = local.dt.hour * 60 + local.dt.minute
    for weekday in range(5):
        selection = local.dt.day_of_week.eq(weekday)
        dates = local.loc[selection].dt.date
        denominator = max(1, len(set(dates)))
        occupancy = minute.loc[selection].value_counts().reindex(range(1440), fill_value=0) / denominator
        gaps = [f"{_clock(start)}–{_clock(end)}" for start, end in _runs(occupancy.lt(.05).to_numpy()) if end - start >= 5]
        windows.append(f"{DAY_NAMES[weekday]}: {', '.join(gaps) if gaps else 'none'}")
    medians = np.asarray([row["median_spread"] for row in hourly], dtype=float)
    return {"symbol": symbol, "status": "measured", "months": f"{paths[0].stem}–{paths[-1].stem}",
            "windows": "; ".join(windows), "hourly_min": float(np.nanmin(medians)),
            "hourly_max": float(np.nanmax(medians)), "point_scale": spec.point_scale}, hourly


def write_reports(root: Path) -> None:
    measurements, hourly = [], []
    for symbol in STAGE9_INSTRUMENTS:
        measured, cost = measure_symbol(root, symbol)
        measurements.append(measured); hourly.extend(cost)
    SPREAD_CSV.parent.mkdir(parents=True, exist_ok=True)
    with SPREAD_CSV.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["symbol", "timezone", "local_hour", "median_spread", "p95_spread", "rows"])
        writer.writeheader(); writer.writerows(hourly)
    lines = ["# Stage 9 remaining-market preparation", "",
             "Quote windows and hourly costs are measured from the latest twelve complete local Dukascopy months. A no-quote window requires <5% minute occupancy on that local weekday. Session rules use these recurring windows and timezone conversion remains DST-aware. The hourly cost artifact contains the median and P95 executable `ask_o − bid_o`; labels continue to consume the actual bid/ask path.", "",
             "| Symbol | Complete sample | Configured quote session | Observed weekday no-quote windows | Hourly median spread range | Point scale | Label class / nightly rate |",
             "|---|---|---|---|---:|---:|---|"]
    for row in measurements:
        symbol = row["symbol"]; spec = STAGE9_INSTRUMENTS[symbol]
        if row["status"] != "measured":
            lines.append(f"| {symbol} | unavailable | pending measurement | no complete local month | — | — | {spec.label_class} / {spec.financing_per_night:.5f} |")
            continue
        opened = _clock(int(spec.session_open_minute)); closed = _clock(int(spec.session_close_minute))
        lines.append(f"| {symbol} | {row['months']} | {opened}–{closed} {spec.timezone} | {row['windows']} | {row['hourly_min']:.6g}–{row['hourly_max']:.6g} | {row['point_scale']:,} | {spec.label_class} / {spec.financing_per_night:.5f} |")
    lines += ["", "## Gaps before production Stage 9", "",
              "- JPNIDXJPY has no complete local month, so its session endpoints, hourly spread costs and point scale remain unset. Its HTF builder fails closed.",
              "- GBRIDXGBP is measured through 2024-12 only. Re-run this audit after the active campaign finishes before its production build.",
              "- The existing label kernel has weekday deadlines and a 17:00 New York financing counter for all non-crypto instruments. The descriptive FX/metal/energy classes and explicit rates are prepared; class-specific rollover financing would require a separate kernel change.",
              "- No production Stage 9 outputs were written. Dry-run artifacts are isolated under `data/tmp/fe242257/`.", "",
              f"Hourly cost artifact: `{SPREAD_CSV}`.", ""]
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines))


def dry_run(root: Path, symbol: str, year: int) -> dict:
    paths = complete_paths(root, symbol, count=10_000)
    paths = [path for path in paths if path.stem.startswith(str(year))]
    if len(paths) != 12:
        raise ValueError(f"{symbol} {year} needs 12 complete months, found {len(paths)}")
    started = time.perf_counter()
    bars = read_paths(paths, ["ts", "bid_o", "bid_h", "bid_l", "bid_c", "ask_o", "ask_h", "ask_l", "ask_c", "volume"])
    outputs = build_all_timeframes(bars, symbol)
    target = root / "data/tmp/fe242257" / symbol
    target.mkdir(parents=True, exist_ok=True)
    for name, frame in outputs.items():
        path = target / f"{year}_{name}.parquet"
        tmp = path.with_name(path.name + f".part.{os.getpid()}")
        try:
            frame.to_parquet(tmp, index=False, compression="zstd")
            os.replace(tmp, path)
        finally:
            tmp.unlink(missing_ok=True)
    return {"symbol": symbol, "year": year, "input_rows": len(bars),
            "output_rows": {name: len(frame) for name, frame in outputs.items()},
            "seconds": round(time.perf_counter() - started, 3),
            "peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=ROOT)
    parser.add_argument("--report", action="store_true")
    parser.add_argument("--dry-run", choices=tuple(STAGE9_INSTRUMENTS))
    parser.add_argument("--year", type=int, default=2025)
    args = parser.parse_args()
    if args.report:
        write_reports(args.data_root)
        print(REPORT)
    if args.dry_run:
        print(json.dumps(dry_run(args.data_root, args.dry_run, args.year), sort_keys=True))


if __name__ == "__main__":
    main()
