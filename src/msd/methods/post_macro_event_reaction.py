"""FROZEN #33 post_macro_event_reaction. At first bar with macro_minutes_since_event >=5 after having been <5, emit both follow and fade variants of the five-minute move if magnitude exceeds 0.2 ATR. External calendar supplies the event clock; no event without it. Stop 1.2 ATR; target 2R.

Expected event volume: <=12 per instrument-day after four-hour same-side cooldown;
zero when required causal inputs are absent. Role: event experiment. Markets: all.
"""
from __future__ import annotations

from ._checkpoint import detect_checkpointed

NAME = "post_macro_event_reaction"


def detect(features, levels, bars, *, state=None, return_state=False):
    return detect_checkpointed(NAME, features, levels, bars, state=state, return_state=return_state)

from .requirements import required_features, market_for
REQUIRED_FEATURES = required_features(NAME)
MARKETS = market_for(NAME)
