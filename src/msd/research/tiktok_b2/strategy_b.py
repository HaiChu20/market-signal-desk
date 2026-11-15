"""Frozen B: 5-minute opening-range breakout, FVG retest, engulfing entry."""
from __future__ import annotations

from itertools import product
from pathlib import Path

import numpy as np

from .execution import admit_stop, execution_bars, simulate_trade

NAME = "B"
GRID = [dict(body_ratio=b, deadline=d, target_r=t, stop_mode=s)
        for b, d, t, s in product((.5, .6, .7), ("10:00", "10:30", "11:00"), (2., 3.), ("engulf", "fvg"))]
DEFAULT = {"body_ratio": .6, "deadline": "10:00", "target_r": 3., "stop_mode": "engulf"}


def _deadline_index(data, day, clock: str, start_i: int, end_i: int) -> int:
    hour, minute = map(int, clock.split(":"))
    idx = np.arange(start_i, end_i)
    local_minutes = data.local_minutes[idx]
    found = np.flatnonzero(local_minutes >= hour * 60 + minute)
    return int(idx[found[0]]) if len(found) else data.force_flat_index(day)


def _signals_for_day(data, row, params, diagnostics):
    day = row.day
    day_idx = np.arange(int(row.first_i), int(row.last_i))
    if len(day_idx) < 7:
        return None
    rth_complete = bool(row.complete)
    if not rth_complete:
        return None
    day_minutes = data.local_minutes[day_idx]
    or_idx = day_idx[day_minutes < 575]
    if len(or_idx) != 5:
        diagnostics["bad_opening_range"] += 1
        return None
    or_high, or_low = float(data.mid_h[or_idx].max()), float(data.mid_l[or_idx].min())
    deadline_i = _deadline_index(data, day, params["deadline"], int(row.first_i), int(row.last_i))
    first = int(or_idx[-1] + 1)
    # Build the breakout candidates in numpy, then inspect only valid FVGs.
    # This avoids walking each remaining morning bar for every candidate gap.
    stop_exclusive = min(int(day_idx[-1]) + 1, deadline_i)
    candidate_j = np.arange(first, max(first, stop_exclusive - 1), dtype=int)
    if not len(candidate_j):
        return None
    spans = data.mid_h[candidate_j] - data.mid_l[candidate_j]
    body_ratios = np.divide(np.abs(data.mid_c[candidate_j] - data.mid_o[candidate_j]), spans,
                            out=np.zeros_like(spans), where=spans > 0)
    directions = np.where(data.mid_c[candidate_j] > or_high, 1,
                          np.where(data.mid_c[candidate_j] < or_low, -1, 0))
    directional = directions * (data.mid_c[candidate_j] - data.mid_o[candidate_j]) > 0
    eligible = (directions != 0) & directional & (body_ratios >= params["body_ratio"])
    candidate_j, directions = candidate_j[eligible], directions[eligible]
    valid_gaps = []
    for j, side in zip(candidate_j, directions):
        k = int(j + 1)
        atr = data.atr1[k]
        if not np.isfinite(atr) or atr <= 0:
            continue
        if side > 0:
            bottom, top = data.mid_h[j - 1], data.mid_l[k]
        else:
            bottom, top = data.mid_h[k], data.mid_l[j - 1]
        if top > bottom and top - bottom >= .1 * atr:
            valid_gaps.append((int(j), int(side), float(bottom), float(top)))
    engulf_bull = np.zeros(len(day_idx), dtype=bool)
    engulf_bear = np.zeros(len(day_idx), dtype=bool)
    current_local = np.arange(1, len(day_idx), dtype=int)
    previous_local = current_local - 1
    current_i = day_idx[current_local]
    previous_i = day_idx[previous_local]
    engulf_bull[current_local] = ((data.mid_c[previous_i] < data.mid_o[previous_i]) &
                                 (data.mid_c[current_i] > data.mid_o[current_i]) &
                                 (data.mid_o[current_i] <= data.mid_c[previous_i]) &
                                 (data.mid_c[current_i] >= data.mid_o[previous_i]))
    engulf_bear[current_local] = ((data.mid_c[previous_i] > data.mid_o[previous_i]) &
                                 (data.mid_c[current_i] < data.mid_o[current_i]) &
                                 (data.mid_o[current_i] >= data.mid_c[previous_i]) &
                                 (data.mid_c[current_i] <= data.mid_o[previous_i]))
    order = None
    for j, side, bottom, top in valid_gaps:
        indices = np.arange(j + 2, stop_exclusive, dtype=int)
        if not len(indices):
            continue
        retest = data.mid_l[indices] <= top if side > 0 else data.mid_h[indices] >= bottom
        local_indices = indices - int(day_idx[0])
        engulf = engulf_bull[local_indices] if side > 0 else engulf_bear[local_indices]
        invalid = data.mid_c[indices] < bottom if side > 0 else data.mid_c[indices] > top
        found = np.flatnonzero(retest & engulf)
        if not len(found):
            continue
        signal_i = int(indices[found[0]])
        invalid_i = np.flatnonzero(invalid)
        if len(invalid_i) and int(indices[invalid_i[0]]) <= signal_i:
            continue
        entry_i = signal_i + 1
        if entry_i >= len(data.ts) or entry_i > deadline_i:
            continue
        if params["stop_mode"] == "engulf":
            anchor = min(data.mid_l[signal_i], data.mid_l[signal_i - 1]) if side > 0 else max(data.mid_h[signal_i], data.mid_h[signal_i - 1])
        else:
            anchor = bottom if side > 0 else top
        stop = float(anchor - side * .25)
        risk = abs(float(data.mid_o[entry_i]) - stop)
        if not admit_stop(data.market, risk, data.atr15_at[entry_i]):
            diagnostics["minimum_stop_skips"] += 1
            continue
        order = {"side": side, "entry_i": entry_i, "stop": stop,
                 "risk_points": risk, "deadline_i": data.force_flat_index(day),
                 "signal_i": signal_i, "or_high": or_high, "or_low": or_low}
        break
    return order


