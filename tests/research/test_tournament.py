import hashlib
import json
import pandas as pd
import pytest

from msd.research.method_registry import load_registry
from msd.research.tournament import validate_schema,verify_frozen_events


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


def test_frozen_events_sha_match_and_mismatch(tmp_path):
    events=tmp_path/'data/events';path=events/'BTCUSDT/2022-01.parquet'
    path.parent.mkdir(parents=True);path.write_bytes(b'frozen event bytes')
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    frozen_path='data/events_replay_dev/BTCUSDT/2022-01.parquet'
    combined=hashlib.sha256(f'{frozen_path}\0{digest}\n'.encode()).hexdigest()
    manifest=tmp_path/'manifest.json'
    manifest.write_text(json.dumps({'root':'data/events_replay_dev','files':[
        {'path':frozen_path,'size':path.stat().st_size,'sha256':digest}],
        'combined_sha256':combined}))
    assert verify_frozen_events(events,combined,manifest_path=manifest,expected_count=1)==combined
    with pytest.raises(ValueError,match='SHA mismatch'):
        verify_frozen_events(events,'0'*64,manifest_path=manifest,expected_count=1)
