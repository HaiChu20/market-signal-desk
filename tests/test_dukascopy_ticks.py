import hashlib
import http.client
import lzma
import struct
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

from msd.data import dukascopy_ticks as ticks

HOUR = datetime(2024, 6, 12, 12, tzinfo=timezone.utc)


def sample():
    rows = [(0, 5_000_100, 5_000_000, 3.0, 2.0),
            (100, 5_000_200, 5_000_100, 5.0, 4.0),
            (1000, 5_000_200, 5_000_100, 2.0, 5.0)]
    return lzma.compress(b"".join(struct.pack(">IIIff", *row) for row in rows))


def test_url_decode_and_scale():
    assert ticks.url("USA500IDXUSD", HOUR).endswith("/2024/05/12/12h_ticks.bi5")
    frame = ticks.decode_ticks(sample(), "USA500IDXUSD", HOUR)
    assert len(frame) == 3
    assert frame.iloc[0].bid == 5000.0
    assert frame.iloc[0].ask == pytest.approx(5000.1)
    assert frame.iloc[1].ts == pd.Timestamp("2024-06-12T12:00:00.100Z")
    with pytest.raises(ValueError, match="20 bytes"):
        ticks.decode_ticks(lzma.compress(b"bad"), "USA500IDXUSD", HOUR)


def test_flow_ofi_and_second_bars():
    frame = ticks.decode_ticks(sample(), "USA500IDXUSD", HOUR)
    minute, second, last = ticks.aggregate_ticks(frame)
    assert len(minute) == 1
    row = minute.iloc[0]
    assert row.tick_count == 3
    assert row.mean_spread == pytest.approx(0.1)
    assert row.bid_size_sum == 11
    assert row.ask_size_sum == 10
    assert row.size_imbalance == pytest.approx(1 / 21)
    assert row.ofi == pytest.approx(11)
    assert row.mid_low_ms == 0
    assert row.mid_high_ms == 100
    assert row.known_at == row.ts + pd.Timedelta(minutes=1)
    assert len(second) == 2
    assert second.iloc[0].tick_count == 2
    assert second.iloc[0].bid_o == 5000
    assert second.iloc[0].bid_c == pytest.approx(5000.1)
    assert second.iloc[0].known_at == second.iloc[0].ts + pd.Timedelta(seconds=1)
    assert last == (5000.1, 5000.2, 5.0, 2.0)


def test_scale_checked_against_stored_minute(monkeypatch, tmp_path):
    monkeypatch.setattr(ticks, "REFERENCE", tmp_path)
    path = tmp_path / "USA500IDXUSD/2024-06.parquet"
    path.parent.mkdir(parents=True)
    minute, _, _ = ticks.aggregate_ticks(ticks.decode_ticks(sample(), "USA500IDXUSD", HOUR))
    columns = ["ts", "bid_o", "bid_h", "bid_l", "bid_c", "ask_o", "ask_h", "ask_l", "ask_c"]
    minute[columns].to_parquet(path, index=False)
    assert ticks.ohlc_match_rate("USA500IDXUSD", "2024-06", minute) == (1, 1)
    wrong = minute[columns].copy()
    wrong[columns[1:]] /= 10
    wrong.to_parquet(path, index=False)
    with pytest.raises(ValueError, match="point scale"):
        ticks.ohlc_match_rate("USA500IDXUSD", "2024-06", minute)


class Response:
    def __init__(self, raw):
        self.raw = raw
        self.status = 200
    def getheader(self, name):
        return str(len(self.raw)) if name == "Content-Length" else None
    def read(self):
        return self.raw


class Connection:
    def __init__(self, raw):
        self.raw = raw
        self.requests = []
    def request(self, method, path, headers):
        self.requests.append((method, path, headers))
    def getresponse(self):
        return Response(self.raw)
    def close(self):
        pass


