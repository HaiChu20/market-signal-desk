from types import SimpleNamespace

import numpy as np
import pandas as pd

from msd.research.wide_pure_rules import _finite, _load_unit, evaluate_unit


def test_repairs_market_event_keys_and_serializes_nonfinite(tmp_path):
    root=tmp_path/"events";path=root/"BTCUSDT"/"2022-01.parquet";path.parent.mkdir(parents=True)
    rows=[]
    for event in range(12):
        for sl in (1.,1.5):
            for tp in (1.,2.):
                ts=pd.Timestamp("2022-01-01",tz="UTC")+pd.Timedelta(days=event)
                rows.append({"method":"sr_touch","variant":None,"sym":"BTCUSDT","event_key":None,
                    "ts":ts,"side":1,"entry_type":"market","limit_price":np.nan,
                    "known_at":ts+pd.Timedelta(minutes=1),"entry_ts":ts+pd.Timedelta(minutes=2),
                    "label_end_ts":ts+pd.Timedelta(hours=1),"sl_atr":sl,"tp_r":tp,
                    "net_R":1. if (sl,tp)==(1.5,2.) else -1.,"spread_R":.1,"outcome":"tp"})
    pd.DataFrame(rows).to_parquet(path,index=False)
    spec=SimpleNamespace(symbols=("BTCUSDT",),name="sr_touch",variant=None,key="sr_touch")
    frame=_load_unit(root,spec)
    assert frame.event_key.notna().all()
    assert frame.event_key.nunique()==12
    signals,metrics,*_=evaluate_unit(frame)
    assert len(signals)>0 and metrics["net_avg_R"]>0
    assert _finite({"x":float("nan"),"y":np.float64(1)})=={"x":None,"y":1.}
