from pathlib import Path
import time

import pandas as pd
import pytest

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


class FakeTelegram:
    token = "token-secret"
    chat_id = "chat-secret"

    def __init__(self, failures=0):
        self.messages = []
        self.failures = failures

    def send_message(self, text):
        if self.failures:
            self.failures -= 1
            raise RuntimeError(f"transport exposed {self.token} and {self.chat_id}")
        self.messages.append(text)


def _telegram_record(market, contract, **values):
    record = {column: "" for column in shadow.LOG_COLUMNS}
    record.update({"market": market, "contract": contract,
                   "signal_close": "2026-11-12T22:00:00+00:00",
                   "stale": "false", "state": "FLAT"})
    record.update(values)
    return record


def _seed_telegram_history(path: Path, now: pd.Timestamp):
    event = {"event_id": "ALL|CONNECTED|initial", "market": "ALL",
             "event_type": "CONNECTED", "reference": "initial"}
    shadow._append_sent(path / "telegram_sent.csv", [event], now)


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
    assert "Intended daily run: 07:00 Europe/Helsinki" in message


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


def test_first_send_is_one_connected_message_with_all_current_states(tmp_path: Path):
    now = pd.Timestamp("2026-11-17 05:00Z")
    records = [
        _telegram_record(
            "USATECHIDXUSD", "MNQ", state="OPEN", side=1,
            entry_ts="2026-11-10T07:00:00+00:00", entry_price=25000., sl=24500.,
            tp=26500., unrealised_R=.4, cap_session_end="2026-12-21T22:00:00+00:00",
        ),
        _telegram_record(
            "XAUUSD", "MGC", side=-1, plan_entry_ts="2026-11-17T07:00:00+00:00",
            reference_price=4100., sl_distance=100., tp_distance=300.,
            plan_sl=4200., plan_tp=3800.,
        ),
        _telegram_record("BTCUSDT", "MBT", state="STALE", stale="true",
                         refresh_error="TimeoutError: refresh exceeded 600 seconds"),
    ]
    client = FakeTelegram()
    assert shadow.deliver_telegram(records, tmp_path, now, client) == [
        "Telegram: CONNECTED accepted."
    ]
    assert len(client.messages) == 1
    message = client.messages[0]
    assert message.startswith("📡 Signal Desk connected\n6-month trend · MNQ / MGC / MBT")
    assert "━━━━ OPEN TRADES ━━━━" in message
    assert "🟢 MNQ · LONG" in message and "500.0 pts below" in message
    assert "Entry: 25,000.0" in message
    assert "━━━━ NEW SIGNAL ━━━━" in message and "🔴 MGC · SHORT" in message
    assert "⚠️ MBT: no fresh data, no signal today." in message
    assert "T07:00" not in message
    # Embedded NEW and STALE events were accepted by the CONNECTED delivery.
    assert shadow.deliver_telegram(records, tmp_path, now, client) == []
    assert len(client.messages) == 1


def test_connected_old_cap_exit_is_information_not_action():
    record = _telegram_record(
        "USATECHIDXUSD", "MNQ", state="EXITED", side=1,
        entry_ts="2026-10-01T07:00:00+00:00", exit_ts="2026-11-12T23:00:00+00:00",
        exit_reason="cap", net_R=.2,
    )
    message = shadow.connected_message([record], pd.Timestamp("2026-11-13 05:00Z"))
    assert "ℹ️ MNQ: previous trade closed · 6-week limit · +0.20R" in message
    assert "ACTION" not in message


def test_status_sends_snapshot_without_dedup_history(monkeypatch, tmp_path: Path):
    shadow_root = tmp_path / "shadow"
    shadow_root.mkdir()
    history = shadow_root / "telegram_sent.csv"
    history.write_text("sent_at,event_id,market,event_type,reference\n")
    before = history.read_bytes()
    record = _telegram_record("BTCUSDT", "MBT", state="STALE", stale="true")
    monkeypatch.setattr(shadow, "MARKETS", ("BTCUSDT",))
    monkeypatch.setattr(shadow.s1, "load_minutes", lambda *args, **kwargs: object())
    monkeypatch.setattr(shadow, "analyze_market", lambda *args, **kwargs: (record, "MBT block"))
    client = FakeTelegram()
    output = shadow.run(
        tmp_path / "data", shadow_root, now=pd.Timestamp("2026-11-17 05:00Z"),
        refresh=False, status=True, telegram_client=client,
    )
    assert "Telegram status accepted." in output
    assert client.messages[0].startswith("📡 Signal Desk status")
    assert "⚠️ MBT: no fresh data, no signal today." in client.messages[0]
    assert history.read_bytes() == before


