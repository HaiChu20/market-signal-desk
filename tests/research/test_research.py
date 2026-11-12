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
        '1m_return_bars_5':[3,99], 'spread_atr':[.01,.01], '1m_atr14':[1.,1.]})
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


def test_cpcv_embargo_is_one_weekday_and_purge_removes_overlap():
    from msd.research.splits import _purge
    t=pd.to_datetime(['2022-01-06 12:00','2022-01-07 12:00','2022-01-10 11:59',
                      '2022-01-10 12:00','2022-01-11 12:00'],utc=True)
    frame=pd.DataFrame({'known_at':t,'label_end_ts':t})
    kept=_purge(frame,np.array([1]))
    assert kept.tolist()==[0,4]  # Friday test embargoes through Monday 12:00 inclusive.

    overlap=pd.DataFrame({'known_at':pd.to_datetime(['2022-01-01','2022-01-03'],utc=True),
                          'label_end_ts':pd.to_datetime(['2022-01-04','2022-01-03'],utc=True)})
    assert len(_purge(overlap,np.array([1])))==0


def test_trial_ledger_is_append_only_and_capped(tmp_path):
    from msd.research.ledger import append_trial,read_trials,FIELDS
    path=tmp_path/'trials.csv'
    def row(i):
        return dict(zip(FIELDS,[f't{i}','2026-11-12',f'h{i}','method','{}','2019/2022',
                                'dev','{}','dry']))
    append_trial(path,row(0),max_configs=2);before=path.read_bytes()
    append_trial(path,row(1),max_configs=2)
    assert path.read_bytes().startswith(before) and len(read_trials(path))==2
    with pytest.raises(ValueError,match='already present'):append_trial(path,row(1),max_configs=2)
    with pytest.raises(ValueError,match='limit'):append_trial(path,row(2),max_configs=2)

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

def test_feature_filter_uses_training_data_only():
    from msd.research.models import fit_time_ordered
    f=synthetic(True).iloc[:300].copy()
    f['train_dense']=np.arange(len(f),dtype=float)
    f['future_only']=np.nan
    f.loc[f.index>=240,'future_only']=1.0
    m=fit_time_ordered(f)
    assert 'train_dense' in m.features
    assert 'future_only' not in m.features


def test_shrinkage_blocks_weak_candidate():
    f=synthetic(True).iloc[:9].copy()
    f['p']=.62
    f['cost_R']=.1
    assert len(choose(f,threshold=.05,uncertainty=np.full(len(f),.2)))==0


def test_random_direction_benchmark_uses_same_entry(tmp_path):
    from msd.research.benchmark import random_direction
    t=pd.date_range('2022-01-03',periods=20,freq='min',tz='UTC')
    bars=pd.DataFrame({'ts':t})
    for side,shift in [('bid',-.05),('ask',.05)]:
        bars[f'{side}_o']=100+shift
        bars[f'{side}_h']=101+shift
        bars[f'{side}_l']=99+shift
        bars[f'{side}_c']=100+shift
    path=tmp_path/'bars'/'dukascopy'/'USATECHIDXUSD'/'2022-01.parquet'
    path.parent.mkdir(parents=True)
    bars.to_parquet(path,index=False)
    signals=pd.DataFrame({'ts':[t[0]],'sym':['USATECHIDXUSD'],'side':[1],'price':[100.],
        'sl':[99.],'tp':[101.],'deadline_ts':[t[10]],'label_end_ts':[t[5]],
        'spread_R':[.1],'planned_risk':[1.],'net_R':[1.]})
    percentile,n,manifest=random_direction(signals,tmp_path)
    assert n==1 and 0<=percentile<=100 and len(manifest)==1


def test_pbo_cscv_from_logged_dev_years():
    import json
    from msd.research.report_card import trial_diagnostics
    rows=[]
    for i,values in enumerate(([1,1,-1,-1],[-1,-1,1,1])):
        rows.append({'method':'x','period':'development','metrics':json.dumps(
            {'daily_sharpe':.2+i,'per_year':dict(zip(('2019','2020','2021','2022'),values))})})
    sharpes,pbo,count=trial_diagnostics(rows,'x')
    assert len(sharpes)==2 and count==2 and 0<=pbo<=1


def test_pbo_uses_logged_cpcv_train_and_test_ranks():
    import json
    from msd.research.report_card import trial_diagnostics
    rows=[
        {'method':'x','period':'dev','metrics':json.dumps({'daily_sharpe':1.,
            'cpcv_train_scores':[2.,0.], 'cpcv_test_scores':[-2.,0.]})},
        {'method':'x','period':'dev','metrics':json.dumps({'daily_sharpe':.5,
            'cpcv_train_scores':[0.,2.], 'cpcv_test_scores':[0.,-2.]})},
    ]
    _,pbo,count=trial_diagnostics(rows,'x')
    assert count==2 and pbo==1.0

def test_dev_excludes_labels_ending_in_test_period():
    e,f=fixture_events()
    e.loc[3,'exit_ts']=pd.Timestamp('2023-01-01',tz='UTC')
    with pytest.raises(ValueError,match='label_end_ts'):
        assemble(e,f,('1m_return_bars_5',),return_audit=True)


