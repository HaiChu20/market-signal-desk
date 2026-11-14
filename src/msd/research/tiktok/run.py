"""Dev-only TikTok runner and explicitly guarded one-time holdout runner."""
from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import time

import numpy as np
import pandas as pd

from . import common as c
from . import strategy_a

FROZEN_SPEC_COMMIT = "102c54d"
REPORT_DIR = Path("reports/research/tiktok")
LEDGER = Path("reports/trials.csv")
A_SELECTION = "strategy_A_selection.json"
B_SELECTION = "strategy_B_selection.json"
A_DEFAULT = dict(strategy_a.DEFAULT_PARAMS)
B_DEFAULT = {"fast_ema": 20, "slow_ema": 50, "stop_atr": 1.5,
             "exit_mode": "close", "overlap": "single", "time_stop_days": None}
B_GRID = tuple({"fast_ema": fast, "slow_ema": slow, "stop_atr": stop,
                "exit_mode": "close", "overlap": "single", "time_stop_days": None}
               for fast in (9, 20, 50) for slow in (20, 50, 100) for stop in (1.0, 1.5, 2.5))
assert len(B_GRID) == 27


def _selection_file(strategy: str) -> str:
    return A_SELECTION if strategy == "A" else B_SELECTION


def _run_id(strategy: str, period: str) -> str:
    return f"tiktok-{strategy}-{period}"


def _ensure_run_unused(strategy: str, period: str, reports: Path, ledger: Path) -> None:
    report_period = "dev" if period == "dev" else "holdout"
    target = reports / f"strategy_{strategy}_{report_period}.json"
    if target.exists():
        raise FileExistsError(f"TikTok {strategy} {period} report already exists: {target}")
    if ledger.exists() and any(row["run_id"] == _run_id(strategy, period)
                               for row in c.read_trials(ledger)):
        raise FileExistsError(f"TikTok {strategy} {period} already appears in {ledger}")


def _param_grid(strategy: str) -> tuple[dict, ...]:
    return strategy_a.GRID if strategy == "A" else B_GRID


def _simulate(strategy: str, bars: pd.DataFrame, market: str, params: dict, *,
              period: str, allow_holdout: bool, prepared_sessions=None) -> list[dict]:
    if strategy == "A":
        rows = strategy_a.simulate(
            bars, market, params, period=period, allow_holdout=allow_holdout,
            sessions=prepared_sessions,
        )
    else:
        # B is a pure simulator with the same record schema. The runner calls it
        # only on DEV bars or from the explicitly authorized holdout path.
        rows = c.strategy_simulator("B")(bars, market, params)
    return c.validate_trade_records(rows)


def _cell(params: dict, trades: list[dict], *, allow_holdout: bool) -> dict:
    summary = c.required_outputs(trades, allow_holdout=allow_holdout)
    return {"params": dict(params), "summary": summary,
            "exit_reason_counts": summary["overall"]["exit_reason_counts"]}


def _b_unresolved_count(bars: pd.DataFrame, market: str, params: dict,
                        closed_trades: list[dict]) -> int:
    """Count a selected B position still open at the data end, without rerunning exits."""
    from . import strategy_b as b
    checked = b._validate(bars, market, params)
    five, hourly = b._indicator_bars(
        checked, market, int(params["fast_ema"]), int(params["slow_ema"])
    )
    sessions = b._complete_sessions(checked, market)
    candidates = b._entry_candidates(checked, market, params, five, hourly, sessions)
    by_entry = {pd.Timestamp(row["entry_ts"]).isoformat(): row for row in closed_trades}
    next_entry = pd.Timestamp.min.tz_localize("UTC")
    for candidate in candidates:
        entry_ts = pd.Timestamp(candidate["entry_ts"])
        if entry_ts < next_entry:
            continue
        closed = by_entry.get(entry_ts.isoformat())
        if closed is None:
            return 1
        next_entry = pd.Timestamp(closed["exit_ts"])
    return 0


