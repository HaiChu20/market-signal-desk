"""Stage 10C ambiguity parity; slow randomized test runs explicitly with -m slow."""
import numpy as np
import pandas as pd
import pytest

from msd.backtest import evaluate_bar, second_quotes, timestamp_ints
from msd.processing.labels import first_hit_reference, first_hit


def fixture(tp_second=10, sl_second=20, missing=False):
    ts = pd.date_range('2022-06-01', periods=3, freq='min', tz='UTC')
    minute = pd.DataFrame({'ts':ts, 'bid_o':[100.]*3, 'bid_h':[100.,100.,102.],
        'bid_l':[100.,100.,98.], 'bid_c':[100.]*3, 'ask_o':[100.]*3,
        'ask_h':[100.,100.,102.], 'ask_l':[100.,100.,98.], 'ask_c':[100.]*3})
    second_ts = pd.date_range(ts[2], periods=60, freq='s')
    single = pd.DataFrame({'ts':second_ts, 'o':100., 'h':100., 'l':100., 'c':100.})
    single.loc[tp_second,'h'] = 101.5
    single.loc[sl_second,'l'] = 98.5
    if missing: single = single.drop(index=30).reset_index(drop=True)
    return minute, second_quotes(single,0.)


def _batch(minute, seconds):
    from msd._msd_kernels import first_hit_batch
    cols=['bid_o','bid_h','bid_l','bid_c','ask_o','ask_h','ask_l','ask_c']
    raw=minute[cols].to_numpy(dtype='<f8').tobytes()
    stamps=np.asarray(timestamp_ints(minute.ts,unit='s'),dtype='<i8').tobytes()
    second_raw=seconds[cols].to_numpy(dtype='<f8').tobytes()
    second_stamps=np.asarray(timestamp_ints(seconds.ts,unit='s'),dtype='<i8').tobytes()
    job=[0.,1.,100.,99.,101.,float('nan'),1.,0.,float('nan'),float('nan'),1.]
    return first_hit_batch(raw,stamps,job,11,second_raw,second_stamps,True)


@pytest.mark.parametrize('tp_second,sl_second,missing,reason,key', [
    (10,20,False,'tp','resolved_tp'), (20,10,False,'stop','resolved_sl'),
    (10,10,False,'stop','resolved_sl'), (10,20,True,'stop','unresolved')])
def test_second_resolution_matches_reference_and_both_rust_entries(tp_second,sl_second,missing,reason,key):
    minute,seconds=fixture(tp_second,sl_second,missing)
    reference=first_hit_reference(minute,0,1,100.,99.,101.,delay_bars=1,
                                  seconds=seconds,detailed=True,return_stats=True)
    wrapper=first_hit(minute,0,1,100.,99.,101.,delay_bars=1,
                      seconds=seconds,detailed=True,return_stats=True)
    assert wrapper[0] == reference[0] == reason
    np.testing.assert_allclose(wrapper[1:9],reference[1:9],equal_nan=True)
    assert wrapper[9] == reference[9] == {'ambiguous':1,'resolved_tp':0,'resolved_sl':0,'unresolved':0} | {key:1}
    batch=_batch(minute,seconds)
    assert int(batch[0])=={'tp':1,'stop':-1}[reason]
    np.testing.assert_allclose(batch[1:9],
        [reference[1],reference[5],reference[2],reference[3],reference[4],reference[6],reference[7],reference[8]],
        equal_nan=True)
    assert list(map(int,batch[9:13]))==list(reference[9].values())
    stats={}
    _,bar_reason,_=evaluate_bar(1,99.,101.,minute.iloc[2].to_dict(),seconds=seconds,ambiguity_stats=stats)
    assert bar_reason==reason and stats==reference[9]


@pytest.mark.slow
def test_10000_randomized_rust_python_second_parity():
    rng=np.random.default_rng(821)
    for _ in range(10_000):
        tp_second=int(rng.integers(0,60));sl_second=int(rng.integers(0,60))
        missing=bool(rng.integers(0,8)==0)
        minute,seconds=fixture(tp_second,sl_second,missing)
        reference=first_hit_reference(minute,0,1,100.,99.,101.,delay_bars=1,
                                      seconds=seconds,detailed=True,return_stats=True)
        rust=first_hit(minute,0,1,100.,99.,101.,delay_bars=1,
                       seconds=seconds,detailed=True,return_stats=True)
        assert rust[0]==reference[0]
        np.testing.assert_allclose(rust[1:9],reference[1:9],equal_nan=True)
        assert rust[9]==reference[9]
        no_seconds_reference=first_hit_reference(minute,0,1,100.,99.,101.,delay_bars=1,
                                                detailed=True,return_stats=True)
        no_seconds_rust=first_hit(minute,0,1,100.,99.,101.,delay_bars=1,
                                  detailed=True,return_stats=True)
        assert no_seconds_rust[0]==no_seconds_reference[0]
        np.testing.assert_allclose(no_seconds_rust[1:9],no_seconds_reference[1:9],equal_nan=True)
        assert no_seconds_rust[9]==no_seconds_reference[9]


@pytest.mark.parametrize('unit',['s','ms','us','ns'])
def test_timestamp_resolution_does_not_change_rust_or_python_result(unit):
    minute,seconds=fixture(10,20)
    minute['ts']=minute.ts.dt.as_unit(unit)
    seconds['ts']=seconds.ts.dt.as_unit(unit)
    reference=first_hit_reference(minute,0,1,100.,99.,101.,delay_bars=1,
                                  seconds=seconds,detailed=True,return_stats=True)
    rust=first_hit(minute,0,1,100.,99.,101.,delay_bars=1,
                   seconds=seconds,detailed=True,return_stats=True)
    assert rust[0]==reference[0]=='tp'
    np.testing.assert_allclose(rust[1:9],reference[1:9],equal_nan=True)
    assert rust[9]==reference[9]
    batch=_batch(minute,seconds)
    assert int(batch[0])==1
    assert list(map(int,batch[9:13]))==list(reference[9].values())
