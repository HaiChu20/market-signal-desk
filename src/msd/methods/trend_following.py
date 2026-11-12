"""FROZEN #37 trend_following. On first observation of a newly completed daily bar, emit when both 20-day and 60-day time-series returns have same sign. Stop 1.2 ATR; target 2R.

Expected event volume: <=12 per instrument-day after four-hour same-side cooldown;
zero when required causal inputs are absent. Role: regime. Markets: all.
"""
from __future__ import annotations

from ._checkpoint import detect_checkpointed

NAME = "trend_following"


def detect(features, levels, bars, *, state=None, return_state=False):
    return detect_checkpointed(NAME, features, levels, bars, state=state, return_state=return_state)

from .requirements import required_features, market_for
REQUIRED_FEATURES = required_features(NAME)
MARKETS = market_for(NAME)
