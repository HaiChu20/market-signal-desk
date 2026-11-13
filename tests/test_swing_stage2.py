import numpy as np
import pandas as pd

from msd.research import swing_stage2 as stage2
from msd.research.swing_stage2 import (OPTIONS, choose_option, daily_features,
                                       sequential_trades, training_mask)


def test_features_use_only_completed_signal_days():
    ends = pd.date_range("2020-01-01 22:00Z", periods=400, freq="D")
    daily = pd.DataFrame({"end": ends, "c": 100.+np.arange(400)*.1,
                          "atr": np.full(400, 2.)})
    original = daily_features(daily).iloc[300].copy()
    daily.loc[301:, "c"] += 10000.
    daily.loc[301:, "atr"] *= 100.
    pd.testing.assert_series_equal(original, daily_features(daily).iloc[300])
    assert np.isfinite(original.to_numpy(float)).all()


def test_walk_forward_purges_exit_at_year_boundary():
    exits = np.array(["2019-12-31T23:59:00", "2020-01-01T00:00:00",
                      "2020-01-02T00:00:00"], dtype="datetime64[ns]")
    assert training_mask(exits, 2020).tolist() == [True, False, False]
    assert training_mask(exits, 2021).tolist() == [True, True, True]


def test_walk_forward_model_receives_only_purged_rows(monkeypatch):
    exits = np.array(["2019-12-31T23:59:00", "2020-01-01T00:00:00"],
                     dtype="datetime64[ns]")
    monkeypatch.setattr(stage2, "YEARS", (2020,))
    monkeypatch.setattr(stage2, "make_training_rows", lambda _: (
        np.ones((2, len(stage2.FEATURES)), dtype=np.float32),
        np.array([1., 2.], dtype=np.float32), exits))
    captured = {}
    monkeypatch.setattr(stage2.lgb, "Dataset", lambda data, label, feature_name: (data, label))
    def fake_train(params, dataset, num_boost_round):
        captured["labels"] = dataset[1].tolist()
        return object()
    monkeypatch.setattr(stage2.lgb, "train", fake_train)
    stage2.walk_forward({market:[] for market in stage2.s1.TRADED}, {})
    assert captured["labels"] == [1.]


def _opportunity(entry, exit_index, best=.1):
    labels = [None]*len(OPTIONS)
    labels[0] = {"entry_index":entry,"exit_index":exit_index,"net_R":.2}
    prediction = np.full(len(OPTIONS), -.1)
    prediction[0] = best
    return {"entry_index":entry,"labels":labels,"predictions":prediction}


def test_sequential_never_overlaps_one_market():
    rows, counts = sequential_trades([_opportunity(0,2),_opportunity(1,3),
                                      _opportunity(3,5)])
    assert [r["entry_index"] for r in rows] == [0,3]
    assert counts["blocked_open"] == 1


def test_skip_when_best_prediction_below_threshold():
    assert choose_option(np.full(len(OPTIONS), .049)) is None
    assert choose_option(np.full(len(OPTIONS), .05)) == 0
    rows, counts = sequential_trades([_opportunity(0,1,.049)])
    assert rows == []
    assert counts["skip_rate"] == 1.
