"""Disk-backed Layer 2–5 processing runner; one bounded calendar-year batch at a time."""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
import inspect
import os
from pathlib import Path
import shutil
import tempfile
import time

import numpy as np
import pandas as pd

from msd.data import load
from .features import build_features, external_feature_frame, feature_qa_files, prepare_feature_cache
from .labels import label_grid, rust_fallback
from .levels import apply_level_invalidations, build_levels
from .timeframes import INDEX_SYMBOLS, TIMEFRAMES, build_all_timeframes
from msd.methods.common import assert_event_volume, exit_candidates, prepare_exit_levels
from msd.methods import (
    bollinger, btc_order_flow, candlestick_at_level, chart_patterns,
    donchian_atr_breakout, dow_trend_confirmation, fib_pullback,
    funding_extreme_fade, fvg_retrace, ichimoku_cloud, intraday_momentum,
    liquidity_sweep, ma_cross, macd_signal, market_structure_pullback,
    order_block_retest, ote_zone, post_earnings_index_reaction,
    post_macro_event_reaction, price_action_h2l2, range_breakout_nr4_nr7,
    round_number_reaction, rsi2_mean_reversion, session_level_reaction,
    sr_touch, stochastic, supply_demand_zone_retest, trend_following,
    trendline_channel, vix_spike_dip_buy, volume_profile_poc_vah_val,
    vwap_reclaim_reject, wyckoff_spring_upthrust,
)

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
# Explicit registry: every frozen detector is considered, then its SYMBOLS
# declaration narrows the instrument scope. Keep pilots in the same path.
METHOD_REGISTRY = (
    bollinger, btc_order_flow, candlestick_at_level, chart_patterns,
    donchian_atr_breakout, dow_trend_confirmation, fib_pullback,
    funding_extreme_fade, fvg_retrace, ichimoku_cloud, intraday_momentum,
    liquidity_sweep, ma_cross, macd_signal, market_structure_pullback,
    order_block_retest, ote_zone, post_earnings_index_reaction,
    post_macro_event_reaction, price_action_h2l2, range_breakout_nr4_nr7,
    round_number_reaction, rsi2_mean_reversion, session_level_reaction,
    sr_touch, stochastic, supply_demand_zone_retest, trend_following,
    trendline_channel, vix_spike_dip_buy, volume_profile_poc_vah_val,
    vwap_reclaim_reject, wyckoff_spring_upthrust,
)


def _check_disk() -> None:
    free=shutil.disk_usage(".").free
    if free<MIN_FREE_BYTES:
        raise OSError(f"Pipeline stopped before writing: only {free/1024**3:.1f} GiB free (65 GiB minimum)")