def _a_random_callback(bars: pd.DataFrame, market: str, params: dict,
                       sessions: list[c.SessionFrame], allow_holdout: bool):
    return strategy_a.random_exit_factory(
        bars, market, params, allow_holdout=allow_holdout, sessions=sessions
    )


def _b_random_callback(bars: pd.DataFrame, market: str, params: dict,
                       allow_holdout: bool):
    from . import strategy_b as b
    checked = b._validate(bars, market, params)
    five, hourly = b._indicator_bars(
        checked, market, int(params["fast_ema"]), int(params["slow_ema"])
    )
    sessions = b._complete_sessions(checked, market)
    candidates = b._entry_candidates(checked, market, params, five, hourly, sessions)
    by_entry = {pd.Timestamp(row["entry_ts"]).isoformat(): row for row in candidates}

    def simulate_exit(trade: dict, side: int):
        if trade["period"] == "holdout" and not allow_holdout:
            raise PermissionError("holdout random exits require an explicit holdout run")
        candidate = by_entry.get(pd.Timestamp(trade["entry_ts"]).isoformat())
        if candidate is None:
            raise ValueError(f"Strategy B random benchmark lacks entry {trade['entry_ts']}")
        candidate = dict(candidate)
        entry_i = candidate["entry_i"]
        bar = checked.iloc[entry_i]
        candidate["side"] = side
        candidate["entry_price"] = float(bar.ask_o if side > 0 else bar.bid_o)
        candidate["risk"] = float(trade["risk_points"])
        candidate["initial_stop"] = candidate["entry_price"] - side * candidate["risk"]
        outcome = b._simulate_candidate(checked, hourly, market, params, candidate)
        return outcome

    return simulate_exit


def _benchmark(strategy: str, bars: pd.DataFrame, market: str, params: dict,
               trades: list[dict], *, allow_holdout: bool,
               prepared_sessions: list[c.SessionFrame] | None = None) -> dict:
    if strategy == "A":
        callback = _a_random_callback(
            bars, market, params, prepared_sessions or [], allow_holdout
        )
    else:
        callback = _b_random_callback(bars, market, params, allow_holdout)
    return c.random_entry_benchmark(
        trades, callback, seeds=1000, seed=1, allow_holdout=allow_holdout
    )


def _run_market_grid(strategy: str, bars: pd.DataFrame, market: str,
                     params_grid: tuple[dict, ...], *, period: str,
                     allow_holdout: bool, keep_params: set[str] | None = None,
                     chosen_params: dict | None = None) -> tuple[list[dict], dict[str, list[dict]], dict]:
    keep_params = keep_params or set()
    cache = {}
    if strategy == "A":
        cache = {kind: c.session_frames(bars, market, kind) for kind in ("rth", "full_day")}
    grid, kept = [], {}
    for params in params_grid:
        prepared = cache.get(params["session"]) if strategy == "A" else None
        all_records = _simulate(strategy, bars, market, params, period=period,
                                allow_holdout=allow_holdout, prepared_sessions=prepared)
        records = all_records
        if period == "holdout":
            records = [record for record in records if record["period"] == "holdout"]
        cell = _cell(params, records, allow_holdout=allow_holdout)
        cell["unresolved_at_end"] = (_b_unresolved_count(bars, market, params, all_records)
                                     if strategy == "B" else 0)
        grid.append(cell)
        key = c.config_hash(params)
        if key in keep_params or (chosen_params is not None and params == chosen_params):
            kept[key] = records
    quality = {}
    if strategy == "A":
        for session in ("rth", "full_day"):
            quality[session] = {
                "sessions_with_data": sum(bool(item.bars.shape[0]) for item in cache[session]),
                "complete_sessions": sum(item.complete for item in cache[session]),
                "skipped_incomplete": sum(not item.complete for item in cache[session]),
            }
    else:
        from . import strategy_b as b
        quality["rth"] = {"complete_sessions": len(b._complete_sessions(bars, market))}
    return grid, kept, quality


def _select(grid: list[dict], params_grid: tuple[dict, ...]) -> dict:
    score = [row["summary"]["overall"]["net_avg_R"] for row in grid]
    if not any(value is not None for value in score):
        return dict(params_grid[0])
    best = max(range(len(score)), key=lambda i: float("-inf") if score[i] is None else score[i])
    return dict(params_grid[best])


