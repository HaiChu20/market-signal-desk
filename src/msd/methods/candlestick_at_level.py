"""FROZEN #9 candlestick_at_level. At a currently active confirmed level cluster candidate within 0.15 ATR, a bullish/bearish candle with a wick of at least 0.3 ATR emits toward the candle body. Stop beyond wick/level plus 0.2 ATR; target 2R.

Expected event volume: <=12 per instrument-day after four-hour same-side cooldown;
zero when required causal inputs are absent. Role: entry feature. Markets: all.
"""
from __future__ import annotations

from ._checkpoint import detect_checkpointed

NAME = "candlestick_at_level"


def detect(features, levels, bars, *, state=None, return_state=False):
    return detect_checkpointed(NAME, features, levels, bars, state=state, return_state=return_state)

from .requirements import required_features, market_for
REQUIRED_FEATURES = required_features(NAME)
MARKETS = market_for(NAME)
