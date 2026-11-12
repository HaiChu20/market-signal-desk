"""FROZEN #13 fvg_retrace. A three-candle bullish gap forms when bar 3 low exceeds bar 1 high by >=0.1 ATR; bearish gap is symmetric. Known at bar 3 close. A later retest through its near edge within 60 bars places four-minute limit at that edge; stop beyond far edge plus 0.2 ATR; target 2R.

Expected event volume: <=12 per instrument-day after four-hour same-side cooldown;
zero when required causal inputs are absent. Role: feature. Markets: all.
"""
from __future__ import annotations

from ._checkpoint import detect_checkpointed

NAME = "fvg_retrace"


def detect(features, levels, bars, *, state=None, return_state=False):
    return detect_checkpointed(NAME, features, levels, bars, state=state, return_state=return_state)

from .requirements import required_features, market_for
REQUIRED_FEATURES = required_features(NAME)
MARKETS = market_for(NAME)
