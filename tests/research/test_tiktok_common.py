from datetime import date

import numpy as np
import pandas as pd
import pytest

from msd.research.tiktok import common


def _bars(times, price=100.0, spread=0.2):
    frame = pd.DataFrame({"ts": pd.to_datetime(times, utc=True)})
    for field in "ohlc":
        frame[f"bid_{field}"] = float(price) - spread / 2
        frame[f"ask_{field}"] = float(price) + spread / 2
    return frame


def test_market_sessions_follow_dst_and_frozen_hours():
    winter = common.session_bounds("USATECHIDXUSD", date(2022, 1, 10), "rth")
    summer = common.session_bounds("USATECHIDXUSD", date(2022, 7, 11), "rth")
    assert winter == (pd.Timestamp("2022-01-10 14:30Z"), pd.Timestamp("2022-01-10 21:00Z"))
    assert summer == (pd.Timestamp("2022-07-11 13:30Z"), pd.Timestamp("2022-07-11 20:00Z"))
    full = common.session_bounds("USATECHIDXUSD", date(2022, 7, 11), "full_day")
    assert full == (pd.Timestamp("2022-07-10 22:00Z"), pd.Timestamp("2022-07-11 21:00Z"))
    dax = common.session_bounds("DEUIDXEUR", date(2022, 1, 10), "full_day")
    assert dax == (pd.Timestamp("2022-01-09 23:00Z"), pd.Timestamp("2022-01-10 23:00Z"))


def test_resample_emits_only_fully_closed_bars():
    times = pd.date_range("2022-01-03 14:30Z", periods=11, freq="min")
    bars = _bars(times)
    five = common.resample_closed_bars(bars, 5)
    assert five.ts.tolist() == [pd.Timestamp("2022-01-03 14:35Z"),
                                pd.Timestamp("2022-01-03 14:40Z")]
    hour = common.resample_closed_bars(_bars(pd.date_range("2022-01-03", periods=61,
                                                          freq="min", tz="UTC")), 60)
    assert hour.ts.tolist() == [pd.Timestamp("2022-01-03 01:00Z")]


def test_dev_loader_uses_only_2022_end_day_and_holdout_requires_explicit_flag(monkeypatch):
    seen = {}

    def fake_load(symbol, start, end, source, raw):
        seen.update(symbol=symbol, start=start, end=end, source=source, raw=raw)
        return _bars(["2022-12-31 23:59Z"])

    monkeypatch.setattr(common, "load_data", fake_load)
    loaded = common.load_1m("USATECHIDXUSD")
    assert seen["end"] == pd.Timestamp("2022-12-31T00:00Z")
    assert seen["source"] == "dukascopy" and seen["raw"] is True
    assert loaded.ts.max() < common.HOLDOUT_START
    with pytest.raises(PermissionError):
        common.load_1m("USATECHIDXUSD", common.WARMUP_START,
                       pd.Timestamp("2023-01-02", tz="UTC"))
    assert len(loaded) == 1


def test_shared_record_costs_r_and_holdout_guard():
    duka = common.build_trade_record(
        "USATECHIDXUSD", "A", {"k": .5}, 1, "2022-04-01T10:00Z", "2022-04-01T11:00Z",
        100.1, 101.9, 2., gross_entry=100., gross_exit=102.,
        entry_spread=.2, exit_spread=.2, exit_reason="session_close",
    )
    assert tuple(duka) == common.TRADE_KEYS
    assert duka["gross_R"] == 1.
    assert duka["net_R"] == pytest.approx(.9)
    assert duka["net_R_cost15"] == pytest.approx(.85)
    crypto = common.build_trade_record(
        "BTCUSDT", "A", {"k": .5}, 1, "2022-04-01T10:00Z", "2022-04-01T11:00Z",
        100., 110., 10., exit_reason="session_close",
    )
    assert crypto["net_R"] == pytest.approx(.9895)
    assert crypto["net_R_cost15"] == pytest.approx(.98425)
    with pytest.raises(PermissionError):
        common.build_trade_record("BTCUSDT", "A", {}, 1, "2023-01-01T00:00Z",
                                  "2023-01-01T01:00Z", 100., 101., 1.,
                                  exit_reason="session_close")


def test_metrics_and_fixed_entry_random_direction_precompute_two_outcomes():
    rows = [
        common.build_trade_record("BTCUSDT", "A", {}, side, f"2022-01-0{i}T10:00Z",
                                  f"2022-01-0{i}T11:00Z", 100., 101. if side > 0 else 99.,
                                  1., exit_reason="session_close")
        for i, side in ((1, 1), (2, -1), (3, 1))
    ]
    summary = common.required_outputs(rows)
    assert summary["overall"]["trades"] == 3
    assert summary["overall"]["exit_reason_counts"] == {"session_close": 3}
    calls = []

    def fake_exit(trade, side):
        calls.append((trade["entry_ts"], side))
        return float(side)

    result = common.random_entry_benchmark(rows, fake_exit, seeds=1000, seed=3)
    assert len(calls) == 2 * len(rows)
    assert result["seeds"] == 1000
    assert 0 <= result["random_percentile"] <= 100


def test_metrics_reject_holdout_without_explicit_guard():
    record = common.build_trade_record(
        "BTCUSDT", "A", {}, 1, "2023-01-01T10:00Z", "2023-01-01T11:00Z",
        100., 101., 1., exit_reason="session_close", allow_holdout=True,
    )
    with pytest.raises(PermissionError):
        common.metrics([record])
    assert common.metrics([record], allow_holdout=True)["trades"] == 1
