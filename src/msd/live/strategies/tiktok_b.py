"""Causal live adapter for frozen TikTok B (first 5-minute candle vs EMAs)."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from msd.research.tiktok import common
from msd.research.tiktok import strategy_b as research

NAME = "TikTok B first-candle trend"
SYMBOLS = ("USATECHIDXUSD",)
RESOLUTION = "MINUTE"
PAIR = "US100 / MNQ"
HISTORY_DAYS = 42
EXPECTED_PARAMS = {
    "fast_ema": 9, "slow_ema": 50, "stop_atr": 1.0,
    "exit_mode": "close", "overlap": "single", "time_stop_days": None,
}
SELECTION = Path(__file__).resolve().parents[4] / "reports/research/tiktok/strategy_B_selection.json"


def _frozen_params() -> dict:
    selection = json.loads(SELECTION.read_text())
    params = selection.get("params")
    if selection.get("strategy") != "B" or params != EXPECTED_PARAMS:
        raise ValueError("Strategy B selection does not match the frozen live parameters")
    return dict(params)


PARAMS = _frozen_params()


def should_update(bars: pd.DataFrame, through, *, phase: str) -> bool:
    stamp = pd.Timestamp(through)
    if stamp.tzinfo is None:
        stamp = stamp.tz_localize("UTC")
    else:
        stamp = stamp.tz_convert("UTC")
    if phase == "entry":
        local = stamp.tz_convert("America/New_York")
        return local.hour == 9 and local.minute == 34
    if phase == "update":
        boundary = stamp + pd.Timedelta(minutes=1)
        return boundary.minute == 0
    return True


def _as_order(candidate: dict, exit_ts=None) -> dict:
    return {
        "decision_ts": pd.Timestamp(candidate["entry_ts"]) - pd.Timedelta(minutes=1),
        "side": int(candidate["side"]),
        "entry_type": "market",
        "risk_distance": float(candidate["risk"]),
        "stop": candidate.get("initial_stop"),
        "tp": None,
        "exit_ts": exit_ts,
        "exit_at_close": False,
        "reminder_minutes": 0,
        "exit_rule": "Bot will message when to exit · can last days",
        "confidence": "low",
    }


def orders(bars: pd.DataFrame) -> list[dict]:
    """Expose known entries and the current causal hourly-close exit plan."""
    if bars.empty:
        return []
    checked = research._validate(bars, SYMBOLS[0], PARAMS)
    five, hourly = research._indicator_bars(
        checked, SYMBOLS[0], int(PARAMS["fast_ema"]), int(PARAMS["slow_ema"])
    )
    active = bars.attrs.get("open_signals", [])
    if active:
        sessions = research._complete_sessions(checked, SYMBOLS[0])
        candidates = research._entry_candidates(checked, SYMBOLS[0], PARAMS, five, hourly, sessions)
        current = research.live_candidate_from_closed_candle(
            checked, SYMBOLS[0], PARAMS, five, hourly
        )
        if current is not None:
            candidates.append(current)
        target = pd.Timestamp(active[0]["entry_ts"])
        candidates = [row for row in candidates if pd.Timestamp(row["entry_ts"]) == target]
    else:
        current = research.live_candidate_from_closed_candle(
            checked, SYMBOLS[0], PARAMS, five, hourly
        )
        candidates = [] if current is None else [current]

    output = []
    observe_through = pd.Timestamp(checked.ts.iloc[-1]) + pd.Timedelta(minutes=1)
    for candidate in candidates:
        if candidate.get("entry_i") is None:
            output.append(_as_order(candidate))
            break
        state = research._simulate_candidate(
            checked, hourly, SYMBOLS[0], PARAMS, candidate,
            expose_state=True, observe_through=observe_through,
        )
        trade = state["trade"]
        exit_ts = (trade["exit_ts"] if trade is not None
                   else state["planned_exit_ts"])
        output.append(_as_order(candidate, exit_ts))
        break
    return output
