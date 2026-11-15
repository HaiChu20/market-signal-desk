"""Frozen C: textbook ICT Silver Bullet."""
from __future__ import annotations

from bisect import bisect_left, bisect_right, insort
from datetime import datetime, time
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd

from . import prep, primitives
from .execution import admit_stop, execution_bars, simulate_trade, tick_size

NAME = "C"
WINDOWS = ((180, 240), (600, 660), (840, 900))
GRID = [
    dict(bias=bias, windows=windows, entry=entry, exit=exit_, L=3,
         min_target=10., timeframe="1m")
    for bias, windows, entry, exit_ in product(
        ("B0", "B1", "B2", "B3"), ("primary", "all"),
        ("proximal", "ce"), ("16:00", "window"),
    )
]
DEFAULT = dict(bias="B1", windows="primary", entry="proximal", exit="16:00",
               L=3, min_target=10., timeframe="1m")
for key, values in (("L", (2, 5)), ("min_target", (20.,)), ("timeframe", ("5m",))):
    for value in values:
        GRID.append({**DEFAULT, key: value})


def _sweep_events(high, low, close, lookback: int, max_confirm: int, tick: float):
    """Chronological active-level sweep scan; each level is touched only once."""
    swing_highs, swing_lows = primitives.confirmed_swings(high, low, lookback)
    additions: dict[int, list[primitives.LiquidityLevel]] = {}
    for level in (*swing_highs, *swing_lows):
        additions.setdefault(level.known_i, []).append(level)
    active_highs: list[tuple[float, int, primitives.LiquidityLevel]] = []
    active_lows: list[tuple[float, int, primitives.LiquidityLevel]] = []
    pending = []
    result = []
    serial = 0
    for i in range(len(close)):
        for level in additions.get(i, ()):
            serial += 1
            target = active_highs if level.kind == "high" else active_lows
            insort(target, (level.price, serial, level))
        low_cut = bisect_right(active_lows, (float(low[i] + tick), np.inf, None))
        crossed_lows, active_lows = active_lows[low_cut:], active_lows[:low_cut]
        high_cut = bisect_left(active_highs, (float(high[i] - tick), -np.inf, None))
        crossed_highs, active_highs = active_highs[:high_cut], active_highs[high_cut:]
        pending.extend({"level": row[2], "sweep_i": i, "side": 1,
                        "extreme": float(low[i]), "expires": i + max_confirm}
                       for row in crossed_lows)
        pending.extend({"level": row[2], "sweep_i": i, "side": -1,
                        "extreme": float(high[i]), "expires": i + max_confirm}
                       for row in crossed_highs)
        keep = []
        for event in pending:
            event["extreme"] = (min(event["extreme"], float(low[i])) if event["side"] > 0
                                else max(event["extreme"], float(high[i])))
            confirmed = (close[i] > event["level"].price if event["side"] > 0
                         else close[i] < event["level"].price)
            if confirmed:
                result.append({**event, "known_i": i})
            elif i < event["expires"]:
                keep.append(event)
        pending = keep
    return sorted(result, key=lambda row: (row["known_i"], row["sweep_i"]))


def _mid_frame(frame: pd.DataFrame) -> dict[str, np.ndarray]:
    return {field: (frame[f"bid_{field}"].to_numpy(float)
                    + frame[f"ask_{field}"].to_numpy(float)) / 2 for field in "ohlc"}


def _level_lifetimes(high, low, levels, tick: float) -> dict[str, np.ndarray]:
    """Precompute each confirmed level's first trade-through index in one scan."""
    additions = {}
    for serial, level in enumerate(levels):
        additions.setdefault(level.known_i, []).append((serial, level))
    active_highs, active_lows = [], []
    invalid = np.full(len(levels), len(high) + 1, dtype=int)
    for i in range(len(high)):
        for serial, level in additions.get(i, ()):
            insort(active_highs if level.kind == "high" else active_lows,
                   (level.price, serial))
        low_cut = bisect_right(active_lows, (float(low[i] + tick), np.inf))
        for _, serial in active_lows[low_cut:]:
            invalid[serial] = i
        active_lows = active_lows[:low_cut]
        high_cut = bisect_left(active_highs, (float(high[i] - tick), -np.inf))
        for _, serial in active_highs[:high_cut]:
            invalid[serial] = i
        active_highs = active_highs[high_cut:]
    return {
        "price": np.asarray([level.price for level in levels], float),
        "known": np.asarray([level.known_i for level in levels], int),
        "invalid": invalid,
        "side": np.asarray([1 if level.kind == "high" else -1 for level in levels], int),
    }


