from pathlib import Path
import time

import pandas as pd

from msd.live import swing_shadow as shadow
from msd.research import swing_stage1 as stage1


def _bars(times):
    frame = pd.DataFrame({"ts": pd.to_datetime(times, utc=True)})
    for side in ("bid", "ask"):
        for field in "ohlc":
            frame[f"{side}_{field}"] = 100.0
    return frame


def _slow_refresh_worker(data_root, market, now, connection):
    time.sleep(1)


def test_state_replay_completed_rows_equal_evaluate_market(monkeypatch):
    bars = _bars(["2022-01-03 07:00Z", "2022-01-04 07:00Z"])
    signal = pd.DataFrame({
        "end": pd.to_datetime(["2022-01-02 22:00Z"], utc=True),
        "c": [100.0], "atr": [1.0], "S1": [0], "S2": [0], "S3": [1],
    })
    monkeypatch.setattr(stage1, "daily_bars", lambda bars, period: signal)
    monkeypatch.setattr(stage1, "signals", lambda daily, first_year: signal)
    monkeypatch.setattr(stage1, "exit_trade",
                        lambda ts, prices, mask, entry, side, stop, target, cap:
                        (1, 103.0, "tp"))
    replayed, replay_drops, _ = stage1.replay_market(
        bars, "USATECHIDXUSD", primary_only=True, setups=("S3",)
    )
    evaluated, evaluate_drops = stage1.evaluate_market(
        bars, "USATECHIDXUSD", primary_only=True, setups=("S3",)
    )
    assert replayed == evaluated
    assert replay_drops == evaluate_drops


def test_live_period_loads_partial_end_month_but_dev_does_not(monkeypatch, tmp_path: Path):
    directory = tmp_path / "bars/dukascopy/USATECHIDXUSD"
    directory.mkdir(parents=True)
    for month in ("2022-12", "2023-01", "2026-10", "2026-11"):
        (directory / f"{month}.parquet").touch()
    opened = []

    def fake_load(symbol, start, end, root):
        opened.append(start.strftime("%Y-%m"))
        stamp = pd.Timestamp(start)
        frame = _bars([stamp])
        return frame

    monkeypatch.setattr(stage1, "load_dukascopy", fake_load)
    stage1.load_minutes(tmp_path, "USATECHIDXUSD")
    assert opened == ["2022-12"]
    opened.clear()
    stage1.load_minutes(
        tmp_path, "USATECHIDXUSD",
        period=stage1.Period(
            data_start=pd.Timestamp("2026-10-01", tz="UTC"),
            end=pd.Timestamp("2026-11-13 05:01", tz="UTC"),
        ),
    )
    assert opened == ["2026-10", "2026-11"]


def test_stale_data_guard_uses_latest_new_york_close():
    now = pd.Timestamp("2026-11-13 22:05Z")
    assert shadow.latest_ny_close(now) == pd.Timestamp("2026-11-13 22:00Z")
    assert shadow.is_stale(pd.Timestamp("2026-11-13 21:58Z"), now)
    assert not shadow.is_stale(pd.Timestamp("2026-11-13 21:59Z"), now)
    # Before Monday's close, Friday remains the required close.
    assert shadow.latest_ny_close(pd.Timestamp("2026-11-16 12:00Z")) == pd.Timestamp(
        "2026-11-13 22:00Z"
    )
    # Intended 05:00 UTC run: prior day's 17:00 New York close, in both DST regimes.
    assert shadow.latest_ny_close(pd.Timestamp("2026-11-13 05:00Z")) == pd.Timestamp(
        "2026-11-12 22:00Z"
    )
    assert shadow.latest_ny_close(pd.Timestamp("2026-07-14 05:00Z")) == pd.Timestamp(
        "2026-07-13 21:00Z"
    )
    assert not shadow.is_stale(pd.Timestamp("2026-11-12 21:59Z"),
                               pd.Timestamp("2026-11-13 05:00Z"))


def test_append_log_deduplicates_market_and_signal_close(tmp_path: Path):
    path = tmp_path / "swing_v1.csv"
    record = {column: "" for column in shadow.LOG_COLUMNS}
    record.update({"market": "BTCUSDT", "signal_close": "2026-11-13T22:00:00+00:00"})
    assert shadow.append_records(path, [record]) == 1
    assert shadow.append_records(path, [record]) == 0
    rows = pd.read_csv(path)
    assert len(rows) == 1


