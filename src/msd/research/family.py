"""Protocol-v2 DEV feature-family tournament over the frozen wide geometry grid.

The unit of validation is a 15-minute anchor.  Model fitting uses the hourly
subset of training anchors to keep the five-market run below 10 GiB RSS; every
15-minute test anchor still receives an out-of-fold prediction.  Test and Final
data are rejected, not silently filtered.
"""
from __future__ import annotations

import argparse
import gc
import hashlib
import json
from pathlib import Path
import resource
import sys
import time

import numpy as np
import pandas as pd
import pyarrow.dataset as pads
import pyarrow.parquet as pq

from .benchmark import random_direction
from .dataset import FORBIDDEN
from .decision import choose
from .gating import gate_open_signals
from .ledger import FIELDS, append_trial, read_trials
from .models import ResidualModel
from .report_card import metrics, report, trial_diagnostics
from .splits import cpcv_folds


DEV_END = pd.Timestamp("2023-01-01", tz="UTC")
SYMBOLS = ("USATECHIDXUSD", "USA500IDXUSD", "XAUUSD", "BTCUSDT", "ETHUSDT")
CONFIG_PATH = Path("config/research/phase2_families_v1.json")
MAX_RSS_GIB = 10.0
PREDICT_CHUNK = 250_000
MAX_TRAIN_ANCHORS = 25_000
THRESHOLD = 0.05
N_GROUPS = 5
N_TEST_GROUPS = 2

LABEL_COLUMNS = (
    "ts", "side", "sl_atr", "tp_r", "outcome", "net_R", "gross_R",
    "cost_R", "entry_ts", "exit_ts", "label_end_ts", "deadline_ts",
    "fill_price", "entry_price", "planned_risk", "financing_nights",
)


def load_config(path: Path = CONFIG_PATH) -> dict:
    config = json.loads(path.read_text())
    if config.get("protocol") != "phase2_family_v1":
        raise ValueError("Unexpected family protocol")
    if pd.Timestamp(config["development_end"]) != DEV_END:
        raise ValueError("Family runner must be locked to DEV ending 2022-12-31")
    return config


def _peak_rss_gib() -> float:
    value = float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return value / (1024 ** 3 if sys.platform == "darwin" else 1024 ** 2)


def _memory_guard() -> None:
    if _peak_rss_gib() > MAX_RSS_GIB:
        raise MemoryError(f"Phase-2 family runner exceeded {MAX_RSS_GIB:g} GiB RSS")


def _utc(values) -> pd.Series:
    return pd.to_datetime(values, utc=True).astype("datetime64[ns, UTC]")


def _schema_names(directory: Path) -> set[str]:
    path = next(iter(sorted(directory.glob("*.parquet"))), None)
    return set() if path is None else set(pq.read_schema(path).names)


def feature_spec(family: str, dense_schema: set[str], flow_schema: set[str], config: dict) -> dict:
    """Resolve the committed feature-group config without outcome-derived fields."""
    if family not in config["families"]:
        raise KeyError(family)
    item = config["families"][family]
    dense = list(item.get("dense_columns", ()))
    dense.extend(
        f"{timeframe}_{suffix}"
        for timeframe in item.get("timeframes", ())
        for suffix in item.get("timeframe_suffixes", ())
    )
    for prefix in item.get("dense_prefixes", ()):
        dense.extend(sorted(column for column in dense_schema if column.startswith(prefix)))
    dense = list(dict.fromkeys(dense))
    flow = list(dict.fromkeys(item.get("flow_columns", ())))
    source = dense + flow
    missing = [f"{column}__missing" for column in source] if item.get("add_missing_flags") else []
    model = source + missing + list(config["shared_geometry_features"])
    assert_no_outcome_features(model)
    if family == "f3_order_flow":
        raw = [column for column in flow if "_delta_" in column and "divergence" not in column]
        if raw:
            raise AssertionError(f"Raw, scale-dependent deltas configured: {raw}")
    return {"dense": dense, "flow": flow, "source": source, "model": model}


def assert_no_outcome_features(features) -> None:
    forbidden = set(FORBIDDEN) | {
        "outcome", "exit_kind", "exit_reason", "label", "label_2r", "R",
        "net_R", "gross_R", "cost_R", "tp_first", "label_end_ts",
    }
    bad = sorted(set(features) & forbidden)
    bad.extend(
        feature for feature in features
        if any(token in feature.lower() for token in ("outcome", "exit_price", "label_end"))
    )
    if bad:
        raise AssertionError(f"Outcome-derived family features: {sorted(set(bad))}")


