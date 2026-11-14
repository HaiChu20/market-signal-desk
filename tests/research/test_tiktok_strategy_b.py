from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from msd.research.tiktok import strategy_b


PARAMS = {
    "fast_ema": 2,
    "slow_ema": 2,
    "stop_atr": 1.0,
    "exit_mode": "close",
    "overlap": "single",
    "time_stop_days": None,
}


def _bars(times, price=100.0, spread=0.2) -> pd.DataFrame:
    times = pd.DatetimeIndex(times)
    values = np.full(len(times), float(price))
    frame = pd.DataFrame({"ts": times, "volume": 1.0})
    for field in "ohlc":
        frame[f"bid_{field}"] = values - spread / 2
        frame[f"ask_{field}"] = values + spread / 2
    return frame


def _candidate(ts, *, side=1, entry=100.1, risk=1.0, deadline=None) -> dict:
    return {
        "day": date(2021, 6, 1),
        "entry_ts": pd.Timestamp(ts),
        "entry_i": 0,
        "entry_price": entry,
        "side": side,
        "risk": risk,
        "initial_stop": entry - side * risk,
        "initial_slow": np.nan,
        "time_deadline": deadline,
    }


def _hourly(rows) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["known_at", "mid_close", "slow_ema"])


def test_entry_is_next_bar_open_and_session_clock_handles_us_dst():
    friday = pd.date_range("2021-03-12 14:30", periods=391, freq="min", tz="UTC")
    monday = pd.date_range("2021-03-15 13:30", periods=391, freq="min", tz="UTC")
    bars = _bars(friday.append(monday))
    sessions = strategy_b._complete_sessions(bars, "EURUSD")
    five = pd.DataFrame(
        {
            "ts": [
                sessions[0][1] + pd.Timedelta(minutes=5),
                sessions[1][1] + pd.Timedelta(minutes=5),
            ],
            "known_at": [
                sessions[0][1] + pd.Timedelta(minutes=5),
                sessions[1][1] + pd.Timedelta(minutes=5),
            ],
            "mid_close": [101.0, 101.0],
            "fast_ema": [100.0, 100.0],
        }
    )
    hourly = pd.DataFrame(
        {
            "known_at": [
                pd.Timestamp("2021-03-12 14:00", tz="UTC"),
                pd.Timestamp("2021-03-15 13:00", tz="UTC"),
            ],
            "atr14": [1.0, 1.0],
            "slow_ema": [100.0, 100.0],
        }
    )
    candidates = strategy_b._entry_candidates(
        bars, "EURUSD", PARAMS, five, hourly, sessions
    )
    assert [row["entry_ts"] for row in candidates] == [
        pd.Timestamp("2021-03-12 14:35", tz="UTC"),
        pd.Timestamp("2021-03-15 13:35", tz="UTC"),
    ]
    assert all(row["entry_price"] == 100.1 for row in candidates)


def test_indicator_bars_use_common_complete_right_labelled_resampler():
    times = pd.date_range("2021-06-01", periods=120, freq="min", tz="UTC")
    five, hourly = strategy_b._indicator_bars(_bars(times), "JPNIDXJPY", 2, 2)
    assert five.known_at.iloc[0] == pd.Timestamp("2021-06-01 00:05", tz="UTC")
    assert hourly.known_at.tolist() == [
        pd.Timestamp("2021-06-01 01:00", tz="UTC"),
        pd.Timestamp("2021-06-01 02:00", tz="UTC"),
    ]


def test_same_minute_stop_wins_over_hourly_close_exit():
    times = pd.date_range("2021-06-01 13:35", periods=2, freq="min", tz="UTC")
    bars = _bars(times)
    bars.loc[1, "bid_l"] = 98.0
    hourly = _hourly(
        [(times[1], 98.0, 100.5)]
    )
    trade = strategy_b._simulate_candidate(
        bars, hourly, "EURUSD", PARAMS, _candidate(times[0])
    )
    assert trade is not None
    assert trade["exit_reason"] == "stop"
    assert trade["exit_price"] == 99.1
    assert trade["net_R"] == -1.0


