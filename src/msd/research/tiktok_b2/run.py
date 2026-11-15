"""Run batch-2 Strategy B or B-alt on the frozen development period."""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import date
import json
import multiprocessing
import os
from pathlib import Path
import time

import pandas as pd

from msd.research.tiktok import common
from . import prep, reporting, strategy_b, strategy_b_alt

REPORTS = Path("reports/research/tiktok_b2")
STRATEGIES = {"B": strategy_b, "B-alt": strategy_b_alt}
_WORKER_DATA = None
_WORKER_STRATEGY = None
_WORKER_MODEL = None
_WORKER_MULTIPLIER = 1.
_WORKER_FILL_MODEL = "trade_through"


def _init_worker(data, strategy_name, model, multiplier, fill_model):
    global _WORKER_DATA, _WORKER_STRATEGY, _WORKER_MODEL, _WORKER_MULTIPLIER, _WORKER_FILL_MODEL
    _WORKER_DATA = data
    _WORKER_STRATEGY = STRATEGIES[strategy_name]
    _WORKER_MODEL = model
    _WORKER_MULTIPLIER = multiplier
    _WORKER_FILL_MODEL = fill_model


def _worker(params):
    if _WORKER_STRATEGY.NAME == "B":
        return _WORKER_STRATEGY.simulate_group(_WORKER_DATA, params,
                                              model=_WORKER_MODEL,
                                              multiplier=_WORKER_MULTIPLIER,
                                              fill_model=_WORKER_FILL_MODEL)
    return _WORKER_STRATEGY.simulate(_WORKER_DATA, params,
                                     model=_WORKER_MODEL,
                                     multiplier=_WORKER_MULTIPLIER,
                                     fill_model=_WORKER_FILL_MODEL)


def _run_grid(module, data, *, workers: int = 12, model: str = "futures", multiplier: float = 1.,
              fill_model: str = "trade_through"):
    if module.NAME == "B":
        grouped = {}
        for params in module.GRID:
            grouped.setdefault((params["body_ratio"], params["deadline"]), []).append(dict(params))
        tasks = list(grouped.values())
    else:
        tasks = [dict(params) for params in module.GRID]
    workers = max(1, min(int(workers), 12, len(tasks), os.cpu_count() or 1))
    if workers == 1:
        results = []
        for task in tasks:
            if module.NAME == "B":
                results.extend(module.simulate_group(data, task, model=model,
                    multiplier=multiplier, fill_model=fill_model))
            else:
                results.append((task, *module.simulate(data, task, model=model,
                    multiplier=multiplier, fill_model=fill_model)))
        return results
    context = multiprocessing.get_context("spawn")
    results = []
    with ProcessPoolExecutor(max_workers=workers, mp_context=context,
                             initializer=_init_worker,
                             initargs=(data, module.NAME, model, multiplier, fill_model)) as pool:
        futures = {pool.submit(_worker, task): task for task in tasks}
        completed = 0
        for future in as_completed(futures):
            payload = futures[future]
            value = future.result()
            if module.NAME == "B":
                results.extend(value)
                completed += len(payload)
            else:
                results.append((payload, *value))
                completed += 1
            print(f"{module.NAME}: {completed}/{len(module.GRID)} cells", flush=True)
    results.sort(key=lambda row: tuple(str(row[0][key]) for key in sorted(row[0])))
    return results


def _cell(results, params):
    return next((trades for candidate, trades, _ in results if candidate == params), [])


def _summaries(module, results, data):
    grid = []
    for params, trades, diagnostics in results:
        summary = reporting.summarize(trades, data, diagnostics=diagnostics)
        grid.append({"params": params, "summary": summary,
                     "exit_reason_counts": summary["overall"]["exit_reason_counts"],
                     "unresolved_at_end": diagnostics["unresolved_at_end"]})
    eligible = [row for row in grid if row["summary"]["overall"]["trades"] >= 100]
    chosen = max(eligible, key=lambda row: row["summary"]["overall"]["net_avg_R"]) if eligible else None
    default = next(row for row in grid if row["params"] == module.DEFAULT)
    return grid, chosen, default


