"""Frozen D: practitioner ICT Silver Bullet and ablation ladder."""
from __future__ import annotations

from bisect import bisect_left
from datetime import datetime, time, timedelta
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd

from . import prep, primitives, strategy_c
from .execution import admit_stop, execution_bars, simulate_trade, tick_size

NAME = "D"
GRID = [
    dict(target=target, time_exit=minutes, entry=entry, L=3, M=3, N=10,
         displacement=False, session="all")
    for target, minutes, entry in product((1., 2., "dol"), (60, 120, 240),
                                           ("proximal", "ce"))
]
DEFAULT = dict(target=2., time_exit=120, entry="proximal", L=3, M=3, N=10,
               displacement=False, session="all")
for key, values in (("L", (2, 5)), ("M", (1,)), ("N", (5, 20)),
                    ("displacement", (True,)), ("session", ("rth",))):
    for value in values:
        GRID.append({**DEFAULT, key: value})

ABLATION = (
    ("fvg_only", {"require_sweep": False, "displacement": False,
                  "session": "all", "bias": "B0"}),
    ("plus_sweep", {"require_sweep": True, "displacement": False,
                    "session": "all", "bias": "B0"}),
    ("plus_displacement", {"require_sweep": True, "displacement": True,
                           "session": "all", "bias": "B0"}),
    ("plus_windows", {"require_sweep": True, "displacement": True,
                      "session": "windows", "bias": "B0"}),
    ("plus_B4", {"require_sweep": True, "displacement": True,
                 "session": "windows", "bias": "B4"}),
    ("hindsight_Binf", {"require_sweep": True, "displacement": True,
                        "session": "windows", "bias": "B∞"}),
)
VIDEO_COMPARISON = {
    "ablation_sharpe": {
        "fvg_only": 0.33, "plus_sweep": 0.69, "plus_displacement": 0.59,
        "plus_windows": 0.56, "plus_B4": 0.16, "hindsight_Binf": 1.02,
    },
    "win_rate": {"textbook_5m_NQ": 0.46, "textbook_1m_NQ": 0.37,
                 "practitioner_NQ": 0.42},
    "winning_months": {"textbook_5m": 0.43, "textbook_1m": 0.48,
                       "practitioner": 0.62},
}


def _inside_session(series, i: int, mode: str) -> bool:
    if i < 2 or len(set(series["days"][i - 2:i + 1])) != 1:
        return False
    minutes = series["minutes"][i - 2:i + 1]
    if mode == "all":
        return bool(((minutes < 960) | (minutes >= 1080)).all())
    if mode == "rth":
        return bool(((minutes >= 570) & (minutes < 960)).all())
    if mode == "windows":
        return any(bool(((minutes >= start) & (minutes < end)).all())
                   for start, end in strategy_c.WINDOWS)
    raise ValueError(f"unknown session {mode}")


def _candidate_orders(data, params: dict, diagnostics: dict):
    cache = data.__dict__.setdefault("_strategy_d_orders", {})
    cache_key = tuple((key, params.get(key)) for key in
                      ("L", "M", "N", "displacement", "session", "bias",
                       "require_sweep", "entry", "target"))
    if cache_key in cache:
        orders, counts = cache[cache_key]
        for key, value in counts.items():
            diagnostics[key] += value
        return orders
    initial_counts = dict(diagnostics)
    series = strategy_c._series(data, "1m", int(params["L"]), int(params["M"]))
    displaced = primitives.displacement(series["o"], series["h"], series["l"],
                                         series["c"], series["atr"], 1.)
    events = {side: [row for row in series["events"] if row["side"] == side]
              for side in (-1, 1)}
    known = {side: [row["known_i"] for row in rows] for side, rows in events.items()}
    require_sweep = bool(params.get("require_sweep", True))
    bias_name = params.get("bias", "B0")
    orders = []
    for zone in series["fvgs"]:
        i, side = zone.formed_i, zone.side
        if i < 2 or series["days"][i].year < 2019 or not _inside_session(series, i, params["session"]):
            continue
        if params["displacement"]:
            if not displaced[i - 1] or np.sign(series["c"][i - 1] - series["o"][i - 1]) != side:
                continue
        event = None
        if require_sweep:
            position = bisect_left(known[side], i) - 1
            if position < 0:
                continue
            candidate = events[side][position]
            if i - candidate["known_i"] > int(params["N"]):
                continue
            event = candidate
        minute_i = int(series["minute_index"][i])
        entry = strategy_c._limit_price(zone, params["entry"])
        direction = strategy_c._bias_for(
            data, bias_name, series["days"][i], minute_i, entry
        )
        if bias_name != "B0" and direction != side:
            continue
        anchor = (event["extreme"] if event is not None else
                  (series["l"][i - 2] if side > 0 else series["h"][i - 2]))
        stop = float(anchor - side * tick_size(data.market))
        risk = side * (entry - stop)
        if risk <= 0:
            diagnostics["entry_beyond_stop_skips"] += 1
            continue
        target_r = params["target"]
        if target_r == "dol":
            target = strategy_c._target(data, series, side, i, entry, risk,
                                        series["days"][i], 0.)
            if target is None:
                diagnostics["missing_target_skips"] += 1
                continue
            target_r = abs(target - entry) / risk
        invalid = np.flatnonzero(
            series["c"][i + 1:min(len(series["c"]), i + 61)] < zone.bottom
            if side > 0 else
            series["c"][i + 1:min(len(series["c"]), i + 61)] > zone.top
        )
        expiry = min(len(data.ts) - 1, i + 60)
        if len(invalid):
            expiry = min(expiry, i + 1 + int(invalid[0]))
        # No fills are admitted during the daily 16:00-18:00 maintenance gap.
        local_after = data.local_minutes[i + 1:expiry + 1]
        prohibited = np.flatnonzero((local_after >= 960) & (local_after < 1080))
        if len(prohibited):
            expiry = min(expiry, i + int(prohibited[0]))
        orders.append({"day": series["days"][i], "side": side, "entry_i": i + 1,
                       "limit": entry, "stop": stop, "risk": risk,
                       "target_r": float(target_r), "expiry_i": expiry,
                       "signal_i": i})
    orders.sort(key=lambda row: row["signal_i"])
    cache[cache_key] = (
        orders,
        {key: diagnostics[key] - initial_counts.get(key, 0) for key in diagnostics},
    )
    return orders


