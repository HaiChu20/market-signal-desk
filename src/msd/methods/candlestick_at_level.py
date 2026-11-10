"""FROZEN #9 candlestick_at_level. At a currently active confirmed level cluster candidate within 0.15 ATR, a bullish/bearish candle with a wick of at least 0.3 ATR emits toward the candle body. Stop beyond wick/level plus 0.2 ATR; target 2R.

Expected event volume: <=12 per instrument-day after four-hour same-side cooldown;
zero when required causal inputs are absent. Role: entry feature. Markets: all.
"""
from __future__ import annotations

from ._detectors import detect_rule

NAME = "candlestick_at_level"


def detect(features, levels, bars):
    return detect_rule(NAME, features, levels, bars)
