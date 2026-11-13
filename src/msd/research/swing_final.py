"""Frozen swing v1 FINAL runner. Run once, only by the data owner."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from msd.research import swing_stage1 as s1
from msd.research import swing_stage2 as s2

SCORE_START = pd.Timestamp("2025-01-01", tz="UTC")
WARMUP_START = pd.Timestamp("2023-01-01", tz="UTC")
FINAL_YEARS = (2025, 2026)
WARMUP_PERIOD = s1.Period(data_start=WARMUP_START, score_start=SCORE_START, end=None)
FULL_HISTORY_PERIOD = s1.Period(score_start=SCORE_START, end=None)
MAIN_TRIAL_ID = "swing-v1-final-main"
MODEL_TRIAL_ID = "swing-v1-final-stage2"


def _random_percentile(scores_by_market: dict[str, dict], rows_by_market: dict[str, list[dict]]) -> float | None:
    arrays: list[list[float]] = []
    weights: list[int] = []
    for market in s1.TRADED:
        rows = rows_by_market[market]
        for key, scores in scores_by_market.get(market, {}).items():
            count = sum((r["setup"], r["sl_atr"], r["tp_R"]) == key for r in rows)
            if count:
                arrays.append(scores)
                weights.append(count)
    if not arrays:
        return None
    return float(np.percentile(np.average(np.asarray(arrays), axis=0, weights=weights), 95))


def _version_summary(rows: dict[str, list[dict]], random_95: float | None,
                     unresolved: dict[str, int], **audit: object) -> dict:
    traded = [row for market in s1.TRADED for row in rows[market]]
    evidence = [row for market in s1.EVIDENCE for row in rows[market]]
    per_market = {market: s1._summary(rows[market]) for market in rows}
    per_year = {
        str(year): s1._summary([row for row in traded if row["year"] == year])
        for year in FINAL_YEARS
    }
    evidence_values = [per_market[market]["net_R"] for market in s1.EVIDENCE
                       if per_market[market]["net_R"] is not None]
    return {
        "pooled_traded": s1._summary(traded),
        "per_market": per_market,
        "per_year": per_year,
        "evidence_market_average_R": (float(np.mean(evidence_values))
                                      if evidence_values else None),
        "evidence_trades": len(evidence),
        "random_direction_95pct_R": random_95,
        "random_direction_seeds": 200,
        "unresolved_at_end": unresolved,
        "unresolved_at_end_total": sum(unresolved.values()),
        **audit,
    }


def _main_version(data_root: Path) -> dict:
    selected: dict[str, list[dict]] = {}
    scores: dict[str, dict] = {}
    unresolved: dict[str, int] = {}
    for market in (*s1.TRADED, *s1.EVIDENCE):
        bars = s1.load_minutes(data_root, market, period=WARMUP_PERIOD)
        rows, drops = s1.evaluate_market(
            bars, market, primary_only=True, period=WARMUP_PERIOD, setups=("S3",)
        )
        selected[market] = rows
        unresolved[market] = drops["unresolved_at_cutoff"]
        if market in s1.TRADED:
            scores[market] = s1.baseline(bars, rows, market)
        print(f"main {market}: {len(rows)} scored trades", flush=True)
    random_95 = _random_percentile(scores, selected)
    result = _version_summary(
        selected, random_95, unresolved,
        rule="S3;SL=2ATR;TP=3R", score_start=SCORE_START.isoformat(),
        warmup_start=WARMUP_START.isoformat(),
    )
    net_r = result["pooled_traded"]["net_R"]
    result["verdict"] = "NOT BROKEN" if net_r is not None and net_r > 0 else "BROKEN"
    return result


def _stage2_version(data_root: Path) -> dict:
    traded: dict[str, list[dict]] = {}
    evidence: dict[str, list[dict]] = {}
    bars_for_baseline: dict[str, pd.DataFrame] = {}
    opportunity_drops: dict[str, dict] = {}
    for market in s1.TRADED:
        bars = s1.load_minutes(data_root, market, period=FULL_HISTORY_PERIOD)
        traded[market], opportunity_drops[market] = s2.market_opportunities(
            bars, market, period=FULL_HISTORY_PERIOD
        )
        bars_for_baseline[market] = bars
        print(f"model {market}: opportunities prepared", flush=True)
    for market in s1.EVIDENCE:
        bars = s1.load_minutes(data_root, market, period=WARMUP_PERIOD)
        evidence[market], opportunity_drops[market] = s2.market_opportunities(
            bars, market, period=WARMUP_PERIOD
        )
        print(f"model {market}: opportunities prepared", flush=True)

    scored, models = s2.walk_forward(traded, evidence, years=FINAL_YEARS)
    selected: dict[str, list[dict]] = {}
    counts: dict[str, dict] = {}
    scores: dict[str, dict] = {}
    unresolved: dict[str, int] = {}
    for market, opportunities in scored.items():
        final_opportunities = [opp for opp in opportunities if opp["year"] in FINAL_YEARS]
        selected[market], counts[market] = s2.sequential_trades(final_opportunities)
        unresolved[market] = counts[market].get("unresolved_chosen", 0)
        if market in s1.TRADED:
            scores[market] = s1.baseline(bars_for_baseline[market], selected[market], market)

    result = _version_summary(
        selected, _random_percentile(scores, selected), unresolved,
        models=models, selection_counts=counts, opportunity_drops=opportunity_drops,
        training_features=list(s2.FEATURES), model_params=s2.MODEL_PARAMS,
        num_boost_round=300, threshold_R=s2.THRESHOLD,
    )
    result["verdict"] = "REPORTED ONLY"
    return result


def _fmt(value: object) -> str:
    if value is None:
        return ""
    return f"{value:.4f}" if isinstance(value, float) else str(value)


def _metric_rows(name: str, result: dict) -> list[str]:
    pooled = result["pooled_traded"]
    return [
        f"| {name} | {pooled['trades']} | {_fmt(pooled['net_R'])} | "
        f"{_fmt(pooled['t_stat'])} | {_fmt(pooled['no_carry_R'])} | "
        f"{_fmt(pooled['double_cost_R'])} | {_fmt(result['random_direction_95pct_R'])} | "
        f"{_fmt(result['evidence_market_average_R'])} | {result['unresolved_at_end_total']} |"
    ]


def markdown(result: dict) -> str:
    main = result["main"]
    model = result["stage2"]
    lines = [
        "# Swing v1 — FINAL test", "",
        f"**{main['verdict']}** — the frozen main-version verdict is based only on pooled "
        "net R per trade being greater than zero.", "",
        "Trades entered before 2025-01-01 UTC are not scored. The main version carries "
        "one-trade-per-market state from the 2023–24 warm-up. The Stage 2 version is "
        "reported only and does not affect the verdict.", "",
        "| Version | Trades | Net R/trade | t | No-carry R | 2× cost R | Random 95% R | Evidence avg R | Unresolved |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        *_metric_rows("Main: S3, 2 ATR / 3R", main),
        *_metric_rows("Stage 2 walk-forward", model),
    ]
    for title, version in (("Main version", main), ("Stage 2 version", model)):
        lines += ["", f"## {title}: per market", "",
                  "| Market | Trades | Net R | t | No-carry R | 2× cost R |",
                  "|---|---:|---:|---:|---:|---:|"]
        for market, item in version["per_market"].items():
            lines.append(f"| {market} | {item['trades']} | {_fmt(item['net_R'])} | "
                         f"{_fmt(item['t_stat'])} | {_fmt(item['no_carry_R'])} | "
                         f"{_fmt(item['double_cost_R'])} |")
        lines += ["", f"## {title}: traded markets per year", "",
                  "| Year | Trades | Net R | t | No-carry R | 2× cost R |",
                  "|---|---:|---:|---:|---:|---:|"]
        for year, item in version["per_year"].items():
            lines.append(f"| {year} | {item['trades']} | {_fmt(item['net_R'])} | "
                         f"{_fmt(item['t_stat'])} | {_fmt(item['no_carry_R'])} | "
                         f"{_fmt(item['double_cost_R'])} |")
    lines += ["", "## Stage 2 model audit", "",
              "| Predicted year | Training rows | Latest training exit |",
              "|---|---:|---|",
              *[f"| {item['year']} | {item['training_rows']} | {item['latest_training_exit']} |"
                for item in model["models"]], "",
              "The JSON report contains all summaries, selection counts, unresolved counts, "
              "model settings, and opportunity-drop audit fields.", ""]
    return "\n".join(lines)


def _ensure_once(output: Path, ledger: Path) -> None:
    final_files = (output / "final.md", output / "final.json")
    if any(path.exists() for path in final_files):
        raise FileExistsError("FINAL output already exists; refusing to rerun")
    if ledger.exists():
        text = ledger.read_text(errors="strict")
        if MAIN_TRIAL_ID in text or MODEL_TRIAL_ID in text:
            raise RuntimeError("FINAL trial row already exists; refusing to rerun")


def _append_trials(ledger: Path, result: dict) -> None:
    rows = []
    for trial_id, version, rule in (
        (MAIN_TRIAL_ID, result["main"], "S3;SL=2ATR;TP=3R"),
        (MODEL_TRIAL_ID, result["stage2"], "S3;LightGBM net-R;12 options;threshold=0.05R;walk-forward"),
    ):
        pooled = version["pooled_traded"]
        rows.append([
            trial_id, pd.Timestamp.now(tz="UTC").date().isoformat(),
            hashlib.sha256(f"{trial_id}:section11".encode()).hexdigest(), "swing_v1_final",
            rule, "FINAL>=2025-01-01", "final",
            json.dumps({"net_R": pooled["net_R"], "t": pooled["t_stat"],
                        "trades": pooled["trades"],
                        "unresolved": version["unresolved_at_end_total"]}),
            version["verdict"],
        ])
    with ledger.open("a", newline="") as handle:
        csv.writer(handle, lineterminator="\r\n").writerows(rows)


def run(data_root: Path, output: Path, ledger: Path) -> dict:
    _ensure_once(output, ledger)
    result = {
        "protocol": "docs/swing_v1_design.md section 11",
        "score_start": SCORE_START.isoformat(),
        "main": _main_version(data_root),
        "stage2": _stage2_version(data_root),
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "final.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    (output / "final.md").write_text(markdown(result))
    _append_trials(ledger, result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--output", type=Path, default=Path("reports/research/swing_v1"))
    parser.add_argument("--ledger", type=Path, default=Path("reports/trials.csv"))
    parser.add_argument("--run-final-once", action="store_true",
                        help="required acknowledgement that this consumes the one final evaluation")
    args = parser.parse_args()
    if not args.run_final_once:
        parser.error("--run-final-once is required")
    result = run(args.data_root, args.output, args.ledger)
    print(result["main"]["verdict"])


if __name__ == "__main__":
    main()
