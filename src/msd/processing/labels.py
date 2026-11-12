"""Python contract and Rust acceleration for causal first-hit labels."""
from __future__ import annotations

import logging
import os
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from msd.backtest import AMBIGUITY_KEYS, evaluate_bar, timestamp_ints

_RUST_FALLBACK_WARNED = False


def rust_fallback(error: ImportError) -> None:
    """Make a missing kernel visible, or fatal when production requires Rust."""
    global _RUST_FALLBACK_WARNED
    if os.getenv("MSD_REQUIRE_RUST") == "1":
        raise RuntimeError("MSD_REQUIRE_RUST=1 but msd._msd_kernels is unavailable") from error
    if not _RUST_FALLBACK_WARNED:
        logging.getLogger(__name__).warning("Rust kernels unavailable; using slow Python reference: %s", error)
        _RUST_FALLBACK_WARNED = True

NY=ZoneInfo("America/New_York")


def deadline_after_trading_days(entry_ts, days: int=5, instrument_class: str="index") -> pd.Timestamp:
    """Return entry time plus N weekdays; crypto holds use straight 24h days."""
    deadline=pd.Timestamp(entry_ts)
    deadline=deadline.tz_localize("UTC") if deadline.tzinfo is None else deadline.tz_convert("UTC")
    if instrument_class.lower() in {"crypto","24x7"}:
        return deadline+pd.Timedelta(days=days)
    count=0
    while count<days:
        deadline+=pd.Timedelta(days=1)
        if deadline.weekday()<5:
            count+=1
    return deadline


