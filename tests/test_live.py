from datetime import datetime, timedelta, timezone
import sys, types
import numpy as np
import pandas as pd
from msd.live.engine import (OutageAlerts, SignalEngine, StaleDataAlarm, create_engine, market_open,
                             process_poll_cycle, verify_bars)
from msd.live.store import SignalStore
from msd.live.capital import parse_prices

SYMBOL="TEST"


def _strategy_module(name="test_breakout"):
    module=types.ModuleType(name)
    module.NAME="test_breakout"
    module.SYMBOLS=(SYMBOL,)
    module.RESOLUTION="MINUTE"
    def orders(bars):
        result=[]
        if len(bars)<61: return result
        high=bars.bid_h.to_numpy(float); low=bars.bid_l.to_numpy(float); close=bars.bid_c.to_numpy(float)
        for i in range(60,len(bars)):
            if close[i] > np.max(high[i-60:i]) and close[i-1] <= np.max(high[i-60:i-1]):
                risk=close[i]-np.min(low[i-60:i])
                if risk>0:
                    result.append({"decision_ts":bars.ts.iloc[i],"side":1,"stop":float(np.min(low[i-60:i])),"tp":float(close[i]+2*risk),"exit_ts":None})
        return result
    module.orders=orders
    sys.modules[name]=module
    return module


def _bars():
    # Sunday reopen after the US spring DST transition; includes a weekend gap.
    local1=pd.date_range("2025-03-07 16:00",periods=60,freq="min",tz="America/New_York")
    local2=pd.date_range("2025-03-09 18:00",periods=120,freq="min",tz="America/New_York")
    ts=local1.append(local2).tz_convert("UTC")
    n=len(ts); px=np.full(n,100.)
    px[65:]=103.
    frame=pd.DataFrame({"ts":ts,"volume":np.ones(n)})
    for side,offset in (("bid",0.),("ask",.1)):
        for f,delta in (("o",0.),("h",.2),("l",-.2),("c",0.)):
            frame[f"{side}_{f}"]=px+offset+delta
    return frame


def test_capital_price_parser():
    payload={"prices":[{"snapshotTimeUTC":"2025-01-02T03:04:00","openPrice":{"bid":10,"ask":11},"highPrice":{"bid":12,"ask":13},"lowPrice":{"bid":9,"ask":10},"closePrice":{"bid":11,"ask":12},"lastTradedVolume":4}]}
    parsed=parse_prices(payload)
    assert parsed.iloc[0].bid_o==10 and parsed.iloc[0].volume==4


def test_market_hours_dst_weekend_daily_break_and_friday_close():
    assert market_open(datetime(2025,3,9,22,30,tzinfo=timezone.utc),"cme_equity")
    assert not market_open(datetime(2025,3,10,21,30,tzinfo=timezone.utc),"cme_equity") # 17:30 EDT
    assert market_open(datetime(2025,3,10,22,30,tzinfo=timezone.utc),"cme_equity")
    assert not market_open(datetime(2025,3,8,17,0,tzinfo=timezone.utc),"cme_equity")
    assert market_open(datetime.now(timezone.utc),"24x7")


def test_stale_alarm_only_warns_active_and_recovers():
    alarm=StaleDataAlarm(); now=datetime(2025,1,1,tzinfo=timezone.utc)
    assert alarm.update(now,None,False) is None
    assert alarm.update(now,None,True)=="stale"
    assert alarm.update(now+timedelta(minutes=1),now,True)=="recovered"
    assert alarm.update(now+timedelta(minutes=2),now,False) is None


def test_outage_alert_rate_limit():
    sent=[]; alert=OutageAlerts(sent.append)
    t=datetime(2025,1,1,tzinfo=timezone.utc)
    alert.failure(RuntimeError("offline"),t); alert.failure(RuntimeError("offline"),t+timedelta(minutes=2))
    alert.failure(RuntimeError("offline"),t+timedelta(hours=1)); alert.recovered()
    assert sent==["Feed outage; reconnecting","Feed outage; reconnecting","Feed recovered"]


