"""Strategy A: Larry Williams volatility breakout, frozen rule and 24-cell grid."""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd

from . import common as c

STRATEGY = "A"
DEFAULT_PARAMS = {"session": "rth", "k": 0.5, "stop": "opposite_trigger", "direction": "both"}
GRID = tuple({"session": session, "k": k, "stop": stop, "direction": direction}
             for session in ("rth", "full_day")
             for k in (0.3, 0.5, 0.7)
             for stop in ("opposite_trigger", "half_range")
             for direction in ("both", "long_only"))
assert len(GRID) == 24


def _session_id_for(ts: pd.Timestamp, market: str, session: str) -> date:
    spec = c.MARKET_SESSIONS[market]
    local = pd.Timestamp(ts).tz_convert(spec.timezone)
    if session == "full_day" and not spec.full_day_local and local.hour >= 18:
        return local.date() + timedelta(days=1)
    return local.date()


def _period_allowed(ts: pd.Timestamp, period: str) -> bool:
    if period == "dev":
        return c.DEV_START <= ts < c.DEV_END_EXCLUSIVE
    if period == "holdout":
        return ts >= c.HOLDOUT_START
    if period == "all":
        return ts >= c.DEV_START
    raise ValueError("period must be dev, holdout, or all")


def _mid(row: pd.Series, field: str) -> float:
    if c.MARKETS and row.get("bid_" + field) is not None and row.get("ask_" + field) is not None:
        return (float(row["bid_" + field]) + float(row["ask_" + field])) / 2.
    return float(row[field])


def _find_exit(frame: pd.DataFrame, entry_index: int, side: int, stop: float,
               market: str) -> tuple[int, str, float, float, float, float]:
    """Return index, reason, executable fill, mid, spread, and risk-neutral inputs."""
    crypto = market in c.CRYPTO_MARKETS
    if side > 0:
        opens = frame.bid_o.to_numpy(float)[entry_index:]
        extremes = frame.bid_l.to_numpy(float)[entry_index:]
        crossed = np.flatnonzero((opens <= stop) | (extremes <= stop))
    else:
        opens = frame.ask_o.to_numpy(float)[entry_index:]
        extremes = frame.ask_h.to_numpy(float)[entry_index:]
        crossed = np.flatnonzero((opens >= stop) | (extremes >= stop))
    if len(crossed):
        idx = entry_index + int(crossed[0])
        row = frame.iloc[idx]
        spread = 0. if crypto else c.spread_at(row, "o")
        open_px = float(row.bid_o if side > 0 else row.ask_o)
        gap = open_px <= stop if side > 0 else open_px >= stop
        fill = open_px if gap else float(stop)
        mid = fill if crypto else fill + side * spread / 2.
        return idx, "stop", fill, mid, spread, fill
    idx = len(frame) - 1
    row = frame.iloc[idx]
    spread = 0. if crypto else c.spread_at(row, "c")
    if side > 0:
        fill = float(row["bid_c"])
        mid = fill if crypto else fill + spread / 2.
    else:
        fill = float(row["ask_c"])
        mid = fill if crypto else fill - spread / 2.
    return idx, "session_close", fill, mid, spread, mid


