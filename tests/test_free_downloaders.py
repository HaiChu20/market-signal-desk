import csv
import gzip
import hashlib
import io
import json
from datetime import date
from pathlib import Path
from urllib.error import HTTPError

import numpy as np
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


def _archive(*rows: str, header: str = "timestamp,side,size,price") -> bytes:
    return gzip.compress(("\n".join((header, *rows)) + "\n").encode())


@pytest.mark.parametrize("row, header, message", [
    ("1704067200,Maker,1,2", "timestamp,side,size,price", "invalid taker side: maker"),
    ("1704067200,Buy,-1,100", "timestamp,side,size,price", "invalid size or price"),
    ("1704067200,Buy,1,0", "timestamp,side,size,price", "invalid size or price"),
    ("1706745600,Buy,1,100", "timestamp,side,size,price", "outside archive month"),
    ("1704067200,1", "timestamp,size", "schema mismatch"),
])
def test_bybit_rejects_invalid_archives(row, header, message):
    with pytest.raises(ValueError, match=message):
        bybit.aggregate_bytes(_archive(row, header=header), "2024-01")


def test_bybit_fetch_day_waits_out_rate_limit_then_succeeds(monkeypatch):
    calls, waits = [], []

    def size(_):
        calls.append(1)
        if len(calls) < 3:
            raise HTTPError("u", 403, "Forbidden", {}, None)
        return 10

    monkeypatch.setattr(bybit, "remote_size", size)
    monkeypatch.setattr(bybit, "stream_archive", lambda *args: "digest")
    monkeypatch.setattr(bybit.time, "sleep", waits.append)
    assert bybit.fetch_day("BTCUSDT", date(2024, 1, 1))[2] == "10 bytes"
    assert waits == list(bybit.BLOCK_WAITS[:2])
    monkeypatch.setattr(bybit, "remote_size", lambda _: (_ for _ in ()).throw(HTTPError("u", 500, "x", {}, None)))
    with pytest.raises(HTTPError):
        bybit.fetch_day("BTCUSDT", date(2024, 1, 1))


def test_bybit_zero_size_dust_trade_keeps_count():
    bars = bybit.aggregate_bytes(_archive("1593339590.1551,Sell,0.0,9055.5"), "2020-06")
    assert bars.trade_count.tolist() == [1] and bars.sell_trade_count.tolist() == [1]
    assert bars.sell_taker_volume.tolist() == [0.0] and bars.vwap_sell.isna().all()


def test_bybit_vectorised_sums_equal_sequential_row_loop(tmp_path):
    rng = np.random.default_rng(7)
    stamps = 1704067200 + np.sort(rng.uniform(0, 1200, 4000)).round(4)
    rows = [f"{t},{rng.choice(['Buy', 'Sell'])},{rng.uniform(0, 3):.6f},{rng.uniform(4e4, 5e4):.2f}"
            for t in stamps]
    paths = []
    # The split falls inside a minute, so that minute accumulates across two files.
    for name, part in (("a", rows[:2001]), ("b", rows[2001:])):
        paths.append(tmp_path / f"{name}.csv.gz")
        paths[-1].write_bytes(_archive(*part))
    acc = {}
    for row in rows:
        stamp, side, size, price = row.split(",")
        size, price, s = float(size), float(price), 0 if side == "Buy" else 1
        v = acc.setdefault(pd.to_datetime(float(stamp), unit="s", utc=True).floor("min"), [0.0] * 8)
        v[s] += size; v[s + 2] += 1; v[s + 4] += size * price; v[6] = max(v[6], size); v[7] += 1
    expected = pd.DataFrame.from_records(
        [{"ts": ts, "known_at": ts + pd.Timedelta(minutes=1), "buy_taker_volume": v[0],
          "sell_taker_volume": v[1], "delta": v[0] - v[1], "buy_trade_count": int(v[2]),
          "sell_trade_count": int(v[3]), "vwap_buy": v[4] / v[0] if v[0] else float("nan"),
          "vwap_sell": v[5] / v[1] if v[1] else float("nan"), "max_trade": v[6],
          "trade_count": int(v[7])} for ts, v in sorted(acc.items())], columns=bybit.COLUMNS)
    pd.testing.assert_frame_equal(bybit.aggregate_files(paths, "2024-01"), expected, check_exact=True)


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
    before = target.stat().st_mtime_ns
    assert bybit.write_month("BTCUSDT", "2024-01", [path]) == 1
    assert target.stat().st_mtime_ns == before
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


def test_depth_decimal_and_optional_band():
    rows = [{"timestamp": "2026-01-15 00:00:09", "percentage": f"{p:.2f}",
             "depth": "2" if p < 0 else "1", "notional": "4" if p < 0 else "2"}
            for p in (-5, -4, -3, -2, -1, -0.2, 0.2, 1, 2, 3, 4, 5)]
    frame = binance_depth.parse_depth_rows(rows)
    assert frame.iloc[0].depth_bid_5pct == 2
    assert frame.iloc[0].depth_ask_0p2pct == 1
    assert frame.iloc[0].depth_imbalance_1pct == pytest.approx(1 / 3)
    with pytest.raises(ValueError, match="invalid bookDepth band"):
        binance_depth.parse_depth_rows([*rows, {**rows[0], "percentage": "0.50"}])
    with pytest.raises(ValueError, match="incomplete optional"):
        binance_depth.parse_depth_rows([r for r in rows if r["percentage"] != "0.20"])


def test_depth_run_logs_day_and_month_errors_and_continues(monkeypatch, tmp_path):
    missing = tmp_path / "missing_bookdepth.csv"
    monkeypatch.setattr(binance_depth, "MISSING", missing)
    def fetch(symbol, day):
        if symbol == "BTCUSDT":
            raise ValueError("bad day")
        return day, tmp_path / f"{symbol}-bookDepth-{day}.zip", "verified"
    monkeypatch.setattr(binance_depth, "fetch_day", fetch)
    monkeypatch.setattr(binance_depth, "write_month", lambda *args: (_ for _ in ()).throw(ValueError("bad month")))
    binance_depth.run(date(2023, 1, 1))
    rows = list(csv.DictReader(missing.open()))
    assert [(r["symbol"], r["scope"]) for r in rows] == [
        ("BTCUSDT", "fetch_day"), ("ETHUSDT", "aggregate_month")]


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