def test_forming_entry_timing_preentry_exits_reminder_stop_update_flip_and_dedupe():
    module=_strategy_module("test_engine_strategy")
    store=SignalStore(":memory:"); messages=[]
    entry={"module":module.__name__,"enabled":True}
    engine=SignalEngine(store,messages.append,instruments=[{"symbol":SYMBOL}],strategies=[entry])
    frame=_bars().iloc[:70]
    for row in frame.iloc[:66].to_dict("records"): engine.process_completed(SYMBOL,"MINUTE",row)
    decision=frame.ts.iloc[65]
    forming=frame.iloc[66].to_dict()
    engine.process_forming(SYMBOL,"MINUTE",forming)
    key=f"{SYMBOL}:{module.NAME}:{decision.isoformat()}"
    saved=store.get(key)
    assert saved and pd.Timestamp(saved["entry_ts"])==forming["ts"]
    sent_count=len(messages)
    engine.process_forming(SYMBOL,"MINUTE",forming)
    assert len(messages)==sent_count
    # Bars before entry cannot touch the stop.
    old=frame.iloc[0].to_dict(); old.update(bid_l=0.,ask_h=1000.)
    engine._check_exits(SYMBOL,"MINUTE",old)
    assert store.get(key)["status"]=="open"
    # Reminder is idempotent.
    deadline=pd.Timestamp("2025-03-10 12:00",tz="UTC")
    store.update(key,planned_exit_ts=deadline.isoformat())
    n=len(messages); engine.reminder((deadline-pd.Timedelta(minutes=4)).to_pydatetime()); engine.reminder((deadline-pd.Timedelta(minutes=3)).to_pydatetime())
    assert len(messages)==n+1
    # Stop update on a timestamp is announced once and stored.
    engine._apply_updates(entry,module,frame,decision,SYMBOL)
    store.close()


def test_zero_strategy_engine_and_invalid_order_rejection():
    store=SignalStore(":memory:"); msgs=[]
    engine=create_engine({"mode":"paper","instruments":[],"strategies":[]},store,msgs.append)
    assert engine.strategies==[] and "no strategies enabled" in msgs[0]
    module=_strategy_module("test_invalid_strategy")
    class Invalid:
        pass
    entry={"module":module.__name__}
    bad={"decision_ts":pd.Timestamp("2025-01-01",tz="UTC"),"side":1,"stop":101.,"tp":99.}
    assert not engine._validate(entry,module,bad,100.)
    assert any("Invalid order" in msg for msg in msgs)
    store.close()


def test_assert_causal_rejects_future_dependent_strategy():
    from msd.strategy_check import assert_causal
    module=types.ModuleType("leaky")
    module.orders=lambda bars:[{"decision_ts":bars.ts.iloc[0],"side":1,"stop":float(bars.volume.max()),"tp":None}]
    frame=_bars().iloc[:80].copy(); frame["volume"]=np.arange(len(frame),dtype=float)
    try:
        assert_causal(module,frame,n=10,seed=3)
    except AssertionError: pass
    else: raise AssertionError("look-ahead was not detected")


def test_verify_live_equivalence_full_day_synthetic_dst_weekend():
    module=_strategy_module("test_verify_strategy")
    frame=_bars()
    result=verify_bars(module,SYMBOL,frame)
    assert result["orders"]>=1 and result["mismatches"]==0, result


