"""Causal higher-timeframe bars stamped at their scheduled open."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

NY = ZoneInfo("America/New_York")
INDEX_SYMBOLS = {"USATECHIDXUSD", "USA500IDXUSD", "USA30IDXUSD", "DEUIDXEUR", "GBRIDXGBP", "JPNIDXJPY", "NSXUSD", "SPXUSD", "GRXEUR"}
TIMEFRAMES = {"5m": 5, "15m": 15, "1h": 60, "4h": 240, "1d": 1440}
BAR_COLUMNS = ["ts", "bid_o", "bid_h", "bid_l", "bid_c", "ask_o", "ask_h", "ask_l", "ask_c", "volume"]
# Dukascopy US index CFDs publish no quotes 16:15-17:00 ET; those minutes are
# never expected inside a bucket.
US_INDEX_QUOTE_GAP_MINUTES = 45
US_INDEX_SYMBOLS = {"USATECHIDXUSD", "USA500IDXUSD", "USA30IDXUSD", "NSXUSD", "SPXUSD"}
# Dukascopy metals pause 17:00-18:00 ET (the NY rollover) every trading day.
METAL_SYMBOLS = {"XAUUSD", "XAGUSD"}
# A minute without ticks has no bar but leaves OHLC unchanged, so an intraday
# bucket is complete once this share of its expected minutes is observed.
MIN_COVERAGE = 0.80


def _session_info(ts: pd.Timestamp, index_market: bool) -> tuple[date, pd.Timestamp, pd.Timestamp]:
    if not index_market:
        start = ts.floor("D")
        return ts.date(), start, start + pd.Timedelta(days=1)
    local = ts.tz_convert(NY)
    day = local.date()
    minute = local.hour * 60 + local.minute
    if minute >= 18 * 60:
        trade_day = day + timedelta(days=1)
        open_day = day
    else:
        trade_day = day
        open_day = day - timedelta(days=1)
    open_ts = pd.Timestamp(datetime.combine(open_day, time(18, 0), tzinfo=NY)).tz_convert("UTC")
    end_ts = pd.Timestamp(datetime.combine(trade_day, time(17, 0), tzinfo=NY)).tz_convert("UTC")
    return trade_day, open_ts, end_ts


def build_timeframe(bars: pd.DataFrame, symbol: str, timeframe: str) -> pd.DataFrame:
    """Aggregate only complete intervals; `known_at` is the interval close."""
    if timeframe not in TIMEFRAMES:
        raise ValueError(timeframe)
    if bars.empty:
        return pd.DataFrame(columns=[*BAR_COLUMNS, "known_at", "observed_minutes", "expected_minutes"])
    minutes = TIMEFRAMES[timeframe]
    index_market = symbol in INDEX_SYMBOLS
    source = bars.sort_values("ts").drop_duplicates("ts").reset_index(drop=True).copy()
    ts = pd.to_datetime(source.ts, utc=True).astype("datetime64[ns, UTC]")
    source["ts"] = ts
    if index_market:
        local = ts.dt.tz_convert(NY)
        minute_of_day, dow = local.dt.hour * 60 + local.dt.minute, local.dt.day_of_week
        active = (((dow >= 0) & (dow <= 3) & ((minute_of_day < 17*60) | (minute_of_day >= 18*60))) |
                  ((dow == 4) & (minute_of_day < 17*60)) | ((dow == 6) & (minute_of_day >= 18*60)))
        source, ts, local, minute_of_day = source.loc[active].copy(), ts.loc[active], local.loc[active], minute_of_day.loc[active]
        trade_day = pd.to_datetime(local.dt.date) + pd.to_timedelta((minute_of_day >= 18*60).astype(int), unit="D")
        open_day = trade_day - pd.Timedelta(days=1)
        session_open = (open_day.dt.tz_localize(NY) + pd.Timedelta(hours=18)).dt.tz_convert("UTC")
        session_end = (trade_day.dt.tz_localize(NY) + pd.Timedelta(hours=17)).dt.tz_convert("UTC")
        elapsed = ((ts - session_open).dt.total_seconds() // 60).astype(np.int64)
        offsets = np.zeros(len(source), dtype=np.int64) if timeframe == "1d" else (elapsed // minutes) * minutes
        bucket_open = session_open + pd.to_timedelta(offsets, unit="m")
        bucket_end = session_end if timeframe == "1d" else (bucket_open + pd.Timedelta(minutes=minutes)).where(
            bucket_open + pd.Timedelta(minutes=minutes) <= session_end, session_end)
        expected_for = ((bucket_end - bucket_open).dt.total_seconds() // 60).astype(np.int64)
        gap_minutes = US_INDEX_QUOTE_GAP_MINUTES if symbol in US_INDEX_SYMBOLS else 0
        gap_start = session_end - pd.Timedelta(minutes=gap_minutes)
        overlap = ((bucket_end - np.maximum(bucket_open, gap_start)).dt.total_seconds() // 60).clip(lower=0)
        effective_for = expected_for - overlap.astype(np.int64)
        expected = None
    else:
        day_open = ts.dt.floor("D")
        elapsed = ((ts - day_open).dt.total_seconds() // 60).astype(np.int64)
        offsets = np.zeros(len(source), dtype=np.int64) if timeframe == "1d" else (elapsed // minutes) * minutes
        bucket_open = day_open + pd.to_timedelta(offsets, unit="m")
        expected = 1440 if timeframe == "1d" else minutes
        expected_for = np.full(len(source), expected, dtype=np.int64)
        effective_for = expected_for
        if symbol in METAL_SYMBOLS:
            bucket_end = bucket_open + pd.Timedelta(minutes=expected)
            break_start = (bucket_open.dt.tz_convert(NY).dt.tz_localize(None).dt.normalize()
                           + pd.Timedelta(hours=17)).dt.tz_localize(NY).dt.tz_convert("UTC")
            break_end = break_start + pd.Timedelta(hours=1)
            overlap = ((np.minimum(bucket_end, break_end) - np.maximum(bucket_open, break_start))
                       .dt.total_seconds() // 60).clip(lower=0)
            effective_for = expected_for - overlap.astype(np.int64).to_numpy()
    if source.empty:
        return pd.DataFrame(columns=[*BAR_COLUMNS, "known_at", "observed_minutes", "expected_minutes"])
    source["_bucket"] = bucket_open.to_numpy()
    source["_expected"] = expected_for
    source["_effective"] = np.asarray(effective_for, dtype=np.int64)
    source["_source_ts"] = ts.to_numpy()
    grouped = source.groupby("_bucket", sort=True)
    agg = {"_source_ts": ["count", "min", "max"], "_expected": "first", "_effective": "first"}
    for side in ("bid", "ask"):
        agg.update({f"{side}_o": "first", f"{side}_h": "max", f"{side}_l": "min", f"{side}_c": "last"})
    if "feed" in source:
        agg["feed"] = ["first", "nunique"]
    if "roll" in source:
        agg["roll"] = lambda values: bool(values.fillna(False).any())
    if "volume" in source:
        agg["volume"] = lambda x: x.sum(min_count=1)
    result = grouped.agg(agg)
    result.columns = ["_".join(col).rstrip("_") if isinstance(col, tuple) else col for col in result.columns]
    rename = {}
    for side in ("bid", "ask"):
        rename.update({f"{side}_o_first": f"{side}_o", f"{side}_h_max": f"{side}_h",
                       f"{side}_l_min": f"{side}_l", f"{side}_c_last": f"{side}_c"})
    result = result.rename(columns=rename)
    count, first, last = result["_source_ts_count"], result["_source_ts_min"], result["_source_ts_max"]
    expected_values = result["_expected_first"].astype(int)
    if timeframe == "1d" and index_market:
        # Dukascopy's recurring pre-close quote gap ends around 16:15 ET,
        # before the CME session closes at 17:00. Treat a well-covered session
        # as complete at the scheduled close so daily features become
        # available at 17:00, not at the next quote after the daily break.
        scheduled_end = pd.to_datetime(result.index, utc=True) + pd.to_timedelta(expected_values.to_numpy(), unit="m")
        complete = ((count >= np.ceil(expected_values * 0.90)) &
                    (last >= scheduled_end - pd.Timedelta(hours=1)) &
                    (first < scheduled_end))
    else:
        effective_values = result["_effective_first"].astype(int)
        scheduled_end = pd.to_datetime(result.index, utc=True) + pd.to_timedelta(expected_values.to_numpy(), unit="m")
        # Partial coverage is accepted only for buckets the input has passed,
        # so a truncated history never emits a bar the full history changes.
        input_end = ts.max() + pd.Timedelta(minutes=1)
        complete = ((effective_values > 0) & (count >= np.ceil(effective_values * MIN_COVERAGE))
                    & ((count == expected_values) | (scheduled_end <= input_end)))
    if "feed_nunique" in result:
        complete &= result["feed_nunique"].eq(1)
    result = result.loc[complete]
    if "feed_first" in result:
        result = result.rename(columns={"feed_first":"feed"}).drop(columns="feed_nunique")
    roll_col=next((column for column in result.columns if str(column).startswith("roll_")),None)
    if roll_col is not None:
        result=result.rename(columns={roll_col:"roll"})
    opened = pd.to_datetime(result.index, utc=True)
    end_minutes = expected_values.loc[complete].to_numpy()
    observed_minutes = count.loc[complete].to_numpy()
    result.insert(0, "ts", opened)
    result["known_at"] = opened + pd.to_timedelta(end_minutes, unit="m")
    result["observed_minutes"] = observed_minutes
    result["expected_minutes"] = end_minutes
    volume_col = next((c for c in result.columns if c.startswith("volume_")), None)
    if volume_col:
        result = result.rename(columns={volume_col: "volume"})
    elif "volume" not in result:
        result["volume"] = np.nan
    result["ts"]=pd.to_datetime(result.ts,utc=True).astype("datetime64[ns, UTC]")
    result["known_at"]=pd.to_datetime(result.known_at,utc=True).astype("datetime64[ns, UTC]")
    columns=[*BAR_COLUMNS, "known_at", "observed_minutes", "expected_minutes"]
    if "feed" in result and "feed" not in columns: columns.append("feed")
    if "roll" in result: columns.append("roll")
    return result[columns].reset_index(drop=True)


def build_all_timeframes(bars: pd.DataFrame, symbol: str) -> dict[str, pd.DataFrame]:
    return {name: build_timeframe(bars, symbol, name) for name in TIMEFRAMES}
