import pandas as pd
import pytest

from msd.research.method_registry import load_registry
from msd.research.tournament import validate_schema


def test_method_schema_guard_and_dev_end_guard():
    spec=next(item for item in load_registry() if item.name=='sr_touch')
    frame=pd.DataFrame({'known_at':[pd.Timestamp('2022-12-31',tz='UTC')],
        'label_end_ts':[pd.Timestamp('2022-12-31 01:00',tz='UTC')]})
    with pytest.raises(ValueError,match='missing required'):
        validate_schema(frame,spec)

    required={'sym':'BTCUSDT','method':'sr_touch','event_key':'e','side':1,'price':100.,
        'sl':99.,'tp':101.,'planned_risk':1.,'tp_first':1,'net_R':1.,'gross_R':1.,
        'p0':.5,'TP_R':1.,'cost_R':0.,'financing_R':0.,'feature':1.}
    good=pd.DataFrame([{**required,'known_at':pd.Timestamp('2022-12-31',tz='UTC'),
                        'label_end_ts':pd.Timestamp('2022-12-31 01:00',tz='UTC')}])
    validate_schema(good,spec)
    bad=good.copy();bad['label_end_ts']=pd.Timestamp('2023-01-01',tz='UTC')
    with pytest.raises(ValueError,match='crosses'):validate_schema(bad,spec)
