from __future__ import annotations

from datetime import datetime, timedelta
import json
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest

from msd.research import swing_stage1 as swing
from msd.research.tiktok_b2_e import core


def _bars(times, prices=None, spread=0.2):
    times = pd.DatetimeIndex(times)
    values = np.asarray(prices if prices is not None else np.full(len(times), 100.0), dtype=float)
    frame = pd.DataFrame({"ts": times})
    for field in "ohlc":
        frame[f"bid_{field}"] = values - spread / 2
        frame[f"ask_{field}"] = values + spread / 2
    return frame


def test_hourly_atr_uses_only_completed_bars():
    times = pd.date_range("2021-01-01", periods=15 * 60, freq="min", tz="UTC")
    prices = np.repeat(np.arange(100.0, 115.0), 60)
    original = _bars(times, prices)
    changed = original.copy()
    for field in "ohlc":
        changed.loc[14 * 60 :, f"bid_{field}"] += 1000
        changed.loc[14 * 60 :, f"ask_{field}"] += 1000
    first = core.completed_hourly(original)
    second = core.completed_hourly(changed)
    known = pd.Timestamp("2021-01-01 14:00", tz="UTC")
    assert first.loc[first.known_at == known, "atr14"].iloc[0] == second.loc[
        second.known_at == known, "atr14"
    ].iloc[0]
    assert first.loc[first.known_at == known, "atr14"].notna().all()
    assert first.known_at.iloc[0] == pd.Timestamp("2021-01-01 01:00", tz="UTC")


def test_range_statistics_on_handmade_hourly_path():
    known = pd.date_range("2021-01-01 01:00", periods=6, freq="h", tz="UTC")
    close = np.arange(6.0)
    hourly = pd.DataFrame(
        {
            "known_at": known,
            "o": close,
            "h": close + 0.5,
            "l": close - 0.5,
            "c": close,
            "atr14": 1.0,
        }
    )
    result = core.range_statistics(
        hourly, known[0], known[0] + pd.Timedelta(minutes=1)
    )
    row = next(item for item in result["overall"] if item["N"] == 4)
    assert row["close_move"]["samples"] == 1
    assert row["close_move"]["median"] == 4.0
    assert row["path_range"]["median"] == 4.0
    assert row["atr_sqrt_N"]["median"] == 2.0


def test_stop_hit_and_both_return_windows_on_handmade_minute_path():
    times = pd.date_range("2021-01-01", periods=4, freq="min", tz="UTC")
    minute = {
        "ts": times.asi8,
        "h": np.array([100.0, 99.2, 100.2, 100.1]),
        "l": np.array([100.0, 98.5, 99.5, 99.8]),
    }
    assert core.path_hit_and_returns(minute, 0, 4, 100.0, 99.0, 1) == (
        True,
        True,
        True,
    )
    assert core.path_hit_and_returns(minute, 0, 4, 100.0, 101.0, -1) == (
        False,
        False,
        False,
    )


def _swing_sample() -> pd.DataFrame:
    ny = ZoneInfo("America/New_York")
    times, prices = [], []
    day = datetime(2019, 12, 1)
    for offset in range(150):
        current = day + timedelta(days=offset)
        close = pd.Timestamp(
            datetime(current.year, current.month, current.day, 16, 59), tz=ny
        ).tz_convert("UTC")
        entry = pd.Timestamp(current.date(), tz="UTC") + pd.Timedelta(hours=7)
        times.extend([entry, close])
        level = 100.0 + offset
        prices.extend([level, level + 0.5])
    order = np.argsort(pd.DatetimeIndex(times).asi8)
    return _bars(pd.DatetimeIndex(times)[order], np.asarray(prices)[order])


def test_original_e2_rule_is_exact_swing_stage1_replay():
    bars = _swing_sample()
    period = swing.Period(
        data_start=pd.Timestamp("2019-12-01", tz="UTC"),
        score_start=pd.Timestamp("2020-01-01", tz="UTC"),
        end=pd.Timestamp("2020-05-01", tz="UTC"),
    )
    expected = swing.evaluate_market(
        bars, "USATECHIDXUSD", primary_only=True, period=period, setups=("S1", "S2")
    )
    actual = core.original_trades(bars, "USATECHIDXUSD", period)
    assert actual == expected
    assert actual[0]


def test_e2_holdout_requires_flag_selection_and_once_only_output(tmp_path):
    selection = tmp_path / "selection.json"
    output = tmp_path / "holdout.json"
    with pytest.raises(PermissionError, match="--run-e2-holdout-once"):
        core.require_e2_holdout(False, selection, output)
    with pytest.raises(FileNotFoundError, match="selection"):
        core.require_e2_holdout(True, selection, output)
    selection.write_text(
        json.dumps(
            {
                "selection": {
                    setup: {"params": {"c": 0.75, "N": 24, "tp_R": 2.0}}
                    for setup in core.E2_SETUPS
                }
            }
        )
    )
    assert core.require_e2_holdout(True, selection, output)["selection"]
    output.write_text("{}")
    with pytest.raises(FileExistsError, match="already exists"):
        core.require_e2_holdout(True, selection, output)
