from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import numpy as np
import pandas as pd

from msd.research.tiktok_b2 import primitives, strategy_c, strategy_d


DAY = date(2019, 1, 2)


def _series(event_known=4):
    size = 10
    open_ = np.full(size, 100.0)
    high = np.full(size, 100.5)
    low = np.full(size, 99.5)
    close = np.full(size, 100.0)
    open_[4], high[4], low[4], close[4] = 100.0, 102.0, 99.0, 102.0
    high[3], low[5] = 100.0, 101.0
    zone = primitives.FVG(100.0, 101.0, 1, 5, 5, 1.0, 65)
    event = {"known_i": event_known, "sweep_i": 2, "side": 1, "extreme": 95.0}
    return {
        "o": open_, "h": high, "l": low, "c": close, "atr": np.ones(size),
        "minutes": np.arange(600, 610), "days": np.array([DAY] * size, dtype=object),
        "minute_index": np.arange(1, 11), "scale": 1,
        "fvgs": [zone], "fvgs_by_day": {DAY: [zone]}, "events": [event],
        "swing20": [],
    }


def _data():
    ts = pd.date_range("2019-01-02 15:00", periods=20, freq="min", tz="UTC")
    rth = pd.DataFrame(
        [{"day": DAY, "complete": True, "first_i": 0, "last_i": 20,
          "open": 100.0, "high": 110.0, "low": 90.0, "close": 105.0}]
    )
    return SimpleNamespace(
        market="USATECHIDXUSD", ts=ts, ny=ts.tz_convert("America/New_York"),
        local_minutes=np.arange(600, 620), rth_days=rth,
        mid_c=np.full(20, 100.0), atr15_at=np.ones(20),
        midnight_open={DAY: 100.0}, daily_ema20={}, ema15_20_at=np.ones(20),
        ema15_50_at=np.zeros(20), pdh={DAY: 110.0}, pdl={DAY: 90.0},
        force_flat_index=lambda day: 19,
    )


def test_sweep_is_not_usable_until_swing_confirmation():
    high = np.full(7, 6.0)
    low = np.array([5.0, 4.0, 3.0, 4.0, 5.0, 2.5, 4.0])
    close = np.array([5.5, 4.5, 3.5, 4.5, 5.5, 3.5, 4.5])
    events = strategy_c._sweep_events(high, low, close, 2, 3, 0.25)
    assert len(events) == 1
    assert events[0]["level"].origin_i == 2
    assert events[0]["level"].known_i == 4
    assert events[0]["sweep_i"] == events[0]["level"].known_i + 1


def test_c_chain_requires_prior_sweep_then_displacement_fvg(monkeypatch):
    data = _data()
    monkeypatch.setattr(strategy_c, "_series", lambda *args: _series(4))
    monkeypatch.setattr(strategy_c, "_bias_for", lambda *args: 1)
    monkeypatch.setattr(strategy_c, "_target", lambda *args: 110.0)
    diagnostics = {"entry_beyond_stop_skips": 0, "missing_target_skips": 0}
    orders = strategy_c._orders(data, strategy_c.DEFAULT, diagnostics)
    assert len(orders) == 1
    assert orders[0]["side"] == 1
    assert orders[0]["limit"] == 101.0
    assert orders[0]["stop"] == 94.75

    monkeypatch.setattr(strategy_c, "_series", lambda *args: _series(5))
    assert strategy_c._orders(data, strategy_c.DEFAULT, diagnostics) == []


def test_d_chain_enforces_sweep_recency_and_session(monkeypatch):
    data = _data()
    monkeypatch.setattr(strategy_c, "_series", lambda *args: _series(4))
    monkeypatch.setattr(strategy_c, "_bias_for", lambda *args: 0)
    diagnostics = {"entry_beyond_stop_skips": 0, "missing_target_skips": 0}
    orders = strategy_d._candidate_orders(data, strategy_d.DEFAULT, diagnostics)
    assert len(orders) == 1
    assert orders[0]["target_r"] == 2.0
    assert orders[0]["expiry_i"] == 19 or orders[0]["expiry_i"] == 9

    stale = {**strategy_d.DEFAULT, "N": 0}
    assert strategy_d._candidate_orders(data, stale, diagnostics) == []


def test_frozen_grid_sizes_and_defaults_are_present():
    assert len(strategy_c.GRID) == 36
    assert len(strategy_d.GRID) == 25
    assert strategy_c.DEFAULT in strategy_c.GRID
    assert strategy_d.DEFAULT in strategy_d.GRID
