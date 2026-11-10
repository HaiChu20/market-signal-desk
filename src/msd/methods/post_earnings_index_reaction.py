"""FROZEN #34 post_earnings_index_reaction. NQ only: at first bar five minutes after a tagged megacap earnings event, follow the five-minute move if above 0.2 ATR. Stop 1.2 ATR; target 2R.

Expected event volume: <=12 per instrument-day after four-hour same-side cooldown;
zero when required causal inputs are absent. Role: event experiment. Markets: NQ.
"""
from __future__ import annotations

from ._detectors import detect_rule

NAME = "post_earnings_index_reaction"
SYMBOLS = ('USATECHIDXUSD',)


def detect(features, levels, bars):
    return detect_rule(NAME, features, levels, bars)
