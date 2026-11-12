"""Versioned Binance USDT-M perpetual executable labels for DEV research."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .labels import label_grid

SYMBOLS = ("BTCUSDT", "ETHUSDT")
TICK = {"BTCUSDT": 0.1, "ETHUSDT": 0.01}
TAKER_FEE = 0.0005
SLIPPAGE_PER_SIDE = 0.00005  # 0.5 bp of notional.
DEV_END = pd.Timestamp("2023-01-01", tz="UTC")


def executable_perp_bars(frame: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """Convert trade-price UM klines to conservative executable bid/ask bars.

    Binance archive klines normally contain no quote spread (bid == ask). If a
    future source contains a positive quote spread, retain its half-spread and
    add 0.5 bp slippage per side. Otherwise use one tick + 0.5 bp per side.
    """
    if symbol not in SYMBOLS:
        raise ValueError(symbol)
    result = frame.copy()
    for field in "ohlc":
        bid = pd.to_numeric(result[f"bid_{field}"], errors="coerce").to_numpy(float)
        ask = pd.to_numeric(result[f"ask_{field}"], errors="coerce").to_numpy(float)
        mid = (bid + ask) / 2
        observed = np.maximum((ask - bid) / 2, 0)
        fallback = TICK[symbol] + SLIPPAGE_PER_SIDE * mid
        half = np.where(observed > 0, observed + SLIPPAGE_PER_SIDE * mid, fallback)
        result[f"bid_{field}"] = mid - half
        result[f"ask_{field}"] = mid + half
    result["perp_half_spread"] = ((result.ask_c - result.bid_c) / 2).astype("float32")
    result["spread_modeled"] = (pd.to_numeric(frame.ask_c, errors="coerce") <=
                                 pd.to_numeric(frame.bid_c, errors="coerce")).astype(bool)
    result["venue"] = "binance_usdt_perp"
    return result


def funding_sums(labels: pd.DataFrame, funding: pd.DataFrame) -> np.ndarray:
    """Sum settlements strictly after entry through and including exit."""
    if funding.empty:
        return np.zeros(len(labels), dtype=float)
    times = pd.to_datetime(funding.ts, utc=True).astype("int64").to_numpy()
    rates = pd.to_numeric(funding.funding_rate, errors="raise").to_numpy(float)
    order = np.argsort(times, kind="stable"); times = times[order]; rates = rates[order]
    cumulative = np.concatenate(([0.0], np.cumsum(rates)))
    entry = pd.to_datetime(labels.entry_ts, utc=True).astype("int64").to_numpy()
    exit_ = pd.to_datetime(labels.exit_ts, utc=True).astype("int64").to_numpy()
    left = np.searchsorted(times, entry, side="right")
    right = np.searchsorted(times, exit_, side="right")
    return cumulative[right] - cumulative[left]


def apply_perp_costs(labels: pd.DataFrame, bars: pd.DataFrame,
                     funding: pd.DataFrame) -> pd.DataFrame:
    """Replace CFD financing with spread, taker fees, and actual funding."""
    result = labels.copy()
    lookup = bars.set_index("ts")
    entry = lookup.reindex(pd.to_datetime(result.entry_ts, utc=True))
    exit_ = lookup.reindex(pd.to_datetime(result.exit_ts, utc=True))
    entry_half = entry.perp_half_spread.to_numpy(float)
    exit_half = exit_.perp_half_spread.to_numpy(float)
    risk = pd.to_numeric(result.planned_risk, errors="coerce").to_numpy(float)
    executable_gross = pd.to_numeric(result.gross_R, errors="coerce").to_numpy(float)
    result["spread_R"] = (entry_half + exit_half) / risk
    result["fee_R"] = TAKER_FEE * (result.fill_price.abs() + result.exit_price.abs()) / risk
    result["funding_rate_sum"] = funding_sums(result, funding)
    # Positive funding is paid by longs and received by shorts.
    result["funding_R"] = result.side * result.funding_rate_sum * result.fill_price.abs() / risk
    result["executable_gross_R"] = executable_gross
    result["gross_R"] = executable_gross + result.spread_R
    result["cost_R"] = result.spread_R + result.fee_R + result.funding_R
    result["net_R"] = result.gross_R - result.cost_R
    result["venue"] = "binance_usdt_perp"
    result["cost_model"] = "perp_taker_5bp_each_plus_spread_plus_actual_funding_v1"
    return result


def _read_range(root: Path, symbol: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    months = pd.period_range(start.tz_localize(None).to_period("M"),
                             (end-pd.Timedelta(nanoseconds=1)).tz_localize(None).to_period("M"), freq="M")
    parts = [pd.read_parquet(root/symbol/f"{month}.parquet") for month in months
             if (root/symbol/f"{month}.parquet").exists()]
    if not parts:
        raise FileNotFoundError(f"No UM bars for {symbol} {start:%Y-%m}")
    frame = pd.concat(parts, ignore_index=True).sort_values("ts").drop_duplicates("ts")
    frame["ts"] = pd.to_datetime(frame.ts, utc=True)
    return frame[(frame.ts >= start) & (frame.ts < end)].reset_index(drop=True)


def _funding(root: Path, symbol: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    months = pd.period_range(start.tz_localize(None).to_period("M"),
                             (end-pd.Timedelta(nanoseconds=1)).tz_localize(None).to_period("M"), freq="M")
    paths = [root/symbol/f"{month}.parquet" for month in months if (root/symbol/f"{month}.parquet").exists()]
    if not paths:
        raise FileNotFoundError(f"No funding data for {symbol}")
    return pd.concat([pd.read_parquet(path, columns=["ts", "funding_rate"]) for path in paths], ignore_index=True)


def build_symbol(symbol: str, data_root: Path, output_root: Path,
                 start_year: int = 2020, end_year: int = 2022) -> list[dict]:
    if symbol not in SYMBOLS:
        raise ValueError(symbol)
    label_root = output_root/"labels"/symbol; feature_root = output_root/"features"/symbol
    label_root.mkdir(parents=True, exist_ok=True); feature_root.mkdir(parents=True, exist_ok=True)
    manifest = []
    for month in pd.period_range(f"{start_year}-01", f"{end_year}-12", freq="M"):
        start = pd.Timestamp(month.start_time, tz="UTC")
        end = min(pd.Timestamp(month.end_time, tz="UTC")+pd.Timedelta(nanoseconds=1), DEV_END)
        read_end = min(end+pd.Timedelta(days=8), DEV_END)
        raw = _read_range(data_root/"bars"/"binance_um", symbol, start, read_end)
        bars = executable_perp_bars(raw, symbol)
        base_features = pd.read_parquet(data_root/"features"/symbol/f"{month}.parquet",
                                        columns=["ts", "known_at", "1h_atr14", "1m_atr14"])
        atr_map = pd.Series(base_features["1h_atr14"].to_numpy(float),
                            index=pd.to_datetime(base_features.ts, utc=True))
        atr = pd.Series(pd.to_datetime(bars.ts, utc=True).map(atr_map).to_numpy(), index=bars.index)
        labels = label_grid(bars, atr, max_trading_days=5, instrument_class="crypto",
                            signal_start=start, signal_end=end, financing_per_night=0.0)
        labels["ts"] = bars.ts.iloc[labels.signal_index.to_numpy()].to_numpy()
        funding = _funding(data_root/"aux"/"funding", symbol, start, read_end)
        labels = apply_perp_costs(labels, bars, funding)
        labels = labels[pd.to_datetime(labels.exit_ts, utc=True) < DEV_END].reset_index(drop=True)
        label_path = label_root/f"{month}.parquet"; labels.to_parquet(label_path, index=False, compression="zstd")
        current = bars[(bars.ts >= start) & (bars.ts < end)].copy()
        spread = 2*current.perp_half_spread.to_numpy(float)
        overlay = base_features[["ts", "known_at"]].copy()
        by_ts = pd.Series(spread, index=current.ts).groupby(level=0).last()
        overlay["spread_atr"] = (pd.to_datetime(overlay.ts, utc=True).map(by_ts).to_numpy(float) /
                                 base_features["1m_atr14"].to_numpy(float)).astype("float32")
        overlay["spread_modeled"] = True
        overlay["venue"] = "binance_usdt_perp"
        feature_path = feature_root/f"{month}.parquet"; overlay.to_parquet(feature_path, index=False, compression="zstd")
        for kind, path in (("labels", label_path), ("features", feature_path)):
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            manifest.append({"path": path.relative_to(output_root).as_posix(), "kind": kind,
                             "size": path.stat().st_size, "sha256": digest})
    manifest_path = output_root/f"manifest_{symbol}_{start_year}_{end_year}.json"
    manifest_path.write_text(json.dumps({"symbol": symbol, "venue": "binance_usdt_perp",
        "start_year": start_year, "end_year": end_year, "files": manifest}, indent=2)+"\n")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", choices=SYMBOLS, required=True)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--output-root", type=Path, default=Path("data/venues/binance_perp"))
    parser.add_argument("--start-year", type=int, default=2020)
    parser.add_argument("--end-year", type=int, default=2022)
    args = parser.parse_args()
    build_symbol(args.symbol, args.data_root, args.output_root, args.start_year, args.end_year)


if __name__ == "__main__":
    main()
