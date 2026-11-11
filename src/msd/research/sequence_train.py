"""DEV-only purged walk-forward training for the sequence barrier model."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import signal
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression

from msd.data.flow_features import join_by_known_at
from msd.research import decision, report_card, splits
from msd.research.dataset import DEV_END
from msd.research.sequence_data import SequenceData, SYMBOL_START, build_windows, load_executable_1m

_STOP_REQUESTED = False


def _request_checkpoint(signum, frame):
    global _STOP_REQUESTED
    _STOP_REQUESTED = True


def _torch():
    try:
        import torch
    except ImportError as error:
        raise RuntimeError("Install the optional gpu extra: uv sync --extra gpu") from error
    return torch


def seed_everything(seed: int) -> None:
    torch = _torch()
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    torch.use_deterministic_algorithms(True)
    if hasattr(torch.backends, "cudnn"):
        torch.backends.cudnn.benchmark = False


def _take(data: SequenceData, indices, device):
    torch = _torch()
    ix = np.asarray(indices, dtype=int)
    return ({tf: torch.as_tensor(v[ix], device=device) for tf, v in data.windows.items()},
            torch.as_tensor(data.dense[ix], device=device),
            torch.as_tensor(data.p0[ix], device=device),
            torch.as_tensor(data.target[ix], device=device),
            torch.as_tensor(data.mask[ix], device=device))


def _dev_guard(data: SequenceData) -> None:
    if len(data) == 0 or pd.to_datetime(data.anchors.known_at, utc=True).ge(DEV_END).any():
        raise ValueError("Training requires DEV anchors through 2022-12-31 only")
    if pd.to_datetime(data.anchors.label_end_ts, utc=True).ge(DEV_END).any():
        raise ValueError("Training labels must resolve by 2022-12-31")


def add_flow_features(features: pd.DataFrame, flow: pd.DataFrame,
                      columns: list[str], min_coverage: float = .8) -> pd.DataFrame:
    """Causally add the pre-registered flow columns after a DEV coverage gate."""
    missing = set(columns) - set(flow)
    if missing:
        raise ValueError(f"Missing configured flow columns: {sorted(missing)}")
    coverage = flow[columns].notna().mean()
    failed = coverage[coverage < min_coverage]
    if len(failed):
        details = ", ".join(f"{name}={value:.1%}" for name, value in failed.items())
        raise ValueError(f"Flow feature coverage below {min_coverage:.0%}: {details}")
    selected = flow[["ts", "known_at", *columns]].copy()
    joined = join_by_known_at(features, selected)
    if len(joined) != len(features):
        raise AssertionError("Flow join changed dense feature row count")
    # build_windows uses fixed zero imputation for dense tensors. Preserve the
    # distinction between a covered no-activity zero and unavailable flow by
    # adding an explicit missingness channel before that imputation.
    for column in columns:
        joined[f"{column}_missing"] = joined[column].isna()
    return joined


def _later_blocks(data: SequenceData, train_indices, embargo=splits.EMBARGO):
    """Chronological fit, early-stop and calibration blocks from past data only."""
    ordered = np.asarray(train_indices)[np.argsort(data.anchors.known_at.iloc[train_indices].to_numpy())]
    blocks = np.array_split(ordered, 3)
    fit, early, cal = blocks
    a = data.anchors
    early_start = a.known_at.iloc[early].min()
    cal_start = a.known_at.iloc[cal].min()
    fit = fit[a.label_end_ts.iloc[fit].lt(early_start - embargo).to_numpy()]
    early = early[a.label_end_ts.iloc[early].lt(cal_start - embargo).to_numpy()]
    if not (len(fit) and len(early) and len(cal)):
        return None
    return fit, early, cal


def _candidates(data: SequenceData, indices, probabilities, symbol, config_sha256, fold, seed):
    rows = []
    label_index = data.labels.set_index(["known_at", "side", "sl_atr", "tp_atr"])
    for k, idx in enumerate(indices):
        anchor = data.anchors.iloc[int(idx)]
        for si, side in enumerate(data.sides):
            for i, sl in enumerate(data.sl_grid):
                for j, tp in enumerate(data.tp_grid):
                    if not data.mask[idx, si, i, j]:
                        continue
                    key = (anchor.known_at, side, sl, tp)
                    try:
                        label = label_index.loc[key]
                    except KeyError:
                        continue
                    price = float(anchor.price)
                    atr = float(anchor.atr)
                    rows.append({"known_at": anchor.known_at, "label_end_ts": label.exit_ts,
                                 "ts": anchor.known_at - pd.Timedelta(minutes=1),
                                 "entry_ts": label.entry_ts, "sym": symbol, "side": side,
                                 "price": price, "sl": price - side * sl * atr,
                                 "tp": price + side * tp * atr,
                                 "p": float(probabilities[k, si, i, j]),
                                 "p0": float(data.p0[idx, si, i, j]),
                                 "tp_first": float(data.target[idx, si, i, j]),
                                 "net_R": float(label.net_R), "TP_R": tp / sl,
                                 "planned_risk": float(label.planned_risk) if "planned_risk" in label else sl * atr,
                                 "deadline_ts": label.deadline_ts if "deadline_ts" in label else label.exit_ts,
                                 "sl_atr": sl, "tp_atr": tp,
                                 "config_sha256": config_sha256, "fold": fold, "seed": seed,
                                 "cost_R": float(anchor.spread / (float(label.planned_risk) if "planned_risk" in label else sl * atr)),
                                 "financing_R": 0., "spread_R": float(anchor.spread / (float(label.planned_risk) if "planned_risk" in label else sl * atr)),
                                 "event_key": f"{symbol}|{anchor.known_at}|{side}",
                                 "candidate_id": f"{symbol}|{anchor.known_at}|{side}|{sl}|{tp}"})
    return pd.DataFrame(rows)


def train_walk_forward(data: SequenceData, output: Path, *, n_folds: int = 5,
                       epochs: int = 20, batch_size: int = 64, patience: int = 4,
                       seed: int = 7, symbol: str = "BTCUSDT", device: str | None = None,
                       width: int = 24, checkpoint_every: int = 100,
                       config_sha256: str = "synthetic-test", max_steps: int | None = None):
    """Fit each fold using strictly earlier fit/stop/calibration blocks."""
    from msd.research.sequence_model import SequenceModel, barrier_loss
    torch = _torch()
    _dev_guard(data)
    seed_everything(seed)
    signal.signal(signal.SIGUSR1, _request_checkpoint)
    signal.signal(signal.SIGTERM, _request_checkpoint)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    selected_device = device or ("cuda" if torch.cuda.is_available() else "cpu")
    cards = []
    for fold, (train_idx, test_idx) in enumerate(splits.walk_forward(data.anchors, n_folds)):
        parts = _later_blocks(data, train_idx)
        if parts is None:
            continue
        fit_idx, early_idx, cal_idx = parts
        # Guard every boundary, including the test fold, against label overlap.
        cutoff = data.anchors.known_at.iloc[test_idx].min() - splits.EMBARGO
        cal_idx = cal_idx[data.anchors.label_end_ts.iloc[cal_idx].lt(cutoff).to_numpy()]
        if not len(cal_idx):
            continue
        torch.manual_seed(seed + fold)
        model = SequenceModel(data.dense.shape[1], width=width).to(selected_device)
        optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3)
        stop_batch = _take(data, early_idx, selected_device)
        best_loss, best_state, stale = float("inf"), None, 0
        fold_output = output / f"fold_{fold:02d}"
        fold_output.mkdir(exist_ok=True)
        checkpoint_path = fold_output / "resume.pt"
        first_epoch, first_batch, step = 0, 0, 0
        if checkpoint_path.exists():
            state = torch.load(checkpoint_path, map_location=selected_device, weights_only=False)
            if state["config_sha256"] != config_sha256 or state["seed"] != seed:
                raise ValueError("Checkpoint config/seed mismatch")
            model.load_state_dict(state["model"])
            optimizer.load_state_dict(state["optimizer"])
            best_loss, best_state, stale = state["best_loss"], state["best_state"], state["stale"]
            first_epoch, first_batch, step = state["epoch"], state["batch"], state["step"]
        def save_progress(next_epoch, next_batch):
            state = {"config_sha256": config_sha256, "seed": seed, "model": model.state_dict(),
                     "optimizer": optimizer.state_dict(), "best_loss": best_loss,
                     "best_state": best_state, "stale": stale, "epoch": next_epoch,
                     "batch": next_batch, "step": step}
            temporary = checkpoint_path.with_suffix(".partial")
            torch.save(state, temporary)
            os.replace(temporary, checkpoint_path)
        for epoch in range(first_epoch, epochs):
            model.train()
            order = np.random.default_rng(seed + fold * 10000 + epoch).permutation(fit_idx)
            batches = np.array_split(order, max(1, int(np.ceil(len(order) / batch_size))))
            for batch_number, batch_idx in enumerate(batches):
                if epoch == first_epoch and batch_number < first_batch:
                    continue
                windows, dense, p0, target, mask = _take(data, batch_idx, selected_device)
                optimizer.zero_grad(set_to_none=True)
                loss = barrier_loss(model(windows, dense, p0), target, mask)
                loss.backward()
                optimizer.step()
                step += 1
                if step % checkpoint_every == 0:
                    save_progress(epoch, batch_number + 1)
                if _STOP_REQUESTED:
                    save_progress(epoch, batch_number + 1)
                    raise SystemExit(99)
                if max_steps is not None and step >= max_steps:
                    save_progress(epoch, batch_number + 1)
                    return []
            model.eval()
            with torch.no_grad():
                windows, dense, p0, target, mask = stop_batch
                score = float(barrier_loss(model(windows, dense, p0), target, mask))
            if score < best_loss - 1e-5:
                best_loss = score
                best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
                stale = 0
            else:
                stale += 1
                if stale >= patience:
                    save_progress(epoch + 1, 0)
                    break
            save_progress(epoch + 1, 0)
        model.load_state_dict(best_state)
        def predict(ix):
            model.eval()
            chunks = []
            with torch.no_grad():
                for batch in np.array_split(ix, max(1, int(np.ceil(len(ix) / batch_size)))):
                    windows, dense, p0, _, _ = _take(data, batch, selected_device)
                    chunks.append(model(windows, dense, p0).sigmoid().cpu().numpy())
            return np.concatenate(chunks)
        raw_cal = predict(cal_idx)
        usable = data.mask[cal_idx]
        calibrator = IsotonicRegression(y_min=0, y_max=1, out_of_bounds="clip")
        calibrator.fit(raw_cal[usable], data.target[cal_idx][usable])
        raw_test = predict(test_idx)
        calibrated = calibrator.transform(raw_test.ravel()).reshape(raw_test.shape)
        candidates = _candidates(data, test_idx, calibrated, symbol, config_sha256, fold, seed)
        signals = decision.choose(candidates) if len(candidates) else candidates
        checkpoint = {"state_dict": best_state, "feature_names": data.feature_names,
                      "config_sha256": config_sha256,
                      "calibration_x": calibrator.X_thresholds_.tolist(),
                      "calibration_y": calibrator.y_thresholds_.tolist(),
                      "seed": seed, "epoch": epoch, "best_early_loss": best_loss}
        fold_output.mkdir(exist_ok=True)
        torch.save(checkpoint, fold_output / "model.pt")
        candidates.to_parquet(fold_output / "oof.parquet", index=False)
        card = report_card.report("sequence_cnn", "dev", signals, candidates, [],
                                  output=fold_output)
        (fold_output / "metrics.json").write_text(json.dumps({"fit": len(fit_idx),
            "early": len(early_idx), "calibration": len(cal_idx), "test": len(test_idx),
            "config_sha256": config_sha256, "seed": seed, "fold": fold,
            "best_early_loss": best_loss, "brier_skill_vs_p0": card["pooled"]["brier_skill_vs_p0"]}, indent=2))
        cards.append(card)
    if not cards:
        raise ValueError("No purged fold has sufficient fit, early-stop and calibration data")
    return cards


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=Path("hpc/roihu/sequence/configs/dev_v2.json"))
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--seed", type=int)
    parser.add_argument("--start")
    parser.add_argument("--end", help="exclusive UTC end, at most 2023-01-01")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--smoke", action="store_true", help="two 2021 months, one epoch, tiny CNN")
    args = parser.parse_args()
    raw_config = args.config.read_bytes()
    config_sha256 = hashlib.sha256(raw_config).hexdigest()
    config = json.loads(raw_config)
    if config.get("period") != "dev" or args.symbol not in config["symbols"]:
        parser.error("Configuration must be DEV and include the symbol")
    if args.seed is not None and args.seed not in config["seeds"]:
        parser.error("Seed must be listed in the config")
    seed = args.seed if args.seed is not None else config["seeds"][0]
    start = pd.Timestamp(args.start or config["starts"][args.symbol], tz="UTC")
    end = pd.Timestamp(args.end or config["end_exclusive"], tz="UTC")
    if end > DEV_END or start >= end:
        parser.error("Only DEV dates through 2022-12-31 are allowed")
    if args.smoke:
        start, end = pd.Timestamp("2021-01-01", tz="UTC"), pd.Timestamp("2021-03-01", tz="UTC")
    root = args.data_root
    months = pd.period_range(start.tz_localize(None).to_period("M"),
                             (end - pd.Timedelta(nanoseconds=1)).tz_localize(None).to_period("M"), freq="M")
    # Extra preceding months supply the 4h/1h warmup. Read only DEV files.
    warmup = (start - pd.Timedelta(days=12)).tz_localize(None).to_period("M")
    months = pd.period_range(warmup, months[-1], freq="M")
    if start < pd.Timestamp(SYMBOL_START[args.symbol]):
        parser.error(f"{args.symbol} cannot start before {SYMBOL_START[args.symbol]}")
    def load(folder, columns=None):
        frames = [pd.read_parquet(folder / f"{m}.parquet", columns=columns)
                  for m in months if (folder / f"{m}.parquet").exists()]
        if not frames:
            raise FileNotFoundError(folder)
        return pd.concat(frames, ignore_index=True)
    bars = {"1m": load_executable_1m(args.symbol, start - pd.Timedelta(days=12),
                                     end - pd.Timedelta(minutes=1), root)}
    bars.update({tf: load(root / "derived" / f"bars_{tf}" / args.symbol)
                 for tf in ("15m", "1h", "4h")})
    features = load(root / "features" / args.symbol)
    flow_columns = config.get("flow_features", {}).get(args.symbol)
    if flow_columns:
        flow = load(root / "features_flow" / args.symbol,
                    columns=["ts", "known_at", *flow_columns])
        features = add_flow_features(features, flow, flow_columns,
                                     float(config["flow_min_non_nan_coverage"]))
    labels = load(root / "labels" / args.symbol)
    labels = labels[(pd.to_datetime(labels.ts, utc=True) >= start) & (pd.to_datetime(labels.ts, utc=True) < end)]
    if args.smoke:
        timestamps = pd.to_datetime(labels.ts, utc=True)
        labels = labels[timestamps.dt.minute.eq(0) & timestamps.dt.hour.isin((0, 12))]
    data = build_windows(bars, features, labels)
    (args.output / "config_sha256.txt").parent.mkdir(parents=True, exist_ok=True)
    (args.output / "config_sha256.txt").write_text(config_sha256 + "\n")
    train_walk_forward(data, args.output, epochs=1 if args.smoke else config["epochs"],
                       n_folds=3 if args.smoke else config["folds"],
                       batch_size=16 if args.smoke else config["batch_size"],
                       patience=config["patience"], seed=seed, symbol=args.symbol,
                       width=8 if args.smoke else config["width"],
                       checkpoint_every=1 if args.smoke else config["checkpoint_every_steps"],
                       config_sha256=config_sha256)


if __name__ == "__main__":
    main()
