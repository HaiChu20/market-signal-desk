"""FROZEN #8 chart_patterns. Use confirmed alternating 15m-4h swings. Double top/bottom has similar outer extremes within 0.3 ATR; head-and-shoulders has similar shoulders within 0.5 ATR and a middle extreme beyond them by 0.3 ATR. Emit on neckline break only after last pivot confirmation. Stop beyond pattern extreme plus 0.2 ATR; target 2R.

Expected event volume: <=12 per instrument-day after four-hour same-side cooldown;
zero when required causal inputs are absent. Role: filter feature. Markets: all.
"""
from __future__ import annotations

from ._detectors import detect_rule

NAME = "chart_patterns"


def detect(features, levels, bars):
    return detect_rule(NAME, features, levels, bars)