def _short_module(name="test_short_breakout"):
    module=types.ModuleType(name); module.NAME=name; module.SYMBOLS=(SYMBOL,); module.RESOLUTION="MINUTE"
    def orders(bars):
        result=[]
        if len(bars)<61:return result
        high=bars.ask_h.to_numpy(float); low=bars.ask_l.to_numpy(float); close=bars.ask_c.to_numpy(float)
        for i in range(60,len(bars)):
            level=np.min(low[i-60:i])
            if close[i]<level and close[i-1]>=level:
                stop=float(np.max(high[i-60:i])); risk=stop-close[i]
                if risk>0: result.append({"decision_ts":bars.ts.iloc[i],"side":-1,"stop":stop,"tp":float(close[i]-2*risk)})
        return result
    module.orders=orders; sys.modules[name]=module; return module


def test_two_test_only_strategy_modules_share_contract():
    long=_strategy_module("test_long_breakout")
    short=_short_module()
    store=SignalStore(":memory:")
    engine=SignalEngine(store,lambda _m:None,instruments=[{"symbol":SYMBOL}],strategies=[
        {"module":long.__name__,"enabled":True},{"module":short.__name__,"enabled":True}])
    assert len(engine.strategies)==2
    assert all(m.SYMBOLS==(SYMBOL,) and m.RESOLUTION=="MINUTE" and callable(m.orders) for _,m in engine.strategies)
    store.close()


def test_stop_path_update_is_persisted_and_announced():
    module=_strategy_module("test_path_strategy"); module.NAME="path_strategy"
    decision=pd.Timestamp("2025-03-09 22:05",tz="UTC")
    module.orders=lambda _bars:[{"decision_ts":decision,"side":1,"stop":99.,"tp":105.,"stop_path":{decision:100.}}]
    store=SignalStore(":memory:"); messages=[]
    engine=SignalEngine(store,messages.append,instruments=[{"symbol":SYMBOL,"hours":"cme_equity"}],strategies=[{"module":module.__name__,"enabled":True}])
    key=f"{SYMBOL}:path_strategy:{decision.isoformat()}"
    store.insert({"signal_key":key,"symbol":SYMBOL,"setup":"path_strategy","side":1,"decision_ts":decision.isoformat(),"entry_ts":(decision+pd.Timedelta(minutes=1)).isoformat(),"entry_price":101.,"initial_stop":99.,"stop":99.,"take_profit":105.,"planned_risk":2.,"status":"open","created_at":"test"})
    engine._apply_updates({"module":module.__name__},module,pd.DataFrame(),decision,SYMBOL)
    assert store.get(key)["stop"]==100.
    assert any("Move SL" in message for message in messages)
    store.close()


def test_flip_exits_old_signal_and_restart_dedupe(tmp_path):
    module=_strategy_module("test_flip_strategy"); module.NAME="flip_strategy"
    store=SignalStore(":memory:"); messages=[]
    engine=SignalEngine(store,messages.append,instruments=[{"symbol":SYMBOL,"hours":"cme_equity"}],strategies=[{"module":module.__name__,"enabled":True}])
    decision=pd.Timestamp("2025-03-09 22:05",tz="UTC")
    old_key=f"{SYMBOL}:flip_strategy:old"
    old={"signal_key":old_key,"symbol":SYMBOL,"setup":"flip_strategy","side":1,"decision_ts":(decision-pd.Timedelta(minutes=2)).isoformat(),"entry_ts":(decision-pd.Timedelta(minutes=1)).isoformat(),"entry_price":101.,"initial_stop":99.,"stop":99.,"take_profit":105.,"planned_risk":2.,"status":"open","created_at":"test"}
    assert store.insert(old)
    forming={"ts":decision+pd.Timedelta(minutes=1),"bid_o":100.,"ask_o":100.1}
    order={"decision_ts":decision,"side":-1,"stop":102.,"tp":97.}
    engine._create_signal({"module":module.__name__},module,order,forming,SYMBOL)
    assert store.get(old_key)["status"]=="flip"
    assert any("EXIT now" in message for message in messages)
    store.close()
    path=tmp_path/"state.db"
    first=SignalStore(path)
    assert first.insert({**old,"signal_key":"dedupe","created_at":"first"})
    first.close()
    reopened=SignalStore(path)
    assert not reopened.insert({**old,"signal_key":"dedupe","created_at":"restart"})
    reopened.close()