def methods_for_symbol(symbol: str) -> tuple:
    """Select registered detectors whose declared scope includes an instrument."""
    return tuple(method for method in METHOD_REGISTRY
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


def _merge_levels_year(level_temp: Path, symbol: str, start_year: int, replace_existing: bool = False,
                       state_levels: pd.DataFrame | None = None) -> None:
    """Atomically merge this year's levels with only earlier completed years."""
    target=LEVEL_DIR/f"{symbol}.parquet"
    current=pd.read_parquet(level_temp)
    if target.exists() and not replace_existing:
        previous=pd.read_parquet(target)
        # Older level files had a misleading all-zero touch counter. Touch
        # counts are recomputed from causal price bars by the event detectors.
        previous=previous.drop(columns=["touches_so_far"],errors="ignore")
        current=current.drop(columns=["touches_so_far"],errors="ignore")
        if state_levels is not None and len(previous):
            invalidations=state_levels.loc[state_levels.invalidated_at.notna(),["level_id","invalidated_at"]]
            if len(invalidations):
                state_map=invalidations.drop_duplicates("level_id",keep="last").set_index("level_id").invalidated_at
                updated=previous.level_id.map(state_map)
                previous["invalidated_at"]=updated.combine_first(previous.invalidated_at)
        cutoff=pd.Timestamp(start_year,1,1,tz="UTC")
        previous=previous[pd.to_datetime(previous.known_at,utc=True)<cutoff]
        current=pd.concat([previous,current],ignore_index=True).sort_values("known_at").reset_index(drop=True)
    if "level_id" in current and current.level_id.duplicated().any():
        raise RuntimeError(f"Level ID collision or duplicate identity in full history for {symbol}")
    _check_disk()
    with tempfile.NamedTemporaryFile(dir=LEVEL_DIR,suffix=".parquet",delete=False) as handle:
        merged_temp=Path(handle.name)
    current.to_parquet(merged_temp,index=False,compression="zstd")
    os.replace(merged_temp,target)


def _timeframes_with_history(symbol: str, current: dict[str,pd.DataFrame], year_start: pd.Timestamp) -> dict[str,pd.DataFrame]:
    """Join stored completed HTF bars before the current warm-up window."""
    result={}
    for tf,frame in current.items():
        root=BAR_DIR/f"bars_{tf}"/symbol
        prior_paths=sorted(root.glob("[0-9][0-9][0-9][0-9]-[0-9][0-9].parquet")) if root.exists() else []
        parts=[]
        for path in prior_paths:
            if path.stem >= year_start.strftime("%Y-%m"):
                continue
            old=pd.read_parquet(path)
            if symbol in INDEX_SYMBOLS:
                old=old[pd.to_datetime(old.ts,utc=True)>=CASH_ERA_START]
            if len(old): parts.append(old)
        if len(frame): parts.append(frame)
        if parts:
            result[tf]=(pd.concat(parts,ignore_index=True).sort_values("ts")
                        .drop_duplicates("ts",keep="last").reset_index(drop=True))
        else:
            result[tf]=frame
    return result


def _load_year_level_history(symbol: str, year_start: pd.Timestamp) -> pd.DataFrame:
    path=LEVEL_DIR/f"{symbol}.parquet"
    if not path.exists(): return pd.DataFrame()
    levels=pd.read_parquet(path)
    levels=levels.drop(columns=["touches_so_far"],errors="ignore")
    levels=levels[pd.to_datetime(levels.known_at,utc=True)<year_start]
    if symbol in INDEX_SYMBOLS:
        levels=levels[pd.to_datetime(levels.known_at,utc=True)>=CASH_ERA_START]
    return levels.reset_index(drop=True)


def _save_event_state(symbol: str, year: int, state: dict, touch_rows: list[tuple]) -> None:
    import json
    root=Path("data/state/pipeline")/symbol
    root.mkdir(parents=True,exist_ok=True)
    target=root/f"{year}.json"
    with tempfile.NamedTemporaryFile(mode="w",dir=root,suffix=".json",delete=False) as handle:
        temp=Path(handle.name);json.dump(state,handle,separators=(",",":"))
    os.replace(temp,target)
    if touch_rows:
        touch_root=Path("data/levels/touches")/symbol;touch_root.mkdir(parents=True,exist_ok=True)
        touch_path=touch_root/f"{year}.parquet"
        frame=pd.DataFrame(touch_rows,columns=["method","level_id","touch_ts","known_at"])
        frame=frame.drop_duplicates(["method","level_id","touch_ts","known_at"])
        with tempfile.NamedTemporaryFile(dir=touch_root,suffix=".parquet",delete=False) as handle:
            tmp=Path(handle.name)
        frame.to_parquet(tmp,index=False,compression="zstd");os.replace(tmp,touch_path)


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


def _history_start(symbol: str) -> pd.Timestamp:
    """Earliest permitted source timestamp used to seed cumulative state."""
    if symbol in INDEX_SYMBOLS:
        return CASH_ERA_START
    roots = {
        "BTCUSDT": Path("data/bars/binance_spot/BTCUSDT"),
        "ETHUSDT": Path("data/bars/binance_spot/ETHUSDT"),
        "XAUUSD": Path("data/bars/dukascopy/XAUUSD"),
    }
    files = sorted(roots.get(symbol, Path("data/bars/dukascopy") / symbol).glob("[0-9][0-9][0-9][0-9]-[0-9][0-9].parquet"))
    if not files:
        return pd.Timestamp(_first_year(symbol), 1, 1, tz="UTC")
    first = pd.read_parquet(files[0], columns=["ts"]).ts
    return pd.to_datetime(first, utc=True).min().floor("min")


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
    earnings_csv=Path("data/aux/earnings/sec_8k_item_2_02.csv")
    if earnings_csv.exists():
        try:
            filings=pd.read_csv(earnings_csv)
            if "acceptanceDateTime" in filings:
                stamp=filings.acceptanceDateTime.astype(str).str.replace(r"\.\d+$","",regex=True)
                parsed=pd.to_datetime(stamp,utc=True,errors="coerce")
                compact=stamp.str.fullmatch(r"\d{14}")
                parsed.loc[compact]=pd.to_datetime(stamp.loc[compact],format="%Y%m%d%H%M%S",utc=True,errors="coerce")
                filings["datetime_utc"]=parsed
            elif "filingDate" in filings:
                filings["datetime_utc"]=pd.to_datetime(filings.filingDate,utc=True,errors="coerce")
            if "ticker" in filings:
                filings["event"]="earnings_"+filings.ticker.astype(str).str.lower()
            earnings=pd.concat([earnings,filings],ignore_index=True) if not earnings.empty else filings
        except (OSError,ValueError,pd.errors.ParserError):
            pass
    if not earnings.empty: auxiliary["earnings"]=earnings
    dix=Path("data/aux/squeezemetrics/DIX.parquet")
    if dix.exists(): auxiliary["dix_gex"]=pd.read_parquet(dix)
    for currency in ("BTC","ETH"):
        dvol=_parquet_union(Path("data/aux/dvol")/currency)
        if not dvol.empty: auxiliary[f"dvol_{currency.lower()}"]=dvol
    return auxiliary


def augment_external_feature_store(symbol: str) -> dict:
    """Attach newly downloaded DIX/DVOL/calendar data to existing monthly features."""
    root=FEATURE_DIR/symbol
    files=sorted(root.glob("[0-9][0-9][0-9][0-9]-[0-9][0-9].parquet"))
    if not files: raise FileNotFoundError(f"no monthly feature files for {symbol}: {root}")
    auxiliary=_auxiliary_inputs()
    hourly_root=BAR_DIR/"bars_1h"/symbol
    hourly_files=sorted(hourly_root.glob("*.parquet")) if hourly_root.exists() else []
    hourly=pd.concat([pd.read_parquet(path) for path in hourly_files],ignore_index=True) if hourly_files else pd.DataFrame()
    written=0
    for path in files:
        _check_disk()
        frame=pd.read_parquet(path)
        extra=external_feature_frame(frame.known_at,auxiliary,hourly)
        for column in extra.columns:
            if column!="known_at": frame[column]=pd.to_numeric(extra[column],errors="coerce").astype("float32")
        external_columns=[column for column in extra if column!="known_at"]
        if external_columns: frame[external_columns]=frame[external_columns].replace([np.inf,-np.inf],np.nan)
        temp=path.with_suffix(".tmp.parquet")
        frame.to_parquet(temp,index=False,compression="zstd")
        os.replace(temp,path)
        written+=len(frame)
    qa=feature_qa_files(files,symbol)
    feature_names=[c for c in pd.read_parquet(files[0]).columns if c not in {"ts","known_at"}]
    dictionary=write_feature_dictionary(feature_names)
    return {"symbol":symbol,"months":len(files),"rows":written,"features":len(feature_names),
            "qa":str(qa),"dictionary":str(dictionary)}


def _attach_market_auxiliary(bars: pd.DataFrame, symbol: str) -> pd.DataFrame:
    result=bars
    if symbol not in {"BTCUSDT","ETHUSDT"}: return result
    funding=_parquet_union(Path("data/aux/funding")/symbol)
    if not funding.empty and ("funding_time" in funding or "ts" in funding):
        # Binance funding archive calc_time is the observation/publication
        # timestamp; legacy fundingTime is the settlement instant. Both are
        # joined only at or after that timestamp.
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
        # Binance metrics create_time labels an instantaneous snapshot, not a
        # candle open, so it is available at that timestamp.
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


def _event_feature_frame(bars: pd.DataFrame, timeframes: dict[str,pd.DataFrame]) -> pd.DataFrame:
    """Minimal causal feature columns needed to scan events over warm-up bars."""
    from .features import indicator_frame
    history=bars.sort_values("ts").reset_index(drop=True)
    result=pd.DataFrame({"ts":pd.to_datetime(history.ts,utc=True).astype("datetime64[ns, UTC]"),
                         "known_at":pd.to_datetime(history.ts,utc=True)+pd.Timedelta(minutes=1),
                         "1m_atr14":indicator_frame(history,"1m").atr14.to_numpy(float)})
    for tf, wanted in (("1h",("atr14",)),("1d",("rsi2","ema200_distance_atr"))):
        frame=timeframes.get(tf,pd.DataFrame())
        if frame.empty: continue
        ind=indicator_frame(frame,tf)
        cols=[col for col in wanted if col in ind]
        htf=frame[["known_at"]].copy()
        htf[f"{tf}_bar_known_at"]=pd.to_datetime(frame.known_at,utc=True).to_numpy()
        for col in cols: htf[f"{tf}_{col}"]=ind[col].to_numpy(float)
        result=pd.merge_asof(result.sort_values("known_at"),htf.sort_values("known_at"),
                             on="known_at",direction="backward")
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
        "minutes_": "Minutes since an observed event; minutes_to_* is emitted only for future dates in a pre-published schedule (CPI/NFP/FOMC/GDP/ISM), never for unscheduled actions or EDGAR acceptance times.",
        "cross_": "Other instrument's trailing return as-of its completed bar close.",
        "vix": "Daily Cboe volatility-index observation, available after source close.",
        "dix_": "SqueezeMetrics dealer-positioning series as-of the next New York day after publication.",
        "gex_": "SqueezeMetrics gamma exposure as-of the next New York day after publication.",
        "dvol_": "Deribit DVOL level/change and trailing 24-hour realized-volatility premium, as-of the published observation.",
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
                        *, return_event_counts: bool = False, event_start=None, event_end=None,
                        method_states: dict | None = None, return_states: bool = False,
                        detector_features: pd.DataFrame | None = None,
                        detector_bars: pd.DataFrame | None = None):
    try:
        from msd._msd_kernels import first_hit_batch
    except ImportError as error:
        rust_fallback(error)
        first_hit_batch = None
    methods=methods_for_symbol(symbol)
    instrument_class="index" if symbol in INDEX_SYMBOLS else "crypto" if symbol in {"BTCUSDT","ETHUSDT"} else "index"
    finance=.0002 if symbol in INDEX_SYMBOLS else .0006 if symbol in {"BTCUSDT","ETHUSDT"} else .00015
    event_bars=bars.sort_values("ts").reset_index(drop=True)
    scan_bars=(detector_bars if detector_bars is not None else event_bars).sort_values("ts").reset_index(drop=True)
    scan_features=detector_features if detector_features is not None else features
    atr_map=features.set_index("ts")["1m_atr14"] if "1m_atr14" in features else pd.Series(dtype=float)
    close_mid=(event_bars.bid_c.to_numpy(float)+event_bars.ask_c.to_numpy(float))/2
    ts_pos=pd.Series(np.arange(len(event_bars)),index=event_bars.ts)
    jobs=[]; metadata=[]; detected_counts={}; state_out={}; touch_rows=[]
    prepared_levels=prepare_exit_levels(levels)
    for method in methods:
        method_started=time.perf_counter()
        detector_state=(method_states or {}).get(method.NAME)
        if "return_state" in inspect.signature(method.detect).parameters:
            if return_states:
                events,next_state,method_touches=method.detect(
                    scan_features,levels,scan_bars,state=detector_state,return_state=True)
                state_out[method.NAME]=next_state
                touch_rows.extend(method_touches)
            else:
                events=method.detect(scan_features,levels,scan_bars,state=detector_state)
        else:
            events=method.detect(scan_features,levels,scan_bars)
            if return_states and detector_state is not None:
                state_out[method.NAME]=detector_state
        if event_start is not None:
            events=[event for event in events if pd.Timestamp(event["ts"]) >= pd.Timestamp(event_start)]
        if event_end is not None:
            events=[event for event in events if pd.Timestamp(event["ts"]) < pd.Timestamp(event_end)]
        detected_counts[method.NAME] = len(events)
        if symbol in INDEX_SYMBOLS:
            day_features=scan_features
            if event_start is not None: day_features=day_features[day_features.ts>=pd.Timestamp(event_start)]
            if event_end is not None: day_features=day_features[day_features.ts<pd.Timestamp(event_end)]
            local_event = pd.to_datetime(day_features.ts,utc=True).dt.tz_convert("America/New_York")
            session_day = local_event.dt.tz_localize(None).to_numpy().astype("datetime64[D]")
            session_day += (local_event.dt.hour.to_numpy() >= 18).astype("timedelta64[D]")
            day_count = max(1, len(np.unique(session_day)))
        else:
            day_features=scan_features
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
            entry_type=str(event.get("entry_type","market"))
            limit_price=float(event["limit_price"]) if entry_type=="limit" and event.get("limit_price") is not None else None
            entry=limit_price if limit_price is not None else float(close_mid[int(event_i)])
            atr=float(atr_map.get(event["ts"],np.nan))
            sides=event.get("side_candidates",[event.get("side")])
            for side in sides:
                if side not in (-1,1): continue
                oriented={**event,"side":int(side),"price":entry}
                for candidate in exit_candidates(oriented,levels,atr,prepared_levels):
                    sl,tp=candidate.get("sl"),candidate.get("tp")
                    if sl is None or tp is None or not np.isfinite(sl) or not np.isfinite(tp): continue
                    if int(side)*(entry-float(sl))<=0 or int(side)*(float(tp)-entry)<=0: continue
                    entry_i=int(event_i)+2
                    if entry_i>=len(event_bars): continue
                    from .labels import deadline_after_trading_days
                    deadline=deadline_after_trading_days(event_bars.ts.iloc[entry_i],MAX_HOLD_TRADING_DAYS,instrument_class)
                    class_code=1 if instrument_class in {"crypto","24x7"} else 0
                    expiry=event.get("expiry_at",event.get("expiry_ts")) if limit_price is not None else None
                    expiry_seconds=float(pd.Timestamp(expiry).timestamp()) if expiry is not None else np.nan
                    jobs.extend([int(event_i),int(side),entry,float(sl),float(tp),int(deadline.value//1_000_000_000),
                                 2,finance,limit_price if limit_price is not None else np.nan,expiry_seconds,class_code])
                    metadata.append({**oriented,"exit_kind":candidate["kind"],"sl":float(sl),"tp":float(tp),
                                     "deadline_ts":deadline,"entry_type":entry_type,
                                     "limit_price":limit_price,"expiry_at":expiry if limit_price is not None else None})
    if not jobs:
        empty = pd.DataFrame()
        if return_states:
            return empty, detected_counts, state_out, touch_rows
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
                deadline_ts=event["deadline_ts"],instrument_class=instrument_class,
                limit_price=event.get("limit_price"),expiry_ts=event.get("expiry_at"),detailed=True)
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
    if return_states:
        return result, detected_counts, state_out, touch_rows
    return (result, detected_counts) if return_event_counts else result


