import numpy as np
import pandas as pd
from msd.levels import confirmed_swings, prepare


def test_swing_requires_three_right_bars():
    high=np.array([1,2,3,5,3,2,1,1.],float)
    peaks,troughs=confirmed_swings(high,-high)
    assert np.isnan(peaks[:6]).all() and peaks[6] == 5 and troughs[6] == -5


def test_opening_range_ready_at_0945_close():
    ts=pd.date_range(pd.Timestamp("2024-06-12 09:30",tz="America/New_York"),periods=30,freq="min").tz_convert("UTC")
    frame=pd.DataFrame({"ts":ts,"volume":np.ones(30)})
    for side in ("bid","ask"):
        for field in "ohlc": frame[f"{side}_{field}"]=100.+(side=="ask")*.1
    frame.loc[14,["bid_h","ask_h"]]=[102.,102.1]
    context=prepare(frame,"USATECHIDXUSD")
    assert np.isnan(context.levels["orh"][13]) and context.levels["orh"][14] == 102.05
