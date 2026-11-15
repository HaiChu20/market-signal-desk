from __future__ import annotations

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest

from msd.research.tiktok import common
from msd.research.tiktok_b2.prep import prepare

NY = ZoneInfo("America/New_York")


def _frame(days):
    rows = []
    for day, base, remove in days:
        start = pd.Timestamp(datetime.combine(day, time(9, 30)), tz=NY).tz_convert("UTC")
        stamps = pd.date_range(start, periods=390, freq="min")
        indexes = [i for i in range(390) if i not in set(remove)]
        for i in indexes:
            value = base + i * .01
            rows.append({"ts": stamps[i], **{f"{side}_{field}": value + offset
                for side, offset in (("bid", -.05), ("ask", .05)) for field in "ohlc"}})
    # Overnight feature timestamps used for Jan 2, 2019.
    for local_stamp, value in (("2019-01-01 18:00", 80.), ("2019-01-01 23:59", 81.),
                               ("2019-01-02 00:00", 82.), ("2019-01-02 02:00", 83.),
                               ("2019-01-02 04:59", 84.)):
        stamp = pd.Timestamp(local_stamp, tz=NY).tz_convert("UTC")
        rows.append({"ts": stamp, **{f"{side}_{field}": value + offset
            for side, offset in (("bid", -.05), ("ask", .05)) for field in "ohlc"}})
    return pd.DataFrame(rows).sort_values("ts").reset_index(drop=True)


def test_prepare_builds_mid_arrays_timezone_features_and_quality_skip_counts():
    frame = _frame([(date(2018, 12, 31), 100., ()),
                    (date(2019, 1, 2), 110., ()),
                    (date(2019, 1, 3), 120., ()),
                    (date(2019, 1, 4), 130., tuple(range(100, 107)))])
    prepared = prepare(frame, "USATECHIDXUSD")
    assert prepared.mid_o[0] == pytest.approx((frame.bid_o.iloc[0] + frame.ask_o.iloc[0]) / 2)
    assert str(prepared.ny.tz) == "America/New_York"
    jan2 = prepared.rth_days.loc[prepared.rth_days.day == date(2019, 1, 2)].iloc[0]
    assert jan2.complete
    jan4 = prepared.rth_days.loc[prepared.rth_days.day == date(2019, 1, 4)].iloc[0]
    assert not jan4.complete and jan4.skip_reason == "gap_over_5m"
    jan1 = prepared.rth_days.loc[prepared.rth_days.day == date(2019, 1, 1)].iloc[0]
    assert jan1.skip_reason == "holiday_or_half_day"
    assert prepared.pdh[date(2019, 1, 2)] == pytest.approx(prepared.rth_days.loc[
        prepared.rth_days.day == date(2018, 12, 31), "high"].iloc[0])
    assert prepared.globex_high[date(2019, 1, 2)] >= 110.
    assert prepared.asia_high[date(2019, 1, 2)] == pytest.approx(81.)
    assert prepared.london_high[date(2019, 1, 2)] == pytest.approx(84.)
    assert prepared.midnight_open[date(2019, 1, 2)] == pytest.approx(82.)
    assert len(prepared.fifteen) > 20 and len(prepared.five) > len(prepared.fifteen)
    assert len(prepared.atr1) == len(frame) and len(prepared.atr15_at) == len(frame)


def test_resample_closed_bars_supports_15m_without_changing_existing_timeframes():
    frame = _frame([(date(2019, 1, 2), 100., ())])
    five = common.resample_closed_bars(frame, 5)
    fifteen = common.resample_closed_bars(frame, 15)
    hourly = common.resample_closed_bars(frame, 60)
    assert len(five) > len(fifteen) > len(hourly)
    assert five.ts.is_monotonic_increasing and fifteen.ts.is_monotonic_increasing


def test_prepare_rejects_holdout_data_without_explicit_authorization():
    frame = _frame([(date(2019, 1, 2), 100., ())])
    frame.loc[frame.index[-1], "ts"] = pd.Timestamp("2023-01-01T00:00Z")
    with pytest.raises(ValueError, match="holdout"):
        prepare(frame, "USATECHIDXUSD")
    with pytest.raises(FileNotFoundError, match="selection"):
        prepare(frame, "USATECHIDXUSD", allow_holdout=True)
