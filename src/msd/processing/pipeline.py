"""Disk-backed Layer 2–5 processing runner; one bounded calendar-year batch at a time."""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
import os
from pathlib import Path
import shutil
import tempfile
import time

import numpy as np
import pandas as pd

from msd.data import load
from .features import build_features, feature_qa
from .labels import label_grid
from .levels import build_levels
from .timeframes import INDEX_SYMBOLS, TIMEFRAMES, build_all_timeframes
from msd.methods.common import assert_event_volume, exit_candidates, prepare_exit_levels
from msd.methods import sr_touch, rsi2_mean_reversion, liquidity_sweep

TIER1 = ("USATECHIDXUSD", "USA500IDXUSD", "XAUUSD", "BTCUSDT", "ETHUSDT")
MAX_LOOKBACK_DAYS = 370
MAX_HOLD_TRADING_DAYS = 5
INDEX_SPREAD_FALLBACK = {"USATECHIDXUSD": 2.881, "NSXUSD": 2.881,
                         "USA500IDXUSD": 0.462, "SPXUSD": 0.462}
BAR_DIR = Path("data/derived")
LEVEL_DIR = Path("data/levels")
FEATURE_DIR = Path("data/features")
LABEL_DIR = Path("data/labels")
MIN_FREE_BYTES = 65*1024**3
CASH_ERA_START = pd.Timestamp("2018-12-16 23:00:00",tz="UTC")
PILOT_METHODS = (sr_touch, rsi2_mean_reversion, liquidity_sweep)


def _check_disk() -> None:
    free=shutil.disk_usage(".").free
    if free<MIN_FREE_BYTES:
        raise OSError(f"Pipeline stopped before writing: only {free/1024**3:.1f} GiB free (65 GiB minimum)")


def methods_for_symbol(symbol: str) -> tuple:
    """Select pilots whose declared symbol scope includes this instrument."""
    return tuple(method for method in PILOT_METHODS
                 if not hasattr(method, "SYMBOLS") or symbol in method.SYMBOLS)


