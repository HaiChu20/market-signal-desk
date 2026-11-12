"""Read-only DEV diagnostics for the protocol-v2 tournament's silence."""
from __future__ import annotations

import argparse
import gc
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from .dataset import DEV_END, load_method
from .method_registry import load_registry
from .models import fit_time_ordered
from .splits import cpcv_folds
from .tournament import CONFIG, validate_schema

SYMBOLS = ("BTCUSDT", "USATECHIDXUSD", "USA500IDXUSD", "XAUUSD")
MARKET = {"BTCUSDT": "BTC", "USATECHIDXUSD": "NQ", "USA500IDXUSD": "SPX", "XAUUSD": "XAU"}
SL_VALUES = (0.5, 1.0, 1.5, 2.0, 3.0)
SKILL_UNITS = ("rsi2_mean_reversion", "supply_demand_zone_retest", "trend_following",
               "fvg_retrace", "liquidity_sweep")


def _read_month(root: Path, sym: str, stem: str, columns: list[str]) -> pd.DataFrame:
    path = root / sym / f"{stem}.parquet"
    if not path.exists():
        return pd.DataFrame(columns=columns)
    available = set(pq.read_schema(path).names)
    return pd.read_parquet(path, columns=[c for c in columns if c in available])


def _cost_month(data_root: Path, sym: str, path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    columns = ["ts", "entry_ts", "exit_ts", "side", "sl_atr", "tp_atr", "planned_risk",
               "gross_R", "net_R", "financing_nights"]
    labels = pd.read_parquet(path, columns=columns)
    labels["ts"] = pd.to_datetime(labels.ts, utc=True)
    labels["exit_ts"] = pd.to_datetime(labels.exit_ts, utc=True)
    labels = labels[(labels.ts < DEV_END) & (labels.exit_ts < DEV_END) &
                    labels.sl_atr.isin(SL_VALUES)].copy()
    if labels.empty:
        return labels, labels
    features = _read_month(data_root / "features", sym, path.stem,
                           ["ts", "spread_atr", "1m_atr14"])
    features["ts"] = pd.to_datetime(features.ts, utc=True)
    labels = labels.merge(features, on="ts", how="left", validate="many_to_one")
    labels["spread_R"] = (labels.spread_atr * labels["1m_atr14"] /
                          labels.planned_risk).clip(lower=0)
    labels["financing_R"] = (labels.gross_R - labels.net_R).clip(lower=0)
    labels["cost_R"] = labels.spread_R + labels.financing_R
    labels["market"] = MARKET[sym]
    keys = pd.DataFrame({"ts": labels.ts.astype(str), "entry_ts": labels.entry_ts.astype(str),
                         "side": labels.side, "sl": labels.sl_atr, "tp": labels.tp_atr})
    labels["sample_hash"] = pd.util.hash_pandas_object(keys, index=False).astype("uint64")
    sample = labels.nsmallest(40, "sample_hash").copy()
    return labels, sample


def cost_diagnostic(data_root: Path, output: Path) -> dict:
    sums: dict[tuple, np.ndarray] = {}
    samples = []
    for sym in SYMBOLS:
        for path in sorted((data_root / "labels" / sym).glob("*.parquet")):
            if path.stem[:4] > "2022":
                continue
            frame, sample = _cost_month(data_root, sym, path)
            for key, group in frame.groupby(["market", "sl_atr", "tp_atr"], observed=True):
                values = np.array([len(group), group.gross_R.sum(), group.cost_R.sum(),
                                   group.net_R.sum()], dtype=float)
                sums[key] = sums.get(key, np.zeros(4)) + values
            samples.append(sample)
            del frame
            gc.collect()
    cells = [{"market": k[0], "sl_atr": float(k[1]), "tp_atr": float(k[2]), "n": int(v[0]),
              "mean_gross_R": v[1]/v[0], "mean_cost_R": v[2]/v[0], "mean_net_R": v[3]/v[0]}
             for k, v in sorted(sums.items())]
    sample = pd.concat(samples, ignore_index=True).sort_values("sample_hash").groupby("market").head(100)
    sanity = cost_sanity(data_root, sample)
    best = {}
    for market in MARKET.values():
        rows = [row for row in cells if row["market"] == market]
        best[market] = max(rows, key=lambda row: row["mean_net_R"])
    result = {"cells": cells, "best_fixed": best, "cost_sanity": sanity,
              "note": "gross_R already uses executable bid/ask; cost_R here is the ex-ante entry spread plus realized financing, while net_R is the persisted executable result."}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, allow_nan=False))
    return result


