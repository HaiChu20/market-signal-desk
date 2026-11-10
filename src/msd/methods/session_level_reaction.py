"""FROZEN #3 session_level_reaction. React to a causal prior-day/week high or low, overnight high/low, or confirmed 15-minute opening-range edge when the bar enters +/-0.15 ATR(1h). Direction follows the close side; stop beyond level/bar plus 0.2 ATR; target 2R.

Expected event volume: <=12 per instrument-day after four-hour same-side cooldown;
zero when required causal inputs are absent. Role: core level. Markets: all.
"""
from __future__ import annotations

from ._checkpoint import detect_checkpointed

NAME = "session_level_reaction"


def detect(features, levels, bars, *, state=None, return_state=False):
    return detect_checkpointed(NAME, features, levels, bars, state=state, return_state=return_state)