def _modelled_spread(frame: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """Model HistData spread; preserve executable bid/ask quotes from Dukascopy."""
    result = frame.copy()
    # Real Dukascopy quotes already carry executable bid/ask. Do not replace
    # their observed spread with a modeled cost unless this is a crypto trade
    # series, whose prices are intentionally single-price spot/UM bars.
    if symbol not in {"BTCUSDT", "ETHUSDT"} and "ask_o" in result and (result.ask_o > result.bid_o).any() and "feed" not in result:
        return result
    reference_symbols={"BTCUSDT":"BTCUSD","ETHUSDT":"ETHUSD",
                       "USATECHIDXUSD":"USATECHIDXUSD","NSXUSD":"USATECHIDXUSD",
                       "USA500IDXUSD":"USA500IDXUSD","SPXUSD":"USA500IDXUSD",
                       "GRXEUR":"DEUIDXEUR","WTIUSD":"LIGHTCMDUSD"}
    if symbol in reference_symbols and "duka_spread" not in result:
        duka_symbol = reference_symbols[symbol]
        try:
            duka = load(duka_symbol, result.ts.min(), result.ts.max(), raw=True)
        except FileNotFoundError:
            duka = pd.DataFrame()
        if not duka.empty:
            spread = duka.assign(duka_spread=duka.ask_o-duka.bid_o)[["ts", "duka_spread"]]
            result = result.merge(spread, on="ts", how="left", validate="one_to_one")
    if symbol in {"BTCUSDT", "ETHUSDT"}:
        # The spot source has trade-price OHLC. Model executable bid/ask from
        # the Dukascopy CFD spread series (nearest available year per bar).
        from msd.data.binance import BTC_SPREAD
        observed = result.get("duka_spread", pd.Series(np.nan,index=result.index)).to_numpy(float).copy()
        observed[~np.isfinite(observed)|(observed<=0)] = np.nan
        if symbol == "BTCUSDT":
            annual = pd.Series(BTC_SPREAD,dtype=float)
        else:
            # The ETH table is derived from the June 12–14 Dukascopy medians,
            # matching the BTC calibration convention, then nearest-year
            # carried for years without an exact sample.
            try:
                reference=load("ETHUSD",pd.Timestamp("2018-06-12",tz="UTC"),result.ts.max(),raw=True)
            except FileNotFoundError:
                reference=pd.DataFrame()
            if not reference.empty:
                sample=reference[(reference.ts.dt.month==6)&reference.ts.dt.day.between(12,14)]
                annual=sample.assign(spread=sample.ask_o-sample.bid_o).groupby(sample.ts.dt.year).spread.median()
            else:
                annual=pd.Series(dtype=float)
        spread = np.full(len(result),np.nan)
        available_years=annual.dropna().index.to_numpy(dtype=int)
        if not len(available_years):
            raise ValueError(f"No Dukascopy modeled spread history available for {symbol}")
        for year in result.ts.dt.year.unique():
            exact=annual.get(int(year),np.nan)
            if not np.isfinite(exact):
                nearest=int(np.argmin(np.abs(available_years-int(year))))
                exact=float(annual.loc[available_years[nearest]])
            spread[result.ts.dt.year.to_numpy()==year]=float(exact)
        for field in "ohlc":
            mid=(result[f"bid_{field}"].to_numpy(float)+result[f"ask_{field}"].to_numpy(float))/2
            result[f"bid_{field}"]=mid-spread/2
            result[f"ask_{field}"]=mid+spread/2
        result["duka_spread"]=spread
        return result
    if "feed" in result:
        already_executable=(result.ask_o.to_numpy(float)>result.bid_o.to_numpy(float))
        model_mask=(result.feed.to_numpy() != "cash_cfd") | ~already_executable
    else:
        model_mask=np.ones(len(result),dtype=bool)
    if not model_mask.any():
        return result
    observed = result.get("duka_spread", pd.Series(np.nan, index=result.index)).to_numpy(float).copy()
    observed[~np.isfinite(observed) | (observed <= 0)] = np.nan
    observed[~model_mask] = np.nan
    spread = observed.copy()
    annual = pd.Series(observed[model_mask], index=result.ts[model_mask]).groupby(result.ts[model_mask].dt.year).median()
    annual = annual[np.isfinite(annual) & (annual > 0)]
    fallback = INDEX_SPREAD_FALLBACK.get(symbol, np.nan)
    for year in result.ts.dt.year.unique():
        mask = (result.ts.dt.year.to_numpy() == year) & model_mask
        candidate = annual.get(year, np.nan)
        if not np.isfinite(candidate) or candidate <= 0:
            nearest = int(np.argmin(np.abs(annual.index.to_numpy(dtype=int)-int(year)))) if len(annual) else None
            candidate = float(annual.iloc[nearest]) if nearest is not None else fallback
        spread[mask & ~np.isfinite(spread)] = candidate
    valid = model_mask & np.isfinite(spread)
    if valid.any():
        for field in "ohlc":
            mid=(result[f"bid_{field}"].to_numpy(float)+result[f"ask_{field}"].to_numpy(float))/2
            result.loc[valid,f"bid_{field}"] = mid[valid]-spread[valid]/2
            result.loc[valid,f"ask_{field}"] = mid[valid]+spread[valid]/2
    return result


def assert_executable_spread(frame: pd.DataFrame, symbol: str) -> None:
    """Reject label inputs without a positive modeled or quoted spread."""
    if any(f"{side}_{field}" not in frame for side in ("bid","ask") for field in "ohlc"):
        raise ValueError(f"Incomplete bid/ask bars for {symbol}")
    valid=all(np.isfinite(frame[f"ask_{field}"].to_numpy(float)).all() and
              np.isfinite(frame[f"bid_{field}"].to_numpy(float)).all() and
              (frame[f"ask_{field}"].to_numpy(float)>frame[f"bid_{field}"].to_numpy(float)).all()
              for field in "ohlc")
    if not valid:
        raise ValueError(f"Label input has non-positive or non-finite bid/ask spread: {symbol}")


def _feature_label_bars(frame: pd.DataFrame) -> pd.DataFrame:
    """Exclude bad ticks and stale expired-contract bars from all derived data."""
    mask=np.ones(len(frame),dtype=bool)
    for flag in ("bad_tick","stale_expired"):
        if flag in frame:
            mask &= ~frame[flag].fillna(False).astype(bool).to_numpy()
    if "feed" in frame and "adj_bid_c" in frame:
        futures=frame.feed.eq("futures_cont").to_numpy()
        adjusted=np.isfinite(frame.adj_bid_c.to_numpy(float))
        mask &= ~futures|adjusted
    return frame.loc[mask].copy().reset_index(drop=True)


def _adjusted_price_view(frame: pd.DataFrame) -> pd.DataFrame:
    """Use back-adjusted bid prices for indicators while preserving source flags."""
    out=frame.copy()
    if not all(f"adj_bid_{field}" in out for field in "ohlc"):
        return out
    modeled = out.feed.eq("futures_cont").to_numpy() if "feed" in out else np.zeros(len(out),dtype=bool)
    for field in "ohlc":
        adj=out[f"adj_bid_{field}"].to_numpy(float)
        old_bid=out[f"bid_{field}"].to_numpy(float)
        old_ask=out[f"ask_{field}"].to_numpy(float)
        real_spread=np.maximum(old_ask-old_bid,0.0)
        adjusted_bid=np.where(modeled,adj,old_bid)
        out[f"bid_{field}"]=adjusted_bid
        # Historical bid-only bars stay centered for the modeled spread pass;
        # cash CFD rows preserve their original executable spread.
        out[f"ask_{field}"]=adjusted_bid+real_spread
    return out


def _write_monthly(frame: pd.DataFrame, directory: Path, symbol: str, compression: str = "zstd") -> int:
    if frame.empty:
        return 0
    work = frame.copy()
    work["_month"] = pd.to_datetime(work.ts, utc=True).dt.strftime("%Y-%m")
    for month, part in work.groupby("_month", sort=True):
        _check_disk()
        target = directory / symbol / f"{month}.parquet"
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=target.parent,suffix=".parquet",delete=False) as handle:
            temp=Path(handle.name)
        part.drop(columns="_month").to_parquet(temp,index=False,compression=compression)
        os.replace(temp,target)
    return len(work)


