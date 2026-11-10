"""FROZEN #23 macd_signal. Emit on fresh 1h MACD histogram zero cross. Stop beyond signal bar by 1.2 ATR; target 2R.

Expected event volume: <=12 per instrument-day after four-hour same-side cooldown;
zero when required causal inputs are absent. Role: low expectation. Markets: all.
"""
from __future__ import annotations

from ._detectors import detect_rule

NAME = "macd_signal"


def detect(features, levels, bars):
    return detect_rule(NAME, features, levels, bars)
