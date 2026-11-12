"""FROZEN #16 ote_zone. In 1h EMA50/200 trend, first entry into 62-79% retracement of a confirmed high-low swing places a four-minute limit at the 62% boundary. Stop beyond opposite swing plus 0.2 ATR; target prior extreme.

Expected event volume: <=12 per instrument-day after four-hour same-side cooldown;
zero when required causal inputs are absent. Role: feature. Markets: all.
"""
from __future__ import annotations

from ._checkpoint import detect_checkpointed

NAME = "ote_zone"


def detect(features, levels, bars, *, state=None, return_state=False):
    return detect_checkpointed(NAME, features, levels, bars, state=state, return_state=return_state)

from .requirements import required_features, market_for
REQUIRED_FEATURES = required_features(NAME)
MARKETS = market_for(NAME)