def test_touch_trail_activates_and_never_loosens():
    times = pd.date_range("2021-06-01 13:35", periods=3, freq="min", tz="UTC")
    bars = _bars(times)
    for field in "ohlc":
        bars.loc[1, f"bid_{field}"] = 101.1
        bars.loc[1, f"ask_{field}"] = 101.3
        bars.loc[2, f"bid_{field}"] = 101.9
        bars.loc[2, f"ask_{field}"] = 102.1
    bars.loc[2, "bid_l"] = 100.5
    hourly = _hourly(
        [
            (times[1], 101.2, 101.0),
            (times[2], 102.0, 100.0),
        ]
    )
    params = {**PARAMS, "exit_mode": "touch"}
    trade = strategy_b._simulate_candidate(
        bars, hourly, "EURUSD", params, _candidate(times[0])
    )
    assert trade is not None
    assert trade["exit_reason"] == "slow_ema_touch"
    assert trade["exit_price"] == 101.0


def test_stop_gap_fills_at_first_available_open():
    times = pd.DatetimeIndex(
        [pd.Timestamp("2021-06-04 20:59", tz="UTC"), pd.Timestamp("2021-06-06 22:00", tz="UTC")]
    )
    bars = _bars(times)
    for field in "ohlc":
        bars.loc[1, f"bid_{field}"] = 97.9
        bars.loc[1, f"ask_{field}"] = 98.1
    trade = strategy_b._simulate_candidate(
        bars, _hourly([]), "EURUSD", PARAMS, _candidate(times[0])
    )
    assert trade is not None
    assert trade["exit_ts"] == times[1]
    assert trade["exit_price"] == 97.9
    assert trade["exit_reason"] == "stop"


def test_overlap_single_skips_open_trade_but_daily_keeps_each_day(monkeypatch):
    times = pd.date_range("2021-06-01", periods=4, freq="D", tz="UTC")
    bars = _bars(times)
    candidates = [
        _candidate(times[0]),
        {**_candidate(times[1]), "entry_i": 1},
        {**_candidate(times[2]), "entry_i": 2},
    ]
    exits = [times[2], times[2] + pd.Timedelta(hours=1), times[3]]

    monkeypatch.setattr(strategy_b, "_indicator_bars", lambda *args: (pd.DataFrame(), pd.DataFrame()))
    monkeypatch.setattr(strategy_b, "_complete_sessions", lambda *args: [])
    monkeypatch.setattr(strategy_b, "_entry_candidates", lambda *args: candidates)

    def fake_trade(_bars, _hourly, market, params, candidate):
        index = candidates.index(candidate)
        return {
            "market": market,
            "strategy": "B",
            "params": dict(params),
            "period": "dev",
            "side": 1,
            "entry_ts": candidate["entry_ts"],
            "exit_ts": exits[index],
            "entry_price": 100.1,
            "exit_price": 100.2,
            "risk_points": 1.0,
            "gross_R": 0.2,
            "net_R": 0.1,
            "net_R_cost15": 0.05,
            "exit_reason": "slow_ema_close",
        }

    monkeypatch.setattr(strategy_b, "_simulate_candidate", fake_trade)
    single = strategy_b.simulate(bars, "BTCUSDT", PARAMS)
    daily = strategy_b.simulate(bars, "BTCUSDT", {**PARAMS, "overlap": "daily"})
    assert [row["entry_ts"] for row in single] == [times[0], times[2]]
    assert [row["entry_ts"] for row in daily] == list(times[:3])


def test_shared_schema_and_cost15_widens_each_dukascopy_half_spread():
    times = pd.date_range("2021-06-01", periods=2, freq="min", tz="UTC")
    bars = _bars(times)
    record = strategy_b._fill_record(
        bars, "EURUSD", PARAMS, _candidate(times[0]), 1, 100.9, "slow_ema_close"
    )
    assert set(record) == {
        "market",
        "strategy",
        "params",
        "period",
        "side",
        "entry_ts",
        "exit_ts",
        "entry_price",
        "exit_price",
        "risk_points",
        "gross_R",
        "net_R",
        "net_R_cost15",
        "exit_reason",
    }
    assert np.isclose(record["gross_R"], 1.0)
    assert np.isclose(record["net_R"], 0.8)
    assert np.isclose(record["net_R_cost15"], 0.7)
