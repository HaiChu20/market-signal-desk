"""FROZEN #4 supply_demand_zone_retest. At first qualifying retest of an active supply/demand zone edge within 0.15 ATR(1h), place a four-minute limit at the edge in the direction of the close. Stop beyond edge/bar by 0.2 ATR; target 2R.

Expected event volume: <=12 per instrument-day after four-hour same-side cooldown;
zero when required causal inputs are absent. Role: feature. Markets: all.
"""
from __future__ import annotations

from ._checkpoint import detect_checkpointed

NAME = "supply_demand_zone_retest"


def detect(features, levels, bars, *, state=None, return_state=False):
    return detect_checkpointed(NAME, features, levels, bars, state=state, return_state=return_state)

from .requirements import required_features, market_for
REQUIRED_FEATURES = required_features(NAME)
MARKETS = market_for(NAME)
