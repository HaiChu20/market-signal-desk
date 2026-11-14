from datetime import date

import numpy as np
import pandas as pd
import pytest

from msd.research.tiktok import common, strategy_a


def _rth_bars(*, breakout="long"):
    pieces = []
    for day, start in ((date(2022, 1, 3), "2022-01-03 14:30Z"),
                       (date(2022, 1, 4), "2022-01-04 14:30Z")):
        ts = pd.date_range(start, periods=390, freq="min")
        base = np.full(390, 100.)
        part = pd.DataFrame({"ts": ts})
        for field in "ohlc":
            part[f"bid_{field}"] = base - .1
            part[f"ask_{field}"] = base + .1
        if day.day == 3:
            part.loc[100, ["bid_h", "ask_h"]] = [110., 110.2]
            part.loc[200, ["bid_l", "ask_l"]] = [89.8, 90.]
        elif breakout == "long":
            part.loc[10, "ask_h"] = 111.
            part.loc[25, "ask_h"] = 112.
            part.loc[389, ["bid_c", "ask_c"]] = [101.9, 102.1]
        elif breakout == "short":
            part.loc[10, "bid_l"] = 89.
        else:
            part.loc[10, ["ask_h", "bid_l"]] = [111., 89.]
        pieces.append(part)
    return pd.concat(pieces, ignore_index=True)


def _params(**updates):
    return {**strategy_a.DEFAULT_PARAMS, **updates}


def test_grid_and_default_match_frozen_24_cell_spec():
    assert len(strategy_a.GRID) == 24
    assert strategy_a.DEFAULT_PARAMS == {
        "session": "rth", "k": .5, "stop": "opposite_trigger", "direction": "both"
    }


def test_first_breakout_only_one_trade_per_day_and_stop_then_close():
    bars = _rth_bars()
    rows = strategy_a.simulate(bars, "USATECHIDXUSD", _params())
    assert len(rows) == 1
    trade = rows[0]
    assert tuple(trade) == common.TRADE_KEYS
    assert trade["entry_ts"] == "2022-01-04T14:40:00+00:00"
    assert trade["exit_ts"] == "2022-01-04T20:59:00+00:00"
    assert trade["exit_reason"] == "session_close"
    assert trade["side"] == 1
    assert trade["risk_points"] > 0
    assert trade["period"] == "dev"


def test_long_only_ignores_short_but_both_sides_use_first_trigger():
    short = _rth_bars(breakout="short")
    both = strategy_a.simulate(short, "USATECHIDXUSD", _params())
    long_only = strategy_a.simulate(short, "USATECHIDXUSD", _params(direction="long_only"))
    assert len(both) == 1 and both[0]["side"] == -1
    assert long_only == []


def test_same_minute_double_trigger_is_skipped_as_ambiguous():
    bars = _rth_bars(breakout="both")
    assert strategy_a.simulate(bars, "USATECHIDXUSD", _params()) == []


def test_random_exit_callback_reuses_entry_time_and_stop_rule():
    bars = _rth_bars()
    params = _params()
    trades = strategy_a.simulate(bars, "USATECHIDXUSD", params)
    callback = strategy_a.random_exit_factory(bars, "USATECHIDXUSD", params)
    long_out = callback(trades[0], 1)
    short_out = callback(trades[0], -1)
    assert long_out["entry_ts"] == trades[0]["entry_ts"]
    assert short_out["entry_ts"] == trades[0]["entry_ts"]
    assert long_out["side"] == 1 and short_out["side"] == -1


def test_holdout_bars_are_refused_before_simulation_without_explicit_flag():
    bars = _rth_bars()
    extra = bars.iloc[-1:].copy()
    extra["ts"] = pd.Timestamp("2023-01-03 14:30Z")
    bars = pd.concat([bars, extra], ignore_index=True)
    with pytest.raises(PermissionError):
        strategy_a.simulate(bars, "USATECHIDXUSD", _params())
