"""FROZEN #29 volume_profile_poc_vah_val. React when price touches an active prior-day POC/VAH/VAL within 0.15 ATR. Direction follows close side of level; stop beyond level/bar plus 0.2 ATR; target 2R.

Expected event volume: <=12 per instrument-day after four-hour same-side cooldown;
zero when required causal inputs are absent. Role: level source. Markets: all.
"""
from __future__ import annotations

from ._checkpoint import detect_checkpointed

NAME = "volume_profile_poc_vah_val"


def detect(features, levels, bars, *, state=None, return_state=False):
    return detect_checkpointed(NAME, features, levels, bars, state=state, return_state=return_state)
