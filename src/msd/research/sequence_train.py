"""DEV-only purged walk-forward training for the sequence barrier model."""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression

from msd.research import decision, report_card, splits
from msd.research.dataset import DEV_END
from msd.research.sequence_data import SequenceData, build_windows


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


def _candidates(data: SequenceData, indices, probabilities, symbol):
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
                                 "entry_ts": label.entry_ts, "sym": symbol, "side": side,
                                 "price": price, "sl": price - side * sl * atr,
                                 "tp": price + side * tp * atr,
                                 "p": float(probabilities[k, si, i, j]),
                                 "p0": float(data.p0[idx, si, i, j]),
                                 "tp_first": float(data.target[idx, si, i, j]),
                                 "net_R": float(label.net_R), "TP_R": tp / sl,
                                 "cost_R": float(anchor.spread / (sl * atr)),
                                 "financing_R": 0., "spread_R": float(anchor.spread / (sl * atr)),
                                 "event_key": f"{symbol}|{anchor.known_at}|{side}",
                                 "candidate_id": f"{symbol}|{anchor.known_at}|{side}|{sl}|{tp}"})
    return pd.DataFrame(rows)


def train_walk_forward(data: SequenceData, output: Path, *, n_folds: int = 5,
                       epochs: int = 20, batch_size: int = 64, patience: int = 4,
                       seed: int = 7, symbol: str = "BTCUSDT", device: str | None = None):
    """Fit each fold using strictly earlier fit/stop/calibration blocks."""
    from msd.research.sequence_model import SequenceModel, barrier_loss
    torch = _torch()
    _dev_guard(data)
    seed_everything(seed)
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
        model = SequenceModel(data.dense.shape[1]).to(selected_device)
        optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3)
        stop_batch = _take(data, early_idx, selected_device)
        best_loss, best_state, stale = float("inf"), None, 0
        for epoch in range(epochs):
            model.train()
            order = np.random.permutation(fit_idx)
            for batch_idx in np.array_split(order, max(1, int(np.ceil(len(order) / batch_size)))):
                windows, dense, p0, target, mask = _take(data, batch_idx, selected_device)
                optimizer.zero_grad(set_to_none=True)
                loss = barrier_loss(model(windows, dense, p0), target, mask)
                loss.backward()
                optimizer.step()
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
                    break
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
        candidates = _candidates(data, test_idx, calibrated, symbol)
        signals = decision.choose(candidates) if len(candidates) else candidates
        fold_output = output / f"fold_{fold:02d}"
        checkpoint = {"state_dict": best_state, "feature_names": data.feature_names,
                      "calibration_x": calibrator.X_thresholds_.tolist(),
                      "calibration_y": calibrator.y_thresholds_.tolist(),
                      "seed": seed, "epoch": epoch, "best_early_loss": best_loss}
        fold_output.mkdir(exist_ok=True)
        torch.save(checkpoint, fold_output / "model.pt")
        card = report_card.report("sequence_cnn", "dev", signals, candidates, [],
                                  output=fold_output)
        (fold_output / "metrics.json").write_text(json.dumps({"fit": len(fit_idx),
            "early": len(early_idx), "calibration": len(cal_idx), "test": len(test_idx),
            "best_early_loss": best_loss, "brier_skill_vs_p0": card["pooled"]["brier_skill_vs_p0"]}, indent=2))
        cards.append(card)
    if not cards:
        raise ValueError("No purged fold has sufficient fit, early-stop and calibration data")
    return cards


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True, help="exclusive UTC end, at most 2023-01-01")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()
    start = pd.Timestamp(args.start, tz="UTC")
    end = pd.Timestamp(args.end, tz="UTC")
    if end > DEV_END or start >= end:
        parser.error("Only DEV dates through 2022-12-31 are allowed")
    root = args.data_root
    months = pd.period_range(start.tz_localize(None).to_period("M"),
                             (end - pd.Timedelta(nanoseconds=1)).tz_localize(None).to_period("M"), freq="M")
    # Extra preceding months supply the 4h/1h warmup. Read only DEV files.
    warmup = (start - pd.Timedelta(days=12)).to_period("M")
    months = pd.period_range(warmup, months[-1], freq="M")
    def load(folder):
        frames = [pd.read_parquet(folder / f"{m}.parquet") for m in months if (folder / f"{m}.parquet").exists()]
        if not frames:
            raise FileNotFoundError(folder)
        return pd.concat(frames, ignore_index=True)
    bars = {tf: load((root / "bars/binance_spot" if tf == "1m" else root / "derived" / f"bars_{tf}") / args.symbol)
            for tf in ("1m", "15m", "1h", "4h")}
    features = load(root / "features" / args.symbol)
    labels = load(root / "labels" / args.symbol)
    labels = labels[(pd.to_datetime(labels.ts, utc=True) >= start) & (pd.to_datetime(labels.ts, utc=True) < end)]
    data = build_windows(bars, features, labels)
    train_walk_forward(data, args.output, epochs=args.epochs, seed=args.seed, symbol=args.symbol)


if __name__ == "__main__":
    main()
