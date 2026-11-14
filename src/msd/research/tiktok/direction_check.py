"""Post-hoc diagnostic: does the strategy's direction beat 'always long' at the same entries?

Not a selection step: parameters are the frozen chosen/default cells; verdicts are unchanged.
Uses already-revealed holdout data, so every holdout number here is labelled post-hoc.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import common as c
from . import run, strategy_a

MARKETS = ("USATECHIDXUSD", "USA500IDXUSD", "XAUUSD")
OUT = Path("reports/research/tiktok/direction_check.json")


def _stats(x: np.ndarray) -> dict:
    x = x[np.isfinite(x)]
    if len(x) < 2:
        return {"n": int(len(x)), "avg_R": float(x.mean()) if len(x) else None, "t": None}
    return {"n": int(len(x)), "avg_R": float(x.mean()),
            "t": float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x))))}


def _net(value) -> float:
    return np.nan if value is None else float(value["net_R"] if isinstance(value, dict) else value)


def _a_replay(market: str, params: dict, sessions):
    """Replay an A trade at its real entry price (mid), either side, same risk and exits.

    strategy_a.random_exit_factory enters at the breakout minute's open, before the
    trigger was hit inside that minute (look-ahead for the matching side).
    """
    lookup = {s.session_id: s for s in sessions if s.complete}
    crypto = market in c.CRYPTO_MARKETS

    def replay(trade: dict, side: int) -> dict:
        entry_ts = pd.Timestamp(trade["entry_ts"])
        frame = lookup[strategy_a._session_id_for(entry_ts, market, params["session"])].bars
        idx = int(np.flatnonzero(pd.to_datetime(frame.ts, utc=True).eq(entry_ts).to_numpy())[0])
        spread = 0. if crypto else c.spread_at(frame.iloc[idx], "o")
        entry_mid = float(trade["entry_price"]) - trade["side"] * spread / 2.
        fill = entry_mid + side * spread / 2.
        risk = float(trade["risk_points"])
        exit_idx, reason, exit_fill, exit_mid, exit_spread, _ = strategy_a._find_exit(
            frame, idx, side, entry_mid - side * risk, market)
        return c.build_trade_record(
            market, "A", params, side, entry_ts, frame.ts.iloc[exit_idx], fill, exit_fill,
            risk, gross_entry=entry_mid, gross_exit=exit_mid,
            entry_spread=None if crypto else spread, exit_spread=None if crypto else exit_spread,
            exit_reason=reason, allow_holdout=True)
    return replay


def _direction(strategy: str, bars, market: str, params: dict) -> dict:
    prepared = c.session_frames(bars, market, params["session"]) if strategy == "A" else None
    trades = run._simulate(strategy, bars, market, params, period="all",
                           allow_holdout=True, prepared_sessions=prepared)
    callback = (_a_replay(market, params, prepared) if strategy == "A"
                else run._b_random_callback(bars, market, params, True))
    out = {}
    for period in ("dev", "holdout"):
        rows = [t for t in trades if t["period"] == period]
        actual = np.array([t["net_R"] for t in rows], float)
        long_r = np.array([_net(callback(t, 1)) for t in rows], float)
        short_r = np.array([_net(callback(t, -1)) for t in rows], float)
        same = np.where([t["side"] > 0 for t in rows], long_r, short_r)
        mismatch = float(np.nanmax(np.abs(same - actual))) if rows else 0.
        if mismatch > 1e-9:
            raise AssertionError(f"{market} {strategy} {period}: same-side replay off by {mismatch}")
        random = c.random_entry_benchmark(rows, callback, seeds=1000, seed=1, allow_holdout=True)
        out[period] = {"random_percentile": random["random_percentile"],
                       "random_p95_R": random["random_p95_R"],
                       "actual": _stats(actual), "always_long": _stats(long_r),
                       "always_short": _stats(short_r),
                       "share_long": float(np.mean([t["side"] > 0 for t in rows])) if rows else None,
                       "actual_minus_long": _stats(actual - long_r)}
    return out


def _a_open_baseline(bars, market: str, params: dict) -> dict:
    """Buy at every complete session's first bar, same stop rule, exit at session close."""
    sessions = [s for s in c.session_frames(bars, market, params["session"]) if s.complete]
    callback = strategy_a.random_exit_factory(bars, market, params, allow_holdout=True,
                                              sessions=sessions)
    k = float(params["k"])
    by_period = {"dev": [], "holdout": []}
    for previous, current in zip(sessions, sessions[1:]):
        mid_h = ((previous.bars.bid_h + previous.bars.ask_h) / 2.).max()
        mid_l = ((previous.bars.bid_l + previous.bars.ask_l) / 2.).min()
        prior_range = float(mid_h - mid_l)
        if not np.isfinite(prior_range) or prior_range <= 0:
            continue
        risk = (k if params["stop"] == "opposite_trigger" else .5) * prior_range
        entry_ts = pd.Timestamp(current.bars.ts.iloc[0])
        if entry_ts < c.DEV_START:
            continue
        period = "dev" if entry_ts < c.DEV_END_EXCLUSIVE else "holdout"
        by_period[period].append(_net(callback(
            {"entry_ts": entry_ts, "risk_points": risk, "period": period}, 1)))
    return {p: _stats(np.array(v, float)) for p, v in by_period.items()}


def main() -> None:
    a_sel = json.loads((run.REPORT_DIR / run.A_SELECTION).read_text())["params"]
    b_sel = json.loads((run.REPORT_DIR / run.B_SELECTION).read_text())["params"]
    cells = {"A_default": ("A", run.A_DEFAULT), "A_chosen": ("A", a_sel),
             "B_default": ("B", run.B_DEFAULT), "B_chosen": ("B", b_sel)}
    end = pd.Timestamp.now(tz="UTC").normalize() + pd.Timedelta(days=1)
    result = {"note": "post-hoc diagnostic on already-revealed holdout; verdicts unchanged",
              "markets": {}}
    for market in MARKETS:
        bars = c.load_1m(market, c.WARMUP_START, end, allow_holdout=True)
        res = {}
        for name, (strategy, params) in cells.items():
            res[name] = _direction(strategy, bars, market, dict(params))
            if strategy == "A":
                res[name]["open_baseline"] = _a_open_baseline(bars, market, dict(params))
            print(market, name, json.dumps(res[name]), flush=True)
        result["markets"][market] = res
    OUT.write_text(json.dumps(result, indent=1))


if __name__ == "__main__":
    main()