def _read_labels(labels_root: Path, symbol: str) -> tuple[pd.DataFrame, list[dict]]:
    directory = labels_root / symbol
    paths = [path for path in sorted(directory.glob("*.parquet")) if path.stem <= "2022-12"]
    if not paths:
        raise FileNotFoundError(f"No wide-v1 labels for {symbol}: {directory}")
    manifest = []
    available = set(pq.read_schema(paths[0]).names)
    columns = [column for column in LABEL_COLUMNS if column in available]
    for path in paths:
        stat = path.stat()
        manifest.append({"path": str(path), "size": stat.st_size, "mtime_ns": stat.st_mtime_ns})
    table = pads.dataset([str(path) for path in paths], format="parquet").to_table(columns=columns)
    frame = table.to_pandas(split_blocks=True, self_destruct=True)
    required = {"ts", "side", "sl_atr", "tp_r", "outcome", "net_R", "gross_R",
                "planned_risk", "deadline_ts"}
    missing = required - set(frame)
    if missing:
        raise ValueError(f"Wide-v1 labels missing columns: {sorted(missing)}")
    frame["ts"] = _utc(frame.ts)
    frame["known_at"] = frame.ts + pd.Timedelta(minutes=1)
    end_column = "label_end_ts" if "label_end_ts" in frame else "exit_ts"
    frame["label_end_ts"] = _utc(frame[end_column])
    for column in ("entry_ts", "deadline_ts"):
        if column in frame:
            frame[column] = _utc(frame[column])
    if frame.known_at.ge(DEV_END).any() or frame.label_end_ts.ge(DEV_END).any():
        raise ValueError("DEV family labels include a decision or label_end at/after 2023-01-01")
    if not frame.ts.dt.minute.isin((0, 15, 30, 45)).all():
        raise ValueError("Wide-v1 labels contain non-15-minute anchors")
    if pd.api.types.is_numeric_dtype(frame.outcome):
        frame["tp_first"] = frame.outcome.eq(1).astype("int8")
    else:
        frame["tp_first"] = frame.outcome.astype(str).str.lower().eq("tp").astype("int8")
    frame["p0"] = (1.0 / (1.0 + pd.to_numeric(frame.tp_r))).astype("float32")
    frame["TP_R"] = pd.to_numeric(frame.tp_r).astype("float32")
    frame["SL_R"] = np.float32(1.0)
    frame["cost_R"] = pd.to_numeric(
        frame.cost_R if "cost_R" in frame else frame.gross_R - frame.net_R,
        errors="coerce",
    ).astype("float32")
    frame["financing_R"] = np.float32(0.0)
    frame["spread_R"] = frame.cost_R.clip(lower=0)
    frame["price"] = pd.to_numeric(
        frame.fill_price if "fill_price" in frame else frame.entry_price, errors="coerce"
    )
    frame["sl"] = frame.price - frame.side * frame.planned_risk
    frame["tp"] = frame.price + frame.side * frame.planned_risk * frame.tp_r
    frame["entry_ts"] = frame.get("entry_ts", frame.ts + pd.Timedelta(minutes=2))
    frame["sym"] = pd.Categorical(np.repeat(symbol, len(frame)))
    frame["candidate_id"] = np.arange(len(frame), dtype=np.int64)
    frame = frame.drop(columns=[column for column in ("outcome", "exit_ts", "fill_price", "entry_price")
                                if column in frame])
    keep = np.isfinite(frame.net_R) & np.isfinite(frame.gross_R) & frame.planned_risk.gt(0)
    frame = frame.loc[keep].sort_values(["ts", "side", "sl_atr", "tp_r"], kind="stable").reset_index(drop=True)
    frame["candidate_id"] = np.arange(len(frame), dtype=np.int64)
    for column in ("side", "tp_first"):
        frame[column] = frame[column].astype("int8")
    for column in ("sl_atr", "tp_r", "TP_R", "SL_R", "p0", "net_R", "gross_R",
                   "cost_R", "financing_R", "spread_R", "planned_risk"):
        frame[column] = pd.to_numeric(frame[column]).astype("float32")
    return frame, manifest