def _sensitivity(module, data, params, default_params, workers, base_map,
                 cost15_map, cost2_map, touch_map):
    output = {"cost_multipliers": {}, "cost_models": {}, "fill_variants": {}}
    for label, cell in (("chosen", params), ("default", default_params)):
        if cell is None:
            continue
        key = tuple(sorted(cell.items()))
        # These sweeps already exist for every grid cell; reuse them instead of
        # serially recomputing the chosen/default rule.
        for multiplier, result_map in ((1., base_map), (1.5, cost15_map), (2., cost2_map)):
            trades, diagnostics = result_map[key]
            output["cost_multipliers"].setdefault(label, {})[str(multiplier)] = {
                "summary": reporting.summarize(trades, data, diagnostics=diagnostics)["overall"]}
        for model in ("futures", "dukascopy", "capital"):
            if model == "futures":
                trades, diagnostics = base_map[key]
            else:
                trades, diagnostics = module.simulate(data, cell, model=model)
            output["cost_models"].setdefault(label, {})[model] = {
                "summary": reporting.summarize(trades, data, diagnostics=diagnostics)["overall"]}
        # Both W1 strategies use market entries; these runs document that fill
        # sensitivity is exactly invariant for the currently frozen rule.
        for variant, result_map in (("trade_through", base_map), ("touch", touch_map)):
            trades, diagnostics = result_map[key]
            output["fill_variants"].setdefault(label, {})[variant] = {
                "summary": reporting.summarize(trades, data, diagnostics=diagnostics)["overall"]}
    return output


def _load_selection(strategy: str, selection_path: Path) -> dict:
    if not selection_path.is_file():
        raise FileNotFoundError(f"frozen dev selection required before holdout: {selection_path}")
    selection = json.loads(selection_path.read_text())
    params = selection.get("params")
    if selection.get("strategy") != strategy or not isinstance(params, dict):
        raise ValueError("frozen dev selection does not match this strategy")
    if selection.get("config_hash") != common.config_hash(params):
        raise ValueError("frozen dev selection hash is invalid")
    return params


def _output_name(strategy: str, market: str, period: str) -> str:
    return f"{strategy.replace('-', '_')}_{market}_{period}"


