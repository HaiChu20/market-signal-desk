import numpy as np
import pandas as pd
import pytest

from msd.research.swing_stage1 import (CUT, cap_index, cost_r, daily_bars, entry_index,
                                       exit_trade, globex, ny_day_end, signals)


def stamps(values):
    return pd.DatetimeIndex(pd.to_datetime(values, utc=True))


def bars(values, closes):
    frame = pd.DataFrame({"ts": stamps(values)})
    for side in ("bid", "ask"):
        for field in "ohlc":
            frame[f"{side}_{field}"] = closes
    return frame


def test_ny_cut_across_dst():
    ts = stamps(["2022-03-11 21:59Z", "2022-03-11 22:00Z",
                 "2022-03-14 20:59Z", "2022-03-14 21:00Z"])
    result = ny_day_end(ts)
    assert list(result) == list(stamps(["2022-03-11 22:00Z", "2022-03-12 22:00Z",
                                       "2022-03-14 21:00Z", "2022-03-15 21:00Z"]))


def test_no_lookahead_signal():
    ends = pd.date_range("2022-01-01 22:00Z", periods=23, freq="D")
    frame = pd.DataFrame({"end": ends, "c": [100.]*21+[101., 200.],
                          "atr": [1.]*23})
    signal = signals(frame, 2021)
    assert signal.S1.iloc[21] == 1
    assert signal.S1.iloc[20] == 0
    assert signal.S1.iloc[22] == 1
    frame.loc[22, "c"] = 50.
    assert signals(frame, 2021).S1.iloc[21] == 1


def test_entry_timing():
    ts = stamps(["2022-03-13 22:00Z", "2022-03-14 07:00Z"])
    assert entry_index(ts, pd.Timestamp("2022-03-11 22:00Z")) == 1
    assert entry_index(ts, pd.Timestamp("2022-03-11 22:00Z"), True) == 0
    assert entry_index(ts, pd.Timestamp("2022-03-12 22:00Z"), True) == 0


def test_globex_and_btc_weekend_gap():
    ts = stamps(["2022-03-11 21:59Z", "2022-03-12 12:00Z",
                 "2022-03-13 21:59Z", "2022-03-13 22:00Z"])
    mask = globex(ts)
    assert list(mask) == [True, False, False, True]
    prices = np.array([[100.,100.,100.,100.], [80.,80.,80.,80.],
                       [80.,80.,80.,80.], [85.,85.,85.,85.]])
    assert exit_trade(ts, prices, mask, 0, 1, 90., 120., 4) == (3, 85., "sl")


def test_same_minute_sl_first():
    ts = stamps(["2022-03-14 12:00Z", "2022-03-14 12:01Z"])
    prices = np.array([[100.]*4, [100., 120., 80., 100.]])
    assert exit_trade(ts, prices, globex(ts), 0, 1, 90., 110., 2) == (1, 90., "sl")


def test_entry_minute_is_executable():
    ts = stamps(["2022-03-14 12:00Z", "2022-03-14 12:01Z"])
    prices = np.array([[100., 120., 80., 100.], [100.]*4])
    assert exit_trade(ts, prices, globex(ts), 0, 1, 90., 110., 2) == (0, 90., "sl")


def test_cap_exit():
    ts = stamps(["2022-03-14 12:00Z", "2022-03-14 12:01Z", "2022-03-14 12:02Z"])
    prices = np.array([[100.]*4, [101.]*4, [102.]*4])
    assert exit_trade(ts, prices, globex(ts), 0, 1, 90., 110., 2) == (2, 102., "cap")


def test_cap_after_thirty_trading_sessions():
    ts = pd.date_range("2022-01-03 12:00Z", periods=32, freq="B")
    assert cap_index(ts, 0, ny_day_end(ts), globex(ts)) == 30


def test_cost_to_r():
    # MNQ: 0.25 spread + 1.25 commission + 0.25 stop slip = 1.75 points.
    assert cost_r("MNQ", "USATECHIDXUSD", 100., 2., 1, 0., "sl") == .875
    assert cost_r("MNQ", "USATECHIDXUSD", 100., 2., 1, 0., "tp") == .75
    assert cost_r("MNQ", "USATECHIDXUSD", 100., 2., -1, 365.25, "tp") < cost_r("MNQ", "USATECHIDXUSD", 100., 2., 1, 365.25, "tp")


def test_dev_cutoff():
    frame = bars(["2022-12-31 22:00Z", "2023-01-01 00:00Z"], [1., 2.])
    with pytest.raises(ValueError):
        daily_bars(frame)
    assert CUT == pd.Timestamp("2023-01-01", tz="UTC")