def causal_asof(left: pd.DataFrame, right: pd.DataFrame, columns: list[str], stamp: str) -> pd.DataFrame:
    """Backward join with an exposed source timestamp for causality tests."""
    result = left.sort_values("known_at", kind="stable").copy()
    result["known_at"] = _utc(result.known_at)
    if right.empty:
        result[stamp] = pd.NaT
        for column in columns:
            result[column] = np.nan
        return result
    source = right.copy()
    source["known_at"] = _utc(source.known_at)
    for column in columns:
        if column not in source:
            source[column] = np.nan
    source = source[["known_at", *columns]].sort_values("known_at", kind="stable")
    source = source.drop_duplicates("known_at", keep="last").rename(columns={"known_at": stamp})
    result = pd.merge_asof(result, source, left_on="known_at", right_on=stamp, direction="backward")
    if (result[stamp] > result.known_at).any():
        raise AssertionError(f"Future {stamp} joined")
    return result


def _read_feature_month(path: Path | None, columns: list[str]) -> tuple[pd.DataFrame, dict | None]:
    if path is None or not path.exists():
        return pd.DataFrame(columns=["known_at", *columns]), None
    available = set(pq.read_schema(path).names)
    read = ["known_at", *[column for column in columns if column in available]]
    frame = pd.read_parquet(path, columns=read)
    for column in columns:
        if column not in frame:
            frame[column] = np.nan
    stat = path.stat()
    return frame[["known_at", *columns]], {"path": str(path), "size": stat.st_size, "mtime_ns": stat.st_mtime_ns}


def load_anchor_features(data_root: Path, symbol: str, anchors: pd.DataFrame,
                         family: str, config: dict) -> tuple[pd.DataFrame, dict, list[dict]]:
    dense_dir = data_root / "features" / symbol
    flow_dir = data_root / "features_flow" / symbol
    spec = feature_spec(family, _schema_names(dense_dir), _schema_names(flow_dir), config)
    parts = []
    manifest = []
    work = anchors[["anchor_index", "ts", "known_at"]].copy()
    work["month"] = work.known_at.dt.strftime("%Y-%m")
    for month, left in work.groupby("month", sort=True):
        left = left.drop(columns="month").sort_values("known_at")
        dense, item = _read_feature_month(dense_dir / f"{month}.parquet", spec["dense"])
        if item: manifest.append(item)
        joined = causal_asof(left, dense, spec["dense"], "dense_known_at")
        flow, item = _read_feature_month(flow_dir / f"{month}.parquet", spec["flow"])
        if item: manifest.append(item)
        joined = causal_asof(joined, flow, spec["flow"], "flow_known_at")
        parts.append(joined)
    result = pd.concat(parts, ignore_index=True).sort_values("anchor_index").reset_index(drop=True)
    if len(result) != len(anchors) or not np.array_equal(result.anchor_index, anchors.anchor_index):
        raise RuntimeError("Feature join changed the anchor grid")
    ratios = {}
    for timeframe in config["families"][family].get("timeframes", ()):
        ratio = f"{timeframe}_atr_ratio14_50"
        if ratio in spec["source"]:
            numerator = pd.to_numeric(result[f"{timeframe}_atr14"], errors="coerce")
            denominator = pd.to_numeric(result[f"{timeframe}_atr50"], errors="coerce")
            ratios[ratio] = numerator.div(denominator.where(denominator > 0))
    if ratios:
        result = result.drop(columns=list(ratios)).join(pd.DataFrame(ratios, index=result.index))
    converted = pd.DataFrame(
        {column: pd.to_numeric(result[column], errors="coerce").astype("float32")
         for column in spec["source"]}, index=result.index)
    missing = pd.DataFrame(
        {f"{column}__missing": converted[column].isna().astype("int8")
         for column in spec["source"]}, index=result.index)
    result = pd.concat([result.drop(columns=spec["source"]), converted, missing], axis=1)
    return result, spec, manifest


MODEL_BASE_COLUMNS = ["anchor_index", "known_at", "label_end_ts", "p0", "tp_first", "event_key",
                      "side", "sl_atr", "tp_r", "net_R"]


def _materialize(labels: pd.DataFrame, indices: np.ndarray, feature_values: np.ndarray,
                 columns: list[str]) -> pd.DataFrame:
    base = labels.iloc[indices][MODEL_BASE_COLUMNS].reset_index(drop=True).copy()
    values = pd.DataFrame(feature_values[base.anchor_index.to_numpy()], columns=columns)
    return pd.concat([base, values], axis=1)


