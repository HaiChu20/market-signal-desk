import csv
import gzip
import hashlib
import io
import json
from datetime import date
from pathlib import Path
from urllib.error import HTTPError

import pandas as pd
import pytest

from msd.data import archive_download, binance_depth, bybit


def test_bybit_parser_and_asof(tmp_path):
    path = tmp_path / "trades.csv.gz"
    with gzip.open(path, "wt") as out:
        out.write("timestamp,side,size,price\n")
        out.write("1704067200.1,Buy,2,100\n")
        out.write("1704067200.8,Sell,1,110\n")
        out.write("1704067260.0,Buy,3,120\n")
    bars = bybit.aggregate_files([path], "2024-01")
    assert len(bars) == 2
    assert bars.iloc[0].buy_taker_volume == 2
    assert bars.iloc[0].sell_taker_volume == 1
    assert bars.iloc[0].delta == 1
    assert bars.iloc[0].vwap_buy == 100
    assert bars.iloc[0].vwap_sell == 110
    assert bars.iloc[0].max_trade == 2
    assert bars.iloc[0].known_at == bars.iloc[1].ts
    assert bars.iloc[0].known_at > bars.iloc[0].ts
    assert pd.merge_asof(pd.DataFrame({"decision": [bars.iloc[0].ts]}),
                        bars.rename(columns={"known_at": "decision"}).sort_values("decision"),
                        on="decision").delta.isna().all()


def test_bybit_rejects_bad_side():
    with pytest.raises(ValueError):
        bybit.parse_trade({"timestamp": "1", "side": "Maker", "size": "1", "price": "2"})


def test_bybit_memory_matches_disk_and_manifest_resume(monkeypatch, tmp_path):
    raw = gzip.compress(b"timestamp,side,size,price\n1704067200.1,Buy,2,100\n"
                        b"1704067200.8,Sell,1,110\n")
    path = tmp_path / "2024-01-01.csv.gz"
    path.write_bytes(raw)
    pd.testing.assert_frame_equal(bybit.aggregate_bytes(raw, "2024-01"),
                                  bybit.aggregate_files([path], "2024-01"))
    monkeypatch.setattr(bybit, "OUT", tmp_path / "bars")
    monkeypatch.setattr(bybit, "MISSING", tmp_path / "missing.csv")
    monkeypatch.setattr(bybit, "START", date(2024, 1, 1))
    monkeypatch.setattr(bybit, "SYMBOLS", ("BTCUSDT",))
    monkeypatch.setattr(bybit, "listed_days", lambda _: {date(2024, 1, 1)})
    monkeypatch.setattr(bybit, "remote_size", lambda _: len(raw))
    monkeypatch.setattr(bybit.shutil, "disk_usage", lambda _: type("Space", (), {"free": 100 * 1024**3})())
    monkeypatch.setattr(bybit, "urlopen", lambda request, timeout: FakeResponse(raw))
    bybit.run_no_raw(date(2024, 1, 1))
    target = tmp_path / "bars/BTCUSDT/2024-01.parquet"
    assert len(pd.read_parquet(target)) == 1
    entry = json.loads((tmp_path / "bars/BTCUSDT/manifest.json").read_text())["days"]["2024-01-01"]
    assert entry["bytes"] == len(raw)
    assert entry["sha256"] == hashlib.sha256(raw).hexdigest()
    assert entry["row_count"] == 2
    monkeypatch.setattr(bybit, "urlopen", lambda request, timeout: pytest.fail("completed day re-downloaded"))
    bybit.run_no_raw(date(2024, 1, 1))


def test_depth_parser_and_imbalance():
    rows = [{"timestamp": "2023-01-01 00:06:05", "percentage": str(p),
             "depth": str(2 if p < 0 else 1), "notional": str(4 if p < 0 else 2)}
            for p in list(range(-5, 0)) + list(range(1, 6))]
    frame = binance_depth.parse_depth_rows(rows)
    assert len(frame) == 1
    assert frame.iloc[0].known_at == frame.iloc[0].ts
    assert frame.iloc[0].depth_bid_1pct == 2
    assert frame.iloc[0].depth_ask_1pct == 1
    assert frame.iloc[0].depth_imbalance_1pct == pytest.approx(1 / 3)
    with pytest.raises(ValueError):
        binance_depth.parse_depth_rows(rows[:-1])


class FakeResponse(io.BytesIO):
    def __init__(self, data, length=None):
        super().__init__(data)
        self.headers = {"Content-Length": str(len(data) if length is None else length)}


def test_archive_resume_skip_and_size(monkeypatch, tmp_path):
    data = b"archive contents"
    calls = []
    def fake_open(request, timeout):
        calls.append(request.full_url)
        return FakeResponse(data)
    monkeypatch.setattr(archive_download, "urlopen", fake_open)
    monkeypatch.setattr(archive_download.shutil, "disk_usage", lambda _: type("Space", (), {"free": 100 * 1024**3})())
    target = tmp_path / "file.zip"
    digest = archive_download.stream_archive("https://example.test/file.zip", target, len(data), retries=1)
    assert digest == hashlib.sha256(data).hexdigest()
    assert target.read_bytes() == data
    assert Path(str(target) + ".sha256").exists()
    assert archive_download.stream_archive("https://example.test/file.zip", target, len(data), retries=1) == digest
    assert len(calls) == 1
    with pytest.raises(RuntimeError):
        archive_download.stream_archive("https://example.test/bad.zip", tmp_path / "bad.zip", len(data) + 1, retries=1)
    assert not (tmp_path / "bad.zip").exists()


def test_missing_logging_and_404(monkeypatch, tmp_path):
    monkeypatch.setattr(bybit, "MISSING", tmp_path / "missing_bybit.csv")
    bybit.log_missing("BTCUSDT", date(2020, 3, 26), "absent from listing")
    rows = list(csv.DictReader(bybit.MISSING.open()))
    assert rows[0]["date"] == "2020-03-26"
    def missing(request, timeout):
        raise HTTPError(request.full_url, 404, "missing", {}, None)
    monkeypatch.setattr(archive_download, "urlopen", missing)
    assert archive_download.remote_size("https://example.test/missing") is None
