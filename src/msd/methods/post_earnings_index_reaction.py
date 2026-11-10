"""FROZEN #34 post_earnings_index_reaction. NQ only: at first bar five minutes after a tagged megacap earnings event, follow the five-minute move if above 0.2 ATR. Stop 1.2 ATR; target 2R.

Expected event volume: <=12 per instrument-day after four-hour same-side cooldown;
zero when required causal inputs are absent. Role: event experiment. Markets: NQ.
"""
from __future__ import annotations

from ._checkpoint import detect_checkpointed

NAME = "post_earnings_index_reaction"
SYMBOLS = ('USATECHIDXUSD',)


def detect(features, levels, bars, *, state=None, return_state=False):
    return detect_checkpointed(NAME, features, levels, bars, state=state, return_state=return_state)
