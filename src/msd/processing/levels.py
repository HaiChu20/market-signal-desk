"""Causal structural levels and as-of snapshots."""
from __future__ import annotations

from bisect import bisect_left, bisect_right
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from .timeframes import INDEX_SYMBOLS

LEVEL_COLUMNS = ["level_id", "price", "type", "timeframe", "created_at", "known_at", "touches_so_far", "invalidated_at", "strength", "direction"]
PIVOT_TFS = ("5m", "15m", "1h", "4h", "1d")
PIVOT_K = (3, 5)
NY = ZoneInfo("America/New_York")
LEVEL_INVALIDATION_ATR = 0.25
PROFILE_BINS = 100
PROFILE_VALUE_FRACTION = 0.70
BASE_BARS = 3
BASE_RANGE_ATR = 0.50
IMPULSE_RANGE_ATR = 2.0
ATR_PERIOD = 14
ROUND_STEPS = {"USATECHIDXUSD": 100, "NSXUSD": 100, "USA500IDXUSD": 25, "SPXUSD": 25,
               "XAUUSD": 50, "XAGUSD": 5, "BTCUSDT": 1000, "ETHUSDT": 100}


def levels_asof(levels: pd.DataFrame, t, level_ids=None) -> pd.DataFrame:
    """Return only level state that was known at UTC time ``t``.

    A state-history table may contain multiple rows per level with ``state_at``
    timestamps. In that case the latest state at or before ``t`` is selected.
    Base level tables without ``state_at`` are filtered by their confirmation
    ``known_at``. In both cases levels already invalidated by ``t`` are omitted.
    ``level_ids`` optionally narrows the snapshot for event-detector use.
    """
    if levels is None or levels.empty:
        return pd.DataFrame(columns=levels.columns if levels is not None else LEVEL_COLUMNS)
    cutoff = pd.Timestamp(t)
    cutoff = cutoff.tz_localize("UTC") if cutoff.tzinfo is None else cutoff.tz_convert("UTC")
    result = levels
    if level_ids is not None:
        ids = np.asarray(list(level_ids))
        if not len(ids):
            return levels.iloc[0:0].copy()
        result = result[result.level_id.isin(ids)]
    state_column = "state_at" if "state_at" in result else "known_at"
    if "state_at" not in result and "touches_so_far" in result:
        touches = pd.to_numeric(result.touches_so_far, errors="coerce").fillna(0)
        if touches.gt(0).any():
            raise ValueError("Nonzero touches_so_far requires per-touch state_at snapshots")
    confirmed = pd.to_datetime(result.known_at, utc=True).le(cutoff)
    result = result.loc[confirmed].copy()
    if result.empty:
        return result
    state = pd.to_datetime(result[state_column], utc=True)
    result = result.loc[state.le(cutoff)].copy()
    if result.empty:
        return result
    if "state_at" in result and "level_id" in result:
        result = (result.sort_values(["state_at", "level_id"], kind="stable")
                  .drop_duplicates("level_id", keep="last"))
    if "invalidated_at" in result:
        invalid = pd.to_datetime(result.invalidated_at, utc=True, errors="coerce")
        result = result.loc[invalid.isna() | invalid.gt(cutoff)].copy()
    return result.reset_index(drop=True)


def pivot_events(frame: pd.DataFrame, k: int, timeframe: str) -> pd.DataFrame:
    """Confirm centered pivots at the close of the kth right-hand bar."""
    if len(frame) < 2 * k + 1:
        return pd.DataFrame(columns=["price", "type", "timeframe", "created_at", "known_at", "direction"])
    highs, lows = frame.bid_h.to_numpy(float), frame.bid_l.to_numpy(float)
    try:
        from msd._msd_kernels import pivots
        candidates = pivots(highs.tolist(), lows.tolist(), int(k))
    except ImportError:
        candidates = []
        for center in range(k, len(frame) - k):
            if highs[center] == np.max(highs[center-k:center+k+1]):
                candidates.append((center, 1))
            if lows[center] == np.min(lows[center-k:center+k+1]):
                candidates.append((center, -1))
    rows = []
    for center, direction in candidates:
        right = center + k
        if direction > 0:
            rows.append((highs[center], "swing_high", timeframe, frame.ts.iloc[center], frame.known_at.iloc[right], -1))
        else:
            rows.append((lows[center], "swing_low", timeframe, frame.ts.iloc[center], frame.known_at.iloc[right], 1))
    return pd.DataFrame(rows, columns=["price", "type", "timeframe", "created_at", "known_at", "direction"])


