"""FROZEN #40 range_breakout_nr4_nr7. When completed daily ATR is below the preceding seven observations, emit on crossing of a causal prior-day high/low distance. Stop 1.2 ATR; target 2R.

Expected event volume: <=12 per instrument-day after four-hour same-side cooldown;
zero when required causal inputs are absent. Role: feature. Markets: all.
"""
from __future__ import annotations

from ._checkpoint import detect_checkpointed

NAME = "range_breakout_nr4_nr7"


def detect(features, levels, bars, *, state=None, return_state=False):
    return detect_checkpointed(NAME, features, levels, bars, state=state, return_state=return_state)
