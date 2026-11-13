import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal

from msd.methods.range_bounce import active_ranges
from msd.research.range_bounce_stage1 import DEV_END, label_setups


def _candles(periods=160, frequency="15min"):
    ts = pd.date_range("2021-01-01", periods=periods, freq=frequency, tz="UTC")
    x = np.arange(periods)
    close = 100+2*np.sin(2*np.pi*x/12)
    return pd.DataFrame({"ts": ts, "known_at": ts+pd.Timedelta(frequency),
                         "bid_h": close+.12, "bid_l": close-.12, "bid_c": close})


def test_range_detector_is_truncation_causal():
    bars = _candles()
    full = active_ranges(bars, "15m")
    cut = 117
    prefix = active_ranges(bars.iloc[:cut], "15m")
    assert_frame_equal(full.iloc[:cut].reset_index(drop=True), prefix.reset_index(drop=True))
    assert full.active.any(), "fixture must exercise an active range"


def test_time_exit_never_exceeds_effective_deadline():
    ts = pd.date_range("2021-01-01", periods=8*24*60, freq="1min", tz="UTC")
    price = np.full(len(ts), 96.0)
    bars = pd.DataFrame({"ts": ts})
    for field in "ohlc":
        bars[f"bid_{field}"] = price-.01
        bars[f"ask_{field}"] = price+.01
    candidate = pd.DataFrame([{"symbol": "BTCUSDT", "timeframe": "15m", "range_id": "r",
        "edge": "bottom", "side": 1, "ts": ts[0], "known_at": ts[1], "entry_index": 1,
        "entry_ts": ts[1], "entry_price": 96.01, "top": 105., "bottom": 95., "atr": 2.,
        "height_atr": 5., "age_candles": 12, "top_touches": 2, "bottom_touches": 2}])
    labels = label_setups(candidate, bars, "BTCUSDT")
    assert len(labels) == 15
    assert labels.exit_reason.eq("time").all()
    assert (labels.net_R < 0).all(), "one executable spread must be charged from ask entry to bid exit"
    assert (pd.to_datetime(labels.exit_ts, utc=True) <= pd.to_datetime(labels.deadline_ts, utc=True)).all()
    assert labels.exit_ts.eq(labels.deadline_ts).all()
    assert pd.to_datetime(labels.exit_ts, utc=True).max() < DEV_END
    assert (labels.planned_risk >= .1*labels.atr).all()


def test_setup_below_point_one_atr_risk_is_dropped_whole():
    ts=pd.date_range("2021-01-01",periods=8*24*60,freq="1min",tz="UTC")
    bars=pd.DataFrame({"ts":ts})
    for field in "ohlc":
        bars[f"bid_{field}"]=94.54
        bars[f"ask_{field}"]=94.56
    candidate=pd.DataFrame([{"symbol":"BTCUSDT","timeframe":"15m","range_id":"r","edge":"bottom",
        "side":1,"ts":ts[0],"known_at":ts[1],"entry_index":1,"entry_ts":ts[1],"entry_price":94.56,
        "top":105.,"bottom":95.,"atr":2.,"height_atr":5.,"age_candles":12,
        "top_touches":2,"bottom_touches":2}])
    labels=label_setups(candidate,bars,"BTCUSDT")
    assert labels.empty
    assert labels.attrs["dropped_risk_setups"]==1