def _series(data, timeframe: str, lookback: int, max_confirm: int = 3):
    cache = data.__dict__.setdefault("_strategy_c_series", {})
    key = (timeframe, lookback, max_confirm)
    if key in cache:
        return cache[key]
    base_key = (timeframe, "base")
    base = cache.get(base_key)
    if base is None:
        if timeframe == "1m":
            arrays = {field: getattr(data, f"mid_{field}") for field in "ohlc"}
            atr = data.atr1
            stamps = data.ts
            minute_index = np.arange(len(data.ts), dtype=int) + 1
            local = data.ny
            bar_minutes = data.local_minutes
            bar_days = np.asarray(local.date, dtype=object)
        elif timeframe == "5m":
            arrays = _mid_frame(data.five)
            atr = prep._atr(arrays["h"], arrays["l"], arrays["c"])
            stamps = pd.DatetimeIndex(data.five.ts)
            minute_index = np.searchsorted(data.ts.asi8, stamps.asi8)
            local = stamps.tz_convert(prep.NY)
            bar_minutes = local.hour.to_numpy() * 60 + local.minute.to_numpy()
            bar_days = np.asarray(local.date, dtype=object)
        else:
            raise ValueError("timeframe must be 1m or 5m")
        fvgs = primitives.fvgs(arrays["o"], arrays["h"], arrays["l"], arrays["c"], atr)
        swing20 = sum(primitives.confirmed_swings(arrays["h"], arrays["l"], 20), [])
        liquidity20 = _level_lifetimes(arrays["h"], arrays["l"], swing20,
                                       tick_size(data.market))
        base = {**arrays, "atr": atr, "stamps": stamps, "minute_index": minute_index,
                "minutes": np.asarray(bar_minutes), "days": bar_days,
                "fvgs": fvgs, "swing20": swing20, "liquidity20": liquidity20,
                "scale": 1 if timeframe == "1m" else 5, "fvgs_by_day": {}}
        for zone in fvgs:
            base["fvgs_by_day"].setdefault(bar_days[zone.formed_i], []).append(zone)
        cache[base_key] = base
    arrays, atr = base, base["atr"]
    events = _sweep_events(arrays["h"], arrays["l"], arrays["c"], lookback,
                           max_confirm, tick_size(data.market))
    output = {**base, "events": events}
    cache[key] = output
    return output


def _prior_complete(data, day):
    rows = data.rth_days[(data.rth_days.day < day) & data.rth_days.complete]
    return None if rows.empty else rows.iloc[-1]


def _bias_for(data, name: str, day, minute_i: int, price: float | None = None) -> int:
    prior = _prior_complete(data, day)
    prior_open = prior.open if prior is not None else None
    prior_close = prior.close if prior is not None else None
    prior_ema = data.daily_ema20.get(prior.day) if prior is not None else None
    row = data.rth_days[data.rth_days.day == day]
    today = None if row.empty else row.iloc[0]
    return primitives.bias(
        name,
        yesterday_open=prior_open,
        yesterday_close=prior_close,
        daily_ema=prior_ema,
        price=(data.mid_c[min(minute_i, len(data.ts) - 1)] if price is None else price),
        midnight_open=data.midnight_open.get(day),
        ema20_15=data.ema15_20_at[min(minute_i, len(data.ts) - 1)],
        ema50_15=data.ema15_50_at[min(minute_i, len(data.ts) - 1)],
        rth_open=None if today is None else today.open,
        rth_close=None if today is None else today.close,
    )


def _limit_price(zone, mode: str) -> float:
    if mode == "ce":
        return (zone.bottom + zone.top) / 2
    return zone.top if zone.side > 0 else zone.bottom


def _target(data, series, side: int, signal_i: int, entry: float, risk: float,
            day, min_target: float) -> float | None:
    levels = series["liquidity20"]
    distance = side * (levels["price"] - entry)
    eligible = ((levels["side"] == side) & (levels["known"] <= signal_i)
                & (levels["invalid"] > signal_i) & (distance >= risk))
    candidates = list(levels["price"][eligible])
    daily = data.pdh.get(day) if side > 0 else data.pdl.get(day)
    if daily is not None and side * (daily - entry) >= risk:
        candidates.append(float(daily))
    near = min(candidates, key=lambda value: side * (value - entry)) if candidates else None
    required = min_target * (.25 if data.market == "USA500IDXUSD" else 1.)
    return near if near is not None and side * (near - entry) >= required else None


