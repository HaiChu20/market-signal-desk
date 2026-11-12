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
    metrics = [pd.read_json(path, typ="series") for path in tmp_path.glob("fold_*/metrics.json")]
    assert all(row.early_loss_finite for row in metrics)
    assert all(row.best_early_loss < 1.5 for row in metrics)


def test_dev_guard_rejects_test_and_final():
    from msd.research.sequence_train import _dev_guard
    from msd.research.sequence_data import SequenceData, WINDOWS
    for year in (2023, 2025):
        stamp = pd.Timestamp(f"{year}-01-01", tz="UTC")
        data = SequenceData({tf: np.zeros((1, 2, 6), dtype="float32") for tf in WINDOWS},
                            np.zeros((1, 1), dtype="float32"), np.zeros((1, 2, 5, 7), dtype="float32"),
                            np.ones((1, 2, 5, 7), dtype=bool), np.full((1, 2, 5, 7), .5),
                            pd.DataFrame({"known_at": [stamp], "label_end_ts": [stamp]}), ("x",))
        with pytest.raises(ValueError, match="DEV"):
            _dev_guard(data)


def test_index_loader_and_window_causality():
    from msd.research.sequence_data import load_executable_1m
    root = Path("/Users/bfhach/Projects/market-signal-desk/data")
    if not root.exists():
        pytest.skip("Read-only local data is absent")
    bars = load_executable_1m("USATECHIDXUSD", "2021-01-01", "2021-01-04", root)
    assert not bars.empty
    assert (bars.ask_c >= bars.bid_c).all()
    assert bars.ts.min() >= pd.Timestamp("2018-12-16 23:00", tz="UTC")
    bars["known_at"] = pd.to_datetime(bars.ts, utc=True) + pd.Timedelta(minutes=1)
    anchor = pd.Timestamp("2021-01-04 12:00", tz="UTC")
    assert bars.loc[bars.known_at <= anchor, "known_at"].max() <= anchor
    assert bars.loc[bars.known_at > anchor, "known_at"].min() > anchor


def _small_training_data():
    from msd.research.sequence_data import SequenceData, WINDOWS
    n = 30
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
    dense = np.column_stack((np.arange(n, dtype="float32") * 1e10,
                             np.ones(n, dtype="float32") * 1.4e6))
    return SequenceData({tf: np.zeros((n, 8, 6), dtype="float32") for tf in WINDOWS},
                        dense,
                        np.random.default_rng(1).integers(0, 2, (n, 2, 5, 7)).astype("float32"),
                        np.ones((n, 2, 5, 7), dtype=bool), baseline, anchors,
                        ("huge", "constant"),
                        labels=pd.DataFrame(rows))


def test_dense_scaling_uses_fit_only_and_clips_huge_columns():
    from msd.research.sequence_train import _dense_stats, _scale_dense
    dense = np.array([[1., 4.], [3., 4.], [1e12, -1e12]], dtype="float32")
    expected = _dense_stats(dense, [0, 1])
    changed = dense.copy()
    changed[2] = [-1e20, 1e20]
    actual = _dense_stats(changed, [0, 1])
    np.testing.assert_array_equal(actual[0], expected[0])
    np.testing.assert_array_equal(actual[1], expected[1])
    assert expected[1][1] == 1.
    assert np.abs(_scale_dense(changed, actual)).max() <= 10.


def test_checkpoint_resume_matches_uninterrupted(tmp_path):
    torch = pytest.importorskip("torch")
    from msd.research.sequence_train import train_walk_forward
    data = _small_training_data()
    common = dict(n_folds=3, epochs=2, batch_size=2, width=8, checkpoint_every=1,
                  config_sha256="fixture", seed=7)
    train_walk_forward(data, tmp_path / "full", **common)
    assert train_walk_forward(data, tmp_path / "resumed", max_steps=1, **common) == []
    resume_state = torch.load(tmp_path / "resumed/fold_00/resume.pt", weights_only=False)
    assert "dense_mean" in resume_state and "dense_std" in resume_state
    train_walk_forward(data, tmp_path / "resumed", **common)
    full = sorted((tmp_path / "full").rglob("oof.parquet"))
    resumed = sorted((tmp_path / "resumed").rglob("oof.parquet"))
    assert len(full) == len(resumed) > 0
    for left, right in zip(full, resumed):
        pd.testing.assert_frame_equal(pd.read_parquet(left), pd.read_parquet(right), check_exact=True)
    model_state = torch.load(tmp_path / "resumed/fold_00/model.pt", weights_only=False)
    np.testing.assert_array_equal(model_state["dense_mean"], resume_state["dense_mean"])
    np.testing.assert_array_equal(model_state["dense_std"], resume_state["dense_std"])


