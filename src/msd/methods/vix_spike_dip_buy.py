"""FROZEN #44 vix_spike_dip_buy. On newly completed daily bar for an index, emit long when VIX is above its trailing one-year 90th percentile and daily return is below -2%. Stop 1.2 ATR; target 2R.

Expected event volume: <=12 per instrument-day after four-hour same-side cooldown;
zero when required causal inputs are absent. Role: regime feature. Markets: indices.
"""
from __future__ import annotations

from ._detectors import detect_rule

NAME = "vix_spike_dip_buy"
SYMBOLS = ('USATECHIDXUSD', 'USA500IDXUSD')


def detect(features, levels, bars):
    return detect_rule(NAME, features, levels, bars)
