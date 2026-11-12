"""FROZEN #5 trendline_channel. Project a line through the last two confirmed 15m-4h swing lows/highs with rising/falling slope. Reclaim touch within 0.2 ATR triggers. Stop beyond projected line/bar by 0.2 ATR; target 2R.

Expected event volume: <=12 per instrument-day after four-hour same-side cooldown;
zero when required causal inputs are absent. Role: low priority feature. Markets: all.
"""
from __future__ import annotations

from ._checkpoint import detect_checkpointed

NAME = "trendline_channel"


def detect(features, levels, bars, *, state=None, return_state=False):
    return detect_checkpointed(NAME, features, levels, bars, state=state, return_state=return_state)

from .requirements import required_features, market_for
REQUIRED_FEATURES = required_features(NAME)
MARKETS = market_for(NAME)
