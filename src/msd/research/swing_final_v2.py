"""One-time S1/S2 final check from frozen final_check_v2 Part A."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

import pandas as pd

from msd.research import swing_final as base
from msd.research import swing_stage1 as s1

TRIALS = (("S1", "swing-v1-final-s1"), ("S2", "swing-v1-final-s2"))


def _rule(data_root: Path, setup: str) -> dict:
    rows_by_market = {}
    random_by_market = {}
    unresolved = {}
    for market in (*s1.TRADED, *s1.EVIDENCE):
        bars = s1.load_minutes(data_root, market, period=base.WARMUP_PERIOD)
        rows, drops = s1.evaluate_market(
            bars, market, primary_only=True, period=base.WARMUP_PERIOD, setups=(setup,)
        )
        rows_by_market[market] = rows
        unresolved[market] = drops["unresolved_at_cutoff"]
        if market in s1.TRADED:
            random_by_market[market] = s1.baseline(bars, rows, market)
        print(f"{setup} {market}: {len(rows)} scored trades", flush=True)
    result = base._version_summary(
        rows_by_market, base._random_percentile(random_by_market, rows_by_market),
        unresolved, rule=f"{setup};SL=2ATR;TP=3R",
        score_start=base.SCORE_START.isoformat(), warmup_start=base.WARMUP_START.isoformat(),
    )
    value = result["pooled_traded"]["net_R"]
    result["verdict"] = "KEEP" if value is not None and value > 0 else "DROP"
    return result


def markdown(result: dict) -> str:
    lines = ["# Swing v1 FINAL check — S1 and S2", "",
             "Frozen protocol: docs/final_check_v2.md Part A. Each rule is graded separately; "
             "KEEP iff pooled traded-market net R per trade is positive.", "",
             "| Rule | Verdict | Trades | Net R/trade | t | No-carry R | 2× cost R | Random 95% R | Evidence avg R | Unresolved |",
             "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for setup, _ in TRIALS:
        item = result[setup]
        pooled = item["pooled_traded"]
        vals = [setup, item["verdict"], pooled["trades"], pooled["net_R"], pooled["t_stat"],
                pooled["no_carry_R"], pooled["double_cost_R"],
                item["random_direction_95pct_R"], item["evidence_market_average_R"],
                item["unresolved_at_end_total"]]
        lines.append("| " + " | ".join(base._fmt(x) for x in vals) + " |")
        lines += ["", f"## {setup} per market", "",
                  "| Market | Trades | Net R | t | No-carry R | 2× cost R |",
                  "|---|---:|---:|---:|---:|---:|"]
        for market, metric in item["per_market"].items():
            lines.append(f"| {market} | {metric['trades']} | {base._fmt(metric['net_R'])} | "
                         f"{base._fmt(metric['t_stat'])} | {base._fmt(metric['no_carry_R'])} | "
                         f"{base._fmt(metric['double_cost_R'])} |")
        lines += ["", f"## {setup} traded markets per year", "",
                  "| Year | Trades | Net R | t | No-carry R | 2× cost R |",
                  "|---|---:|---:|---:|---:|---:|"]
        for year, metric in item["per_year"].items():
            lines.append(f"| {year} | {metric['trades']} | {base._fmt(metric['net_R'])} | "
                         f"{base._fmt(metric['t_stat'])} | {base._fmt(metric['no_carry_R'])} | "
                         f"{base._fmt(metric['double_cost_R'])} |")
    lines += ["", "Evidence-market metrics and all audit details are in final_s1_s2.json.", ""]
    return "\n".join(lines)


def run(data_root: Path, output: Path, ledger: Path) -> dict:
    md_path, json_path = output / "final_s1_s2.md", output / "final_s1_s2.json"
    if md_path.exists() or json_path.exists():
        raise FileExistsError("S1/S2 final output exists; refusing rerun")
    prior = ledger.read_text() if ledger.exists() else ""
    if any(trial_id in prior for _, trial_id in TRIALS):
        raise RuntimeError("S1/S2 final trial row exists; refusing rerun")
    result = {"protocol": "docs/final_check_v2.md Part A",
              "score_start": base.SCORE_START.isoformat()}
    for setup, _ in TRIALS:
        result[setup] = _rule(data_root, setup)
    output.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    md_path.write_text(markdown(result))
    with ledger.open("a", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\r\n")
        for setup, trial_id in TRIALS:
            item = result[setup]
            pooled = item["pooled_traded"]
            writer.writerow([trial_id, pd.Timestamp.now(tz="UTC").date().isoformat(),
                hashlib.sha256(f"{trial_id}:final_check_v2:part_a".encode()).hexdigest(),
                "swing_v1_final", item["rule"], "FINAL>=2025-01-01", "final",
                json.dumps({"net_R": pooled["net_R"], "t": pooled["t_stat"],
                            "trades": pooled["trades"],
                            "unresolved": item["unresolved_at_end_total"]}), item["verdict"]])
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--output", type=Path, default=Path("reports/research/swing_v1"))
    parser.add_argument("--ledger", type=Path, default=Path("reports/trials.csv"))
    parser.add_argument("--run-final-once", action="store_true")
    args = parser.parse_args()
    if not args.run_final_once:
        parser.error("--run-final-once is required")
    result = run(args.data_root, args.output, args.ledger)
    print(" ".join(f"{setup}={result[setup]['verdict']}" for setup, _ in TRIALS))


if __name__ == "__main__":
    main()
