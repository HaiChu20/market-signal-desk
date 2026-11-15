"""Causal dev-period preparation shared by batch-2 strategies."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from msd.live.strategies.us_calendar import skip_day
from msd.research.tiktok import common

NY = ZoneInfo("America/New_York")
DEV_START = pd.Timestamp("2019-01-01", tz="UTC")
DEV_END = pd.Timestamp("2023-01-01", tz="UTC")
WARMUP_START = pd.Timestamp("2018-01-01", tz="UTC")


def _atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> np.ndarray:
    tr = np.empty(len(close), dtype=float)
    tr[:] = np.nan
    if not len(close):
        return tr
    tr[0] = high[0] - low[0]
    if len(close) > 1:
        tr[1:] = np.maximum.reduce((high[1:] - low[1:],
                                    np.abs(high[1:] - close[:-1]),
                                    np.abs(low[1:] - close[:-1])))
    return pd.Series(tr).ewm(alpha=1 / period, adjust=False, min_periods=period).mean().to_numpy()


@dataclass
class PreparedData:
    market: str
    bars: pd.DataFrame
    ts: pd.DatetimeIndex
    ny: pd.DatetimeIndex
    local_minutes: np.ndarray
    mid_o: np.ndarray
    mid_h: np.ndarray
    mid_l: np.ndarray
    mid_c: np.ndarray
    atr1: np.ndarray
    atr15_at: np.ndarray
    ema15_20_at: np.ndarray
    ema15_50_at: np.ndarray
    daily_ema20: dict[date, float]
    rth_days: pd.DataFrame
    pdh: dict[date, float]
    pdl: dict[date, float]
    globex_high: dict[date, float]
    globex_low: dict[date, float]
    asia_high: dict[date, float]
    asia_low: dict[date, float]
    london_high: dict[date, float]
    london_low: dict[date, float]
    midnight_open: dict[date, float]
    five: pd.DataFrame
    fifteen: pd.DataFrame

    def index_at(self, stamp) -> int:
        return int(self.ts.searchsorted(pd.Timestamp(stamp).tz_convert("UTC")))

    def force_flat_index(self, day: date) -> int:
        end = pd.Timestamp(datetime.combine(day, time(16), NY)).tz_convert("UTC")
        return min(len(self.ts), int(self.ts.searchsorted(end)))


def _session_table(frame: pd.DataFrame, market: str) -> tuple[pd.DataFrame, dict, dict]:
    ny = pd.DatetimeIndex(frame.ts).tz_convert(NY)
    local_day = np.asarray(ny.date, dtype=object)
    minutes = ny.hour * 60 + ny.minute
    mask = (minutes >= 9 * 60 + 30) & (minutes < 16 * 60)
    rows = []
    rth = {}
    mid_high = (frame.bid_h.to_numpy(float) + frame.ask_h.to_numpy(float)) / 2
    mid_low = (frame.bid_l.to_numpy(float) + frame.ask_l.to_numpy(float)) / 2
    mid_open = (frame.bid_o.to_numpy(float) + frame.ask_o.to_numpy(float)) / 2
    mid_close = (frame.bid_c.to_numpy(float) + frame.ask_c.to_numpy(float)) / 2
    candidates = []
    day = min(local_day)
    last_day = max(local_day)
    while day <= last_day:
        if day.weekday() < 5:
            candidates.append(day)
        day += timedelta(days=1)
    rth_indices = np.flatnonzero(mask)
    rth_local_days = local_day[rth_indices]
    observed_days, starts = np.unique(rth_local_days, return_index=True)
    grouped = {}
    for group_i, observed_day in enumerate(observed_days):
        left = int(starts[group_i])
        right = int(starts[group_i + 1]) if group_i + 1 < len(starts) else len(rth_indices)
        grouped[observed_day] = rth_indices[left:right]
    for day in candidates:
        idx = grouped.get(day, np.empty(0, dtype=int))
        stamps = ny[idx]
        reason = "holiday_or_half_day" if skip_day(day) else ""
        if not len(idx):
            reason = reason or "no_rth_data"
        elif reason:
            pass
        elif stamps[0].hour != 9 or stamps[0].minute != 30 or stamps[-1].hour != 15 or stamps[-1].minute != 59:
            reason = "incomplete_rth"
        elif len(idx) > 1 and frame.ts.iloc[idx].diff().dt.total_seconds().max() > 6 * 60:
            reason = "gap_over_5m"
        complete = not reason
        rows.append({"day": day, "complete": complete, "skip_reason": reason,
                     "first_i": int(idx[0]) if len(idx) else -1,
                     "last_i": int(idx[-1]) + 1 if len(idx) else -1,
                     "open": float(mid_open[idx[0]]) if len(idx) else np.nan,
                     "high": float(np.max(mid_high[idx])) if len(idx) else np.nan,
                     "low": float(np.min(mid_low[idx])) if len(idx) else np.nan,
                     "close": float(mid_close[idx[-1]]) if len(idx) else np.nan,
                     "bars": len(idx)})
        if complete:
            rth[day] = idx
    return pd.DataFrame(rows), rth, {"day": local_day, "minute": minutes}


def _window_extremes(ts_ny: pd.DatetimeIndex, high: np.ndarray, low: np.ndarray,
                     start_time: time, end_time: time, *, previous_day: bool = False) -> tuple[dict, dict]:
    days = np.asarray(ts_ny.date, dtype=object)
    mins = ts_ny.hour * 60 + ts_ny.minute
    start_min, end_min = start_time.hour * 60 + start_time.minute, end_time.hour * 60 + end_time.minute
    result_hi, result_lo = {}, {}
    observed, starts = np.unique(days, return_index=True)
    indices = {}
    for group_i, observed_day in enumerate(observed):
        left = int(starts[group_i])
        right = int(starts[group_i + 1]) if group_i + 1 < len(starts) else len(days)
        indices[observed_day] = np.arange(left, right)
    for day in observed:
        prior = day - timedelta(days=1) if previous_day else day
        if start_min < end_min:
            candidate = indices.get(prior, np.empty(0, dtype=int))
            idx = candidate[(mins[candidate] >= start_min) & (mins[candidate] < end_min)]
        else:
            left = indices.get(prior, np.empty(0, dtype=int))
            right = indices.get(day, np.empty(0, dtype=int))
            left = left[mins[left] >= start_min]
            right = right[mins[right] < end_min]
            idx = np.r_[left, right]
        if len(idx):
            result_hi[day], result_lo[day] = float(high[idx].max()), float(low[idx].min())
    return result_hi, result_lo


def prepare(bars_1m: pd.DataFrame, market: str, *, allow_holdout: bool = False,
            selection_path=None) -> PreparedData:
    """Build arrays and day/session features; the default boundary is dev-only."""
    if market not in {"USATECHIDXUSD", "USA500IDXUSD"}:
        raise ValueError("batch-2 W1 supports NQ and ES only")
    if allow_holdout and (selection_path is None or not Path(selection_path).is_file()):
        raise FileNotFoundError("holdout preparation requires an existing frozen dev selection file")
    frame = bars_1m.copy()
    frame["ts"] = pd.to_datetime(frame.ts, utc=True)
    frame = frame.sort_values("ts").drop_duplicates("ts", keep="last").reset_index(drop=True)
    if frame.empty or frame.ts.min() < WARMUP_START or (not allow_holdout and frame.ts.max() >= DEV_END):
        raise ValueError("prepared data must be nonempty and contain no holdout bars without authorization")
    ts = pd.DatetimeIndex(frame.ts)
    ny = ts.tz_convert(NY)
    # DatetimeIndex.hour/minute converts the full UTC index to local time on
    # every property access. Cache the minute-of-day once; strategies index it
    # repeatedly while testing every grid cell.
    local_minutes = ny.hour.to_numpy(dtype=np.int16) * 60 + ny.minute.to_numpy(dtype=np.int16)
    mids = {f: (frame[f"bid_{f}"].to_numpy(float) + frame[f"ask_{f}"].to_numpy(float)) / 2
            for f in "ohlc"}
    atr1 = _atr(mids["h"], mids["l"], mids["c"])
    fifteen = common.resample_closed_bars(frame, 15)
    mid15 = {f: (fifteen[f"bid_{f}"].to_numpy(float) + fifteen[f"ask_{f}"].to_numpy(float)) / 2
             for f in "ohlc"}
    atr15 = _atr(mid15["h"], mid15["l"], mid15["c"])
    close15 = pd.Series(mid15["c"])
    e20 = close15.ewm(span=20, adjust=False, min_periods=20).mean().to_numpy()
    e50 = close15.ewm(span=50, adjust=False, min_periods=50).mean().to_numpy()
    # A value is available at a 1m entry only after the corresponding 15m close.
    atr15_at = np.full(len(frame), np.nan)
    ema20_at = np.full(len(frame), np.nan)
    ema50_at = np.full(len(frame), np.nan)
    close_ns = pd.DatetimeIndex(fifteen.ts).asi8
    known = np.searchsorted(close_ns, ts.asi8, side="right") - 1
    available = known >= 0
    atr15_at[available] = atr15[known[available]]
    ema20_at[available] = e20[known[available]]
    ema50_at[available] = e50[known[available]]
    rth_days, complete_idx, _ = _session_table(frame, market)
    daily_ema = {}
    if not rth_days.empty:
        complete = rth_days[rth_days.complete].sort_values("day")
        ema = complete.close.ewm(span=20, adjust=False, min_periods=20).mean()
        daily_ema = dict(zip(complete.day, ema))
    pdh, pdl = {}, {}
    ordered_days = list(rth_days.sort_values("day").itertuples())
    for i, row in enumerate(ordered_days):
        if i:
            prior = next((x for x in reversed(ordered_days[:i]) if x.complete), None)
            if prior is not None:
                pdh[row.day], pdl[row.day] = float(prior.high), float(prior.low)
    globex_hi, globex_lo = _window_extremes(ny, mids["h"], mids["l"], time(18), time(17), previous_day=True)
    asia_hi, asia_lo = _window_extremes(ny, mids["h"], mids["l"], time(18), time(0), previous_day=True)
    london_hi, london_lo = _window_extremes(ny, mids["h"], mids["l"], time(2), time(5))
    midnight = {}
    for day in set(ny.date):
        at = pd.Timestamp(datetime.combine(day, time(0), NY)).tz_convert("UTC")
        ix = int(ts.searchsorted(at))
        if ix < len(ts) and ny[ix].date() == day and ny[ix].hour == 0 and ny[ix].minute == 0:
            midnight[day] = float(mids["o"][ix])
    five = common.resample_closed_bars(frame, 5)
    return PreparedData(market, frame, ts, ny, local_minutes, *[mids[f] for f in "ohlc"], atr1,
                        atr15_at, ema20_at, ema50_at, daily_ema, rth_days,
                        pdh, pdl, globex_hi, globex_lo, asia_hi, asia_lo,
                        london_hi, london_lo, midnight, five, fifteen)


def load_dev(market: str) -> PreparedData:
    bars = common.load_1m(market, start=WARMUP_START, end=DEV_END)
    return prepare(bars, market)