def test_grade_sequence_cli_fixture(tmp_path):
    from msd.research.grade_sequence import grade
    folder = tmp_path / "oof" / "fold_00"
    folder.mkdir(parents=True)
    time = pd.Timestamp("2021-02-01", tz="UTC")
    row = {"known_at": time, "label_end_ts": time + pd.Timedelta(hours=1),
           "entry_ts": time + pd.Timedelta(minutes=2), "ts": time - pd.Timedelta(minutes=1),
           "side": 1, "sl": 98., "tp": 104., "price": 100., "p": .8, "p0": 1 / 3,
           "tp_first": 1., "net_R": 1., "cost_R": .01, "financing_R": 0., "spread_R": .01,
           "TP_R": 2., "sym": "BTCUSDT", "event_key": "event", "candidate_id": "candidate",
           "config_sha256": "fixture", "fold": 0, "seed": 7}
    pd.DataFrame([row]).to_parquet(folder / "oof.parquet")
    cards = grade(tmp_path / "oof", data_root=tmp_path / "absent")
    assert next(iter(cards.values()))["pooled"]["brier"] is not None
    assert (tmp_path / "oof" / "grade" / "summary.json").exists()
    row["known_at"] = pd.Timestamp("2023-01-01", tz="UTC")
    pd.DataFrame([row]).to_parquet(folder / "oof.parquet")
    with pytest.raises(ValueError, match="TEST/FINAL"):
        grade(tmp_path / "oof", data_root=tmp_path / "absent")


def test_cli_refuses_test_dates_even_in_smoke(monkeypatch, tmp_path):
    from msd.research.sequence_train import main
    config = Path(__file__).resolve().parents[2] / "hpc/roihu/sequence/configs/dev_v1.json"
    monkeypatch.setattr("sys.argv", ["sequence_train", "--data-root", str(tmp_path),
                                    "--config", str(config), "--symbol", "BTCUSDT",
                                    "--output", str(tmp_path / "out"), "--end", "2024-01-01",
                                    "--smoke"])
    with pytest.raises(SystemExit) as caught:
        main()
    assert caught.value.code == 2


def test_flow_join_is_backward_only_and_preserves_missing_vs_zero():
    from msd.research.sequence_train import add_flow_features
    stamps = pd.date_range("2021-01-01", periods=3, freq="min", tz="UTC")
    dense = pd.DataFrame({"known_at": stamps, "base": [1., 2., 3.]})
    flow = pd.DataFrame({"ts": stamps[[0, 2]] - pd.Timedelta(minutes=1),
                         "known_at": stamps[[0, 2]], "spot_imbalance_1m": [0., .4],
                         "spot_flow_coverage": [True, True]})
    joined = add_flow_features(dense, flow, ["spot_imbalance_1m", "spot_flow_coverage"], .6)
    assert joined.spot_imbalance_1m.iloc[:2].tolist() == [0., 0.]
    assert joined.spot_imbalance_1m.iloc[2] == .4
    assert not joined.spot_imbalance_1m_missing.any()
    late = flow.iloc[1:].copy()
    joined_late = add_flow_features(dense, late, ["spot_imbalance_1m"], .5)
    assert joined_late.spot_imbalance_1m.iloc[:2].isna().all()
    assert joined_late.spot_imbalance_1m_missing.tolist() == [True, True, False]
    sparse = flow.copy()
    sparse.loc[1, "spot_imbalance_1m"] = np.nan
    with pytest.raises(ValueError, match="coverage"):
        add_flow_features(dense, sparse, ["spot_imbalance_1m"], .8)


def test_flow_join_clips_intensity_and_rejects_raw_delta_scale():
    from msd.research.sequence_train import add_flow_features
    stamps = pd.date_range("2021-01-01", periods=2, freq="min", tz="UTC")
    dense = pd.DataFrame({"known_at": stamps})
    flow = pd.DataFrame({"ts": stamps - pd.Timedelta(minutes=1), "known_at": stamps,
                         "spot_trade_intensity_z20d": [-45., 31.]})
    joined = add_flow_features(dense, flow, ["spot_trade_intensity_z20d"])
    assert joined.spot_trade_intensity_z20d.tolist() == [-10., 10.]
    raw = flow.rename(columns={"spot_trade_intensity_z20d": "spot_delta_60m"})
    with pytest.raises(ValueError, match="Unscaled flow feature"):
        add_flow_features(dense, raw, ["spot_delta_60m"])