def test_non_stale_row_may_follow_stale_but_never_reverse(tmp_path: Path):
    path = tmp_path / "swing_v1.csv"
    base = {column: "" for column in shadow.LOG_COLUMNS}
    base.update({"market": "XAUUSD", "signal_close": "2026-11-12T22:00:00+00:00"})
    stale = {**base, "stale": "true", "state": "STALE"}
    fresh = {**base, "stale": "false", "state": "FLAT"}
    assert shadow.append_records(path, [stale]) == 1
    assert shadow.append_records(path, [stale]) == 0
    assert shadow.append_records(path, [fresh]) == 1
    assert shadow.append_records(path, [stale]) == 0
    assert shadow.append_records(path, [fresh]) == 0
    assert pd.read_csv(path).state.tolist() == ["STALE", "FLAT"]


def test_dukascopy_refresh_stops_at_last_complete_utc_day(monkeypatch, tmp_path: Path):
    captured = {}

    def fake_download(symbol, start, end, root, workers):
        captured.update(symbol=symbol, start=start, end=end, root=root, workers=workers)

    monkeypatch.setattr(shadow.dukascopy, "download", fake_download)
    shadow.refresh_market(tmp_path, "XAUUSD", pd.Timestamp("2026-11-13 05:00Z"))
    assert captured["end"].isoformat() == "2026-11-12"
    assert captured["root"] == tmp_path / "bars/dukascopy"


def test_market_refresh_has_hard_timeout(tmp_path: Path):
    started = time.monotonic()
    try:
        shadow.refresh_with_timeout(
            tmp_path, "BTCUSDT", pd.Timestamp("2026-11-13 05:00Z"),
            timeout_seconds=.05, _worker=_slow_refresh_worker,
        )
    except TimeoutError as exc:
        assert "BTCUSDT refresh exceeded" in str(exc)
    else:
        raise AssertionError("refresh did not time out")
    assert time.monotonic() - started < .8


def test_message_header_names_run_and_planned_entry_times(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(shadow, "MARKETS", ())
    message = shadow.run(
        tmp_path / "data", tmp_path / "shadow",
        now=pd.Timestamp("2026-11-13 05:00Z"), refresh=False,
    )
    assert "run 2026-11-13T05:00:00+00:00" in message
    assert "planned entry 2026-11-13T07:00:00+00:00" in message
    assert "Intended daily run time: about 05:00 UTC" in message


def test_no_plan_while_trade_is_open(monkeypatch):
    now = pd.Timestamp("2026-11-13 22:05Z")
    bars = _bars(["2026-11-12 21:59Z", "2026-11-13 21:59Z"])
    daily = pd.DataFrame({
        "end": pd.to_datetime(["2026-11-12 22:00Z", "2026-11-13 22:00Z"], utc=True),
        "c": [99.0, 100.0], "atr": [2.0, 2.0],
    })
    signal = daily.assign(S1=0, S2=0, S3=1)
    monkeypatch.setattr(stage1, "daily_bars", lambda bars, period: daily)
    monkeypatch.setattr(stage1, "signals", lambda frame, first_year: signal)
    open_trade = {
        "market": "BTCUSDT", "setup": "S3", "sl_atr": 2.0, "tp_R": 3.0,
        "signal_end": "2026-11-10T22:00:00+00:00",
        "entry_ts": "2026-11-11T07:00:00+00:00", "entry_index": 0,
        "entry_price": 100.0, "side": 1, "risk": 4.0, "stop": 96.0,
        "target": 112.0, "cap_index": 2,
        "cap_session_end": "2026-12-22T22:00:00+00:00",
    }
    monkeypatch.setattr(
        stage1, "replay_market",
        lambda *args, **kwargs: ([], {}, {("S3", 2.0, 3.0): open_trade}),
    )
    record, message = shadow.analyze_market(bars, "BTCUSDT", now)
    assert record["state"] == "OPEN"
    assert record["plan_entry_ts"] == ""
    assert "No new plan while the trade is open." in message
    assert "NEW " not in message


def test_refresh_error_fails_closed_even_when_local_bars_are_fresh(monkeypatch):
    now = pd.Timestamp("2026-11-13 05:00Z")
    bars = _bars(["2026-11-11 21:59Z", "2026-11-12 21:59Z"])
    daily = pd.DataFrame({
        "end": pd.to_datetime(["2026-11-11 22:00Z", "2026-11-12 22:00Z"], utc=True),
        "c": [99.0, 100.0], "atr": [2.0, 2.0],
    })
    monkeypatch.setattr(stage1, "daily_bars", lambda bars, period: daily)
    monkeypatch.setattr(stage1, "signals",
                        lambda frame, first_year: frame.assign(S1=0, S2=0, S3=1))
    monkeypatch.setattr(stage1, "replay_market", lambda *args, **kwargs: ([], {}, {}))
    record, message = shadow.analyze_market(
        bars, "BTCUSDT", now, "TimeoutError: BTCUSDT refresh exceeded 600 seconds"
    )
    assert record["stale"] == "true"
    assert record["plan_entry_ts"] == ""
    assert "no new trade plan issued" in message
    assert "TimeoutError" in message
