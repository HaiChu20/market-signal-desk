"""FROZEN #7 dow_trend_confirmation. Emit on a fresh 1h EMA50/200 trend cross that agrees with the last completed daily EMA50/200 regime and has positive 20-bar volume z-score. Stop beyond the bar by 1.2 ATR; target 2R.

Expected event volume: <=12 per instrument-day after four-hour same-side cooldown;
zero when required causal inputs are absent. Role: filter feature. Markets: all.
"""
from __future__ import annotations

from ._detectors import detect_rule

NAME = "dow_trend_confirmation"


def detect(features, levels, bars):
    return detect_rule(NAME, features, levels, bars)
