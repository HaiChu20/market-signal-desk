"""FROZEN #29 volume_profile_poc_vah_val. React when price touches an active prior-day POC/VAH/VAL within 0.15 ATR. Direction follows close side of level; stop beyond level/bar plus 0.2 ATR; target 2R.

Expected event volume: <=12 per instrument-day after four-hour same-side cooldown;
zero when required causal inputs are absent. Role: level source. Markets: all.
"""
from __future__ import annotations

from ._detectors import detect_rule

NAME = "volume_profile_poc_vah_val"


def detect(features, levels, bars):
    return detect_rule(NAME, features, levels, bars)
