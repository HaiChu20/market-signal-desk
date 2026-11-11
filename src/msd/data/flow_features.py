"""Causal, separately stored features derived from minute flow feeds.

Every row is keyed by ``known_at`` (the close time of its source minute). Missing
source minutes remain NaN and are indicated by explicit coverage columns.
"""
from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

BAR_ROOT = Path("data/bars")
OUTPUT_ROOT = Path("data/features_flow")
REPORT_ROOT = Path("reports/data")
WINDOWS = (1, 5, 15, 60)
INTENSITY_WINDOW_MIN = 20 * 24 * 60
INTENSITY_MIN_PERIODS = 24 * 60
MIN_COVERAGE = 0.80
DEPTH_COLUMNS = ("depth_coverage", "depth_imbalance_1pct", "depth_imbalance_1pct_change_5m",
                 "depth_imbalance_1pct_change_15m", "depth_imbalance_1pct_change_60m",
                 "depth_imbalance_2pct", "depth_imbalance_2pct_change_5m",
                 "depth_imbalance_2pct_change_15m", "depth_imbalance_2pct_change_60m",
                 "depth_imbalance_5pct", "depth_imbalance_5pct_change_5m",
                 "depth_imbalance_5pct_change_15m", "depth_imbalance_5pct_change_60m",
                 "total_depth_notional_5pct", "total_depth_notional_5pct_z_7d")


