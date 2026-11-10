"""FROZEN #26 vwap_reclaim_reject. Emit on fresh crossing of session VWAP distance from negative to positive or reverse. Session VWAP is accumulated only through current bar; stop 1.2 ATR; target 2R.

Expected event volume: <=12 per instrument-day after four-hour same-side cooldown;
zero when required causal inputs are absent. Role: level feature. Markets: all.
"""
from __future__ import annotations

from ._checkpoint import detect_checkpointed

NAME = "vwap_reclaim_reject"


def detect(features, levels, bars, *, state=None, return_state=False):
    return detect_checkpointed(NAME, features, levels, bars, state=state, return_state=return_state)
