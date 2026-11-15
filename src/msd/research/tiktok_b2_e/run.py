"""Run TikTok batch-2 Strategy E statistics and swing stop experiments."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from time import perf_counter

import pandas as pd

from msd.research import swing_stage1 as swing
from msd.research.tiktok import common
from msd.research.tiktok_b2_e import core

OUTPUT = Path("reports/research/tiktok_b2/E")
SELECTION = OUTPUT / "e2_selection.json"


def _latest_month_end(market: str) -> pd.Timestamp:
    paths = sorted((Path("data/bars/dukascopy") / market).glob("????-??.parquet"))
    if not paths:
        raise FileNotFoundError(f"no local data for {market}")
    return pd.Timestamp(paths[-1].stem + "-01", tz="UTC") + pd.offsets.MonthBegin(1)


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def _fmt(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def _e1_markdown(result: dict) -> str:
    lines = [
        "# TikTok batch 2 — Strategy E1",
        "",
        "Completed 1-hour midpoint bars; ATR(14) is causal and N counts bars present.",
        "",
        "## Range check (overall medians)",
        "",
        "| Market | Period | N | Samples | |close move| | Path range | ATR×√N |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for item in result["results"]:
        for row in item["range"]["overall"]:
            lines.append(
                f"| {item['market']} | {item['period']} | {row['N']} | "
                f"{row['close_move']['samples']} | {_fmt(row['close_move']['median'])} | "
                f"{_fmt(row['path_range']['median'])} | {_fmt(row['atr_sqrt_N']['median'])} |"
            )
    lines += [
        "",
        "## 24-bar stop hits and returns",
        "",
        "| Market | Period | Side | k | Hit % | Return in window % | Return within 24h % |",
        "|---|---|---|---:|---:|---:|---:|",
    ]
    for item in result["results"]:
        for row in item["stop_hit_24_bars"]:
            lines.append(
                f"| {item['market']} | {item['period']} | {row['side']} | {row['k']} | "
                f"{_fmt(100 * row['hit_probability'] if row['hit_probability'] is not None else None)} | "
                f"{_fmt(100 * row['return_rest_of_window_given_hit'] if row['return_rest_of_window_given_hit'] is not None else None)} | "
                f"{_fmt(100 * row['return_within_24h_after_hit_given_hit'] if row['return_within_24h_after_hit_given_hit'] is not None else None)} |"
            )
    lines += [
        "",
        "## Video comparison",
        "",
        "Video gold values: measured move 8h 37 vs formula 38; 24h 65 vs 66; "
        "48h 92 vs 94. Reported 24h stop-hit rates were 73%, 52%, 35% for "
        "1/2/3 ATR, with 74% returning to entry after a 1 ATR hit.",
        "",
        "All means, year splits, ATR-tercile splits, both return definitions, and the "
        "full c×ATR×√N table are in `e1.json`.",
        "",
    ]
    return "\n".join(lines)


def run_e1(output: Path = OUTPUT) -> dict:
    started = perf_counter()
    results = []
    for market in core.E2_MARKETS[::-1]:  # XAU first, then NQ as in the plan.
        requested_end = _latest_month_end(market)
        bars = common.load_1m(
            market, common.WARMUP_START, requested_end, allow_holdout=True
        )
        actual_end = pd.Timestamp(bars.ts.max()) + pd.Timedelta(minutes=1)
        for label, start, end in (
            ("dev", core.DEV_START, core.HOLDOUT_START),
            ("2023+", core.HOLDOUT_START, actual_end),
        ):
            item_start = perf_counter()
            item = core.e1_market_period(bars, market, label, start, end)
            item["runtime_seconds"] = perf_counter() - item_start
            results.append(item)
            print(
                f"E1 {market} {label}: {item['hourly_samples_with_atr']} samples "
                f"in {item['runtime_seconds']:.1f}s",
                flush=True,
            )
    result = {
        "protocol": "docs/research/tiktok_batch2_plan.md section 4 E1",
        "video_numbers": {
            "range": {"8h": [38, 37], "24h": [66, 65], "48h": [94, 92]},
            "stop_hit_percent": {"1ATR": 73, "2ATR": 52, "3ATR": 35},
            "return_percent": 74,
        },
        "results": results,
        "runtime_seconds": perf_counter() - started,
    }
    _write_json(output / "e1.json", result)
    (output / "e1.md").write_text(_e1_markdown(result))
    return result


def _e2_markdown(result: dict) -> str:
    lines = [
        "# TikTok batch 2 — Strategy E2 DEV",
        "",
        "Original S1/S2 entries, costs and 30-session exits are unchanged. Selection is "
        "the highest pooled DEV net R/trade over NQ and gold for each setup.",
        "",
        "| Setup | Selected c | N | TP R | Pooled trades | Pooled net R |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for setup, selected in result["selection"].items():
        params = selected["params"]
        lines.append(
            f"| {setup} | {params['c']} | {params['N']} | {params['tp_R']} | "
            f"{selected['trades']} | {_fmt(selected['pooled_net_avg_R'])} |"
        )
    lines += [
        "",
        "## Selected versus original by market",
        "",
        "| Setup | Market | Rule | Trades | Net R | t | Win rate | 1.5× cost R | Median stop | vs original |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for market, market_result in result["markets"].items():
        for setup in core.E2_SETUPS:
            original = market_result["setups"][setup]["original"]
            selected = result["selection"][setup]["params"]
            cell = next(
                row for row in market_result["setups"][setup]["cells"]
                if row["params"] == selected
            )["metrics"]
            for name, metric in (("original", original), ("selected", cell)):
                lines.append(
                    f"| {setup} | {market} | {name} | {metric['trades']} | "
                    f"{_fmt(metric['net_avg_R'])} | {_fmt(metric['t'])} | "
                    f"{_fmt(metric['win_rate'])} | {_fmt(metric['net_avg_R_cost15'])} | "
                    f"{_fmt(metric['median_stop_points'])} | "
                    f"{_fmt(metric['median_stop_vs_original'])} |"
                )
    lines += ["", "Full grid and per-year metrics are in `e2_dev.json`.", ""]
    return "\n".join(lines)


def run_e2_dev(output: Path = OUTPUT) -> dict:
    started = perf_counter()
    period = swing.Period(
        data_start=common.WARMUP_START,
        score_start=core.DEV_START,
        end=core.HOLDOUT_START,
    )
    markets = {}
    for market in core.E2_MARKETS:
        bars = common.load_1m(market)
        market_start = perf_counter()
        markets[market] = core.e2_market_dev(bars, market, period)
        markets[market]["runtime_seconds"] = perf_counter() - market_start
        print(f"E2 {market}: {markets[market]['runtime_seconds']:.1f}s", flush=True)
    selection = core.choose_e2(markets)
    result = {
        "protocol": "docs/research/tiktok_batch2_plan.md section 4 E2",
        "period": "dev 2019-2022",
        "markets": markets,
        "selection": selection,
        "runtime_seconds": perf_counter() - started,
    }
    _write_json(output / "e2_dev.json", result)
    (output / "e2_dev.md").write_text(_e2_markdown(result))
    _write_json(
        output / "e2_selection.json",
        {
            "protocol": result["protocol"],
            "period": result["period"],
            "selection": selection,
        },
    )
    return result


def run_e2_holdout_once(
    *, run_flag: bool, output: Path = OUTPUT, selection_path: Path = SELECTION
) -> dict:
    selection_doc = core.require_e2_holdout(
        run_flag, selection_path, output / "e2_holdout.json"
    )
    started = perf_counter()
    markets = {}
    for market in core.E2_MARKETS:
        requested_end = _latest_month_end(market)
        bars = common.load_1m(
            market, common.WARMUP_START, requested_end, allow_holdout=True
        )
        actual_end = pd.Timestamp(bars.ts.max()) + pd.Timedelta(minutes=1)
        period = swing.Period(
            data_start=common.WARMUP_START,
            score_start=core.HOLDOUT_START,
            end=actual_end,
        )
        original, drops = core.original_trades(bars, market, period)
        market_result = {"original_drops": drops, "setups": {}}
        for setup in core.E2_SETUPS:
            params = selection_doc["selection"][setup]["params"]
            baseline = core._original_report_rows(
                [row for row in original if row["setup"] == setup]
            )
            original_median = (
                float(pd.Series([row["risk_points"] for row in baseline]).median())
                if baseline else float("nan")
            )
            rows, cell_drops = core.replay_e2_config(
                bars, market, setup, params["c"], params["N"], params["tp_R"],
                period=period,
            )
            market_result["setups"][setup] = {
                "params": params,
                "original": core.summarise_e2(baseline, original_median),
                "selected": core.summarise_e2(rows, original_median),
                "drops": cell_drops,
            }
        markets[market] = market_result
    result = {
        "protocol": "docs/research/tiktok_batch2_plan.md section 4 E2",
        "period": "holdout 2023+",
        "selection": selection_doc["selection"],
        "markets": markets,
        "runtime_seconds": perf_counter() - started,
    }
    _write_json(output / "e2_holdout.json", result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--run-e1", action="store_true")
    parser.add_argument("--run-e2-dev", action="store_true")
    parser.add_argument("--run-e2-holdout-once", action="store_true")
    args = parser.parse_args()
    if not (args.run_e1 or args.run_e2_dev or args.run_e2_holdout_once):
        parser.error("choose --run-e1, --run-e2-dev, or --run-e2-holdout-once")
    if args.run_e1:
        result = run_e1(args.output)
        print(f"E1 complete in {result['runtime_seconds']:.1f}s")
    if args.run_e2_dev:
        result = run_e2_dev(args.output)
        print(f"E2 DEV complete in {result['runtime_seconds']:.1f}s")
    if args.run_e2_holdout_once:
        result = run_e2_holdout_once(
            run_flag=True,
            output=args.output,
            selection_path=args.output / "e2_selection.json",
        )
        print(f"E2 holdout complete in {result['runtime_seconds']:.1f}s")


if __name__ == "__main__":
    main()
