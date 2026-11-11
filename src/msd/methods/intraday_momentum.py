"""FROZEN #38 intraday_momentum. After 30 session minutes, emit on first breakout beyond trailing 20-bar mean absolute distance from session open. Record gamma and VIX percentile when present. Stop 1.2 ATR; target 2R.

Expected event volume: <=12 per instrument-day after four-hour same-side cooldown;
zero when required causal inputs are absent. Role: conditional feature. Markets: indices.
"""
from __future__ import annotations

from ._checkpoint import detect_checkpointed

NAME = "intraday_momentum"
SYMBOLS = ('USATECHIDXUSD', 'USA500IDXUSD')


def detect(features, levels, bars, *, state=None, return_state=False):
    return detect_checkpointed(NAME, features, levels, bars, state=state, return_state=return_state)

from .requirements import required_features, market_for
REQUIRED_FEATURES = required_features(NAME)
MARKETS = market_for(NAME)