def simulate(data, params: dict | None = None, *, model: str = "futures", multiplier: float = 1.,
             fill_model: str = "trade_through", signal_delay: int = 0,
             allow_holdout: bool = False, selection_path: Path | None = None) -> tuple[list[dict], dict]:
    params = dict(DEFAULT if params is None else params)
    diagnostics = {"minimum_stop_skips": 0, "bad_opening_range": 0, "signals": 0, "unresolved_at_end": 0}
    exec_bars = execution_bars(data, data.market, model, multiplier)
    trades = []
    for row in data.rth_days.itertuples():
        if not row.complete or row.day.year < 2019:
            continue
        order = _signals_for_day(data, row, params, diagnostics)
        if order is None:
            continue
        diagnostics["signals"] += 1
        entry_i = order["entry_i"] + int(signal_delay)
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


def simulate_group(data, cells: list[dict], *, model: str = "futures", multiplier: float = 1.,
                   fill_model: str = "trade_through") -> list[tuple[dict, list[dict], dict]]:
    """Evaluate all four SL/TP cells after sharing one signal scan per SL anchor."""
    if not cells:
        return []
    body, deadline = cells[0]["body_ratio"], cells[0]["deadline"]
    if any(row["body_ratio"] != body or row["deadline"] != deadline for row in cells):
        raise ValueError("a B worker group must share body ratio and deadline")
    outputs = {tuple(sorted(cell.items())): [dict(cell), [],
               {"minimum_stop_skips": 0, "bad_opening_range": 0,
                "signals": 0, "unresolved_at_end": 0}] for cell in cells}
    exec_bars = execution_bars(data, data.market, model, multiplier)
    for row in data.rth_days.itertuples():
        if not row.complete or row.day.year < 2019:
            continue
        for stop_mode in ("engulf", "fvg"):
            members = [cell for cell in cells if cell["stop_mode"] == stop_mode]
            if not members:
                continue
            first_cell = members[0]
            local_diag = {"minimum_stop_skips": 0, "bad_opening_range": 0}
            order = _signals_for_day(data, row, first_cell, local_diag)
            for cell in members:
                _, trades, diag = outputs[tuple(sorted(cell.items()))]
                diag["minimum_stop_skips"] += local_diag["minimum_stop_skips"]
                diag["bad_opening_range"] += local_diag["bad_opening_range"]
                if order is None:
                    continue
                diag["signals"] += 1
                entry_i = order["entry_i"]
                risk = order["risk_points"]
                stop = order["stop"]
                if entry_i >= order["deadline_i"]:
                    diag["unresolved_at_end"] += 1
                    continue
                trade = simulate_trade(exec_bars, market=data.market, strategy=NAME, params=cell,
                                       side=order["side"], entry_i=entry_i, stop=stop,
                                       target_r=cell["target_r"], risk_points=risk,
                                       deadline_i=order["deadline_i"], fill_model=fill_model)
                if trade is None:
                    diag["unresolved_at_end"] += 1
                    continue
                trade.update({"_signal_i": order["signal_i"],
                              "entry_hour": int(data.ny[entry_i].hour)})
                trades.append(trade)
    return list(outputs.values())
