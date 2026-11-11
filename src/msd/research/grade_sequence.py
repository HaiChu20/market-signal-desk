"""Grade returned DEV-only sequence OOF predictions on the laptop."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from msd.research.gating import gate_open_signals
from msd.research.benchmark import random_direction
from msd.research.dataset import DEV_END
from msd.research.decision import choose
from msd.research.report_card import report

REQUIRED = {"known_at", "label_end_ts", "side", "sl", "tp", "p", "p0",
            "tp_first", "net_R", "cost_R", "financing_R", "TP_R",
            "entry_ts", "price", "sym", "event_key", "candidate_id",
            "config_sha256", "fold", "seed"}


def grade(input_dir: Path, *, data_root: Path = Path("data"), output: Path | None = None):
    files = sorted(Path(input_dir).rglob("oof.parquet"))
    if not files:
        raise FileNotFoundError(f"No OOF predictions under {input_dir}")
    tables = []
    for path in files:
        frame = pd.read_parquet(path)
        if not REQUIRED <= set(frame):
            raise ValueError(f"{path} lacks {sorted(REQUIRED - set(frame))}")
        stamp = path.parent.parent / "config_sha256.txt"
        if stamp.exists() and (frame.config_sha256.nunique() != 1 or
                               frame.config_sha256.iloc[0] != stamp.read_text().strip()):
            raise ValueError(f"Config SHA mismatch: {path}")
        tables.append(frame)
    all_rows = pd.concat(tables, ignore_index=True)
    if (pd.to_datetime(all_rows.known_at, utc=True).ge(DEV_END).any() or
            pd.to_datetime(all_rows.label_end_ts, utc=True).ge(DEV_END).any()):
        raise ValueError("TEST/FINAL rows or unresolved DEV labels in OOF input")
    if all_rows.duplicated(["sym", "seed", "known_at", "side", "sl", "tp"]).any():
        raise ValueError("Duplicate OOF candidate")
    destination = output or Path(input_dir) / "grade"
    results = {}
    for (symbol, seed, config_sha), candidates in all_rows.groupby(["sym", "seed", "config_sha256"]):
        candidates = candidates.sort_values("known_at").reset_index(drop=True)
        signals = gate_open_signals(choose(candidates))
        random_percentile, random_n, manifest = random_direction(signals, Path(data_root))
        card = report(f"sequence_cnn_{symbol}_seed{seed}_{config_sha[:12]}", "dev",
                      signals, candidates, manifest, random_percentile=random_percentile,
                      random_n=random_n, output=destination)
        results[f"{symbol}:{seed}:{config_sha}"] = card
    (destination / "summary.json").write_text(json.dumps({key: value["pooled"] for key, value in results.items()},
                                                         indent=2, allow_nan=False))
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    cards = grade(args.input, data_root=args.data_root, output=args.output)
    print(json.dumps({key: {"n": card["pooled"]["n"],
                            "brier_skill_vs_p0": card["pooled"]["brier_skill_vs_p0"],
                            "net_avg_R": card["pooled"]["net_avg_R"]}
                      for key, card in cards.items()}, indent=2))


if __name__ == "__main__":
    main()
