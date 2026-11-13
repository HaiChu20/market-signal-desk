from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from msd.research.information_audit import (
    DEV_END,
    _asof_features,
    _cost_atr,
    audit_deadline_execution,
    _effective_daily_dvol,
    run,
)


def test_cfd_cost_is_round_trip_spread_in_one_hour_atr(tmp_path: Path):
    frame = pd.DataFrame({
        "ts": pd.date_range("2022-01-01", periods=3, freq="15min", tz="UTC"),
        "spread_atr": [0.5, 1.0, np.nan],
        "1m_atr14": [2.0, 2.0, 2.0],
        "1h_atr14": [10.0, 10.0, 10.0],
    })
    assert _cost_atr(tmp_path, tmp_path, "USATECHIDXUSD", frame) == pytest.approx(0.15)


def test_dvol_check_uses_one_non_overlapping_anchor_per_day():
    stamp = pd.date_range("2021-01-01", periods=8, freq="12h", tz="UTC")
    frame = pd.DataFrame({
        "known_at": stamp,
        "dvol_btc_level": np.arange(8, dtype=float),
        "return_1d": np.arange(8, dtype=float),
    })
    result = _effective_daily_dvol(frame)
    assert result["n"] == 4
    assert result["ic"] == pytest.approx(1.0)
    assert result["years"][0]["year"] == 2021
    assert result["years"][0]["n"] == 4
    assert result["years"][0]["ic"] == pytest.approx(1.0)


def test_asof_join_is_causal_under_future_perturbation(tmp_path: Path):
    directory = tmp_path / "features" / "TEST"
    directory.mkdir(parents=True)
    source = pd.DataFrame({
        "known_at": pd.to_datetime(["2022-01-01 10:00Z", "2022-01-01 11:00Z"]),
        "signal": [1.0, 2.0],
    })
    source.to_parquet(directory / "2022-01.parquet", index=False)
    anchors = pd.DataFrame({
        "ts": pd.to_datetime(["2022-01-01 10:29Z"]),
        "known_at": pd.to_datetime(["2022-01-01 10:30Z"]),
        "label_end_ts": pd.to_datetime(["2022-01-01 12:00Z"]),
    })
    before = _asof_features(tmp_path, "TEST", anchors, ["signal"], [])
    source.loc[1, "signal"] = 999.0
    source.to_parquet(directory / "2022-01.parquet", index=False)
    after = _asof_features(tmp_path, "TEST", anchors, ["signal"], [])
    assert before.signal.tolist() == after.signal.tolist() == [1.0]
    assert before.dense_known_at.iloc[0] <= anchors.known_at.iloc[0]


def test_audit_rejects_test_period_before_reading_data(tmp_path: Path):
    with pytest.raises(ValueError, match="cannot load 2023"):
        run(tmp_path, tmp_path, tmp_path / "out.md", end=DEV_END + pd.Timedelta(days=1))


def test_deadline_audit_distinguishes_gaps_from_skipped_bars(tmp_path: Path):
    target=tmp_path / "labels" / "USATECHIDXUSD"
    target.mkdir(parents=True)
    pd.DataFrame({
        "exit_ts": pd.to_datetime(["2022-01-01T10:02Z", "2022-01-01T10:02Z",
                                    "2022-01-01T10:02Z", "2022-01-01T10:00Z"]),
        "deadline_ts": pd.to_datetime(["2022-01-01T10:01Z", "2022-01-01T10:00Z",
                                        "2022-01-01T10:01Z", "2022-01-01T10:00Z"]),
        "exit_reason": ["time","time","tp","time"],
    }).to_parquet(target / "2022-01.parquet",index=False)
    bars=tmp_path / "bars" / "dukascopy" / "USATECHIDXUSD"
    bars.mkdir(parents=True)
    pd.DataFrame({"ts":pd.to_datetime(["2022-01-01T10:00Z", "2022-01-01T10:02Z",
                                        "2022-01-01T10:04Z"])}).to_parquet(bars / "2022-01.parquet",index=False)
    result=audit_deadline_execution(tmp_path,tmp_path/"labels",symbols=("USATECHIDXUSD",))[0]
    assert result == {"symbol":"USATECHIDXUSD","labels":4,"exit_after_deadline":3,
        "correct_first_bar_after_gap":1,"non_time_after_deadline":1,
        "time_exit_skipped_first_bar":1,"defective":2,"defective_share":0.5}
