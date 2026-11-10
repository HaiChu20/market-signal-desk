"""FROZEN #45 funding_extreme_fade. BTC/ETH only: fade first crossing of published 20-observation funding z-score beyond +2 or -2. Stop 1.2 ATR; target 2R.

Expected event volume: <=12 per instrument-day after four-hour same-side cooldown;
zero when required causal inputs are absent. Role: BTC feature. Markets: BTC/ETH.
"""
from __future__ import annotations

from ._detectors import detect_rule

NAME = "funding_extreme_fade"
SYMBOLS = ('BTCUSDT', 'ETHUSDT')


def detect(features, levels, bars):
    return detect_rule(NAME, features, levels, bars)