def _fit_fold(train: pd.DataFrame, features: list[str], kind: str) -> ResidualModel:
    """Fit then calibrate on a later, anchor-aligned slice of the CPCV training set."""
    times = np.array(sorted(train.known_at.unique()))
    if len(times) < 10:
        return ResidualModel(kind, features).fit(train)
    cal_start = pd.Timestamp(times[max(1, int(0.8 * len(times)))])
    fit = train[(train.known_at < cal_start) & (train.label_end_ts < cal_start)]
    cal = train[train.known_at >= cal_start]
    model = ResidualModel(kind, features).fit(fit if len(fit) else train)
    if len(cal):
        model.calibrate(cal)
    return model


def _cell_base_rates(train: pd.DataFrame) -> tuple[pd.Series, float]:
    cells = train.groupby(["side", "sl_atr", "tp_r"], observed=True).tp_first.mean()
    return cells, float(train.tp_first.mean())


def _cell_predict(frame: pd.DataFrame, cells: pd.Series, fallback: float) -> np.ndarray:
    index = pd.MultiIndex.from_frame(frame[["side", "sl_atr", "tp_r"]])
    return cells.reindex(index).fillna(fallback).to_numpy(float)


def _pbo(train_cells: list[np.ndarray], test_cells: list[np.ndarray]) -> float | None:
    failures = []
    for train, test in zip(train_cells, test_cells):
        valid = np.isfinite(train) & np.isfinite(test)
        if valid.sum() < 2:
            continue
        winner = np.flatnonzero(valid)[np.argmax(train[valid])]
        failures.append(float(test[winner] < np.nanmedian(test[valid])))
    return float(np.mean(failures)) if failures else None


def cpcv_oof(labels: pd.DataFrame, anchors: pd.DataFrame, feature_frame: pd.DataFrame,
             spec: dict, *, model_kind="lightgbm") -> tuple[pd.DataFrame, dict]:
    """Purged CPCV OOF predictions, hourly training and 15-minute evaluation."""
    features = spec["model"]
    source_features = [column for column in features if column not in {"side", "sl_atr"}]
    feature_values = feature_frame[source_features].to_numpy(dtype=np.float32, copy=False)
    total = np.zeros(len(labels), dtype=np.float64)
    base_total = np.zeros(len(labels), dtype=np.float64)
    uncertainty2 = np.zeros(len(labels), dtype=np.float64)
    counts = np.zeros(len(labels), dtype=np.uint8)
    train_scores, test_scores, groups = [], [], []
    train_cell_scores, test_cell_scores = [], []
    geometry = pd.MultiIndex.from_product(([-1, 1], [1., 1.5, 2., 3., 4.], [.5, 1., 1.5, 2., 3.]))
    anchor_lookup = labels.anchor_index.to_numpy()
    for fold in cpcv_folds(anchors, N_GROUPS, N_TEST_GROUPS):
        train_anchor = np.zeros(len(anchors), dtype=bool)
        train_anchor[fold.train] = anchors.iloc[fold.train].ts.dt.minute.eq(0).to_numpy()
        eligible = np.flatnonzero(train_anchor)
        if len(eligible) > MAX_TRAIN_ANCHORS:
            keep = eligible[np.linspace(0, len(eligible) - 1, MAX_TRAIN_ANCHORS, dtype=int)]
            train_anchor[:] = False
            train_anchor[keep] = True
        test_anchor = np.zeros(len(anchors), dtype=bool); test_anchor[fold.test] = True
        train_indices = np.flatnonzero(train_anchor[anchor_lookup])
        test_indices = np.flatnonzero(test_anchor[anchor_lookup])
        train = _materialize(labels, train_indices, feature_values, source_features)
        model = _fit_fold(train, features, model_kind)
        cells, fallback = _cell_base_rates(train)
        train_p = model.predict(train)
        train_scores.append(float(-np.mean((train_p - train.tp_first.to_numpy()) ** 2)))
        train_cell_scores.append(
            train.groupby(["side", "sl_atr", "tp_r"], observed=True).net_R.mean().reindex(geometry).to_numpy()
        )
        squared_error = 0.0
        test_count = 0
        cell_sum = np.zeros(len(geometry)); cell_n = np.zeros(len(geometry), dtype=int)
        for start in range(0, len(test_indices), PREDICT_CHUNK):
            indices = test_indices[start:start + PREDICT_CHUNK]
            test = _materialize(labels, indices, feature_values, source_features)
            probabilities = model.predict(test)
            uncertainty = model.uncertainty(test)
            base = _cell_predict(test, cells, fallback)
            total[indices] += probabilities
            base_total[indices] += base
            uncertainty2[indices] += np.square(uncertainty)
            counts[indices] += 1
            squared_error += float(np.square(probabilities - test.tp_first.to_numpy()).sum())
            test_count += len(test)
            cell_codes = geometry.get_indexer(pd.MultiIndex.from_frame(test[["side", "sl_atr", "tp_r"]]))
            np.add.at(cell_sum, cell_codes, test.net_R.to_numpy(float))
            np.add.at(cell_n, cell_codes, 1)
        test_scores.append(float(-squared_error / test_count))
        test_cell_scores.append(np.divide(cell_sum, cell_n, out=np.full(len(geometry), np.nan), where=cell_n > 0))
        groups.append(list(fold.test_groups))
        del train, model
        gc.collect()
        _memory_guard()
    if (counts == 0).any():
        raise RuntimeError("CPCV did not predict every wide-grid candidate")
    result = labels.copy()
    result["p"] = total / counts
    result["base_rate_p"] = base_total / counts
    result["p_uncertainty"] = np.sqrt(uncertainty2 / counts)
    audit = {
        "cpcv_test_groups": groups,
        "cpcv_train_scores": train_scores,
        "cpcv_test_scores": test_scores,
        "pbo": _pbo(train_cell_scores, test_cell_scores),
        "training_anchor_cadence": "hourly (:00) within each purged fold",
        "maximum_training_anchors_per_fold": MAX_TRAIN_ANCHORS,
        "evaluation_anchor_cadence": "every 15 minutes",
    }
    return result, audit


