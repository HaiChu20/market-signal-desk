"""FROZEN #10 price_action_h2l2. In 1h EMA50/200 trend, two alternating pullback legs followed by close beyond prior bar high/low trigger H2/L2 continuation. Stop beyond last confirmed opposite swing plus 0.2 ATR; target prior swing.

Expected event volume: <=12 per instrument-day after four-hour same-side cooldown;
zero when required causal inputs are absent. Role: feature. Markets: all.
"""
from __future__ import annotations

from ._checkpoint import detect_checkpointed

NAME = "price_action_h2l2"


def detect(features, levels, bars, *, state=None, return_state=False):
    return detect_checkpointed(NAME, features, levels, bars, state=state, return_state=return_state)
