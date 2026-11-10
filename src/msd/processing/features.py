"""Trailing-only dense features with explicit close-time known_at."""
from __future__ import annotations

import numpy as np
import pandas as pd
from bisect import bisect_left, insort_right
import heapq

from .levels import pivot_events
from .timeframes import INDEX_SYMBOLS, build_all_timeframes

EMA_WINDOWS = (20, 50, 200)
DONCHIAN_WINDOWS = (20, 55)
RETURN_WINDOWS = {
    "1m": (1, 5, 15, 60, 240, 1440),
    "5m": (1, 4, 12, 48), "15m": (1, 4, 12, 48),
    "1h": (1, 4, 24, 120), "4h": (1, 6, 30), "1d": (1, 5, 20, 60),
}
ATR_WINDOWS = (14, 50)
EMA_SLOPE_LAG = 5
DMI_PERIOD = 14
RSI_WINDOWS = (2, 14)
STOCH_WINDOW, STOCH_D_WINDOW = 14, 3
MACD_FAST, MACD_SLOW, MACD_SIGNAL = 12, 26, 9
BOLLINGER_WINDOW, BOLLINGER_WIDTH = 20, 2.0
VOLUME_Z_WINDOW = 20
REALIZED_VOL_WINDOW = 30


def _rsi(close: pd.Series, period: int) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1/period, adjust=False, min_periods=period).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1/period, adjust=False, min_periods=period).mean()
    return 100 - 100 / (1 + gain / loss.replace(0, np.nan))