def _first_year(symbol: str) -> int:
    root = {
        "USATECHIDXUSD": Path("data/bars/histdata/NSXUSD"),
        "USA500IDXUSD": Path("data/bars/histdata/SPXUSD"),
        "BTCUSDT": Path("data/bars/binance_spot/BTCUSDT"),
        "ETHUSDT": Path("data/bars/binance_spot/ETHUSDT"),
        "XAUUSD": Path("data/bars/dukascopy/XAUUSD"),
    }[symbol]
    files = sorted(root.glob("[0-9][0-9][0-9][0-9]-[0-9][0-9].parquet"))
    return int(files[0].stem[:4]) if files else datetime.now(timezone.utc).year


def _active_mask(bars: pd.DataFrame, symbol: str) -> np.ndarray:
    if symbol not in INDEX_SYMBOLS:
        return np.ones(len(bars),dtype=bool)
    local=bars.ts.dt.tz_convert("America/New_York")
    minute=local.dt.hour*60+local.dt.minute
    dow=local.dt.day_of_week
    return ((((dow>=0)&(dow<=3))&((minute<17*60)|(minute>=18*60)))|
            ((dow==4)&(minute<17*60))|((dow==6)&(minute>=18*60))).to_numpy()


def _parquet_union(root: Path) -> pd.DataFrame:
    paths=sorted(root.rglob("*.parquet")) if root.exists() else []
    frames=[pd.read_parquet(path) for path in paths]
    return pd.concat(frames,ignore_index=True) if frames else pd.DataFrame()


def _auxiliary_inputs() -> dict[str,pd.DataFrame]:
    auxiliary={}
    for name,path in (("vix",Path("data/aux/vix/VIX_History.parquet")),
                      ("vix3m",Path("data/aux/vix/VIX3M_History.parquet")),
                      ("vix9d",Path("data/aux/vix/VIX9D_History.parquet"))):
        if path.exists(): auxiliary[name]=pd.read_parquet(path)
    macro=Path("data/aux/macro_events.csv")
    if macro.exists(): auxiliary["macro_events"]=pd.read_csv(macro)
    earnings=_parquet_union(Path("data/aux/earnings"))
    if not earnings.empty: auxiliary["earnings"]=earnings
    return auxiliary


