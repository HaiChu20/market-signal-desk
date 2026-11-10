"""Shared natural/structural/ATR-grid exit candidate construction."""
from __future__ import annotations

import numpy as np
import pandas as pd
from bisect import bisect_left, bisect_right

SL_ATR_GRID = (0.5, 1.0, 1.5, 2.0, 3.0)
TP_ATR_GRID = (0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0)
MAX_EVENTS_PER_INSTRUMENT_DAY = 50


def assert_event_volume(method: str, symbol: str, event_count: int, instrument_days: int) -> None:
    """Fail before labeling if a detector exceeds the registered event budget."""
    average = event_count / max(int(instrument_days), 1)
    if average > MAX_EVENTS_PER_INSTRUMENT_DAY:
        raise RuntimeError(
            f"Event-volume guard failed: method={method} symbol={symbol} "
            f"events={event_count} instrument_days={instrument_days} "
            f"average_per_day={average:.2f} limit={MAX_EVENTS_PER_INSTRUMENT_DAY}"
        )


def prepare_exit_levels(levels: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Build sorted structural arrays once for a batch of candidate events."""
    if levels is None or levels.empty:
        return (np.empty(0, dtype=float), np.empty(0, dtype=np.int64),
                np.empty(0, dtype=np.int64), np.empty(0, dtype=object))
    if "session_vwap" in set(levels.type.astype(str).unique()):
        levels = levels[levels.type.astype(str) != "session_vwap"]
    prices = levels.price.to_numpy(float)
    known = pd.to_datetime(levels.known_at, utc=True).astype("datetime64[ns, UTC]").astype("int64").to_numpy()
    invalid_ts = pd.to_datetime(levels.invalidated_at, utc=True, errors="coerce") if "invalidated_at" in levels else pd.Series(pd.NaT, index=levels.index, dtype="datetime64[ns, UTC]")
    invalid = invalid_ts.astype("datetime64[ns, UTC]").astype("int64").to_numpy(copy=True)
    invalid[invalid_ts.isna().to_numpy()] = np.iinfo(np.int64).max
    types = levels.type.astype(str).to_numpy()
    order = np.argsort(prices, kind="stable")
    return prices[order], known[order], invalid[order], types[order]


def exit_candidates(event: dict, levels: pd.DataFrame, atr: float,
                    prepared_levels: tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray] | None = None) -> list[dict]:
    """Combine event natural exits, nearby structure and the fixed ATR grid."""
    side, entry = int(event["side"]), float(event["price"])
    candidates = []
    natural_sl, natural_tp = event.get("natural_sl"), event.get("natural_tp")
    candidates.append({"sl": natural_sl, "tp": natural_tp, "kind": "natural"})
    if not np.isfinite(atr) or atr <= 0:
        return candidates
    if levels is not None and not levels.empty:
        prices, known, invalid, types = prepared_levels if prepared_levels is not None else prepare_exit_levels(levels)
        if not len(prices): return candidates
        now=pd.Timestamp(event["known_at"])
        if now.tzinfo is None: now=now.tz_localize("UTC")
        now_ns=int(now.tz_convert("UTC").value)
        if side > 0:
            start, end = bisect_left(prices, entry + 0.5 * atr), bisect_right(prices, entry + 6 * atr)
            candidate_indexes = range(start, end)
        else:
            start, end = bisect_left(prices, entry - 6 * atr), bisect_right(prices, entry - 0.5 * atr)
            candidate_indexes = range(end - 1, start - 1, -1)
        index = next((i for i in candidate_indexes if known[i] <= now_ns and invalid[i] > now_ns and np.isfinite(prices[i])), None)
        if index is not None:
            structural_sl = natural_sl if natural_sl is not None else entry - side * atr
            candidates.append({"sl": structural_sl, "tp": float(prices[index]), "kind": f"structural:{types[index]}"})
    for sl_mult in SL_ATR_GRID:
        sl = entry - side * sl_mult * atr
        for tp_mult in TP_ATR_GRID:
            candidates.append({"sl": sl, "tp": entry + side * tp_mult * atr, "kind": f"atr:{sl_mult:g}:{tp_mult:g}"})
    return candidates
