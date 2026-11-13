"""Deterministically reproduce frozen family signals, then fix one diagnostic.

The rerun uses the unchanged Phase-2 family configuration and never appends to
the trial ledger.  Corrected random percentiles are accepted only after every
unit reproduces the original OOF row count and selected-signal metrics.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
import pandas as pd

from .family import SYMBOLS
from .family_random_v2 import FAMILIES,run as correct_random


FLOAT_FIELDS=("net_avg_R","hit_rate","brier")


def _same(left, right) -> bool:
    if left is None or right is None:return left is None and right is None
    return bool(np.isclose(float(left),float(right),rtol=1e-10,atol=1e-12,equal_nan=True))


def compare_jobs(original: dict, rerun: dict) -> dict:
    row={"family":original["family"],"symbol":original["symbol"],
         "original_oof_n":original["candidates"],"rerun_oof_n":rerun["candidates"],
         "original_signal_n":original["pooled"]["n"],"rerun_signal_n":rerun["pooled"]["n"]}
    row["oof_n_match"]=original["candidates"]==rerun["candidates"]
    row["signal_n_match"]=original["pooled"]["n"]==rerun["pooled"]["n"]
    for field in FLOAT_FIELDS:
        row[f"original_{field}"]=original["pooled"].get(field)
        row[f"rerun_{field}"]=rerun["pooled"].get(field)
        row[f"{field}_match"]=_same(row[f"original_{field}"],row[f"rerun_{field}"])
    row["deterministic"]=all(row[key] for key in
        ("oof_n_match","signal_n_match",*(f"{field}_match" for field in FLOAT_FIELDS)))
    return row


def _sha256(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def _card_unit(output: Path, family: str, symbol: str) -> dict:
    path=output/"cards"/f"phase2_{family}_{symbol}_dev.json"
    card=json.loads(path.read_text());pooled=card["pooled"]
    accounting=pooled.get("row_accounting",{})
    if "assembled_rows" not in accounting:
        raise ValueError(f"original card lacks OOF row accounting: {path}")
    return {"family":family,"symbol":symbol,"candidates":accounting["assembled_rows"],
            "pooled":pooled}


def _write_determinism(path: Path, rows: list[dict], ledger_unchanged: bool) -> None:
    table=pd.DataFrame(rows);table.to_csv(path.with_suffix(".csv"),index=False)
    lines=["# Phase 2 family signal determinism rerun","",
        "Frozen Family 3–5 configs were rerun solely to recover the previously unpersisted selected OOF signals. No model, threshold, feature, gate, label or seed changed. No trial-ledger row was appended.","",
        f"Ledger unchanged: {'yes' if ledger_unchanged else 'NO'}. All 15 units deterministic: {'yes' if table.deterministic.all() else 'NO'}.","",
        "| Family | Market | OOF rows | Signals | Net R match | Hit match | Brier match | Deterministic |",
        "|---|---|---:|---:|---|---|---|---|"]
    for row in rows:
        lines.append(f"| {row['family']} | {row['symbol']} | {row['rerun_oof_n']:,} | {row['rerun_signal_n']:,} | "
                     f"{'yes' if row['net_avg_R_match'] else 'NO'} | {'yes' if row['hit_rate_match'] else 'NO'} | "
                     f"{'yes' if row['brier_match'] else 'NO'} | {'yes' if row['deterministic'] else 'NO'} |")
    path.write_text("\n".join(lines)+"\n")


def run(data_root: Path, labels_root: Path, original_output: Path,
        rerun_root: Path, ledger: Path, seeds: int=200) -> pd.DataFrame:
    signals_root=rerun_root/"signals";rerun_output=rerun_root/"reports";logs=rerun_root/"logs"
    signals_root.mkdir(parents=True,exist_ok=True);logs.mkdir(parents=True,exist_ok=True)
    ledger_before=_sha256(ledger);rows=[]
    for family in FAMILIES:
        for symbol in SYMBOLS:
            command=[sys.executable,"-m","msd.research.family","--family",family,"--symbol",symbol,
                "--data-root",str(data_root),"--labels-root",str(labels_root),"--output",str(rerun_output),
                "--ledger",str(ledger),"--random-seeds",str(seeds),"--no-ledger",
                "--persist-signals-root",str(signals_root),"--skip-random-benchmark"]
            with (logs/f"{family}_{symbol}.log").open("w") as stream:
                subprocess.run(command,stdout=stream,stderr=subprocess.STDOUT,check=True)
            original=_card_unit(original_output,family,symbol)
            rerun=_card_unit(rerun_output,family,symbol)
            rows.append(compare_jobs(original,rerun))
    ledger_unchanged=_sha256(ledger)==ledger_before
    _write_determinism(rerun_root/"families_rerun_determinism.md",rows,ledger_unchanged)
    if not ledger_unchanged:raise RuntimeError("trial ledger changed during diagnostic rerun")
    failures=[row for row in rows if not row["deterministic"]]
    if failures:raise RuntimeError(f"family rerun was not deterministic for {len(failures)} units")
    return correct_random(data_root,signals_root,original_output,seeds=seeds)


def main() -> None:
    parser=argparse.ArgumentParser()
    parser.add_argument("--data-root",type=Path,required=True)
    parser.add_argument("--labels-root",type=Path)
    parser.add_argument("--original-output",type=Path,default=Path("reports/research/phase2_v1"))
    parser.add_argument("--rerun-root",type=Path,default=Path("reports/research/phase2_v1_rerun_signals"))
    parser.add_argument("--ledger",type=Path,default=Path("reports/trials.csv"))
    parser.add_argument("--seeds",type=int,default=200)
    args=parser.parse_args();labels=args.labels_root or args.data_root/"labels_wide_v1"
    result=run(args.data_root,labels,args.original_output,args.rerun_root,args.ledger,args.seeds)
    nq=result[(result.family=="f4_regime")&(result.symbol=="USATECHIDXUSD")].iloc[0]
    print(json.dumps({"units":len(result),"f4_nq_random_pct_v2":nq.random_pct_v2,
                      "f4_nq_random_pass_v2":bool(nq.random_pass_v2)}),flush=True)


if __name__=="__main__":main()
