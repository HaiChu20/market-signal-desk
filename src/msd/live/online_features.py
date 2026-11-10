"""Causal minute-bar feature and pilot-event adapter.

Keep the complete warm-up history for exact EMA and higher-timeframe values.
Call ``update`` only after a minute bar has closed. A restart must restore the
same warm-up bars and detector state, or replay them before accepting new bars.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from msd.processing.features import build_features
from msd.processing.levels import build_levels, levels_asof
from msd.processing.pipeline import methods_for_symbol
from msd.processing.timeframes import build_all_timeframes


@dataclass
class OnlineRow:
    features: pd.Series
    levels: pd.DataFrame
    events: list[dict]


class OnlineFeatures:
    """Append completed Capital-format bars and return the current offline row.

    ``history`` is causal warm-up history, never future bars. Keeping all history
    is necessary for float32-exact EWM equivalence; callers may checkpoint it.
    """

    def __init__(self, symbol: str, history: pd.DataFrame | None = None):
        self.symbol = symbol
        self.bars = pd.DataFrame() if history is None else history.copy().sort_values("ts").reset_index(drop=True)
        self.states: dict[str, dict] = {}
        self.previous_features = pd.DataFrame()
        if not self.bars.empty:
            self._prime()

    def _inputs(self):
        timeframes = build_all_timeframes(self.bars, self.symbol)
        levels = build_levels(self.bars, self.symbol, timeframes)
        return timeframes, levels

    def _prime(self):
        timeframes, levels = self._inputs()
        features = build_features(self.bars, self.symbol, timeframes, levels)
        for method in methods_for_symbol(self.symbol):
            if method.NAME in {"sr_touch", "liquidity_sweep"}:
                _, state, _ = method.detect(features, levels, self.bars, return_state=True)
                self.states[method.NAME] = state
        self.previous_features = features.tail(1).reset_index(drop=True)

    def update(self, bar: dict) -> OnlineRow:
        stamp = pd.Timestamp(bar["ts"])
        stamp = stamp.tz_localize("UTC") if stamp.tzinfo is None else stamp.tz_convert("UTC")
        if not self.bars.empty and stamp <= self.bars.ts.iloc[-1]:
            raise ValueError("completed bars must arrive in strictly increasing order")
        row = dict(bar)
        row["ts"] = stamp
        self.bars = pd.concat([self.bars, pd.DataFrame([row])], ignore_index=True)
        timeframes, levels = self._inputs()
        current = build_features(self.bars, self.symbol, timeframes, levels, output_start=stamp)
        detector_features = pd.concat([self.previous_features, current], ignore_index=True)
        one_bar = self.bars.tail(1)
        events = []
        for method in methods_for_symbol(self.symbol):
            if method.NAME in {"sr_touch", "liquidity_sweep"}:
                found, state, _ = method.detect(current, levels, one_bar,
                                                state=self.states.get(method.NAME), return_state=True)
                self.states[method.NAME] = state
            else:
                found = method.detect(detector_features, levels, self.bars.tail(2))
            events.extend({**event, "sym": self.symbol} for event in found if event["ts"] == stamp)
        self.previous_features = current
        return OnlineRow(current.iloc[0], levels_asof(levels, stamp + pd.Timedelta(minutes=1)), events)
