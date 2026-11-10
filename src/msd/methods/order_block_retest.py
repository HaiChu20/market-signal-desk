"""FROZEN #12 order_block_retest. After a completed bar breaks a confirmed swing high/low, mark the immediately preceding opposite candle as a block. A later retest of its near edge within 60 bars places a four-minute limit at the edge; stop beyond far edge plus 0.2 ATR; target 2R.

Expected event volume: <=12 per instrument-day after four-hour same-side cooldown;
zero when required causal inputs are absent. Role: feature. Markets: all.
"""
from __future__ import annotations

from ._detectors import detect_rule

NAME = "order_block_retest"


def detect(features, levels, bars):
    return detect_rule(NAME, features, levels, bars)