def test_long_and_short_breakout_dummy_candidates():
    long=_strategy_module("test_long_shape")
    short=_short_module("test_short_shape")
    frame=_bars().copy()
    for column in ("bid_o","bid_h","bid_l","bid_c","ask_o","ask_h","ask_l","ask_c"):
        frame.loc[120:,column]-=8.
    longs=long.orders(frame)
    shorts=short.orders(frame)
    assert longs and longs[0]["side"]==1
    assert shorts and shorts[0]["side"]==-1
    assert shorts[0]["stop"]>float(frame.loc[shorts[0]["decision_ts"]==frame.ts,"ask_c"].iloc[0])


def test_exit_deadline_closes_at_open_of_first_bar_at_or_after_exit_ts():
    store=SignalStore(":memory:"); messages=[]
    engine=SignalEngine(store,messages.append,instruments=[],strategies=[])
    entry=pd.Timestamp("2025-03-09 22:00",tz="UTC"); deadline=entry+pd.Timedelta(minutes=2)
    key="TEST:timer:"+entry.isoformat()
    store.insert({"signal_key":key,"symbol":"TEST","setup":"timer","side":1,"decision_ts":entry.isoformat(),"entry_ts":entry.isoformat(),"entry_price":101.,"initial_stop":99.,"stop":99.,"planned_risk":2.,"planned_exit_ts":deadline.isoformat(),"status":"open","created_at":"test"})
    bar={"ts":deadline,"bid_o":103.,"bid_h":110.,"bid_l":90.,"bid_c":102.,"ask_o":103.1,"ask_h":110.1,"ask_l":90.1,"ask_c":102.1}
    engine._check_exits("TEST","MINUTE",bar)
    live=store.get(key)
    assert live["status"]=="time" and live["exit_price"]==103.
    from msd.backtest import simulate
    times=pd.date_range(entry,periods=3,freq="min")
    market=pd.DataFrame({"ts":times,"volume":1.})
    for prefix,offset in (("bid",0.),("ask",.1)):
        market[f"{prefix}_o"]=[100.+offset,101.+offset,103.+offset]
        market[f"{prefix}_h"]=[100.5+offset,102.+offset,110.+offset]
        market[f"{prefix}_l"]=[99.5+offset,101.+offset,90.+offset]
        market[f"{prefix}_c"]=[100.+offset,102.+offset,102.+offset]
    expected=simulate(market,[{"decision_ts":entry,"side":1,"stop":98.,"tp":102.5,"exit_ts":deadline}]).iloc[0]
    assert expected.exit_reason=="time" and expected.exit_ts==pd.Timestamp(live["exit_ts"]) and expected.exit_price==live["exit_price"]==103.
    store.close()


def test_time_exit_gap_uses_first_later_bar_open_and_ignores_its_range():
    from msd.backtest import simulate
    ts=pd.to_datetime(["2024-06-03 20:13Z","2024-06-03 20:14Z","2024-06-03 22:07Z"])
    frame=pd.DataFrame({"ts":ts,"volume":1.})
    values={"bid_o":[100.,100.,100.5],"bid_h":[101.,101.,104.],"bid_l":[99.5,99.5,98.],"bid_c":[100.,100.,102.],
            "ask_o":[100.1,100.1,100.6],"ask_h":[101.1,101.1,104.1],"ask_l":[99.6,99.6,98.1],"ask_c":[100.1,100.1,102.1]}
    for key,value in values.items():frame[key]=value
    deadline=pd.Timestamp("2024-06-03 21:28",tz="UTC")
    order={"decision_ts":ts[0],"side":1,"stop":99.,"tp":102.,"exit_ts":deadline}
    simulated=simulate(frame,[order]).iloc[0]
    assert simulated.exit_reason=="time" and simulated.exit_ts==ts[2] and simulated.exit_price==100.5
    store=SignalStore(":memory:"); engine=SignalEngine(store,lambda _m:None,instruments=[],strategies=[])
    key=f"TEST:gap:{pd.Timestamp(ts[0]).isoformat()}"
    store.insert({"signal_key":key,"symbol":"TEST","setup":"gap","side":1,"decision_ts":pd.Timestamp(ts[0]).isoformat(),"entry_ts":pd.Timestamp(ts[1]).isoformat(),"entry_price":100.1,"initial_stop":99.,"stop":99.,"take_profit":102.,"planned_risk":1.1,"planned_exit_ts":deadline.isoformat(),"status":"open","created_at":"test"})
    engine._check_exits("TEST","MINUTE",frame.iloc[2].to_dict())
    live=store.get(key)
    assert live["status"]==simulated.exit_reason and live["exit_price"]==simulated.exit_price
    store.close()


