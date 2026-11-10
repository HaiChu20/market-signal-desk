"""FROZEN #17 wyckoff_spring_upthrust. A spring/upthrust wicks at least 0.1 ATR beyond a confirmed swing low/high and closes back inside on the same bar. Stop beyond wick/swing plus 0.2 ATR; target opposite swing.

Expected event volume: <=12 per instrument-day after four-hour same-side cooldown;
zero when required causal inputs are absent. Role: feature. Markets: all.
"""
from __future__ import annotations

from ._detectors import detect_rule

NAME = "wyckoff_spring_upthrust"


def detect(features, levels, bars):
    return detect_rule(NAME, features, levels, bars)