def _attach_market_auxiliary(bars: pd.DataFrame, symbol: str) -> pd.DataFrame:
    result=bars
    if symbol not in {"BTCUSDT","ETHUSDT"}: return result
    funding=_parquet_union(Path("data/aux/funding")/symbol)
    if not funding.empty and ("funding_time" in funding or "ts" in funding):
        time_col="funding_time" if "funding_time" in funding else "ts"
        funding["known_at"]=pd.to_datetime(funding[time_col],utc=True).astype("datetime64[ns, UTC]")
        funding=funding.sort_values("known_at").drop_duplicates("known_at",keep="last")
        funding["funding_z20"]=(funding.funding_rate-funding.funding_rate.rolling(20,min_periods=20).mean())/funding.funding_rate.rolling(20,min_periods=20).std(ddof=0).replace(0,np.nan)
        left=result[["ts"]].assign(known_at=(pd.to_datetime(result.ts,utc=True)+pd.Timedelta(minutes=1)).astype("datetime64[ns, UTC]")).sort_values("known_at")
        aligned=pd.merge_asof(left,funding[["known_at","funding_rate","funding_z20"]],on="known_at",direction="backward")
        result=result.copy()
        result["funding_rate"]=aligned.funding_rate.to_numpy()
        result["funding_z20"]=aligned.funding_z20.to_numpy()
    metrics=_parquet_union(Path("data/aux/metrics")/symbol)
    if not metrics.empty and "create_time" in metrics:
        metrics["known_at"]=pd.to_datetime(metrics.create_time,utc=True).astype("datetime64[ns, UTC]")
        cols=[c for c in ("sum_open_interest","count_long_short_ratio","sum_taker_long_short_vol_ratio") if c in metrics]
        metrics=metrics[["known_at",*cols]].sort_values("known_at")
        left=result[["ts"]].assign(known_at=(pd.to_datetime(result.ts,utc=True)+pd.Timedelta(minutes=1)).astype("datetime64[ns, UTC]")).sort_values("known_at")
        aligned=pd.merge_asof(left,metrics,on="known_at",direction="backward")
        result=result.copy()
        if "sum_open_interest" in aligned: result["open_interest"]=aligned.sum_open_interest.to_numpy()
        if "count_long_short_ratio" in aligned: result["long_short_ratio"]=aligned.count_long_short_ratio.to_numpy()
        if "sum_taker_long_short_vol_ratio" in aligned: result["taker_long_short_ratio"]=aligned.sum_taker_long_short_vol_ratio.to_numpy()
        if "sum_open_interest" in aligned:
            oi=aligned.sum_open_interest.to_numpy(float)
            previous=np.r_[np.nan,oi[:-1]]
            result["open_interest_change"]=np.divide(oi-previous,previous,out=np.full(len(oi),np.nan),where=np.isfinite(previous)&(previous!=0))
    return result


def write_feature_dictionary(columns: list[str]) -> Path:
    prefixes = {
        "return_": "Trailing close-to-close fractional return over the named bar window.",
        "realized_vol": "Trailing log-return standard deviation scaled by square root of window length.",
        "parkinson_vol": "Trailing high/low Parkinson volatility estimator.",
        "atr": "Trailing mean true range; price units unless normalized in the feature name.",
        "ema": "Trailing EMA slope, distance or gap; distance values are ATR normalized.",
        "rsi": "Wilder-style trailing relative strength index.",
        "level_": "Nearest active level distance/type/strength/age, as-of joined by known_at.",
        "vwap_": "Cumulative session VWAP distance; NaN when volume is unavailable.",
        "volume": "Trailing volume statistic; NaN when source volume is unavailable.",
        "taker_": "Binance taker-buy base volume divided by total base volume.",
        "minutes_": "Minutes to or since a published event timestamp.",
        "cross_": "Other instrument's trailing return as-of its completed bar close.",
        "vix": "Daily Cboe volatility-index observation, available after source close.",
        "spread_": "Bid/ask spread divided by trailing ATR.",
    }
    rows = ["# Feature dictionary", "", "Every row carries ts (bar open) and known_at (bar close). Values use observations known at or before known_at; joined higher-timeframe values appear only after that timeframe closes.", "",
            "| Feature | Definition | Timeframe | Known-at rule |", "|---|---|---|---|"]
    for name in sorted(set(columns)-{"ts", "known_at"}):
        prefix = name.split("_", 1)[0]
        tf = prefix if prefix in {"1m", "5m", "15m", "1h", "4h", "1d"} else "1m / calendar"
        definition = next((text for key,text in prefixes.items() if name.startswith(key)), "Trailing causal feature or calendar encoding.")
        rows.append(f"| {name} | {definition} | {tf} | Completed close at or before row known_at |" )
    path=Path("reports/data/feature_dictionary.md"); path.parent.mkdir(parents=True,exist_ok=True); path.write_text("\n".join(rows)+"\n")
    return path


