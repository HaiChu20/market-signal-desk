"""Frozen B-alt: first 5-minute close outside a 30-minute opening range."""
from __future__ import annotations

from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd
from datetime import datetime, time
from zoneinfo import ZoneInfo

from .execution import admit_stop, execution_bars, simulate_trade

NAME = "B-alt"
GRID = [dict(target_r=target, stop_mode=stop)
        for target, stop in product((1.5, 2., 3.), ("opposite", "mid"))]
DEFAULT = {"target_r": 2., "stop_mode": "opposite"}


def _signal(data, row, params, diagnostics, five):
    day = row.day
    if not row.complete:
        return None
    day_idx = np.arange(int(row.first_i), int(row.last_i))
    minute = data.local_minutes[day_idx]
    opening = day_idx[minute < 600]
    if len(opening) != 30:
        diagnostics["bad_opening_range"] += 1
        return None
    hi, lo = float(data.mid_h[opening].max()), float(data.mid_l[opening].min())
    five_ts, fivemin, mid5_close, mid5_high, mid5_low = five
    start = pd.Timestamp(datetime.combine(day, time(9, 30)), tz=ZoneInfo("America/New_York")).tz_convert("UTC")
    end = pd.Timestamp(datetime.combine(day, time(16)), tz=ZoneInfo("America/New_York")).tz_convert("UTC")
    left, right = five_ts.searchsorted(start), five_ts.searchsorted(end)
    local_minutes = fivemin[left:right]
    selected = left + np.flatnonzero((local_minutes >= 605) & (local_minutes < 960))
    for j in selected:
        side = 1 if mid5_close[j] > hi else -1 if mid5_close[j] < lo else 0
        if not side:
            continue
        # A close labelled 10:05 is known at 10:05; the next 5m bar opens there.
        entry_ts = data.five.ts.iloc[j]
        entry_i = int(data.ts.searchsorted(entry_ts))
        if entry_i >= len(data.ts) or data.ts[entry_i] != entry_ts:
            continue
        anchor = (lo if side > 0 else hi) if params["stop_mode"] == "opposite" else (hi + lo) / 2
        stop = float(anchor - side * .25)
        risk = abs(float(data.mid_o[entry_i]) - stop)
        if not admit_stop(data.market, risk, data.atr15_at[entry_i]):
            diagnostics["minimum_stop_skips"] += 1
            # First breakout only: a rejected stop still consumes the day's setup.
            return None
        return {"side": side, "entry_i": entry_i, "stop": stop, "risk": risk,
                "signal_i": max(0, entry_i - 1), "deadline_i": data.force_flat_index(day),
                "or_high": hi, "or_low": lo}
    return None


def simulate(data, params: dict | None = None, *, model: str = "futures", multiplier: float = 1.,
             fill_model: str = "trade_through", signal_delay: int = 0,
             allow_holdout: bool = False, selection_path: Path | None = None) -> tuple[list[dict], dict]:
    params = dict(DEFAULT if params is None else params)
    diagnostics = {"minimum_stop_skips": 0, "bad_opening_range": 0, "signals": 0, "unresolved_at_end": 0}
    exec_bars = execution_bars(data, data.market, model, multiplier)
    five_ts = pd.DatetimeIndex(data.five.ts)
    five_ny = five_ts.tz_convert("America/New_York")
    five = (five_ts, five_ny.hour * 60 + five_ny.minute,
            (data.five.bid_c.to_numpy(float) + data.five.ask_c.to_numpy(float)) / 2,
            (data.five.bid_h.to_numpy(float) + data.five.ask_h.to_numpy(float)) / 2,
            (data.five.bid_l.to_numpy(float) + data.five.ask_l.to_numpy(float)) / 2)
    trades = []
    for row in data.rth_days.itertuples():
        if row.day.year < 2019:
            continue
        order = _signal(data, row, params, diagnostics, five)
        if order is None:
            continue
        diagnostics["signals"] += 1
        entry_i = order["entry_i"] + 5 * int(signal_delay)
        if entry_i >= order["deadline_i"]:
            diagnostics["unresolved_at_end"] += 1
            continue
        risk = abs(float(data.mid_o[entry_i]) - order["stop"])
        if not admit_stop(data.market, risk, data.atr15_at[entry_i]):
            diagnostics["minimum_stop_skips"] += 1
            continue
        trade = simulate_trade(exec_bars, market=data.market, strategy=NAME, params=params,
                               side=order["side"], entry_i=entry_i, stop=order["stop"],
                               target_r=params["target_r"], risk_points=risk,
                               deadline_i=order["deadline_i"], fill_model=fill_model,
                               allow_holdout=allow_holdout, selection_path=selection_path)
        if trade is None:
            diagnostics["unresolved_at_end"] += 1
            continue
        trade.update({"_signal_i": order["signal_i"], "entry_hour": int(data.ny[entry_i].hour)})
        trades.append(trade)
    return trades, diagnostics