def cost_sanity(data_root: Path, sample: pd.DataFrame) -> list[dict]:
    rows = []
    for market, group in sample.groupby("market"):
        sym = next(s for s, name in MARKET.items() if name == market)
        direct = []
        for stem, month in group.groupby(pd.to_datetime(group.entry_ts, utc=True).dt.strftime("%Y-%m")):
            venue = "binance_spot" if sym == "BTCUSDT" else "dukascopy"
            bars = _read_month(data_root / "bars" / venue, sym, stem,
                               ["ts", "bid_o", "ask_o"])
            bars["ts"] = pd.to_datetime(bars.ts, utc=True)
            part = month.copy()
            part["entry_ts"] = pd.to_datetime(part.entry_ts, utc=True)
            part = part.merge(bars.rename(columns={"ts": "entry_ts"}), on="entry_ts", how="left")
            part["direct_spread_R"] = (part.ask_o - part.bid_o) / part.planned_risk
            direct.append(part)
        checked = pd.concat(direct, ignore_index=True)
        ratio = checked.spread_R / checked.direct_spread_R.replace(0, np.nan)
        finite = ratio[np.isfinite(ratio)]
        median_ratio = float(finite.median()) if len(finite) else None
        flag = ("raw bid/ask has no usable spread" if median_ratio is None else
                "unit/scale mismatch" if not 0.5 <= median_ratio <= 2.0 else "consistent scale")
        rows.append({"market": market, "n": int(len(checked)),
                     "direct_spread_R_mean": _finite_mean(checked.direct_spread_R),
                     "feature_cost_R_mean": _finite_mean(checked.spread_R),
                     "feature_to_direct_median": median_ratio, "flag": flag})
    return rows


def _finite_mean(values) -> float | None:
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    return float(values.mean()) if len(values) else None


def skill_diagnostic(unit: str, data_root: Path, output_dir: Path) -> dict:
    spec = next(item for item in load_registry() if item.key == unit)
    frame, _, _ = load_method(unit, data_root, symbols=spec.symbols, return_audit=True)
    frame = frame.sort_values("known_at", kind="stable").reset_index(drop=True)
    validate_schema(frame, spec)
    total = np.zeros(len(frame)); base_total = np.zeros(len(frame)); count = np.zeros(len(frame), dtype=np.int16)
    cell = pd.MultiIndex.from_arrays([frame.sym, frame.exit_kind.astype(str)])
    for fold in cpcv_folds(frame, CONFIG["cpcv_groups"], CONFIG["cpcv_test_groups"]):
        train = frame.iloc[fold.train]; test = frame.iloc[fold.test]
        model = fit_time_ordered(train)
        total[fold.test] += model.predict(test)
        rates = train.groupby(["sym", train.exit_kind.astype(str)], observed=True).tp_first.mean()
        fallback = float(train.tp_first.mean())
        base_total[fold.test] += pd.Series(cell[fold.test].map(rates), dtype=float).fillna(fallback).to_numpy()
        count[fold.test] += 1
        del model, train, test
        gc.collect()
    if (count == 0).any():
        raise RuntimeError(f"{unit}: incomplete CPCV predictions")
    out = frame[["sym", "known_at", "event_key", "exit_kind", "TP_R", "p0", "tp_first",
                 "cost_R", "financing_R", "net_R"]].copy()
    out["p"] = (total/count).astype("float32")
    out["cell_p"] = (base_total/count).astype("float32")
    out["predicted_edge_R"] = (out.p*out.TP_R - (1-out.p) - out.cost_R - out.financing_R).astype("float32")
    y = out.tp_first.to_numpy(float); p = out.p.to_numpy(float)
    brier = float(np.mean((p-y)**2)); p0_brier = float(np.mean((out.p0-y)**2))
    cell_brier = float(np.mean((out.cell_p-y)**2))
    ranked = out.predicted_edge_R.rank(method="first")
    out["edge_decile"] = pd.qcut(ranked, 10, labels=False) + 1
    deciles = out.groupby("edge_decile", observed=True).agg(
        n=("net_R", "size"), mean_predicted_edge_R=("predicted_edge_R", "mean"),
        mean_net_R=("net_R", "mean")).reset_index().to_dict("records")
    output_dir.mkdir(parents=True, exist_ok=True)
    prediction_path = output_dir / f"{unit}_oof.parquet"
    out.to_parquet(prediction_path, index=False, compression="zstd")
    digest = hashlib.sha256(prediction_path.read_bytes()).hexdigest()
    result = {"unit": unit, "n": len(out), "brier": brier,
              "brier_skill_vs_p0": 1-brier/p0_brier,
              "brier_skill_vs_cell_base_rate": 1-brier/cell_brier,
              "edge_gt_0_05": int((out.predicted_edge_R > CONFIG["threshold"]).sum()),
              "edge_deciles": deciles, "predictions": str(prediction_path), "predictions_sha256": digest}
    (output_dir / f"{unit}.json").write_text(json.dumps(result, indent=2, allow_nan=False))
    return result