def label_method_events(features: pd.DataFrame, levels: pd.DataFrame, bars: pd.DataFrame, symbol: str,
                        *, return_event_counts: bool = False, event_start=None, event_end=None):
    try:
        from msd._msd_kernels import first_hit_batch
    except ImportError:
        first_hit_batch = None
    methods=methods_for_symbol(symbol)
    instrument_class="index" if symbol in INDEX_SYMBOLS else "crypto" if symbol in {"BTCUSDT","ETHUSDT"} else "index"
    finance=.0002 if symbol in INDEX_SYMBOLS else .0006 if symbol in {"BTCUSDT","ETHUSDT"} else .00015
    event_bars=bars.sort_values("ts").reset_index(drop=True)
    atr_map=features.set_index("ts")["1m_atr14"] if "1m_atr14" in features else pd.Series(dtype=float)
    close_mid=(event_bars.bid_c.to_numpy(float)+event_bars.ask_c.to_numpy(float))/2
    ts_pos=pd.Series(np.arange(len(event_bars)),index=event_bars.ts)
    jobs=[]; metadata=[]; detected_counts={}
    prepared_levels=prepare_exit_levels(levels)
    for method in methods:
        method_started=time.perf_counter()
        events=method.detect(features,levels,event_bars)
        if event_start is not None:
            events=[event for event in events if pd.Timestamp(event["ts"]) >= pd.Timestamp(event_start)]
        if event_end is not None:
            events=[event for event in events if pd.Timestamp(event["ts"]) < pd.Timestamp(event_end)]
        detected_counts[method.NAME] = len(events)
        if symbol in INDEX_SYMBOLS:
            day_features=features
            if event_start is not None: day_features=day_features[day_features.ts>=pd.Timestamp(event_start)]
            if event_end is not None: day_features=day_features[day_features.ts<pd.Timestamp(event_end)]
            local_event = pd.to_datetime(day_features.ts,utc=True).dt.tz_convert("America/New_York")
            session_day = local_event.dt.tz_localize(None).to_numpy().astype("datetime64[D]")
            session_day += (local_event.dt.hour.to_numpy() >= 18).astype("timedelta64[D]")
            day_count = max(1, len(np.unique(session_day)))
        else:
            day_features=features
            if event_start is not None: day_features=day_features[day_features.ts>=pd.Timestamp(event_start)]
            if event_end is not None: day_features=day_features[day_features.ts<pd.Timestamp(event_end)]
            day_count = max(1, pd.to_datetime(day_features.ts,utc=True).dt.floor("D").nunique())
        assert_event_volume(method.NAME, symbol, len(events), day_count)
        print({"symbol":symbol,"phase":"event_detection","method":method.NAME,
               "events":len(events),"elapsed_seconds":time.perf_counter()-method_started},flush=True)
        for event in events:
            event["sym"]=symbol
            event_i=ts_pos.get(event["ts"])
            if event_i is None: continue
            entry=float(close_mid[int(event_i)])
            atr=float(atr_map.get(event["ts"],np.nan))
            sides=event.get("side_candidates",[event.get("side")])
            for side in sides:
                if side not in (-1,1): continue
                oriented={**event,"side":int(side)}
                for candidate in exit_candidates(oriented,levels,atr,prepared_levels):
                    sl,tp=candidate.get("sl"),candidate.get("tp")
                    if sl is None or tp is None or not np.isfinite(sl) or not np.isfinite(tp): continue
                    if int(side)*(entry-float(sl))<=0 or int(side)*(float(tp)-entry)<=0: continue
                    entry_i=int(event_i)+2
                    if entry_i>=len(event_bars): continue
                    from .labels import deadline_after_trading_days
                    deadline=deadline_after_trading_days(event_bars.ts.iloc[entry_i],MAX_HOLD_TRADING_DAYS,instrument_class)
                    class_code=1 if instrument_class in {"crypto","24x7"} else 0
                    jobs.extend([int(event_i),int(side),entry,float(sl),float(tp),int(deadline.value//1_000_000_000),
                                 2,finance,np.nan,np.nan,class_code])
                    metadata.append({**oriented,"exit_kind":candidate["kind"],"sl":float(sl),"tp":float(tp),
                                     "deadline_ts":deadline})
    if not jobs:
        empty = pd.DataFrame()
        return (empty, detected_counts) if return_event_counts else empty
    matrix=event_bars[["bid_o","bid_h","bid_l","bid_c","ask_o","ask_h","ask_l","ask_c"]].to_numpy(dtype="<f8")
    stamps=pd.to_datetime(event_bars.ts,utc=True).astype("datetime64[ns, UTC]").astype("int64").to_numpy()//1_000_000_000
    if first_hit_batch is not None:
        result=np.asarray(first_hit_batch(matrix.tobytes(),np.asarray(stamps,dtype="<i8").tobytes(),jobs,11)).reshape(-1,9)
    else:
        from .labels import first_hit_reference
        result=[]
        for event in metadata:
            signal_i=int(ts_pos.get(event["ts"]))
            ref=first_hit_reference(event_bars,signal_i,int(event["side"]),float(event["price"]),
                event["sl"],event["tp"],delay_bars=2,financing_per_night=finance,
                deadline_ts=event["deadline_ts"],instrument_class=instrument_class,detailed=True)
            reason,exit_i,exit_price,net,gross,fill,nights,entry_i,risk=ref
            result.append(({"tp":1,"stop":-1,"time":0,"no_fill":-2}[reason],exit_i,fill,exit_price,
                           net,gross,nights,entry_i,risk))
        result=np.asarray(result,dtype=float)
    labels=[]
    outcome={1:"tp",-1:"sl",0:"time",-2:"no_fill"}
    for event,row in zip(metadata,result):
        code,exit_i,fill,exit_price,net_r,gross_r,nights,entry_i,risk=row
        entry_i=int(entry_i);exit_i=int(exit_i)
        record={**event,"entry_ts":event_bars.ts.iloc[entry_i] if 0<=entry_i<len(event_bars) else pd.NaT,
                "entry_price":float(fill),"planned_risk":float(risk),
                "outcome":outcome[int(code)],"exit_ts":event_bars.ts.iloc[exit_i] if 0<=exit_i<len(event_bars) else pd.NaT,
                "exit_price":float(exit_price),"R":float(net_r),"gross_R":float(gross_r),
                "financing_nights":int(nights)}
        labels.append(record)
    result = pd.DataFrame(labels)
    return (result, detected_counts) if return_event_counts else result


def run_symbol(symbol: str, start_year: int | None = None, end_year: int | None = None) -> dict:
    start_year = start_year or _first_year(symbol)
    started = time.perf_counter()
    end_year = min(end_year or datetime.now(timezone.utc).year, datetime.now(timezone.utc).year)
    timeframes_written = features_written = labels_written = events_written = 0
    level_parts = []
    timings=[]
    event_year_counts=[]
    bad_tick_count=0
    for year in range(start_year, end_year+1):
        year_started=time.perf_counter()
        left = pd.Timestamp(year=year, month=1, day=1, tz="UTC") - pd.Timedelta(days=MAX_LOOKBACK_DAYS)
        right = pd.Timestamp(year=year+1, month=1, day=1, tz="UTC") + pd.Timedelta(days=8)
        bars = load(symbol, left, right)
        if bars.empty:
            continue
        bars=_cash_era_only(bars,symbol)
        if bars.empty:
            continue
        _assert_index_cash_only(bars,symbol)
        bars = _adjusted_price_view(bars.sort_values("ts").reset_index(drop=True))
        if "bad_tick" in bars:
            bad_tick_count+=int(bars.bad_tick.fillna(False).astype(bool).sum())
        bars=_feature_label_bars(bars)
        bars = _modelled_spread(bars, symbol)
        assert_executable_spread(bars,symbol)
        bars = _attach_market_auxiliary(bars,symbol)
        active_bars=bars.loc[_active_mask(bars,symbol)].reset_index(drop=True)
        tfs = build_all_timeframes(bars, symbol)
        year_end = pd.Timestamp(year=year+1, month=1, day=1, tz="UTC")
        year_start=pd.Timestamp(year,1,1,tz="UTC")
        selected_tfs = {tf: frame[(frame.ts >= year_start) & (frame.ts < year_end)].copy() for tf, frame in tfs.items()}
        for tf, frame in selected_tfs.items():
            timeframes_written += _write_monthly(frame, BAR_DIR / f"bars_{tf}", symbol)
        levels = build_levels(active_bars, symbol, tfs)
        levels=levels[levels.known_at < year_end]
        level_parts.append(levels[levels.known_at>=year_start])
        auxiliary=_auxiliary_inputs()
        cross={}
        for other in TIER1:
            if other==symbol: continue
            # Cross-asset returns use the source price series, not executable
            # fills.  Loading raw avoids requiring a modeled BTC/ETH spread
            # just to construct a price-only context feature.
            other_bars=load(other,left,right,raw=True)
            if not other_bars.empty:
                other_bars=_cash_era_only(other_bars,other)
            if not other_bars.empty:
                other_bars=_feature_label_bars(other_bars)
                cross[other]=other_bars[["ts","bid_c",*( ["feed"] if "feed" in other_bars else [] )]]
        # Keep one causal predecessor row for event detectors that need to
        # recognize an as-of HTF transition at the first row of a year.
        feature_history = build_features(bars, symbol, tfs, levels, auxiliary=auxiliary, cross_asset=cross,
                                         output_start=year_start-pd.Timedelta(minutes=1),output_end=year_end)
        feature_mask=(feature_history.ts >= pd.Timestamp(year, 1, 1, tz="UTC")) & (feature_history.ts < year_end)
        features=feature_history.loc[feature_mask]
        features=features.replace([np.inf,-np.inf],np.nan)
        write_feature_dictionary(features.columns.tolist())
        features_written += _write_monthly(features, FEATURE_DIR, symbol)
        feature_qa(features,symbol,append=True)
        # Preserve the bar alignment directly.  Building a Python set of
        # hundreds of thousands of Timestamps and probing it row-wise is
        # expensive and unnecessary because features retain the input order.
        method_mask=(feature_history.ts>=year_start-pd.Timedelta(minutes=1))&(feature_history.ts<year_end)
        method_features=feature_history.loc[method_mask]
        method_features=method_features.loc[_active_mask(method_features,symbol)]
        events, unique_events = label_method_events(method_features,levels,active_bars,symbol,
                                                    return_event_counts=True,event_start=year_start,event_end=year_end)
        if len(events):
            events=events[events.ts < year_end]
            candidate_counts=events.groupby("method",dropna=False).size()
            event_year_counts.extend({"symbol":symbol,"year":year,"method":str(method),
                                      "unique_events":int(unique_events.get(str(method),0)),
                                      "candidate_rows":int(candidate_counts.get(method,0))}
                                     for method in sorted(set(unique_events)|set(candidate_counts.index)))
            print({"symbol":symbol,"year":year,"phase":"event_counts",
                   "counts":{str(method):{"unique_events":int(unique_events.get(str(method),0)),
                                          "candidate_rows":int(candidate_counts.get(method,0))}
                            for method in sorted(set(unique_events)|set(candidate_counts.index))}},flush=True)
            events_written += _write_monthly(events,Path("data/events"),symbol)
        # ATR(1h) is joined by its completed-bar timestamp; no in-progress HTF value is used.
        if not tfs["1h"].empty:
            atr = tfs["1h"][["known_at"]].copy()
            atr["atr"] = __import__("msd.processing.features", fromlist=["indicator_frame"]).indicator_frame(tfs["1h"]).atr14
            per_minute = pd.merge_asof(bars[["ts"]].assign(known_at=bars.ts+pd.Timedelta(minutes=1)).sort_values("known_at"),
                                       atr.sort_values("known_at"), on="known_at", direction="backward").atr
        else:
            per_minute = pd.Series(np.nan, index=bars.index)
        label_mask = (bars.ts >= pd.Timestamp(year, 1, 1, tz="UTC")) & (bars.ts < right) & _active_mask(bars,symbol)
        label_bars = bars.loc[label_mask].reset_index(drop=True)
        label_atr = per_minute.loc[label_mask].reset_index(drop=True)
        label_started=time.perf_counter()
        instrument_class="index" if symbol in INDEX_SYMBOLS else "crypto" if symbol in {"BTCUSDT","ETHUSDT"} else "index"
        labels = label_grid(label_bars, label_atr, max_trading_days=MAX_HOLD_TRADING_DAYS,
                            instrument_class=instrument_class)
        print({"symbol":symbol,"year":year,"phase":"grid_labels",
               "rows":len(labels),"elapsed_seconds":time.perf_counter()-label_started},flush=True)
        if len(labels):
            labels["ts"] = label_bars.ts.iloc[labels.signal_index.to_numpy()].to_numpy()
            labels = labels[labels.ts < year_end]
            labels_written += _write_monthly(labels, LABEL_DIR, symbol)
        timings.append((year,len(bars),len(features),len(labels),time.perf_counter()-year_started))
        print({"symbol":symbol,"year":year,"input_bars":len(bars),"feature_rows":len(features),
               "label_rows":len(labels),"elapsed_seconds":timings[-1][-1]},flush=True)
    if level_parts:
        levels = pd.concat(level_parts, ignore_index=True).drop_duplicates(
            ["price", "type", "timeframe", "known_at"], keep="last").sort_values("known_at")
        _check_disk()
        LEVEL_DIR.mkdir(parents=True, exist_ok=True)
        target=LEVEL_DIR/f"{symbol}.parquet"
        with tempfile.NamedTemporaryFile(dir=LEVEL_DIR,suffix=".parquet",delete=False) as handle: temp=Path(handle.name)
        levels.to_parquet(temp,index=False,compression="zstd"); os.replace(temp,target)
    result={"symbol": symbol, "features": features_written, "levels": sum(map(len, level_parts)),
            "bars": timeframes_written, "labels": labels_written,"events":events_written,
            "unique_events":sum(row["unique_events"] for row in event_year_counts),
            "event_year_counts":event_year_counts,"bad_ticks_excluded":bad_tick_count,
            "year_timings":timings,"runtime_seconds": time.perf_counter()-started}
    return result


def _cash_era_only(bars: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """Exclude every futures-era minute from index features and labels."""
    if symbol not in {"USATECHIDXUSD","USA500IDXUSD"} or bars.empty:
        return bars
    ts=pd.to_datetime(bars.ts,utc=True)
    return bars.loc[ts>=CASH_ERA_START].copy()


def _assert_index_cash_only(bars: pd.DataFrame, symbol: str) -> None:
    """Prevent any futures-era index minute from entering the pipeline."""
    if symbol in {"USATECHIDXUSD","USA500IDXUSD"} and not bars.empty and pd.to_datetime(bars.ts,utc=True).lt(CASH_ERA_START).any():
        raise RuntimeError(f"Index pipeline rejects pre-cash-era bars for {symbol}; earliest allowed ts is {CASH_ERA_START}")


def write_pipeline_report(results: list[dict]) -> Path:
    inventory=[]
    for root in (BAR_DIR, LEVEL_DIR, FEATURE_DIR, Path("data/events"), LABEL_DIR):
        if root.exists():
            files=[p for p in root.rglob("*.parquet") if p.is_file()]
            inventory.append((root,len(files),sum(p.stat().st_size for p in files)))
    lines=["# Processing pipeline report", "", "Protocol: docs/protocol.md v2. No model training was run. The final period remains locked.", "",
           "## Fixed processing constants", "", "| Constant | Value |", "|---|---:|", 
           f"| Index input boundary | {CASH_ERA_START} (futures era excluded) |",
           "| Index development period | 2019-01-01 through 2022-12-31 |",
           f"| Maximum HTF warm-up | {MAX_LOOKBACK_DAYS} calendar days |", "| Label entry delay | 2 bars after signal bar |", 
           f"| Maximum label holding window | {MAX_HOLD_TRADING_DAYS} weekdays (non-crypto; deadline at first bar open at/after timestamp) or {MAX_HOLD_TRADING_DAYS}×24h (crypto) |", 
           "| Label cadence | every 15 UTC minutes; both sides |", "| S/R touch | level clusters within 0.25 ATR(1h), >=2 touches; edge-trigger within 0.1 ATR, 0.5 ATR re-arm; 4h cooldown |", "| Liquidity sweep | clustered 15m+ levels; 0.1 ATR wick, close-back within 3 bars; 4h cooldown |", "| SL ATR grid | 0.5, 1, 1.5, 2, 3 |", 
           "| TP ATR grid | 0.5, 1, 1.5, 2, 3, 4, 6 |", "| ATR source | 14-period ATR on completed 1h bars |", "",
           "## Output inventory", "", "| Root | Parquet files | Bytes |", "|---|---:|---:|"]
    lines += [f"| {root} | {count:,} | {size:,} |" for root,count,size in inventory]
    lines += ["", "## Processing runs", "", "| Symbol | Feature rows | Level rows | HTF rows | Unique events | Event candidate rows | Grid labels | Bad ticks excluded | Runtime (s) |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    lines += [f"| {r['symbol']} | {r['features']:,} | {r['levels']:,} | {r['bars']:,} | {r.get('unique_events',0):,} | {r.get('events',0):,} | {r['labels']:,} | {r.get('bad_ticks_excluded',0):,} | {r['runtime_seconds']:.1f} |" for r in results]
    if not results: lines.append("| No production symbol batch completed yet | 0 | 0 | 0 | 0 | 0 | 0 |" )
    lines += ["", "## Events per year", "", "| Symbol | Year | Method | Unique events | Candidate rows |", "|---|---:|---|---:|---:|"]
    event_rows=[row for result in results for row in result.get("event_year_counts",[])]
    lines += [f"| {row['symbol']} | {row['year']} | {row['method']} | {row['unique_events']:,} | {row['candidate_rows']:,} |" for row in event_rows]
    if not event_rows: lines.append("| No events | — | — | 0 | 0 |")
    lines += ["", "## Validation", "", "Rust label/reference agreement is tested on 10,000 seeded randomized cases. Build: PATH=/Users/bfhach/.cargo/bin:$PATH maturin develop --manifest-path rust/msd_kernels/Cargo.toml --offline. pytest summary is recorded at completion.", ""]
    path=Path("reports/data/pipeline_report.md"); path.parent.mkdir(parents=True,exist_ok=True); path.write_text("\n".join(lines))
    return path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", choices=TIER1)
    parser.add_argument("--start-year", type=int)
    parser.add_argument("--end-year", type=int)
    args = parser.parse_args()
    report = []
    for symbol in ((args.symbol,) if args.symbol else TIER1):
        result = run_symbol(symbol, args.start_year, args.end_year)
        report.append(result)
        print(result, flush=True)
    write_pipeline_report(report)
    print(report, flush=True)


if __name__ == "__main__":
    main()
