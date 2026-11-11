import numpy as np
import pandas as pd
import pytest
import subprocess
import sys


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


def test_sr_touch_state_checkpoint_matches_unbroken_scan():
    from msd.methods.sr_touch import detect
    features, levels, bars = _event_frames(
        [99.9, 102.8, 99.9, 102.8, 99.9],
        [100.1, 103.2, 100.1, 103.2, 100.1],
        [100.0, 103.0, 100.0, 103.0, 100.0])
    whole = detect(features, levels, bars)
    first, state, touches_a = detect(features.iloc[:3], levels, bars.iloc[:3], return_state=True)
    second, final_state, touches_b = detect(features.iloc[3:], levels, bars.iloc[3:], state=state, return_state=True)
    assert first + second == whole
    assert final_state["touch_counts"] == detect(features, levels, bars, return_state=True)[1]["touch_counts"]
    assert len(touches_a) + len(touches_b) > 0


def test_sr_touch_checkpoint_carries_previous_close_for_first_bar_rearm():
    from msd.methods.sr_touch import detect
    features, levels, bars = _event_frames(
        [99.9, 97.9, 99.9], [100.1, 98.1, 100.1], [100.0, 98.0, 100.0])
    whole=detect(features,levels,bars)
    first,state,_=detect(features.iloc[:2],levels,bars.iloc[:2],return_state=True)
    second,final_state,_=detect(features.iloc[2:],levels,bars.iloc[2:],state=state,return_state=True)
    assert len(whole)==1
    assert first+second==whole
    assert second[0]["ts"]==bars.ts.iloc[2]
    assert state["last_close"]==98.0
    assert final_state["last_close"]==100.0


def test_level_ids_stay_stable_when_later_chunk_adds_levels():
    from msd.processing.levels import _stable_level_ids
    base = pd.DataFrame({
        "price": [100.0, 101.0], "type": ["swing_high", "prior_day_low"],
        "timeframe": ["15m", "1d"],
        "created_at": pd.to_datetime(["2023-01-01", "2023-01-02"], utc=True),
        "known_at": pd.to_datetime(["2023-01-01 01:00", "2023-01-03 00:00"], utc=True),
        "direction": [-1, 1],
    })
    later = pd.concat([base, pd.DataFrame({
        "price": [99.0], "type": ["swing_low"], "timeframe": ["1h"],
        "created_at": [pd.Timestamp("2023-01-04", tz="UTC")],
        "known_at": [pd.Timestamp("2023-01-05", tz="UTC")], "direction": [1],
    })], ignore_index=True)
    assert _stable_level_ids(base).tolist() == _stable_level_ids(later)[:len(base)].tolist()


def test_level_ids_are_identical_across_processes_and_collision_fails(monkeypatch):
    from msd.processing import levels
    rows={"price":[100.125,101.0],"type":["swing_high","prior_day_low"],
          "timeframe":["15m","1d"],"created_at":["2023-01-01T00:00:00Z","2023-01-02T00:00:00Z"],
          "known_at":["2023-01-01T01:00:00Z","2023-01-03T00:00:00Z"],"direction":[-1,1]}
    frame=pd.DataFrame(rows)
    expected=levels._stable_level_ids(frame).tolist()
    code=("import pandas as pd; from msd.processing.levels import _stable_level_ids; "
          f"print(_stable_level_ids(pd.DataFrame({rows!r})).tolist())")
    other=eval(subprocess.check_output([sys.executable,"-c",code],text=True).strip())
    assert other==expected

    monkeypatch.setattr(levels.hashlib,"blake2b",lambda *_a,**_k:type("Digest",(),{"digest":lambda _self:b"\\0"*8})())
    with pytest.raises(RuntimeError,match="collision"):
        levels._stable_level_ids(frame)


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


def test_sweep_pending_state_crosses_chunk_boundary_exactly():
    from msd.methods.liquidity_sweep import detect
    features, levels, bars = _event_frames(
        [99.8, 102.8, 99.8, 99.7], [100.1, 103.2, 100.3, 100.1],
        [100.0, 103.0, 100.1, 99.9])
    whole = detect(features, levels, bars)
    first, state, _ = detect(features.iloc[:3], levels, bars.iloc[:3], return_state=True)
    second, final, _ = detect(features.iloc[3:], levels, bars.iloc[3:], state=state, return_state=True)
    assert first + second == whole
    assert final["touch_counts"] == detect(features, levels, bars, return_state=True)[1]["touch_counts"]


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