def _period_levels(daily: pd.DataFrame, symbol: str) -> list[pd.DataFrame]:
    output = []
    if daily.empty:
        return output
    daily = daily.sort_values("ts").reset_index(drop=True)
    local = daily.ts.dt.tz_convert("America/New_York") + pd.Timedelta(hours=6)
    local_day = local.dt.date
    iso = local.dt.isocalendar()
    groups = (("day", list(local_day)),
              ("week", list(zip(iso.year.to_numpy(), iso.week.to_numpy()))),
              ("month", list(zip(local.dt.year.to_numpy(), local.dt.month.to_numpy()))))

    def add_levels(period: str, previous: dict) -> None:
        known = previous["known_at"]
        output.append(pd.DataFrame([
            {"price": previous["high"], "type": f"prior_{period}_high", "timeframe": "1d", "created_at": known, "known_at": known, "direction": -1, "strength": 1.0},
            {"price": previous["low"], "type": f"prior_{period}_low", "timeframe": "1d", "created_at": known, "known_at": known, "direction": 1, "strength": 1.0},
        ]))

    for period, keys in groups:
        key_series=pd.Series(keys,dtype=object)
        buckets = key_series.ne(key_series.shift()).cumsum().to_numpy()
        grouped = daily.groupby(buckets, sort=True)
        previous = None
        for _, group in grouped:
            current = {"high": group.bid_h.max(), "low": group.bid_l.min(), "known_at": group.known_at.max()}
            if period == "day":
                # A complete daily bar itself confirms the prior-day levels;
                # waiting for the next completed daily bar made truncations
                # lose levels that were already known at the day close.
                add_levels(period, current)
            elif symbol in {"BTCUSDT", "ETHUSDT"}:
                day = pd.Timestamp(group.ts.iloc[-1]).date()
                if (period == "week" and day.weekday() == 6) or (
                        period == "month" and day.day == (pd.Timestamp(day) + pd.offsets.MonthEnd(0)).day):
                    add_levels(period, current)
            elif previous is not None:
                add_levels(period, previous)
            previous = current
    return output


def _cme_session_levels(bars: pd.DataFrame) -> list[pd.DataFrame]:
    if bars.empty:
        return []
    local = bars.ts.dt.tz_convert(NY)
    minute = local.dt.hour * 60 + local.dt.minute
    trade_day = [d + timedelta(days=1) if m >= 18*60 else d for d, m in zip(local.dt.date, minute)]
    work = bars.copy(); work["trade_day"] = trade_day; work["local_minute"] = minute
    rows = []
    for day, session in work.groupby("trade_day", sort=True):
        prev_day = day - timedelta(days=1)
        overnight = session[(session.local_minute >= 18*60) | (session.local_minute < 9*60+30)]
        at_open = session[session.local_minute >= 9*60+30]
        known_open = pd.Timestamp(datetime.combine(day, time(9, 30), tzinfo=NY)).tz_convert("UTC")
        if len(overnight):
            rows += [(overnight.bid_h.max(), "overnight_high", "1m", known_open, known_open, -1, 1.0),
                     (overnight.bid_l.min(), "overnight_low", "1m", known_open, known_open, 1, 1.0)]
        opening = at_open[(at_open.local_minute >= 570) & (at_open.local_minute < 585)]
        known_or = pd.Timestamp(datetime.combine(day, time(9, 45), tzinfo=NY)).tz_convert("UTC")
        if len(opening) == 15:
            rows += [(opening.bid_h.max(), "opening_range_high_15m", "15m", known_or, known_or, -1, 1.0),
                     (opening.bid_l.min(), "opening_range_low_15m", "15m", known_or, known_or, 1, 1.0)]
    if not rows:
        return []
    return [pd.DataFrame(rows, columns=["price", "type", "timeframe", "created_at", "known_at", "direction", "strength"])]


