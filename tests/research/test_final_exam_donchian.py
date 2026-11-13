from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd
import pytest

from msd.research import final_exam_donchian as final


def _minute_frame(start: str, periods: int) -> pd.DataFrame:
    ts = pd.date_range(start, periods=periods, freq="min", tz="UTC")
    price = pd.Series(range(periods), dtype=float) / 100 + 100
    frame = pd.DataFrame({"ts": ts, "volume": 1.0})
    for side in ("bid", "ask"):
        for field in "ohlc":
            frame[f"{side}_{field}"] = price.to_numpy()
    return frame


def _write_stamp(path: Path, stamp: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame({"ts": [pd.Timestamp(stamp)], "funding_rate": [0.0]})
    for side in ("bid", "ask"):
        for field in "ohlc":
            frame[f"{side}_{field}"] = 100.0
    frame.to_parquet(path, index=False)


def _complete_inventory(root: Path, *, funding: bool = True) -> None:
    for symbol in final.SYMBOLS:
        source = final.SOURCE[symbol]
        for month in pd.period_range("2024-01", "2024-12", freq="M"):
            _write_stamp(
                root / "bars" / source / symbol / f"{month}.parquet",
                f"{month}-02",
            )
        _write_stamp(root / "bars" / source / symbol / "2025-01.parquet", "2025-01-02")
        execution = "binance_um" if symbol == "BTCUSDT" else "dukascopy"
        if execution != source:
            _write_stamp(
                root / "bars" / execution / symbol / "2025-01.parquet", "2025-01-02"
            )
    if funding:
        _write_stamp(
            root / "aux" / "funding" / "BTCUSDT" / "2025-01.parquet",
            "2025-01-02 00:00",
        )


def test_input_inventory_uses_only_required_minute_and_funding_sources(tmp_path: Path):
    _complete_inventory(tmp_path)
    inventory = final.input_inventory(tmp_path)
    assert inventory["symbols"]["BTCUSDT"]["detector_source"] == "binance_spot"
    assert inventory["symbols"]["BTCUSDT"]["execution_source"] == "binance_um"
    assert inventory["symbols"]["XAUUSD"]["execution_source"] == "dukascopy"
    assert inventory["end_exclusive"]["BTCUSDT"].startswith("2025-01-02")


def test_input_inventory_refuses_missing_funding_month(tmp_path: Path):
    _complete_inventory(tmp_path, funding=False)
    with pytest.raises(FileNotFoundError, match="no monthly parquet|funding"):
        final.input_inventory(tmp_path)


def test_detector_features_are_causal_and_need_no_dense_feature_store():
    bars = _minute_frame("2024-01-01", 25 * 60)
    features = final._detector_features(bars, "BTCUSDT")
    assert len(features) == len(bars)
    assert {"1h_atr14", "1h_donchian20_position"} <= set(features)
    assert features["1h_atr14"].notna().any()
    assert features["1h_donchian20_position"].notna().any()
    assert (features.known_at == features.ts + pd.Timedelta(minutes=1)).all()


def test_open_at_end_filter_keeps_hits_and_only_real_time_exits():
    end = pd.Timestamp("2026-01-01", tz="UTC")
    frame = pd.DataFrame(
        {
            "outcome": ["tp", "sl", "time", "time"],
            "deadline_ts": [end + pd.Timedelta(days=1), end, end - pd.Timedelta(minutes=1), end],
            "exit_ts": [
                end - pd.Timedelta(minutes=1),
                end - pd.Timedelta(minutes=1),
                end - pd.Timedelta(minutes=1),
                end - pd.Timedelta(minutes=1),
            ],
        }
    )
    assert final._resolved_before_end(frame, end).tolist() == [True, True, True, False]


def test_verdict_uses_only_strictly_positive_pooled_net_r():
    assert final._verdict(0.0001) == "KEEP"
    assert final._verdict(0.0) == "DROP"
    assert final._verdict(-0.1) == "DROP"
    assert final._verdict(None) == "DROP"


def test_run_writes_exact_outputs_and_one_ledger_row_once(tmp_path: Path, monkeypatch):
    data = tmp_path / "data"
    events = tmp_path / "events"
    output = tmp_path / "reports"
    ledger = tmp_path / "trials.csv"
    inventory = {"end_exclusive": {symbol: "2026-01-01T00:00:00+00:00" for symbol in final.SYMBOLS}}
    manifest = {"inventory": inventory, "config_hash": "fixture"}
    metric = {
        "n": 2,
        "hit_rate": 0.5,
        "net_avg_R": 0.1,
        "t_stat": 0.2,
        "profit_factor": 1.1,
    }
    result = {
        **metric,
        "verdict": "KEEP",
        "random_direction_percentile": 80.0,
        "random_direction_matched_signals": 2,
        "random_direction_seeds": 200,
        "events": 3,
        "dropped_at_end": 1,
        "per_market": {symbol: metric for symbol in final.SYMBOLS},
        "per_year": {"2025": metric},
    }
    monkeypatch.setattr(final, "_assert_frozen_provenance", lambda: None)
    monkeypatch.setattr(final, "_load_manifest", lambda _: manifest)
    monkeypatch.setattr(final, "input_inventory", lambda _: inventory)
    monkeypatch.setattr(final, "_result", lambda *_: (result, pd.DataFrame()))

    payload = final.run(data, events, output, ledger)
    assert payload["result"]["verdict"] == "KEEP"
    assert (output / "donchian.md").exists()
    assert (output / "donchian.json").exists()
    with ledger.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert [row["run_id"] for row in rows] == [final.RUN_ID]
    with pytest.raises(FileExistsError, match="already exists"):
        final.run(data, events, output, ledger)
