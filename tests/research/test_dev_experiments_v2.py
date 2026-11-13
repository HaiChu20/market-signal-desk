from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from msd.research import dev_experiments_v2 as exp


def test_dev_guard_rejects_test_or_final_rows():
    exp._assert_dev(pd.DataFrame({"ts":[pd.Timestamp("2022-12-31 23:59",tz="UTC")]}),"ts")
    with pytest.raises(AssertionError,match="non-DEV"):
        exp._assert_dev(pd.DataFrame({"ts":[pd.Timestamp("2023-01-01",tz="UTC")]}),"ts")


def _rule_frame(train_cell_one: bool, test_cell_two: bool) -> pd.DataFrame:
    rows=[]
    for event in range(4):
        ts=pd.Timestamp("2021-01-01",tz="UTC")+pd.Timedelta(days=event*3)
        for sl in (1.,2.):
            if event<2:score=(1. if sl==1 else -1.) if train_cell_one else -1.
            else:score=10. if sl==2 and test_cell_two else -2.
            rows.append({"event_key":f"e{event}","sym":"BTCUSDT","known_at":ts,
                "label_end_ts":ts+pd.Timedelta(hours=1),"entry_ts":ts,"sl_atr":sl,"tp_r":1.,
                "net_R":score,"outcome":"tp" if score>0 else "sl"})
    return pd.DataFrame(rows)


def test_nested_selection_never_uses_test_fold_rows(monkeypatch):
    monkeypatch.setattr(exp,"cpcv_folds",lambda rep,*args:[SimpleNamespace(train=np.array([0,1]),test=np.array([2,3]))])
    hold1=_rule_frame(True,True);hold3=_rule_frame(False,True)
    selected=exp._nested_rule(hold1,hold3,"rule",{})
    assert len(selected)==2
    assert selected.selected_horizon.eq("hold1").all()
    assert selected.sl_atr.eq(1.).all()  # test rows strongly favor SL2, but train rows choose SL1


def _bar(ts,mid):
    return {"ts":ts,"bid_o":mid-1,"ask_o":mid+1,"bid_c":mid-1,"ask_c":mid+1}


def test_intraday_et_times_and_dst_transition(tmp_path):
    symbol="USATECHIDXUSD";rows=[]
    schedule={
        "2019-03-07":{"15:59":100.},
        "2019-03-08":{"09:59":101.,"15:30":102.,"15:59":104.},
        "2019-03-11":{"09:59":103.,"15:30":102.,"15:59":100.},
    }
    for date,clocks in schedule.items():
        for clock,mid in clocks.items():
            local=pd.Timestamp(f"{date} {clock}",tz="America/New_York")
            rows.append(_bar(local.tz_convert("UTC"),mid))
    bar_path=tmp_path/"bars"/"dukascopy"/symbol/"2019-03.parquet";bar_path.parent.mkdir(parents=True)
    pd.DataFrame(rows).to_parquet(bar_path,index=False)
    features=[]
    for date in ("2019-03-08","2019-03-11"):
        entry=pd.Timestamp(f"{date} 15:30",tz="America/New_York").tz_convert("UTC")
        features.append({"ts":entry-pd.Timedelta(minutes=1),"known_at":entry,"1h_atr14":10.})
    feature_path=tmp_path/"features"/symbol/"2019-03.parquet";feature_path.parent.mkdir(parents=True)
    pd.DataFrame(features).to_parquet(feature_path,index=False)
    out=exp._intraday_rows(tmp_path,symbol)
    assert out.date.tolist()==["2019-03-08","2019-03-11"]
    assert pd.Timestamp(out.entry_ts.iloc[0]).hour==20  # EST
    assert pd.Timestamp(out.entry_ts.iloc[1]).hour==19  # EDT after spring transition
    assert out.side.tolist()==[1,-1]
    assert out.gross_R.tolist()==pytest.approx([.2,.2])
    assert out.net_R.tolist()==pytest.approx([0.,0.])  # one spread paid at entry and exit


def test_ledger_preflight_is_read_only(tmp_path):
    from msd.research.ledger import FIELDS,append_trial
    path=tmp_path/"trials.csv"
    base=dict(zip(FIELDS,["base","2026-01-01","a","rule","{}","dev","dev","{}","base"]))
    append_trial(path,base);before=path.read_bytes()
    fresh={**base,"run_id":"fresh","config_hash":"b"}
    exp._preflight(path,[fresh]);assert path.read_bytes()==before
    with pytest.raises(ValueError,match="duplicate"):
        exp._preflight(path,[base])
    assert path.read_bytes()==before


def test_wide_event_deadline_uses_epoch_seconds():
    from msd.processing.wide_v1 import _event_jobs
    times=pd.DatetimeIndex([pd.Timestamp("2021-01-04 00:00",tz="UTC")+pd.Timedelta(minutes=i) for i in range(3)]+[
        pd.Timestamp("2021-01-05 00:02",tz="UTC"),pd.Timestamp("2021-01-06 00:02",tz="UTC")])
    bars=pd.DataFrame({"ts":pd.Series(times).astype("datetime64[us, UTC]")})
    for side in ("bid","ask"):
        for field in "ohlc":bars[f"{side}_{field}"]=100.
    event=pd.DataFrame([{"ts":times[0],"known_at":times[0]+pd.Timedelta(minutes=1),"sym":"BTCUSDT",
        "method":"x","side":1,"entry_type":"market","event_key":"e"}])
    result=_event_jobs(event,bars,pd.Series({times[0]:1.}),
                       {"sl_atr":[100.],"tp_r":[100.],"max_hold_trading_days":1},"BTCUSDT")
    assert result.outcome.tolist()==["time"]
    assert pd.Timestamp(result.exit_ts.iloc[0])==times[3]


def test_epoch_seconds_matches_for_microsecond_and_nanosecond_inputs():
    from msd.processing.timeutil import epoch_ns,epoch_seconds
    values=["2021-01-01T00:00:00.123456Z","2021-01-01T00:00:01.654321Z"]
    us=pd.Series(pd.to_datetime(values,utc=True)).astype("datetime64[us, UTC]")
    ns=pd.Series(pd.to_datetime(values,utc=True)).astype("datetime64[ns, UTC]")
    np.testing.assert_array_equal(np.asarray(epoch_seconds(us)),np.asarray(epoch_seconds(ns)))
    np.testing.assert_array_equal(np.asarray(epoch_ns(us)),np.asarray(epoch_ns(ns)))
    assert np.asarray(epoch_ns(us))[1]-np.asarray(epoch_ns(us))[0]==1_530_865_000
