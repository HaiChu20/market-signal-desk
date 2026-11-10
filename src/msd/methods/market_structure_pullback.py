"""FROZEN #6 market_structure_pullback. After confirmed 1h/15m swing and positive/negative EMA50-200 trend, emit when a bar retests and closes beyond the broken high/low. Stop beyond the last confirmed opposite swing by 0.2 ATR; target prior high/low.

Expected event volume: <=12 per instrument-day after four-hour same-side cooldown;
zero when required causal inputs are absent. Role: core. Markets: all.
"""
from __future__ import annotations

from ._detectors import detect_rule

NAME = "market_structure_pullback"


def detect(features, levels, bars):
    return detect_rule(NAME, features, levels, bars)