def run_dev(strategy: str, market: str, *, workers: int = 12, trials: int = 0) -> dict:
    module = STRATEGIES[strategy]
    started = time.perf_counter()
    data = prep.load_dev(market)
    grid_results = _run_grid(module, data, workers=workers)
    grid, chosen, default = _summaries(module, grid_results, data)
    cost15_results = _run_grid(module, data, workers=workers, multiplier=1.5)
    cost2_results = _run_grid(module, data, workers=workers, multiplier=2.)
    touch_results = _run_grid(module, data, workers=workers, fill_model="touch")
    def result_map(results):
        return {tuple(sorted(params.items())): (trades, diagnostics)
                for params, trades, diagnostics in results}
    primary_map, cost15_map, cost2_map, touch_map = map(
        result_map, (grid_results, cost15_results, cost2_results, touch_results))
    for row in grid:
        key = tuple(sorted(row["params"].items()))
        sensitivities = {}
        for label, result in (("x1_5", cost15_map[key]), ("x2", cost2_map[key]),
                              ("touch", touch_map[key])):
            alternate_trades, alternate_diag = result
            alternate_summary = reporting.summarize(alternate_trades, data, diagnostics=alternate_diag)["overall"]
            sensitivities[label] = alternate_summary
        row["sensitivity"] = sensitivities
        row["summary"]["overall"]["net_avg_R_cost15"] = sensitivities["x1_5"]["net_avg_R"]
        row["summary"]["overall"]["net_avg_R_cost2"] = sensitivities["x2"]["net_avg_R"]
        row["summary"]["overall"]["fill_touch_net_avg_R"] = sensitivities["touch"]["net_avg_R"]
    chosen_params = chosen["params"] if chosen else None
    selection_path = REPORTS / f"selection_{strategy.replace('-', '_')}.json"
    if chosen_params is not None and market == "USATECHIDXUSD":
        selection = reporting.selection_file(selection_path, strategy, chosen_params, market=market)
    elif selection_path.exists():
        selection = json.loads(selection_path.read_text())
    else:
        selection = None
    project_count = reporting.project_configuration_count()
    grid_path = REPORTS / f"{_output_name(strategy, market, 'dev')}_grid.csv"
    current_new = 0 if grid_path.exists() else len(module.GRID)
    count_paths = dict(project_count["by_dev_grid"])
    if current_new:
        count_paths[str(grid_path)] = current_new
    project_count = {**project_count,
                     "tried": project_count["tried"] + current_new,
                     "by_dev_grid": count_paths,
                     "current_grid_cells": len(module.GRID)}
    if trials <= 0:
        trials = max(1, project_count["tried"])
    scopes = {"default": default["summary"]}
    chosen_trades = []
    random_rows = {}
    sensitivity = {}
    lookahead = {}
    if chosen:
        scopes["chosen"] = chosen["summary"]
        chosen_trades = _cell(grid_results, chosen_params)
    default_trades = _cell(grid_results, module.DEFAULT)
    from .execution import execution_bars
    exec_bars = execution_bars(data, market)
    random_rows["default"] = reporting.random_direction(default_trades, exec_bars)
    if chosen:
        random_rows["chosen"] = reporting.random_direction(chosen_trades, exec_bars)
        delayed_trades, delayed_diag = module.simulate(data, chosen_params, signal_delay=1)
        delayed_summary = reporting.summarize(delayed_trades, data, diagnostics=delayed_diag)
        delayed_net = delayed_summary["overall"]["net_avg_R"]
        lookahead = {"summary": delayed_summary,
                     "change_net_avg_R": (None if delayed_net is None else
                         delayed_net - chosen["summary"]["overall"]["net_avg_R"])}
        sensitivity = _sensitivity(module, data, chosen_params, module.DEFAULT, workers,
                                   primary_map,
                                   cost15_map, cost2_map, touch_map)
    else:
        sensitivity = _sensitivity(module, data, None, module.DEFAULT, workers,
                                   primary_map,
                                   cost15_map, cost2_map, touch_map)
    report = {"strategy": strategy, "market": market, "period": "dev",
              "primary_cost_model": "futures", "selection": selection,
              "chosen_params": chosen_params, "default_params": module.DEFAULT,
              "chosen_eligible": chosen is not None,
              "scopes": scopes, "random_benchmark": random_rows,
              "lookahead_audit": lookahead, "sensitivity": sensitivity,
              "dsr": reporting.dsr(reporting.daily_returns(chosen_trades, data), trials) if chosen else None,
              "project_configuration_count": project_count,
              "skip_counts": {str(reason): int(count) for reason, count in
                              data.rth_days.skip_reason.value_counts().items() if reason},
              "rth_quality": {"sessions": int(len(data.rth_days)),
                              "complete": int(data.rth_days.complete.sum()),
                              "skipped": int((~data.rth_days.complete).sum())},
              "grid_cells": len(grid),
              "grid_details": [{"params": row["params"], "summary": row["summary"]["overall"],
                                "sensitivity": row["sensitivity"],
                                "exit_reason_counts": row["exit_reason_counts"]} for row in grid],
              "runtime_seconds": None}
    cross_market = None
    if market == "USATECHIDXUSD" and chosen:
        es_data = prep.load_dev("USA500IDXUSD")
        cross_market = {}
        for label, params in (("chosen", chosen_params), ("default", module.DEFAULT)):
            es_trades, es_diag = module.simulate(es_data, params)
            cross_market[label] = reporting.summarize(es_trades, es_data, diagnostics=es_diag)
        report["cross_market"] = cross_market
    report["runtime_seconds"] = time.perf_counter() - started
    # Primary cell list is persisted; chosen trades are the representative equity path.
    clean_grid = [{"params": row["params"], "summary": row["summary"],
                   "unresolved_at_end": row["unresolved_at_end"],
                   "exit_reason_counts": row["exit_reason_counts"],
                   "sensitivity": row["sensitivity"]} for row in grid]
    output_name = _output_name(strategy, market, "dev")
    reporting.write_b2_report(REPORTS, output_name, report, clean_grid,
                              chosen_trades or default_trades)
    print(json.dumps({"strategy": strategy, "market": market,
                      "chosen_params": chosen_params,
                      "chosen": chosen["summary"]["overall"] if chosen else None,
                      "default": default["summary"]["overall"],
                      "runtime_seconds": report["runtime_seconds"],
                      "cross_market": {k: v["overall"] for k, v in (cross_market or {}).items()}},
                     indent=2, allow_nan=False))
    return report