def test_later_events_are_sent_exactly_once(tmp_path: Path):
    now = pd.Timestamp("2026-11-17 05:00Z")
    _seed_telegram_history(tmp_path, now)
    records = [
        _telegram_record(
            "XAUUSD", "MGC", side=1, plan_entry_ts="2026-11-17T07:00:00+00:00",
            reference_price=4100., sl_distance=100., tp_distance=300.,
            plan_sl=4000., plan_tp=4400.,
        ),
        _telegram_record(
            "BTCUSDT", "MBT", state="EXITED", side=-1,
            entry_ts="2026-11-01T07:00:00+00:00", exit_ts="2026-11-16T12:00:00+00:00",
            exit_reason="tp", net_R=2.9,
        ),
        _telegram_record("USATECHIDXUSD", "MNQ", state="STALE", stale="true"),
    ]
    client = FakeTelegram()
    statuses = shadow.deliver_telegram(records, tmp_path, now, client)
    assert len(statuses) == len(client.messages) == 3
    assert client.messages[0].startswith("NEW SIGNAL\n🟢 MGC · LONG")
    assert "Enter: Tue 17 Nov, 09:00" in client.messages[0]
    assert "Confidence: low" in client.messages[0]
    assert "T07:00" not in client.messages[0]
    assert "✅ MBT 🔴 SHORT closed: target hit, +2.90R" in client.messages[1]
    assert "⚠️ MNQ: no fresh data, no signal today." in client.messages[2]
    assert shadow.deliver_telegram(records, tmp_path, now, client) == []
    assert len(client.messages) == 3


def test_failed_send_is_redacted_and_retried_next_run(tmp_path: Path):
    now = pd.Timestamp("2026-11-17 05:00Z")
    _seed_telegram_history(tmp_path, now)
    records = [_telegram_record(
        "XAUUSD", "MGC", side=1, plan_entry_ts="2026-11-17T07:00:00+00:00",
        reference_price=4100., sl_distance=100., tp_distance=300.,
        plan_sl=4000., plan_tp=4400.,
    )]
    failed = FakeTelegram(failures=1)
    statuses = shadow.deliver_telegram(records, tmp_path, now, failed)
    assert len(statuses) == 1 and "will retry" in statuses[0]
    assert "token-secret" not in statuses[0] and "chat-secret" not in statuses[0]
    accepted = FakeTelegram()
    assert shadow.deliver_telegram(records, tmp_path, now, accepted) == [
        "Telegram: NEW accepted for XAUUSD."
    ]
    assert len(accepted.messages) == 1


def test_cap_exit_is_a_manual_action(tmp_path: Path):
    now = pd.Timestamp("2026-11-17 05:00Z")
    _seed_telegram_history(tmp_path, now)
    record = _telegram_record(
        "USATECHIDXUSD", "MNQ", state="EXITED", side=1,
        entry_ts="2026-10-01T07:00:00+00:00", exit_ts="2026-11-16T23:00:00+00:00",
        exit_reason="cap", net_R=.2,
    )
    client = FakeTelegram()
    shadow.deliver_telegram([record], tmp_path, now, client)
    assert client.messages == ["⏰ ACTION: close MNQ 🟢 LONG now\n"
                               "6-week limit reached\nResult: +0.20R"]


def test_weekly_heartbeat_only_on_monday(tmp_path: Path):
    monday = pd.Timestamp("2026-11-16 05:00Z")
    _seed_telegram_history(tmp_path, monday)
    record = _telegram_record(
        "BTCUSDT", "MBT", state="OPEN", side=1,
        entry_ts="2026-11-10T07:00:00+00:00", entry_price=80000., sl=76000.,
        tp=92000., unrealised_R=.25, cap_session_end="2026-12-21T22:00:00+00:00",
    )
    client = FakeTelegram()
    shadow.deliver_telegram([record], tmp_path, monday, client)
    assert len(client.messages) == 1
    assert client.messages[0].startswith("Weekly check: bot running\n\n🟢 MBT · LONG")
    assert "Entry: 80,000" in client.messages[0]
    tuesday = pd.Timestamp("2026-11-17 05:00Z")
    assert shadow.deliver_telegram([record], tmp_path, tuesday, client) == []
    assert len(client.messages) == 1


def test_missed_run_sends_closed_exit_and_late_open_entry(tmp_path: Path):
    connected = pd.Timestamp("2026-11-13 05:00Z")
    now = pd.Timestamp("2026-11-17 05:00Z")
    _seed_telegram_history(tmp_path, connected)
    old_trade = {
        "entry_ts": "2026-10-01T07:00:00+00:00",
        "exit_ts": "2026-11-14T12:00:00+00:00",
        "exit": "sl", "net_R": -1.03, "side": 1,
    }
    record = _telegram_record(
        "USATECHIDXUSD", "MNQ", state="OPEN", side=-1,
        entry_ts="2026-11-16T07:00:00+00:00", entry_price=25000., sl=25500.,
        tp=23500., unrealised_R=.2, cap_session_end="2026-12-28T22:00:00+00:00",
        _current_price=24900., _open_trade={"entry_ts": "2026-11-16T07:00:00+00:00"},
        _replay_rows=[old_trade],
    )
    client = FakeTelegram()
    statuses = shadow.deliver_telegram([record], tmp_path, now, client)
    assert statuses == [
        "Telegram: EXIT_SL accepted for USATECHIDXUSD.",
        "Telegram: LATE_ENTRY accepted for USATECHIDXUSD.",
    ]
    assert "❌ MNQ 🟢 LONG closed: stop hit, -1.03R" in client.messages[0]
    assert client.messages[1].startswith("⚠️ LATE ENTRY (bot was offline)\n🔴 MNQ · SHORT")
    assert "You can enter now or skip." in client.messages[1]
    assert "Price now: 24,900.0" in client.messages[1]
    assert "Confidence: low" in client.messages[1]
    assert "Since: Mon 16 Nov, 09:00" in client.messages[1]
    assert "T07:00" not in client.messages[1]
    assert shadow.deliver_telegram([record], tmp_path, now, client) == []


