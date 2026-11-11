"""Causal, minute-close features from Binance USD-M bookDepth snapshots.

The ±5% band is cumulative, so total depth uses its bid and ask notionals
once rather than summing nested percentage bands. A month is built with seven
days of prior minute history for an identical time-based rolling z-score.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import os
import time
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path("/Users/bfhach/Projects/market-signal-desk")
SYMBOLS = ("BTCUSDT", "ETHUSDT")
BANDS = (1, 2, 5)
WINDOWS = (5, 15, 60)
STALE_SECONDS = 120
COLUMNS = ["ts", *(f"depth_{side}_{band}pct" for band in BANDS for side in ("bid", "ask")),
           "notional_bid_5pct", "notional_ask_5pct"]


def missing_archive_days(root: Path, symbol: str) -> set[str]:
    log = root / "data/logs/missing_bookdepth.csv"
    if not log.exists():
        return set()
    with log.open(newline="") as stream:
        recorded = {row["date_or_month"] for row in csv.DictReader(stream)
                    if row.get("symbol") == symbol and row.get("scope") == "fetch_day"
                    and row.get("reason") == "HTTP 404"}
    raw = root / "data/raw/binance/bookDepth" / symbol
    return {day for day in recorded
            if not ((raw / f"{symbol}-bookDepth-{day}.zip").exists()
                    and (raw / f"{symbol}-bookDepth-{day}.zip.sha256").exists())}


def month_bounds(month: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    start = pd.Timestamp(month + "-01", tz="UTC")
    return start, start + pd.offsets.MonthBegin(1)


def read_snapshots(root: Path, symbol: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    base = root / "data/aux/binance_depth" / symbol
    months = pd.period_range(start.tz_localize(None).to_period("M"),
                             end.tz_localize(None).to_period("M"), freq="M")
    frames = []
    for month in months:
        path = base / f"{month}.parquet"
        if path.exists():
            frames.append(pq.read_table(path, columns=COLUMNS).to_pandas())
        else:
            raw = read_raw_month(root, symbol, str(month))
            if not raw.empty:
                frames.append(raw)
    if not frames:
        return pd.DataFrame(columns=COLUMNS)
    result = pd.concat(frames, ignore_index=True)
    result["ts"] = pd.to_datetime(result.ts, utc=True)
    return result.loc[(result.ts >= start) & (result.ts <= end)].sort_values("ts").drop_duplicates("ts")


def parse_raw_zip(path: Path) -> pd.DataFrame:
    """Read one verified archive, accepting integral CSV bands like '-5.00'."""
    sidecar = path.with_name(path.name + ".sha256")
    if not sidecar.exists():
        raise ValueError(f"Missing verified SHA256 sidecar: {path}")
    expected = sidecar.read_text().split()[0].lower()
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    if digest.hexdigest() != expected:
        raise ValueError(f"SHA256 mismatch: {path}")
    with zipfile.ZipFile(path) as archive:
        names = [name for name in archive.namelist() if name.endswith(".csv")]
        if len(names) != 1:
            raise ValueError(f"Expected one bookDepth CSV: {path}")
        with archive.open(names[0]) as stream:
            rows = pd.read_csv(stream, usecols=["timestamp", "percentage", "depth", "notional"])
    pct = pd.to_numeric(rows.percentage, errors="raise").to_numpy(dtype=float)
    required = {-5, -4, -3, -2, -1, 1, 2, 3, 4, 5}
    allowed = list(required | {-0.2, 0.2})
    if not np.isfinite(pct).all() or not np.isin(pct, allowed).all():
        raise ValueError(f"Invalid percentage band: {path}")
    if not (np.isfinite(rows.depth).all() and np.isfinite(rows.notional).all()
            and (rows.depth >= 0).all() and (rows.notional >= 0).all()):
        raise ValueError(f"Invalid depth/notional: {path}")
    rows["percentage"] = pct
    rows["ts"] = pd.to_datetime(rows.timestamp, utc=True)
    if rows.duplicated(["ts", "percentage"]).any():
        raise ValueError(f"Incomplete/duplicate snapshot: {path}")
    depths = rows.pivot(index="ts", columns="percentage", values="depth")
    if not required.issubset(depths.columns) or not depths[list(required)].notna().all().all():
        raise ValueError(f"Incomplete/duplicate snapshot: {path}")
    if (-0.2 in depths.columns) != (0.2 in depths.columns) or (
        {-0.2, 0.2} <= set(depths.columns) and not depths[-0.2].notna().equals(depths[0.2].notna())
    ):
        raise ValueError(f"Unpaired optional 0.2% band: {path}")
    notionals = rows.loc[rows.percentage.isin([-5, 5])].pivot(index="ts", columns="percentage", values="notional")
    result = pd.DataFrame({"ts": depths.index})
    for band in BANDS:
        result[f"depth_bid_{band}pct"] = depths[-band].to_numpy(dtype=float)
        result[f"depth_ask_{band}pct"] = depths[band].to_numpy(dtype=float)
    result["notional_bid_5pct"] = notionals[-5].to_numpy(dtype=float)
    result["notional_ask_5pct"] = notionals[5].to_numpy(dtype=float)
    return result


def read_raw_month(root: Path, symbol: str, month: str) -> pd.DataFrame:
    base = root / "data/raw/binance/bookDepth" / symbol
    paths = sorted(base.glob(f"{symbol}-bookDepth-{month}-??.zip"))
    if not paths:
        return pd.DataFrame(columns=COLUMNS)
    return pd.concat([parse_raw_zip(path) for path in paths], ignore_index=True).sort_values("ts").drop_duplicates("ts")


def _asof_indices(times: np.ndarray, queries: np.ndarray) -> np.ndarray:
    return np.searchsorted(times, queries, side="right") - 1


def make_features(snapshots: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """Return one minute-open row per minute in [start,end); no future lookup."""
    opens = pd.date_range(start, end, freq="min", inclusive="left")
    closes = opens + pd.Timedelta(minutes=1)
    result = pd.DataFrame({"ts": opens, "known_at": closes})
    value_columns = [f"depth_imbalance_{band}pct" for band in BANDS]
    value_columns += [f"depth_imbalance_{band}pct_change_{window}m" for band in BANDS for window in WINDOWS]
    value_columns += ["total_depth_notional_5pct", "total_depth_notional_5pct_z_7d"]
    if snapshots.empty:
        result["snapshot_ts"] = pd.NaT
        result["staleness_seconds"] = np.nan
        result["coverage"] = False
        for col in value_columns:
            result[col] = np.nan
        return result

    snap = snapshots.sort_values("ts").drop_duplicates("ts").reset_index(drop=True)
    snap_time = pd.to_datetime(snap.ts, utc=True).to_numpy(dtype="datetime64[ns]")
    close_time = closes.to_numpy(dtype="datetime64[ns]")
    current_idx = _asof_indices(snap_time, close_time)
    present = current_idx >= 0
    safe_idx = np.maximum(current_idx, 0)
    age = np.full(len(closes), np.nan)
    age[present] = (close_time[present] - snap_time[current_idx[present]]) / np.timedelta64(1, "s")
    valid = present & (age <= STALE_SECONDS)
    result["snapshot_ts"] = pd.Series(pd.to_datetime(snap_time[safe_idx], utc=True)).where(present)
    result["staleness_seconds"] = age
    result["coverage"] = valid

    for band in BANDS:
        bid = snap[f"depth_bid_{band}pct"].to_numpy(dtype=float)
        ask = snap[f"depth_ask_{band}pct"].to_numpy(dtype=float)
        with np.errstate(divide="ignore", invalid="ignore"):
            imbalance = (bid - ask) / (bid + ask)
        current = imbalance[safe_idx].copy()
        current[~valid] = np.nan
        result[f"depth_imbalance_{band}pct"] = current
        for window in WINDOWS:
            cutoff = close_time - np.timedelta64(window, "m")
            old_idx = _asof_indices(snap_time, cutoff)
            old_present = old_idx >= 0
            old_safe = np.maximum(old_idx, 0)
            old_age = np.full(len(closes), np.inf)
            old_age[old_present] = (cutoff[old_present] - snap_time[old_idx[old_present]]) / np.timedelta64(1, "s")
            change = current - imbalance[old_safe]
            change[~valid | ~old_present | (old_age > STALE_SECONDS)] = np.nan
            result[f"depth_imbalance_{band}pct_change_{window}m"] = change

    total = (snap.notional_bid_5pct.to_numpy(dtype=float) + snap.notional_ask_5pct.to_numpy(dtype=float))[safe_idx]
    total = total.astype(float, copy=True)
    total[~valid] = np.nan
    result["total_depth_notional_5pct"] = total
    # Compute against the complete warm-up minute grid, never later snapshots.
    series = pd.Series(total, index=closes)
    rolling = series.rolling("7D", min_periods=2)
    mean, std = rolling.mean().to_numpy(), rolling.std(ddof=0).to_numpy()
    with np.errstate(divide="ignore", invalid="ignore"):
        z = (total - mean) / std
    z[~np.isfinite(z)] = np.nan
    result["total_depth_notional_5pct_z_7d"] = z
    return result


def build_month(root: Path, symbol: str, month: str) -> tuple[pd.DataFrame, dict]:
    start, end = month_bounds(month)
    warm_start = start - pd.Timedelta(days=7)
    snapshots = read_snapshots(root, symbol, warm_start, end)
    frame = make_features(snapshots, warm_start, end)
    frame = frame.loc[(frame.ts >= start) & (frame.ts < end)].reset_index(drop=True)
    frame["source_missing_day"] = frame.ts.dt.strftime("%Y-%m-%d").isin(missing_archive_days(root, symbol))
    missing_mask = frame.source_missing_day
    if missing_mask.any():
        frame.loc[missing_mask, "coverage"] = False
        frame.loc[missing_mask, "snapshot_ts"] = pd.NaT
        frame.loc[missing_mask, "staleness_seconds"] = np.nan
        features = [column for column in frame if column.startswith(("depth_imbalance_", "total_depth_"))]
        frame.loc[missing_mask, features] = np.nan
    in_month = snapshots.loc[(snapshots.ts >= start) & (snapshots.ts < end)].sort_values("ts")
    cadence = in_month.ts.diff().dt.total_seconds()
    stats = {"month": month, "snapshots": len(in_month), "minutes": len(frame),
             "source": "parsed parquet" if (root / "data/aux/binance_depth" / symbol / f"{month}.parquet").exists() else "verified raw ZIP",
             "covered": int(frame.coverage.sum()), "stale": int((frame.staleness_seconds > STALE_SECONDS).sum()),
             "missing_day_minutes": int(missing_mask.sum()),
             "no_prior": int(frame.staleness_seconds.isna().sum()),
             "first_snapshot": str(in_month.ts.min()) if len(in_month) else "none",
             "last_snapshot": str(in_month.ts.max()) if len(in_month) else "none",
             "cadence_median_s": float(cadence.median()) if len(cadence.dropna()) else float("nan"),
             "max_gap_s": float(cadence.max()) if len(cadence.dropna()) else float("nan")}
    return frame, stats


def write_month(root: Path, symbol: str, month: str, frame: pd.DataFrame) -> Path:
    out = root / "data/features_depth" / symbol / f"{month}.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + f".part.{os.getpid()}")
    try:
        pq.write_table(pa.Table.from_pandas(frame, preserve_index=False), tmp, compression="zstd")
        if pq.read_metadata(tmp).num_rows != len(frame):
            raise ValueError(f"Parquet row count mismatch: {tmp}")
        os.replace(tmp, out)
    finally:
        tmp.unlink(missing_ok=True)
    return out


def write_report(root: Path, symbol: str, rows: list[dict], elapsed: float) -> Path:
    path = Path("reports/data") / f"depth_feature_coverage_{symbol}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        note = f"# Binance bookDepth feature coverage — {symbol}\n\nNo parsed monthly snapshots or verified raw archives were present for {symbol}; no feature months were generated.\n"
        log = root / "data/logs/binance_depth_download.log"
        if log.exists() and "invalid literal for int() with base 10: '-5.00'" in log.read_text():
            note += "\nThe downloader stopped while parsing BTC January 2026 because the existing parser expects integral band strings. It did not reach ETH. The feature builder can parse verified raw ZIPs with decimal band strings, but no ETH ZIPs are present.\n"
        path.write_text(note)
        return path
    first = rows[0]["month"]
    lines = [f"# Binance bookDepth feature coverage — {symbol}", "",
             f"Available snapshots: {first} through {rows[-1]['month']}. The public UM daily archive begins 2023-01-01 (2021–2022 URLs returned 404 during downloader discovery).",
             f"First parsed snapshot: `{rows[0]['first_snapshot']}`; last parsed snapshot: `{rows[-1]['last_snapshot']}`. Largest within-month snapshot gap: {max(r['max_gap_s'] for r in rows):,.0f} seconds.",
             "", "Each archive CSV has `timestamp`, `percentage` (−5 through −1 bid; +1 through +5 ask), `depth` (base units), and `notional` (quote units). January 2026 introduced decimal-form integral bands and an optional paired ±0.2% band. Every snapshot must contain the ten required bands. The parser pivots them to one snapshot row and sets snapshot `known_at = timestamp`. Snapshot cadence is approximately 30 seconds. Features are minute-open rows with `known_at` at minute close. Every as-of snapshot time is ≤ `known_at`; observations older than 120 seconds have `coverage=False` and NaN features. The 5% total notional avoids double-counting nested bands. The z-score uses a trailing 7D minute grid with at least two valid values and population standard deviation; missing first-history observations remain NaN.",
             "", "`source_missing_day=True` marks a source archive confirmed HTTP 404. All market features, snapshot time and staleness are null on those days; coverage is false.",
             "", "| Month | Source | Snapshots | Minutes | Covered | Coverage | Missing archive minutes | Stale >120s | No prior | Median cadence (s) | Max gap (s) |",
             "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for r in rows:
        lines.append(f"| {r['month']} | {r['source']} | {r['snapshots']:,} | {r['minutes']:,} | {r['covered']:,} | {r['covered']/r['minutes']:.2%} | {r['missing_day_minutes']:,} | {r['stale']:,} | {r['no_prior']:,} | {r['cadence_median_s']:.1f} | {r['max_gap_s']:.0f} |")
    minutes = sum(r["minutes"] for r in rows)
    covered = sum(r["covered"] for r in rows)
    lines += ["", f"Total: **{sum(r['snapshots'] for r in rows):,}** snapshots; **{covered:,}/{minutes:,}** minutes covered (**{covered/minutes:.2%}**). Build runtime: **{elapsed:.1f} s**.", ""]
    if rows[-1]["minutes"] < int((month_bounds(rows[-1]["month"])[1] - month_bounds(rows[-1]["month"])[0]) / pd.Timedelta(minutes=1)):
        lines.append(f"The final month is partial; output stops at the close of the last downloaded source day ({rows[-1]['last_snapshot'][:10]}).")
        lines.append("")
    path.write_text("\n".join(lines))
    return path


def run(root: Path = ROOT, symbols: tuple[str, ...] = SYMBOLS) -> None:
    for symbol in symbols:
        started = time.monotonic()
        base = root / "data/aux/binance_depth" / symbol
        months = {p.stem for p in base.glob("????-??.parquet")} if base.exists() else set()
        raw_base = root / "data/raw/binance/bookDepth" / symbol
        if raw_base.exists():
            months.update(p.name[len(symbol) + len("-bookDepth-"):][:7]
                          for p in raw_base.glob(f"{symbol}-bookDepth-????-??-??.zip"))
        months = sorted(months)
        rows = []
        for month in months:
            frame, stats = build_month(root, symbol, month)
            if month == months[-1] and stats["last_snapshot"] != "none":
                final_day = pd.Timestamp(stats["last_snapshot"]).floor("D") + pd.Timedelta(days=1)
                missing_days = [pd.Timestamp(day, tz="UTC") + pd.Timedelta(days=1)
                                for day in missing_archive_days(root, symbol) if day.startswith(month)]
                if missing_days:
                    final_day = max(final_day, *missing_days)
                frame = frame.loc[frame.ts < final_day].reset_index(drop=True)
                stats.update(minutes=len(frame), covered=int(frame.coverage.sum()),
                             stale=int((frame.staleness_seconds > STALE_SECONDS).sum()),
                             no_prior=int(frame.staleness_seconds.isna().sum()),
                             missing_day_minutes=int(frame.source_missing_day.sum()))
            path = write_month(root, symbol, month, frame)
            rows.append(stats)
            print(f"{symbol} {month}: {stats['covered']:,}/{stats['minutes']:,} covered; {stats['snapshots']:,} snapshots -> {path}", flush=True)
        report = write_report(root, symbol, rows, time.monotonic() - started)
        print(f"{symbol}: {len(months)} months; report {report}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=ROOT)
    parser.add_argument("--symbols", nargs="+", choices=SYMBOLS, default=list(SYMBOLS))
    args = parser.parse_args()
    run(args.data_root, tuple(args.symbols))