def render_report(work_dir: Path, output: Path) -> None:
    costs = json.loads((work_dir / "costs.json").read_text())
    skills = [json.loads((work_dir / f"{unit}.json").read_text()) for unit in SKILL_UNITS]
    lines = ["# Why protocol-v2 DEV is silent", "", "**PRELIMINARY diagnostic. Development data only; Test and Final were not loaded.**", "",
             "No trading rule, threshold, model configuration, or trial-ledger row was changed.", "",
             "## Conclusion", "", _conclusion(costs, skills), "", "## Cost versus gross", "",
             costs["note"], "", "| Market | SL ATR | TP ATR | n | Mean gross R | Mean cost R | Mean net R |",
             "|---|---:|---:|---:|---:|---:|---:|"]
    for row in costs["cells"]:
        lines.append(f"| {row['market']} | {row['sl_atr']:.1f} | {row['tp_atr']:.1f} | {row['n']:,} | {row['mean_gross_R']:.4f} | {row['mean_cost_R']:.4f} | {row['mean_net_R']:.4f} |")
    lines += ["", "### Best fixed cell per market", "", "| Market | SL ATR | TP ATR | n | Mean gross R | Mean cost R | Mean net R |", "|---|---:|---:|---:|---:|---:|---:|"]
    for market, row in costs["best_fixed"].items():
        lines.append(f"| {market} | {row['sl_atr']:.1f} | {row['tp_atr']:.1f} | {row['n']:,} | {row['mean_gross_R']:.4f} | {row['mean_cost_R']:.4f} | {row['mean_net_R']:.4f} |")
    lines += ["", "## Cost sanity", "", "| Market | n | Direct spread/R | Feature spread/R | Feature/direct median | Assessment |", "|---|---:|---:|---:|---:|---|"]
    for row in costs["cost_sanity"]:
        ratio = "NA" if row["feature_to_direct_median"] is None else f"{row['feature_to_direct_median']:.3f}"
        lines.append(f"| {row['market']} | {row['n']} | {row['direct_spread_R_mean'] or 0:.4f} | {row['feature_cost_R_mean'] or 0:.4f} | {ratio} | {row['flag']} |")
    lines += ["", "## Frozen-model skill", "", "| Unit | candidates | Brier skill vs p0 | Brier skill vs cell base | edge > 0.05R |", "|---|---:|---:|---:|---:|"]
    for row in skills:
        lines.append(f"| {row['unit']} | {row['n']:,} | {row['brier_skill_vs_p0']:.4f} | {row['brier_skill_vs_cell_base_rate']:.4f} | {row['edge_gt_0_05']:,} |")
    for row in skills:
        lines += ["", f"### {row['unit']}: edge deciles", "", "| Decile | n | Mean predicted edge R | Mean realized net R |", "|---:|---:|---:|---:|"]
        for decile in row["edge_deciles"]:
            lines.append(f"| {decile['edge_decile']} | {decile['n']:,} | {decile['mean_predicted_edge_R']:.4f} | {decile['mean_net_R']:.4f} |")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + "\n")


def _conclusion(costs: dict, skills: list[dict]) -> str:
    negative = sum(row["mean_net_R"] < 0 for row in costs["best_fixed"].values())
    genuine = sum(row["brier_skill_vs_cell_base_rate"] > 0 for row in skills)
    return (f"The silence is attributable to both economics and limited incremental ranking skill: "
            f"{negative}/4 markets have a negative best fixed label-grid cell, while only {genuine}/5 "
            "frozen models beat a fold-trained geometry-cell base rate. The cost-sanity table determines "
            "whether the economic conclusion is genuine or contaminated by a spread unit mismatch.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--work-dir", type=Path, default=Path("data/silence_diagnostic"))
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--costs", action="store_true")
    group.add_argument("--skill", choices=SKILL_UNITS)
    group.add_argument("--report", action="store_true")
    args = parser.parse_args()
    if args.costs:
        cost_diagnostic(args.data_root, args.work_dir / "costs.json")
    elif args.skill:
        skill_diagnostic(args.skill, args.data_root, args.work_dir)
    else:
        render_report(args.work_dir, Path("reports/research/dev_v2/silence_diagnostic.md"))


if __name__ == "__main__":
    main()
