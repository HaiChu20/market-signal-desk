"""Pure computations for TikTok batch-2 Strategy E."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from msd.research import swing_stage1 as swing
from msd.research.tiktok import common

RANGE_N = (4, 8, 24, 48, 120)
STOP_K = (1, 2, 3)
SQRT_C = (0.5, 0.75, 1.0, 1.25)
SQRT_N = (8, 24, 48)
E2_C = (0.75, 1.0)
E2_N = (24, 48, 120)
E2_TP = (1.0, 2.0, 3.0)
E2_SETUPS = ("S1", "S2")
E2_MARKETS = ("USATECHIDXUSD", "XAUUSD")
DEV_START = pd.Timestamp("2019-01-01", tz="UTC")
HOLDOUT_START = pd.Timestamp("2023-01-01", tz="UTC")


def completed_hourly(bars_1m: pd.DataFrame) -> pd.DataFrame:
    """Build strict completed 1h midpoint bars and causal ATR(14)."""
    result = common.resample_closed_bars(bars_1m, 60)
    for field in "ohlc":
        result[field] = (
            result[f"bid_{field}"].to_numpy(float)
            + result[f"ask_{field}"].to_numpy(float)
        ) / 2
    previous = result.c.shift(1)
    true_range = pd.concat(
        [
            result.h - result.l,
            (result.h - previous).abs(),
            (result.l - previous).abs(),
        ],
        axis=1,
    ).max(axis=1)
    result["atr14"] = true_range.rolling(14, min_periods=14).mean()
    result["known_at"] = result.ts
    return result[["known_at", "o", "h", "l", "c", "atr14"]]


def _metric(values: np.ndarray) -> dict:
    finite = np.asarray(values, dtype=float)
    finite = finite[np.isfinite(finite)]
    return {
        "samples": int(len(finite)),
        "median": float(np.median(finite)) if len(finite) else None,
        "mean": float(np.mean(finite)) if len(finite) else None,
    }


def _range_rows(hourly: pd.DataFrame, mask: np.ndarray) -> list[dict]:
    close = hourly.c.to_numpy(float)
    high = hourly.h.to_numpy(float)
    low = hourly.l.to_numpy(float)
    atr = hourly.atr14.to_numpy(float)
    rows = []
    for n in RANGE_N:
        size = len(hourly) - n
        eligible = mask[:size] & np.isfinite(atr[:size])
        if size <= 0 or not eligible.any():
            continue
        future_high = np.lib.stride_tricks.sliding_window_view(high[1:], n).max(axis=1)
        future_low = np.lib.stride_tricks.sliding_window_view(low[1:], n).min(axis=1)
        close_move = np.abs(close[n:] - close[:size])
        path_range = future_high - future_low
        formula = atr[:size] * np.sqrt(n)
        rows.append(
            {
                "N": n,
                "close_move": _metric(close_move[eligible]),
                "path_range": _metric(path_range[eligible]),
                "atr_sqrt_N": _metric(formula[eligible]),
            }
        )
    return rows


def range_statistics(
    hourly: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp
) -> dict:
    """Range checks overall, by entry year, and by period-local ATR tercile."""
    known = pd.DatetimeIndex(hourly.known_at)
    base = (known >= start) & (known < end) & hourly.atr14.notna().to_numpy()
    years = known.year
    finite_atr = hourly.loc[base, "atr14"]
    if len(finite_atr):
        q1, q2 = finite_atr.quantile([1 / 3, 2 / 3]).to_numpy(float)
        atr = hourly.atr14.to_numpy(float)
        terciles = np.where(atr <= q1, "low", np.where(atr <= q2, "mid", "high"))
    else:
        q1 = q2 = np.nan
        terciles = np.full(len(hourly), "none", dtype=object)
    return {
        "overall": _range_rows(hourly, base),
        "by_year": {
            str(year): _range_rows(hourly, base & (years == year))
            for year in sorted(set(years[base]))
        },
        "atr_tercile_edges": [float(q1), float(q2)] if np.isfinite(q1) else [],
        "by_atr_tercile": {
            label: _range_rows(hourly, base & (terciles == label))
            for label in ("low", "mid", "high")
        },
    }


def _minute_mid_arrays(bars: pd.DataFrame) -> dict[str, np.ndarray]:
    return {
        "ts": pd.DatetimeIndex(pd.to_datetime(bars.ts, utc=True)).asi8,
        "h": (bars.bid_h.to_numpy(float) + bars.ask_h.to_numpy(float)) / 2,
        "l": (bars.bid_l.to_numpy(float) + bars.ask_l.to_numpy(float)) / 2,
    }


def path_hit_and_returns(
    minute: dict[str, np.ndarray], start_i: int, end_i: int, entry: float,
    stop: float, side: int,
) -> tuple[bool, bool, bool]:
    """Return hit, return during original window, and return within 24h of hit."""
    trigger = minute["l"] if side > 0 else minute["h"]
    hits = np.flatnonzero(
        trigger[start_i:end_i] <= stop
        if side > 0
        else trigger[start_i:end_i] >= stop
    )
    if not len(hits):
        return False, False, False
    hit_i = start_i + int(hits[0])
    after = hit_i + 1
    return_side = minute["h"] if side > 0 else minute["l"]
    rest = bool(
        np.any(return_side[after:end_i] >= entry)
        if side > 0
        else np.any(return_side[after:end_i] <= entry)
    )
    after_end_ns = minute["ts"][hit_i] + pd.Timedelta(hours=24).value
    after_end = int(np.searchsorted(minute["ts"], after_end_ns, side="right"))
    within_24h = bool(
        np.any(return_side[after:after_end] >= entry)
        if side > 0
        else np.any(return_side[after:after_end] <= entry)
    )
    return True, rest, within_24h


def stop_statistics(
    bars: pd.DataFrame, hourly: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp
) -> tuple[list[dict], list[dict]]:
    """Compute 24-bar k-ATR and sqrt-N stop probabilities from minute paths."""
    minute = _minute_mid_arrays(bars)
    known_ns = pd.DatetimeIndex(hourly.known_at).asi8
    atr = hourly.atr14.to_numpy(float)
    entry = hourly.c.to_numpy(float)
    period = (
        (known_ns >= start.value)
        & (known_ns < end.value)
        & np.isfinite(atr)
    )
    hit_counts = {(side, k): [0, 0, 0, 0] for side in (-1, 1) for k in STOP_K}
    sqrt_counts = {
        (side, c, n): [0, 0] for side in (-1, 1) for c in SQRT_C for n in SQRT_N
    }
    for i in np.flatnonzero(period):
        start_i = int(np.searchsorted(minute["ts"], known_ns[i]))
        end_by_n = {
            n: int(np.searchsorted(minute["ts"], known_ns[i + n]))
            for n in set(SQRT_N) | {24}
            if i + n < len(hourly)
        }
        for side in (-1, 1):
            if 24 in end_by_n:
                for k in STOP_K:
                    counts = hit_counts[(side, k)]
                    counts[0] += 1
                    hit, rest, after = path_hit_and_returns(
                        minute, start_i, end_by_n[24], entry[i],
                        entry[i] - side * k * atr[i], side,
                    )
                    counts[1] += int(hit)
                    counts[2] += int(rest)
                    counts[3] += int(after)
            trigger = minute["l"] if side > 0 else minute["h"]
            for n in SQRT_N:
                if n not in end_by_n:
                    continue
                path = trigger[start_i:end_by_n[n]]
                for c in SQRT_C:
                    stop = entry[i] - side * c * atr[i] * np.sqrt(n)
                    hit = bool(np.any(path <= stop) if side > 0 else np.any(path >= stop))
                    sqrt_counts[(side, c, n)][0] += 1
                    sqrt_counts[(side, c, n)][1] += int(hit)
    hit_rows = []
    for (side, k), (samples, hits, rest, after) in hit_counts.items():
        hit_rows.append(
            {
                "side": "long" if side > 0 else "short",
                "k": k,
                "samples": samples,
                "hit_probability": hits / samples if samples else None,
                "hits": hits,
                "return_rest_of_window_given_hit": rest / hits if hits else None,
                "return_within_24h_after_hit_given_hit": after / hits if hits else None,
            }
        )
    sqrt_rows = [
        {
            "side": "long" if side > 0 else "short",
            "c": c,
            "N": n,
            "samples": counts[0],
            "stopped_probability": counts[1] / counts[0] if counts[0] else None,
        }
        for (side, c, n), counts in sqrt_counts.items()
    ]
    return hit_rows, sqrt_rows


def e1_market_period(
    bars: pd.DataFrame, market: str, period: str, start: pd.Timestamp, end: pd.Timestamp
) -> dict:
    hourly = completed_hourly(bars)
    stop_hit, sqrt_rule = stop_statistics(bars, hourly, start, end)
    return {
        "market": market,
        "period": period,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "hourly_samples_with_atr": int(
            ((hourly.known_at >= start) & (hourly.known_at < end) & hourly.atr14.notna()).sum()
        ),
        "range": range_statistics(hourly, start, end),
        "stop_hit_24_bars": stop_hit,
        "sqrt_rule": sqrt_rule,
    }


def original_trades(
    bars: pd.DataFrame, market: str, period: swing.Period, setups: tuple[str, ...] = E2_SETUPS
) -> tuple[list[dict], dict]:
    """Call the frozen swing implementation verbatim for the original rule."""
    return swing.evaluate_market(
        bars, market, primary_only=True, period=period, setups=setups
    )


def _hourly_at_signal(hourly: pd.DataFrame, signal_end: pd.Timestamp) -> float:
    times = pd.DatetimeIndex(hourly.known_at).asi8
    position = int(np.searchsorted(times, signal_end.value, side="right") - 1)
    return float(hourly.atr14.iloc[position]) if position >= 0 else np.nan


def replay_e2_config(
    bars: pd.DataFrame, market: str, setup: str, c: float, n: int, tp: float,
    *, period: swing.Period,
) -> tuple[list[dict], dict]:
    """Replay one sqrt-stop cell with the frozen swing entry/exit/cost mechanics."""
    ts = pd.DatetimeIndex(pd.to_datetime(bars.ts, utc=True))
    daily = swing.daily_bars(bars, period=period)
    first_year = int(ts[0].tz_convert(swing.NY).year)
    signals = swing.signals(daily, first_year)
    hourly = completed_hourly(bars)
    prices = np.column_stack(
        [(bars[f"bid_{field}"].to_numpy(float) + bars[f"ask_{field}"].to_numpy(float)) / 2
         for field in "ohlc"]
    )
    mask = swing.globex(ts)
    sessions = swing.ny_day_end(ts)
    session_closes = pd.DatetimeIndex(sessions[mask]).unique().sort_values()
    session_first = np.searchsorted(sessions.asi8, session_closes.asi8, side="right")
    contract = (swing.TRADED | swing.EVIDENCE)[market]
    rows = []
    drops = {"unresolved_at_cutoff": 0, "missing_entry": 0, "missing_hourly_atr": 0}
    next_free = -1
    for signal in signals.itertuples(index=False):
        side = int(getattr(signal, setup))
        if side == 0:
            continue
        entry_i = swing.entry_index(ts, signal.end)
        if entry_i is None:
            drops["missing_entry"] += 1
            continue
        if entry_i <= next_free or not mask[entry_i]:
            continue
        atr1h = _hourly_at_signal(hourly, signal.end)
        if not np.isfinite(atr1h) or atr1h <= 0:
            drops["missing_hourly_atr"] += 1
            continue
        entry = float(prices[entry_i, 0])
        risk = float(c * atr1h * np.sqrt(n))
        stop = entry - side * risk
        target = entry + side * risk * tp
        session_number = int(session_closes.searchsorted(sessions[entry_i]))
        cap_number = session_number + 29
        cap = int(session_first[cap_number]) if cap_number < len(session_first) else len(ts)
        while cap < len(ts) and not mask[cap]:
            cap += 1
        outcome = swing.exit_trade(ts, prices, mask, entry_i, side, stop, target, cap)
        if outcome is None or (period.end is not None and ts[outcome[0]] >= period.end):
            drops["unresolved_at_cutoff"] += 1
            next_free = len(ts)
            continue
        exit_i, fill, reason = outcome
        next_free = exit_i
        if period.score_start is not None and ts[entry_i] < period.score_start:
            continue
        days = (ts[exit_i] - ts[entry_i]).total_seconds() / 86400
        gross = side * (fill - entry) / risk
        fee = swing.cost_r(contract, market, entry, risk, side, days, reason)
        fee15 = swing.cost_r(contract, market, entry, risk, side, days, reason, multiplier=1.5)
        rows.append(
            {
                "market": market,
                "setup": setup,
                "c": c,
                "N": n,
                "tp_R": tp,
                "signal_end": signal.end.isoformat(),
                "entry_ts": ts[entry_i].isoformat(),
                "exit_ts": ts[exit_i].isoformat(),
                "year": int(ts[entry_i].year),
                "exit": reason,
                "net_R": float(gross - fee),
                "net_R_cost15": float(gross - fee15),
                "risk_points": risk,
            }
        )
    return rows, drops


def summarise_e2(
    rows: list[dict], original_median: float, *, include_years: bool = True
) -> dict:
    values = np.asarray([row["net_R"] for row in rows], dtype=float)
    values15 = np.asarray([row["net_R_cost15"] for row in rows], dtype=float)
    sd = values.std(ddof=1) if len(values) > 1 else 0
    median = float(np.median([row["risk_points"] for row in rows])) if rows else None
    years = sorted({row["year"] for row in rows})
    result = {
        "trades": len(rows),
        "net_avg_R": float(values.mean()) if len(values) else None,
        "t": float(values.mean() / sd * np.sqrt(len(values))) if sd > 0 else None,
        "win_rate": float(np.mean(values > 0)) if len(values) else None,
        "net_avg_R_cost15": float(values15.mean()) if len(values15) else None,
        "median_stop_points": median,
        "original_median_stop_points": original_median,
        "median_stop_vs_original": median / original_median if median and original_median else None,
    }
    result["by_year"] = (
        {
            str(year): summarise_e2(
                [row for row in rows if row["year"] == year],
                original_median,
                include_years=False,
            )
            for year in years
        }
        if include_years
        else {}
    )
    return result


def _original_report_rows(rows: list[dict]) -> list[dict]:
    return [
        {
            **row,
            "risk_points": row["risk"],
            "net_R_cost15": (row["net_R"] + row["double_cost_R"]) / 2,
        }
        for row in rows
    ]


def e2_market_dev(bars: pd.DataFrame, market: str, period: swing.Period) -> dict:
    original, original_drops = original_trades(bars, market, period)
    output = {"market": market, "original_drops": original_drops, "setups": {}}
    for setup in E2_SETUPS:
        baseline = _original_report_rows([row for row in original if row["setup"] == setup])
        original_median = float(np.median([row["risk_points"] for row in baseline])) if baseline else np.nan
        cells = []
        for c in E2_C:
            for n in E2_N:
                for tp in E2_TP:
                    rows, drops = replay_e2_config(
                        bars, market, setup, c, n, tp, period=period
                    )
                    cells.append(
                        {
                            "params": {"c": c, "N": n, "tp_R": tp},
                            "metrics": summarise_e2(rows, original_median),
                            "drops": drops,
                        }
                    )
        output["setups"][setup] = {
            "original": summarise_e2(baseline, original_median),
            "cells": cells,
        }
    return output


def choose_e2(market_results: dict[str, dict]) -> dict:
    selection = {}
    for setup in E2_SETUPS:
        choices = []
        for c in E2_C:
            for n in E2_N:
                for tp in E2_TP:
                    params = {"c": c, "N": n, "tp_R": tp}
                    weighted_sum = 0.0
                    trades = 0
                    for market in E2_MARKETS:
                        cell = next(
                            row for row in market_results[market]["setups"][setup]["cells"]
                            if row["params"] == params
                        )
                        count = cell["metrics"]["trades"]
                        value = cell["metrics"]["net_avg_R"]
                        if value is not None:
                            weighted_sum += value * count
                            trades += count
                    choices.append((weighted_sum / trades if trades else -np.inf, params, trades))
        score, params, trades = max(choices, key=lambda item: item[0])
        selection[setup] = {"params": params, "pooled_net_avg_R": float(score), "trades": trades}
    return selection


def require_e2_holdout(
    run_flag: bool, selection_path: Path, output_json: Path
) -> dict:
    if not run_flag:
        raise PermissionError("E2 holdout requires --run-e2-holdout-once")
    if not selection_path.exists():
        raise FileNotFoundError("E2 DEV selection file is required before holdout")
    if output_json.exists():
        raise FileExistsError("E2 holdout output already exists; refusing rerun")
    import json

    selection = json.loads(selection_path.read_text())
    if set(selection.get("selection", {})) != set(E2_SETUPS):
        raise ValueError("invalid E2 selection file")
    return selection
