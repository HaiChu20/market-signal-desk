import importlib

import numpy as np
import pandas as pd
import pytest

NAMES = [
    'round_number_reaction','session_level_reaction','supply_demand_zone_retest',
    'trendline_channel','market_structure_pullback','dow_trend_confirmation',
    'chart_patterns','candlestick_at_level','price_action_h2l2','fib_pullback',
    'order_block_retest','fvg_retrace','ote_zone','wyckoff_spring_upthrust',
    'ma_cross','macd_signal','bollinger','stochastic','vwap_reclaim_reject',
    'donchian_atr_breakout','ichimoku_cloud','volume_profile_poc_vah_val',
    'btc_order_flow','post_macro_event_reaction','post_earnings_index_reaction',
    'trend_following','intraday_momentum','range_breakout_nr4_nr7',
    'vix_spike_dip_buy','funding_extreme_fade',
]


def frames():
    n=240
    ts=pd.date_range('2022-01-03', periods=n, freq='min',tz='UTC')
    c=np.full(n,100.)
    c[216:]=[100,100.4,101,100.5,101,100.8,101,100.2,100.6,100.8,100.7,100.4,100.8,100.9,101,101.1,101.2,101.1,101,100.9,100.8,100.7,100.6,100.5]
    o=np.r_[c[0],c[:-1]]
    h=np.maximum(o,c)+.2; l=np.minimum(o,c)-.2
    bars=pd.DataFrame({'ts':ts,'bid_o':o,'bid_h':h,'bid_l':l,'bid_c':c,'ask_o':o,'ask_h':h,'ask_l':l,'ask_c':c,'volume':np.full(n,10.),'sym':'BTCUSDT'})
    f=pd.DataFrame({'ts':ts,'known_at':ts+pd.Timedelta(minutes=1),'1h_atr14':np.ones(n),'1m_atr14':np.ones(n),'1h_swing_high':np.full(n,102.),'1h_swing_low':np.full(n,99.),'1h_ema50_200_gap_atr':np.ones(n),'1h_ema20_50_gap_atr':np.ones(n),'1d_ema50_200_gap_atr':np.ones(n),'volume_z20':np.full(n,2.),'1h_macd_hist_atr':np.full(n,-1.),'1h_stoch_k14':np.full(n,10.),'1h_stoch_d3':np.full(n,20.),'1h_bollinger_pctb20':np.full(n,-.1),'1h_bollinger_width20':np.full(n,.1),'vwap_distance_atr':np.full(n,-1.),'1h_donchian20_position':np.full(n,.5),'taker_buy_ratio':np.full(n,.5),'funding_z20':np.zeros(n),'1d_return_bars_20':np.full(n,.1),'1d_return_bars_60':np.full(n,.1),'1d_return_bars_1':np.full(n,-.03),'vix_percentile_1y':np.full(n,.95),'minutes_since_session_open':np.arange(n),'session_id':np.zeros(n),'prior_day_high_distance_atr':np.full(n,-1.),'prior_day_low_distance_atr':np.full(n,1.),'macro_minutes_since_event':np.full(n,0.),'earnings_minutes_since_event':np.full(n,0.),'1d_atr14':np.full(n,1.),'1d_bar_known_at':[pd.Timestamp('2022-01-02',tz='UTC')]*n})
    f.loc[220:,'1h_macd_hist_atr']=1
    f.loc[220:,'1h_ema20_50_gap_atr']=-1
    f.loc[220:,'1h_stoch_k14']=30
    f.loc[220:,'1h_bollinger_pctb20']=.2
    f.loc[220:,'vwap_distance_atr']=1
    f.loc[220:,'1h_donchian20_position']=1
    f.loc[220:,'taker_buy_ratio']=.7
    f.loc[220:,'funding_z20']=3
    f.loc[220:,'macro_minutes_since_event']=5
    f.loc[220:,'earnings_minutes_since_event']=5
    f.loc[220:,'1d_bar_known_at']=pd.Timestamp('2022-01-03',tz='UTC')
    levels=pd.DataFrame({'price':[100.5,100.5,100.5,100.5], 'type':['round_number','prior_day_high','demand_zone_edge','prior_day_poc'],'known_at':[ts[0]-pd.Timedelta(days=1)]*4,'invalidated_at':[pd.NaT]*4})
    return f,levels,bars


