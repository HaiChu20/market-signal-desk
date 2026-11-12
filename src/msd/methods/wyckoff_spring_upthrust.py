"""FROZEN #17 wyckoff_spring_upthrust. A spring/upthrust wicks at least 0.1 ATR beyond a confirmed swing low/high and closes back inside on the same bar. Stop beyond wick/swing plus 0.2 ATR; target opposite swing.

Expected event volume: <=12 per instrument-day after four-hour same-side cooldown;
zero when required causal inputs are absent. Role: feature. Markets: all.
"""
from __future__ import annotations

from ._checkpoint import detect_checkpointed

NAME = "wyckoff_spring_upthrust"


def detect(features, levels, bars, *, state=None, return_state=False):
    return detect_checkpointed(NAME, features, levels, bars, state=state, return_state=return_state)

from .requirements import required_features, market_for
REQUIRED_FEATURES = required_features(NAME)
MARKETS = market_for(NAME)