def _write_selection(path: Path, strategy: str, params: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    document = {"strategy": strategy, "params": params, "spec_commit": FROZEN_SPEC_COMMIT,
                "selection_period": "dev", "selection_market": "USATECHIDXUSD",
                "selection_metric": "highest dev net avg R after cost"}
    path.write_text(json.dumps(document, indent=2, allow_nan=False) + "\n")


def _load_selection(path: Path, strategy: str) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"frozen DEV selection required before holdout: {path}")
    document = json.loads(path.read_text())
    if document.get("strategy") != strategy or document.get("spec_commit") != FROZEN_SPEC_COMMIT:
        raise ValueError("frozen selection does not match the current strategy spec")
    params = document.get("params")
    if params not in _param_grid(strategy):
        raise ValueError("frozen chosen cell is not in the preregistered parameter grid")
    return dict(params)


def _neighbor_check(grid: list[dict], chosen: dict) -> dict:
    def adjacent(key: str, left, right) -> bool:
        if left == right:
            return False
        values = list(dict.fromkeys(row["params"][key] for row in grid))
        return abs(values.index(left) - values.index(right)) == 1
    neighbors = [row for row in grid if sum(
        adjacent(key, chosen[key], row["params"][key]) for key in chosen
    ) == 1]
    positive = sum((row["summary"]["overall"]["net_avg_R"] or 0.) > 0 for row in neighbors)
    return {"neighbors": len(neighbors), "positive_neighbors": positive,
            "mostly_positive": bool(neighbors and positive > len(neighbors) / 2)}


def _strategy_summary(trades: list[dict], *, allow_holdout: bool) -> dict:
    return c.required_outputs(trades, allow_holdout=allow_holdout)