def test_live_stop_update_and_backtest_exit_share_next_bar_rule():
    from msd.backtest import simulate
    module=_strategy_module("test_shared_stop_strategy"); module.NAME="shared_stop"
    t=pd.date_range("2025-03-09 22:00",periods=4,freq="min",tz="UTC")
    frame=pd.DataFrame({"ts":t,"volume":1.})
    prices=[100.,100.,100.,100.]
    for prefix,offset in (("bid",0.),("ask",.1)):
        for fld,delta in (("o",0.),("h",1.),("l",-1.),("c",0.)):
            frame[f"{prefix}_{fld}"]=np.asarray(prices)+offset+delta
    frame.loc[2,"bid_l"]=99.5
    order={"decision_ts":t[0],"side":1,"stop":95.,"stop_path":{t[1]:100.},"exit_ts":t[3]}
    module.orders=lambda _bars:[order]
    store=SignalStore(":memory:"); messages=[]
    entry={"module":module.__name__,"enabled":True}
    engine=SignalEngine(store,messages.append,instruments=[{"symbol":SYMBOL,"hours":"cme_equity"}],strategies=[entry])
    engine.process_completed(SYMBOL,"MINUTE",frame.iloc[0].to_dict())
    engine.process_forming(SYMBOL,"MINUTE",frame.iloc[1].to_dict())
    key=f"{SYMBOL}:shared_stop:{t[0].isoformat()}"
    engine.process_completed(SYMBOL,"MINUTE",frame.iloc[1].to_dict())
    assert store.get(key)["stop"]==100.
    engine.process_completed(SYMBOL,"MINUTE",frame.iloc[2].to_dict())
    expected=simulate(frame,[order]).iloc[0]
    actual=store.get(key)
    assert actual["status"]==expected.exit_reason=="stop"
    assert pd.Timestamp(actual["exit_ts"])==expected.exit_ts and actual["exit_price"]==expected.exit_price==100.
    store.close()


def test_startup_rejects_strategy_symbol_missing_instruments():
    module=_strategy_module("test_missing_instrument")
    try:
        SignalEngine(SignalStore(":memory:"),lambda _m:None,instruments=[],strategies=[{"module":module.__name__,"enabled":True}])
    except ValueError as exc:
        assert "requires unconfigured instrument" in str(exc) and SYMBOL in str(exc)
    else: raise AssertionError("missing strategy instrument was not rejected")


def test_verify_bars_limits_multi_symbol_module_to_requested_symbol():
    module=_strategy_module("test_verify_multi_symbol")
    module.SYMBOLS=(SYMBOL,"OTHER")
    result=verify_bars(module,SYMBOL,_bars())
    assert result["mismatches"]==0 and result["signals"]==1


def test_short_signal_uses_red_icon():
    from msd.live.engine import format_signal
    module=_short_module("test_short_message")
    text=format_signal(SYMBOL,module,{"side":-1,"stop":102.,"tp":97.,"confidence":None,"size":None},100.)
    assert text.startswith("🔴 SHORT TEST")