def test_fetch_resume(monkeypatch, tmp_path):
    raw = sample()
    monkeypatch.setattr(ticks, "RAW", tmp_path / "raw")
    monkeypatch.setattr(ticks.shutil, "disk_usage", lambda _: type("Space", (), {"free": 100 * 1024**3})())
    ticks._disconnect()
    connections = []
    def factory(host, timeout):
        conn = Connection(raw)
        connections.append(conn)
        return conn
    monkeypatch.setattr(ticks.http.client, "HTTPConnection", factory)
    _, path, _ = ticks.fetch_hour("USA500IDXUSD", HOUR)
    assert path.read_bytes() == raw
    assert Path(str(path) + ".sha256").read_text().split()[0] == hashlib.sha256(raw).hexdigest()
    assert ticks.fetch_hour("USA500IDXUSD", HOUR)[2] == "resume verified"
    assert len(connections) == 1 and len(connections[0].requests) == 1
    ticks._disconnect()


def test_keepalive_connection_reused_across_hours(monkeypatch, tmp_path):
    monkeypatch.setattr(ticks, "RAW", tmp_path / "raw")
    monkeypatch.setattr(ticks.shutil, "disk_usage", lambda _: type("Space", (), {"free": 100 * 1024**3})())
    ticks._disconnect()
    connections = []
    def factory(host, timeout):
        conn = Connection(sample())
        connections.append(conn)
        return conn
    monkeypatch.setattr(ticks.http.client, "HTTPConnection", factory)
    for i in range(3):
        _, path, _ = ticks.fetch_hour("USA500IDXUSD", HOUR + timedelta(hours=i))
        assert path.exists()
    assert len(connections) == 1
    assert len(connections[0].requests) == 3
    assert all(request[2]["Connection"] == "keep-alive" for request in connections[0].requests)
    ticks._disconnect()


def test_empty_hour_is_missing_without_retry(monkeypatch, tmp_path):
    monkeypatch.setattr(ticks, "RAW", tmp_path / "raw")
    monkeypatch.setattr(ticks.shutil, "disk_usage", lambda _: type("Space", (), {"free": 100 * 1024**3})())
    ticks._disconnect()
    conn = Connection(b"")
    monkeypatch.setattr(ticks.http.client, "HTTPConnection", lambda host, timeout: conn)
    assert ticks.fetch_hour("USA500IDXUSD", HOUR)[2] == "empty archive"
    assert len(conn.requests) == 1
    ticks._disconnect()


def test_reconnects_after_remote_disconnect(monkeypatch, tmp_path):
    monkeypatch.setattr(ticks, "RAW", tmp_path / "raw")
    monkeypatch.setattr(ticks.shutil, "disk_usage", lambda _: type("Space", (), {"free": 100 * 1024**3})())
    monkeypatch.setattr(ticks.time, "sleep", lambda _: None)
    ticks._disconnect()
    made = []
    class Dropped(Connection):
        def getresponse(self):
            raise http.client.RemoteDisconnected("connection dropped")
    def factory(host, timeout):
        conn = Dropped(sample()) if not made else Connection(sample())
        made.append(conn)
        return conn
    monkeypatch.setattr(ticks.http.client, "HTTPConnection", factory)
    assert ticks.fetch_hour("USA500IDXUSD", HOUR)[1].exists()
    assert len(made) == 2
    ticks._disconnect()


def test_tick_workers_env(monkeypatch):
    monkeypatch.delenv("MSD_TICK_WORKERS", raising=False)
    assert ticks.tick_workers() == 2
    monkeypatch.setenv("MSD_TICK_WORKERS", "4")
    assert ticks.tick_workers() == 4


def test_redirect_waits_out_dns_ttl_then_succeeds(monkeypatch, tmp_path):
    monkeypatch.setattr(ticks, "RAW", tmp_path / "raw")
    monkeypatch.setattr(ticks.shutil, "disk_usage", lambda _: type("Space", (), {"free": 100 * 1024**3})())
    waits = []
    monkeypatch.setattr(ticks.time, "sleep", waits.append)
    ticks._disconnect()
    made = []
    class Redirected(Connection):
        def getresponse(self):
            response = Response(b"")
            response.status = 301
            return response
    def factory(host, timeout):
        conn = Redirected(b"") if not made else Connection(sample())
        made.append(conn)
        return conn
    monkeypatch.setattr(ticks.http.client, "HTTPConnection", factory)
    assert ticks.fetch_hour("USA500IDXUSD", HOUR)[1].exists()
    assert len(made) == 2 and len(waits) == 1 and waits[0] >= ticks.REDIRECT_WAIT
    ticks._disconnect()