def _run_dev(strategy: str, reports: Path, ledger: Path) -> dict:
    started = time.perf_counter()
    _ensure_run_unused(strategy, "dev", reports, ledger)
    selection_path = reports / _selection_file(strategy)
    frozen = _load_selection(selection_path, strategy) if selection_path.exists() else None
    grid_params = _param_grid(strategy)
    # This end is exclusive; the source-aware loader receives only the final
    # 2022 calendar day, never a 2023 minute.
    nasdaq = c.load_1m("USATECHIDXUSD", c.WARMUP_START, c.DEV_END_EXCLUSIVE)
    nasdaq_grid, nasdaq_kept, nasdaq_quality = _run_market_grid(
        strategy, nasdaq, "USATECHIDXUSD", grid_params, period="dev",
        allow_holdout=False, chosen_params=frozen,
        keep_params={c.config_hash((A_DEFAULT if strategy == "A" else B_DEFAULT))},
    )
    chosen = frozen if frozen is not None else _select(nasdaq_grid, grid_params)
    if frozen is None:
        _write_selection(selection_path, strategy, chosen)
    default = dict(A_DEFAULT if strategy == "A" else B_DEFAULT)
    chosen_trades = nasdaq_kept.get(c.config_hash(chosen))
    if chosen_trades is None:
        chosen_trades = _simulate(strategy, nasdaq, "USATECHIDXUSD", chosen,
                                  period="dev", allow_holdout=False,
                                  prepared_sessions=(c.session_frames(nasdaq, "USATECHIDXUSD", chosen["session"])
                                                     if strategy == "A" else None))
    default_trades = nasdaq_kept.get(c.config_hash(default))
    if default_trades is None:
        default_trades = _simulate(strategy, nasdaq, "USATECHIDXUSD", default,
                                   period="dev", allow_holdout=False,
                                   prepared_sessions=(c.session_frames(nasdaq, "USATECHIDXUSD", default["session"])
                                                      if strategy == "A" else None))
    nasdaq_random = {}
    for label, params, trades in (("chosen", chosen, chosen_trades), ("default", default, default_trades)):
        sessions = (c.session_frames(nasdaq, "USATECHIDXUSD", params["session"])
                    if strategy == "A" else None)
        nasdaq_random[label] = _benchmark(
            strategy, nasdaq, "USATECHIDXUSD", params, trades,
            allow_holdout=False, prepared_sessions=sessions,
        )
    grids_by_market = {"USATECHIDXUSD": nasdaq_grid}
    quality = {"USATECHIDXUSD": nasdaq_quality}
    unresolved_by_market = {"USATECHIDXUSD": {
        label: next((row.get("unresolved_at_end", 0) for row in nasdaq_grid
                     if row["params"] == params), 0)
        for label, params in (("chosen", chosen), ("default", default))
    }}
    selected_by_market = {"USATECHIDXUSD": {
        "chosen": _strategy_summary(chosen_trades, allow_holdout=False),
        "default": _strategy_summary(default_trades, allow_holdout=False),
        "random": nasdaq_random,
    }}
    chosen_equity = list(chosen_trades)
    full_grid_for_report = [{"params": {"market": "USATECHIDXUSD", **row["params"]},
                            "summary": row["summary"],
                            "exit_reason_counts": row["exit_reason_counts"],
                            "unresolved_at_end": row.get("unresolved_at_end", 0), "trades": []}
                           for row in nasdaq_grid]
    missing = []
    for market in c.MARKETS:
        if market == "USATECHIDXUSD":
            continue
        try:
            bars = c.load_1m(market, c.WARMUP_START, c.DEV_END_EXCLUSIVE)
        except FileNotFoundError:
            missing.append(market)
            continue
        grid, retained, market_quality = _run_market_grid(
            strategy, bars, market, grid_params, period="dev", allow_holdout=False,
            keep_params={c.config_hash(chosen), c.config_hash(default)},
        )
        grids_by_market[market] = grid
        quality[market] = market_quality
        unresolved_by_market[market] = {
            label: next((row.get("unresolved_at_end", 0) for row in grid
                         if row["params"] == params), 0)
            for label, params in (("chosen", chosen), ("default", default))
        }
        summaries = {}
        randoms = {}
        for label, params in (("chosen", chosen), ("default", default)):
            trades = retained[c.config_hash(params)]
            summaries[label] = _strategy_summary(trades, allow_holdout=False)
            sessions = (c.session_frames(bars, market, params["session"])
                        if strategy == "A" else None)
            randoms[label] = _benchmark(strategy, bars, market, params, trades,
                                        allow_holdout=False, prepared_sessions=sessions)
            if label == "chosen":
                chosen_equity.extend(trades)
        selected_by_market[market] = {"chosen": summaries["chosen"],
                                      "default": summaries["default"], "random": randoms}
        full_grid_for_report.extend(
            {"params": {"market": market, **row["params"]},
             "summary": row["summary"], "exit_reason_counts": row["exit_reason_counts"],
             "unresolved_at_end": row.get("unresolved_at_end", 0), "trades": []} for row in grid
        )
    if missing:
        raise FileNotFoundError("missing local development data for: " + ", ".join(missing))
    tier_pooled = c.equal_weight_tiers(selected_by_market)
    chosen_nasdaq = selected_by_market["USATECHIDXUSD"]["chosen"]
    random_chosen = nasdaq_random["chosen"]
    decision = {"dev_net_positive": (chosen_nasdaq["overall"]["net_avg_R"] or 0.) > 0,
                "dev_cost15_nonnegative": (chosen_nasdaq["overall"]["net_avg_R_cost15"] or 0.) >= 0,
                "positive_years": sum(
                    (chosen_nasdaq["by_year"].get(str(year), {}).get("net_avg_R") or 0.) > 0
                    for year in (2019, 2020, 2021, 2022)
                ),
                "random_percentile_above_95": (random_chosen.get("random_percentile") or 0.) > 95.,
                "neighbor_check": _neighbor_check(nasdaq_grid, chosen),
                "holdout_net_positive": None,
                "status": "awaiting one-time holdout"}
    if strategy == "B":
        decision["chosen_variants_nasdaq"] = {}
        for key, value in (("exit_mode", "touch"), ("overlap", "daily"), ("time_stop_days", 10)):
            variant = dict(chosen)
            variant[key] = value
            trades = _simulate("B", nasdaq, "USATECHIDXUSD", variant,
                               period="dev", allow_holdout=False)
            decision["chosen_variants_nasdaq"][key] = _strategy_summary(trades, allow_holdout=False)
    elapsed = time.perf_counter() - started
    report = {
        "strategy": strategy, "period": "dev", "spec_commit": FROZEN_SPEC_COMMIT,
        "data_range": {"warmup_start": str(c.WARMUP_START), "dev_start": str(c.DEV_START),
                       "dev_end_exclusive": str(c.DEV_END_EXCLUSIVE)},
        "chosen_params": chosen, "default_params": default,
        "selection": "highest Nasdaq dev net avg R after costs",
        "markets": selected_by_market, "session_quality": quality,
        "unresolved_at_end_by_market": unresolved_by_market,
        "tier_pooled_equal_market_weight": tier_pooled,
        "full_grid_by_market": grids_by_market, "decision_check": decision,
        "equity_period_markers": ["dev"], "runtime_seconds": elapsed,
    }
    name = f"strategy_{strategy}_dev"
    c.write_report(reports, name, {"scopes": {
        "Nasdaq chosen": selected_by_market["USATECHIDXUSD"]["chosen"],
        "Nasdaq default": selected_by_market["USATECHIDXUSD"]["default"],
    }, **report}, full_grid_for_report, chosen_equity, allow_holdout=False)
    ledger_row = _ledger_row(strategy, "dev", chosen, chosen_nasdaq, elapsed)
    c.append_trial_once(ledger, ledger_row, run_id=_run_id(strategy, "dev"))
    return report