def _round_levels(bars: pd.DataFrame, symbol: str) -> pd.DataFrame:
    step = ROUND_STEPS.get(symbol)
    if not step or bars.empty:
        return pd.DataFrame()
    rows = []
    seen: set[float] = set()
    lo_seen, hi_seen = np.inf, -np.inf
    for row in bars.itertuples(index=False):
        old_lo, old_hi = lo_seen, hi_seen
        lo_seen, hi_seen = min(lo_seen, float(row.bid_l)), max(hi_seen, float(row.bid_h))
        lo = np.floor(lo_seen / step) * step
        hi = np.ceil(hi_seen / step) * step
        if old_lo == np.inf:
            candidates = np.arange(lo, hi + step, step)
        else:
            old_lo_rounded, old_hi_rounded = np.floor(old_lo / step) * step, np.ceil(old_hi / step) * step
            candidates = np.r_[np.arange(lo, old_lo_rounded, step), np.arange(old_hi_rounded + step, hi + step, step)]
        for price in candidates:
            if price not in seen:
                seen.add(float(price))
                known = row.ts + pd.Timedelta(minutes=1)
                rows.append((price, "round_number", "all", known, known, 0, 0.5))
    return pd.DataFrame(rows, columns=["price", "type", "timeframe", "created_at", "known_at", "direction", "strength"])


def _vwap_snapshots(bars: pd.DataFrame, symbol: str) -> pd.DataFrame:
    volume_col = "duka_volume" if "duka_volume" in bars and bars.duka_volume.notna().any() else "volume"
    if bars.empty or volume_col not in bars or not bars[volume_col].notna().any():
        return pd.DataFrame()
    local = bars.ts.dt.tz_convert(NY if symbol in INDEX_SYMBOLS else "UTC")
    if symbol in INDEX_SYMBOLS:
        trade_day = [d + timedelta(days=1) if h >= 18 else d for d, h in zip(local.dt.date, local.dt.hour)]
        keys = np.asarray(trade_day)
    else:
        keys = local.dt.date.to_numpy()
    mid = (bars.bid_c.to_numpy(float) + bars.ask_c.to_numpy(float)) / 2
    volume = bars[volume_col].to_numpy(float)
    # Cumsum each contiguous session independently to preserve the original
    # floating-point accumulation order while avoiding per-row pandas access.
    starts = np.r_[0, np.flatnonzero(keys[1:] != keys[:-1]) + 1]
    ends = np.r_[starts[1:], len(bars)]
    vwap = np.full(len(bars), np.nan)
    for start, end in zip(starts, ends):
        v = volume[start:end]
        pv = mid[start:end] * v
        cumulative_volume = np.cumsum(np.where(np.isfinite(v), v, 0.0))
        cumulative_pv = np.cumsum(np.where(np.isfinite(pv), pv, 0.0))
        vwap[start:end] = np.divide(cumulative_pv, cumulative_volume,
                                    out=np.full(end-start, np.nan), where=cumulative_volume > 0)
    valid = np.isfinite(vwap)
    created = bars.ts.array[valid]
    return pd.DataFrame({
        "price": vwap[valid], "type": "session_vwap", "timeframe": "1m",
        "created_at": created, "known_at": created + pd.Timedelta(minutes=1),
        "direction": np.zeros(valid.sum(), dtype=np.int64),
        "strength": np.full(valid.sum(), 0.25),
    })


