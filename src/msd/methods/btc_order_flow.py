"""FROZEN #30 btc_order_flow. BTC/ETH only: taker-buy ratio freshly crosses 0.65 up or 0.35 down with 20-bar volume z-score above 1. Stop 1.2 ATR; target 2R.

Expected event volume: <=12 per instrument-day after four-hour same-side cooldown;
zero when required causal inputs are absent. Role: BTC feature. Markets: BTC/ETH.
"""
from __future__ import annotations

from ._checkpoint import detect_checkpointed

NAME = "btc_order_flow"
SYMBOLS = ('BTCUSDT', 'ETHUSDT')


def detect(features, levels, bars, *, state=None, return_state=False):
    return detect_checkpointed(NAME, features, levels, bars, state=state, return_state=return_state)
