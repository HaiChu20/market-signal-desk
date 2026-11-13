"""Frozen v1 causal range-bounce detector.

The detector deliberately contains no learned or fitted quantities.  A row at
``known_at`` depends only on completed candles and swings confirmed by then.
"""
from __future__ import annotations

import hashlib

import numpy as np
import pandas as pd

from msd.levels import confirmed_swings

NAME = "range_bounce"
TIMEFRAMES = ("15m", "1h")
LOOKBACK = 48
PIVOT_SIDES = 3


def active_ranges(candles: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    """Return one causal state row for every completed input candle."""
    if timeframe not in TIMEFRAMES:
        raise ValueError(timeframe)
    required = {"ts", "known_at", "bid_h", "bid_l", "bid_c"}
    missing = required-set(candles)
    if missing:
        raise ValueError(f"range_bounce missing candles: {sorted(missing)}")
    bars = candles.sort_values("known_at").reset_index(drop=True).copy()
    bars["ts"] = pd.to_datetime(bars.ts, utc=True).astype("datetime64[ns, UTC]")
    bars["known_at"] = pd.to_datetime(bars.known_at, utc=True).astype("datetime64[ns, UTC]")
    if len(bars) and not bars.known_at.is_monotonic_increasing:
        raise ValueError("known_at must be monotonic")

    # The frozen rule uses the production 1h ATR(14), computed only from
    # completed 1h candles.  As-of alignment below makes it available to 15m.
    hourly = bars if timeframe == "1h" else None
    if hourly is None:
        grouped = bars.set_index("ts")[["bid_h", "bid_l", "bid_c"]].resample("1h")
        raw = grouped.agg({"bid_h": "max", "bid_l": "min", "bid_c": "last"})
        raw = raw.loc[grouped.bid_c.count().eq(4)].dropna().reset_index()
        raw["known_at"] = raw.ts+pd.Timedelta(hours=1)
        hourly = raw
    previous = hourly.bid_c.shift(1)
    tr = pd.concat([hourly.bid_h-hourly.bid_l, (hourly.bid_h-previous).abs(),
                    (hourly.bid_l-previous).abs()], axis=1).max(axis=1)
    atr_frame = hourly[["known_at"]].copy()
    atr_frame["atr"] = tr.rolling(14, min_periods=14).mean().to_numpy()
    bars = pd.merge_asof(bars, atr_frame.dropna().sort_values("known_at"), on="known_at", direction="backward")

    peaks, troughs = confirmed_swings(bars.bid_h.to_numpy(float), bars.bid_l.to_numpy(float), PIVOT_SIDES)
    top_at = np.flatnonzero(np.isfinite(peaks))
    bottom_at = np.flatnonzero(np.isfinite(troughs))
    rows: list[dict] = []
    for i, row in enumerate(bars.itertuples(index=False)):
        state = {"ts": row.ts, "known_at": row.known_at, "timeframe": timeframe,
                 "active": False, "range_id": None, "top": np.nan, "bottom": np.nan,
                 "atr": float(row.atr) if pd.notna(row.atr) else np.nan,
                 "height_atr": np.nan, "age_candles": np.nan,
                 "top_touches": 0, "bottom_touches": 0}
        atr = state["atr"]
        if not np.isfinite(atr) or atr <= 0:
            rows.append(state); continue
        left = max(0, i-LOOKBACK+1)
        ti = top_at[(top_at >= left) & (top_at <= i)]
        bi = bottom_at[(bottom_at >= left) & (bottom_at <= i)]
        if len(ti) < 2 or len(bi) < 2:
            rows.append(state); continue
        # There may be unrelated swings in the 48-candle window.  Search
        # newest-first for the most recent mutually compatible top and bottom
        # clusters; requiring *all* swings to cluster would silently redefine
        # "at least two" as "every swing".
        def pairs(indices, values):
            answer = []
            for b in range(len(indices)-1, 0, -1):
                for a in range(b-1, -1, -1):
                    if abs(values[b]-values[a]) <= .5*atr:
                        answer.append((indices[[a, b]], values[[a, b]]))
            return answer
        chosen = None
        for tix, tops in pairs(ti, peaks[ti]):
            for bix, bottoms in pairs(bi, troughs[bi]):
                top, bottom = float(np.mean(tops)), float(np.mean(bottoms))
                height = top-bottom
                formed = int(min(tix.min(), bix.min())-PIVOT_SIDES)
                age = i-formed+1
                if not (1.5*atr <= height <= 6*atr) or age < 8:
                    continue
                closes = bars.bid_c.iloc[max(0, formed):i+1].to_numpy(float)
                if (closes > top+.25*atr).any() or (closes < bottom-.25*atr).any():
                    continue
                chosen=(tix,tops,bix,bottoms,top,bottom,height,formed,age);break
            if chosen is not None: break
        if chosen is None:
            rows.append(state);continue
        tix,tops,bix,bottoms,top,bottom,height,formed,age=chosen
        key = f"{timeframe}|{bars.ts.iloc[formed].isoformat()}|{tix[-1]}|{bix[-1]}"
        state.update(active=True, range_id=hashlib.sha1(key.encode()).hexdigest()[:16],
                     top=top, bottom=bottom, height_atr=height/atr,
                     age_candles=age, top_touches=len(tops), bottom_touches=len(bottoms))
        rows.append(state)
    return pd.DataFrame(rows)


def setups(bars: pd.DataFrame, states: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    """Scan completed 1m bars, entering at the following executable open."""
    if bars.empty or states.empty:
        return pd.DataFrame()
    minute = bars.sort_values("ts").reset_index(drop=True).copy()
    minute["ts"] = pd.to_datetime(minute.ts, utc=True).astype("datetime64[ns, UTC]")
    minute["known_at"] = minute.ts+pd.Timedelta(minutes=1)
    state = states.sort_values("known_at").copy()
    state["known_at"] = pd.to_datetime(state.known_at, utc=True).astype("datetime64[ns, UTC]")
    joined = pd.merge_asof(minute, state, on="known_at", direction="backward", suffixes=("", "_range"))
    mid_l = (joined.bid_l.to_numpy(float)+joined.ask_l.to_numpy(float))/2
    mid_h = (joined.bid_h.to_numpy(float)+joined.ask_h.to_numpy(float))/2
    mid_c = (joined.bid_c.to_numpy(float)+joined.ask_c.to_numpy(float))/2
    armed: dict[tuple[str, str], bool] = {}
    last: dict[tuple[str, str], pd.Timestamp] = {}
    out = []
    for i, row in enumerate(joined.itertuples(index=False)):
        if i+1 >= len(joined) or not bool(getattr(row, "active", False)):
            continue
        rid = row.range_id
        if not isinstance(rid, str) or not np.isfinite(row.atr):
            continue
        inner_low = row.bottom+.25*(row.top-row.bottom)
        inner_high = row.top-.25*(row.top-row.bottom)
        if inner_low <= mid_c[i] <= inner_high:
            armed[(rid, "bottom")] = True; armed[(rid, "top")] = True
        for edge, side, touched in (("bottom", 1, mid_l[i] <= row.bottom+.1*row.atr),
                                    ("top", -1, mid_h[i] >= row.top-.1*row.atr)):
            key = (rid, edge)
            previous = last.get(key)
            ready = armed.get(key, True) and (previous is None or row.known_at-previous >= pd.Timedelta(hours=1))
            if not touched or not ready:
                continue
            entry = float(joined.ask_o.iloc[i+1] if side > 0 else joined.bid_o.iloc[i+1])
            # Structural targets must remain beyond the executable entry.
            middle = (row.bottom+row.top)/2
            nearest_stop = row.bottom-.25*row.atr if side > 0 else row.top+.25*row.atr
            if side*(middle-entry) <= 0 or side*(entry-nearest_stop) <= 0:
                continue
            out.append({"symbol": getattr(row, "symbol", None), "timeframe": timeframe,
                        "range_id": rid, "edge": edge, "side": side,
                        "ts": row.ts, "known_at": row.known_at,
                        "entry_index": i+1, "entry_ts": joined.ts.iloc[i+1], "entry_price": entry,
                        "top": row.top, "bottom": row.bottom, "atr": row.atr,
                        "height_atr": row.height_atr, "age_candles": row.age_candles,
                        "top_touches": row.top_touches, "bottom_touches": row.bottom_touches})
            armed[key] = False; last[key] = row.known_at
    return pd.DataFrame(out)
