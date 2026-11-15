"""Shared market/limit/stop execution with frozen batch-2 costs."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd


@dataclass
class ExecutionBars:
    ts: pd.DatetimeIndex
    mid_o: np.ndarray
    mid_h: np.ndarray
    mid_l: np.ndarray
    mid_c: np.ndarray
    bid_o: np.ndarray
    bid_h: np.ndarray
    bid_l: np.ndarray
    bid_c: np.ndarray
    ask_o: np.ndarray
    ask_h: np.ndarray
    ask_l: np.ndarray
    ask_c: np.ndarray
    atr15: np.ndarray
    model: str = "futures"
    market: str = "USATECHIDXUSD"
    multiplier: float = 1.
    tick: float = .25
    slippage: float = .25
    commission: float = .5


def execution_bars(data, market: str, model: str = "futures", multiplier: float = 1.) -> ExecutionBars:
    """Adapt prepared raw mid/bid/ask arrays to a named quoted-fill model."""
    if model not in {"futures", "dukascopy", "capital"}:
        raise ValueError("model must be futures, dukascopy, or capital")
    if multiplier not in (1., 1.5, 2.):
        raise ValueError("cost multiplier must be 1, 1.5, or 2")
    tick = tick_size(market)
    mid = {field: getattr(data, f"mid_{field}") for field in "ohlc"}
    if model == "dukascopy":
        raw = data.bars
        bid = {field: raw[f"bid_{field}"].to_numpy(float) for field in "ohlc"}
        ask = {field: raw[f"ask_{field}"].to_numpy(float) for field in "ohlc"}
        for field in "ohlc":
            bid[field] = mid[field] + (bid[field] - mid[field]) * multiplier
            ask[field] = mid[field] + (ask[field] - mid[field]) * multiplier
    else:
        width = tick if model == "futures" else (1.8 if market == "USATECHIDXUSD" else .5)
        half = width * multiplier / 2
        bid = {field: value - half for field, value in mid.items()}
        ask = {field: value + half for field, value in mid.items()}
    commission = commission_points(market) * multiplier
    slip = tick * multiplier
    return ExecutionBars(data.ts, *[mid[f] for f in "ohlc"],
                         *[bid[f] for f in "ohlc"], *[ask[f] for f in "ohlc"],
                         data.atr15_at, model, market, multiplier, tick, slip, commission)


def tick_size(market: str) -> float:
    return .10 if market == "XAUUSD" else .25


def commission_points(market: str) -> float:
    return .5 if market == "USATECHIDXUSD" else .2 if market == "USA500IDXUSD" else 0.


@dataclass
class PositionState:
    """Minimal reusable one-position-at-a-time guard."""
    key: object | None = None

    def open(self, key) -> bool:
        if self.key is not None:
            return False
        self.key = key
        return True

    def close(self, key=None) -> None:
        if key is None or self.key == key:
            self.key = None


def minimum_stop(market: str, atr15_at_entry: float) -> float:
    floor = 4. if market == "USATECHIDXUSD" else 1. if market == "USA500IDXUSD" else 0.
    return max(floor, .25 * atr15_at_entry) if np.isfinite(atr15_at_entry) else floor


def admit_stop(market: str, risk_points: float, atr15_at_entry: float) -> bool:
    return np.isfinite(risk_points) and risk_points >= minimum_stop(market, atr15_at_entry)


def simulate_trade(bars: ExecutionBars, *, market: str, strategy: str, params: dict,
                   side: int, entry_i: int, stop: float, target_r: float,
                   risk_points: float, deadline_i: int, entry_type: str = "market",
                   trigger: float | None = None, limit_price: float | None = None,
                   expiry_i: int | None = None, fill_model: str = "trade_through",
                   signal_delay: int = 0, allow_holdout: bool = False,
                   selection_path: Path | None = None) -> dict | None:
    """Replay one order. Entry and exits are causal; ambiguous stop+TP loses."""
    if side not in (-1, 1) or entry_type not in {"market", "limit", "stop"}:
        raise ValueError("invalid side or entry type")
    if fill_model not in {"trade_through", "touch"}:
        raise ValueError("fill model must be trade_through or touch")
    if risk_points <= 0 or not np.isfinite(risk_points):
        raise ValueError("risk_points must be positive")
    if signal_delay:
        entry_i += int(signal_delay)
    n = len(bars.ts)
    if entry_i >= n:
        return None
    planned_mid = float(limit_price if entry_type == "limit" else bars.mid_o[entry_i])
    target = planned_mid + side * target_r * risk_points
    slip = bars.slippage
    fill_i = None
    entry_price = entry_cost = 0.
    entry_mid = planned_mid
    last = min(n - 1, expiry_i if expiry_i is not None else deadline_i)
    for i in range(entry_i, last + 1):
        if entry_type == "market":
            fill_i = i
            if side > 0:
                entry_price = bars.ask_o[i] + slip
            else:
                entry_price = bars.bid_o[i] - slip
            entry_mid = float(bars.mid_o[i])
            entry_cost = side * (entry_price - entry_mid)
            break
        if entry_type == "stop":
            if trigger is None:
                raise ValueError("stop entries require a trigger")
            touched = bars.ask_h[i] >= trigger if side > 0 else bars.bid_l[i] <= trigger
            if touched:
                fill_i = i
                entry_price = (max(bars.ask_o[i], trigger) + slip if side > 0
                               else min(bars.bid_o[i], trigger) - slip)
                entry_mid = float(bars.mid_o[i])
                entry_cost = side * (entry_price - entry_mid)
                break
        else:
            if limit_price is None:
                raise ValueError("limit entries require a price")
            tick = bars.tick
            threshold = limit_price if fill_model == "touch" else limit_price - side * tick
            touched = bars.ask_l[i] <= threshold if side > 0 else bars.bid_h[i] >= threshold
            if touched:
                fill_i = i
                entry_price = float(limit_price)
                entry_mid = float(limit_price)
                entry_cost = 0.
                break
    if fill_i is None:
        return None
    # TP distance is always based on the actual price used to define planned R.
    target = entry_mid + side * target_r * risk_points
    exit_i = None
    exit_price = exit_mid = None
    reason = None
    exit_cost = 0.
    for i in range(fill_i, min(n, deadline_i + 1)):
        stop_hit = bars.bid_l[i] <= stop if side > 0 else bars.ask_h[i] >= stop
        tp_threshold = target + side * (bars.tick if fill_model == "trade_through" else 0.)
        tp_hit = (bars.bid_h[i] >= tp_threshold if side > 0 else bars.ask_l[i] <= tp_threshold)
        if entry_type == "limit" and i == fill_i:
            tp_hit = False  # limit-fill bar checks the stop only
        if stop_hit:
            gap = bars.bid_o[i] <= stop if side > 0 else bars.ask_o[i] >= stop
            if side > 0:
                base = min(stop, bars.bid_o[i]) if gap else stop
                exit_price = float(base - slip)
            else:
                base = max(stop, bars.ask_o[i]) if gap else stop
                exit_price = float(base + slip)
            exit_mid = float(bars.mid_o[i]) if gap else float(stop)
            exit_cost = -side * (exit_price - exit_mid)
            reason = "stop"
        elif tp_hit:
            exit_price = float(target)
            exit_mid = float(target)
            reason = "target"
        elif i >= deadline_i:
            exit_mid = float(bars.mid_o[i])
            exit_price = float((bars.ask_o[i] + slip) if side < 0 else (bars.bid_o[i] - slip))
            exit_cost = -side * (exit_price - exit_mid)
            reason = "time"
        if reason:
            exit_i = i
            break
    if exit_i is None:
        return None
    commission = bars.commission
    gross_r = side * (float(exit_mid) - entry_mid) / risk_points
    net_r = gross_r - (entry_cost + exit_cost + commission) / risk_points
    cost_r = gross_r - net_r
    entry_ts = pd.Timestamp(bars.ts[fill_i])
    exit_ts = pd.Timestamp(bars.ts[exit_i])
    if entry_ts >= pd.Timestamp("2023-01-01", tz="UTC"):
        if not allow_holdout:
            raise PermissionError("holdout numbers require the explicit one-time holdout flag")
        if selection_path is None or not Path(selection_path).is_file():
            raise FileNotFoundError("holdout numbers require an existing frozen dev selection file")
    return {
        "market": market, "strategy": strategy, "params": dict(params),
        "period": "dev" if entry_ts < pd.Timestamp("2023-01-01", tz="UTC") else "holdout",
        "side": int(side), "entry_ts": entry_ts.isoformat(), "exit_ts": exit_ts.isoformat(),
        "entry_price": float(entry_price), "exit_price": float(exit_price),
        "entry_mid": entry_mid, "exit_mid": float(exit_mid), "risk_points": float(risk_points),
        "gross_R": float(gross_r), "net_R": float(net_r),
        "net_R_cost15": float(gross_r - cost_r * 1.5),
        "net_R_cost2": float(gross_r - cost_r * 2.),
        "cost_R": float(cost_r), "fill_model": bars.model, "fill_variant": fill_model,
        "cost_multiplier": bars.multiplier, "exit_reason": reason,
        "_entry_i": fill_i, "_exit_i": exit_i, "_deadline_i": deadline_i,
        "_stop": float(stop), "_target": float(target), "_entry_cost": float(entry_cost),
        "_exit_cost": float(exit_cost), "_commission": float(commission),
    }


def replay_fixed_entry(bars: ExecutionBars, trade: dict, side: int, *, fill_model: str = "trade_through") -> dict:
    """Recompute exits from a fixed real fill/time; same-side must reproduce exactly."""
    entry_i = int(trade["_entry_i"])
    entry_mid = float(trade["entry_mid"])
    risk = float(trade["risk_points"])
    stop_distance = abs(float(trade["entry_price"]) - float(trade["_stop"]))
    target_distance = abs(float(trade["_target"]) - float(trade["entry_mid"]))
    stop = float(trade["entry_price"]) - side * stop_distance
    target = float(trade["entry_mid"]) + side * target_distance
    entry_cost = float(trade["_entry_cost"]) if side == trade["side"] else _entry_cost_for(bars, entry_i, side, float(trade["entry_price"]))
    for i in range(entry_i, min(len(bars.ts), int(trade["_deadline_i"]) + 1)):
        stop_hit = bars.bid_l[i] <= stop if side > 0 else bars.ask_h[i] >= stop
        tp_hit = bars.bid_h[i] >= target + (bars.tick if fill_model == "trade_through" else 0.) if side > 0 else bars.ask_l[i] <= target - (bars.tick if fill_model == "trade_through" else 0.)
        if stop_hit:
            gap = bars.bid_o[i] <= stop if side > 0 else bars.ask_o[i] >= stop
            exit_price = (min(stop, bars.bid_o[i]) - bars.slippage if side > 0 else
                          max(stop, bars.ask_o[i]) + bars.slippage)
            exit_mid = float(bars.mid_o[i] if gap else stop)
            exit_cost = -side * (exit_price - exit_mid)
            reason = "stop"
        elif tp_hit:
            exit_price = target
            exit_mid = target
            exit_cost, reason = 0., "target"
        elif i >= int(trade["_deadline_i"]):
            exit_mid = float(bars.mid_o[i])
            exit_price = float(bars.bid_o[i] - bars.slippage if side > 0 else bars.ask_o[i] + bars.slippage)
            exit_cost = -side * (exit_price - exit_mid)
            reason = "time"
        else:
            continue
        gross_r = side * (exit_mid - entry_mid) / risk
        net_r = gross_r - (entry_cost + exit_cost + bars.commission) / risk
        return {"net_R": float(net_r), "gross_R": float(gross_r),
                "exit_ts": pd.Timestamp(bars.ts[i]).isoformat(), "exit_reason": reason}
    return {"net_R": np.nan, "gross_R": np.nan, "exit_ts": None, "exit_reason": "unresolved"}


def _entry_cost_for(bars: ExecutionBars, index: int, side: int, entry_price: float) -> float:
    mid = float(bars.mid_o[index])
    return abs(entry_price - mid)
