from __future__ import annotations

import numpy as np

from msd.research.tiktok_b2.primitives import (
    FVG, LiquidityLevel, bias, confirmed_swings, displacement, dol, engulfing,
    fvg_valid, fvgs, ifvg_inversion, liquidity_active, sweeps,
)


def test_swing_is_not_usable_until_confirmation_bar_i_plus_lookback():
    highs = np.array([1, 2, 3, 8, 3, 2, 1], float)
    lows = -highs
    swing_highs, swing_lows = confirmed_swings(highs, lows, 2)
    level = next(row for row in swing_highs if row.origin_i == 3)
    assert level.known_i == 5
    assert not liquidity_active(level, 4, highs, lows, .25)
    assert liquidity_active(level, 5, highs, lows, .25)
    assert any(row.origin_i == 3 and row.known_i == 5 for row in swing_lows)


def test_liquidity_level_is_removed_after_traded_through():
    level = LiquidityLevel(10., "high", 1, 4)
    high = [8, 9, 8, 9, 9, 10.25]
    low = [7] * len(high)
    assert liquidity_active(level, 4, high, low, .25)
    assert not liquidity_active(level, 5, high, low, .25)


def test_sweep_known_only_at_confirming_close_and_uses_confirmed_extreme():
    level = LiquidityLevel(10., "low", 1, 3)
    high = np.array([11, 11, 11, 11, 11, 11], float)
    low = np.array([10, 10, 10, 9.5, 9.25, 10], float)
    close = np.array([10.5, 10.5, 10.5, 9.75, 10.5, 10.5])
    rows = sweeps(high, low, close, [level], max_confirm=2, tick=.25)
    assert len(rows) == 1
    assert rows[0]["sweep_i"] == 3
    assert rows[0]["known_i"] == 4
    assert rows[0]["extreme"] == 9.25


def test_sweep_without_confirmation_inside_m_window_is_not_emitted():
    level = LiquidityLevel(10., "low", 1, 3)
    rows = sweeps([11] * 6, [10, 10, 10, 9.5, 9.5, 9.5],
                  [10.5, 10.5, 10.5, 9.5, 9.5, 9.5], [level], max_confirm=1)
    assert rows == []


def test_displacement_requires_atr_body_and_sixty_percent_body_ratio():
    got = displacement([10, 10, 10], [12, 11, 10.5], [10, 9, 9.5],
                       [12, 10.9, 10.1], [1, 1, 1], k=1.)
    assert got.tolist() == [True, False, False]


def test_fvg_edges_size_expiry_and_close_invalidation():
    o = [10, 10, 10, 10, 10]
    h = [10, 10.5, 10.8, 11, 10]
    l = [9.5, 10, 11, 10, 9]
    c = [9.8, 10.2, 11.2, 10.5, 9.4]
    zones = fvgs(o, h, l, c, [1] * 5, min_atr=.1, expiry=2)
    bullish = next(row for row in zones if row.side > 0)
    assert (bullish.bottom, bullish.top, bullish.known_i, bullish.expiry_i) == (10., 11., 2, 4)
    assert fvg_valid(bullish, 3, c)
    assert not fvg_valid(bullish, 4, c)
    assert not fvg_valid(bullish, 5, c)
    assert all(row.size >= .1 for row in zones)


def test_ifvg_requires_body_fully_beyond_the_far_edge():
    bearish = FVG(9., 10., -1, 2, 2, 1., 8)
    assert ifvg_inversion(bearish, [9, 9, 9, 9, 10.1, 9], [9, 9, 9, 10.1, 10.5, 9], start=3) == 4
    bullish = FVG(9., 10., 1, 2, 2, 1., 8)
    assert ifvg_inversion(bullish, [9, 9, 9, 9, 8.9, 9], [9, 9, 9, 8.9, 8.5, 9], start=3) == 4


def test_engulfing_inclusive_edges_and_directional_close():
    o, c = [10, 9, 9.5, 9, 10], [9, 10, 10, 10, 9]
    assert engulfing(o, c, 1, 1)
    assert engulfing(o, c, 4, -1)
    assert not engulfing(o, c, 3, 1)
    assert not engulfing(o, c, 0, 1)


def test_dol_near_far_requires_one_r_and_unswept_opposing_levels():
    levels = [LiquidityLevel(105, "high", 1, 2),
              LiquidityLevel(108, "high", 3, 3),
              LiquidityLevel(120, "high", 4, 4)]
    high = [100, 101, 102, 103, 104]
    low = [99] * 5
    near, far = dol(levels, 1, 100, 4, index=4, high=high, low=low, pdh=107)
    assert near == 105
    assert far == 107  # nearer than the next swing high
    assert dol(levels, 1, 100, 6, index=4, high=high, low=low) == (108, 120)


def test_biases_and_hindsight_diagnostic():
    assert bias("B0") == 0
    assert bias("B1", yesterday_open=1, yesterday_close=2) == 1
    assert bias("B2", price=1, midnight_open=2) == -1
    assert bias("B3", yesterday_close=2, daily_ema=1) == 1
    assert bias("B4", ema20_15=1, ema50_15=2) == -1
    assert bias("B∞", rth_open=10, rth_close=11) == 1
