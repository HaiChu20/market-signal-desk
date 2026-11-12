"""Liquidity sweep: eligible levels are confirmed 15m+ swings (k=3/5),
prior day/week H/L, round numbers and supply/demand zone edges. Nearby active
levels are clustered within 0.25 ATR(1h) using touch-weighted mean prices; require
at least 2 cumulative cluster touches. A sweep
is a wick at least 0.1 ATR(1h) beyond the cluster followed by a close back inside
within 3 bars. Emit once per cluster per 4 hours at the close-back bar; high sweeps
offer short candidates and low sweeps offer long candidates. Event known_at is the
close time, and all level inputs are filtered by known_at/invalidated_at at that time.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

NAME = "liquidity_sweep"
SWEEP_ATR = 0.10
CLUSTER_ATR = 0.25
RETURN_WINDOW_BARS = 3
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
    stamps = pd.to_datetime(frame.ts, utc=True).astype("datetime64[ns, UTC]").astype("int64").to_numpy() + 60_000_000_000
    bar_ts = frame.ts.array
    state = state or {}
    state_counts = state.get("touch_counts", {})
    touches = np.asarray([int(state_counts.get(str(level_id), 0)) for level_id in ids], dtype=np.int64)
    touch_state = np.zeros(len(prices), dtype=bool)
    touching_ids = set(map(int, state.get("touching_ids", [])))
    previous_touching = np.asarray([i for i, level_id in enumerate(ids) if int(level_id) in touching_ids], dtype=np.int64)
    touch_state[previous_touching] = True
    pending: dict[int, tuple[int, float, int]] = {}
    for key, value in state.get("pending", {}).items():
        age = int(value.get("age", 0))
        pending[int(key)] = (-age-1, float(value["extreme"]), int(value["side"]))
    last_emit: dict[int, int] = {int(k): int(v) for k,v in state.get("last_emit", {}).items()}
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
        for key, (sweep_i, _, _) in list(pending.items()):
            if i - sweep_i > RETURN_WINDOW_BARS:
                pending.pop(key, None)
        for cluster in clusters:
            key, level = cluster["key"], cluster["price"]
            if cluster["touches"] < MIN_CLUSTER_TOUCHES:
                continue
            if key not in pending:
                if highs[i] >= level + SWEEP_ATR*a:
                    pending[key] = (i, float(highs[i]), -1)
                elif lows[i] <= level - SWEEP_ATR*a:
                    pending[key] = (i, float(lows[i]), 1)
            pending_item = pending.get(key)
            if pending_item is None:
                continue
            sweep_i, extreme, side = pending_item
            returned = closes[i] < level if side < 0 else closes[i] > level
            if i - sweep_i > RETURN_WINDOW_BARS or not returned:
                continue
            if now - last_emit.get(key, -10**30) < COOLDOWN_MINUTES*60_000_000_000:
                pending.pop(key, None)
                continue
            visible = levels_asof(levels, pd.Timestamp(now, tz="UTC"), cluster["members"])
            if visible.empty:
                pending.pop(key, None)
                continue
            last_emit[key] = now
            pending.pop(key, None)
            events.append({"ts": bar_ts[i], "sym": "", "side": side,
                           "price": float(closes[i]), "natural_sl": extreme, "natural_tp": None,
                           "method": NAME, "cluster_id": key, "cluster_price": level,
                           "cluster_strength": cluster["touches"], "cluster_types": cluster["types"],
                           "cluster_age_minutes": cluster["age_minutes"], "known_at": pd.Timestamp(now, tz="UTC")})
    if not return_state:
        return events
    pending_out = {}
    for key,(sweep_i,extreme,side) in pending.items():
        age = max(0, len(frame)-1-sweep_i)
        if age <= RETURN_WINDOW_BARS:
            pending_out[str(key)] = {"age":int(age),"extreme":float(extreme),"side":int(side)}
    state_out = {
        "touch_counts": {str(int(level_id)): int(touches[i]) for i,level_id in enumerate(ids) if touches[i]},
        "touching_ids": [int(ids[i]) for i in previous_touching],
        "pending": pending_out,
        "last_emit": {str(k): int(v) for k,v in last_emit.items()},
    }
    return events, state_out, touch_rows

from .requirements import required_features, market_for
REQUIRED_FEATURES = required_features(NAME)
MARKETS = market_for(NAME)
