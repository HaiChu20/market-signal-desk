"""FROZEN #24 bollinger. Variant band_reversion emits on 1h percent-b reentry inside 0/1 after outside close; variant squeeze_breakout emits when width is below trailing 100-observation 20th percentile and percent-b breaks outside. Stop 1.2 ATR; target 2R.

Expected event volume: <=12 per instrument-day after four-hour same-side cooldown;
zero when required causal inputs are absent. Role: volatility feature. Markets: all.
"""
from __future__ import annotations

from ._checkpoint import detect_checkpointed

NAME = "bollinger"


def detect(features, levels, bars, *, state=None, return_state=False):
    return detect_checkpointed(NAME, features, levels, bars, state=state, return_state=return_state)
