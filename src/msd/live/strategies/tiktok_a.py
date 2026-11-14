"""Causal live adapter for frozen TikTok A (full-day Nasdaq breakout)."""
from __future__ import annotations

from datetime import timedelta
import json
from pathlib import Path

import pandas as pd

from msd.research.tiktok import common
from msd.research.tiktok import strategy_a as research

NAME = "TikTok A breakout (intraday)"
SYMBOLS = ("USATECHIDXUSD",)
RESOLUTION = "MINUTE"
PAIR = "US100 / MNQ"
USES_FORMING_BAR = True
HISTORY_DAYS = 14
EXPECTED_PARAMS = {"session": "full_day", "k": 0.7, "stop": "half_range", "direction": "long_only"}
SELECTION = Path(__file__).resolve().parents[4] / "reports/research/tiktok/strategy_A_selection.json"


def _frozen_params() -> dict:
    selection = json.loads(SELECTION.read_text())
    params = selection.get("params")
    if selection.get("strategy") != "A" or params != EXPECTED_PARAMS:
        raise ValueError("Strategy A selection does not match the frozen live parameters")
    return dict(params)


PARAMS = _frozen_params()


def should_update(bars: pd.DataFrame, through, *, phase: str) -> bool:
    if phase == "update":
        return False  # A's session exit time is fixed when its stop order is placed.
    if phase != "entry":
        return True
    if bars.empty:
        return True
    previous = pd.Timestamp(bars.ts.iloc[-1])
    current = pd.Timestamp(through)
    return (research._session_id_for(previous, SYMBOLS[0], "full_day") !=
            research._session_id_for(current, SYMBOLS[0], "full_day"))


def orders(bars: pd.DataFrame) -> list[dict]:
    """Expose one stop-entry plan per session using only bars seen so far."""
    if bars.empty:
        return []
    data = bars.copy()
    data["ts"] = pd.to_datetime(data.ts, utc=True)
    data = data.sort_values("ts").drop_duplicates("ts").reset_index(drop=True)
    sessions = common.session_frames(data, SYMBOLS[0], "full_day")
    complete_prior = [session for session in sessions if session.complete]
    result = []
    for current in sessions:
        if current.bars.empty:
            continue
        prior = next((session for session in reversed(complete_prior)
                      if session.session_id < current.session_id), None)
        if prior is None:
            continue
        opening = common.midpoint(current.bars.iloc[0], "o")
        prior_high = float(((prior.bars.bid_h + prior.bars.ask_h) / 2.).max())
        prior_low = float(((prior.bars.bid_l + prior.bars.ask_l) / 2.).min())
        prior_range = prior_high - prior_low
        if not pd.notna(prior_range) or prior_range <= 0:
            continue
        level = opening + float(PARAMS["k"]) * prior_range
        distance = 0.5 * prior_range
        # The CFD's normal final bar is stamped 16:14 ET; its close is the
        # frozen research session-close exit. The 17:00 window end expires
        # unfilled orders after the session's last possible trigger.
        exit_ts = current.end - pd.Timedelta(minutes=46)
        result.append({
            "decision_ts": pd.Timestamp(current.bars.ts.iloc[0]),
            "side": 1,
            "entry_type": "stop",
            "trigger_price": float(level),
            "risk_distance": float(distance),
            "risk_from_mid": True,
            "stop": float(level - distance),
            "tp": None,
            "expiry_ts": current.end,
            "exit_ts": exit_ts,
            "exit_at_close": True,
            "reminder_minutes": 10,
            "exit_rule": f"Close by {_helsinki_clock(exit_ts)} Helsinki",
            "confidence": "low",
        })
    return result


def _helsinki_clock(value) -> str:
    return pd.Timestamp(value).tz_convert("Europe/Helsinki").strftime("%H:%M")