def _choose_monthly(evaluated: pd.DataFrame) -> pd.DataFrame:
    """Call the shared decision rule in bounded independent anchor chunks."""
    months = evaluated.known_at.dt.tz_localize(None).dt.to_period("M")
    selected = []
    for _, positions in evaluated.groupby(months, sort=True).groups.items():
        chunk = evaluated.loc[positions]
        chosen = choose(chunk, threshold=THRESHOLD, uncertainty=chunk.p_uncertainty)
        if len(chosen):
            selected.append(chosen)
    return pd.concat(selected, ignore_index=True) if selected else evaluated.iloc[:0].copy()


def _config_hash(family: str, symbol: str, config: dict, model_kind: str) -> str:
    payload = {"protocol": config["protocol"], "family": family, "symbol": symbol,
               "family_config": config["families"][family], "model": model_kind,
               "threshold": THRESHOLD, "cpcv": [N_GROUPS, N_TEST_GROUPS]}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def _write_job_markdown(path: Path, family: str, symbol: str, pooled: dict) -> None:
    def fmt(value):
        return "NA" if value is None or not np.isfinite(value) else f"{value:.4f}"
    lines = [f"# {family} — {symbol} DEV", "",
             "Development only. Test and Final were neither loaded nor evaluated.", "",
             f"Training anchors are subsampled to hourly (:00), capped at {MAX_TRAIN_ANCHORS:,} anchors per fold, for the 10 GiB memory cap; OOF evaluation uses every 15-minute anchor.", "",
             "| n | trades/year | hit | net avg R | t | PF | Brier skill vs p0 | Brier skill vs cell base | random pct | beat base + positive net |",
             "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
             f"| {pooled['n']} | {fmt(pooled.get('signals_per_year'))} | {fmt(pooled.get('hit_rate'))} | "
             f"{fmt(pooled.get('net_avg_R'))} | {fmt(pooled.get('t_stat'))} | {fmt(pooled.get('profit_factor'))} | "
             f"{fmt(pooled.get('brier_skill_vs_p0'))} | {fmt(pooled.get('brier_skill_vs_cell_base_rate'))} | "
             f"{fmt(pooled.get('random_direction_percentile'))} | {'yes' if pooled.get('beats_cell_base_and_positive_net') else 'no'} |"]
    path.write_text("\n".join(lines) + "\n")


