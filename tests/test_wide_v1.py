import json
from pathlib import Path

import numpy as np
import pandas as pd

from msd.processing.crypto_perp import executable_perp_bars
from msd.processing.labels import label_grid
from msd.processing.wide_v1 import load_config


def test_wide_config_controls_fifty_options_and_invalid_atr_is_skipped():
    config=load_config(Path("hpc/roihu/sequence/configs/wide_v1.json"))
    ts=pd.date_range("2022-01-03",periods=20,freq="1min",tz="UTC")
    raw=pd.DataFrame({"ts":ts})
    for side in ("bid","ask"):
        for field in "ohlc":raw[f"{side}_{field}"]=100.+np.arange(len(ts))*.01
    bars=executable_perp_bars(raw,"BTCUSDT")
    atr=pd.Series(1.,index=bars.index);atr.iloc[0]=0
    labels=label_grid(bars,atr,every_minutes=15,max_trading_days=1,financing_per_night=0.,
        signal_start=ts[0],signal_end=ts[1],sl_grid=tuple(config["sl_atr"]),
        tp_grid=tuple(config["tp_r"]),tp_is_r_multiple=True)
    assert labels.empty
    labels=label_grid(bars,pd.Series(1.,index=bars.index),every_minutes=15,max_trading_days=1,
        financing_per_night=0.,signal_start=ts[0],signal_end=ts[1],
        sl_grid=tuple(config["sl_atr"]),tp_grid=tuple(config["tp_r"]),tp_is_r_multiple=True)
    assert len(labels)==50
    assert set(labels.sl_atr)==set(config["sl_atr"])
    assert set(labels.tp_r)==set(config["tp_r"])
    assert np.allclose(labels.tp_atr,labels.sl_atr*labels.tp_r)
