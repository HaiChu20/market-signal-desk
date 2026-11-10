"""FROZEN #5 trendline_channel. Project a line through the last two confirmed 15m-4h swing lows/highs with rising/falling slope. Reclaim touch within 0.2 ATR triggers. Stop beyond projected line/bar by 0.2 ATR; target 2R.

Expected event volume: <=12 per instrument-day after four-hour same-side cooldown;
zero when required causal inputs are absent. Role: low priority feature. Markets: all.
"""
from __future__ import annotations

from ._detectors import detect_rule

NAME = "trendline_channel"


def detect(features, levels, bars):
    return detect_rule(NAME, features, levels, bars)