def _window_bounds(data, day, start: int, end: int) -> tuple[int, int]:
    opened = pd.Timestamp(datetime.combine(day, time(start // 60, start % 60)), tz=prep.NY).tz_convert("UTC")
    closed = pd.Timestamp(datetime.combine(day, time(end // 60, end % 60)), tz=prep.NY).tz_convert("UTC")
    return int(data.ts.searchsorted(opened)), int(data.ts.searchsorted(closed))


def _orders(data, params: dict, diagnostics: dict):
    series = _series(data, params["timeframe"], int(params["L"]))
    displacement = primitives.displacement(series["o"], series["h"], series["l"],
                                            series["c"], series["atr"], 1.)
    windows = (WINDOWS[1],) if params["windows"] == "primary" else WINDOWS
    events_by_side = {side: [row for row in series["events"] if row["side"] == side]
                      for side in (-1, 1)}
    event_known = {side: [row["known_i"] for row in rows]
                   for side, rows in events_by_side.items()}
    output = []
    for day_row in data.rth_days.itertuples():
        if not day_row.complete or day_row.day.year < 2019:
            continue
        for start, end in windows:
            candidates = []
            for zone in series["fvgs_by_day"].get(day_row.day, ()):
                i = zone.formed_i
                if i < 2 or series["days"][i] != day_row.day:
                    continue
                # Right-labelled 5m bars close at `minutes`; 1m bars are labelled at open.
                minutes = series["minutes"][i - 2:i + 1]
                inside = ((minutes > start) & (minutes <= end) if params["timeframe"] == "5m"
                          else (minutes >= start) & (minutes < end))
                if not inside.all() or not displacement[i - 1]:
                    continue
                middle_direction = np.sign(series["c"][i - 1] - series["o"][i - 1])
                if middle_direction != zone.side:
                    continue
                events = events_by_side[zone.side]
                pos = bisect_left(event_known[zone.side], i) - 1
                event = None
                while pos >= 0:
                    candidate = events[pos]
                    event_day = series["days"][candidate["sweep_i"]]
                    if event_day != day_row.day:
                        break
                    sweep_minute = series["minutes"][candidate["sweep_i"]]
                    inside_sweep = (start < sweep_minute <= end if params["timeframe"] == "5m"
                                    else start <= sweep_minute < end)
                    if inside_sweep:
                        event = candidate
                        break
                    pos -= 1
                if event is None:
                    continue
                minute_i = int(series["minute_index"][i])
                entry = _limit_price(zone, params["entry"])
                direction = _bias_for(data, params["bias"], day_row.day, minute_i, entry)
                if params["bias"] != "B0" and direction != zone.side:
                    continue
                stop = float(event["extreme"] - zone.side * tick_size(data.market))
                risk = zone.side * (entry - stop)
                if risk <= 0:
                    diagnostics["entry_beyond_stop_skips"] += 1
                    continue
                target = _target(data, series, zone.side, i, entry, risk,
                                 day_row.day, params["min_target"])
                if target is None:
                    diagnostics["missing_target_skips"] += 1
                    continue
                candidates.append((i, zone, entry, stop, risk, target))
            if candidates:
                i, zone, entry, stop, risk, target = min(candidates, key=lambda row: row[0])
                start_i = int(series["minute_index"][i]) + int(params.get("signal_delay", 0)) * series["scale"]
                _, window_end = _window_bounds(data, day_row.day, start, end)
                deadline = (window_end if params["exit"] == "window"
                            else data.force_flat_index(day_row.day))
                output.append({"day": day_row.day, "window": (start, end), "side": zone.side,
                               "entry_i": start_i, "limit": entry, "stop": stop, "risk": risk,
                               "target_r": abs(target - entry) / risk,
                               "expiry_i": window_end - 1, "deadline_i": deadline,
                               "signal_i": int(series["minute_index"][i])})
    return output


def simulate(data, params: dict | None = None, *, model: str = "futures", multiplier: float = 1.,
             fill_model: str = "trade_through", signal_delay: int = 0,
             allow_holdout: bool = False, selection_path: Path | None = None):
    params = dict(DEFAULT if params is None else params)
    scan_params = {**params, "signal_delay": signal_delay}
    diagnostics = {"minimum_stop_skips": 0, "entry_beyond_stop_skips": 0,
                   "missing_target_skips": 0, "signals": 0, "unfilled": 0,
                   "unresolved_at_end": 0}
    orders = _orders(data, scan_params, diagnostics)
    bars = execution_bars(data, data.market, model, multiplier)
    trades = []
    blocked_days = set()
    next_free = -1
    for order in sorted(orders, key=lambda row: row["entry_i"]):
        if order["day"] in blocked_days or order["entry_i"] <= next_free:
            continue
        diagnostics["signals"] += 1
        trade = simulate_trade(
            bars, market=data.market, strategy=NAME, params=params,
            side=order["side"], entry_i=order["entry_i"], stop=order["stop"],
            target_r=order["target_r"], risk_points=order["risk"],
            deadline_i=order["deadline_i"], entry_type="limit", limit_price=order["limit"],
            expiry_i=order["expiry_i"], fill_model=fill_model,
            allow_holdout=allow_holdout, selection_path=selection_path,
        )
        if trade is None:
            diagnostics["unfilled"] += 1
            continue
        if not admit_stop(data.market, order["risk"], data.atr15_at[trade["_entry_i"]]):
            diagnostics["minimum_stop_skips"] += 1
            continue
        next_free = trade["_exit_i"]
        if trade["exit_reason"] == "stop":
            blocked_days.add(order["day"])
        trade.update({"_signal_i": order["signal_i"],
                      "entry_hour": int(data.ny[trade["_entry_i"]].hour)})
        trades.append(trade)
    return trades, diagnostics
