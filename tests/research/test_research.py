import numpy as np
import pandas as pd
import pytest
from msd.research.dataset import assemble
from msd.research.splits import walk_forward,cpcv
from msd.research.models import ResidualModel
from msd.research.decision import choose
from msd.research.report_card import metrics


def fixture_events():
    t=pd.date_range('2022-01-01',periods=4,freq='D',tz='UTC')
    events=pd.DataFrame({'ts':t,'known_at':t,'sym':'BTCUSDT','method':'sr_touch','side':1,
        'price':100,'sl':99,'tp':101,'planned_risk':1,'entry_ts':t+pd.Timedelta(minutes=2),
        'exit_ts':t+pd.Timedelta(hours=2),'outcome':['tp','sl','tp','sl'],
        'R':[1,-1,1,-1],'gross_R':[1,-1,1,-1]})
    features=pd.DataFrame({'known_at':[t[0]-pd.Timedelta(minutes=1),t[2]+pd.Timedelta(minutes=1)],
        '1m_return_bars_5':[3,99]})
    return events,features

def test_causal_asof_and_outcome_exclusion():
    e,f=fixture_events();out=assemble(e,f,('1m_return_bars_5',))
    assert out['1m_return_bars_5'].tolist()==[3,3,3,99]
    assert (out.feature_known_at<=out.known_at).all()
    assert out.p0.eq(.5).all()
    with pytest.raises(AssertionError):assemble(e,f,('R',))

def test_purge_and_forward():
    t=pd.date_range('2022-01-03',periods=30,freq='D',tz='UTC')
    frame=pd.DataFrame({'known_at':t,'label_end_ts':t+pd.Timedelta(days=3)})
    for generator in (walk_forward(frame,3),cpcv(frame,5,2)):
        for train,test in generator:
            for tr in train:
                assert not any(frame.known_at.iloc[tr]<=frame.label_end_ts.iloc[te] and frame.label_end_ts.iloc[tr]>=frame.known_at.iloc[te] for te in test)
            if len(test) and frame.known_at.iloc[train].max()<frame.known_at.iloc[test].min():
                pass
    for train,test in walk_forward(frame,3):
        assert frame.known_at.iloc[train].max()<frame.known_at.iloc[test].min()

def synthetic(edge=False):
    rng=np.random.default_rng(7);n=3000
    x=rng.normal(size=n);p=1/(1+np.exp(-(1.4*x if edge else np.zeros(n))))
    y=rng.binomial(1,p)
    t=pd.date_range('2020-01-01',periods=n,freq='h',tz='UTC')
    return pd.DataFrame({'known_at':t,'label_end_ts':t+pd.Timedelta(minutes=30),'entry_ts':t,
        'p0':.5,'tp_first':y,'1m_return_bars_5':x,'event_key':[str(i//3) for i in range(n)],
        'TP_R':1,'cost_R':.15,'financing_R':0,'price':100,'sl':99,'net_R':np.where(y,1,-1),
        'sym':'BTCUSDT','spread_R':.15})

def test_random_features_offset_near_baseline():
    f=synthetic();m=ResidualModel(features=('1m_return_bars_5',)).fit(f.iloc[:2000])
    p=m.predict(f.iloc[2000:]);y=f.tp_first.iloc[2000:].to_numpy()
    skill=1-np.mean((p-y)**2)/np.mean((.5-y)**2)
    assert abs(skill)<.05
    test=f.iloc[2000:].copy();test['p']=p
    assert len(choose(test,threshold=.15))<20

def test_planted_edge_found():
    f=synthetic(True);m=ResidualModel(features=('1m_return_bars_5',)).fit(f.iloc[:2000])
    p=m.predict(f.iloc[2000:]);x=f['1m_return_bars_5'].iloc[2000:].to_numpy()
    assert p[x>1].mean()>p[x< -1].mean()+.25
    assert np.mean((p-f.tp_first.iloc[2000:].to_numpy())**2)<np.mean((.5-f.tp_first.iloc[2000:].to_numpy())**2)

def test_report_metrics_toy():
    e,f=fixture_events();d=assemble(e,f,('1m_return_bars_5',));d['p']=.5;d['spread_R']=0
    m=metrics(d,d)
    assert m['n']==4 and m['hit_rate']==.5 and m['net_avg_R']==0
    assert m['profit_factor']==1 and m['brier_skill_vs_p0']==0