def test_supplemental_asof_join_is_causal_and_missing_layer_is_nan():
    e,f=fixture_events()
    flow=pd.DataFrame({'known_at':[e.known_at.iloc[0]-pd.Timedelta(minutes=1),
                                         e.known_at.iloc[2]+pd.Timedelta(minutes=1)],
                       'flow_coverage':[True,True],'spot_delta_5m':[2.,99.]})
    depth=pd.DataFrame(columns=['known_at','depth_coverage','depth_imbalance_1pct'])
    out=assemble(e,f,('1m_return_bars_5',),supplemental={'flow':flow,'depth':depth})
    assert out.spot_delta_5m.tolist()==[2,2,2,99]
    assert out.flow_feature_known_at.le(out.known_at).all()
    assert out.depth_coverage.isna().all() and out.depth_imbalance_1pct.isna().all()

    # A future perturbation cannot alter any joined value at or before the cut.
    cut=e.known_at.iloc[1]
    perturbed=flow.copy();perturbed.loc[perturbed.known_at>cut,'spot_delta_5m']=-12345
    truncated=assemble(e[e.known_at<=cut],f,('1m_return_bars_5',),supplemental={'flow':perturbed})
    pd.testing.assert_series_equal(out.loc[out.known_at<=cut,'spot_delta_5m'].reset_index(drop=True),
                                   truncated.spot_delta_5m.reset_index(drop=True))


def test_eth_random_direction_uses_pipeline_spread_and_crypto_costs(monkeypatch, tmp_path):
    import sys
    from msd.processing import pipeline
    from msd.processing.labels import first_hit_reference
    from msd.research import benchmark, sequence_data

    times = pd.date_range('2022-06-12 23:55', periods=68, freq='min', tz='UTC')
    raw = pd.DataFrame({'ts': times})
    for side in ('bid', 'ask'):
        for field in 'ohlc':
            raw[f'{side}_{field}'] = 100.
    reference = pd.DataFrame({'ts': [times[0]], 'bid_o': [99.], 'ask_o': [101.]})
    monkeypatch.setattr(pipeline, 'load', lambda *args, **kwargs: reference)
    executable = pipeline._modelled_spread(raw, 'ETHUSDT')
    assert np.allclose(executable.ask_c - executable.bid_c, 2.)
    monkeypatch.setattr(sequence_data, 'load_executable_1m', lambda *args: executable)
    monkeypatch.setitem(sys.modules, 'msd._msd_kernels', None)
    captured = []
    def checked_kernel(bars, entry_index, side, entry_price, sl, tp, *args, **kwargs):
        result = first_hit_reference(bars, entry_index, side, entry_price, sl, tp, *args, **kwargs)
        captured.append((bars.copy(), kwargs, result))
        return result
    monkeypatch.setattr(benchmark, 'first_hit_reference', checked_kernel)
    signal = pd.DataFrame({'ts': [times[0]], 'sym': ['ETHUSDT'], 'side': [1],
                           'price': [100.], 'sl': [90.], 'tp': [110.],
                           'deadline_ts': [times[-1]], 'label_end_ts': [times[-1]],
                           'spread_R': [.2], 'planned_risk': [10.], 'net_R': [0.]})
    _, count, _ = benchmark.random_direction(signal, tmp_path, seeds=3)
    assert count == 1 and len(captured) == 1
    used_bars, options, observed = captured[0]
    assert options['financing_per_night'] == .0006
    assert options['instrument_class'] == 'crypto'
    np.testing.assert_allclose(used_bars.ask_c - used_bars.bid_c, 2.)
    expected = first_hit_reference(executable, 0, -1, 100., 110., 90.,
        delay_bars=2, financing_per_night=.0006, deadline_ts=times[-1],
        instrument_class='crypto', detailed=True)
    assert observed[3] == pytest.approx(expected[3])
    assert observed[6] == 1  # Sunday-to-Monday UTC midnight
    assert observed[5] == pytest.approx(99.)  # short opens at modeled bid
    assert observed[4] - observed[3] == pytest.approx(.0006 * observed[5] / observed[8])


def test_shared_gate_allows_next_entry_at_exit_plus_one_minute():
    from msd.research.gating import gate_open_signals
    start = pd.Timestamp('2021-01-01 00:00', tz='UTC')
    signals = pd.DataFrame({'known_at': [start, start + pd.Timedelta(minutes=1),
                                               start + pd.Timedelta(minutes=5),
                                               start + pd.Timedelta(minutes=6)],
                            'label_end_ts': [start + pd.Timedelta(minutes=5)] * 4,
                            'sym': ['BTCUSDT', 'ETHUSDT', 'BTCUSDT', 'BTCUSDT'],
                            'event_key': ['a', 'b', 'c', 'd']})
    chosen = gate_open_signals(signals)
    assert chosen.event_key.tolist() == ['a', 'b', 'd']


def test_btc_random_direction_uses_pipeline_executable_loader(monkeypatch, tmp_path):
    import sys
    from msd.processing.labels import first_hit_reference
    from msd.research import benchmark, sequence_data
    times = pd.date_range('2021-01-01', periods=20, freq='min', tz='UTC')
    bars = pd.DataFrame({'ts': times})
    for side, shift in [('bid', -1.), ('ask', 1.)]:
        for field in 'ohlc':
            bars[f'{side}_{field}'] = 100. + shift
    calls = []
    monkeypatch.setattr(sequence_data, 'load_executable_1m',
                        lambda symbol, *args: calls.append(symbol) or bars)
    monkeypatch.setitem(sys.modules, 'msd._msd_kernels', None)
    monkeypatch.setattr(benchmark, 'first_hit_reference', first_hit_reference)
    signal = pd.DataFrame({'ts': [times[0]], 'sym': ['BTCUSDT'], 'side': [1],
                           'price': [100.], 'sl': [90.], 'tp': [110.],
                           'deadline_ts': [times[-1]], 'label_end_ts': [times[-1]],
                           'spread_R': [999.], 'planned_risk': [10.], 'net_R': [0.]})
    _, count, _ = benchmark.random_direction(signal, tmp_path, seeds=2)
    assert count == 1 and calls == ['BTCUSDT']
