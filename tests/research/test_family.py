from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from msd.research import family
from msd.research.splits import cpcv_folds


def _config():
    return family.load_config(Path("config/research/phase2_families_v1.json"))


def test_family_feature_config_has_no_outcomes_or_raw_deltas():
    config = _config()
    for name in config["families"]:
        spec = family.feature_spec(name, {"cross_NQ_return_15m"}, set(), config)
        family.assert_no_outcome_features(spec["model"])
    flow = family.feature_spec("f3_order_flow", set(), set(), config)["flow"]
    assert not [column for column in flow if "_delta_" in column and "divergence" not in column]


def test_causal_asof_is_unchanged_by_future_perturbation():
    stamp = pd.date_range("2022-01-01", periods=12, freq="min", tz="UTC")
    left = pd.DataFrame({"known_at": stamp, "anchor_index": range(len(stamp))})
    source = pd.DataFrame({"known_at": stamp, "value": np.arange(len(stamp), dtype=float)})
    cut = stamp[6]
    expected = family.causal_asof(left[left.known_at <= cut], source, ["value"], "source_known_at")
    changed = source.copy()
    changed.loc[changed.known_at > cut, "value"] = 1e9
    actual = family.causal_asof(left[left.known_at <= cut], changed, ["value"], "source_known_at")
    pd.testing.assert_frame_equal(expected, actual)


def test_family_cpcv_reuses_purge_and_one_trading_day_embargo():
    known = pd.date_range("2022-01-03", periods=80, freq="6h", tz="UTC")
    anchors = pd.DataFrame({"known_at": known, "label_end_ts": known + pd.Timedelta(hours=8)})
    folds = list(cpcv_folds(anchors, 5, 2))
    assert len(folds) == 10
    for fold in folds:
        test = anchors.iloc[fold.test]
        train = anchors.iloc[fold.train]
        # Every retained interval is disjoint from each test block and its
        # one-business-day post-block embargo.  The implementation handles
        # non-contiguous test groups block by block.
        order = np.argsort(test.known_at.to_numpy(), kind="stable")
        ordered = test.iloc[order]
        gaps = np.flatnonzero(np.diff(ordered.index.to_numpy()) > 1) + 1
        for positions in np.split(np.arange(len(ordered)), gaps):
            block = ordered.iloc[positions]
            start = block.known_at.min()
            embargo_end = block.label_end_ts.max() + pd.offsets.BDay(1)
            assert not ((train.known_at <= embargo_end) & (train.label_end_ts >= start)).any()


def _write_synthetic(root: Path, *, after_dev=False, days=30):
    labels_root = root / "labels_wide_v1" / "BTCUSDT"
    dense_root = root / "features" / "BTCUSDT"
    flow_root = root / "features_flow" / "BTCUSDT"
    labels_root.mkdir(parents=True); dense_root.mkdir(parents=True); flow_root.mkdir(parents=True)
    start = pd.Timestamp("2022-01-03", tz="UTC")
    anchors = []
    for day in range(days):
        base = start + pd.Timedelta(days=day)
        anchors.extend(base + pd.Timedelta(minutes=minute) for minute in (0, 15, 30, 45))
    rows = []
    for number, ts in enumerate(anchors):
        feature = np.sin(number / 11)
        for side in (-1, 1):
            for sl in (1., 1.5, 2., 3., 4.):
                for tp in (.5, 1., 1.5, 2., 3.):
                    hit = int((feature * side + .15 * (2 - tp)) > 0)
                    rows.append({"ts":ts, "side":side, "sl_atr":sl, "tp_r":tp,
                        "outcome":"tp" if hit else "sl", "net_R":tp if hit else -1.,
                        "gross_R":tp if hit else -1., "cost_R":0.,
                        "entry_ts":ts + pd.Timedelta(minutes=2),
                        "exit_ts":ts + pd.Timedelta(minutes=30),
                        "label_end_ts":(pd.Timestamp("2023-01-02", tz="UTC") if after_dev and number == 0
                                        else ts + pd.Timedelta(minutes=30)),
                        "deadline_ts":ts + pd.Timedelta(days=1), "fill_price":20_000.,
                        "planned_risk":100.})
    pd.DataFrame(rows).to_parquet(labels_root / "2022-01.parquet", index=False)
    known = pd.DatetimeIndex(anchors) + pd.Timedelta(minutes=1)
    dense = pd.DataFrame({"known_at":known, "ts":pd.DatetimeIndex(anchors),
                          "volume_z20":np.sin(np.arange(len(known)) / 11)})
    flow = pd.DataFrame({"known_at":known, "ts":pd.DatetimeIndex(anchors),
                         "flow_coverage":True,
                         "spot_imbalance_15m":np.sin(np.arange(len(known)) / 11)})
    dense.to_parquet(dense_root / "2022-01.parquet", index=False)
    flow.to_parquet(flow_root / "2022-01.parquet", index=False)
    return root / "labels_wide_v1"


def test_dev_label_end_hard_fails(tmp_path):
    labels = _write_synthetic(tmp_path, after_dev=True, days=1)
    with pytest.raises(ValueError, match="label_end"):
        family._read_labels(labels, "BTCUSDT")


def test_small_synthetic_family_run_writes_report_card(tmp_path, monkeypatch):
    labels = _write_synthetic(tmp_path, days=30)
    monkeypatch.setattr(family, "random_direction", lambda *args, **kwargs: (55., 10, []))
    persisted=tmp_path/"saved_signals"
    result = family.run_one("f3_order_flow", "BTCUSDT", tmp_path, labels,
                            tmp_path / "reports", ledger=tmp_path / "trials.csv",
                            model_kind="lightgbm", random_seeds=2,
                            persist_signals_root=persisted)
    assert result["candidates"] == 30 * 4 * 50
    assert result["feature_count"] > 5
    assert (tmp_path / "reports" / "families_summary.md").exists()
    assert (tmp_path / "reports" / "cards" / "phase2_f3_order_flow_BTCUSDT_dev.json").exists()
    saved=pd.read_parquet(persisted/"f3_order_flow_BTCUSDT.parquet")
    assert len(saved)==result["signals"]
    assert {"ts","side","price","sl","tp","deadline_ts","net_R"} <= set(saved)
    rows = pd.read_csv(tmp_path / "trials.csv")
    assert len(rows) == 1
    assert rows.iloc[0].period == "dev"
    assert json.loads(rows.iloc[0].parameters)["protocol"] == "phase2_family_v1"
