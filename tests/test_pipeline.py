from datetime import date

import numpy as np
import pandas as pd
import pytest


def test_vectorized_session_vwap_snapshots_reset_and_ignore_missing_volume():
    from msd.processing.levels import _vwap_snapshots
    ts=pd.to_datetime(["2024-01-01 00:00Z","2024-01-01 00:01Z",
                       "2024-01-02 00:00Z","2024-01-02 00:01Z"],utc=True)
    close=np.array([10.,20.,30.,40.])
    bars=pd.DataFrame({"ts":ts,"bid_c":close,"ask_c":close,"volume":[1.,3.,np.nan,2.]})
    result=_vwap_snapshots(bars,"BTCUSDT")
    assert result.price.tolist()==[10.,17.5,40.]
    assert result.created_at.tolist()==list(ts[[0,1,3]])
    assert result.known_at.tolist()==list(ts[[0,1,3]]+pd.Timedelta(minutes=1))


def _bars(ts):
    n = len(ts)
    values = np.arange(n, dtype=float) + 100
    return pd.DataFrame({"ts": ts, "bid_o": values, "bid_h": values + 1, "bid_l": values - 1, "bid_c": values + .5,
                         "ask_o": values + .2, "ask_h": values + 1.2, "ask_l": values - .8, "ask_c": values + .7,
                         "volume": np.ones(n)})


def test_level_type_codes_do_not_depend_on_future_level_universe():
    from msd.processing.features import _nearest_level_features
    base = pd.DataFrame({"known_at": pd.to_datetime(["2024-01-01", "2024-01-02"], utc=True),
                         "mid_close": [100., 100.], "base_atr14": [1., 1.]})
    levels = pd.DataFrame({"price": [101.], "type": ["swing_high"],
                           "known_at": pd.to_datetime(["2024-01-01"], utc=True),
                           "invalidated_at": [pd.NaT], "strength": [1/3]})
    future = pd.concat([levels, pd.DataFrame({"price": [90.], "type": ["brand_new_type"],
        "known_at": [pd.Timestamp("2024-01-03", tz="UTC")], "invalidated_at": [pd.NaT],
        "strength": [1.]})], ignore_index=True)
    a = _nearest_level_features(base, levels)
    b = _nearest_level_features(base, future)
    np.testing.assert_array_equal(a.level_above_1_type_code, b.level_above_1_type_code)


def test_level_invalidation_is_causal_and_persistable():
    from msd.processing.levels import apply_level_invalidations, levels_asof
    ts=pd.date_range("2024-01-01",periods=50,freq="min",tz="UTC")
    close=np.r_[np.full(30,100.),np.full(20,110.)]
    bars=pd.DataFrame({"ts":ts,"bid_o":close,"bid_h":close+.2,"bid_l":close-.2,"bid_c":close,
                       "ask_o":close+.1,"ask_h":close+.3,"ask_l":close-.1,"ask_c":close+.1})
    levels=pd.DataFrame({"level_id":[7],"price":[100.],"type":["swing_high"],"timeframe":["15m"],
        "created_at":[ts[10]],"known_at":[ts[20]+pd.Timedelta(minutes=1)],"invalidated_at":[pd.NaT],
        "strength":[1/3],"direction":[-1]})
    updated=apply_level_invalidations(bars,levels)
    invalidated=updated.invalidated_at.iloc[0]
    assert pd.notna(invalidated) and invalidated>levels.known_at.iloc[0]
    assert len(levels_asof(updated,invalidated-pd.Timedelta(minutes=1)))==1
    assert levels_asof(updated,invalidated).empty


def test_nearest_level_ties_use_stable_level_id_not_input_order():
    from msd.processing.features import _nearest_level_features
    base = pd.DataFrame({"known_at": pd.to_datetime(["2024-01-02"], utc=True),
                         "mid_close": [99.], "base_atr14": [1.]})
    levels = pd.DataFrame({"level_id": [10, 20], "price": [100., 100.],
                           "type": ["swing_high", "prior_day_high"],
                           "known_at": pd.to_datetime(["2024-01-01"]*2, utc=True),
                           "invalidated_at": [pd.NaT, pd.NaT], "strength": [1/3, 1.]})
    forward = _nearest_level_features(base, levels)
    reverse = _nearest_level_features(base, levels.iloc[::-1].reset_index(drop=True))
    assert forward.level_above_1_type_code.iloc[0] == reverse.level_above_1_type_code.iloc[0]
    assert forward.level_above_1_strength.iloc[0] == reverse.level_above_1_strength.iloc[0]


def test_cme_daily_bar_open_is_dst_correct():
    from msd.processing.timeframes import build_timeframe
    for day, expected in (("2024-01-15", "2024-01-14 23:00Z"), ("2024-07-15", "2024-07-14 22:00Z")):
        prior = pd.Timestamp(day) - pd.Timedelta(days=1)
        start = pd.Timestamp(f"{prior.date()} 18:00", tz="America/New_York").tz_convert("UTC")
        ts = pd.date_range(start, periods=1380, freq="min")
        frame = build_timeframe(_bars(ts), "USATECHIDXUSD", "1d")
        assert len(frame) == 1
        assert frame.ts.iloc[0] == pd.Timestamp(expected)
        assert frame.known_at.iloc[0] == pd.Timestamp(f"{day} 17:00", tz="America/New_York").tz_convert("UTC")


def test_cme_daily_bar_completes_at_scheduled_close_with_recurring_feed_gap():
    from msd.processing.timeframes import build_timeframe
    # Quotes stop at 16:14 ET and resume after the daily break. The scheduled
    # 17:00 ET close must still become known before that next quote arrives.
    start=pd.Timestamp("2024-06-02 18:00",tz="America/New_York")
    end=pd.Timestamp("2024-06-03 16:14",tz="America/New_York")
    ts=pd.date_range(start,end,freq="min").tz_convert("UTC")
    frame=build_timeframe(_bars(ts),"USATECHIDXUSD","1d")
    assert len(frame)==1
    assert frame.known_at.iloc[0]==pd.Timestamp("2024-06-03 17:00",tz="America/New_York").tz_convert("UTC")
    assert frame.observed_minutes.iloc[0] < frame.expected_minutes.iloc[0]


def test_cme_timeframe_does_not_bridge_daily_break():
    from msd.processing.timeframes import build_timeframe
    ts = pd.date_range("2024-06-12 15:00", "2024-06-12 19:00", freq="min", tz="America/New_York").tz_convert("UTC")
    ts = ts[(ts.tz_convert("America/New_York").hour < 17) | (ts.tz_convert("America/New_York").hour >= 18)]
    frame = build_timeframe(_bars(ts), "USATECHIDXUSD", "1h")
    assert (frame.known_at - frame.ts).dt.total_seconds().le(3600).all()
    assert not frame.ts.dt.tz_convert("America/New_York").dt.hour.eq(17).any()


def test_higher_timeframe_propagates_roll_flag():
    from msd.processing.timeframes import build_timeframe
    ts=pd.date_range("2024-01-01",periods=5,freq="min",tz="UTC")
    bars=_bars(ts);bars["roll"]=[False,False,True,False,False]
    result=build_timeframe(bars,"BTCUSDT","5m")
    assert len(result)==1 and bool(result.roll.iloc[0])


def test_htf_truncation_keeps_completed_rows_identical():
    from msd.processing.timeframes import build_timeframe
    ts = pd.date_range("2024-01-01", periods=1200, freq="min", tz="UTC")
    full = build_timeframe(_bars(ts), "BTCUSDT", "15m")
    cut = pd.Timestamp("2024-01-01 08:00", tz="UTC")
    truncated = build_timeframe(_bars(ts[ts < cut]), "BTCUSDT", "15m")
    expected = full[full.known_at <= cut]
    pd.testing.assert_frame_equal(truncated, expected.reset_index(drop=True))


def test_rust_label_kernel_matches_reference_on_10000_random_cases():
    from msd.processing.labels import first_hit, first_hit_reference
    rng = np.random.default_rng(42)
    checked = 0
    for _ in range(10_000):
        n = int(rng.integers(8, 22))
        mid = 100 + np.cumsum(rng.normal(0, .25, n))
        op = mid + rng.normal(0, .05, n)
        spread = rng.uniform(.01, .2, n)
        high = np.maximum(mid, op) + rng.uniform(0, .4, n)
        low = np.minimum(mid, op) - rng.uniform(0, .4, n)
        ts = pd.date_range("2024-03-08", periods=n, freq="h", tz="UTC")
        bars = pd.DataFrame({"ts": ts,
            "bid_o": op-spread/2, "bid_h": high-spread/2, "bid_l": low-spread/2, "bid_c": mid-spread/2,
            "ask_o": op+spread/2, "ask_h": high+spread/2, "ask_l": low+spread/2, "ask_c": mid+spread/2})
        side = int(rng.choice([-1, 1]))
        signal = 1
        entry = signal + 2
        signal_mid = float(mid[signal])
        risk = float(rng.uniform(.2, .8))
        sl = signal_mid - side * risk
        tp = signal_mid + side * float(rng.uniform(.2, 1.5))
        args = (bars, signal, side, signal_mid, sl, tp, int(rng.integers(2, 10)))
        limit = None
        expiry = None
        if _ % 7 == 0:
            limit = float(bars.ask_l.iloc[entry] + (0.02 if side > 0 else -0.02))
            expiry = entry + 3
        ref = first_hit_reference(*args, financing_per_night=.0002, limit_price=limit, expiry_index=expiry)
        got = first_hit(*args, financing_per_night=.0002, limit_price=limit, expiry_index=expiry)
        assert got[0] == ref[0]
        assert got[1] == ref[1]
        assert np.allclose(got[2:], ref[2:], rtol=1e-9, atol=1e-10, equal_nan=True)
        checked += 1
    assert checked == 10_000


