"""FROZEN #45 funding_extreme_fade. BTC/ETH only: fade first crossing of published 20-observation funding z-score beyond +2 or -2. Stop 1.2 ATR; target 2R.

Expected event volume: <=12 per instrument-day after four-hour same-side cooldown;
zero when required causal inputs are absent. Role: BTC feature. Markets: BTC/ETH.
"""
from __future__ import annotations

from ._checkpoint import detect_checkpointed

NAME = "funding_extreme_fade"
SYMBOLS = ('BTCUSDT', 'ETHUSDT')


def detect(features, levels, bars, *, state=None, return_state=False):
    return detect_checkpointed(NAME, features, levels, bars, state=state, return_state=return_state)