def _utc(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result["ts"] = pd.to_datetime(result.ts, utc=True).astype("datetime64[ns, UTC]")
    if "known_at" not in result:
        result["known_at"] = result.ts + pd.Timedelta(minutes=1)
    result["known_at"] = pd.to_datetime(result.known_at, utc=True).astype("datetime64[ns, UTC]")
    return result.sort_values("known_at", kind="stable").reset_index(drop=True)


def _load_months(root: Path, symbol: str, month: str, *, prior_months: int = 1) -> pd.DataFrame:
    paths = _paths(root, symbol, month, prior_months=prior_months)
    target_start = pd.Period(month, freq="M").start_time.tz_localize("UTC")
    frames = []
    for path in paths:
        frame = pd.read_parquet(path)
        frame["ts"] = pd.to_datetime(frame.ts, utc=True)
        if len(frame):
            frames.append(frame)
    if not frames:
        return pd.DataFrame()
    return _utc(pd.concat(frames, ignore_index=True)).drop_duplicates("known_at", keep="last")


def _join_source(grid: pd.DataFrame, source: pd.DataFrame | None, prefix: str) -> pd.DataFrame:
    if source is None or source.empty:
        return grid
    source = _utc(source)
    if source.known_at.duplicated().any():
        raise ValueError(f"duplicate known_at in {prefix} flow rows")
    source = source.drop(columns=["ts"], errors="ignore").rename(
        columns={column: f"{prefix}_{column}" for column in source.columns if column != "known_at"}
    )
    return grid.merge(source, on="known_at", how="left", validate="one_to_one", sort=False)


def _rolling_features(frame: pd.DataFrame, prefix: str, *, buy_col: str, sell_col: str,
                      count_col: str, large_pairs: tuple[tuple[str, str, str], ...] = ()) -> pd.DataFrame:
    result = frame
    buy = result.get(f"{prefix}_{buy_col}", pd.Series(np.nan, index=result.index, dtype="float64"))
    sell = result.get(f"{prefix}_{sell_col}", pd.Series(np.nan, index=result.index, dtype="float64"))
    delta = buy - sell
    volume = buy + sell
    index = pd.DatetimeIndex(result.known_at)
    delta = pd.Series(delta.to_numpy(float), index=index)
    volume = pd.Series(volume.to_numpy(float), index=index)
    covered = pd.Series(result[f"{prefix}_flow_coverage"].to_numpy(bool), index=index)
    for window in WINDOWS:
        roll = f"{window}min"
        enough = covered.rolling(roll, closed="right").sum() >= math.ceil(MIN_COVERAGE * window)
        dsum = delta.rolling(roll, closed="right").sum().where(enough)
        total = volume.rolling(roll, closed="right").sum().where(enough)
        result[f"{prefix}_delta_{window}m"] = dsum.to_numpy()
        result[f"{prefix}_imbalance_{window}m"] = (dsum / total.where(total != 0)).to_numpy()

    intensity = result.get(f"{prefix}_{count_col}", pd.Series(np.nan, index=result.index, dtype="float64"))
    intensity = pd.Series(intensity.to_numpy(float), index=index)
    rolling = intensity.rolling("20D", closed="right", min_periods=INTENSITY_MIN_PERIODS)
    std = rolling.std(ddof=0).replace(0, np.nan)
    result[f"{prefix}_trade_intensity_z20d"] = ((intensity - rolling.mean()) / std).to_numpy()

    for threshold, large_buy, large_sell in large_pairs:
        bcol, scol = f"{prefix}_{large_buy}", f"{prefix}_{large_sell}"
        if bcol not in result or scol not in result:
            result[f"{prefix}_large{threshold}_imbalance_1m"] = np.nan
            continue
        lb, ls = result[bcol], result[scol]
        result[f"{prefix}_large{threshold}_imbalance_1m"] = (lb - ls) / (lb + ls).where((lb + ls) != 0)
    return result


def build_flow_features(primary: pd.DataFrame, *, spot: pd.DataFrame | None = None,
                        perp: pd.DataFrame | None = None, bybit: pd.DataFrame | None = None,
                        ticks: pd.DataFrame | None = None,
                        covered_minutes: dict[str, pd.DatetimeIndex] | None = None) -> pd.DataFrame:
    """Build one causal minute feature layer aligned to primary bars."""
    base = _utc(primary)
    base["known_at"] = base.ts + pd.Timedelta(minutes=1)
    if base.known_at.duplicated().any():
        raise ValueError("primary bars must have unique known_at timestamps")
    primary_known_at = pd.DatetimeIndex(base.known_at)
    if "close" in base:
        close = base.close
    elif {"bid_c", "ask_c"}.issubset(base.columns):
        close = (base.bid_c + base.ask_c) / 2
    elif "bid_c" in base:
        close = base.bid_c
    elif "c" in base:
        close = base.c
    else:
        close = pd.Series(np.nan, index=base.index, dtype="float64")
    grid = base[["ts", "known_at"]].copy()
    grid["_primary_close"] = close.to_numpy(dtype=np.float64)
    # Quote-less minutes are absent from Dukascopy's primary bars. Tick flow is
    # therefore calculated on a complete clock and sampled back to primary rows.
    # Crypto keeps its original primary grid unchanged.
    tick_clock = "ticks" in (covered_minutes or {})
    if tick_clock and len(grid):
        clock_known_at = pd.date_range(grid.known_at.min(), grid.known_at.max(), freq="min", tz="UTC")
        clock = pd.DataFrame({"known_at": clock_known_at})
        clock["ts"] = clock.known_at - pd.Timedelta(minutes=1)
        grid = clock.merge(grid[["known_at", "_primary_close"]], on="known_at", how="left",
                           validate="one_to_one", sort=True)

    source_frames = {"spot": spot, "perp": perp, "bybit": bybit}
    covered_minutes = covered_minutes or {}
    for name, source in source_frames.items():
        if source is not None and not source.empty:
            source = _utc(source)
            if {"buy_taker_volume", "sell_taker_volume"}.issubset(source.columns):
                source["buy_vol"] = source.buy_taker_volume
                source["sell_vol"] = source.sell_taker_volume
            if "trade_count" not in source:
                if {"buy_n", "sell_n"}.issubset(source.columns):
                    source["trade_count"] = source.buy_n + source.sell_n
                elif {"buy_trade_count", "sell_trade_count"}.issubset(source.columns):
                    source["trade_count"] = source.buy_trade_count + source.sell_trade_count
            source_frames[name] = source
        grid = _join_source(grid, source, name)
        activity = grid.get(f"{name}_buy_vol", pd.Series(np.nan, index=grid.index)).notna()
        grid[f"{name}_flow_coverage"] = (grid.known_at.isin(covered_minutes[name]) if name in covered_minutes
                                          else activity)
        missing_source = ~grid[f"{name}_flow_coverage"]
        raw_columns = [column for column in grid if column.startswith(f"{name}_")
                       and column != f"{name}_flow_coverage"]
        grid.loc[missing_source, raw_columns] = np.nan
        for column in ("buy_vol", "sell_vol", "trade_count", "buy_n", "sell_n",
                       "large100k_buy_notional", "large100k_sell_notional",
                       "large1m_buy_notional", "large1m_sell_notional"):
            key = f"{name}_{column}"
            if key in grid:
                grid.loc[grid[f"{name}_flow_coverage"] & ~activity, key] = 0.0
        if f"{name}_trade_count" not in grid:
            if f"{name}_buy_n" in grid and f"{name}_sell_n" in grid:
                grid[f"{name}_trade_count"] = grid[f"{name}_buy_n"] + grid[f"{name}_sell_n"]
            else:
                grid[f"{name}_trade_count"] = np.nan
        _rolling_features(
            grid, name, buy_col="buy_vol", sell_col="sell_vol", count_col="trade_count",
            large_pairs=(("100k", "large100k_buy_notional", "large100k_sell_notional"),
                         ("1m", "large1m_buy_notional", "large1m_sell_notional")),
        )

    for window in WINDOWS:
        grid[f"spot_perp_delta_spread_{window}m"] = grid[f"spot_delta_{window}m"] - grid[f"perp_delta_{window}m"]
        grid[f"spot_bybit_delta_spread_{window}m"] = grid[f"spot_delta_{window}m"] - grid[f"bybit_delta_{window}m"]

    if ticks is not None and not ticks.empty:
        tick = _utc(ticks)
        tick_columns = [column for column in ("ofi", "size_imbalance", "tick_count", "mean_spread", "max_spread",
                                               "bid_size_sum", "ask_size_sum")
                        if column in tick]
        grid = _join_source(grid, tick[["ts", "known_at", *tick_columns]], "ticks")
        grid["tick_flow_coverage"] = (grid.known_at.isin(covered_minutes["ticks"]) if "ticks" in covered_minutes
                                      else grid.get("ticks_tick_count", pd.Series(np.nan, index=grid.index)).notna())
    else:
        grid["tick_flow_coverage"] = False
        for column in ("ofi", "size_imbalance", "tick_count", "mean_spread", "max_spread",
                       "bid_size_sum", "ask_size_sum"):
            grid[f"ticks_{column}"] = np.nan
    if "ticks" in covered_minutes:
        grid["tick_flow_coverage"] = grid.known_at.isin(covered_minutes["ticks"])
        raw_columns = [column for column in grid if column.startswith("ticks_")]
        grid.loc[~grid.tick_flow_coverage, raw_columns] = np.nan
        inactive = grid.tick_flow_coverage & grid.ticks_tick_count.isna()
        for column in ("ticks_ofi", "ticks_tick_count", "ticks_bid_size_sum", "ticks_ask_size_sum"):
            grid.loc[inactive, column] = 0.0
    index = pd.DatetimeIndex(grid.known_at)
    covered = pd.Series(grid.tick_flow_coverage.to_numpy(bool), index=index)
    for window in (5, 15, 60):
        sufficient = covered.rolling(f"{window}min", closed="right").sum() >= math.ceil(MIN_COVERAGE * window)
        for column, how in (("ticks_ofi", "sum"), ("ticks_tick_count", "sum")):
            values = pd.Series(grid[column].to_numpy(float), index=index)
            roll = values.rolling(f"{window}min", closed="right")
            data = roll.sum() if how == "sum" else roll.mean()
            grid[f"{column}_{window}m"] = data.where(sufficient).to_numpy()
        bid = pd.Series(grid.ticks_bid_size_sum.to_numpy(float), index=index).rolling(f"{window}min", closed="right").sum()
        ask = pd.Series(grid.ticks_ask_size_sum.to_numpy(float), index=index).rolling(f"{window}min", closed="right").sum()
        grid[f"ticks_size_imbalance_{window}m"] = ((bid - ask) / (bid + ask).where((bid + ask) != 0)).where(sufficient).to_numpy()
    count = pd.Series(grid.ticks_tick_count.to_numpy(float), index=index)
    roll = count.rolling("20D", closed="right", min_periods=INTENSITY_MIN_PERIODS)
    grid["ticks_count_z20d"] = ((count - roll.mean()) / roll.std(ddof=0).replace(0, np.nan)).to_numpy()

    grid["flow_coverage"] = grid[[column for column in grid if column.endswith("_flow_coverage")]].any(axis=1)
    prices = pd.Series(grid._primary_close.to_numpy(float), index=index)
    prior = prices.reindex(index - pd.Timedelta(minutes=60)).to_numpy()
    grid["cum_delta_divergence_60m"] = -np.sign(grid["spot_delta_60m"]) * (grid._primary_close / prior - 1)
    grid = grid.drop(columns="_primary_close")
    columns = ["ts", "known_at", "flow_coverage", "tick_flow_coverage"]
    for name in ("spot", "perp", "bybit"):
        columns += [f"{name}_flow_coverage", f"{name}_trade_intensity_z20d",
                    f"{name}_large100k_imbalance_1m", f"{name}_large1m_imbalance_1m"]
        for window in WINDOWS:
            columns += [f"{name}_delta_{window}m", f"{name}_imbalance_{window}m"]
    for window in WINDOWS:
        columns += [f"spot_perp_delta_spread_{window}m", f"spot_bybit_delta_spread_{window}m"]
    columns += ["cum_delta_divergence_60m", "perp_uncovered_volume", "perp_um_kline_agg_mismatch",
                "ticks_ofi", "ticks_size_imbalance", "ticks_tick_count", "ticks_mean_spread",
                "ticks_max_spread", "ticks_bid_size_sum", "ticks_ask_size_sum", "ticks_count_z20d"]
    for window in (5, 15, 60):
        columns += [f"ticks_ofi_{window}m", f"ticks_size_imbalance_{window}m",
                    f"ticks_tick_count_{window}m"]
    for column in columns:
        if column not in grid:
            grid[column] = np.nan
    result = grid[columns]
    if tick_clock:
        result = result.loc[result.known_at.isin(primary_known_at)].reset_index(drop=True)
    return result


def join_by_known_at(features: pd.DataFrame, flow_features: pd.DataFrame,
                     depth_path: Path | None = None) -> pd.DataFrame:
    """Backward as-of join flow and optional depth, both keyed by publication time."""
    left = features.copy()
    right = flow_features.copy()
    left["known_at"] = pd.to_datetime(left.known_at, utc=True).astype("datetime64[ns, UTC]")
    right["known_at"] = pd.to_datetime(right.known_at, utc=True).astype("datetime64[ns, UTC]")
    if left.known_at.duplicated().any() or right.known_at.duplicated().any():
        raise ValueError("known_at keys must be unique for flow feature joins")
    left = left.sort_values("known_at", kind="stable")
    right = right.sort_values("known_at", kind="stable").drop(columns="ts", errors="ignore")
    joined = pd.merge_asof(left, right, on="known_at", direction="backward", tolerance=pd.Timedelta(minutes=1),
                           suffixes=("", "_flow"))
    if depth_path is not None:
        if depth_path.is_file():
            depth = pd.read_parquet(depth_path)
            depth = depth.rename(columns={"coverage": "depth_coverage"})
            depth = depth[[column for column in ("known_at", *DEPTH_COLUMNS) if column in depth.columns]]
            depth["known_at"] = pd.to_datetime(depth.known_at, utc=True).astype("datetime64[ns, UTC]")
            joined = pd.merge_asof(joined.sort_values("known_at"), depth.sort_values("known_at"),
                                   on="known_at", direction="backward", tolerance=pd.Timedelta(minutes=1),
                                   suffixes=("", "_depth"))
        else:
            for column in DEPTH_COLUMNS:
                joined[column] = np.nan
        for column in DEPTH_COLUMNS:
            if column not in joined:
                joined[column] = np.nan
    return joined


def _paths(root: Path, symbol: str, month: str, *, prior_months: int = 1) -> list[Path]:
    target = pd.Period(month, freq="M")
    earliest = target - prior_months
    selected = []
    for path in root.glob(f"{symbol}/*.parquet"):
        try:
            file_month = pd.Period(path.stem[:7], freq="M")
        except ValueError:
            continue
        if earliest <= file_month <= target:
            selected.append(path)
    full_months = {p.stem for p in selected if len(p.stem) == 7}
    return sorted(p for p in selected if len(p.stem) == 7 or p.stem[:7] not in full_months)


def _file_coverage(symbol: str, month: str, primary: pd.DataFrame, crypto: bool) -> dict[str, pd.DatetimeIndex]:
    """Source presence, including valid files with no trades in a minute."""
    times = pd.to_datetime(primary.ts, utc=True)
    known = pd.to_datetime(primary.known_at, utc=True)
    result: dict[str, pd.DatetimeIndex] = {}
    if crypto:
        for name, root in (("spot", BAR_ROOT / "binance_flow" / "spot"),
                           ("perp", BAR_ROOT / "binance_flow" / "um")):
            months = {pd.Period(p.stem[:7], "M") for p in _paths(root, symbol, month, prior_months=2)
                      if (pq.read_schema(p).metadata or {}).get(b"msd_complete") == b"1"}
            result[name] = pd.DatetimeIndex(known[times.dt.tz_localize(None).dt.to_period("M").isin(months)])
        bybit_days = set()
        bybit_months = {pd.Period(p.stem[:7], "M") for p in _paths(BAR_ROOT / "bybit_flow", symbol, month, prior_months=2)}
        for path in (Path("data/raw/bybit") / symbol).glob("*.csv.gz.sha256"):
            try:
                day = pd.Timestamp(path.name[len(symbol):len(symbol)+10])
                if day.to_period("M") in bybit_months:
                    bybit_days.add(day.date())
            except ValueError:
                continue
        result["bybit"] = pd.DatetimeIndex(known[times.dt.date.astype(object).isin(bybit_days)])
    else:
        raw = Path("data/raw/dukascopy_ticks") / symbol
        empty = set()
        missing = Path("data/logs/missing_dukascopy_ticks.csv")
        if missing.exists():
            with missing.open(newline="") as stream:
                for row in csv.reader(stream):
                    if len(row) >= 4 and row[1] == symbol and "empty archive" in row[3]:
                        empty.add(pd.Timestamp(row[2]).floor("h"))
        clock_ts = pd.date_range(times.min().floor("min"), times.max().floor("min"), freq="min", tz="UTC")
        hours = pd.DatetimeIndex(clock_ts.floor("h").unique())
        present = set(empty)
        for hour in hours:
            path = raw / hour.strftime("%Y/%m/%d/%Hh_ticks.bi5")
            if path.is_file() and path.with_suffix(".bi5.sha256").is_file():
                present.add(hour)
        result["ticks"] = pd.DatetimeIndex(clock_ts[clock_ts.floor("h").isin(present)] + pd.Timedelta(minutes=1))
    return result


def build_month(symbol: str, month: str) -> Path:
    crypto = symbol in {"BTCUSDT", "ETHUSDT"}
    primary_root = BAR_ROOT / ("binance_spot" if crypto else "dukascopy")
    primary = _load_months(primary_root, symbol, month, prior_months=2)
    if primary.empty:
        raise FileNotFoundError(f"No primary bars for {symbol} {month} under {primary_root}")
    start = pd.Period(month, freq="M").start_time.tz_localize("UTC")
    end = start + pd.DateOffset(months=1)
    current_mask = primary.ts.ge(start) & primary.ts.lt(end)
    warm = primary.loc[~current_mask].copy()
    current = primary.loc[current_mask].copy()
    if current.empty:
        raise ValueError(f"No primary bars in requested month {symbol} {month}")

    if crypto:
        # Include prior-month warm-up rows as well as the requested month.
        def for_month(root: Path) -> pd.DataFrame:
            frames = []
            for p in _paths(root, symbol, month, prior_months=2):
                f = pd.read_parquet(p)
                if len(f):
                    frames.append(f)
            if not frames:
                return pd.DataFrame()
            merged = pd.concat(frames, ignore_index=True)
            duplicate = merged.loc[merged.known_at.duplicated(keep=False)]
            if not duplicate.empty and (duplicate.groupby("known_at", sort=False).nunique(dropna=False).max(axis=1) > 1).any():
                raise ValueError(f"conflicting duplicate flow minutes in {root} {symbol} {month}")
            return merged.drop_duplicates("known_at", keep="last")
        spot, perp, bybit = (for_month(BAR_ROOT / "binance_flow" / "spot"),
                             for_month(BAR_ROOT / "binance_flow" / "um"),
                             for_month(BAR_ROOT / "bybit_flow"))
        features = build_flow_features(pd.concat([warm, current], ignore_index=True),
                                       spot=spot, perp=perp, bybit=bybit,
                                       covered_minutes=_file_coverage(symbol, month, primary, True))
    else:
        ticks = _load_months(BAR_ROOT / "dukascopy_flow", symbol, month, prior_months=2)
        features = build_flow_features(pd.concat([warm, current], ignore_index=True), ticks=ticks,
                                       covered_minutes=_file_coverage(symbol, month, primary, False))
    features = features.loc[features.ts.ge(start) & features.ts.lt(end)].copy()
    output = OUTPUT_ROOT / symbol / f"{month}.parquet"
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_name(output.name + f".{__import__('os').getpid()}.tmp")
    features.to_parquet(tmp, compression="zstd", index=False)
    tmp.replace(output)
    return output


def write_report(symbol: str) -> Path:
    paths = sorted((OUTPUT_ROOT / symbol).glob("*.parquet"))
    if not paths:
        raise FileNotFoundError(f"No flow feature files for {symbol}")
    flags = ["flow_coverage", "spot_flow_coverage", "perp_flow_coverage",
             "bybit_flow_coverage", "tick_flow_coverage"]
    coverage = []
    feature_columns: list[str] = []
    for path in paths:
        columns = pd.read_parquet(path, columns=["ts", *flags])
        columns["year"] = pd.to_datetime(columns.ts, utc=True).dt.year
        for column in flags:
            if column in columns:
                coverage.append(columns.groupby("year")[column].agg(["count", "sum"]).assign(source=column))
        if not feature_columns:
            feature_columns = [column for column in pq.read_schema(path).names if column not in {"ts", "known_at"}]
    totals: dict[tuple[int, str], list[int]] = {}
    for frame in coverage:
        for year, row in frame.iterrows():
            key = (int(year), str(row.source))
            values = totals.setdefault(key, [0, 0])
            values[0] += int(row["sum"])
            values[1] += int(row["count"])
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    output = REPORT_ROOT / f"flow_feature_coverage_{symbol}.md"
    with output.open("w") as report:
        report.write(f"# Flow feature coverage: {symbol}\n\n")
        report.write("Coverage includes verified source files with no activity; unavailable source periods remain NaN.\n\n")
        report.write("| Year | Source flag | Covered rows | Total rows | Coverage |\n|---:|---|---:|---:|---:|\n")
        for (year, source), (covered, total) in sorted(totals.items()):
            report.write(f"| {year} | `{source}` | {covered} | {total} | {covered/max(1,total):.2%} |\n")
        report.write("\n## Feature definitions\n\n")
        report.write("All flow values are known at the minute close (`known_at`), plus any source publication lag. A rolling window is valid when at least 80% of its clock minutes have verified source coverage. Covered minutes with no activity contribute zero; missing source periods remain NaN.\n\n")
        report.write("- `*_delta_{1,5,15,60}m`: sum of buy volume minus sell volume over the trailing window.\n")
        report.write("- `*_imbalance_{1,5,15,60}m`: trailing delta divided by total buy plus sell volume.\n")
        report.write("- `*_large100k_imbalance_1m`, `*_large1m_imbalance_1m`: buy minus sell notional for trades at or above 100k/1m USDT, divided by that bucket's total notional; NaN where the source lacks sided large-trade totals.\n")
        report.write("- `*_trade_intensity_z20d`: current trade count z-scored against the trailing 20×24×60 minute window (minimum 1×24×60 observations; population standard deviation).\n")
        report.write("- `spot_perp_delta_spread_*`, `spot_bybit_delta_spread_*`: difference between the two venues' trailing base-quantity deltas.\n")
        report.write("- `cum_delta_divergence_60m`: negative sign of spot 60-minute delta multiplied by the 60-bar primary-price return; positive values indicate price/delta disagreement.\n")
        report.write("- `ticks_ofi`, `ticks_size_imbalance`, `ticks_tick_count`, `ticks_mean_spread`, `ticks_max_spread`: same-minute Dukascopy tick aggregates.\n\n")
        report.write("## Feature columns\n\n")
        report.write("\n".join(f"- `{column}`" for column in feature_columns))
        report.write("\n")
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--start", required=True, help="YYYY-MM")
    parser.add_argument("--end", required=True, help="YYYY-MM, inclusive")
    args = parser.parse_args()
    first, last = pd.Period(args.start, "M"), pd.Period(args.end, "M")
    crypto = args.symbol in {"BTCUSDT", "ETHUSDT"}
    primary_root = BAR_ROOT / ("binance_spot" if crypto else "dukascopy") / args.symbol
    available = set()
    for source_path in primary_root.glob("*.parquet"):
        try:
            available.add(pd.Period(source_path.stem[:7], freq="M"))
        except ValueError:
            continue
    flow_root = (BAR_ROOT / "binance_flow" / "spot" if crypto else BAR_ROOT / "dukascopy_flow") / args.symbol
    flow_months = {pd.Period(p.stem[:7], freq="M") for p in flow_root.glob("*.parquet")}
    available &= flow_months
    months = [month for month in pd.period_range(first, last, freq="M") if month in available]
    if not months:
        raise FileNotFoundError(f"No primary month files for {args.symbol} in {first}..{last}")
    for month in months:
        path = build_month(args.symbol, str(month))
        print(f"DONE {args.symbol} {month} rows={len(pd.read_parquet(path, columns=['ts']))} path={path}", flush=True)
    print(f"REPORT {write_report(args.symbol)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
