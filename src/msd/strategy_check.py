"""Contract checks for causal strategy modules."""
from __future__ import annotations

import copy
import numpy as np
import pandas as pd


def _key(order: dict, cutoff: pd.Timestamp | None = None) -> tuple:
    path = order.get("stop_path") or {}
    if isinstance(path, dict):
        path = tuple(sorted((pd.Timestamp(ts), float(level)) for ts, level in path.items()
                            if cutoff is None or pd.Timestamp(ts) <= cutoff))
    else:
        path = tuple(np.asarray(path, dtype=float))
    return (pd.Timestamp(order["decision_ts"]), int(order["side"]), float(order["stop"]),
            None if order.get("tp") is None else float(order["tp"]), path)


def assert_causal(module, bars: pd.DataFrame, n: int = 200, seed: int = 0) -> None:
    """Require truncated and future-volume-perturbed runs to preserve past decisions."""
    bars = bars.sort_values("ts").reset_index(drop=True)
    if len(bars) < 3:
        return
    full_orders = module.orders(bars)
    rng = np.random.default_rng(seed)
    cut_indices = rng.integers(1, len(bars) - 1, size=n)
    for cut_index in cut_indices:
        cut = pd.Timestamp(bars.ts.iloc[cut_index])
        expected = [_key(order, cut) for order in full_orders if pd.Timestamp(order["decision_ts"]) <= cut]
        truncated = module.orders(bars.iloc[:cut_index + 1].copy())
        actual = [_key(order, cut) for order in truncated if pd.Timestamp(order["decision_ts"]) <= cut]
        if expected != actual:
            raise AssertionError(f"causal truncation mismatch at {cut}")
        changed = bars.copy()
        if "volume" in changed:
            future = np.arange(len(changed)) > cut_index
            changed.loc[future, "volume"] = rng.permutation(
                np.nan_to_num(changed.loc[future, "volume"].to_numpy(float), nan=0.0) + 1.0) * 17.0
        # Perturb future prices too; levels and price-based patterns must remain causal.
        future = np.arange(len(changed)) > cut_index
        for col in ("bid_o", "bid_h", "bid_l", "bid_c", "ask_o", "ask_h", "ask_l", "ask_c"):
            if col in changed:
                changed.loc[future, col] *= rng.uniform(0.5, 1.5)
        perturbed = [_key(order, cut) for order in module.orders(changed)
                     if pd.Timestamp(order["decision_ts"]) <= cut]
        if expected != perturbed:
            raise AssertionError(f"future perturbation changed decisions at/before {cut}")
