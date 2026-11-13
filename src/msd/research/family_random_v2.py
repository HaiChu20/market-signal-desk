"""Correct Phase-2 family random-direction percentiles from saved signals.

This is deliberately diagnostic-only.  It never fits a model, chooses a
signal, or writes the trial ledger.  Input parquet files must be the exact OOF
signals selected by the original family run.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .benchmark import random_direction
from .family import SYMBOLS


DEV_END = pd.Timestamp("2023-01-01", tz="UTC")
FAMILIES = ("f3_order_flow", "f4_regime", "f5_cross_market")
REQUIRED = ("sym", "ts", "side", "price", "sl", "tp", "deadline_ts", "net_R")
SECTION = "## Random-direction percentile correction v2"
SUPPLEMENTAL_THRESHOLD = 95.0


def _signals(path: Path, family: str, symbol: str) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(
            f"Saved OOF signals are required (models will not be refit): {path}"
        )
    frame = pd.read_parquet(path)
    missing = sorted(set(REQUIRED) - set(frame))
    if missing:
        raise ValueError(f"{path} missing signal columns: {missing}")
    frame = frame.loc[:, REQUIRED].copy()
    frame["ts"] = pd.to_datetime(frame.ts, utc=True).astype("datetime64[ns, UTC]")
    frame["deadline_ts"] = pd.to_datetime(frame.deadline_ts, utc=True).astype("datetime64[ns, UTC]")
    if frame.ts.ge(DEV_END).any() or frame.deadline_ts.ge(DEV_END).any():
        raise ValueError(f"{family}/{symbol} saved signals include 2023+ data")
    if not frame.sym.astype(str).eq(symbol).all():
        raise ValueError(f"{path} contains a symbol other than {symbol}")
    return frame


def _fmt(value) -> str:
    return "NA" if value is None or not np.isfinite(value) else f"{value:.4f}"


def write_correction(summary: Path, rows: list[dict], signals_root: Path) -> None:
    original = summary.read_text()
    if SECTION in original:
        original = original.split(SECTION, 1)[0].rstrip() + "\n"
    lines = ["", SECTION, "",
        f"The original Family 3–5 random-direction percentiles used a broken microsecond timestamp conversion. The table below is the benchmark-only correction from the deterministically reproduced OOF signals stored under `{signals_root}`. Frozen configs, model fits, thresholds, features, gates, selected-signal metrics and labels were unchanged. This diagnostic rerun appended **no trial-ledger rows** because it is not a new configuration.", "",
        "The original Family 3–5 summary displayed random percentile as a diagnostic but defined no random-percentile pass threshold; its pass flag was Brier skill versus the cell base rate > 0 and net R > 0. Accordingly the original-threshold verdict is N/A. The ≥95 column is a clearly labelled supplemental check, not a retroactive protocol criterion.","",
        "| Family | Market | Signals | Original pct (invalid) | Corrected pct | Original-threshold verdict | Supplemental pct ≥95 |",
        "|---|---|---:|---:|---:|---|---|"]
    for row in rows:
        lines.append(f"| {row['family']} | {row['symbol']} | {row['signals']} | "
                     f"{_fmt(row['original_random_pct'])} | {_fmt(row['random_pct_v2'])} | N/A | "
                     f"{'yes' if row['random_pass_95'] else 'no'} |")
    summary.write_text(original + "\n".join(lines) + "\n")


def run(data_root: Path, signals_root: Path, output: Path, seeds: int = 200) -> pd.DataFrame:
    jobs = output / "jobs"
    rows=[]
    for family in FAMILIES:
        for symbol in SYMBOLS:
            job_path=jobs/f"{family}_{symbol}.json"
            if not job_path.exists():raise FileNotFoundError(job_path)
            job=json.loads(job_path.read_text())
            signals=_signals(signals_root/f"{family}_{symbol}.parquet",family,symbol)
            percentile,matched,_=random_direction(signals,data_root,seeds=seeds)
            if matched!=len(signals):
                raise RuntimeError(f"{family}/{symbol}: benchmark matched {matched}/{len(signals)} signals")
            old=job["pooled"].get("random_direction_percentile")
            rows.append({"family":family,"symbol":symbol,"signals":len(signals),
                "original_random_pct":old,"random_pct_v2":percentile,
                "original_random_threshold":None,"original_random_pass":None,
                "random_pass_95":bool(percentile is not None and percentile>=SUPPLEMENTAL_THRESHOLD)})
    result=pd.DataFrame(rows)
    output.mkdir(parents=True,exist_ok=True)
    result.to_csv(output/"families_random_pct_v2.csv",index=False)
    write_correction(output/"families_summary.md",rows,signals_root)
    return result


def main() -> None:
    parser=argparse.ArgumentParser()
    parser.add_argument("--data-root",type=Path,required=True)
    parser.add_argument("--signals-root",type=Path,required=True)
    parser.add_argument("--output",type=Path,default=Path("reports/research/phase2_v1"))
    parser.add_argument("--seeds",type=int,default=200)
    args=parser.parse_args()
    result=run(args.data_root,args.signals_root,args.output,args.seeds)
    nq=result[(result.family=="f4_regime")&(result.symbol=="USATECHIDXUSD")].iloc[0]
    print(json.dumps({"rows":len(result),"f4_nq_random_pct_v2":nq.random_pct_v2,
                      "f4_nq_original_threshold_pass":None,
                      "f4_nq_supplemental_pass_95":bool(nq.random_pass_95)}),flush=True)


if __name__=="__main__":main()
