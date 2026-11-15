"""Causal, array-based ICT primitives used by batch-2 strategies."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class LiquidityLevel:
    price: float
    kind: str  # "high" or "low"
    origin_i: int
    known_i: int
    source: str = "swing"


@dataclass(frozen=True)
class FVG:
    bottom: float
    top: float
    side: int
    formed_i: int
    known_i: int
    size: float
    expiry_i: int


def confirmed_swings(high, low, lookback: int = 3) -> tuple[list[LiquidityLevel], list[LiquidityLevel]]:
    """Strict local extrema; a level's first usable index is origin + lookback."""
    high, low = np.asarray(high, float), np.asarray(low, float)
    if lookback < 1:
        raise ValueError("lookback must be positive")
    swing_highs, swing_lows = [], []
    for i in range(lookback, len(high) - lookback):
        if high[i] > np.max(high[i - lookback:i]) and high[i] > np.max(high[i + 1:i + lookback + 1]):
            swing_highs.append(LiquidityLevel(float(high[i]), "high", i, i + lookback))
        if low[i] < np.min(low[i - lookback:i]) and low[i] < np.min(low[i + 1:i + lookback + 1]):
            swing_lows.append(LiquidityLevel(float(low[i]), "low", i, i + lookback))
    return swing_highs, swing_lows


def liquidity_active(level: LiquidityLevel, index: int, high, low, tick: float) -> bool:
    """Whether an already-confirmed level remains unswept through index."""
    if index < level.known_i:
        return False
    highs, lows = np.asarray(high, float), np.asarray(low, float)
    if level.kind == "high":
        return not np.any(highs[level.known_i:index + 1] >= level.price + tick)
    return not np.any(lows[level.known_i:index + 1] <= level.price - tick)


def sweeps(high, low, close, levels: list[LiquidityLevel], max_confirm: int = 3,
           tick: float = .25) -> list[dict]:
    """Return sweeps only at the confirming close, with the full sweep extreme."""
    high, low, close = (np.asarray(x, float) for x in (high, low, close))
    result = []
    for level in levels:
        start = max(level.known_i, level.origin_i + 1)
        for i in range(start, len(close)):
            if level.kind == "low":
                swept = low[i] < level.price - tick
                confirms = close[i:min(len(close), i + max_confirm + 1)] > level.price
            else:
                swept = high[i] > level.price + tick
                confirms = close[i:min(len(close), i + max_confirm + 1)] < level.price
            if not swept:
                continue
            found = np.flatnonzero(confirms)
            if len(found):
                known_i = i + int(found[0])
                extreme = float(np.min(low[i:known_i + 1]) if level.kind == "low"
                                else np.max(high[i:known_i + 1]))
                result.append({"level": level, "sweep_i": i, "known_i": known_i,
                               "side": 1 if level.kind == "low" else -1,
                               "extreme": extreme})
                break
    return sorted(result, key=lambda row: (row["known_i"], row["sweep_i"]))


def displacement(open_, high, low, close, atr, k: float = 1.) -> np.ndarray:
    o, h, l, c, a = (np.asarray(x, float) for x in (open_, high, low, close, atr))
    body, span = np.abs(c - o), h - l
    return np.isfinite(a) & (a > 0) & (body >= k * a) & (span > 0) & (body / span >= .6)


def fvgs(open_, high, low, close, atr, *, min_atr: float = .1, expiry: int = 60) -> list[FVG]:
    """Enumerate 3-bar gaps at the close of their third bar."""
    h, l, a = np.asarray(high, float), np.asarray(low, float), np.asarray(atr, float)
    result = []
    for i in range(2, len(h)):
        if not np.isfinite(a[i]) or a[i] <= 0:
            continue
        if l[i] > h[i - 2] and l[i] - h[i - 2] >= min_atr * a[i]:
            result.append(FVG(float(h[i - 2]), float(l[i]), 1, i, i, float(l[i] - h[i - 2]), i + expiry))
        if h[i] < l[i - 2] and l[i - 2] - h[i] >= min_atr * a[i]:
            result.append(FVG(float(h[i]), float(l[i - 2]), -1, i, i, float(l[i - 2] - h[i]), i + expiry))
    return result


def fvg_valid(zone: FVG, index: int, close) -> bool:
    """Valid through expiry, but cancelled by a close beyond its far edge."""
    if index < zone.known_i or index > zone.expiry_i:
        return False
    closes = np.asarray(close, float)
    seen = closes[zone.known_i + 1:index + 1]
    return not np.any(seen < zone.bottom if zone.side > 0 else seen > zone.top)


def ifvg_inversion(zone: FVG, open_, close, start: int | None = None) -> int | None:
    """First post-formation candle body fully closes beyond the zone's far edge."""
    o, c = np.asarray(open_, float), np.asarray(close, float)
    for i in range(max(zone.known_i + 1, start or 0), min(len(c), zone.expiry_i + 1)):
        body_low, body_high = min(o[i], c[i]), max(o[i], c[i])
        if zone.side < 0 and body_low > zone.top:
            return i
        if zone.side > 0 and body_high < zone.bottom:
            return i
    return None


def engulfing(open_, close, index: int, side: int) -> bool:
    """Frozen body-engulfing rule; engulfing bar itself must be directional."""
    o, c = np.asarray(open_, float), np.asarray(close, float)
    if index <= 0 or index >= len(c):
        return False
    if side > 0:
        return c[index - 1] < o[index - 1] and c[index] > o[index] and o[index] <= c[index - 1] and c[index] >= o[index - 1]
    return c[index - 1] > o[index - 1] and c[index] < o[index] and o[index] >= c[index - 1] and c[index] <= o[index - 1]


def dol(levels: list[LiquidityLevel], side: int, entry: float, risk: float,
        *, index: int, high, low, pdh: float | None = None, pdl: float | None = None,
        tick: float = .25) -> tuple[float | None, float | None]:
    """Nearest and far opposing unswept levels at least one risk away."""
    candidates = []
    for level in levels:
        if level.known_i > index or level.kind != ("high" if side > 0 else "low"):
            continue
        if not liquidity_active(level, index, high, low, tick):
            continue
        distance = side * (level.price - entry)
        if distance >= risk:
            candidates.append(level.price)
    opposing_daily = pdh if side > 0 else pdl
    if opposing_daily is not None and side * (opposing_daily - entry) >= risk:
        candidates.append(float(opposing_daily))
    ordered = sorted(set(candidates), key=lambda value: side * (value - entry))
    if not ordered:
        return None, None
    return ordered[0], ordered[1] if len(ordered) > 1 else None


def bias(name: str, *, yesterday_open=None, yesterday_close=None, daily_ema=None,
         price=None, midnight_open=None, ema20_15=None, ema50_15=None,
         rth_open=None, rth_close=None) -> int:
    """Return +1 / -1 directional filter or 0 for B0/equality/missing data."""
    if name == "B0":
        return 0
    pairs = {
        "B1": (yesterday_close, yesterday_open),
        "B2": (price, midnight_open),
        "B3": (yesterday_close, daily_ema),
        "B4": (ema20_15, ema50_15),
        "B∞": (rth_close, rth_open),
    }
    if name not in pairs:
        raise ValueError(f"unknown bias {name}")
    left, right = pairs[name]
    if left is None or right is None or not np.isfinite(left) or not np.isfinite(right):
        return 0
    return int(np.sign(left - right))