def indicator_frame(frame: pd.DataFrame, timeframe: str = "1m") -> pd.DataFrame:
    """Compute trailing OHLCV indicators on completed bars."""
    if frame.empty:
        return pd.DataFrame(index=frame.index)
    out = pd.DataFrame(index=frame.index)
    close = frame.bid_c.astype(float)
    high, low = frame.bid_h.astype(float), frame.bid_l.astype(float)
    volume = frame.volume.astype(float) if "volume" in frame else pd.Series(np.nan, index=frame.index)
    prev = close.shift(1)
    tr = pd.concat([(high-low), (high-prev).abs(), (low-prev).abs()], axis=1).max(axis=1)
    logret = np.log(close / prev)
    feed = frame["feed"] if "feed" in frame else None
    roll = frame["roll"].fillna(False).astype(bool) if "roll" in frame else pd.Series(False,index=frame.index)
    if feed is not None:
        logret = logret.where(feed.eq(feed.shift(1)))
    logret = logret.where(~roll)
    for period in RETURN_WINDOWS.get(timeframe, RETURN_WINDOWS["1m"]):
        values=close.pct_change(period, fill_method=None)
        if feed is not None:
            values=values.where(feed.eq(feed.shift(period)))
        spans_roll=roll.astype("int8").rolling(period+1,min_periods=1).max().astype(bool)
        values=values.where(~spans_roll)
        out[f"return_bars_{period}"] = values
    out[f"realized_vol{REALIZED_VOL_WINDOW}"] = logret.rolling(REALIZED_VOL_WINDOW, min_periods=REALIZED_VOL_WINDOW).std(ddof=0) * np.sqrt(REALIZED_VOL_WINDOW)
    for period in ATR_WINDOWS:
        atr = tr.rolling(period, min_periods=period).mean()
        out[f"atr{period}"] = atr
        out[f"atr{period}_price"] = atr / close
        out[f"realized_vol{period}"] = logret.rolling(period, min_periods=period).std(ddof=0) * np.sqrt(period)
        out[f"parkinson_vol{period}"] = np.sqrt(np.log(high/low).pow(2).rolling(period, min_periods=period).mean() / (4*np.log(2)))
    out["vol_ratio14_50"] = out.realized_vol14 / out.realized_vol50
    for period in EMA_WINDOWS:
        ema = close.ewm(span=period, adjust=False, min_periods=period).mean()
        out[f"ema{period}_slope"] = ema.pct_change(EMA_SLOPE_LAG, fill_method=None)
        out[f"ema{period}_distance_atr"] = (close-ema) / out.atr14
    ema20 = close.ewm(span=20, adjust=False, min_periods=20).mean()
    ema50 = close.ewm(span=50, adjust=False, min_periods=50).mean()
    ema200 = close.ewm(span=200, adjust=False, min_periods=200).mean()
    out["ema20_50_gap_atr"] = (ema20-ema50)/out.atr14
    out["ema50_200_gap_atr"] = (ema50-ema200)/out.atr14
    for period in DONCHIAN_WINDOWS:
        upper = high.rolling(period, min_periods=period).max()
        lower = low.rolling(period, min_periods=period).min()
        out[f"donchian{period}_position"] = (close-lower)/(upper-lower).replace(0,np.nan)
        out[f"donchian{period}_width_atr"] = (upper-lower)/out.atr14
    up, down = high.diff(), -low.diff()
    plus_dm = up.where((up > down) & (up > 0), 0.0)
    minus_dm = down.where((down > up) & (down > 0), 0.0)
    atr14 = tr.ewm(alpha=1/DMI_PERIOD, adjust=False, min_periods=DMI_PERIOD).mean()
    out["plus_di14"] = 100*plus_dm.ewm(alpha=1/DMI_PERIOD, adjust=False, min_periods=DMI_PERIOD).mean()/atr14
    out["minus_di14"] = 100*minus_dm.ewm(alpha=1/DMI_PERIOD, adjust=False, min_periods=DMI_PERIOD).mean()/atr14
    dx = 100*(out.plus_di14-out.minus_di14).abs()/(out.plus_di14+out.minus_di14).replace(0,np.nan)
    out["adx14"] = dx.ewm(alpha=1/DMI_PERIOD, adjust=False, min_periods=DMI_PERIOD).mean()
    out[f"rsi{RSI_WINDOWS[0]}"], out[f"rsi{RSI_WINDOWS[1]}"] = (_rsi(close, period) for period in RSI_WINDOWS)
    lowest, highest = low.rolling(STOCH_WINDOW,min_periods=STOCH_WINDOW).min(), high.rolling(STOCH_WINDOW,min_periods=STOCH_WINDOW).max()
    out[f"stoch_k{STOCH_WINDOW}"] = 100*(close-lowest)/(highest-lowest).replace(0,np.nan)
    out[f"stoch_d{STOCH_D_WINDOW}"] = out[f"stoch_k{STOCH_WINDOW}"].rolling(STOCH_D_WINDOW,min_periods=STOCH_D_WINDOW).mean()
    macd = close.ewm(span=MACD_FAST,adjust=False,min_periods=MACD_FAST).mean()-close.ewm(span=MACD_SLOW,adjust=False,min_periods=MACD_SLOW).mean()
    signal = macd.ewm(span=MACD_SIGNAL,adjust=False,min_periods=MACD_SIGNAL).mean()
    out["macd_line_atr"], out["macd_signal_atr"], out["macd_hist_atr"] = macd/out.atr14, signal/out.atr14, (macd-signal)/out.atr14
    mid = close.rolling(BOLLINGER_WINDOW,min_periods=BOLLINGER_WINDOW).mean()
    std = close.rolling(BOLLINGER_WINDOW,min_periods=BOLLINGER_WINDOW).std(ddof=0)
    upper, lower = mid+BOLLINGER_WIDTH*std, mid-BOLLINGER_WIDTH*std
    out[f"bollinger_pctb{BOLLINGER_WINDOW}"] = (close-lower)/(upper-lower).replace(0,np.nan)
    out[f"bollinger_width{BOLLINGER_WINDOW}"] = (upper-lower)/mid.replace(0,np.nan)
    out["range_position14"] = (close-lowest)/(highest-lowest).replace(0,np.nan)
    lo50, hi50 = low.rolling(50,min_periods=50).min(), high.rolling(50,min_periods=50).max()
    out["range_position50"] = (close-lo50)/(hi50-lo50).replace(0,np.nan)
    vmean, vstd = volume.rolling(VOLUME_Z_WINDOW,min_periods=VOLUME_Z_WINDOW).mean(), volume.rolling(VOLUME_Z_WINDOW,min_periods=VOLUME_Z_WINDOW).std(ddof=0)
    out[f"volume_z{VOLUME_Z_WINDOW}"] = (volume-vmean)/vstd.replace(0,np.nan)
    out["volume_ratio20"] = volume/vmean.replace(0,np.nan)
    out["upper_wick_atr"] = (high-pd.concat([frame.bid_o,close],axis=1).max(axis=1))/out.atr14
    out["lower_wick_atr"] = (pd.concat([frame.bid_o,close],axis=1).min(axis=1)-low)/out.atr14
    return out.replace([np.inf,-np.inf],np.nan)


