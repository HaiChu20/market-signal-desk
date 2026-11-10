"""FROZEN #11 fib_pullback. In positive/negative 1h EMA50/200 trend, first entry into 40-60% retracement of a confirmed high-low swing emits with trend. Stop beyond opposite swing plus 0.2 ATR; target prior extreme.

Expected event volume: <=12 per instrument-day after four-hour same-side cooldown;
zero when required causal inputs are absent. Role: depth feature. Markets: all.
"""
from __future__ import annotations

from ._checkpoint import detect_checkpointed

NAME = "fib_pullback"


def detect(features, levels, bars, *, state=None, return_state=False):
    return detect_checkpointed(NAME, features, levels, bars, state=state, return_state=return_state)
