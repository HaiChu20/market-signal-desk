"""FROZEN #2 round_number_reaction. At an active confirmed round-number level, emit on a one-minute bar whose range enters +/-0.15 ATR(1h); direction is the close side of the level. Stop beyond the bar/level by 0.2 ATR; target 2 stop distances.

Expected event volume: <=12 per instrument-day after four-hour same-side cooldown;
zero when required causal inputs are absent. Role: core level. Markets: all.
"""
from __future__ import annotations

from ._detectors import detect_rule

NAME = "round_number_reaction"


def detect(features, levels, bars):
    return detect_rule(NAME, features, levels, bars)
