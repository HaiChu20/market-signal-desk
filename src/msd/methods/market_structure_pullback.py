"""FROZEN #6 market_structure_pullback. After confirmed 1h/15m swing and positive/negative EMA50-200 trend, emit when a bar retests and closes beyond the broken high/low. Stop beyond the last confirmed opposite swing by 0.2 ATR; target prior high/low.

Expected event volume: <=12 per instrument-day after four-hour same-side cooldown;
zero when required causal inputs are absent. Role: core. Markets: all.
"""
from __future__ import annotations

from ._checkpoint import detect_checkpointed

NAME = "market_structure_pullback"


def detect(features, levels, bars, *, state=None, return_state=False):
    return detect_checkpointed(NAME, features, levels, bars, state=state, return_state=return_state)

from .requirements import required_features, market_for
REQUIRED_FEATURES = required_features(NAME)
MARKETS = market_for(NAME)