def _with_volume_profile(daily: pd.DataFrame, bars: pd.DataFrame, symbol: str) -> pd.DataFrame:
    volume_col = "duka_volume" if "duka_volume" in bars and bars.duka_volume.notna().any() else "volume"
    if daily.empty or bars.empty or volume_col not in bars or not bars[volume_col].notna().any():
        return pd.DataFrame()
    if bars.ts.dt.tz is None:
        stamps = pd.to_datetime(bars.ts, utc=True)
    else:
        stamps = bars.ts
    if len(daily) and str(daily.ts.dt.tz) == "UTC":
        if symbol in INDEX_SYMBOLS:
            local = stamps.dt.tz_convert(NY)
            minute = local.dt.hour*60+local.dt.minute
            day_key = pd.Series(local.dt.date.to_numpy(), index=bars.index) + pd.to_timedelta((minute>=18*60).astype(int),unit="D")
            daily_local = daily.ts.dt.tz_convert(NY)
            daily_key = pd.Series(daily_local.dt.date.to_numpy(), index=daily.index)+pd.Timedelta(days=1)
        else:
            day_key = stamps.dt.floor("D")
            daily_key = daily.ts.dt.floor("D")
    else:
        day_key = stamps.dt.floor("D")
        daily_key = daily.ts.dt.floor("D")
    known_by_day = dict(zip(daily_key, daily.known_at))
    rows = []
    for _, day in bars.groupby(day_key, sort=True):
        volumes = day[volume_col].to_numpy(float)
        if not np.isfinite(volumes).any() or np.nansum(volumes) <= 0:
            continue
        price = ((day.bid_c + day.ask_c) / 2).to_numpy(float)
        lo, hi = np.nanmin(price), np.nanmax(price)
        edges = np.linspace(lo, hi + 1e-9, PROFILE_BINS)
        profile, _ = np.histogram(price, bins=edges, weights=np.nan_to_num(volumes))
        centers = (edges[:-1] + edges[1:]) / 2
        poc_i = int(np.argmax(profile)); target = PROFILE_VALUE_FRACTION * profile.sum(); left = right = poc_i; total = profile[poc_i]
        while total < target and (left > 0 or right < len(profile)-1):
            choose_left = left > 0 and (right == len(profile)-1 or profile[left-1] >= profile[right+1])
            if choose_left: left -= 1; total += profile[left]
            else: right += 1; total += profile[right]
        key = day_key.iloc[day.index[0]]
        # Volume profiles are prior-day levels, so a partial current session
        # must not be emitted as a complete profile during truncated builds.
        known = known_by_day.get(key)
        if known is None:
            continue
        for value, kind in ((centers[poc_i], "prior_day_poc"), (edges[left], "prior_day_val"), (edges[right+1], "prior_day_vah")):
            rows.append((value, kind, "1d", known, known, 0, 1.0))
    return pd.DataFrame(rows, columns=["price", "type", "timeframe", "created_at", "known_at", "direction", "strength"])


def _supply_demand_zones(bars: pd.DataFrame) -> pd.DataFrame:
    """Confirm a 3-bar quiet base only when a >2 ATR impulse closes away from it."""
    if len(bars) < 17:
        return pd.DataFrame()
    high, low, close = (bars[c].to_numpy(float) for c in ("bid_h", "bid_l", "bid_c"))
    prev = np.r_[np.nan, close[:-1]]
    tr = np.nanmax(np.column_stack([high-low, np.abs(high-prev), np.abs(low-prev)]), axis=1)
    atr = pd.Series(tr).rolling(ATR_PERIOD, min_periods=ATR_PERIOD).mean().to_numpy()
    ranges = high-low
    rows = []
    for i in range(16, len(bars)):
        a = atr[i]
        if not np.isfinite(a) or a <= 0 or ranges[i] <= IMPULSE_RANGE_ATR*a:
            continue
        base = slice(i-BASE_BARS, i)
        if not np.all(ranges[base] < BASE_RANGE_ATR*a):
            continue
        base_high, base_low = float(high[base].max()), float(low[base].min())
        if close[i] > base_high:
            kind, direction = "demand_zone_edge", 1
        elif close[i] < base_low:
            kind, direction = "supply_zone_edge", -1
        else:
            continue
        created, known = bars.ts.iloc[i-3], bars.ts.iloc[i]+pd.Timedelta(minutes=1)
        rows.extend([(base_low, kind, "1m", created, known, direction, 0.75),
                     (base_high, kind, "1m", created, known, direction, 0.75)])
    return pd.DataFrame(rows, columns=["price", "type", "timeframe", "created_at", "known_at", "direction", "strength"])


