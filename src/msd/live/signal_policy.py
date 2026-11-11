"""Fail-closed checks applied at each completed one-minute decision bar."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class SignalPolicy:
    warmup_minutes: int = 10 * 24 * 60
    max_bar_age_seconds: float = 90.0
    spread_low_percentile: float = 0.05
    spread_high_percentile: float = 0.95
    spread_history_days: int = 7
    spread_min_samples: int = 60
    edge_threshold: float = 0.05
    valid_minutes: int = 4
    chase_atr: float = 0.25
    max_hold_minutes: int = 60

    def __post_init__(self):
        if not (0 <= self.spread_low_percentile < self.spread_high_percentile <= 1):
            raise ValueError("invalid spread percentile band")
        if (self.warmup_minutes < 2 or self.spread_min_samples < 1 or
                self.max_bar_age_seconds <= 0 or self.spread_history_days < 1 or
                self.edge_threshold < 0.05 or self.valid_minutes < 1 or
                self.chase_atr <= 0 or self.max_hold_minutes < 1):
            raise ValueError("invalid live signal policy")

    def data_reason(self, bars: pd.DataFrame, now: pd.Timestamp, *, replay: bool = False) -> str | None:
        """Return a specific data failure, or None when all checks pass."""
        if bars.empty:
            return "warmup"
        ts = pd.Timestamp(bars.ts.iloc[-1])
        now = pd.Timestamp(now)
        if ts.tzinfo is None: ts = ts.tz_localize("UTC")
        if now.tzinfo is None: now = now.tz_localize("UTC")
        if not replay:
            age = (now - (ts + pd.Timedelta(minutes=1))).total_seconds()
            if age < 0 or age > self.max_bar_age_seconds:
                return "stale"
        if len(bars) < self.warmup_minutes:
            return "warmup"
        tail = pd.to_datetime(bars.ts.iloc[-self.warmup_minutes:], utc=True)
        if not tail.diff().iloc[1:].eq(pd.Timedelta(minutes=1)).all():
            return "missing"
        if not {"bid_c", "ask_c"}.issubset(bars):
            return "spread_missing"
        current = float(bars.ask_c.iloc[-1] - bars.bid_c.iloc[-1])
        if not np.isfinite(current) or current <= 0:
            return "spread_missing"
        lookback = ts - pd.Timedelta(days=self.spread_history_days)
        previous = bars.iloc[:-1]
        mask = (previous.ts >= lookback) & (pd.to_datetime(previous.ts, utc=True).dt.hour == ts.hour)
        spread = (previous.loc[mask, "ask_c"] - previous.loc[mask, "bid_c"]).to_numpy(float)
        spread = spread[np.isfinite(spread) & (spread > 0)]
        if len(spread) < self.spread_min_samples:
            return "spread_history"
        low, high = np.quantile(spread, [self.spread_low_percentile, self.spread_high_percentile])
        if not low <= current <= high:
            return "spread_outlier"
        return None
