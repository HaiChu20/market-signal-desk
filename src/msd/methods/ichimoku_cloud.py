"""FROZEN #28 ichimoku_cloud. Causal Tenkan(9)/Kijun(26) high-low midpoint cross on completed one-minute bars, with close on crossing side. No forward-shifted cloud is used. Stop 1.2 ATR; target 2R.

Expected event volume: <=12 per instrument-day after four-hour same-side cooldown;
zero when required causal inputs are absent. Role: low expectation. Markets: all.
"""
from __future__ import annotations

from ._detectors import detect_rule

NAME = "ichimoku_cloud"


def detect(features, levels, bars):
    return detect_rule(NAME, features, levels, bars)