def test_label_kernel_uses_friday_weekend_financing_as_three_nights():
    from msd.processing.labels import _night_count
    assert _night_count(pd.Timestamp("2024-03-08", tz="UTC"), pd.Timestamp("2024-03-11", tz="UTC")) == 3


def test_rust_batch_label_matches_reference():
    from msd.processing.labels import first_hit_reference
    from msd._msd_kernels import first_hit_batch as rust_batch
    ts = pd.date_range("2024-01-01", periods=80, freq="min", tz="UTC")
    mid = np.linspace(100, 102, len(ts))
    bars = pd.DataFrame({"ts": ts, "bid_o": mid-.05, "bid_h": mid+.3, "bid_l": mid-.2, "bid_c": mid,
                         "ask_o": mid+.05, "ask_h": mid+.4, "ask_l": mid-.1, "ask_c": mid+.1})
    jobs = [[2, 1, 100., 99., 100.5, 20, 2, 0.0002],
            [10, -1, 100.2, 101.2, 99.5, 10, 2, 0.0002]]
    raw = bars[["bid_o", "bid_h", "bid_l", "bid_c", "ask_o", "ask_h", "ask_l", "ask_c"]].to_numpy(dtype="<f8")
    stamps = (bars.ts.astype("datetime64[ns, UTC]").astype("int64")//1_000_000_000).to_numpy(dtype="<i8")
    got = np.asarray(rust_batch(raw.tobytes(), stamps.tobytes(), sum(jobs, []))).reshape(-1, 5)
    for i, job in enumerate(jobs):
        signal, side, entry, sl, tp, maximum, delay, finance = job
        ref = first_hit_reference(bars, int(signal), int(side), entry, sl, tp, int(maximum), int(delay), finance)
        assert int(got[i, 0]) == {"tp": 1, "stop": -1, "time": 0, "no_fill": -2}[ref[0]]
        assert int(got[i, 1]) == ref[1]
        assert np.allclose(got[i, 2:], [ref[2], ref[3], ref[4]], rtol=1e-9, atol=1e-10, equal_nan=True)


def test_modern_rust_batch_matches_reference_on_10000_random_cases():
    from msd.processing.labels import first_hit, first_hit_reference
    from msd._msd_kernels import first_hit_batch
    rng=np.random.default_rng(388)
    n=160
    ts=pd.date_range("2024-03-08 15:00",periods=n,freq="h",tz="UTC")
    mid=100+np.cumsum(rng.normal(0,.22,n))
    op=np.r_[mid[0],mid[:-1]+rng.normal(0,.08,n-1)]
    spread=rng.uniform(.01,.15,n)
    high=np.maximum(mid,op)+rng.uniform(0,.5,n)
    low=np.minimum(mid,op)-rng.uniform(0,.5,n)
    bars=pd.DataFrame({"ts":ts,"bid_o":op-spread/2,"bid_h":high-spread/2,
        "bid_l":low-spread/2,"bid_c":mid-spread/2,"ask_o":op+spread/2,
        "ask_h":high+spread/2,"ask_l":low+spread/2,"ask_c":mid+spread/2})
    stamps=(ts.astype("datetime64[ns, UTC]").astype("int64")//1_000_000_000).to_numpy("<i8")
    raw=bars[["bid_o","bid_h","bid_l","bid_c","ask_o","ask_h","ask_l","ask_c"]].to_numpy("<f8")
    jobs=[]; expected=[]; scalar_cases=[]
    code={"tp":1,"stop":-1,"time":0,"no_fill":-2}
    for _ in range(10_000):
        signal=int(rng.integers(0,n-4)); side=int(rng.choice([-1,1])); delay=int(rng.integers(1,4))
        entry_index=min(signal+delay,n-1); entry=float(mid[entry_index])
        risk=float(rng.uniform(.1,.8)); sl=entry-side*risk
        tp=entry+side*float(rng.uniform(.1,1.6))
        hold_hours=int(rng.integers(2,36))
        deadline=ts[entry_index]+pd.Timedelta(hours=hold_hours)
        limit=None; expiry=None
        if _%4==0:
            limit=float((bars.ask_l.iloc[entry_index]+bars.ask_o.iloc[entry_index])/2 if side>0
                        else (bars.bid_h.iloc[entry_index]+bars.bid_o.iloc[entry_index])/2)
            expiry=ts[min(entry_index+int(rng.integers(1,15)),n-1)]
        instrument_class="crypto" if _%2 else "index"
        jobs.extend([signal,side,entry,sl,tp,int(deadline.timestamp()),delay,.0002 if instrument_class=="index" else .0006,
                     np.nan if limit is None else limit,np.nan if expiry is None else int(expiry.timestamp()),
                     1 if instrument_class=="crypto" else 0])
        ref=first_hit_reference(bars,signal,side,entry,sl,tp,delay_bars=delay,
            deadline_ts=deadline,expiry_ts=expiry,limit_price=limit,
            financing_per_night=.0002 if instrument_class=="index" else .0006,
            instrument_class=instrument_class,detailed=True)
        expected.append(ref)
        scalar_cases.append((signal,side,entry,sl,tp,delay,deadline,expiry,limit,instrument_class,ref))
    result=np.asarray(first_hit_batch(raw.tobytes(),stamps.tobytes(),jobs,11),dtype=float).reshape(-1,9)
    for got,ref in zip(result,expected):
        reason,exit_i,exit_price,net,gross,fill,nights,entry_i,planned=ref
        assert int(got[0])==code[reason] and int(got[1])==exit_i and int(got[6])==nights and int(got[7])==entry_i
        assert np.allclose([got[2],got[3],got[4],got[5],got[8]],[fill,exit_price,net,gross,planned],rtol=1e-12,atol=1e-12,equal_nan=True)
    for signal,side,entry,sl,tp,delay,deadline,expiry,limit,instrument_class,ref in scalar_cases:
        got=first_hit(bars,signal,side,entry,sl,tp,delay_bars=delay,
            financing_per_night=.0002 if instrument_class=="index" else .0006,
            limit_price=limit,deadline_ts=deadline,expiry_ts=expiry,
            instrument_class=instrument_class,detailed=True)
        assert got[0:2]==ref[0:2] and got[6:8]==ref[6:8]
        assert np.allclose([got[2],got[3],got[4],got[5],got[8]],
                           [ref[2],ref[3],ref[4],ref[5],ref[8]],rtol=1e-12,atol=1e-12,equal_nan=True)


def test_label_deadline_gap_and_financing_classes():
    from msd.processing.labels import _night_count, first_hit_reference
    ts=pd.DatetimeIndex([pd.Timestamp("2024-06-07 20:00",tz="UTC"),
                         pd.Timestamp("2024-06-10 13:00",tz="UTC")])
    bars=pd.DataFrame({"ts":ts,"bid_o":[100.,101.],"bid_h":[100.2,101.2],"bid_l":[99.8,100.8],"bid_c":[100.,101.],
        "ask_o":[100.1,101.1],"ask_h":[100.3,101.3],"ask_l":[99.9,100.9],"ask_c":[100.1,101.1]})
    deadline=pd.Timestamp("2024-06-08 12:00",tz="UTC")
    result=first_hit_reference(bars,0,1,100.,98.,110.,delay_bars=0,deadline_ts=deadline,detailed=True)
    assert result[0]=="time" and result[1]==1 and result[2]==101.
    assert _night_count(pd.Timestamp("2024-06-08 12:00",tz="UTC"),pd.Timestamp("2024-06-10 12:00",tz="UTC"),"crypto")==2
    assert _night_count(pd.Timestamp("2024-06-10 19:00",tz="UTC"),pd.Timestamp("2024-06-10 20:00",tz="UTC"),"index")==0


def test_label_grid_can_limit_signal_timestamps_without_changing_outcomes():
    from msd.processing.labels import label_grid
    ts=pd.date_range("2024-01-01",periods=120,freq="min",tz="UTC")
    mid=np.linspace(100,101,len(ts))
    bars=pd.DataFrame({"ts":ts,"bid_o":mid-.05,"bid_h":mid+.2,"bid_l":mid-.2,"bid_c":mid,
        "ask_o":mid+.05,"ask_h":mid+.3,"ask_l":mid-.1,"ask_c":mid+.1})
    atr=pd.Series(np.ones(len(bars)),index=bars.index)
    all_rows=label_grid(bars,atr,max_trading_days=1,instrument_class="crypto")
    bounded=label_grid(bars,atr,max_trading_days=1,instrument_class="crypto",
                       signal_start=ts[30],signal_end=ts[90])
    all_rows=all_rows[(all_rows.signal_index>=30)&(all_rows.signal_index<90)].reset_index(drop=True)
    pd.testing.assert_frame_equal(bounded,all_rows,check_dtype=False)


def test_label_grid_accepts_preregistered_stage9_financing(monkeypatch):
    from msd.processing.labels import label_grid
    import msd._msd_kernels as kernels
    ts=pd.date_range("2024-01-01",periods=20,freq="min",tz="UTC")
    bars=_bars(ts);atr=pd.Series(np.ones(len(bars)))
    captured=[]
    def fake_batch(_bars,_times,jobs,size,*_args):
        captured.extend(jobs)
        return np.tile([0.,19.,100.,100.,0.,0.,0.,2.,1.],len(jobs)//size).tolist()
    monkeypatch.setattr(kernels,"first_hit_batch",fake_batch)
    label_grid(bars,atr,max_trading_days=1,instrument_class="fx",financing_per_night=.00015)
    assert set(np.asarray(captured).reshape(-1,11)[:,7]) == {.00015}


def test_verified_month_is_skipped_on_resume(monkeypatch, tmp_path):
    from msd.processing import pipeline
    frame=_bars(pd.date_range("2024-01-01",periods=5,freq="min",tz="UTC"))
    monkeypatch.setattr(pipeline,"_check_disk",lambda:None)
    assert pipeline._write_monthly(frame,tmp_path,"EURUSD")==5
    target=tmp_path/"EURUSD/2024-01.parquet"
    assert target.exists() and target.with_name(target.name+".verified.json").exists()
    monkeypatch.setattr(pd.DataFrame,"to_parquet",lambda *_args,**_kwargs: pytest.fail("verified month rewritten"))
    assert pipeline._write_monthly(frame,tmp_path,"EURUSD")==5


def test_label_gap_sl_first_and_favorable_limit_fill_rules():
    from msd.processing.labels import first_hit, first_hit_reference
    ts=pd.date_range("2024-01-02",periods=3,freq="min",tz="UTC")
    bars=pd.DataFrame({"ts":ts,
        "bid_o":[100.,98.,101.],"bid_h":[100.5,103.,103.],"bid_l":[99.5,97.,100.5],"bid_c":[100.,102.,102.],
        "ask_o":[100.1,98.1,101.1],"ask_h":[100.6,103.1,103.1],"ask_l":[99.6,97.1,100.6],"ask_c":[100.1,102.1,102.1]})
    # Ambiguous gap-through market bar: SL wins and fills at the bid open.
    market=first_hit(bars,0,1,100.,99.,101.,delay_bars=1,deadline_ts=ts[2],detailed=True)
    market_ref=first_hit_reference(bars,0,1,100.,99.,101.,delay_bars=1,deadline_ts=ts[2],detailed=True)
    assert market==market_ref
    assert market[0]=="stop" and market[2]==98.
    # Limit is filled at the favorable ask open, and its fill bar cannot trigger TP.
    limit_bars=bars.copy()
    limit_bars.loc[1,["bid_o","bid_l","ask_o","ask_l"]]=[99.5,99.4,99.6,99.5]
    deadline=ts[2]+pd.Timedelta(minutes=1)
    limit=first_hit(limit_bars,0,1,100.,98.,102.,delay_bars=1,limit_price=100.,
                    expiry_ts=deadline,deadline_ts=deadline,detailed=True)
    limit_ref=first_hit_reference(limit_bars,0,1,100.,98.,102.,delay_bars=1,limit_price=100.,
                    expiry_ts=deadline,deadline_ts=deadline,detailed=True)
    assert limit==limit_ref
    assert limit[0]=="tp" and limit[5]==99.6 and limit[2]==102.


def test_label_kernel_matches_shared_simulator_on_sample_order():
    from msd.backtest import simulate
    from msd.processing.labels import first_hit_reference
    ts = pd.date_range("2024-06-03 14:00", periods=40, freq="min", tz="UTC")
    mid = 100 + np.sin(np.arange(40)/4)
    bars = pd.DataFrame({"ts":ts,"bid_o":mid-.05,"bid_h":mid+.4,"bid_l":mid-.4,"bid_c":mid,
                         "ask_o":mid+.05,"ask_h":mid+.5,"ask_l":mid-.3,"ask_c":mid+.1})
    signal_i, side, sl, tp, hold = 2, 1, 98., 101., 12
    ref = first_hit_reference(bars, signal_i, side, float(mid[signal_i]), sl, tp, hold, delay_bars=2)
    entry_i = signal_i+2
    sim = simulate(bars,[{"decision_ts":ts[entry_i-1],"side":side,"stop":sl,"tp":tp,
                          "exit_ts":ts[entry_i+hold]}]).iloc[0]
    assert sim.exit_reason == ref[0]
    assert sim.exit_ts == ts[ref[1]]
    assert np.isclose(sim.exit_price,ref[2])


def test_strategy_check_catches_future_leak():
    from types import SimpleNamespace
    from msd.strategy_check import assert_causal
    ts = pd.date_range("2024-01-01", periods=20, freq="min", tz="UTC")
    bars = _bars(ts)
    def leaky_orders(frame):
        if frame.bid_c.iloc[-1] > frame.bid_c.iloc[0] + 10:
            return [{"decision_ts": frame.ts.iloc[0], "side": 1, "stop": 99., "tp": 102.}]
        return []
    try:
        assert_causal(SimpleNamespace(orders=leaky_orders), bars, n=5, seed=1)
    except AssertionError:
        pass
    else:
        raise AssertionError("causal checker missed future-dependent output")


def test_pilot_sr_touch_requires_two_touches_and_a_fresh_approach():
    from msd.methods.sr_touch import detect
    ts=pd.date_range("2024-01-01",periods=4,freq="min",tz="UTC")
    bars=pd.DataFrame({"ts":ts,"bid_o":[101,101,101,100.1],"bid_h":[101.2,102,101.2,100.2],
                       "bid_l":[99.8,101,99.8,99.9],"bid_c":[101,101.5,101,100.05],
                       "ask_o":[101.1,101.1,101.1,100.2],"ask_h":[101.3,102.1,101.3,100.3],
                       "ask_l":[99.9,101.1,99.9,100.0],"ask_c":[101.1,101.6,101.1,100.15]})
    features=pd.DataFrame({"ts":ts,"known_at":ts+pd.Timedelta(minutes=1),"1h_atr14":1.})
    levels=pd.DataFrame([{"level_id":1,"price":100.,"type":"swing_high","known_at":ts[0],
                          "timeframe":"15m","strength":1/3,"created_at":ts[0]},
                         {"level_id":2,"price":100.05,"type":"swing_high","known_at":ts[0],
                          "timeframe":"15m","strength":1/3,"created_at":ts[0]}])
    events=detect(features,levels,bars)
    assert len(events)==1 and events[0]["ts"]==ts[2]
    assert events[0]["side_candidates"]==[1,-1]
    assert events[0]["approach_direction"]=="from_above_support"
    assert events[0]["cluster_id"]==1


def test_pilot_liquidity_sweep_returns_inside_causally():
    from msd.methods.liquidity_sweep import detect
    ts=pd.date_range("2024-01-01",periods=4,freq="min",tz="UTC")
    bars=pd.DataFrame({"ts":ts,"bid_o":[100.,103.,100.1,99.9],"bid_h":[100.1,103.2,100.3,100.1],
                       "bid_l":[99.9,102.8,99.8,99.7],"bid_c":[100.,103.,100.1,99.9],
                       "ask_o":[100.01,103.01,100.11,99.91],"ask_h":[100.11,103.21,100.31,100.11],
                       "ask_l":[99.91,102.81,99.81,99.71],"ask_c":[100.01,103.01,100.11,99.91]})
    features=pd.DataFrame({"ts":ts,"known_at":ts+pd.Timedelta(minutes=1),"1h_atr14":2.})
    levels=pd.DataFrame([{"level_id":4,"price":100.,"type":"prior_day_high","known_at":ts[0],
                          "timeframe":"1d","strength":1.,"created_at":ts[0]},
                         {"level_id":5,"price":100.02,"type":"swing_high","known_at":ts[0],
                          "timeframe":"15m","strength":1/3,"created_at":ts[0]}])
    events=detect(features,levels,bars)
    assert len(events)==1 and events[0]["ts"]==ts[3] and events[0]["side"]==-1
    assert events[0]["cluster_id"]==4
    assert events[0]["natural_sl"]==100.3 and events[0]["known_at"]==ts[3]+pd.Timedelta(minutes=1)


def test_exit_candidates_use_prepared_causal_nearest_level():
    from msd.methods.common import exit_candidates, prepare_exit_levels
    ts=pd.Timestamp("2024-01-01",tz="UTC")
    levels=pd.DataFrame({"price":[101.,102.,103.],"type":["swing_high"]*3,
                         "known_at":[ts-pd.Timedelta(minutes=1),ts+pd.Timedelta(minutes=1),ts],
                         "invalidated_at":[ts,pd.NaT,pd.NaT]})
    event={"side":1,"price":100.,"known_at":ts,"natural_sl":None,"natural_tp":None}
    prepared=prepare_exit_levels(levels)
    result=exit_candidates(event,levels,1.,prepared)
    structural=[candidate for candidate in result if candidate["kind"].startswith("structural:")]
    assert len(structural)==1 and structural[0]["tp"]==103.


def test_feature_store_keeps_close_time_metadata_and_float32_features():
    from msd.processing.features import build_features
    ts=pd.date_range("2024-01-01",periods=100,freq="min",tz="UTC")
    bars=_bars(ts)
    features=build_features(bars,"BTCUSDT",timeframes={})
    assert np.array_equal(features.ts.astype("int64").to_numpy(),bars.ts.astype("datetime64[ns, UTC]").astype("int64").to_numpy())
    assert (features.known_at==bars.ts+pd.Timedelta(minutes=1)).all()
    assert len(features.select_dtypes("float64").columns)==0


def test_level_feature_join_normalizes_object_timestamp_columns():
    from msd.processing.features import build_features
    ts=pd.date_range("2024-01-01",periods=100,freq="min",tz="UTC")
    bars=_bars(ts)
    levels=pd.DataFrame({"price":[101.0],"type":["prior_day_high"],
                         "timeframe":["1d"],"created_at":[ts[0].isoformat()],
                         "known_at":[ts[0].isoformat()],"invalidated_at":[None],
                         "direction":[0],"strength":[1.0]})
    features=build_features(bars,"BTCUSDT",timeframes={},levels=levels)
    assert len(features)==len(bars)
    assert features.known_at.dtype=="datetime64[ns, UTC]"


def test_zero_spread_dukas_ticks_get_nearest_valid_annual_spread():
    from msd.processing.pipeline import _modelled_spread
    ts=pd.date_range("2024-01-01",periods=3,freq="min",tz="UTC")
    frame=pd.DataFrame({"ts":ts})
    for field in "ohlc":
        frame[f"bid_{field}"]=[100.,101.,102.]
        frame[f"ask_{field}"]=[100.2,101.,102.4]
    result=_modelled_spread(frame,"XAUUSD")
    assert result.loc[1,"ask_o"]-result.loc[1,"bid_o"]==pytest.approx(0.3)
    assert result.loc[0,"ask_o"]-result.loc[0,"bid_o"]==pytest.approx(0.2)
    assert result.spread_modeled.tolist()==[False,True,False]


def test_spread_modeled_bars_keep_label_costs_but_mask_spread_features():
    from msd.processing.pipeline import _modelled_spread
    from msd.processing.features import build_features
    ts=pd.date_range("2024-01-01",periods=40,freq="min",tz="UTC")
    bars=_bars(ts)
    bars["spread_modeled"]=[False,True]*20
    executable=_modelled_spread(bars,"BTCUSDT")
    assert executable.spread_modeled.all()
    assert (executable.ask_o>executable.bid_o).all()
    features=build_features(executable,"BTCUSDT",timeframes={})
    assert features.spread_modeled.dtype==bool
    assert features.spread_modeled.all()
    assert features.spread_atr.isna().all()


def test_month_window_features_match_full_history_rows():
    from msd.processing.features import build_features,prepare_feature_cache
    ts=pd.date_range("2024-01-01",periods=2400,freq="min",tz="UTC")
    bars=_bars(ts)
    full=build_features(bars,"BTCUSDT",timeframes={})
    start,end=ts[1200],ts[1800]
    chunk=build_features(bars,"BTCUSDT",timeframes={},output_start=start,output_end=end)
    expected=full[(full.ts>=start)&(full.ts<end)].reset_index(drop=True)
    pd.testing.assert_frame_equal(chunk,expected,check_dtype=True,check_exact=True)
    cache=prepare_feature_cache(bars,"BTCUSDT",{})
    chunks=pd.concat([build_features(bars,"BTCUSDT",timeframes={},output_start=start,output_end=ts[1500],cache=cache),
                      build_features(bars,"BTCUSDT",timeframes={},output_start=ts[1500],output_end=end,cache=cache)],ignore_index=True)
    pd.testing.assert_frame_equal(chunks,expected,check_dtype=True,check_exact=True)


def test_bollinger_features_are_exact_across_truncated_history():
    from msd.processing.features import indicator_frame
    rng=np.random.default_rng(4102)
    ts=pd.date_range("2021-01-01",periods=5000,freq="min",tz="UTC")
    close=100+np.cumsum(rng.normal(0,.2,len(ts)))
    bars=pd.DataFrame({"ts":ts,"bid_o":close,"bid_h":close+.15,"bid_l":close-.15,
                       "bid_c":close,"ask_o":close+.01,"ask_h":close+.16,
                       "ask_l":close-.14,"ask_c":close+.01,"volume":np.ones(len(ts))})
    cut=3200
    full=indicator_frame(bars)
    truncated=indicator_frame(bars.iloc[cut-100:])
    for column in ("bollinger_pctb20","bollinger_width20"):
        np.testing.assert_array_equal(full[column].to_numpy()[cut:],
                                      truncated[column].to_numpy()[100:])


def test_feature_returns_are_timeframe_specific_and_no_infinities(tmp_path):
    from msd.processing.features import build_features, indicator_frame
    from msd.processing.features import RETURN_WINDOWS
    ts=pd.date_range("2024-01-01",periods=120,freq="min",tz="UTC")
    bars=_bars(ts)
    features=build_features(bars,"BTCUSDT",timeframes={})
    assert "1m_return_bars_1440" in features
    assert "1m_return_1440" not in features
    assert RETURN_WINDOWS=={"1m":(1,5,15,60,240,1440),"5m":(1,4,12,48),"15m":(1,4,12,48),
                            "1h":(1,4,24,120),"4h":(1,6,30),"1d":(1,5,20,60)}
    daily=indicator_frame(bars,"1d")
    assert "return_bars_60" in daily and "return_bars_1440" not in daily
    assert not np.isinf(features.select_dtypes(include=[np.number]).to_numpy()).any()
    file=tmp_path/"features.parquet"
    features.to_parquet(file)
    stored=pd.read_parquet(file)
    assert not np.isinf(stored.select_dtypes(include=[np.number]).to_numpy()).any()
    flat=bars.copy()
    for col in ("bid_o","bid_h","bid_l","bid_c","ask_o","ask_h","ask_l","ask_c"):
        flat[col]=0.
    from msd.processing.features import indicator_frame
    assert not np.isinf(indicator_frame(flat).to_numpy(dtype=float)).any()


def test_feature_qa_writes_yearly_constant_and_nan_flags(tmp_path):
    from msd.processing.features import feature_qa
    frame=pd.DataFrame({"ts":pd.date_range("2024-01-01",periods=4,freq="min",tz="UTC"),
                        "known_at":pd.date_range("2024-01-01 00:01",periods=4,freq="min",tz="UTC"),
                        "constant":np.ones(4),"empty":np.full(4,np.nan),"varying":[np.nan,1.,2.,3.]})
    path=feature_qa(frame,"TEST",tmp_path)
    report=path.read_text()
    assert "constant full year" in report and "all-NaN full year" in report
    assert "varying" in report


def test_label_input_requires_positive_spread_for_all_ohlc():
    from msd.processing.pipeline import assert_executable_spread
    frame=_bars(pd.date_range("2024-01-01",periods=2,freq="min",tz="UTC"))
    assert_executable_spread(frame,"TEST")
    frame.loc[1,"ask_h"]=frame.loc[1,"bid_h"]
    try:
        assert_executable_spread(frame,"TEST")
    except ValueError as exc:
        assert "spread" in str(exc)
    else:
        raise AssertionError("zero spread was accepted for labels")


def test_bad_tick_flag_is_preserved_in_source_but_excluded_from_features_labels():
    from msd.processing.pipeline import _feature_label_bars
    source=_bars(pd.date_range("2024-01-01",periods=3,freq="min",tz="UTC"))
    source["bad_tick"]=[False,True,False]
    derived=_feature_label_bars(source)
    assert len(source)==3 and source.bad_tick.iloc[1]
    assert derived.ts.tolist()==[source.ts.iloc[0],source.ts.iloc[2]]


def test_oil_nonexecutable_quotes_are_excluded_and_audited(capsys):
    from msd.processing.pipeline import (
        _exclude_nonexecutable_oil_quotes,
        assert_executable_spread,
    )
    ts=pd.date_range("2020-04-01",periods=4,freq="min",tz="UTC")
    source=_bars(ts)
    source.loc[1,"ask_o"]=source.loc[1,"bid_o"]
    source.loc[2,"ask_c"]=source.loc[2,"bid_c"]-.01
    source.loc[3,"ask_h"]=np.nan

    result=_exclude_nonexecutable_oil_quotes(
        source,"LIGHTCMDUSD",ts[0],ts[-1]+pd.Timedelta(minutes=1))
    assert result.ts.tolist()==[ts[0]]
    assert_executable_spread(result,"LIGHTCMDUSD")
    audit=capsys.readouterr().out
    assert "'excluded': 3" in audit
    assert "'nonfinite': 1" in audit
    assert "'zero_spread': 1" in audit
    assert "'crossed': 1" in audit

    untouched=_exclude_nonexecutable_oil_quotes(source,"EURUSD")
    assert len(untouched)==4


def test_modeled_btc_spread_is_baked_into_every_label_bar(monkeypatch):
    from msd.processing import pipeline
    from msd.data.binance import BTC_SPREAD
    ts=pd.date_range("2024-07-01",periods=3,freq="min",tz="UTC")
    bars=_bars(ts)
    monkeypatch.setattr(pipeline,"load",lambda *args,**kwargs: pd.DataFrame())
    modeled=pipeline._modelled_spread(bars,"BTCUSDT")
    for field in "ohlc":
        assert np.allclose(modeled[f"ask_{field}"]-modeled[f"bid_{field}"],BTC_SPREAD[2024])
    pipeline.assert_executable_spread(modeled,"BTCUSDT")


def test_data_load_is_executable_by_default_and_raw_is_available(monkeypatch):
    from msd.data import load
    from msd.data import catalog
    from msd.data.binance import BTC_SPREAD
    ts=pd.date_range("2024-06-12",periods=4,freq="min",tz="UTC")
    spot=_bars(ts)
    spot[[f"{side}_{field}" for side in ("bid","ask") for field in "ohlc"]]=np.tile(
        np.array([100.,101.,99.,100.]),(len(spot),2))
    duka=_bars(ts)
    def fake_load_source(vendor_symbol,start,end,source):
        return spot.copy() if source=="binance_spot" else duka.copy()
    monkeypatch.setattr(catalog,"load_source",fake_load_source)
    executable=load("BTCUSDT",ts[0],ts[-1])
    raw=load("BTCUSDT",ts[0],ts[-1],raw=True)
    assert (executable.ask_o>executable.bid_o).all()
    assert np.allclose(executable.ask_o-executable.bid_o,BTC_SPREAD[2024])
    assert executable.spread_modeled.dtype==bool and executable.spread_modeled.all()
    assert (raw.ask_o==raw.bid_o).all()


def test_open_interest_change_zero_baseline_is_nan_not_inf():
    from msd.processing.features import build_features
    ts=pd.date_range("2024-01-01",periods=4,freq="min",tz="UTC")
    bars=_bars(ts)
    bars["open_interest"]=[0.,1.,2.,4.]
    features=build_features(bars,"BTCUSDT",timeframes={})
    assert pd.isna(features.open_interest_change.iloc[1])
    assert np.isfinite(features.open_interest_change.iloc[2])
    assert not np.isinf(features.select_dtypes(include=[np.number]).to_numpy()).any()


def test_funding_asof_join_uses_publish_time_and_trailing_print_z(monkeypatch):
    from msd.processing import pipeline
    ts=pd.date_range("2024-01-01",periods=30,freq="8h",tz="UTC")
    funding=pd.DataFrame({"ts":ts,"funding_rate":np.arange(30,dtype=float),"mark_price":100.})
    monkeypatch.setattr(pipeline,"_parquet_union",lambda path: funding.copy() if "funding" in str(path) else pd.DataFrame())
    bars=_bars(ts)
    attached=pipeline._attach_market_auxiliary(bars,"BTCUSDT")
    assert attached.funding_rate.iloc[-1]==29
    assert np.isfinite(attached.funding_z20.iloc[-1])
    assert pd.isna(attached.funding_z20.iloc[18])
    features=__import__("msd.processing.features",fromlist=["build_features"]).build_features(attached,"BTCUSDT",timeframes={})
    assert np.isfinite(features.funding_z20.iloc[-1])


def test_daily_rsi_pilot_respects_declared_index_symbol_scope():
    from msd.processing.pipeline import methods_for_symbol
    assert "rsi2_mean_reversion" not in [method.NAME for method in methods_for_symbol("BTCUSDT")]
    assert "rsi2_mean_reversion" in [method.NAME for method in methods_for_symbol("USATECHIDXUSD")]


def test_level_pivot_known_at_confirmation_close():
    from msd.processing.levels import pivot_events
    ts = pd.date_range("2024-01-01", periods=9, freq="5min", tz="UTC")
    high = np.array([1, 2, 3, 4, 10, 4, 3, 2, 1.])
    frame = pd.DataFrame({"ts": ts, "known_at": ts+pd.Timedelta(minutes=5),
                          "bid_h": high, "bid_l": -high})
    pivots = pivot_events(frame, 3, "5m")
    high_pivot = pivots[pivots.type == "swing_high"].iloc[0]
    assert high_pivot.created_at == ts[4]
    assert high_pivot.known_at == ts[7]+pd.Timedelta(minutes=5)


def test_200_point_feature_level_event_truncation_and_future_perturbation():
    from msd.methods.liquidity_sweep import detect
    from msd.methods.sr_touch import detect as detect_sr
    from msd.processing.features import indicator_frame
    from msd.processing.levels import pivot_events
    rng = np.random.default_rng(8)
    n = 360
    ts = pd.date_range("2024-01-01", periods=n, freq="min", tz="UTC")
    close = 100 + np.cumsum(rng.normal(0, .15, n))
    op = np.r_[close[0], close[:-1]]
    high = np.maximum(op, close) + rng.uniform(.01, .5, n)
    low = np.minimum(op, close) - rng.uniform(.01, .5, n)
    bars = pd.DataFrame({"ts": ts, "bid_o": op, "bid_h": high, "bid_l": low, "bid_c": close,
                         "ask_o": op+.02, "ask_h": high+.02, "ask_l": low+.02, "ask_c": close+.02,
                         "volume": rng.uniform(1, 20, n), "known_at": ts+pd.Timedelta(minutes=1)})
    full_ind = indicator_frame(bars)
    full_features = pd.DataFrame({"ts": ts, "known_at": bars.known_at, "1m_atr14": full_ind.atr14})
    level = pd.DataFrame([{"level_id": 1, "price": float(np.median(close)), "type": "swing_high",
                           "timeframe": "5m", "created_at": ts[0], "known_at": ts[0]+pd.Timedelta(minutes=1),
                           "touches_so_far": 0, "invalidated_at": pd.NaT, "strength": 1., "direction": -1}])
    full_pivots = pivot_events(bars, 3, "1m")
    full_events = detect(full_features, level, bars)
    full_sr_events = detect_sr(full_features, level, bars)
    event_sig = lambda events, cut: [(e["ts"], e["side"], e["natural_sl"], e["known_at"])
                                    for e in events if e["known_at"] <= cut]
    for cut_i in rng.integers(2, n-1, 200):
        cut = ts[cut_i]+pd.Timedelta(minutes=1)
        part = bars.iloc[:cut_i+1].copy()
        ind = indicator_frame(part)
        part_features = pd.DataFrame({"ts": part.ts, "known_at": part.known_at, "1m_atr14": ind.atr14})
        pivots = pivot_events(part, 3, "1m")
        past_full = full_pivots[full_pivots.known_at <= cut].reset_index(drop=True)
        past_part = pivots[pivots.known_at <= cut].reset_index(drop=True)
        if past_full.empty:
            assert past_part.empty
        else:
            pd.testing.assert_frame_equal(past_full, past_part)
        assert event_sig(full_events, cut) == event_sig(detect(part_features, level, part), cut)
        assert event_sig(full_sr_events, cut) == event_sig(detect_sr(part_features, level, part), cut)
        perturbed = bars.copy()
        perturbed.loc[cut_i+1:, ["bid_o", "bid_h", "bid_l", "bid_c", "ask_o", "ask_h", "ask_l", "ask_c"]] *= 3
        perturbed.loc[cut_i+1:, "volume"] *= 19
        p_ind = indicator_frame(perturbed)
        p_features = pd.DataFrame({"ts": ts, "known_at": perturbed.known_at, "1m_atr14": p_ind.atr14})
        assert event_sig(full_events, cut) == event_sig(detect(p_features, level, perturbed), cut)
        assert event_sig(full_sr_events, cut) == event_sig(detect_sr(p_features, level, perturbed), cut)


def test_levels_asof_selects_only_confirmed_state_and_drops_invalidated_levels():
    from msd.processing.levels import levels_asof
    base=pd.Timestamp("2024-01-01",tz="UTC")
    levels=pd.DataFrame({
        "level_id":[7,7,7], "price":[100.,100.,100.], "type":["prior_day_high"]*3,
        "timeframe":["1d"]*3, "created_at":[base]*3,
        "known_at":[base]*3, "state_at":[base,base+pd.Timedelta(hours=1),base+pd.Timedelta(hours=2)],
        "touches_so_far":[0,1,1], "invalidated_at":[pd.NaT,pd.NaT,base+pd.Timedelta(hours=2)],
    })
    assert levels_asof(levels,base+pd.Timedelta(minutes=30)).touches_so_far.tolist()==[0]
    assert levels_asof(levels,base+pd.Timedelta(hours=1,minutes=30)).touches_so_far.tolist()==[1]
    assert levels_asof(levels,base+pd.Timedelta(hours=3)).empty


def test_event_label_batch_passes_calendar_deadline_and_instrument_class(monkeypatch):
    from msd.processing import pipeline
    from msd.processing.labels import deadline_after_trading_days
    import msd._msd_kernels as kernels
    ts=pd.date_range("2024-03-08 19:00",periods=8,freq="min",tz="UTC")
    bars=_bars(ts)
    bars["bid_h"]=bars.bid_c+0.1;bars["bid_l"]=bars.bid_c-0.1
    bars["ask_h"]=bars.ask_c+0.1;bars["ask_l"]=bars.ask_c-0.1
    features=pd.DataFrame({"ts":ts,"1m_atr14":np.full(len(ts),1.)})
    class Dummy:
        NAME="dummy"
        @staticmethod
        def detect(*_args):
            return [{"ts":ts[0],"side":1,"price":100.5,"natural_sl":99.,"natural_tp":103.,"known_at":ts[0]+pd.Timedelta(minutes=1)}]
    monkeypatch.setattr(pipeline,"methods_for_symbol",lambda _symbol:(Dummy,))
    seen=[]
    def fake_batch(_rows,_times,jobs,job_size):
        seen.append((list(jobs),job_size))
        count=len(jobs)//job_size
        return np.tile([0.,len(ts)-1,100.6,101.,0.,0.,0.,2.,1.],count).tolist()
    monkeypatch.setattr(kernels,"first_hit_batch",fake_batch)
    for symbol,instrument_class in (("USA500IDXUSD","index"),("BTCUSDT","crypto")):
        seen.clear()
        result=pipeline.label_method_events(features,pd.DataFrame(),bars,symbol)
        assert len(result)>0 and seen
        jobs,job_size=seen[0]
        assert job_size==11 and len(jobs)%11==0
        expected=deadline_after_trading_days(ts[2],5,instrument_class).value//1_000_000_000
        assert set(np.asarray(jobs).reshape(-1,11)[:,5].astype(np.int64))=={expected}
        assert set(np.asarray(jobs).reshape(-1,11)[:,10])==({0.} if instrument_class=="index" else {1.})


def test_rsi2_daily_event_appears_after_gap_when_daily_close_becomes_available():
    from msd.methods.rsi2_mean_reversion import detect
    # June 3 16:15–18:07 ET has no 1m quotes. The CME daily bar closes at
    # 17:00 ET (21:00 UTC), so the first observable feature row is at 18:07 ET.
    ts=pd.to_datetime(["2024-06-03 20:13Z","2024-06-03 20:14Z",
                       "2024-06-03 22:07Z","2024-06-03 22:08Z","2024-06-03 22:09Z"],utc=True)
    bars=pd.DataFrame({"ts":ts,"bid_c":[100.]*5,"ask_c":[100.2]*5})
    daily_close=pd.to_datetime(["2024-06-03 20:00Z","2024-06-03 20:00Z",
                                "2024-06-03 21:00Z","2024-06-03 21:00Z",
                                "2024-06-03 21:00Z"],utc=True)
    features=pd.DataFrame({"ts":ts,"known_at":ts+pd.Timedelta(minutes=1),
                           "1d_bar_known_at":daily_close,"1d_rsi2":[50.,50.,5.,5.,5.],
                           "1d_ema200_distance_atr":[1.]*5})
    events=detect(features,pd.DataFrame(),bars)
    assert len(events)==1
    assert events[0]["ts"]==ts[2]
    assert events[0]["known_at"]==ts[2]+pd.Timedelta(minutes=1)


def test_rsi2_uses_asof_transition_not_exact_htf_timestamp():
    from msd.methods.rsi2_mean_reversion import detect
    ts=pd.date_range("2024-06-04 22:07",periods=3,freq="min",tz="UTC")
    bars=pd.DataFrame({"ts":ts,"bid_c":[100.]*3,"ask_c":[100.2]*3})
    known=pd.to_datetime(["2024-06-04 21:00Z"]*3,utc=True)
    features=pd.DataFrame({"ts":ts,"known_at":ts+pd.Timedelta(minutes=1),
                           "1d_bar_known_at":known,"1d_rsi2":[5.]*3,
                           "1d_ema200_distance_atr":[1.]*3})
    assert len(detect(features,pd.DataFrame(),bars))==1


def test_pipeline_registry_contains_new_detectors_and_filters_by_scope():
    from msd.processing.pipeline import METHOD_REGISTRY, methods_for_symbol
    names=[method.NAME for method in METHOD_REGISTRY]
    assert len(names)==len(set(names))==33
    btc={method.NAME for method in methods_for_symbol("BTCUSDT")}
    index={method.NAME for method in methods_for_symbol("USATECHIDXUSD")}
    assert "btc_order_flow" in btc and "btc_order_flow" not in index
    assert "post_earnings_index_reaction" in index and "post_earnings_index_reaction" not in btc


def test_event_limit_order_fields_are_passed_to_batch_labeler(monkeypatch):
    from msd.processing import pipeline
    import msd._msd_kernels as kernels
    ts=pd.date_range("2024-01-02",periods=8,freq="min",tz="UTC")
    bars=_bars(ts)
    features=pd.DataFrame({"ts":ts,"1m_atr14":np.ones(len(ts))})
    class LimitDummy:
        NAME="limit_dummy"
        @staticmethod
        def detect(*_args):
            return [{"ts":ts[0],"known_at":ts[0]+pd.Timedelta(minutes=1),"side":1,
                     "price":100.5,"natural_sl":99.,"natural_tp":105.,"entry_type":"limit",
                     "limit_price":101.,"expiry_at":ts[0]+pd.Timedelta(minutes=5)}]
    monkeypatch.setattr(pipeline,"methods_for_symbol",lambda _symbol:(LimitDummy,))
    seen=[]
    def fake_batch(_rows,_times,jobs,job_size):
        seen.extend(np.asarray(jobs,dtype=float).reshape(-1,job_size).tolist())
        return np.tile([0.,len(ts)-1,101.,106.,0.,0.,0.,2.,2.],len(jobs)//job_size).tolist()
    monkeypatch.setattr(kernels,"first_hit_batch",fake_batch)
    pipeline.label_method_events(features,pd.DataFrame(),bars,"BTCUSDT")
    assert seen and all(row[8]==101. for row in seen)
    assert all(row[9]==ts[0].timestamp()+300 for row in seen)


@pytest.mark.slow
def test_real_btc_jan22_end_to_end_event_truncation():
    """Rebuild HTFs, levels, features and events at 20 real-data cut points."""
    from pathlib import Path
    import gc
    import pytest
    from msd.data import load
    from msd.methods.sr_touch import detect as detect_sr
    from msd.methods.liquidity_sweep import detect as detect_sweep
    from msd.processing.features import build_features
    from msd.processing.levels import build_levels, levels_asof
    from msd.processing.timeframes import build_all_timeframes

    if not Path("data/bars/binance_spot/BTCUSDT/2022-01.parquet").exists():
        pytest.skip("local BTCUSDT 2022-01 bars are absent")
    start=pd.Timestamp("2021-01-26",tz="UTC")
    month_start=pd.Timestamp("2022-01-01",tz="UTC")
    month_end=pd.Timestamp("2022-02-01",tz="UTC")
    source=load("BTCUSDT",start,month_end)
    source=source[source.ts<month_end].sort_values("ts").reset_index(drop=True)
    assert source.ts.min()<=start+pd.Timedelta(minutes=2), "normal 370-day warm-up is incomplete"
    month_bars=source[(source.ts>=month_start)&(source.ts<month_end)].reset_index(drop=True)
    assert len(month_bars)>40_000

    def rebuild(history):
        history=history.sort_values("ts").reset_index(drop=True)
        tfs=build_all_timeframes(history,"BTCUSDT")
        all_levels=build_levels(history,"BTCUSDT",tfs)
        # Event detectors do not use session_vwap level rows; drop that dense
        # per-minute block before retaining snapshots for comparison.
        level_table=all_levels.loc[all_levels.type.ne("session_vwap")].copy()
        del all_levels
        feature_table=build_features(history,"BTCUSDT",tfs,level_table,
                                     output_start=month_start,output_end=month_end)
        month_features=feature_table[["ts","1h_atr14"]].copy()
        del feature_table,tfs
        event_bars=history[(history.ts>=month_start)&(history.ts<month_end)].reset_index(drop=True)
        return level_table,month_features,event_bars

    full_levels,full_features,full_event_bars=rebuild(source)
    full_sr=detect_sr(full_features,full_levels,full_event_bars)
    full_sweep=detect_sweep(full_features,full_levels,full_event_bars)
    cuts=np.linspace(1200,len(month_bars)-2,20,dtype=int)
    active_counts={"sr_touch":0,"liquidity_sweep":0}
    active_cut_times={"sr_touch":[],"liquidity_sweep":[]}

    def normalize(value):
        if isinstance(value,(list,tuple)):
            return tuple(normalize(item) for item in value)
        if isinstance(value,np.generic):
            value=value.item()
        if isinstance(value,pd.Timestamp):
            return value.isoformat()
        if isinstance(value,float) and np.isnan(value):
            return "NaN"
        return value

    signature_fields=("ts","known_at","method","side","side_candidates","price","natural_sl","natural_tp",
                      "cluster_price","cluster_strength","cluster_types","cluster_age_minutes","approach_direction")
    def signatures(events,cut):
        selected=[event for event in events if pd.Timestamp(event["known_at"])<=cut]
        return [tuple(normalize(event.get(field)) for field in signature_fields) for event in selected]

    level_fields=[c for c in ("price","type","timeframe","created_at","known_at","state_at","touches_so_far","invalidated_at","strength","direction") if c in full_levels]
    for index in cuts:
        cut=month_bars.ts.iloc[index]+pd.Timedelta(minutes=1)
        history=source[source.ts<cut].copy()
        truncated_levels,truncated_features,truncated_event_bars=rebuild(history)
        expected_sr=signatures(full_sr,cut)
        expected_sweep=signatures(full_sweep,cut)
        got_sr=signatures(detect_sr(truncated_features,truncated_levels,truncated_event_bars),cut)
        got_sweep=signatures(detect_sweep(truncated_features,truncated_levels,truncated_event_bars),cut)
        assert got_sr==expected_sr, f"S/R mismatch at {cut}: {len(got_sr)} vs {len(expected_sr)}"
        assert got_sweep==expected_sweep, f"sweep mismatch at {cut}: {len(got_sweep)} vs {len(expected_sweep)}"

        full_asof=levels_asof(full_levels,cut)[level_fields].sort_values(level_fields,kind="stable",na_position="first").reset_index(drop=True)
        truncated_asof=levels_asof(truncated_levels,cut)[level_fields].sort_values(level_fields,kind="stable",na_position="first").reset_index(drop=True)
        pd.testing.assert_frame_equal(full_asof,truncated_asof,check_dtype=False,check_exact=False,rtol=1e-12,atol=1e-12)
        for name,count in (("sr_touch",len(expected_sr)),("liquidity_sweep",len(expected_sweep))):
            if count:
                active_counts[name]+=1
                active_cut_times[name].append(cut.strftime("%Y-%m-%d %H:%MZ"))
        del history,truncated_levels,truncated_features,truncated_event_bars,full_asof,truncated_asof
        gc.collect()

    assert active_counts["sr_touch"]>=15, f"S/R test is too often vacuous: {active_counts}"
    assert active_counts["liquidity_sweep"]>=15, f"sweep test is too often vacuous: {active_counts}"
    print(f"BTCUSDT 2022-01 causal event cuts: S/R {active_counts['sr_touch']}/20 {active_cut_times['sr_touch']}; "
          f"sweep {active_counts['liquidity_sweep']}/20 {active_cut_times['liquidity_sweep']}")


@pytest.mark.slow
def test_real_btc_year_checkpoint_restores_five_sr_boundary_events():
    """A yearly detector checkpoint must preserve the five Jan 2022 S/R signatures."""
    import json
    from pathlib import Path
    from msd.data import load
    from msd.methods.sr_touch import detect
    from msd.processing.levels import apply_level_invalidations, build_levels
    from msd.processing.pipeline import _active_mask, _event_feature_frame
    from msd.processing.timeframes import build_all_timeframes

    if not Path("data/bars/binance_spot/BTCUSDT/2020-05.parquet").exists():
        pytest.skip("local BTC bars for the checkpoint span are absent")

    start=pd.Timestamp("2020-05-27",tz="UTC")
    split=pd.Timestamp("2022-01-01",tz="UTC")
    end=pd.Timestamp("2022-01-06",tz="UTC")
    bars=load("BTCUSDT",start,end).sort_values("ts").reset_index(drop=True)
    assert not bars.empty and bars.ts.min()<=start+pd.Timedelta(minutes=2)
    bars=bars[(bars.ts>=start)&(bars.ts<end)].reset_index(drop=True)
    active=bars.loc[_active_mask(bars,"BTCUSDT")].reset_index(drop=True)
    tfs=build_all_timeframes(bars,"BTCUSDT")
    features=_event_feature_frame(bars,tfs)
    levels=build_levels(active,"BTCUSDT",tfs)
    levels=levels.loc[levels.type.ne("session_vwap")].copy()
    levels=apply_level_invalidations(active,levels)
    first_bars=bars[bars.ts<split].reset_index(drop=True)
    first_active=first_bars.loc[_active_mask(first_bars,"BTCUSDT")].reset_index(drop=True)
    first_tfs=build_all_timeframes(first_bars,"BTCUSDT")
    first_levels=build_levels(first_active,"BTCUSDT",first_tfs)
    first_levels=first_levels.loc[first_levels.type.ne("session_vwap")].copy()
    first_levels=first_levels[pd.to_datetime(first_levels.known_at,utc=True)<=split]
    first_levels=apply_level_invalidations(first_active,first_levels)

    full_events,full_state,_=detect(features,levels,active,return_state=True)
    first_mask=active.ts<split
    pre_events,full_boundary,_=detect(features[features.ts<split],levels,
                                      active.loc[first_mask].reset_index(drop=True),return_state=True)
    chunk_pre,chunk_boundary,_=detect(features[features.ts<split],first_levels,
                                      active.loc[first_mask].reset_index(drop=True),return_state=True)
    assert full_boundary==chunk_boundary
    post_mask=active.ts>=split
    chunk_post,chunk_final,_=detect(features[features.ts>=split],levels,
                                    active.loc[post_mask].reset_index(drop=True),
                                    state=chunk_boundary,return_state=True)
    assert pre_events+chunk_post==full_events
    assert chunk_final==full_state

    fixture=json.loads(Path("tests/fixtures/sr_touch_btc_2022_boundary.json").read_text())
    by_ts={pd.Timestamp(event["ts"]).isoformat():event for event in full_events}
    for expected in fixture:
        event=by_ts[pd.Timestamp(expected["ts"]).isoformat()]
        assert int(event["cluster_id"])==expected["cluster_id"]
        assert event["cluster_types"]==tuple(expected["cluster_types"])
        for field in ("cluster_price","cluster_strength","cluster_age_minutes","approach_direction"):
            assert event[field]==expected[field]
        chunk_match=next(item for item in chunk_post if item["ts"]==event["ts"])
        assert chunk_match==event

    state_at_boundary={}
    for expected in fixture:
        key=str(expected["cluster_id"])
        state_at_boundary[key]={
            "full": {name:full_boundary.get(name,{}).get(key)
                     for name in ("touch_counts","armed","last_emit")},
            "chunked": {name:chunk_boundary.get(name,{}).get(key)
                        for name in ("touch_counts","armed","last_emit")},
        }
    print({"BTCUSDT 2022-01-01 checkpoint":state_at_boundary,
           "fixture_events":len(fixture),"full_events":len(full_events),
           "chunked_events":len(pre_events)+len(chunk_post)})


def test_returns_and_timeframes_do_not_mix_feed_regimes():
    from msd.processing.features import indicator_frame
    from msd.processing.timeframes import build_timeframe
    ts=pd.date_range("2024-01-01",periods=20,freq="min",tz="UTC")
    close=np.arange(100.,120.)
    bars=pd.DataFrame({"ts":ts,"bid_o":close,"bid_h":close+1,"bid_l":close-1,"bid_c":close,
                       "ask_o":close,"ask_h":close+1,"ask_l":close-1,"ask_c":close,"volume":1.,
                       "feed":["futures_cont"]*7+["cash_cfd"]*13})
    features=indicator_frame(bars)
    assert np.isnan(features.return_bars_1.iloc[7])
    assert np.isnan(features.return_bars_5.iloc[7])
    rollbars=bars.drop(columns="feed").copy();rollbars["roll"]=[False]*9+[True]+[False]*10
    roll_features=indicator_frame(rollbars)
    assert roll_features.return_bars_1.iloc[9:].isna().iloc[:1].all()
    assert roll_features.return_bars_5.iloc[9:15].isna().all()
    index_bars=bars.iloc[:10].copy()
    index_bars["feed"]=["futures_cont"]*7+["cash_cfd"]*3
    htf=build_timeframe(index_bars,"USATECHIDXUSD","5m")
    assert htf.feed.tolist()==["futures_cont"]


def test_index_cash_guard_rejects_pre_cash_bars_but_allows_cash():
    import pytest
    from msd.processing.pipeline import _assert_index_cash_only
    pre=pd.DataFrame({"ts":pd.to_datetime(["2018-12-16 22:59Z"]),"bid_c":[1.]})
    cash=pd.DataFrame({"ts":pd.to_datetime(["2018-12-16 23:00Z"]),"bid_c":[1.]})
    with pytest.raises(RuntimeError,match="pre-cash-era bars"):
        _assert_index_cash_only(pre,"USATECHIDXUSD")
    _assert_index_cash_only(cash,"USATECHIDXUSD")


def test_cash_era_filter_starts_at_histdata_switch():
    from msd.processing.pipeline import _cash_era_only
    frame=pd.DataFrame({"ts":pd.to_datetime(["2018-12-16 22:59Z","2018-12-16 23:00Z","2018-12-16 23:01Z"]),
                        "bid_c":[1.,2.,3.],"feed":["futures_cont","cash_cfd","cash_cfd"]})
    result=_cash_era_only(frame,"USATECHIDXUSD")
    assert result.ts.tolist()==frame.ts.iloc[1:].tolist()
    assert _cash_era_only(frame,"BTCUSDT").equals(frame)


def test_cash_cfd_keeps_dukas_bidask_when_adjusted_columns_are_nan():
    from msd.processing.pipeline import _adjusted_price_view
    row={"ts":pd.Timestamp("2019-01-01",tz="UTC"),"feed":"cash_cfd"}
    for field in "ohlc":
        row[f"bid_{field}"]=100.
        row[f"ask_{field}"]=100.5
        row[f"adj_bid_{field}"]=np.nan
    result=_adjusted_price_view(pd.DataFrame([row]))
    assert result.bid_o.iloc[0]==100. and result.ask_o.iloc[0]==100.5


def test_yearly_level_outputs_merge_without_losing_prior_years(tmp_path,monkeypatch):
    from msd.processing import pipeline
    monkeypatch.setattr(pipeline,"LEVEL_DIR",tmp_path)
    old=pd.DataFrame({"known_at":pd.to_datetime(["2018-05-01T00:00Z","2022-05-01T00:00Z"]),"price":[1.,3.]})
    old.to_parquet(tmp_path/"BTCUSDT.parquet",index=False)
    new=pd.DataFrame({"known_at":pd.to_datetime(["2019-05-01T00:00Z"]),"price":[2.]})
    incoming=tmp_path/"incoming.parquet";new.to_parquet(incoming,index=False)
    pipeline._merge_levels_year(incoming,"BTCUSDT",2019)
    saved=pd.read_parquet(tmp_path/"BTCUSDT.parquet")
    assert saved.price.tolist()==[1.,2.]


def test_feature_qa_appends_and_replaces_year_rows(tmp_path):
    from msd.processing.features import feature_qa
    first=pd.DataFrame({"ts":pd.to_datetime(["2020-01-01T00:00Z","2020-01-01T00:01Z"]),
                        "known_at":pd.to_datetime(["2020-01-01T00:01Z","2020-01-01T00:02Z"]),"x":[1.,2.]})
    second=pd.DataFrame({"ts":pd.to_datetime(["2021-01-01T00:00Z","2021-01-01T00:01Z"]),
                         "known_at":pd.to_datetime(["2021-01-01T00:01Z","2021-01-01T00:02Z"]),"x":[3.,4.]})
    path=feature_qa(first,"QA_TEST",path=tmp_path)
    feature_qa(second,"QA_TEST",path=tmp_path,append=True)
    first.x=[10.,20.]
    feature_qa(first,"QA_TEST",path=tmp_path,append=True)
    lines=path.read_text().splitlines()
    assert sum(line.startswith("| 2020 | x |") for line in lines)==1
    assert sum(line.startswith("| 2021 | x |") for line in lines)==1
    assert any(line.startswith("| 2020 | x |") and "10" in line for line in lines)


def test_feature_qa_files_matches_dataframe_stats_without_year_concat(tmp_path):
    from msd.processing.features import feature_qa,feature_qa_files
    frame=pd.DataFrame({"ts":pd.to_datetime(["2024-01-31T23:58Z","2024-01-31T23:59Z",
                                              "2024-02-01T00:00Z","2024-02-01T00:01Z"]),
                        "known_at":pd.to_datetime(["2024-01-31T23:59Z","2024-02-01T00:00Z",
                                                    "2024-02-01T00:01Z","2024-02-01T00:02Z"]),
                        "x":np.array([np.nan,1.,2.,3.],dtype=np.float32),"constant":np.ones(4,dtype=np.float32)})
    first=tmp_path/"2024-01.parquet";second=tmp_path/"2024-02.parquet"
    frame.iloc[:2].to_parquet(first);frame.iloc[2:].to_parquet(second)
    direct=feature_qa(frame,"DIRECT",tmp_path/"direct.md")
    streamed=feature_qa_files([first,second],"STREAM",tmp_path/"stream.md")
    direct_rows=[line.split(" | ",2)[-1] for line in direct.read_text().splitlines() if line.startswith("| 2024 |")]
    stream_rows=[line.split(" | ",2)[-1] for line in streamed.read_text().splitlines() if line.startswith("| 2024 |")]
    assert direct_rows==stream_rows


def test_external_dix_and_dvol_features_are_asof_and_truncation_safe():
    from msd.processing.features import build_features, external_feature_frame
    ts=pd.date_range("2024-01-02 14:00",periods=140,freq="min",tz="UTC")
    close=np.linspace(100.,101.,len(ts))
    bars=pd.DataFrame({"ts":ts,"bid_o":close,"bid_h":close+.1,"bid_l":close-.1,"bid_c":close,
                       "ask_o":close+.02,"ask_h":close+.12,"ask_l":close-.08,"ask_c":close+.02,"volume":1.})
    dix=pd.DataFrame({"known_at":pd.to_datetime(["2024-01-02T15:00Z","2024-01-02T16:00Z"]),
                      "dix":[.42,.99],"gex":[-1.2,8.0]})
    dvol=pd.DataFrame({"ts":pd.to_datetime(["2024-01-02T14:00Z","2024-01-02T15:00Z"]),
                       "known_at":pd.to_datetime(["2024-01-02T15:00Z","2024-01-02T16:00Z"]),
                       "resolution_seconds":[3600,3600],"close":[55.,99.]})
    full=build_features(bars,"BTCUSDT",auxiliary={"dix_gex":dix,"dvol_btc":dvol})
    extra=external_feature_frame(full.known_at,{"dix_gex":dix,"dvol_btc":dvol})
    for column in ("dix_level","gex_level","dvol_btc_level","dvol_btc_change"):
        np.testing.assert_allclose(full[column].to_numpy(float),extra[column].to_numpy(float),equal_nan=True)
    cutoff=pd.Timestamp("2024-01-02T15:30Z")
    perturbed_dvol=dvol.copy(); perturbed_dvol.loc[1,"close"]=999.
    truncated=build_features(bars[bars.ts<=cutoff].copy(),"BTCUSDT",
                              auxiliary={"dix_gex":dix[dix.known_at<=cutoff],"dvol_btc":perturbed_dvol})
    cols=["ts","dix_level","gex_level","dvol_btc_level"]
    expected=full.loc[full.ts<=cutoff,cols].reset_index(drop=True)
    actual=truncated[cols].reset_index(drop=True)
    pd.testing.assert_frame_equal(expected,actual,check_dtype=False)
    before=full.loc[full.ts==pd.Timestamp("2024-01-02T14:58Z"),"dix_level"].iloc[0]
    at=full.loc[full.ts==pd.Timestamp("2024-01-02T14:59Z"),"dix_level"].iloc[0]
    assert np.isnan(before) and at==.42
    assert full.loc[full.ts==pd.Timestamp("2024-01-02T15:10Z"),"dix_level"].iloc[0]==.42
    # The 15:00 candle's close is not available until 16:00.
    dvol_before=full.loc[full.ts==pd.Timestamp("2024-01-02T15:29Z"),"dvol_btc_level"].iloc[0]
    dvol_close=full.loc[full.ts==pd.Timestamp("2024-01-02T15:59Z"),"dvol_btc_level"].iloc[0]
    assert dvol_before==55. and dvol_close==99.


def test_edgar_acceptance_is_since_only_never_a_future_countdown():
    from msd.processing.features import build_features
    ts=pd.date_range("2024-01-02T10:00Z",periods=3,freq="min")
    bars=pd.DataFrame({"ts":ts,"bid_o":[100.]*3,"bid_h":[101.]*3,"bid_l":[99.]*3,"bid_c":[100.]*3,
                       "ask_o":[100.1]*3,"ask_h":[101.1]*3,"ask_l":[99.1]*3,"ask_c":[100.1]*3,"volume":[1.]*3})
    earnings=pd.DataFrame({"event":["earnings_aapl"],"datetime_utc":pd.to_datetime(["2024-01-02T10:03Z"])})
    features=build_features(bars,"BTCUSDT",auxiliary={"earnings":earnings})
    assert "minutes_to_earnings_aapl" not in features
    assert features.minutes_since_earnings_aapl.iloc[:2].isna().all()
    assert features.minutes_since_earnings_aapl.iloc[2]==0.


def test_macro_countdown_uses_only_prepublished_scheduled_events():
    from msd.processing.features import build_features
    ts=pd.date_range("2024-01-02T10:00Z",periods=3,freq="min")
    bars=pd.DataFrame({"ts":ts,"bid_o":[100.]*3,"bid_h":[101.]*3,"bid_l":[99.]*3,"bid_c":[100.]*3,
                       "ask_o":[100.1]*3,"ask_h":[101.1]*3,"ask_l":[99.1]*3,"ask_c":[100.1]*3,"volume":[1.]*3})
    events=pd.DataFrame({"event":["cpi","fomc_emergency"],"datetime_utc":pd.to_datetime(["2024-01-02T10:02Z","2024-01-02T10:02Z"]),
                         "scheduled":[True,False]})
    features=build_features(bars,"BTCUSDT",auxiliary={"macro_events":events})
    mixed=events.copy(); mixed["datetime_utc"]=mixed.datetime_utc.astype("datetime64[us, UTC]")
    features_mixed=build_features(bars,"BTCUSDT",auxiliary={"macro_events":mixed})
    pd.testing.assert_series_equal(features.minutes_to_cpi,features_mixed.minutes_to_cpi,check_dtype=False)
    pd.testing.assert_series_equal(features.minutes_since_fomc_emergency,
                                   features_mixed.minutes_since_fomc_emergency,check_dtype=False)
    assert features.minutes_to_cpi.iloc[0]==1.
    assert "minutes_to_fomc_emergency" not in features
    assert np.isnan(features.minutes_since_fomc_emergency.iloc[0])
    assert features.minutes_since_fomc_emergency.iloc[1]==0.


def _flat_filled(ts, keep):
    """Bars for every minute in ts; the omitted ones repeat the prior close (no ticks)."""
    full = _bars(ts)
    for column in ("bid_o", "bid_h", "bid_l", "bid_c", "ask_o", "ask_h", "ask_l", "ask_c"):
        side = "bid" if column.startswith("bid") else "ask"
        full.loc[~keep, column] = np.nan
        full[column] = full[column].fillna(full[f"{side}_c"].ffill()) if not column.endswith("_c") else full[column].ffill()
    for side in ("bid", "ask"):
        for field in "ohl":
            full.loc[~keep, f"{side}_{field}"] = full.loc[~keep, f"{side}_c"]
    return full


def test_htf_bar_ohlc_is_unchanged_by_no_tick_minute_omissions():
    from msd.processing.timeframes import build_timeframe
    ts = pd.date_range("2024-01-01", periods=24 * 60, freq="min", tz="UTC")
    keep = np.random.default_rng(7).random(len(ts)) > 0.10
    keep[-1] = True  # the input must reach the last bucket's end for it to close
    filled = _flat_filled(ts, keep)
    sparse = filled.loc[keep].reset_index(drop=True)
    for tf in ("15m", "1h", "4h"):
        a = build_timeframe(sparse, "BTCUSDT", tf).set_index("ts")
        b = build_timeframe(filled, "BTCUSDT", tf).set_index("ts")
        assert len(b) == 24 * 60 // {"15m": 15, "1h": 60, "4h": 240}[tf]
        assert a.index.isin(b.index).all() and len(a) >= 0.9 * len(b)  # random clusters can dip below 80%
        # A bucket whose first minute had no ticks opens at its first tick, not
        # at the carried prior close, so compare OHLC where the first minute traded.
        first_traded = a.index[a.index.isin(ts[keep])]
        assert len(first_traded) >= 0.8 * len(a)
        cols = ["bid_o", "bid_h", "bid_l", "bid_c", "ask_o", "ask_h", "ask_l", "ask_c", "known_at"]
        pd.testing.assert_frame_equal(a.loc[first_traded, cols], b.loc[first_traded, cols])
        pd.testing.assert_series_equal(a.bid_c, b.loc[a.index, "bid_c"])


def test_htf_bucket_below_coverage_is_absent_and_index_quote_gap_is_not_expected():
    from msd.processing.timeframes import build_timeframe
    ts = pd.date_range("2024-01-01", periods=120, freq="min", tz="UTC")
    sparse = ts[(ts.minute % 4 != 0) | (ts.hour == 1)]  # hour 0 keeps 75%, hour 1 keeps 100%
    frame = build_timeframe(_bars(sparse), "BTCUSDT", "1h")
    assert frame.ts.tolist() == [pd.Timestamp("2024-01-01 01:00", tz="UTC")]
    # NQ: the 16:00 ET bucket only has quotes until 16:14; 14:00 ET 4h bucket ends at 17:00.
    start = pd.Timestamp("2024-06-02 18:00", tz="America/New_York")
    ny = pd.date_range(start, pd.Timestamp("2024-06-03 20:00", tz="America/New_York"), freq="min")
    local = ny.tz_convert("America/New_York")
    minute = local.hour * 60 + local.minute
    ny = ny[(minute < 16 * 60 + 15) | (minute >= 18 * 60)]
    hours = build_timeframe(_bars(ny.tz_convert("UTC")), "USATECHIDXUSD", "1h")
    four = build_timeframe(_bars(ny.tz_convert("UTC")), "USATECHIDXUSD", "4h")
    sixteen = pd.Timestamp("2024-06-03 16:00", tz="America/New_York")
    fourteen = pd.Timestamp("2024-06-03 14:00", tz="America/New_York")
    assert sixteen in set(hours.ts.dt.tz_convert("America/New_York"))
    row = four[four.ts.dt.tz_convert("America/New_York") == fourteen]
    assert len(row) == 1 and row.known_at.iloc[0] == pd.Timestamp("2024-06-03 17:00", tz="America/New_York")


def test_htf_partial_bucket_is_not_emitted_before_input_passes_its_end():
    from msd.processing.timeframes import build_timeframe
    ts = pd.date_range("2024-01-01", periods=600, freq="min", tz="UTC")
    full = build_timeframe(_bars(ts), "BTCUSDT", "1h")
    for cut_minute in (595, 590, 550, 549):  # 59/60, 50/60, 10/60 and 9/60 of the last bucket
        cut = ts[0] + pd.Timedelta(minutes=cut_minute)
        truncated = build_timeframe(_bars(ts[ts < cut]), "BTCUSDT", "1h")
        assert truncated.known_at.max() <= cut
        pd.testing.assert_frame_equal(truncated, full[full.known_at <= cut].reset_index(drop=True))


def test_metal_daily_rollover_break_is_not_expected_in_utc_buckets():
    from msd.processing.timeframes import build_timeframe
    for day in ("2024-01-10", "2024-07-10"):  # 22:00 UTC in winter, 21:00 UTC in summer
        ts = pd.date_range(f"{day} 00:00", periods=26 * 60, freq="min", tz="UTC")
        local = ts.tz_convert("America/New_York")
        ts = ts[local.hour != 17]
        four = build_timeframe(_bars(ts), "XAUUSD", "4h")
        assert pd.Timestamp(f"{day} 20:00", tz="UTC") in set(four.ts)
        hours = build_timeframe(_bars(ts), "XAUUSD", "1h")
        assert not hours.ts.dt.tz_convert("America/New_York").dt.hour.eq(17).any()
