import numpy as np
import pandas as pd
import pytest


def _event_frames(lows, highs, closes):
    ts = pd.date_range("2024-01-02", periods=len(lows), freq="min", tz="UTC")
    bars = pd.DataFrame({"ts": ts, "bid_o": closes, "bid_h": highs, "bid_l": lows,
                         "bid_c": closes, "ask_o": closes, "ask_h": highs,
                         "ask_l": lows, "ask_c": closes, "volume": np.ones(len(ts))})
    features = pd.DataFrame({"ts": ts, "known_at": ts + pd.Timedelta(minutes=1),
                             "1h_atr14": np.full(len(ts), 2.0)})
    levels = pd.DataFrame({"level_id": [1], "price": [100.0], "type": ["prior_day_high"],
                           "timeframe": ["1d"], "created_at": [ts[0]-pd.Timedelta(days=1)],
                           "known_at": [ts[0]-pd.Timedelta(days=1)], "touches_so_far": [0],
                           "invalidated_at": [pd.NaT], "strength": [1.0], "direction": [-1]})
    return features, levels, bars


def test_sr_touch_is_rearmed_edge_triggered_and_offers_both_sides():
    from msd.methods.sr_touch import detect
    features, levels, bars = _event_frames(
        [99.9, 102.8, 99.9, 102.8, 99.9],
        [100.1, 103.2, 100.1, 103.2, 100.1],
        [100.0, 103.0, 100.0, 103.0, 100.0])
    events = detect(features, levels, bars)
    assert len(events) == 1
    assert events[0]["side_candidates"] == [1, -1]
    assert events[0]["approach_direction"] == "from_above_support"
    assert events[0]["cluster_strength"] >= 2
    assert events[0]["cluster_types"] == ("prior_day_high",)
    assert events[0]["ts"] == bars.ts.iloc[2]


def test_sweep_fvg_pilot_returns_after_wick_back_inside():
    from msd.methods.liquidity_sweep import detect
    features, levels, bars = _event_frames(
        [99.8, 102.8, 99.8, 99.7], [100.1, 103.2, 100.3, 100.1],
        [100.0, 103.0, 100.1, 99.9])
    events = detect(features, levels, bars)
    assert len(events) == 1
    assert events[0]["side"] == -1
    assert events[0]["ts"] == bars.ts.iloc[3]
    assert events[0]["cluster_types"] == ("prior_day_high",)


def test_event_volume_guard_fails_loudly_over_50_per_day():
    from msd.methods.common import assert_event_volume
    with pytest.raises(RuntimeError, match="events=51.*average_per_day=51.00"):
        assert_event_volume("sr_touch", "TEST", 51, 1)
    assert_event_volume("sr_touch", "TEST", 100, 2)


def test_level_universe_excludes_intraday_swings_and_unregistered_types():
    from msd.methods.level_clusters import eligible_level_arrays
    levels = pd.DataFrame({"level_id": [1, 2, 3], "price": [100., 101., 102.],
        "type": ["swing_high", "swing_low", "opening_range_high_15m"],
        "timeframe": ["5m", "15m", "15m"], "created_at": [pd.Timestamp("2024-01-01", tz="UTC")]*3,
        "known_at": [pd.Timestamp("2024-01-01", tz="UTC")]*3, "strength": [1/3, 1/5, 1.0]})
    result = eligible_level_arrays(levels)
    assert result is not None
    assert list(result[3]) == [2]
