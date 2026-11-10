from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from msd.research.sequence_data import SL_GRID, TP_GRID, build_windows


def _fixture():
    start = pd.Timestamp("2021-01-01", tz="UTC")
    bars = {}
    for tf, step, count in (("1m", "1min", 600), ("15m", "15min", 100),
                            ("1h", "1h", 100), ("4h", "4h", 70)):
        ts = pd.date_range(start, periods=count, freq=step)
        price = 100 + np.arange(count) * .01
        frame = pd.DataFrame({"ts": ts, "volume": 10 + np.arange(count) % 7})
        for side, shift in (("bid", 0), ("ask", .1)):
            for field, delta in (("o", 0), ("h", .2), ("l", -.2), ("c", .05)):
                frame[f"{side}_{field}"] = price + shift + delta
        frame["known_at"] = frame.ts + pd.Timedelta(step)
        bars[tf] = frame
    anchor = start + pd.Timedelta(days=11, hours=12, minutes=1)
    # Extend 1m/15m/1h history to the anchor without expensive many-day frames.
    for tf, step, n in (("1m", "1min", 5), ("15m", "15min", 5), ("1h", "1h", 5)):
        shift = anchor - bars[tf].known_at.iloc[-1]
        bars[tf]["ts"] += shift
        bars[tf]["known_at"] += shift
    # Use small windows so the artificial gap before the final rows is outside view.
    features = pd.DataFrame({"known_at": [anchor], "1h_atr14_price": [2.], "x": [.4]})
    labels = pd.DataFrame([{"ts": anchor - pd.Timedelta(minutes=1), "side": side,
                            "sl_atr": sl, "tp_atr": tp, "outcome": 1 if side == 1 else -1,
                            "exit_ts": anchor + pd.Timedelta(hours=1),
                            "entry_ts": anchor + pd.Timedelta(minutes=2), "net_R": .2}
                           for side in (-1, 1) for sl in SL_GRID for tp in TP_GRID])
    return bars, features, labels


def test_causal_truncation_and_grid():
    bars, features, labels = _fixture()
    lengths = {tf: 4 for tf in bars}
    original = build_windows(bars, features, labels, windows=lengths)
    assert len(original) == 1
    assert original.mask.sum() == 70
    assert original.p0[0, 0, 0, 0] == pytest.approx(.5)
    changed = {tf: frame.copy() for tf, frame in bars.items()}
    for frame in changed.values():
        future = frame.iloc[-1:].copy()
        future["known_at"] = original.anchors.known_at.iloc[0] + pd.Timedelta(days=1)
        future["ts"] = future.known_at - pd.Timedelta(minutes=1)
        future[[c for c in frame if c.startswith(("bid_", "ask_"))]] = 1e8
        frame.loc[len(frame)] = future.iloc[0]
    again = build_windows(changed, features, labels, windows=lengths)
    for tf in bars:
        np.testing.assert_array_equal(original.windows[tf], again.windows[tf])
    future_feature = pd.DataFrame({"known_at": [original.anchors.known_at.iloc[0] + pd.Timedelta(days=1)],
                                   "1h_atr14_price": [1e9], "x": [1e9]})
    third = build_windows(bars, pd.concat([features, future_feature]), labels, windows=lengths)
    np.testing.assert_array_equal(original.dense, third.dense)


@pytest.mark.slow
def test_real_btc_2021_smoke():
    root = Path("/Users/bfhach/Projects/market-signal-desk/data")
    if not root.exists():
        pytest.skip("Read-only local data is absent")
    symbol = "BTCUSDT"
    # January history and a few February days provide complete 4h windows.
    def read(folder):
        return pd.concat([pd.read_parquet(folder / f"2021-{month}.parquet")
                          for month in ("01", "02")], ignore_index=True)
    bars = {tf: read((root / "bars/binance_spot" if tf == "1m" else root / "derived" / f"bars_{tf}") / symbol)
            for tf in ("1m", "15m", "1h", "4h")}
    features = read(root / "features" / symbol)
    labels = read(root / "labels" / symbol)
    labels = labels[labels.ts.between("2021-02-01", "2021-02-02", inclusive="left")]
    data = build_windows(bars, features, labels)
    assert len(data) > 20
    assert data.mask.sum() > 1000
    assert all(np.isfinite(v).all() for v in data.windows.values())
    assert max(v.shape[1] for v in data.windows.values()) == 240


def test_model_cpu_smoke_and_planted_pattern():
    torch = pytest.importorskip("torch")
    from msd.research.sequence_model import SequenceModel, barrier_loss
    torch.set_num_threads(1)
    torch.manual_seed(2)
    n = 32
    pattern = torch.cat([torch.ones(n // 2), -torch.ones(n // 2)])
    windows = {tf: torch.randn(n, 16, 6) * .05 for tf in ("1m", "15m", "1h", "4h")}
    for value in windows.values():
        value[:, :, 3] += pattern[:, None]
    dense = pattern[:, None]
    p0 = torch.full((n, 2, 5, 7), .5)
    target = (pattern > 0).float()[:, None, None, None].expand_as(p0)
    mask = torch.ones_like(target, dtype=torch.bool)
    model = SequenceModel(1, width=8)
    opt = torch.optim.Adam(model.parameters(), lr=.01)
    losses = []
    for _ in range(35):
        opt.zero_grad()
        loss = barrier_loss(model(windows, dense, p0), target, mask)
        losses.append(float(loss.detach()))
        loss.backward()
        opt.step()
    assert losses[-1] < losses[0] * .2
    predicted = model(windows, dense, p0).sigmoid().mean(dim=(1, 2, 3)).detach()
    assert predicted[:n // 2].mean() > .9
    assert predicted[n // 2:].mean() < .1


def test_purged_walk_forward_cpu(tmp_path):
    pytest.importorskip("torch")
    from msd.research.sequence_data import SequenceData, WINDOWS
    from msd.research.sequence_train import train_walk_forward
    n = 36
    stamps = pd.date_range("2021-01-01", periods=n, freq="2D", tz="UTC")
    anchors = pd.DataFrame({"known_at": stamps, "label_end_ts": stamps + pd.Timedelta(hours=1),
                            "price": 100., "atr": 2., "spread": .1})
    baseline = np.empty((n, 2, 5, 7), dtype="float32")
    rows = []
    for k, stamp in enumerate(stamps):
        for si, side in enumerate((-1, 1)):
            for i, sl in enumerate(SL_GRID):
                for j, tp in enumerate(TP_GRID):
                    baseline[k, si, i, j] = sl / (sl + tp)
                    rows.append({"known_at": stamp, "side": side, "sl_atr": sl, "tp_atr": tp,
                                 "exit_ts": stamp + pd.Timedelta(hours=1),
                                 "entry_ts": stamp + pd.Timedelta(minutes=2),
                                 "net_R": 1. if k % 2 else -1.})
    data = SequenceData({tf: np.zeros((n, 8, 6), dtype="float32") for tf in WINDOWS},
                        np.zeros((n, 1), dtype="float32"),
                        np.random.default_rng(1).integers(0, 2, (n, 2, 5, 7)).astype("float32"),
                        np.ones((n, 2, 5, 7), dtype=bool), baseline, anchors, ("x",),
                        labels=pd.DataFrame(rows))
    cards = train_walk_forward(data, tmp_path, n_folds=3, epochs=1, batch_size=12)
    assert cards
    assert list(tmp_path.glob("fold_*/model.pt"))
    assert all(card["period"] == "dev" for card in cards)