def _first_limit_fill(bars, order, fill_model: str) -> int | None:
    side, price = order["side"], order["limit"]
    threshold = price if fill_model == "touch" else price - side * bars.tick
    start, stop = order["entry_i"], min(len(bars.ts), order["expiry_i"] + 1)
    touched = (bars.ask_l[start:stop] <= threshold if side > 0
               else bars.bid_h[start:stop] >= threshold)
    found = np.flatnonzero(touched)
    return None if not len(found) else start + int(found[0])


def _force_flat_after(data, index: int) -> int:
    local = data.ny[index]
    day = local.date()
    if data.local_minutes[index] >= 960:
        day += timedelta(days=1)
    while day.weekday() >= 5:
        day += timedelta(days=1)
    stamp = pd.Timestamp(datetime.combine(day, time(16)), tz=prep.NY).tz_convert("UTC")
    return min(len(data.ts) - 1, int(data.ts.searchsorted(stamp)))


def simulate(data, params: dict | None = None, *, model: str = "futures", multiplier: float = 1.,
             fill_model: str = "trade_through", signal_delay: int = 0,
             allow_holdout: bool = False, selection_path: Path | None = None):
    params = dict(DEFAULT if params is None else params)
    diagnostics = {"minimum_stop_skips": 0, "entry_beyond_stop_skips": 0,
                   "missing_target_skips": 0, "signals": 0, "unfilled": 0,
                   "unresolved_at_end": 0}
    orders = _candidate_orders(data, params, diagnostics)
    bars = execution_bars(data, data.market, model, multiplier)
    trades = []
    next_free = -1
    for position, raw in enumerate(orders):
        order = dict(raw)
        order["entry_i"] += int(signal_delay)
        if order["entry_i"] <= next_free or order["entry_i"] >= len(data.ts):
            continue
        # A newer setup replaces an older still-pending limit order.
        if position + 1 < len(orders):
            replacement_i = orders[position + 1]["entry_i"] + int(signal_delay)
            order["expiry_i"] = min(order["expiry_i"], replacement_i - 1)
        if order["expiry_i"] < order["entry_i"]:
            continue
        fill_i = _first_limit_fill(bars, order, fill_model)
        diagnostics["signals"] += 1
        if fill_i is None:
            diagnostics["unfilled"] += 1
            continue
        if not admit_stop(data.market, order["risk"], data.atr15_at[fill_i]):
            diagnostics["minimum_stop_skips"] += 1
            continue
        time_deadline = min(len(data.ts) - 1, fill_i + int(params["time_exit"]))
        deadline = min(time_deadline, _force_flat_after(data, fill_i))
        trade = simulate_trade(
            bars, market=data.market, strategy=NAME, params=params,
            side=order["side"], entry_i=fill_i, stop=order["stop"],
            target_r=order["target_r"], risk_points=order["risk"],
            deadline_i=deadline, entry_type="limit", limit_price=order["limit"],
            expiry_i=fill_i, fill_model=fill_model,
            allow_holdout=allow_holdout, selection_path=selection_path,
        )
        if trade is None:
            diagnostics["unresolved_at_end"] += 1
            continue
        next_free = trade["_exit_i"]
        trade.update({"_signal_i": order["signal_i"],
                      "entry_hour": int(data.ny[trade["_entry_i"]].hour)})
        trades.append(trade)
    return trades, diagnostics


def extra_runs(data):
    """Ablation ladder and the frozen 1m/5m textbook benchmarks."""
    output = {"ablation": {}, "textbook_benchmarks": {}}
    for label, override in ABLATION:
        params = {**DEFAULT, **override}
        output["ablation"][label] = (params, *simulate(data, params))
    textbook = {**strategy_c.DEFAULT, "windows": "all", "exit": "window"}
    for timeframe in ("1m", "5m"):
        params = {**textbook, "timeframe": timeframe}
        output["textbook_benchmarks"][timeframe] = (
            params, *strategy_c.simulate(data, params)
        )
    return output
