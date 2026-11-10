"""FROZEN #28 ichimoku_cloud. Causal Tenkan(9)/Kijun(26) high-low midpoint cross on completed one-minute bars, with close on crossing side. No forward-shifted cloud is used. Stop 1.2 ATR; target 2R.

Expected event volume: <=12 per instrument-day after four-hour same-side cooldown;
zero when required causal inputs are absent. Role: low expectation. Markets: all.
"""
from __future__ import annotations

from ._checkpoint import detect_checkpointed

NAME = "ichimoku_cloud"


def detect(features, levels, bars, *, state=None, return_state=False):
    return detect_checkpointed(NAME, features, levels, bars, state=state, return_state=return_state)