def write_summary(output: Path) -> Path:
    jobs = []
    for path in sorted((output / "jobs").glob("*.json")):
        jobs.append(json.loads(path.read_text()))
    target = output / "families_summary.md"
    lines = ["# Phase 2 v1 — feature-family DEV summary", "",
             "**Development only (decisions and label ends before 2023-01-01). Test and Final were not loaded.**", "",
             f"LightGBM residual models use the geometric p0 offset. CPCV predictions use purging and a one-trading-day embargo. Training anchors are hourly (at most {MAX_TRAIN_ANCHORS:,} per fold) to cap RSS; evaluation anchors remain 15-minute.", "",
             "DXY and Treasury yields are unavailable in v1 and are not included in F5.", "",
             "| Family | Market | OOF net R | Trades/year | Hit | t | PF | Brier skill vs p0 | Brier skill vs cell base | Random pct | Beat base + net > 0 | Runtime min | Peak GiB |",
             "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|"]
    def fmt(value):
        return "NA" if value is None else f"{value:.4f}"
    for job in jobs:
        item = job["pooled"]
        lines.append(f"| {job['family']} | {job['symbol']} | {fmt(item.get('net_avg_R'))} | "
                     f"{fmt(item.get('signals_per_year'))} | {fmt(item.get('hit_rate'))} | "
                     f"{fmt(item.get('t_stat'))} | {fmt(item.get('profit_factor'))} | "
                     f"{fmt(item.get('brier_skill_vs_p0'))} | {fmt(item.get('brier_skill_vs_cell_base_rate'))} | "
                     f"{fmt(item.get('random_direction_percentile'))} | "
                     f"{'yes' if item.get('beats_cell_base_and_positive_net') else 'no'} | "
                     f"{job['runtime_s']/60:.2f} | {job['peak_rss_gib']:.2f} |")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(lines) + "\n")
    return target