def _touch_updates(bars: pd.DataFrame, levels: pd.DataFrame) -> pd.DataFrame:
    """Reference tracker: append snapshots only at causal touch/invalidation events."""
    if bars.empty or levels.empty:
        return pd.DataFrame(columns=LEVEL_COLUMNS)
    rows = []
    for level_id, level in enumerate(levels.itertuples(index=False)):
        price, known = float(level.price), pd.Timestamp(level.known_at)
        start = int(bars.ts.searchsorted(known, side="left"))
        touched_count = 0
        invalidated = pd.NaT
        was_touching = False
        for i in range(start, len(bars)):
            bar = bars.iloc[i]
            touching = float(bar.bid_l) <= price <= float(bar.bid_h)
            if touching and not was_touching:
                touched_count += 1
                rows.append((level_id, price, level.type, level.timeframe, level.created_at, bar.ts + pd.Timedelta(minutes=1), touched_count,
                             invalidated, float(getattr(level, "strength", 1.0)), int(getattr(level, "direction", 0))))
            was_touching = touching
            direction = int(getattr(level, "direction", 0))
            atr = float(bar.get("atr", 0.0)) if isinstance(bar, pd.Series) else 0.0
            if direction < 0 and float(bar.bid_c) > price + LEVEL_INVALIDATION_ATR * atr or direction > 0 and float(bar.bid_c) < price - LEVEL_INVALIDATION_ATR * atr:
                invalidated = bar.ts + pd.Timedelta(minutes=1)
                rows.append((level_id, price, level.type, level.timeframe, level.created_at, invalidated, touched_count,
                             invalidated, float(getattr(level, "strength", 1.0)), direction))
                break
    return pd.DataFrame(rows, columns=LEVEL_COLUMNS)


def build_levels(bars: pd.DataFrame, symbol: str, timeframes: dict[str, pd.DataFrame]) -> pd.DataFrame:
    parts = []
    daily = timeframes.get("1d", pd.DataFrame())
    for tf in PIVOT_TFS:
        frame = timeframes.get(tf)
        if frame is not None and not frame.empty:
            for k in PIVOT_K:
                part = pivot_events(frame, k, tf)
                if len(part):
                    part["strength"] = 1.0 / k
                    parts.append(part)
    if len(daily):
        parts.extend(_period_levels(daily, symbol))
        parts.append(_with_volume_profile(daily, bars, symbol))
    if symbol in INDEX_SYMBOLS:
        parts.extend(_cme_session_levels(bars))
    parts += [_round_levels(bars, symbol), _vwap_snapshots(bars, symbol)]
    zones = _supply_demand_zones(bars)
    if not zones.empty:
        parts.append(zones)
    parts = [part for part in parts if part is not None and not part.empty]
    if not parts:
        return pd.DataFrame(columns=LEVEL_COLUMNS)
    levels = pd.concat(parts, ignore_index=True, sort=False)
    levels["level_id"] = np.arange(len(levels), dtype=np.int64)
    levels["touches_so_far"] = 0
    levels["invalidated_at"] = pd.NaT
    levels["strength"] = pd.to_numeric(levels.get("strength", 1.0), errors="coerce").fillna(1.0)
    levels["direction"] = pd.to_numeric(levels.get("direction", 0), errors="coerce").fillna(0).astype(np.int8)
    return levels[LEVEL_COLUMNS].sort_values("known_at").reset_index(drop=True)