def _ledger_row(strategy: str, period: str, params: dict, summary: dict, runtime: float) -> dict[str, str]:
    period_value = "dev" if period == "dev" else "test"
    config = {"strategy": strategy, "params": params, "spec_commit": FROZEN_SPEC_COMMIT}
    overall = summary["overall"]
    metrics = {"trades": overall["trades"], "net_avg_R": overall["net_avg_R"],
               "net_avg_R_cost15": overall["net_avg_R_cost15"], "t": overall["t"]}
    return {
        "run_id": _run_id(strategy, period), "date": date.today().isoformat(),
        "config_hash": c.config_hash(config), "method": f"tiktok_strategy_{strategy}",
        "parameters": json.dumps(config, sort_keys=True),
        "data_range": "2018-01-01 to 2022-12-31" if period == "dev" else "2023-01-01 to latest local bar",
        "period": period_value, "metrics": json.dumps(metrics, sort_keys=True),
        "note": f"Frozen spec {FROZEN_SPEC_COMMIT}; runtime {runtime:.3f}s.",
    }


def _run_holdout(strategy: str, reports: Path, ledger: Path) -> dict:
    started = time.perf_counter()
    _ensure_run_unused(strategy, "holdout", reports, ledger)
    selection = _load_selection(reports / _selection_file(strategy), strategy)
    dev_report_path = reports / f"strategy_{strategy}_dev.json"
    if not dev_report_path.exists():
        raise FileNotFoundError(f"completed DEV report required before holdout: {dev_report_path}")
    dev_report = json.loads(dev_report_path.read_text())
    default = dict(A_DEFAULT if strategy == "A" else B_DEFAULT)
    end = pd.Timestamp.now(tz="UTC").normalize() + pd.Timedelta(days=1)
    results, grid_rows, quality, curve_trades = {}, [], {}, []
    unresolved_by_market = {}
    randoms_by_market = {}
    missing = []
    for market in c.MARKETS:
        try:
            bars = c.load_1m(
                market, c.WARMUP_START, end, allow_holdout=True
            )
        except FileNotFoundError:
            missing.append(market)
            continue
        for label, params in (("chosen", selection), ("default", default)):
            prepared = (c.session_frames(bars, market, params["session"])
                        if strategy == "A" else None)
            all_trades = _simulate(strategy, bars, market, params, period="all",
                                   allow_holdout=True, prepared_sessions=prepared)
            trades = [row for row in all_trades if row["period"] == "holdout"]
            summary = _strategy_summary(trades, allow_holdout=True)
            unresolved_by_market.setdefault(market, {})[label] = (
                _b_unresolved_count(bars, market, params, all_trades) if strategy == "B" else 0
            )
            random = _benchmark(strategy, bars, market, params, trades, allow_holdout=True,
                                prepared_sessions=prepared)
            results.setdefault(market, {})[label] = summary
            randoms_by_market.setdefault(market, {})[label] = random
            grid_rows.append({"params": {"market": market, "selection": label, **params},
                              "summary": summary, "exit_reason_counts": summary["overall"]["exit_reason_counts"],
                              "unresolved_at_end": _b_unresolved_count(bars, market, params, all_trades)
                              if strategy == "B" else 0, "trades": []})
            if label == "chosen":
                curve_trades.extend(trades)
        if strategy == "A":
            quality[market] = {session: c.session_quality(bars, market, session)
                               for session in ("rth", "full_day")}
        del bars
    if missing:
        raise FileNotFoundError("missing local holdout data for: " + ", ".join(missing))
    for market, random in randoms_by_market.items():
        results[market]["random"] = random
    tier_pooled = c.equal_weight_tiers(results, allow_holdout=True)
    elapsed = time.perf_counter() - started
    chosen_summary = results["USATECHIDXUSD"]["chosen"]
    dev_decision = dev_report["decision_check"]
    holdout_net = chosen_summary["overall"]["net_avg_R"]
    decision = {
        **dev_decision,
        "holdout_net_positive": holdout_net is not None and holdout_net > 0,
    }
    decision["status"] = ("edge" if decision["dev_net_positive"] and
                          decision["dev_cost15_nonnegative"] and decision["positive_years"] >= 3 and
                          decision["random_percentile_above_95"] and
                          decision["neighbor_check"]["mostly_positive"] and
                          decision["holdout_net_positive"] else "no edge")
    report = {"strategy": strategy, "period": "holdout", "spec_commit": FROZEN_SPEC_COMMIT,
              "chosen_params": selection, "default_params": default,
              "data_range": {"start": str(c.HOLDOUT_START), "end_exclusive": str(end)},
              "markets": results, "session_quality": quality,
              "unresolved_at_end_by_market": unresolved_by_market,
              "tier_pooled_equal_market_weight": tier_pooled,
              "decision_check": decision,
              "equity_period_markers": ["holdout"], "runtime_seconds": elapsed}
    c.write_report(reports, f"strategy_{strategy}_holdout",
                   {"scopes": {"Nasdaq chosen": chosen_summary,
                               "Nasdaq default": results["USATECHIDXUSD"]["default"]},
                    **report}, grid_rows, curve_trades, allow_holdout=True)
    c.append_trial_once(ledger, _ledger_row(strategy, "holdout", selection,
                                            chosen_summary, elapsed),
                       run_id=_run_id(strategy, "holdout"))
    return report


def run(strategy: str, *, dev: bool = False, run_holdout_once: bool = False,
        reports: Path = REPORT_DIR, ledger: Path = LEDGER) -> dict:
    if dev == run_holdout_once:
        raise ValueError("choose exactly one of --dev or --run-holdout-once")
    if strategy not in {"A", "B"}:
        raise ValueError("strategy must be A or B")
    return (_run_dev(strategy, reports, ledger) if dev else
            _run_holdout(strategy, reports, ledger))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strategy", choices=("A", "B"), required=True)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--dev", action="store_true", help="run only 2019-2022 development data")
    modes.add_argument("--run-holdout-once", action="store_true",
                       help="run the one-time 2023+ holdout using the frozen DEV selection")
    args = parser.parse_args()
    result = run(args.strategy, dev=args.dev, run_holdout_once=args.run_holdout_once)
    print(json.dumps({key: result[key] for key in
                      ("strategy", "period", "chosen_params", "runtime_seconds")}, sort_keys=True))


if __name__ == "__main__":
    main()
