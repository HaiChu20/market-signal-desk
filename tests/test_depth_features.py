"""Offline causality and boundary checks for Binance depth features."""
import hashlib
import zipfile

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from pandas.testing import assert_frame_equal

from msd.data.depth_features import build_month, make_features, parse_raw_zip, write_month


def snapshots(ts: pd.DatetimeIndex) -> pd.DataFrame:
    data: dict[str, object] = {"ts": ts}
    for band in (1, 2, 5):
        data[f"depth_bid_{band}pct"] = 100 + band + np.arange(len(ts), dtype=float)
        data[f"depth_ask_{band}pct"] = 120 + band - np.arange(len(ts), dtype=float) / 4
    data["notional_bid_5pct"] = 1_000 + np.arange(len(ts), dtype=float)
    data["notional_ask_5pct"] = 1_100 + np.arange(len(ts), dtype=float) / 2
    return pd.DataFrame(data)


def test_later_snapshot_cannot_change_earlier_features() -> None:
    start = pd.Timestamp("2023-01-01", tz="UTC")
    base = snapshots(pd.date_range(start + pd.Timedelta(seconds=30), periods=100, freq="min"))
    original = make_features(base, start, start + pd.Timedelta(minutes=100))
    modified = base.copy()
    modified.loc[modified.ts >= start + pd.Timedelta(minutes=50), "depth_bid_1pct"] *= 100
    changed = make_features(modified, start, start + pd.Timedelta(minutes=100))
    assert_frame_equal(original.iloc[:49], changed.iloc[:49])
    assert original.loc[50, "depth_imbalance_1pct"] != changed.loc[50, "depth_imbalance_1pct"]
    assert (original.snapshot_ts <= original.known_at).all()


def test_stale_snapshot_has_nan_features() -> None:
    start = pd.Timestamp("2023-01-01", tz="UTC")
    frame = make_features(snapshots(pd.DatetimeIndex([start])), start, start + pd.Timedelta(minutes=5))
    assert frame.coverage.tolist() == [True, True, False, False, False]
    feature_columns = [col for col in frame if col.startswith("depth_imbalance_") or col.startswith("total_depth_")]
    assert frame.loc[2:, feature_columns].isna().all().all()
    assert frame.loc[2, "staleness_seconds"] == 180


def test_monthly_warmup_equals_single_run() -> None:
    boundary = pd.Timestamp("2023-02-01", tz="UTC")
    warm_start = boundary - pd.Timedelta(days=8)
    end = boundary + pd.Timedelta(days=2)
    source = snapshots(pd.date_range(warm_start, end, freq="min", inclusive="left"))
    whole = make_features(source, warm_start, end)
    chunk = make_features(source.loc[source.ts >= boundary - pd.Timedelta(days=7)],
                          boundary - pd.Timedelta(days=7), end)
    expected = whole.loc[whole.ts >= boundary].reset_index(drop=True)
    actual = chunk.loc[chunk.ts >= boundary].reset_index(drop=True)
    assert_frame_equal(expected, actual)


def test_monthly_loader_includes_snapshot_at_next_month_boundary(tmp_path) -> None:
    boundary = pd.Timestamp("2023-02-01", tz="UTC")
    source = snapshots(pd.DatetimeIndex([boundary - pd.Timedelta(minutes=2), boundary]))
    base = tmp_path / "data/aux/binance_depth/BTCUSDT"
    base.mkdir(parents=True)
    for month in ("2023-01", "2023-02"):
        part = source.loc[source.ts.dt.strftime("%Y-%m") == month]
        pq.write_table(pa.Table.from_pandas(part, preserve_index=False), base / f"{month}.parquet")
    frame, _ = build_month(tmp_path, "BTCUSDT", "2023-01")
    last = frame.iloc[-1]
    assert last.ts == boundary - pd.Timedelta(minutes=1)
    assert last.snapshot_ts == boundary
    assert last.staleness_seconds == 0


def test_raw_decimal_bands_are_integral_and_verified(tmp_path) -> None:
    path = tmp_path / "BTCUSDT-bookDepth-2026-01-01.zip"
    rows = ["timestamp,percentage,depth,notional"]
    rows += [f"2026-01-01 00:00:09,{band:.2f},{100 + band},{1000 + band}"
             for band in (-5, -4, -3, -2, -1, -0.2, 0.2, 1, 2, 3, 4, 5)]
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("bookDepth.csv", "\n".join(rows))
    path.with_name(path.name + ".sha256").write_text(hashlib.sha256(path.read_bytes()).hexdigest() + "  " + path.name)
    result = parse_raw_zip(path)
    assert len(result) == 1
    assert result.iloc[0].depth_bid_5pct == 95
    assert result.iloc[0].notional_ask_5pct == 1005


def test_http_404_day_is_flagged_and_all_features_nan(tmp_path) -> None:
    start = pd.Timestamp("2023-02-08", tz="UTC")
    source = snapshots(pd.DatetimeIndex([start - pd.Timedelta(minutes=1), start + pd.Timedelta(minutes=1)]))
    base = tmp_path / "data/aux/binance_depth/ETHUSDT"
    base.mkdir(parents=True)
    for month in ("2023-02",):
        pq.write_table(pa.Table.from_pandas(source, preserve_index=False), base / f"{month}.parquet")
    log = tmp_path / "data/logs/missing_bookdepth.csv"
    log.parent.mkdir(parents=True)
    log.write_text("symbol,date_or_month,scope,reason\nETHUSDT,2023-02-08,fetch_day,HTTP 404\n")
    frame, stats = build_month(tmp_path, "ETHUSDT", "2023-02")
    day = frame.loc[frame.ts.dt.strftime("%Y-%m-%d") == "2023-02-08"]
    assert len(day) == 1440 and day.source_missing_day.all()
    assert not day.coverage.any()
    assert day[[c for c in day if c.startswith(("depth_imbalance_", "total_depth_"))]].isna().all().all()
    assert stats["missing_day_minutes"] == 1440
    raw = tmp_path / "data/raw/binance/bookDepth/ETHUSDT"
    raw.mkdir(parents=True)
    (raw / "ETHUSDT-bookDepth-2023-02-08.zip").write_bytes(b"verified")
    (raw / "ETHUSDT-bookDepth-2023-02-08.zip.sha256").write_text("verified")
    recovered, stats = build_month(tmp_path, "ETHUSDT", "2023-02")
    assert stats["missing_day_minutes"] == 0
    assert not recovered.source_missing_day.any()


def test_failed_row_count_check_removes_own_part_file(monkeypatch, tmp_path) -> None:
    frame = pd.DataFrame({"ts": pd.to_datetime(["2023-01-01"], utc=True)})
    real_metadata = pq.read_metadata

    class WrongRows:
        num_rows = 0

    monkeypatch.setattr(pq, "read_metadata", lambda path: WrongRows()
                       if ".part." in str(path) else real_metadata(path))
    with np.testing.assert_raises_regex(ValueError, "row count mismatch"):
        write_month(tmp_path, "BTCUSDT", "2023-01", frame)
    assert not list((tmp_path / "data/features_depth/BTCUSDT").glob("*.part.*"))