def run_one(family: str, symbol: str, data_root: Path, labels_root: Path,
            output: Path, *, ledger: Path = Path("reports/trials.csv"),
            model_kind="lightgbm", random_seeds=200, append_ledger=True,
            persist_signals_root: Path | None = None,
            compute_random_benchmark: bool = True) -> dict:
    if symbol not in SYMBOLS:
        raise ValueError(symbol)
    started = time.perf_counter()
    config = load_config()
    labels, manifest = _read_labels(labels_root, symbol)
    anchor = labels.groupby("ts", sort=True).agg(
        known_at=("known_at", "first"), label_end_ts=("label_end_ts", "max")
    ).reset_index()
    anchor["anchor_index"] = np.arange(len(anchor), dtype=np.int32)
    mapping = pd.Series(anchor.anchor_index.to_numpy(), index=anchor.ts)
    labels["anchor_index"] = labels.ts.map(mapping).astype("int32")
    labels["event_key"] = (labels.anchor_index.astype("int64") * 2 + labels.side.gt(0).astype("int8")).astype("int64")
    features, spec, feature_manifest = load_anchor_features(data_root, symbol, anchor, family, config)
    manifest.extend(feature_manifest)
    evaluated, cpcv = cpcv_oof(labels, anchor, features, spec, model_kind=model_kind)
    signals = gate_open_signals(_choose_monthly(evaluated))
    if persist_signals_root is not None:
        persist_signals_root.mkdir(parents=True,exist_ok=True)
        target=persist_signals_root/f"{family}_{symbol}.parquet"
        temporary=target.with_suffix(".parquet.part")
        keep=[column for column in ("candidate_id","event_key","sym","ts","known_at","side",
            "price","sl","tp","deadline_ts","net_R","p","p0","p_uncertainty","sl_atr",
            "tp_r","TP_R","SL_R","planned_risk") if column in signals]
        signals[keep].to_parquet(temporary,index=False,compression="zstd")
        temporary.replace(target)
    report_candidates = evaluated[["candidate_id", "event_key", "sym", "known_at", "label_end_ts",
                                   "tp_first", "p", "p0", "net_R"]].copy()
    pooled = metrics(signals, report_candidates)
    y = evaluated.tp_first.to_numpy(float)
    brier = float(np.mean(np.square(evaluated.p.to_numpy(float) - y)))
    base_brier = float(np.mean(np.square(evaluated.base_rate_p.to_numpy(float) - y)))
    pooled["brier_skill_vs_cell_base_rate"] = None if base_brier <= 0 else 1 - brier / base_brier
    pooled["beats_cell_base_and_positive_net"] = bool(
        (pooled["brier_skill_vs_cell_base_rate"] or 0) > 0 and (pooled.get("net_avg_R") or 0) > 0
    )
    if compute_random_benchmark:
        percentile, random_n, bar_manifest = random_direction(signals, data_root, seeds=random_seeds)
    else:
        percentile,random_n,bar_manifest=None,0,[]
    manifest.extend(bar_manifest)
    pooled["random_direction_percentile"] = percentile
    pooled["random_direction_matched_signals"] = random_n
    method = f"phase2_{family}_{symbol}"
    existing = read_trials(ledger)
    diagnostic = {**pooled, "cpcv_train_scores": cpcv["cpcv_train_scores"],
                  "cpcv_test_scores": cpcv["cpcv_test_scores"]}
    sharpes, _, trial_count = trial_diagnostics(
        existing + [{"method": method, "period": "dev", "metrics": json.dumps(diagnostic)}], method
    )
    audit = {"events": len(anchor) * 2, "candidate_rows": len(labels),
             "assembled_rows": len(evaluated), "drops": {}, **cpcv}
    card = report(method, "dev", signals, report_candidates, manifest, trial_count=trial_count,
                  trial_sharpes=sharpes, pbo=cpcv["pbo"], random_percentile=percentile,
                  random_n=random_n, audit=audit, output=output / "cards")
    card["pooled"].update({key: pooled[key] for key in (
        "brier_skill_vs_cell_base_rate", "beats_cell_base_and_positive_net")})
    card["cpcv"] = cpcv
    config_hash = _config_hash(family, symbol, config, model_kind)
    ledger_metrics = {**card["pooled"], "cpcv_train_scores": cpcv["cpcv_train_scores"],
                      "cpcv_test_scores": cpcv["cpcv_test_scores"]}
    if append_ledger:
        row = dict(zip(FIELDS, [f"dev-{family}-{symbol}-{config_hash[:12]}",
            str(pd.Timestamp.now(tz="UTC").date()), config_hash, method,
            json.dumps({"protocol":"phase2_family_v1", "family":family, "model":model_kind,
                        "training_anchor_minutes":[0]}, sort_keys=True),
            f"{evaluated.known_at.min()} / {evaluated.known_at.max()}", "dev",
            json.dumps(ledger_metrics, sort_keys=True), "phase2_family_v1"]));
        append_trial(ledger, row, max_configs=20)
    runtime = time.perf_counter() - started
    job = {"family": family, "symbol": symbol, "config_hash": config_hash,
           "features": spec["model"], "feature_count": len(spec["model"]),
           "pooled": card["pooled"], "cpcv": cpcv, "runtime_s": runtime,
           "peak_rss_gib": _peak_rss_gib(), "candidates": len(evaluated),
           "signals": len(signals), "input_manifest": manifest}
    jobs = output / "jobs"; jobs.mkdir(parents=True, exist_ok=True)
    (jobs / f"{family}_{symbol}.json").write_text(json.dumps(job, indent=2, allow_nan=False))
    _write_job_markdown(jobs / f"{family}_{symbol}.md", family, symbol, card["pooled"])
    write_summary(output)
    _memory_guard()
    return job


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--family", choices=tuple(load_config()["families"]), required=True)
    parser.add_argument("--symbol", choices=SYMBOLS, required=True)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--labels-root", type=Path)
    parser.add_argument("--output", type=Path, default=Path("reports/research/phase2_v1"))
    parser.add_argument("--ledger", type=Path, default=Path("reports/trials.csv"))
    parser.add_argument("--model-kind", choices=("lightgbm", "logistic"), default="lightgbm")
    parser.add_argument("--random-seeds", type=int, default=200)
    parser.add_argument("--no-ledger", action="store_true")
    parser.add_argument("--persist-signals-root",type=Path,
                        help="opt-in versioned output for selected OOF signals")
    parser.add_argument("--skip-random-benchmark",action="store_true")
    args = parser.parse_args()
    labels_root = args.labels_root or args.data_root / "labels_wide_v1"
    job = run_one(args.family, args.symbol, args.data_root, labels_root, args.output,
                  ledger=args.ledger, model_kind=args.model_kind,
                  random_seeds=args.random_seeds, append_ledger=not args.no_ledger,
                  persist_signals_root=args.persist_signals_root,
                  compute_random_benchmark=not args.skip_random_benchmark)
    print(json.dumps({key: job[key] for key in ("family", "symbol", "runtime_s",
                                                "peak_rss_gib", "candidates", "signals")}), flush=True)


if __name__ == "__main__":
    main()