def simulate(bars_1m: pd.DataFrame, market: str, params: dict | None = None, *,
             period: str = "dev", allow_holdout: bool = False,
             sessions: list[c.SessionFrame] | None = None) -> list[dict]:
    """Simulate one parameter cell; only the first trigger and one trade/day."""
    params = dict(DEFAULT_PARAMS if params is None else params)
    if set(params) != set(DEFAULT_PARAMS):
        raise ValueError(f"Strategy A parameters must be exactly {tuple(DEFAULT_PARAMS)}")
    if period == "holdout" and not allow_holdout:
        raise PermissionError("holdout simulation requires an explicit holdout run")
    bars = bars_1m.copy()
    bars["ts"] = pd.to_datetime(bars.ts, utc=True)
    bars = bars.sort_values("ts").drop_duplicates("ts").reset_index(drop=True)
    if not allow_holdout and not bars.empty and bars.ts.max() >= c.HOLDOUT_START:
        raise PermissionError("bars reach the holdout boundary; dev simulation refuses them")
    sessions = (c.session_frames(bars, market, params["session"])
                if sessions is None else sessions)
    complete = [session for session in sessions if session.complete]
    rows = []
    for previous, current in zip(complete, complete[1:]):
        frame = current.bars
        open_today = c.midpoint(frame.iloc[0], "o")
        prior_high = float(((previous.bars.bid_h + previous.bars.ask_h) / 2.).max())
        prior_low = float(((previous.bars.bid_l + previous.bars.ask_l) / 2.).min())
        prior_range = prior_high - prior_low
        if not np.isfinite(prior_range) or prior_range <= 0:
            continue
        k = float(params["k"])
        long_trigger = open_today + k * prior_range
        short_trigger = open_today - k * prior_range
        ask_high = frame.ask_h.to_numpy(float)
        bid_low = frame.bid_l.to_numpy(float)
        long_hits = np.flatnonzero(ask_high >= long_trigger)
        short_hits = np.flatnonzero(bid_low <= short_trigger)
        first_long = int(long_hits[0]) if len(long_hits) else None
        first_short = int(short_hits[0]) if len(short_hits) else None
        if params["direction"] == "long_only":
            if first_long is None:
                continue
            side, entry_idx, trigger = 1, first_long, long_trigger
        elif first_long is None and first_short is None:
            continue
        elif first_long is not None and first_short is not None and first_long == first_short:
            # One-minute data cannot establish which stop triggered first.
            continue
        elif first_short is None or (first_long is not None and first_long < first_short):
            side, entry_idx, trigger = 1, first_long, long_trigger
        else:
            side, entry_idx, trigger = -1, first_short, short_trigger
        entry_ts = pd.Timestamp(frame.ts.iloc[entry_idx])
        if not _period_allowed(entry_ts, period):
            continue
        if entry_ts >= c.HOLDOUT_START and not allow_holdout:
            raise PermissionError("holdout entry encountered without explicit authorization")
        row = frame.iloc[entry_idx]
        crypto = market in c.CRYPTO_MARKETS
        spread = 0. if crypto else c.spread_at(row, "o")
        if side > 0:
            entry = max(float(row.ask_o), trigger)
            entry_mid = entry if crypto else entry - spread / 2.
        else:
            entry = min(float(row.bid_o), trigger)
            entry_mid = entry if crypto else entry + spread / 2.
        if params["stop"] == "opposite_trigger":
            stop = open_today - side * k * prior_range
        else:
            stop = entry_mid - side * .5 * prior_range
        risk = abs(entry_mid - stop)
        if not np.isfinite(risk) or risk <= 0:
            continue
        entry_bar = frame.iloc[entry_idx]
        if ((side > 0 and float(entry_bar.bid_o) <= stop) or
                (side < 0 and float(entry_bar.ask_o) >= stop)):
            # The initial stop was already crossed at the minute open, before
            # the breakout trigger can be ordered within that minute.
            continue
        exit_idx, reason, exit_fill, exit_mid, exit_spread, _ = _find_exit(
            frame, entry_idx, side, stop, market
        )
        rows.append(c.build_trade_record(
            market, STRATEGY, params, side, entry_ts, frame.ts.iloc[exit_idx], entry,
            exit_fill, risk, gross_entry=entry_mid, gross_exit=exit_mid,
            entry_spread=(spread if not crypto else None),
            exit_spread=(exit_spread if not crypto else None),
            exit_reason=reason, allow_holdout=allow_holdout,
        ))
    return c.validate_trade_records(rows)


def random_exit_factory(bars_1m: pd.DataFrame, market: str, params: dict, *,
                        allow_holdout: bool = False,
                        sessions: list[c.SessionFrame] | None = None):
    """Make a fixed-entry-time random-side exit callback for the common benchmark."""
    if not allow_holdout and bars_1m.ts.max() >= c.HOLDOUT_START:
        raise PermissionError("randomized holdout exits require an explicit holdout run")
    prepared = c.session_frames(bars_1m, market, params["session"]) if sessions is None else sessions
    lookup = {frame.session_id: frame for frame in prepared if frame.complete}
    def simulate_exit(trade: dict, side: int) -> dict:
        entry_ts = pd.Timestamp(trade["entry_ts"])
        if entry_ts >= c.HOLDOUT_START and not allow_holdout:
            raise PermissionError("holdout benchmark requires an explicit holdout run")
        session_id = _session_id_for(entry_ts, market, params["session"])
        session = lookup.get(session_id)
        if session is None:
            raise ValueError(f"missing complete session for randomized entry {entry_ts}")
        frame = session.bars
        matches = np.flatnonzero(pd.to_datetime(frame.ts, utc=True).eq(entry_ts).to_numpy())
        if len(matches) != 1:
            raise ValueError(f"random benchmark entry minute not present: {entry_ts}")
        entry_idx = int(matches[0])
        row = frame.iloc[entry_idx]
        crypto = market in c.CRYPTO_MARKETS
        spread = 0. if crypto else c.spread_at(row, "o")
        entry = float(row.ask_o if side > 0 else row.bid_o)
        entry_mid = entry if crypto else (entry - spread / 2. if side > 0 else entry + spread / 2.)
        risk = float(trade["risk_points"])
        stop = entry_mid - side * risk
        exit_idx, reason, exit_fill, exit_mid, exit_spread, _ = _find_exit(
            frame, entry_idx, side, stop, market
        )
        return c.build_trade_record(
            market, STRATEGY, params, side, entry_ts, frame.ts.iloc[exit_idx], entry,
            exit_fill, risk, gross_entry=entry_mid, gross_exit=exit_mid,
            entry_spread=spread if not crypto else None,
            exit_spread=exit_spread if not crypto else None,
            exit_reason=reason, allow_holdout=allow_holdout,
        )
    return simulate_exit
