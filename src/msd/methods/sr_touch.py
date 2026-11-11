"""S/R touch: use only active 15m+ swing (k=3/5), prior day/week H/L,
round-number and supply/demand zone-edge levels. Merge prices within 0.25 ATR(1h)
using touch-count-weighted means; cluster strength is summed distinct touches and
clusters require strength >=2. Emit once on the first range entry into +/-0.1 ATR(1h)
after a close >=0.5 ATR(1h) away (re-arm), at most once per cluster per 4 hours.
Record approach direction (above/support or below/resistance), strength, type set
and age. Each event offers both bounce and break side candidates for later modeling.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

NAME = "sr_touch"
CLUSTER_ATR = 0.25
TRIGGER_ATR = 0.10
REARM_ATR = 0.50
COOLDOWN_MINUTES = 240
MIN_CLUSTER_TOUCHES = 2

from .level_clusters import bar_clusters, eligible_level_arrays, update_touches
from msd.processing.levels import levels_asof


def detect(features: pd.DataFrame, levels: pd.DataFrame, bars: pd.DataFrame, *, state: dict | None = None,
           return_state: bool = False):
    if bars.empty or features.empty or levels.empty:
        return ([], state or {}, []) if return_state else []
    frame = bars.sort_values("ts").reset_index(drop=True)
    atr = (features.set_index("ts")["1h_atr14"].reindex(frame.ts).to_numpy(float)
           if "1h_atr14" in features else np.full(len(frame), np.nan))
    universe = eligible_level_arrays(levels)
    if universe is None:
        return []
    prices, known, invalid, ids, types, created, price_order = universe
    lows, highs, closes = (frame[c].to_numpy(float) for c in ("bid_l", "bid_h", "bid_c"))
    stamps = (pd.to_datetime(frame.ts, utc=True).astype("datetime64[ns, UTC]").astype("int64").to_numpy() + 60_000_000_000)
    bar_ts = frame.ts.array
    state = state or {}
    state_counts = state.get("touch_counts", {})
    touches = np.asarray([int(state_counts.get(str(level_id), 0)) for level_id in ids], dtype=np.int64)
    touch_state = np.zeros(len(prices), dtype=bool)
    touching_ids = set(map(int, state.get("touching_ids", [])))
    previous_touching = np.asarray([i for i, level_id in enumerate(ids) if int(level_id) in touching_ids], dtype=np.int64)
    touch_state[previous_touching] = True
    armed: dict[int, int] = {int(k): int(v) for k,v in state.get("armed", {}).items()}
    last_emit: dict[int, int] = {int(k): int(v) for k,v in state.get("last_emit", {}).items()}
    prior_close = float(state.get("last_close", np.nan))
    events: list[dict] = []
    touch_rows: list[tuple] = []
    for i in range(len(frame)):
        a = atr[i]
        if not np.isfinite(a) or a <= 0:
            touch_state[previous_touching] = False
            previous_touching = np.empty(0, dtype=np.int64)
            continue
        now = int(stamps[i])
        touching, newly = update_touches(prices, known, invalid, price_order, now,
                                          lows[i], highs[i], touch_state, previous_touching)
        if len(newly):
            touches[newly] += 1
            touch_rows.extend((NAME, int(ids[j]), bar_ts[i], pd.Timestamp(now, tz="UTC")) for j in newly)
        previous_touching = touching
        clusters = bar_clusters(prices, known, invalid, ids, types, created, price_order,
                                now, lows[i] - 0.6*a, highs[i] + 0.6*a, a, touches, CLUSTER_ATR)
        previous_close = closes[i-1] if i else prior_close
        for cluster in clusters:
            key = cluster["key"]
            level = cluster["price"]
            band = TRIGGER_ATR*a
            if np.isfinite(previous_close) and previous_close >= level + band + REARM_ATR*a:
                armed[key] = 1
            elif np.isfinite(previous_close) and previous_close <= level - band - REARM_ATR*a:
                armed[key] = -1
            entered = lows[i] <= level + band and highs[i] >= level - band
            if not entered:
                continue
            direction = armed.pop(key, 0)
            if direction == 0 or cluster["touches"] < MIN_CLUSTER_TOUCHES:
                continue
            if now - last_emit.get(key, -10**30) < COOLDOWN_MINUTES*60_000_000_000:
                continue
            visible = levels_asof(levels, pd.Timestamp(now, tz="UTC"), cluster["members"])
            if visible.empty:
                continue
            last_emit[key] = now
            events.append({"ts": bar_ts[i], "sym": "", "side_candidates": [1, -1],
                           "price": float(closes[i]), "natural_sl": None, "natural_tp": None,
                           "method": NAME, "cluster_id": key, "cluster_price": level,
                           "approach_direction": "from_above_support" if direction > 0 else "from_below_resistance",
                           "cluster_strength": cluster["touches"], "cluster_types": cluster["types"],
                           "cluster_age_minutes": cluster["age_minutes"], "known_at": pd.Timestamp(now, tz="UTC")})
    if not return_state:
        return events
    state_out = {
        "touch_counts": {str(int(level_id)): int(touches[i]) for i,level_id in enumerate(ids) if touches[i]},
        "touching_ids": [int(ids[i]) for i in previous_touching],
        "armed": {str(k): int(v) for k,v in armed.items()},
        "last_emit": {str(k): int(v) for k,v in last_emit.items()},
        "last_close": float(closes[-1]) if len(closes) else prior_close,
    }
    return events, state_out, touch_rows

from .requirements import required_features, market_for
REQUIRED_FEATURES = required_features(NAME)
MARKETS = market_for(NAME)