def test_cap_warning_is_sent_once_before_next_run(tmp_path: Path):
    connected = pd.Timestamp("2026-11-16 05:00Z")
    now = pd.Timestamp("2026-11-17 05:00Z")
    _seed_telegram_history(tmp_path, connected)
    entry = "2026-10-01T07:00:00+00:00"
    marker = {"event_id": shadow._event_id("XAUUSD", "ENTRY", entry),
              "market": "XAUUSD", "event_type": "ENTRY_CONNECTED", "reference": entry}
    shadow._append_sent(tmp_path / "telegram_sent.csv", [marker], connected)
    record = _telegram_record(
        "XAUUSD", "MGC", state="OPEN", side=1, entry_ts=entry,
        entry_price=4100., sl=4000., tp=4400., unrealised_R=.3,
        cap_session_end="2026-11-17T22:00:00+00:00",
        _current_price=4130., _open_trade={"entry_ts": entry}, _replay_rows=[],
    )
    client = FakeTelegram()
    statuses = shadow.deliver_telegram([record], tmp_path, now, client)
    assert statuses == ["Telegram: CAP_WARNING accepted for XAUUSD."]
    assert len(client.messages) == 1
    assert client.messages[0] == ("⏰ ACTION: close MGC 🟢 LONG by Wed 18 Nov, 00:00 Finland\n"
                                  "6-week limit")
    assert shadow.deliver_telegram([record], tmp_path, now, client) == []


def test_connection_test_uses_client_without_exposing_credentials():
    client = FakeTelegram()
    assert shadow.test_telegram(client) == "Telegram connection test accepted."
    assert client.messages == ["📡 Signal Desk connection test\nTelegram delivery works."]


def test_connection_test_failure_is_redacted():
    with pytest.raises(RuntimeError) as caught:
        shadow.test_telegram(FakeTelegram(failures=1))
    assert "token-secret" not in str(caught.value)
    assert "chat-secret" not in str(caught.value)
    assert "[REDACTED]" in str(caught.value)


def test_rendered_telegram_times_are_never_iso():
    record = _telegram_record(
        "USATECHIDXUSD", "MNQ", state="OPEN", side=1,
        entry_ts="2026-11-13T07:00:00+00:00", entry_price=25000., sl=24500.,
        tp=26500., unrealised_R=.4, cap_session_end="2026-12-21T22:00:00+00:00",
        plan_entry_ts="2026-11-17T07:00:00+00:00", reference_price=25100.,
        sl_distance=500., tp_distance=1500., plan_sl=24600., plan_tp=26600.,
        _current_price=25100.,
    )
    messages = [shadow._open_text(record), shadow._new_text(record),
                shadow._late_entry_text(record), shadow._cap_warning_text(record),
                shadow.connected_message([record], pd.Timestamp("2026-11-17 05:00Z"))]
    assert all("2026-" not in message and "T07:" not in message for message in messages)


def test_send_failure_does_not_break_shadow_audit(monkeypatch, tmp_path: Path):
    now = pd.Timestamp("2026-11-17 05:00Z")
    record = _telegram_record(
        "BTCUSDT", "MBT", side=1, plan_entry_ts="2026-11-17T07:00:00+00:00",
        reference_price=80000., sl_distance=4000., tp_distance=12000.,
        plan_sl=76000., plan_tp=92000.,
    )
    monkeypatch.setattr(shadow, "MARKETS", ("BTCUSDT",))
    monkeypatch.setattr(shadow.s1, "load_minutes", lambda *args, **kwargs: object())
    monkeypatch.setattr(shadow, "analyze_market", lambda *args, **kwargs: (record, "MBT block"))
    output = shadow.run(
        tmp_path / "data", tmp_path / "shadow", now=now, refresh=False,
        send=True, telegram_client=FakeTelegram(failures=1),
    )
    audit = pd.read_csv(tmp_path / "shadow/swing_v1.csv")
    assert len(audit) == 1 and audit.market.iloc[0] == "BTCUSDT"
    assert not (tmp_path / "shadow/telegram_sent.csv").exists()
    assert "will retry" in output
    assert "token-secret" not in output and "chat-secret" not in output