def run_symbol(symbol: str, start_year: int | None = None, end_year: int | None = None) -> dict:
    start_year = start_year or _first_year(symbol)
    started = time.perf_counter()
    end_year = min(end_year or datetime.now(timezone.utc).year, datetime.now(timezone.utc).year)
    timeframes_written = features_written = labels_written = events_written = 0
    level_rows=0
    timings=[]
    event_year_counts=[]
    bad_tick_count=0
    replace_levels_pending=not (Path("data/state/pipeline")/symbol/f"{start_year-1}.json").exists()
    for year in range(start_year, end_year+1):
        year_started=time.perf_counter()
        year_start=pd.Timestamp(year,1,1,tz="UTC")
        year_end = pd.Timestamp(year+1, month=1, day=1, tz="UTC")
        state_root=Path("data/state/pipeline")/symbol
        previous_state_path=state_root/f"{year-1}.json"
        bootstrap=not previous_state_path.exists() or not (LEVEL_DIR/f"{symbol}.parquet").exists()
        # First chunk bootstraps from the permitted source start. Later chunks
        # use bounded 370-day price warm-up plus persisted levels, HTF history,
        # and the prior year's exact event-state checkpoint.
        left = _history_start(symbol) if bootstrap else year_start-pd.Timedelta(days=MAX_LOOKBACK_DAYS)
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
        keep=["ts",*[f"{side}_{field}" for side in ("bid","ask") for field in "ohlc"],"volume"]
        keep += [name for name in ("duka_spread","duka_volume","taker_buy_base","trades","quote_volume",
                                    "funding_z20","open_interest","feed","roll") if name in bars]
        bars=bars.loc[:,keep].copy()
        active_bars=bars.loc[_active_mask(bars,symbol)].reset_index(drop=True)
        tfs_current = build_all_timeframes(bars, symbol)
        for tf, frame in tfs_current.items():
            selected=frame[(frame.ts>=year_start)&(frame.ts<year_end)]
            timeframes_written += _write_monthly(selected,BAR_DIR/f"bars_{tf}",symbol)
        tfs=_timeframes_with_history(symbol,tfs_current,year_start)
        prior_levels=pd.DataFrame() if bootstrap else _load_year_level_history(symbol,year_start)
        current_levels=build_levels(active_bars,symbol,tfs).drop(columns=["touches_so_far"],errors="ignore")
        # The final minute of the prior calendar year closes exactly at
        # year_end; levels confirmed at that instant are causal for that row.
        current_levels=current_levels[pd.to_datetime(current_levels.known_at,utc=True)<=year_end]
        if not bootstrap:
            current_levels=current_levels[pd.to_datetime(current_levels.known_at,utc=True)>=year_start]
        if len(current_levels):
            current_levels=current_levels.drop_duplicates(["price","type","timeframe","created_at","known_at","direction"],keep="last")
        levels=pd.concat([prior_levels,current_levels],ignore_index=True,sort=False)
        levels=levels.drop_duplicates(["price","type","timeframe","created_at","known_at","direction"],keep="last")
        levels=apply_level_invalidations(active_bars,levels)
        level_output_start=left if bootstrap else year_start
        year_levels=levels[(pd.to_datetime(levels.known_at,utc=True)>=level_output_start)&
                           (pd.to_datetime(levels.known_at,utc=True)<=year_end)]
        if len(year_levels):
            _check_disk();LEVEL_DIR.mkdir(parents=True,exist_ok=True)
            Path("data/tmp").mkdir(parents=True,exist_ok=True)
            level_temp=Path("data/tmp")/f"levels_year_{symbol}_{year}.parquet"
            year_levels.to_parquet(level_temp,index=False,compression="zstd")
            _merge_levels_year(level_temp,symbol,year,replace_existing=replace_levels_pending,
                               state_levels=levels)
            replace_levels_pending=False
            level_rows+=len(year_levels)
        del year_levels
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
        feature_cache=prepare_feature_cache(bars,symbol,tfs)
        feature_names=None
        month_cursor=year_start
        if symbol in INDEX_SYMBOLS: month_cursor=max(month_cursor,CASH_ERA_START.floor("D"))
        year_feature_rows=year_label_rows=0
        while month_cursor<year_end:
            month_end=min(year_end,month_cursor+pd.offsets.MonthBegin(1))
            features=build_features(bars,symbol,tfs,levels,auxiliary=auxiliary,cross_asset=cross,
                                    output_start=month_cursor,output_end=month_end,cache=feature_cache)
            features=features.replace([np.inf,-np.inf],np.nan)
            if len(features):
                feature_names=features.columns.tolist()
                if feature_names: write_feature_dictionary(feature_names)
                count=_write_monthly(features,FEATURE_DIR,symbol)
                features_written+=count;year_feature_rows+=count
            month_cursor=month_end
        # QA reads a single year's persisted feature chunks after generation,
        # avoiding a year-sized dense feature frame during calculation.
        del feature_cache
        import gc
        gc.collect()
        year_feature_paths=sorted((FEATURE_DIR/symbol).glob(f"{year}-*.parquet"))
        if year_feature_paths: feature_qa_files(year_feature_paths,symbol,append=True)
        gc.collect()
        method_features=_event_feature_frame(bars,tfs)
        method_features=method_features.loc[_active_mask(method_features,symbol)]
        scan_start=left if bootstrap else year_start
        scan_features=method_features[(method_features.ts>=scan_start)&(method_features.ts<year_end)]
        scan_bars=active_bars[(active_bars.ts>=scan_start)&(active_bars.ts<year_end)]
        if bootstrap:
            method_states={}
        elif previous_state_path.exists():
            import json
            method_states=json.loads(previous_state_path.read_text())
        else:
            method_states={}
        events, unique_events, next_states, touch_rows = label_method_events(
            method_features,levels,active_bars,symbol,return_event_counts=True,
            event_start=year_start,event_end=year_end,method_states=method_states,return_states=True,
            detector_features=scan_features,detector_bars=scan_bars)
        next_states["invalidations"]={str(int(row.level_id)):pd.Timestamp(row.invalidated_at).isoformat()
            for row in levels.loc[levels.invalidated_at.notna()&
                (pd.to_datetime(levels.invalidated_at,utc=True)<=year_end)].itertuples(index=False)}
        candidate_counts=events.groupby("method",dropna=False).size() if len(events) else pd.Series(dtype=int)
        methods=methods_for_symbol(symbol)
        yearly_counts=[]
        for method in methods:
            name=method.NAME
            row={"symbol":symbol,"year":year,"method":name,
                 "unique_events":int(unique_events.get(name,0)),
                 "candidate_rows":int(candidate_counts.get(name,0))}
            event_year_counts.append(row);yearly_counts.append(row)
        print({"symbol":symbol,"year":year,"phase":"event_counts",
               "counts":{row["method"]:{"unique_events":row["unique_events"],
                                           "candidate_rows":row["candidate_rows"]}
                         for row in yearly_counts}},flush=True)
        if len(events): events_written+=_write_monthly(events,Path("data/events"),symbol)
        # ATR(1h) is joined by its completed-bar timestamp; no in-progress HTF value is used.
        if not tfs["1h"].empty:
            atr = tfs["1h"][["known_at"]].copy()
            atr["atr"] = __import__("msd.processing.features", fromlist=["indicator_frame"]).indicator_frame(tfs["1h"]).atr14
            per_minute = pd.merge_asof(bars[["ts"]].assign(known_at=bars.ts+pd.Timedelta(minutes=1)).sort_values("known_at"),
                                       atr.sort_values("known_at"), on="known_at", direction="backward").atr
        else:
            per_minute = pd.Series(np.nan, index=bars.index)
        label_started=time.perf_counter()
        instrument_class="index" if symbol in INDEX_SYMBOLS else "crypto" if symbol in {"BTCUSDT","ETHUSDT"} else "index"
        month_cursor=year_start
        if symbol in INDEX_SYMBOLS: month_cursor=max(month_cursor,CASH_ERA_START.floor("D"))
        while month_cursor<year_end:
            month_end=min(year_end,month_cursor+pd.offsets.MonthBegin(1))
            label_mask=(bars.ts>=month_cursor)&(bars.ts<min(right,month_end+pd.Timedelta(days=8)))&_active_mask(bars,symbol)
            label_bars=bars.loc[label_mask].reset_index(drop=True)
            label_atr=per_minute.loc[label_mask].reset_index(drop=True)
            labels=label_grid(label_bars,label_atr,max_trading_days=MAX_HOLD_TRADING_DAYS,
                              instrument_class=instrument_class)
            if len(labels):
                labels["ts"]=label_bars.ts.iloc[labels.signal_index.to_numpy()].to_numpy()
                labels=labels[labels.ts<month_end]
                if len(labels):
                    count=_write_monthly(labels,LABEL_DIR,symbol)
                    labels_written+=count;year_label_rows+=count
            month_cursor=month_end
        elapsed=time.perf_counter()-year_started
        _save_event_state(symbol,year,next_states,touch_rows)
        timings.append((year,len(bars),year_feature_rows,year_label_rows,elapsed))
        print({"symbol":symbol,"year":year,"input_bars":len(bars),"feature_rows":year_feature_rows,
               "event_unique":sum(x["unique_events"] for x in yearly_counts),
               "event_candidate_rows":sum(x["candidate_rows"] for x in yearly_counts),
               "label_rows":year_label_rows,"elapsed_seconds":elapsed},flush=True)
    result={"symbol": symbol, "features": features_written, "levels": level_rows,
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
           "| HTF/level/event warm-up | full permitted source history (replayed for each output year) |", "| Label entry delay | 2 bars after signal bar |", 
           f"| Maximum label holding window | {MAX_HOLD_TRADING_DAYS} weekdays (non-crypto; deadline at first bar open at/after timestamp) or {MAX_HOLD_TRADING_DAYS}×24h (crypto) |", 
           "| Label cadence | every 15 UTC minutes; both sides |", "| S/R touch | level clusters within 0.25 ATR(1h), >=2 touches; edge-trigger within 0.1 ATR, 0.5 ATR re-arm; 4h cooldown |", "| Liquidity sweep | clustered 15m+ levels; 0.1 ATR wick, close-back within 3 bars; 4h cooldown |", "| SL ATR grid | 0.5, 1, 1.5, 2, 3 |", 
           "| TP ATR grid | 0.5, 1, 1.5, 2, 3, 4, 6 |", "| ATR source | 14-period ATR on completed 1h bars |", "",
           "## Output inventory", "", "| Root | Parquet files | Bytes |", "|---|---:|---:|"]
    lines += [f"| {root} | {count:,} | {size:,} |" for root,count,size in inventory]
    lines += ["", "## Registered event methods", "",
              "Every listed module is frozen for this pipeline run; its module docstring records the trigger, stop/target rule, scope and per-method constants.",
              "| Method | Symbol scope |", "|---|---|"]
    for method in METHOD_REGISTRY:
        scope=", ".join(getattr(method,"SYMBOLS",("all instruments",)))
        lines.append(f"| {method.NAME} | {scope} |")
    lines += ["", "## Processing runs", "", "| Symbol | Feature rows | Level rows | HTF rows | Unique events | Event candidate rows | Grid labels | Bad ticks excluded | Runtime (s) | Peak RSS (GiB) |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    lines += [f"| {r['symbol']} | {r['features']:,} | {r['levels']:,} | {r['bars']:,} | {r.get('unique_events',0):,} | {r.get('events',0):,} | {r['labels']:,} | {r.get('bad_ticks_excluded',0):,} | {r['runtime_seconds']:.1f} | {r.get('peak_rss_gib',float('nan')):.2f} |" for r in results]
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
    parser.add_argument("--augment-external", action="store_true", help="attach downloaded external sources to existing feature files only")
    args = parser.parse_args()
    if args.augment_external:
        if not args.symbol: parser.error("--augment-external requires --symbol")
        print(augment_external_feature_store(args.symbol),flush=True)
        return
    report = []
    for symbol in ((args.symbol,) if args.symbol else TIER1):
        result = run_symbol(symbol, args.start_year, args.end_year)
        report.append(result)
        print(result, flush=True)
    write_pipeline_report(report)
    print(report, flush=True)


if __name__ == "__main__":
    main()
