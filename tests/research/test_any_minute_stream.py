from pathlib import Path
import pandas as pd
import pytest
from msd.research.any_minute import load_grid,paths_for,_gate_open_signals_streaming
from msd.research.event_summary import summarize

def test_grid_cost_and_causal_asof(tmp_path):
    root=tmp_path;p=root/'labels'/'BTCUSDT'/'2022-01.parquet';p.parent.mkdir(parents=True)
    ts=pd.Timestamp('2022-01-01T00:00Z')
    pd.DataFrame({'ts':[ts],'side':[1],'sl_atr':[1.],'tp_atr':[2.],
        'outcome':[1],'net_R':[1.],'gross_R':[1.1],'exit_ts':[ts+pd.Timedelta(minutes=3)],
        'entry_ts':[ts+pd.Timedelta(minutes=2)],'deadline_ts':[ts+pd.Timedelta(days=5)],
        'planned_risk':[10.],'fill_price':[100.]}).to_parquet(p)
    q=root/'features'/'BTCUSDT'/'2022-01.parquet';q.parent.mkdir(parents=True)
    pd.DataFrame({'known_at':[ts+pd.Timedelta(minutes=1),ts+pd.Timedelta(minutes=2)],
        'spread_atr':[.2,99.],'1m_atr14':[10.,10.]}).to_parquet(q)
    data=load_grid(root,'BTCUSDT',p)
    assert len(data)==1 and data.spread_R.iloc[0]==pytest.approx(.2)
    assert data.cost_R.iloc[0]==pytest.approx(.2)
    assert data['spread_atr'].iloc[0]==pytest.approx(.2)

def test_test_final_files_never_selected(tmp_path):
    d=tmp_path/'labels'/'BTCUSDT';d.mkdir(parents=True)
    for name in ('2022-12.parquet','2023-01.parquet','2025-01.parquet'):(d/name).touch()
    assert [p.name for p in paths_for(tmp_path,'BTCUSDT')]==['2022-12.parquet']

def test_tournament_fixture_nonvacuous_and_missing_fails(tmp_path):
    d=tmp_path/'events'/'BTCUSDT';d.mkdir(parents=True)
    t=pd.Timestamp('2022-01-01T00:00Z')
    pd.DataFrame({'method':['a','b','a'],'sym':['BTCUSDT']*3,'ts':[t,t,t+pd.Timedelta(minutes=1)],
        'side':[1,1,1],'known_at':[t]*3,'exit_ts':[t+pd.Timedelta(minutes=2)]*3,
        'R':[1.,-1.,2.]}).to_parquet(d/'2022-01.parquet')
    rows=summarize(tmp_path,['a','b'],('BTCUSDT',))
    assert len(rows)==2 and all(r['candidate_rows']>0 for r in rows)
    with pytest.raises(FileNotFoundError):summarize(tmp_path,['a','b','c'],('BTCUSDT',))
