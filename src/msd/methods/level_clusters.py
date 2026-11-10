"""Causal selection, touch accounting and local clustering for event levels."""
from __future__ import annotations

import numpy as np
import pandas as pd

CLUSTER_ATR = 0.25
SWING_TFS = {"15m", "1h", "4h", "1d"}


def eligible_level_arrays(levels: pd.DataFrame):
    types = levels.type.astype(str)
    strength = pd.to_numeric(levels.get("strength", pd.Series(np.nan, index=levels.index)), errors="coerce")
    is_k3_or_k5 = np.isclose(strength.to_numpy(float), 1.0/3.0) | np.isclose(strength.to_numpy(float), 1.0/5.0)
    swing = types.str.startswith("swing_") & levels.timeframe.astype(str).isin(SWING_TFS) & is_k3_or_k5
    structural = (types.str.startswith(("prior_day_", "prior_week_")) |
                  types.eq("round_number") | types.isin({"supply_zone_edge", "demand_zone_edge"}))
    selected = levels.loc[swing | structural].copy()
    if selected.empty:
        return None
    prices = selected.price.to_numpy(float)
    known = pd.to_datetime(selected.known_at, utc=True).astype("datetime64[ns, UTC]").astype("int64").to_numpy()
    if "invalidated_at" in selected:
        invalid_ts = pd.to_datetime(selected.invalidated_at, utc=True, errors="coerce")
        invalid = invalid_ts.astype("datetime64[ns, UTC]").astype("int64").to_numpy(copy=True)
        invalid[invalid_ts.isna().to_numpy()] = np.iinfo(np.int64).max
    else:
        invalid = np.full(len(selected), np.iinfo(np.int64).max, dtype=np.int64)
    ids = selected.level_id.to_numpy() if "level_id" in selected else selected.index.to_numpy()
    created = pd.to_datetime(selected.created_at, utc=True).astype("datetime64[ns, UTC]").astype("int64").to_numpy()
    types = selected.type.astype(str).to_numpy()
    order = np.argsort(prices, kind="stable")
    return prices, known, invalid, ids, types, created, order


def update_touches(prices, known, invalid, price_order, now, low, high,
                   previous_mask: np.ndarray, previous_indices: np.ndarray):
    """Return current/newly touched indices while updating a reusable bool mask."""
    left = int(np.searchsorted(prices[price_order], low, "left"))
    right = int(np.searchsorted(prices[price_order], high, "right"))
    candidates = price_order[left:right]
    active = candidates[(known[candidates] <= now) & (invalid[candidates] > now)]
    newly = active[~previous_mask[active]]
    previous_mask[previous_indices] = False
    previous_mask[active] = True
    return active, newly


def bar_clusters(prices, known, invalid, ids, types, created, price_order,
                 now, low, high, atr, touches, cluster_atr):
    if atr <= 0 or not np.isfinite(atr):
        return []
    ordered_prices = prices[price_order]
    left = int(np.searchsorted(ordered_prices, low, "left"))
    right = int(np.searchsorted(ordered_prices, high, "right"))
    candidates = price_order[left:right]
    candidates = candidates[(known[candidates] <= now) & (invalid[candidates] > now)]
    if not len(candidates):
        return []
    split_at = np.flatnonzero(np.diff(prices[candidates]) > cluster_atr*atr) + 1
    groups = np.split(candidates, split_at)
    return [_cluster(group,prices,ids,types,created,now,touches) for group in groups]


def _cluster(group, prices, ids, types, created, now, touches):
    group=np.asarray(group,dtype=np.intp)
    weights=touches[group].astype(float)
    strength=int(weights.sum())
    if strength:
        price=float(np.sum(prices[group]*weights)/strength)
    else:
        price=float(np.mean(prices[group]))
    age=max(0.0,(now-int(np.min(created[group])))/60_000_000_000)
    # The smallest (oldest) level id anchors a cluster across later additions.
    # A full membership tuple changes whenever a new confirmed level joins and
    # would reset the 4-hour de-duplication clock for the same price area.
    return {"key":int(np.min(ids[group])), "price":price,
            "touches":strength, "types":tuple(sorted(set(types[group]))), "age_minutes":age,
            "members":tuple(ids[group].tolist())}