def trigger_frames(name):
    f,l,b=frames()
    if name=='trendline_channel':
        b.loc[220,'bid_l']=99.1
        l=pd.DataFrame({'price':[98.,99.], 'type':['swing_low','swing_low'],
            'known_at':[b.ts.iloc[185],b.ts.iloc[205]],
            'created_at':[b.ts.iloc[180],b.ts.iloc[200]],'timeframe':['1h','1h']})
    elif name=='market_structure_pullback':
        f['1h_swing_high']=100.1
        b.loc[220,'bid_l']=100.0
        l=pd.DataFrame({'price':[99.5,98.5,100.0,99.0],
            'type':['swing_high','swing_low','swing_high','swing_low'],
            'known_at':[b.ts.iloc[170],b.ts.iloc[180],b.ts.iloc[190],b.ts.iloc[200]],
            'timeframe':['1h']*4})
    elif name=='dow_trend_confirmation':
        f.loc[:219,'1h_ema50_200_gap_atr']=-1
    elif name=='chart_patterns':
        b.loc[220,'bid_c']=98.5
        l=pd.DataFrame({'price':[102.,99.,102.1],
            'type':['swing_high','swing_low','swing_high'],
            'known_at':[b.ts.iloc[185],b.ts.iloc[195],b.ts.iloc[205]],
            'created_at':[b.ts.iloc[180],b.ts.iloc[190],b.ts.iloc[200]],
            'timeframe':['1h']*3})
    elif name=='candlestick_at_level':
        b.loc[220,'bid_o']=100.0
        b.loc[220,'bid_l']=99.4
        b.loc[220,'bid_c']=100.6
    elif name=='price_action_h2l2':
        b.loc[[217,218,219,220],'bid_c']=[101,100,101.5,102]
        b.loc[220,'bid_h']=101.8
    elif name=='order_block_retest':
        f['1h_swing_high']=100.5
        b.loc[218,['bid_o','bid_c','bid_h','bid_l']]=[100.4,100.0,100.6,99.8]
        b.loc[219,['bid_o','bid_c','bid_h','bid_l']]=[100.0,101.0,101.2,99.9]
        b.loc[220,['bid_o','bid_c','bid_h','bid_l']]=[101.0,100.8,101.1,100.5]
    elif name=='fvg_retrace':
        b.loc[217,['bid_o','bid_c','bid_h','bid_l']]=[99.7,99.8,100.0,99.6]
        b.loc[219,['bid_o','bid_c','bid_h','bid_l']]=[101.3,101.4,101.6,101.1]
        b.loc[220,['bid_o','bid_c','bid_h','bid_l']]=[101.3,101.2,101.5,101.0]
    elif name=='ote_zone':
        b.loc[219,'bid_c']=101
        b.loc[220,'bid_c']=100
    elif name=='wyckoff_spring_upthrust':
        b.loc[220,'bid_l']=98.5
    elif name=='stochastic':
        f.loc[220:,'1h_stoch_k14']=20
        f.loc[220:,'1h_stoch_d3']=15
    elif name in {'post_earnings_index_reaction','vix_spike_dip_buy','intraday_momentum'}:
        b['sym']='USATECHIDXUSD'
    elif name=='range_breakout_nr4_nr7':
        f['session_id']=np.arange(len(f))//25
        b.loc[:174,'bid_h']=103
        b.loc[:174,'bid_l']=97
        b.loc[175:199,'bid_h']=100.2
        b.loc[175:199,'bid_l']=99.8
        f.loc[:219,'prior_day_high_distance_atr']=-1
        f.loc[220:,'prior_day_high_distance_atr']=1
    return f,l,b


@pytest.mark.parametrize('name',NAMES)
def test_no_required_inputs_no_event(name):
    mod=importlib.import_module(f'msd.methods.{name}')
    f,l,b=frames()
    assert mod.detect(f.iloc[0:0],l,b)==[]
    assert mod.detect(f,l,b.iloc[0:0])==[]