def _night_count(start, end, instrument_class: str="index") -> int:
    """Count crossed broker rollovers: 17:00 New York; crypto uses UTC midnight."""
    a=pd.Timestamp(start);b=pd.Timestamp(end)
    a=a.tz_localize("UTC") if a.tzinfo is None else a.tz_convert("UTC")
    b=b.tz_localize("UTC") if b.tzinfo is None else b.tz_convert("UTC")
    if b<=a:return 0
    if instrument_class.lower() in {"crypto","24x7"}:
        first=a.floor("D")+pd.Timedelta(days=1)
        return max(0,int((b.floor("D")-first)//pd.Timedelta(days=1))+1) if first<=b else 0
    start_day=a.tz_convert(NY).date();end_day=b.tz_convert(NY).date()
    day=pd.Timestamp(start_day)
    total=0
    while day.date()<=end_day:
        if day.weekday()<5:
            local=pd.Timestamp(day.date()).tz_localize(NY)+pd.Timedelta(hours=17)
            boundary=local.tz_convert("UTC")
            if a<boundary<=b:
                total+=3 if day.weekday()==4 else 1
        day+=pd.Timedelta(days=1)
    return total


def _row_bar(bars: pd.DataFrame, index: int) -> dict[str,float]:
    row=bars.iloc[index]
    return {f"{side}_{field}":float(row[f"{side}_{field}"])
            for side in ("bid","ask") for field in "ohlc"}


def first_hit_reference(bars: pd.DataFrame, entry_index: int, side: int, entry_price: float,
                        sl: float, tp: float|None, max_bars: int|None=None, delay_bars: int=2,
                        financing_per_night: float=0.0, limit_price: float|None=None,
                        expiry_index: int|None=None, *, deadline_ts=None, expiry_ts=None,
                        instrument_class: str="index", detailed: bool=False,
                        seconds: pd.DataFrame | None=None, return_stats: bool=False):
    """Reference label; market entry is at signal index + delay bars.

    New callers pass deadline_ts/expiry_ts. max_bars and expiry_index remain
    for backward compatibility with earlier stage fixtures.
    """
    n=len(bars);signal_i=int(entry_index);entry_i=signal_i+int(delay_bars)
    no_fill=("no_fill",-1,float("nan"),float("nan"),float("nan"),float("nan"),0,-1,float("nan"))
    empty = no_fill if detailed else no_fill[:5]
    if return_stats: empty = (*empty, dict.fromkeys(AMBIGUITY_KEYS, 0))
    if entry_i>=n or (max_bars is not None and max_bars<1):
        return empty
    side=1 if side>0 else -1
    timestamps=pd.to_datetime(bars.ts,utc=True).astype("datetime64[ns, UTC]")
    if deadline_ts is None and max_bars is not None:
        # Legacy convention is retained only for legacy callers.
        legacy_exit_i=min(entry_i+int(max_bars),n-1)
        deadline=timestamps.iloc[legacy_exit_i] if legacy_exit_i>entry_i else timestamps.iloc[entry_i]
        use_legacy_index=True
    else:
        deadline=pd.Timestamp(deadline_ts) if deadline_ts is not None else None
        if deadline is not None:
            deadline=deadline.tz_localize("UTC") if deadline.tzinfo is None else deadline.tz_convert("UTC")
        legacy_exit_i=-1;use_legacy_index=False
    side_close="bid" if side>0 else "ask"
    fill_i=entry_i
    if limit_price is None:
        fill=float(bars[f"ask_o" if side>0 else "bid_o"].iloc[fill_i])
        mid=(float(bars.bid_o.iloc[fill_i])+float(bars.ask_o.iloc[fill_i]))/2
        risk=abs(mid-float(sl))
        if side*(entry_price-float(sl))<=0:
            return empty
    else:
        limit=float(limit_price)
        if side*(limit-float(sl))<=0:
            return empty
        if expiry_ts is None and expiry_index is not None:
            limit_end=min(int(expiry_index),n)
        else:
            expiry=pd.Timestamp(expiry_ts) if expiry_ts is not None else None
            if expiry is not None: expiry=expiry.tz_localize("UTC") if expiry.tzinfo is None else expiry.tz_convert("UTC")
            limit_end=n
        fill_i=-1
        for i in range(entry_i,limit_end):
            if expiry_ts is not None and timestamps.iloc[i]>=expiry: break
            bar=_row_bar(bars,i)
            touched=(bar["ask_l"]<=limit) if side>0 else (bar["bid_h"]>=limit)
            if touched:
                fill_i=i
                if side>0:
                    fill=min(bar["ask_o"],limit)
                else:
                    fill=max(bar["bid_o"],limit)
                break
        if fill_i<0:
            return empty
        risk=abs(limit-float(sl))
    if not np.isfinite(risk) or risk<=0:
        return empty
    if use_legacy_index:
        end_i=min(n,legacy_exit_i+1)
    else:
        end_i=n
    reason=None;exit_i=-1;exit_price=float("nan")
    stats = dict.fromkeys(AMBIGUITY_KEYS, 0)
    second_groups = ({stamp: frame for stamp,frame in seconds.groupby(
        pd.to_datetime(seconds.ts,utc=True).astype("datetime64[ns, UTC]").dt.floor("min"))}
                     if seconds is not None and not seconds.empty else {})
    for i in range(fill_i,end_i):
        bar=_row_bar(bars,i)
        bar["ts"] = timestamps.iloc[i]
        at_deadline=(i==legacy_exit_i) if use_legacy_index else (deadline is not None and timestamps.iloc[i]>=deadline)
        # A time deadline exits at the first eligible bar's open, before touch checks.
        if at_deadline:
            _,reason,exit_price=evaluate_bar(side,sl,tp,bar,time_exit=True,time_at_open=True,stop_active=False)
            exit_i=i;break
        if limit_price is not None and i==fill_i:
            _,reason,exit_price=evaluate_bar(side,sl,None,bar)
        else:
            _,reason,exit_price=evaluate_bar(side,sl,tp,bar,
                                             seconds=second_groups.get(timestamps.iloc[i]),
                                             ambiguity_stats=stats if return_stats else None)
        if reason:
            exit_i=i;break
    if reason is None:
        exit_i=n-1
        exit_price=float(bars[f"{side_close}_c"].iloc[exit_i])
        reason="time"
    exit_ts=timestamps.iloc[exit_i]
    entry_ts=timestamps.iloc[fill_i]
    nights=_night_count(entry_ts,exit_ts,instrument_class)
    gross=float(side*(exit_price-fill)/risk)
    net=float(gross-float(financing_per_night)*nights*fill/risk)
    result=(reason,exit_i,float(exit_price),net,gross,float(fill),int(nights),int(fill_i),float(risk))
    selected = result if detailed else result[:5]
    return (*selected, stats) if return_stats else selected


def first_hit(bars: pd.DataFrame, entry_index: int, side: int, entry_price: float,
              sl: float, tp: float|None, max_bars: int|None=None, delay_bars: int=2,
              financing_per_night: float=0.0, limit_price: float|None=None,
              expiry_index: int|None=None, *, deadline_ts=None, expiry_ts=None,
              instrument_class: str="index", detailed: bool=False,
              seconds: pd.DataFrame | None=None, return_stats: bool=False):
    """Run the shared-contract Rust kernel; retain the Python reference fallback."""
    try:
        from msd._msd_kernels import first_hit as rust_first_hit
    except ImportError as error:
        rust_fallback(error)
        return first_hit_reference(bars,entry_index,side,entry_price,sl,tp,max_bars,delay_bars,
            financing_per_night,limit_price,expiry_index,deadline_ts=deadline_ts,expiry_ts=expiry_ts,
            instrument_class=instrument_class,detailed=detailed,seconds=seconds,return_stats=return_stats)
    cols=["bid_o","bid_h","bid_l","bid_c","ask_o","ask_h","ask_l","ask_c"]
    rows=bars[cols].to_numpy(dtype=float).tolist()
    timestamps=pd.to_datetime(bars.ts,utc=True).astype("datetime64[ns, UTC]")
    stamps=timestamp_ints(timestamps,unit="s").tolist()
    if deadline_ts is None and max_bars is not None and entry_index+delay_bars<len(bars):
        deadline_i=min(entry_index+delay_bars+int(max_bars),len(bars)-1)
        deadline_ts=timestamps.iloc[deadline_i]
    deadline_seconds=None if deadline_ts is None else int(timestamp_ints(deadline_ts,unit="s"))
    if expiry_ts is None and expiry_index is not None and expiry_index<len(bars):
        expiry_ts=timestamps.iloc[int(expiry_index)]
    expiry_seconds=None if expiry_ts is None else int(timestamp_ints(expiry_ts,unit="s"))
    second_rows = seconds[cols].to_numpy(float).tolist() if seconds is not None else None
    second_stamps = (timestamp_ints(seconds.ts,unit="s")).tolist() if seconds is not None else None
    if return_stats:
        from msd._msd_kernels import first_hit_with_stats as rust_call
    else:
        rust_call = rust_first_hit
    result=rust_call(rows,stamps,int(entry_index),int(side),float(entry_price),float(sl),
        None if tp is None else float(tp),None,delay_bars,float(financing_per_night),limit_price,
        expiry_index,deadline_seconds,expiry_seconds,instrument_class,second_rows,second_stamps)
    reason={1:"tp",-1:"stop",0:"time",-2:"no_fill"}[int(result[0])]
    # Rust's audit tuple is outcome,index,fill,exit,net,gross,rollovers,entry,risk;
    # the Python contract keeps exit/net/gross before fill.
    converted=(reason,int(result[1]),result[3],result[4],result[5],result[2],
               int(result[6]),int(result[7]),result[8])
    selected = converted if detailed else converted[:5]
    return (*selected, dict(zip(AMBIGUITY_KEYS, map(int,result[9:13])))) if return_stats else selected


def label_grid(bars: pd.DataFrame, atr: pd.Series, every_minutes: int=15,
               max_bars: int|None=None, *, max_trading_days: int=5,
               instrument_class: str="crypto", seconds: pd.DataFrame | None=None,
               signal_start=None, signal_end=None,
               financing_per_night: float | None=None) -> pd.DataFrame:
    """Both-side ATR-grid labels; holding limit is a timestamp deadline."""
    try:
        from msd._msd_kernels import first_hit_batch
    except ImportError as error:
        rust_fallback(error)
        first_hit_batch=None
    stop_grid,tp_grid=(.5,1,1.5,2,3),(.5,1,1.5,2,3,4,6)
    stamps=pd.to_datetime(bars.ts,utc=True)
    stamp_ns=np.asarray(timestamp_ints(stamps,unit="ns"),dtype=np.int64)
    stamp_values=stamps.to_numpy()
    atr_values=atr.to_numpy(dtype=float)
    bar_columns=["bid_o","bid_h","bid_l","bid_c","ask_o","ask_h","ask_l","ask_c"]
    packed=bars[bar_columns].to_numpy(dtype="<f8")
    packed_bytes=packed.tobytes()
    time_seconds=np.asarray(timestamp_ints(stamps,unit="s"),dtype="<i8")
    time_bytes=time_seconds.tobytes()
    second_bytes=(seconds[bar_columns].to_numpy(dtype="<f8").tobytes() if seconds is not None else None)
    second_time_bytes=(np.asarray(timestamp_ints(seconds.ts,unit="s"),dtype="<i8").tobytes()
                       if seconds is not None else None)
    bid_c=packed[:,3];ask_c=packed[:,7]
    anchors=np.flatnonzero((stamps.dt.minute.to_numpy()%every_minutes)==0)
    if signal_start is not None:
        bound=pd.Timestamp(signal_start)
        bound=bound.tz_localize("UTC") if bound.tzinfo is None else bound.tz_convert("UTC")
        anchors=anchors[stamps.iloc[anchors].ge(bound).to_numpy()]
    if signal_end is not None:
        bound=pd.Timestamp(signal_end)
        bound=bound.tz_localize("UTC") if bound.tzinfo is None else bound.tz_convert("UTC")
        anchors=anchors[stamps.iloc[anchors].lt(bound).to_numpy()]
    outcome_code={"tp":1,"stop":-1,"sl":-1,"time":0,"no_fill":-2}
    rows=[]
    for anchor_start in range(0,len(anchors),700):
        chunk=anchors[anchor_start:anchor_start+700]
        if not len(chunk):continue
        jobs=[];metadata=[]
        for global_i in chunk:
            a=float(atr_values[global_i])
            if not np.isfinite(a) or a<=0 or global_i+2>=len(bars):continue
            entry_i=int(global_i)+2
            mid=(float(bid_c[global_i])+float(ask_c[global_i]))/2
            entry_stamp=pd.Timestamp(stamp_values[entry_i])
            entry_stamp=entry_stamp.tz_localize("UTC") if entry_stamp.tzinfo is None else entry_stamp.tz_convert("UTC")
            deadline=deadline_after_trading_days(entry_stamp,max_trading_days,instrument_class)
            deadline_value=int(timestamp_ints(deadline,unit="ns"))
            for side in (-1,1):
                for sl_mult in stop_grid:
                    sl=mid-side*sl_mult*a
                    for tp_mult in tp_grid:
                        tp=mid+side*tp_mult*a
                        finance=(financing_per_night if financing_per_night is not None else
                                 .0006 if instrument_class.lower() in {"crypto","24x7"} else .0002)
                        class_code=1 if instrument_class.lower() in {"crypto","24x7"} else 0
                        jobs.extend([global_i,side,mid,sl,tp,deadline_value//1_000_000_000,2,finance,np.nan,np.nan,class_code])
                        metadata.append((int(global_i),side,sl_mult,tp_mult,deadline_value))
        if not jobs:continue
        if first_hit_batch is not None:
            results=np.asarray(first_hit_batch(packed_bytes,time_bytes,jobs,11,second_bytes,
                                               second_time_bytes,seconds is not None),dtype=float).reshape(
                                                   -1,13 if seconds is not None else 9)
            for meta,res in zip(metadata,results):
                signal_i,side,sl_mult,tp_mult,deadline_ns=meta
                code,exit_i,fill,exit_price,net,gross,nights,entry_i,risk=res[:9]
                exit_i=int(exit_i);entry_i=int(entry_i)
                rows.append((signal_i,side,sl_mult,tp_mult,int(code),exit_i-signal_i if exit_i>=0 else -1,
                             net,gross,fill,exit_price,stamp_ns[exit_i] if exit_i>=0 else np.iinfo(np.int64).min,
                             nights,stamp_ns[entry_i] if entry_i>=0 else np.iinfo(np.int64).min,risk,deadline_ns,
                             {1:"tp",-1:"stop",0:"time",-2:"no_fill"}[int(code)],
                             *res[9:]))
        else:
            for signal_i,side,sl_mult,tp_mult,deadline_ns in metadata:
                mid=(float(bid_c[signal_i])+float(ask_c[signal_i]))/2
                a=float(atr_values[signal_i]);sl=mid-side*sl_mult*a;tp=mid+side*tp_mult*a
                deadline=pd.Timestamp(deadline_ns,tz="UTC")
                res=first_hit_reference(bars,signal_i,side,mid,sl,tp,delay_bars=2,deadline_ts=deadline,
                    instrument_class=instrument_class,detailed=True,seconds=seconds,return_stats=seconds is not None)
                reason,exit_i,exit_price,net,gross,fill,nights,entry_i,risk=res[:9]
                extra=tuple(res[9].values()) if seconds is not None else ()
                rows.append((signal_i,side,sl_mult,tp_mult,outcome_code[reason],exit_i-signal_i if exit_i>=0 else -1,
                             net,gross,fill,exit_price,stamp_ns[exit_i] if exit_i>=0 else np.iinfo(np.int64).min,
                             nights,stamp_ns[entry_i] if entry_i>=0 else np.iinfo(np.int64).min,risk,deadline_ns,reason,*extra))
    columns=["signal_index","side","sl_atr","tp_atr","outcome","exit_offset","net_R","gross_R",
             "fill_price","exit_price","exit_ts","financing_nights","entry_ts","planned_risk","deadline_ts","exit_reason"]
    if seconds is not None: columns += list(AMBIGUITY_KEYS)
    result=pd.DataFrame(rows,columns=columns)
    if result.empty:return result
    for column in ("exit_ts","entry_ts","deadline_ts"):
        result[column]=pd.to_datetime(result[column],unit="ns",utc=True,errors="coerce")
    return result.astype({"signal_index":"int32","side":"int8","sl_atr":"float32","tp_atr":"float32",
                          "outcome":"int8","exit_offset":"int32","net_R":"float32","gross_R":"float32",
                          "fill_price":"float32","exit_price":"float32","financing_nights":"int8","planned_risk":"float32"})