def run_holdout(strategy: str, *, workers: int = 1, trials: int = 0) -> dict:
    selection_path = REPORTS / f"selection_{strategy.replace('-', '_')}.json"
    reporting.require_holdout(True, selection_path)
    params = _load_selection(strategy, selection_path)
    module = STRATEGIES[strategy]
    market = "USATECHIDXUSD"
    output_name = _output_name(strategy, market, "holdout")
    if (REPORTS / f"{output_name}.json").exists():
        raise FileExistsError("holdout output already exists; the one-time run has been used")
    end = pd.Timestamp.now(tz="UTC").normalize() + pd.Timedelta(days=1)
    raw = common.load_1m(market, start=prep.WARMUP_START, end=end, allow_holdout=True)
    data = prep.prepare(raw, market, allow_holdout=True, selection_path=selection_path)
    trades, diagnostics = module.simulate(data, params, allow_holdout=True,
                                         selection_path=selection_path)
    trades = [row for row in trades if row["period"] == "holdout"]
    common.assert_holdout_allowed(trades, allow_holdout=True)
    summary = reporting.summarize(trades, data, diagnostics=diagnostics, allow_holdout=True,
                                  selection_path=selection_path)
    from .execution import execution_bars
    ex = execution_bars(data, market)
    random = reporting.random_direction(trades, ex, allow_holdout=True,
                                        selection_path=selection_path)
    report = {"strategy": strategy, "market": market, "period": "holdout", "selection": params,
              "scopes": {"chosen": summary}, "random_benchmark": {"chosen": random},
              "project_configuration_count": reporting.project_configuration_count(),
              "grid_cells": 1, "dsr": reporting.dsr(reporting.daily_returns(trades, data), trials or 1)}
    reporting.write_b2_report(REPORTS, output_name, report,
                              [{"params": params, "summary": summary}], trades,
                              allow_holdout=True, selection_path=selection_path)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strategy", choices=tuple(STRATEGIES), required=True)
    parser.add_argument("--market", choices=("USATECHIDXUSD", "USA500IDXUSD"), default="USATECHIDXUSD")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dev", action="store_true", help="run the frozen 2019–2022 development period")
    mode.add_argument("--run-holdout-once", action="store_true", help="supervisor only; requires an existing dev selection")
    parser.add_argument("--workers", type=int, default=min(12, os.cpu_count() or 1))
    parser.add_argument("--trials", type=int, default=0, help="configuration count used by DSR; 0 counts local dev grids")
    args = parser.parse_args()
    if args.run_holdout_once:
        if args.market != "USATECHIDXUSD":
            parser.error("the one-time holdout uses the frozen NQ selection")
        run_holdout(args.strategy, workers=args.workers, trials=args.trials)
    else:
        run_dev(args.strategy, args.market, workers=args.workers, trials=args.trials)


if __name__ == "__main__":
    main()