@pytest.mark.parametrize('name',NAMES)
def test_causal_truncation_and_level_placement(name):
    mod=importlib.import_module(f'msd.methods.{name}')
    f,l,b=trigger_frames(name)
    whole=mod.detect(f,l,b)
    assert whole, name
    cut=235
    before=mod.detect(f.iloc[:cut],l,b.iloc[:cut])
    assert before, name
    changed=b.copy(); changed.loc[cut:,['bid_o','bid_h','bid_l','bid_c','ask_o','ask_h','ask_l','ask_c']]+=1000
    changed_features=f.copy()
    numeric=changed_features.select_dtypes(include='number').columns
    changed_features.loc[cut:,numeric]=changed_features.loc[cut:,numeric]+1000
    after=mod.detect(changed_features,l,changed)
    assert [e for e in whole if e['ts']<b.ts.iloc[cut]]==before
    assert [e for e in after if e['ts']<b.ts.iloc[cut]]==before
    future_level=l.iloc[[0]].copy()
    future_level['known_at']=b.ts.iloc[cut]+pd.Timedelta(minutes=1)
    if 'created_at' in future_level: future_level['created_at']=b.ts.iloc[cut]
    later_levels=pd.concat([l,future_level],ignore_index=True)
    later=mod.detect(f,later_levels,b)
    assert [e for e in later if e['ts']<b.ts.iloc[cut]]==before
    for e in whole:
        entry=e.get('limit_price',e['price'])
        assert e['side']*(entry-e['natural_sl'])>0
        assert e['side']*(e['natural_tp']-entry)>0
        assert e['known_at']>=e['ts']+pd.Timedelta(minutes=1)
        if e['entry_type']=='limit':
            assert e['expiry_at']>e['known_at']


def test_limit_entries():
    f,l,b=frames()
    for name in ('supply_demand_zone_retest','ote_zone'):
        mod=importlib.import_module(f'msd.methods.{name}')
        events=mod.detect(f,l,b)
        assert all(e['entry_type']=='limit' for e in events)


def test_filters():
    from msd.methods.filters import killzones, macro_blackout, time_of_day_calendar, vol_sizing
    f,_,b=frames()
    e={'ts':b.ts.iloc[220], 'known_at':f.known_at.iloc[220], 'price':100.}
    assert time_of_day_calendar([e])[0]['local_hour']>=0
    assert vol_sizing([e],f)[0]['size_fraction']>0
    assert macro_blackout([e],pd.DataFrame({'ts':[e['known_at']]}))==[]
    assert isinstance(killzones([e]),list)


@pytest.mark.parametrize('name',NAMES)
def test_no_trigger_without_usable_atr(name):
    mod=importlib.import_module(f'msd.methods.{name}')
    f,l,b=trigger_frames(name)
    f[['1h_atr14','1m_atr14']]=np.nan
    assert mod.detect(f,l,b)==[]


def test_head_and_shoulders_waits_for_last_pivot_confirmation():
    from msd.methods.chart_patterns import detect
    f,_,b=frames()
    b.loc[220,'bid_c']=98.5
    l=pd.DataFrame({'price':[101.,99.,103.,99.2,101.1],
        'type':['swing_high','swing_low','swing_high','swing_low','swing_high'],
        'created_at':[b.ts.iloc[i] for i in (170,180,190,200,210)],
        'known_at':[b.ts.iloc[i] for i in (175,185,195,205,215)],
        'timeframe':['1h']*5})
    events=detect(f,l,b)
    assert any(e['pattern']=='head_shoulders' and e['ts']==b.ts.iloc[220] for e in events)
    l.loc[4,'known_at']=b.ts.iloc[230]
    assert not any(e['ts']==b.ts.iloc[220] for e in detect(f,l,b))


@pytest.mark.parametrize('name',('supply_demand_zone_retest','order_block_retest','fvg_retrace','ote_zone'))
def test_limit_entry_has_price_and_expiry(name):
    f,l,b=trigger_frames(name)
    events=importlib.import_module(f'msd.methods.{name}').detect(f,l,b)
    assert events
    assert all(e['entry_type']=='limit' and e['limit_price']>0 and e['expiry_at']>e['known_at'] for e in events)


def test_macro_follow_and_fade_variants():
    from msd.methods.post_macro_event_reaction import detect
    f,l,b=trigger_frames('post_macro_event_reaction')
    events=detect(f,l,b)
    assert {e['variant'] for e in events}=={'follow','fade'}
    assert {e['side'] for e in events}=={1,-1}
