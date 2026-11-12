import pandas as pd
import pytest

from msd.processing.instruments import STAGE9_INSTRUMENTS, label_parameters
from msd.processing.timeframes import build_timeframe


def bars(ts):
    frame = pd.DataFrame({"ts": ts})
    for side, offset in (("bid", 0.0), ("ask", 0.2)):
        for field in "ohlc":
            frame[f"{side}_{field}"] = 100.0 + offset
    frame["volume"] = 1.0
    return frame


@pytest.mark.parametrize("symbol,zone,opened,closed", [
    ("USA30IDXUSD", "America/New_York", "2025-01-05 18:00", "2025-01-06 16:15"),
    ("DEUIDXEUR", "Europe/Berlin", "2025-01-06 00:00", "2025-01-06 22:15"),
    ("GBRIDXGBP", "Europe/London", "2025-01-05 23:00", "2025-01-06 21:15"),
    ("XAGUSD", "America/New_York", "2025-01-05 18:00", "2025-01-06 17:00"),
    ("LIGHTCMDUSD", "America/New_York", "2025-01-05 18:00", "2025-01-06 17:00"),
    ("BRENTCMDUSD", "Europe/London", "2025-01-06 00:00", "2025-01-06 22:00"),
])
def test_measured_session_daily_bar_is_dst_aware(symbol, zone, opened, closed):
    start, end = pd.Timestamp(opened, tz=zone), pd.Timestamp(closed, tz=zone)
    ts = pd.date_range(start, end, freq="min", inclusive="left").tz_convert("UTC")
    result = build_timeframe(bars(ts), symbol, "1d")
    assert len(result) == 1
    assert result.ts.iloc[0] == start.tz_convert("UTC")
    assert result.known_at.iloc[0] == end.tz_convert("UTC")
    assert result.observed_minutes.iloc[0] == result.expected_minutes.iloc[0] == len(ts)


@pytest.mark.parametrize("symbol", ["EURUSD", "USDJPY", "GBPUSD"])
def test_fx_daily_bar_uses_1700_new_york_rollover(symbol):
    start = pd.Timestamp("2025-07-06 17:00", tz="America/New_York")
    ts = pd.date_range(start, periods=1440, freq="min").tz_convert("UTC")
    result = build_timeframe(bars(ts), symbol, "1d")
    assert len(result) == 1
    assert result.ts.iloc[0] == start.tz_convert("UTC")
    assert result.known_at.iloc[0] == (start + pd.Timedelta(days=1)).tz_convert("UTC")


def test_pending_nikkei_session_fails_closed():
    ts = pd.date_range("2025-01-06", periods=60, freq="min", tz="UTC")
    with pytest.raises(ValueError, match="pending measurement"):
        build_timeframe(bars(ts), "JPNIDXJPY", "1h")


def test_stage9_label_specs_are_explicit():
    assert set(STAGE9_INSTRUMENTS) == {"USA30IDXUSD", "DEUIDXEUR", "GBRIDXGBP", "JPNIDXJPY",
                                          "XAGUSD", "EURUSD", "USDJPY", "GBPUSD",
                                          "LIGHTCMDUSD", "BRENTCMDUSD"}
    assert label_parameters("USA30IDXUSD") == ("index", .0002)
    assert label_parameters("EURUSD") == ("fx", .00015)
    assert label_parameters("LIGHTCMDUSD") == ("energy", .0002)
    assert label_parameters("BRENTCMDUSD") == ("energy", .0002)
