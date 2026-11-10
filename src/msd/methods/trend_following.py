"""FROZEN #37 trend_following. On first observation of a newly completed daily bar, emit when both 20-day and 60-day time-series returns have same sign. Stop 1.2 ATR; target 2R.

Expected event volume: <=12 per instrument-day after four-hour same-side cooldown;
zero when required causal inputs are absent. Role: regime. Markets: all.
"""
from __future__ import annotations

from ._detectors import detect_rule

NAME = "trend_following"


def detect(features, levels, bars):
    return detect_rule(NAME, features, levels, bars)
