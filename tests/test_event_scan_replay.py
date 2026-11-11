import importlib,re
from pathlib import Path
import numpy as np,pandas as pd,pytest
from msd.methods.requirements import RULES,COMMON
from msd.processing import pipeline
from test_tournament_methods import NAMES,trigger_frames

def test_declared_inputs_cover_every_col_key_and_fire():
    source=Path('src/msd/methods/_detectors.py').read_text()
    keys=set(re.findall(r"col\(['\"]([^'\"]+)",source))
    assert keys<=set().union(COMMON,*RULES.values())
    for name in NAMES:
        mod=importlib.import_module(f'msd.methods.{name}')
        assert mod.MARKETS in {'all','crypto','indices','gold'}
        f,levels,bars=trigger_frames(name)
        for key in mod.REQUIRED_FEATURES:
            if key not in f:f[key]=0.
        assert set(mod.REQUIRED_FEATURES)<=set(f)
        assert mod.detect(f,levels,bars),name

def test_missing_required_column_raises(monkeypatch):
    class Method:
        NAME='fixture';REQUIRED_FEATURES=('1h_macd_hist_atr',)
        def detect(*args):return []
    monkeypatch.setattr(pipeline,'methods_for_symbol',lambda _: (Method,))
    ts=pd.date_range('2021-01-01',periods=3,freq='min',tz='UTC')
    bars=pd.DataFrame({'ts':ts,**{f'{s}_{f}':np.ones(3) for s in ('bid','ask') for f in 'ohlc'}})
    with pytest.raises(ValueError,match='1h_macd_hist_atr'):
        pipeline.label_method_events(pd.DataFrame({'ts':ts,'1m_atr14':1.}),pd.DataFrame(),bars,'BTCUSDT')

def test_events_only_state_equivalence_across_year(monkeypatch,tmp_path):
    root=tmp_path/'source';sym='BTCUSDT';bars_dir=root/'bars/binance_spot'/sym;bars_dir.mkdir(parents=True)
    for year in (2020,2021):
        ts=pd.date_range(f'{year}-01-01',periods=3,freq='min',tz='UTC')
        pd.DataFrame({'ts':ts,**{f'{s}_{f}':np.ones(3) for s in ('bid','ask') for f in 'ohlc'}}).to_parquet(bars_dir/f'{year}-01.parquet')
    levels=root/'levels';levels.mkdir();pd.DataFrame({'known_at':[pd.Timestamp('2019-01-01',tz='UTC')]}).to_parquet(levels/f'{sym}.parquet')
    monkeypatch.setattr(pipeline,'_feature_label_bars',lambda b:b)
    monkeypatch.setattr(pipeline,'_adjusted_price_view',lambda b:b)
    monkeypatch.setattr(pipeline,'_modelled_spread',lambda b,s:b)
    monkeypatch.setattr(pipeline,'_active_mask',lambda b,s:pd.Series(True,index=b.index))
    monkeypatch.setattr(pipeline,'_event_feature_frame',lambda b,t,**kw:pd.DataFrame({'ts':b.ts,'known_at':b.ts+pd.Timedelta(minutes=1),'1m_atr14':1.}))
    class Method: NAME='fixture'
    monkeypatch.setattr(pipeline,'methods_for_symbol',lambda s:(Method,))
    def fake(features,levels,bars,symbol,**kwargs):
        state=kwargs['method_states'];count=state.get('fixture',0)+1
        frame=pd.DataFrame({'ts':[kwargs['event_start']],'method':['fixture']})
        return frame,{'fixture':count},{'fixture':count},[]
    monkeypatch.setattr(pipeline,'label_method_events',fake)
    monkeypatch.setattr(pipeline,'_write_monthly',lambda frame,directory,symbol:len(frame))
    whole=pipeline.replay_events_only(sym,2020,2021,tmp_path/'whole',root)
    first=pipeline.replay_events_only(sym,2020,2020,tmp_path/'split',root)
    second=pipeline.replay_events_only(sym,2021,2021,tmp_path/'split',root)
    assert whole==first+second
