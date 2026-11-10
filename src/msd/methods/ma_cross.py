"""FROZEN #21 ma_cross. Emit on fresh 1h EMA20/50 or EMA50/200 gap sign cross. Stop beyond signal bar by 1.2 ATR; target 2R.

Expected event volume: <=12 per instrument-day after four-hour same-side cooldown;
zero when required causal inputs are absent. Role: regime. Markets: all.
"""
from __future__ import annotations

from ._detectors import detect_rule

NAME = "ma_cross"


def detect(features, levels, bars):
    return detect_rule(NAME, features, levels, bars)
