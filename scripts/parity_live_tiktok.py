#!/usr/bin/env python3
"""Compare causal SignalEngine replay with frozen TikTok A/B research trades."""
from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
import time

import pandas as pd

from msd.data.dukascopy import load as load_dukascopy
from msd.live.engine import SignalEngine
from msd.live.store import SignalStore
from msd.live.strategies import tiktok_a, tiktok_b
from msd.research.tiktok import strategy_a, strategy_b

MARKET = "USATECHIDXUSD"
STRATEGIES = (tiktok_a, tiktok_b)


def _data_path(value: Path) -> Path:
    if value.name == "dukascopy":
        return value
    if value.name == "bars":
        return value / "dukascopy"
    return value / "bars" / "dukascopy"


def _records(store: SignalStore, module, start: pd.Timestamp, end: pd.Timestamp) -> list[dict]:
    store.connection.row_factory = __import__("sqlite3").Row
    rows = store.connection.execute(
        "SELECT * FROM signals WHERE symbol=? AND setup=? AND status IN ('stop','time','tp')",
        (MARKET, module.NAME),
    ).fetchall()
    return [dict(row) for row in rows if start <= pd.Timestamp(row["entry_ts"]) < end]


def _compare(label: str, expected: list[dict], actual: list[dict]) -> dict:
    expected_by_key = {(pd.Timestamp(row["entry_ts"]).isoformat(), int(row["side"])): row
                       for row in expected}
    actual_by_key = {(pd.Timestamp(row["entry_ts"]).isoformat(), int(row["side"])): row
                     for row in actual}
    mismatches = []
    matched_entries, exit_matches = [], 0
    risk_diffs = []
    for key, research_row in expected_by_key.items():
        engine_row = actual_by_key.get(key)
        if engine_row is None:
            mismatches.append({"reason": "missing engine trade", "entry_ts": key[0], "side": key[1]})
            continue
        matched_entries.append({"entry_ts": key[0], "side": key[1]})
        expected_exit = pd.Timestamp(research_row["exit_ts"])
        actual_exit = pd.Timestamp(engine_row["exit_ts"])
        if expected_exit != actual_exit:
            mismatches.append({"reason": "exit_ts mismatch", "entry_ts": key[0],
                               "expected": expected_exit.isoformat(),
                               "actual": actual_exit.isoformat()})
        else:
            exit_matches += 1
        expected_r = float(research_row["net_R"])
        actual_r = float(engine_row["realized_r"])
        risk_diffs.append(abs(expected_r - actual_r))
        if abs(expected_r - actual_r) > 1e-8:
            mismatches.append({"reason": "R mismatch", "entry_ts": key[0],
                               "expected_R": expected_r, "actual_R": actual_r})
    for key, engine_row in actual_by_key.items():
        if key not in expected_by_key:
            mismatches.append({"reason": "extra engine trade", "entry_ts": key[0], "side": key[1],
                               "exit_ts": engine_row["exit_ts"]})
    return {
        "strategy": label,
        "research_closed_trades": len(expected),
        "engine_closed_trades": len(actual),
        "matched_entries": matched_entries,
        "exit_ts_matches": exit_matches,
        "max_abs_R_diff": max(risk_diffs, default=0.),
        "mismatches": mismatches,
    }


def run(data_root: Path, start: date, end: date) -> dict:
    started = time.perf_counter()
    start_ts = pd.Timestamp(start, tz="UTC")
    end_exclusive = pd.Timestamp(end, tz="UTC") + pd.Timedelta(days=1)
    warm_start = start_ts - pd.Timedelta(days=42)
    bars = load_dukascopy(MARKET, warm_start.date(), end, root=_data_path(data_root))
    bars["ts"] = pd.to_datetime(bars.ts, utc=True)
    bars = bars[(bars.ts >= warm_start) & (bars.ts < end_exclusive)].reset_index(drop=True)
    if bars.empty:
        raise FileNotFoundError(f"no {MARKET} bars in {warm_start.date()}..{end}")

    store = SignalStore(":memory:")
    engine = SignalEngine(
        store, lambda _message: None, mode="live",
        instruments=[{"symbol": MARKET, "hours": "cme_equity"}],
        strategies=[{"module": module.__name__, "enabled": True} for module in STRATEGIES],
    )
    # Match the real poll sequence: process one completed minute, then use the
    # next minute's open as the forming bar for newly known signals.
    for index, row in enumerate(bars.to_dict("records")):
        engine.process_completed(MARKET, "MINUTE", row)
        if index + 1 < len(bars):
            engine.process_forming(MARKET, "MINUTE", bars.iloc[index + 1].to_dict())
    engine.reminder((pd.Timestamp(bars.ts.iloc[-1]) + pd.Timedelta(minutes=1)).to_pydatetime())

    a_research = strategy_a.simulate(bars, MARKET, tiktok_a.PARAMS, period="dev")
    b_research = strategy_b.simulate(bars, MARKET, tiktok_b.PARAMS)
    reports = []
    for module, research_rows in ((tiktok_a, a_research), (tiktok_b, b_research)):
        expected = [row for row in research_rows
                    if start_ts <= pd.Timestamp(row["entry_ts"]) < end_exclusive]
        actual = _records(store, module, start_ts, end_exclusive)
        reports.append(_compare(module.NAME, expected, actual))
    store.close()
    return {"market": MARKET, "start": str(start), "end": str(end),
            "loaded_bars": len(bars), "runtime_seconds": time.perf_counter() - started,
            "comparisons": reports,
            "documented_difference": "Live evaluates each session causally; research can reject a day after observing its completed RTH quality."}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=Path("data"),
                        help="repository data directory, data/bars directory, or Dukascopy bars directory")
    parser.add_argument("--start", type=date.fromisoformat, default=date(2022, 1, 1))
    parser.add_argument("--end", type=date.fromisoformat, default=date(2022, 12, 31))
    args = parser.parse_args()
    result = run(args.data_root, args.start, args.end)
    import json
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
