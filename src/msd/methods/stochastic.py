"""FROZEN #25 stochastic. Emit on fresh 1h stochastic K-D cross with K under 25 for long or over 75 for short. Stop 1.2 ATR; target 2R.

Expected event volume: <=12 per instrument-day after four-hour same-side cooldown;
zero when required causal inputs are absent. Role: low expectation. Markets: all.
"""
from __future__ import annotations

from ._detectors import detect_rule

NAME = "stochastic"


def detect(features, levels, bars):
    return detect_rule(NAME, features, levels, bars)