def _structure(frame: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    out = pd.DataFrame({"known_at": frame.known_at})
    events = pivot_events(frame, 3, timeframe)
    for kind in ("high", "low"):
        selected = events[events.type == f"swing_{kind}"][["known_at","price"]].sort_values("known_at").drop_duplicates("known_at",keep="last")
        if selected.empty:
            out[f"swing_{kind}"] = np.nan
            out[f"swing_{kind}_age"] = np.nan
            continue
        vals = pd.merge_asof(out[["known_at"]].sort_values("known_at"), selected.rename(columns={"price":f"swing_{kind}"}), on="known_at", direction="backward")
        out[f"swing_{kind}"] = vals[f"swing_{kind}"].to_numpy()
        event_ns = selected.known_at.to_numpy(dtype="datetime64[ns]")
        now_ns = out.known_at.to_numpy(dtype="datetime64[ns]")
        pos = np.searchsorted(event_ns,now_ns,side="right")-1
        age = np.full(len(out),np.nan); valid=pos>=0
        age[valid]=((now_ns[valid]-event_ns[pos[valid]])/np.timedelta64(1,"m")).astype(float)
        out[f"swing_{kind}_age"] = age
    out["higher_high"] = (out.swing_high.diff()>0).astype(float)
    out["higher_low"] = (out.swing_low.diff()>0).astype(float)
    close = frame.bid_c.to_numpy(float)
    out["bos_up"] = ((close>out.swing_high.to_numpy(float))&np.isfinite(out.swing_high.to_numpy(float))).astype(float)
    out["bos_down"] = ((close<out.swing_low.to_numpy(float))&np.isfinite(out.swing_low.to_numpy(float))).astype(float)
    out["choch_up"] = ((out.higher_low>0)&(out.bos_up>0)).astype(float)
    out["choch_down"] = ((out.higher_high>0)&(out.bos_down>0)).astype(float)
    return out


def _nearest_level_features(base: pd.DataFrame, levels: pd.DataFrame | None) -> pd.DataFrame:
    empty_fields={f"level_{side}_{rank}_{field}":np.full(len(base),np.nan,dtype=np.float32)
                  for side in ("above","below") for rank in range(1,4)
                  for field in ("distance_atr","type_code","strength","age_minutes")}
    if levels is None or levels.empty:
        return pd.concat([base,pd.DataFrame(empty_fields,index=base.index)],axis=1)
    levels=levels.copy()
    levels=levels[levels.type.astype(str) != "session_vwap"].copy()
    if levels.empty:
        return pd.concat([base,pd.DataFrame(empty_fields,index=base.index)],axis=1)
    codes={v:i+1 for i,v in enumerate(sorted(levels.type.astype(str).unique()))}
    levels["type_code"]=levels.type.astype(str).map(codes)
    prices=levels.price.to_numpy(float)
    known=pd.to_datetime(levels.known_at,utc=True).astype("datetime64[ns, UTC]").astype("int64").to_numpy()
    stamps=pd.to_datetime(base.known_at,utc=True).astype("datetime64[ns, UTC]").astype("int64").to_numpy()
    mids, atr=base.mid_close.to_numpy(float),base.base_atr14.to_numpy(float)
    invalid_ts=(pd.to_datetime(levels.invalidated_at,utc=True,errors="coerce") if "invalidated_at" in levels
                else pd.Series(pd.NaT,index=levels.index,dtype="datetime64[ns, UTC]"))
    invalid=invalid_ts.astype("datetime64[ns, UTC]").astype("int64").to_numpy(copy=True)
    invalid[invalid_ts.isna().to_numpy()]=np.iinfo(np.int64).max
    order=np.argsort(known,kind="stable")
    removals=sorted((int(invalid[i]),float(prices[i]),int(i)) for i in range(len(levels)) if invalid[i] != np.iinfo(np.int64).max)
    active=[]; cursor=0; removal_cursor=0
    fields=empty_fields
    strengths=levels.strength.to_numpy(float) if "strength" in levels else np.ones(len(levels))
    types=levels.type_code.to_numpy(float)
    for row,now in enumerate(stamps):
        while cursor<len(order) and known[order[cursor]]<=now:
            idx=int(order[cursor])
            if np.isfinite(prices[idx]): insort_right(active,(float(prices[idx]),idx))
            cursor+=1
        while removal_cursor<len(removals) and removals[removal_cursor][0]<=now:
            _,price,idx=removals[removal_cursor]
            pos=bisect_left(active,(price,idx))
            if pos<len(active) and active[pos]==(price,idx): active.pop(pos)
            removal_cursor+=1
        if not active or not np.isfinite(atr[row]) or atr[row]<=0 or not np.isfinite(mids[row]): continue
        pos=bisect_left(active,(float(mids[row]),-1))
        below=[active[k] for k in range(max(0,pos-3),pos)][::-1]
        above=[active[k] for k in range(pos,min(len(active),pos+3))]
        for side,ids in (("below",below),("above",above)):
            for rank,(_,idx) in enumerate(ids,1):
                key=f"level_{side}_{rank}_"
                fields[key+"distance_atr"][row]=(prices[idx]-mids[row])/atr[row]
                fields[key+"type_code"][row]=types[idx]
                fields[key+"strength"][row]=strengths[idx]
                fields[key+"age_minutes"][row]=(now-known[idx])/60e9
    return pd.concat([base,pd.DataFrame(fields,index=base.index)],axis=1)


def build_features(bars: pd.DataFrame, symbol: str, timeframes: dict[str,pd.DataFrame] | None=None,
                   levels: pd.DataFrame | None=None, auxiliary: dict[str,pd.DataFrame] | None=None,
                   cross_asset: dict[str,pd.DataFrame] | None=None, *,
                   output_start=None, output_end=None) -> pd.DataFrame:
    """Build rows for an optional output window using full causal warm-up input."""
    history=bars.sort_values("ts").reset_index(drop=True).copy()
    if history.empty: return pd.DataFrame(columns=["ts","known_at"])
    history["ts"]=pd.to_datetime(history.ts,utc=True).astype("datetime64[ns, UTC]")
    tfs=timeframes or build_all_timeframes(history,symbol)
    base_ind_history=indicator_frame(history,"1m")
    if output_start is None and output_end is None:
        output_mask=np.ones(len(history),dtype=bool)
    else:
        output_mask=np.ones(len(history),dtype=bool)
        if output_start is not None: output_mask &= history.ts.ge(pd.Timestamp(output_start)).to_numpy()
        if output_end is not None: output_mask &= history.ts.lt(pd.Timestamp(output_end)).to_numpy()
    source=history.loc[output_mask].reset_index(drop=True)
    base_ind=base_ind_history.loc[output_mask].reset_index(drop=True)
    if source.empty:return pd.DataFrame(columns=["ts","known_at"])
    out=pd.DataFrame({"ts":source.ts,"known_at":source.ts+pd.Timedelta(minutes=1),
                      "mid_close":((source.bid_c+source.ask_c)/2).to_numpy(float),
                      "spread":(source.ask_o-source.bid_o).to_numpy(float)})
    for col in base_ind: out[f"1m_{col}"]=base_ind[col].to_numpy()
    for tf,frame in tfs.items():
        frame=frame.copy()
        frame["ts"]=pd.to_datetime(frame.ts,utc=True).astype("datetime64[ns, UTC]")
        frame["known_at"]=pd.to_datetime(frame.known_at,utc=True).astype("datetime64[ns, UTC]")
        ind=indicator_frame(frame, tf)
        struct=_structure(frame,tf)
        merged=pd.concat([frame[["known_at"]].reset_index(drop=True),
                          frame[["known_at"]].rename(columns={"known_at":f"{tf}_bar_known_at"}).reset_index(drop=True),
                          ind.reset_index(drop=True), struct.drop(columns="known_at").reset_index(drop=True)],axis=1)
        merged=merged.rename(columns={c:f"{tf}_{c}" for c in merged.columns if c not in ("known_at", f"{tf}_bar_known_at")})
        out=pd.merge_asof(out.sort_values("known_at"),merged.sort_values("known_at"),on="known_at",direction="backward")
    out=out.copy()
    out["base_atr14"]=out.get("1m_atr14",np.nan)
    safe_atr=out.base_atr14.to_numpy(float).copy()
    safe_atr[~np.isfinite(safe_atr)|(safe_atr<=0)]=np.nan
    index_market=symbol in INDEX_SYMBOLS
    local=source.ts.dt.tz_convert("America/New_York" if index_market else "UTC")
    minute=(local.dt.hour*60+local.dt.minute).to_numpy()
    out["time_sin"]=np.sin(2*np.pi*minute/1440)
    out["time_cos"]=np.cos(2*np.pi*minute/1440)
    out["weekday"]=local.dt.day_of_week.to_numpy(float)
    out["minutes_since_session_open"]=(minute-(18*60 if index_market else 0))%1440
    local_history=history.ts.dt.tz_convert("America/New_York" if index_market else "UTC")
    minute_history=(local_history.dt.hour*60+local_history.dt.minute).to_numpy()
    if index_market:
        local_day_history=local_history.dt.tz_localize(None).to_numpy().astype("datetime64[D]")
        session_day_history=local_day_history+(minute_history>=18*60).astype("timedelta64[D]")
    else:
        session_day_history=local_history.dt.tz_localize(None).to_numpy().astype("datetime64[D]")
    session_day=session_day_history[output_mask]
    # Use a deterministic UTC-day ordinal so monthly windows match whole-history
    # builds rather than renumbering sessions from their local slice origin.
    out["session_id"]=session_day.astype("datetime64[D]").astype("int64").astype(float)
    out=_nearest_level_features(out,levels)
    for name in ("prior_day_high","prior_day_low","prior_week_high","prior_week_low"):
        selected=levels[levels.type==name] if levels is not None and "type" in levels else pd.DataFrame()
        if selected.empty: out[f"{name}_distance_atr"]=np.nan
        else:
            asof=pd.merge_asof(out[["known_at"]].sort_values("known_at"),selected[["known_at","price"]].sort_values("known_at"),on="known_at",direction="backward")
            out[f"{name}_distance_atr"]=np.divide(
                out.mid_close.to_numpy()-asof.price.to_numpy(), safe_atr,
                out=np.full(len(out), np.nan), where=np.isfinite(safe_atr))
    if "duka_spread" in source: spread=source.duka_spread.to_numpy(float)
    else: spread=out.spread.to_numpy(float)
    out["spread_atr"]=np.divide(spread,safe_atr,out=np.full(len(out),np.nan),where=np.isfinite(safe_atr))
    volume_column = "duka_volume" if "duka_volume" in history and history.duka_volume.notna().any() else "volume"
    volume_history=history[volume_column].to_numpy(float) if volume_column in history else np.full(len(history),np.nan)
    volume=volume_history[output_mask]
    if volume_column == "volume":
        out["volume_z20"]=base_ind.volume_z20.to_numpy(float)
    else:
        vseries=pd.Series(volume_history); vmean=vseries.rolling(20,min_periods=20).mean(); vstd=vseries.rolling(20,min_periods=20).std(ddof=0)
        out["volume_z20"]=((vseries-vmean)/vstd.replace(0,np.nan)).to_numpy(float)[output_mask]
    out["vwap_distance_atr"]=np.nan
    mid_history=((history.bid_c.to_numpy(float)+history.ask_c.to_numpy(float))/2)
    sessions_history=session_day_history.astype("datetime64[D]").astype("int64")
    safe_atr_history=base_ind_history.atr14.to_numpy(float).copy()
    safe_atr_history[~np.isfinite(safe_atr_history)|(safe_atr_history<=0)]=np.nan
    vwap_distance_history=np.full(len(history),np.nan)
    for key in np.unique(sessions_history):
        ix=np.flatnonzero(sessions_history==key); v=volume_history[ix]
        cv=np.cumsum(np.where(np.isfinite(v),v,0)); pv=np.cumsum(np.where(np.isfinite(v),mid_history[ix]*v,0))
        vw=np.divide(pv,cv,out=np.full(len(ix),np.nan),where=cv>0)
        vwap_distance_history[ix]=np.divide(mid_history[ix]-vw,safe_atr_history[ix],out=np.full(len(ix),np.nan),where=np.isfinite(safe_atr_history[ix]))
    out["vwap_distance_atr"]=vwap_distance_history[output_mask]
    out["taker_buy_ratio"]=(source.taker_buy_base/source.volume).to_numpy(float) if {"taker_buy_base","volume"}.issubset(source) else np.nan
    for column, feature in (("trades","trade_count_z20"),("quote_volume","quote_volume_z20")):
        values=history[column].to_numpy(float) if column in history else np.full(len(history),np.nan)
        series=pd.Series(values)
        mean=series.rolling(20,min_periods=20).mean(); std=series.rolling(20,min_periods=20).std(ddof=0)
        out[feature]=((series-mean)/std.replace(0,np.nan)).to_numpy()[output_mask]
    out["funding_z20"] = source.funding_z20.to_numpy(float) if "funding_z20" in source else np.nan
    if "open_interest" in history:
        oi=history.open_interest.to_numpy(float)
        prev_oi=np.r_[np.nan,oi[:-1]]
        change=np.divide(oi-prev_oi,prev_oi,out=np.full(len(oi),np.nan),where=np.isfinite(prev_oi)&(prev_oi!=0))
        out["open_interest_change"]=change[output_mask]
    else:
        out["open_interest_change"]=np.nan
    for name,frame in (auxiliary or {}).items():
        if frame.empty: continue
        if name.lower().startswith("vix") and "close" in frame:
            data=frame.copy()
            data["known_at"]=(pd.to_datetime(data.get("known_at",data.get("date")),utc=True)+pd.Timedelta(days=1)).astype("datetime64[ns, UTC]")
            col=f"{name}_level"
            aligned=pd.merge_asof(out[["known_at"]].sort_values("known_at"),data[["known_at","close"]].rename(columns={"close":col}).sort_values("known_at"),on="known_at",direction="backward")
            out[col]=aligned[col].to_numpy()
            if name.lower() == "vix":
                data["pct_1y"] = data.close.rolling(252, min_periods=126).apply(
                    lambda values: float((values <= values[-1]).mean()), raw=True)
                pct = pd.merge_asof(out[["known_at"]].sort_values("known_at"),
                                    data[["known_at", "pct_1y"]].sort_values("known_at"),
                                    on="known_at", direction="backward")
                out["vix_percentile_1y"] = pct.pct_1y.to_numpy()
        elif {"event","datetime_utc"}.issubset(frame.columns):
            stamps=pd.to_datetime(out.known_at,utc=True).astype("int64").to_numpy()
            for event_type in frame.event.astype(str).unique():
                times=pd.to_datetime(frame.loc[frame.event.astype(str)==event_type,"datetime_utc"],utc=True).astype("int64").to_numpy()
                label=event_type.lower().replace(" ","_")
                future=np.searchsorted(times,stamps,side="left"); prior=np.searchsorted(times,stamps,side="right")-1
                to=np.full(len(out),np.nan); since=to.copy()
                fvalid=future<len(times); pvalid=prior>=0
                to[fvalid]=(times[future[fvalid]]-stamps[fvalid])/60e9
                since[pvalid]=(stamps[pvalid]-times[prior[pvalid]])/60e9
                out[f"minutes_to_{label}"]=to; out[f"minutes_since_{label}"]=since
    for other,other_bars in (cross_asset or {}).items():
        if other==symbol or other_bars.empty: continue
        selected="adj_bid_c" if "adj_bid_c" in other_bars else "bid_c"
        data=other_bars[["ts",selected,*(["feed"] if "feed" in other_bars else [])]].rename(columns={selected:"bid_c"}).sort_values("ts").copy()
        data["known_at"]=data.ts+pd.Timedelta(minutes=1)
        for period in (15,60,240):
            ret=data.bid_c.pct_change(period,fill_method=None)
            if "feed" in data: ret=ret.where(data.feed.eq(data.feed.shift(period)))
            data[f"return_1m_bars_{period}"]=ret
        names=[f"return_1m_bars_{period}" for period in (15,60,240)]
        aligned=pd.merge_asof(out[["known_at"]].sort_values("known_at"),data[["known_at",*names]].sort_values("known_at"),on="known_at",direction="backward")
        for period,name in zip((15,60,240),names): out[f"cross_{other}_{name}"]=aligned[name].to_numpy()
    if "vix_level" in out and "vix3m_level" in out:
        out["vix_vix3m_ratio"] = out.vix_level / out.vix3m_level.replace(0, np.nan)
    excluded={"ts","known_at","mid_close","spread","base_atr14","volume_z20"}
    out=out.drop(columns=[c for c in ("mid_close","spread","base_atr14") if c in out])
    for redundant in ("1m_atr14_price","1m_atr50_price","1m_realized_vol50","1m_parkinson_vol50","1m_volume_ratio20"):
        if redundant in out: out=out.drop(columns=redundant)
    feature_cols=[c for c in out if c not in {"ts", "known_at"} and not c.endswith("_bar_known_at")]
    out[feature_cols]=out[feature_cols].replace([np.inf,-np.inf],np.nan).astype("float32")
    return out


def feature_qa(features: pd.DataFrame, symbol: str, path="reports/data", *, append: bool=False):
    """Write per-year feature coverage and distribution diagnostics."""
    from pathlib import Path
    path=Path(path)
    if path.suffix.lower()!=".md": path=path/f"feature_qa_{symbol}.md"
    path.parent.mkdir(parents=True,exist_ok=True)
    cols=[c for c in features if c not in {"ts","known_at"}]
    lines=[f"# Feature QA: {symbol}", "", "NaN-after-warmup starts at the first non-NaN observation in each year. Infinity counts apply to each yearly build batch.", "",
           f"Infinity values in supplied build batch: {int(np.isinf(features[cols].to_numpy(dtype=float)).sum()) if cols else 0}", "",
           "| Year | Feature | NaN share | NaN after warm-up | Min | P01 | Median | P99 | Max | Constant | Flag |", "|---:|---|---:|---:|---:|---:|---:|---:|---:|:---:|---|"]
    years=pd.to_datetime(features.ts,utc=True).dt.year
    for year in sorted(years.unique()):
        block=features.loc[years.eq(year),cols]
        for col in cols:
            values=pd.to_numeric(block[col],errors="coerce")
            finite=values[np.isfinite(values)]
            nan_share=float(values.isna().mean()) if len(values) else 1.
            first_valid=int(np.flatnonzero(values.notna().to_numpy())[0]) if len(finite) else len(values)
            warm=values.iloc[first_valid:]
            warm_share=float(warm.isna().mean()) if len(warm) else 1.
            constant=bool(len(finite) and finite.nunique(dropna=True)<=1)
            stats=np.nanpercentile(finite,[0,1,50,99,100]) if len(finite) else [np.nan]*5
            flag="constant full year" if constant else "all-NaN full year" if not len(finite) else ">50% NaN after warm-up" if warm_share>.5 else ""
            lines.append(f"| {year} | {col} | {nan_share:.4f} | {warm_share:.4f} | " + " | ".join("" if not np.isfinite(v) else f"{v:.7g}" for v in stats) + f" | {'yes' if constant else 'no'} | {flag} |")
    if append and path.exists():
        old=path.read_text().splitlines()
        separator=next(i for i,line in enumerate(old) if line.startswith("|---:"))
        year_values=set(years.unique().tolist())
        retained=old[separator+1:]
        retained=[line for line in retained if not any(line.startswith(f"| {year} |") for year in year_values)]
        path.write_text("\n".join(old[:separator+1]+retained+lines[separator+1:])+"\n")
    else:
        path.write_text("\n".join(lines)+"\n")
    return path

