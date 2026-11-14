from __future__ import annotations

from datetime import date, timedelta
import json
from pathlib import Path
import types

import numpy as np
import pandas as pd
import pytest

from msd.live import engine
from msd.live.engine import SignalEngine
from msd.live.store import SignalStore
from msd.live.strategies import tiktok_a, tiktok_b


def _bars(times, mid=None):
    times = pd.to_datetime(times, utc=True)
    price = np.full(len(times), 100., dtype=float) if mid is None else np.asarray(mid, dtype=float)
    frame = pd.DataFrame({"ts": times, "volume": 1.})
    for field in "ohlc":
        for side, offset in (("bid", -.05), ("ask", .05)):
            frame[f"{side}_{field}"] = price + offset
    return frame


def _window_data():
    times, prices = [], []
    for day_index, day in enumerate((date(2022, 1, 10), date(2022, 1, 11), date(2022, 1, 12))):
        start, end = tiktok_a.common.session_bounds("USATECHIDXUSD", day, "full_day")
        window = pd.date_range(start, end, freq="min", inclusive="left")
        local = window.tz_convert("America/New_York")
        pause = ((local.date == day) & ((local.hour * 60 + local.minute) >= 16 * 60 + 15))
        window = window[~pause]
        times.extend(window)
        prices.extend(100. + day_index * 10 + np.sin(np.arange(len(window)) / 25) * 4)
    return _bars(times, prices)


def _b_rth_data(days=48):
    times, prices = [], []
    day = date(2021, 10, 4)
    day_index = 0
    while day_index < days:
        if day.weekday() < 5:
            start, end = tiktok_a.common.session_bounds("USATECHIDXUSD", day, "rth")
            window = pd.date_range(start, end, freq="min", inclusive="left")
            times.extend(window)
            prices.extend(10000. + day_index * 20 + np.arange(len(window)) * .02)
            day_index += 1
        day += timedelta(days=1)
    return _bars(times, prices)


def _project(orders):
    return [tuple((pd.Timestamp(order["decision_ts"]).isoformat(), order["side"],
                   order.get("trigger_price"), order.get("risk_distance"), order.get("stop")))
            for order in orders]


def test_tiktok_a_orders_are_causal_at_many_session_cuts():
    bars = _window_data()
    full = tiktok_a.orders(bars)
    assert full
    plan = full[-1]
    decision = pd.Timestamp(plan["decision_ts"])
    rows = np.flatnonzero(pd.to_datetime(bars.ts, utc=True).eq(decision).to_numpy())
    assert len(rows) == 1
    i = int(rows[0])
    for offset in (1, 2, 5, 17, 60, 121, 301):
        cut = bars.iloc[:min(i + offset, len(bars))]
        prefix = [item for item in tiktok_a.orders(cut)
                  if pd.Timestamp(item["decision_ts"]) == decision]
        assert len(prefix) == 1
        for field in ("side", "trigger_price", "risk_distance", "stop", "expiry_ts"):
            assert prefix[0][field] == plan[field]


def test_tiktok_b_orders_are_causal_after_closed_first_candle():
    bars = _b_rth_data()
    longer = tiktok_b.orders(bars)
    assert longer
    expected = longer[-1]
    decision = pd.Timestamp(expected["decision_ts"])
    decision_i = int(np.flatnonzero(pd.to_datetime(bars.ts, utc=True).eq(decision).to_numpy())[0])
    # Cut the developing day at many points after its first 5-minute candle.
    for offset in (1, 2, 4, 9, 17, 33, 65, 121, 241, 350):
        cut = bars.iloc[:min(decision_i + offset + 1, len(bars))]
        prefix = [item for item in tiktok_b.orders(cut)
                  if pd.Timestamp(item["decision_ts"]) == decision]
        assert len(prefix) == 1
        for field in ("side", "risk_distance", "stop"):
            assert prefix[0][field] == expected[field]


def _tiktok_engine(module, store=None, messages=None):
    store = store or SignalStore(":memory:")
    messages = messages if messages is not None else []
    engine_obj = SignalEngine(
        store, messages.append, mode="live",
        instruments=[{"symbol": "USATECHIDXUSD", "hours": "cme_equity"}],
        strategies=[{"module": module.__name__, "enabled": True}],
    )
    return engine_obj, store, messages


def test_stop_entry_fill_uses_actual_fill_mid_for_risk_stop_and_dedupe():
    eng, store, messages = _tiktok_engine(tiktok_a)
    decision = pd.Timestamp("2022-01-10T23:00Z")
    forming = {"ts": decision, "ask_o": 100.1, "bid_o": 100.0}
    order = {"decision_ts": decision, "side": 1, "entry_type": "stop",
             "trigger_price": 101., "risk_distance": 2., "stop": 99.,
             "risk_from_mid": True,
             "expiry_ts": decision + pd.Timedelta(hours=23), "tp": None,
             "exit_ts": decision + pd.Timedelta(hours=22), "exit_at_close": True,
             "reminder_minutes": 10}
    eng._create_signal({"module": tiktok_a.__name__}, tiktok_a, order, forming, "USATECHIDXUSD")
    key = f"USATECHIDXUSD:{tiktok_a.NAME}:{decision.isoformat()}"
    assert store.get(key)["status"] == "pending"
    before = len(messages)
    eng._create_signal({"module": tiktok_a.__name__}, tiktok_a, order, forming, "USATECHIDXUSD")
    assert len(messages) == before

    bar = {"ts": decision + pd.Timedelta(minutes=1),
           "bid_o": 100.4, "bid_h": 101.4, "bid_l": 100.0, "bid_c": 101.0,
           "ask_o": 100.5, "ask_h": 101.5, "ask_l": 100.1, "ask_c": 101.1}
    eng._check_pending("USATECHIDXUSD", "MINUTE", bar)
    saved = store.get(key)
    assert saved["status"] == "open"
    assert saved["entry_price"] == 101.
    assert saved["stop"] == pytest.approx(98.95)  # fill mid 100.95 less 2 points
    assert saved["planned_risk"] == 2.
    assert any("FILLED" in message for message in messages)
    store.close()


def test_pending_risk_uses_executable_fill_price_unless_midpoint_requested():
    decision = pd.Timestamp("2022-01-10T23:00Z")
    bar = {"ts": decision + pd.Timedelta(minutes=1),
           "bid_o": 100.4, "bid_h": 101.4, "bid_l": 100.0, "bid_c": 101.0,
           "ask_o": 100.5, "ask_h": 101.5, "ask_l": 100.1, "ask_c": 101.1}
    eng, store, _ = _tiktok_engine(tiktok_a)
    order = {"decision_ts": decision, "side": 1, "entry_type": "stop",
             "trigger_price": 101., "risk_distance": 2., "stop": 99.,
             "expiry_ts": decision + pd.Timedelta(hours=23), "tp": None}
    forming = {"ts": decision, "ask_o": 100.1, "bid_o": 100.}
    eng._create_signal({"module": tiktok_a.__name__}, tiktok_a, order, forming, "USATECHIDXUSD")
    key = f"USATECHIDXUSD:{tiktok_a.NAME}:{decision.isoformat()}"
    eng._check_pending("USATECHIDXUSD", "MINUTE", bar)
    assert store.get(key)["stop"] == pytest.approx(99.)
    store.close()


def test_signal_dedup_survives_engine_restart(tmp_path):
    path = tmp_path / "state.db"
    decision = pd.Timestamp("2022-01-10T23:00Z")
    order = {"decision_ts": decision, "side": 1, "entry_type": "stop",
             "trigger_price": 101., "risk_distance": 2., "stop": 99.,
             "expiry_ts": decision + pd.Timedelta(hours=23), "tp": None}
    forming = {"ts": decision, "ask_o": 100.1, "bid_o": 100.}
    first_store = SignalStore(path)
    first, _, first_messages = _tiktok_engine(tiktok_a, first_store)
    first._create_signal({"module": tiktok_a.__name__}, tiktok_a, order,
                         forming, "USATECHIDXUSD")
    first_store.close()

    second_store = SignalStore(path)
    second, _, second_messages = _tiktok_engine(tiktok_a, second_store)
    second._create_signal({"module": tiktok_a.__name__}, tiktok_a, order,
                          forming, "USATECHIDXUSD")
    assert second_messages == []
    second_store.close()


def test_stop_entry_same_bar_stop_has_priority_and_expiry_is_automatic():
    eng, store, messages = _tiktok_engine(tiktok_a)
    decision = pd.Timestamp("2022-01-10T23:00Z")
    forming = {"ts": decision, "ask_o": 100., "bid_o": 99.9}
    order = {"decision_ts": decision, "side": 1, "entry_type": "stop",
             "trigger_price": 101., "risk_distance": 2., "stop": 99.,
             "risk_from_mid": True,
             "expiry_ts": decision + pd.Timedelta(hours=23), "tp": None}
    eng._create_signal({"module": tiktok_a.__name__}, tiktok_a, order, forming, "USATECHIDXUSD")
    key = f"USATECHIDXUSD:{tiktok_a.NAME}:{decision.isoformat()}"
    bar = {"ts": decision + pd.Timedelta(minutes=1),
           "bid_o": 100., "bid_h": 102., "bid_l": 98., "bid_c": 100.,
           "ask_o": 100.1, "ask_h": 102.1, "ask_l": 98.1, "ask_c": 100.1}
    eng._check_pending("USATECHIDXUSD", "MINUTE", bar)
    assert store.get(key)["status"] == "stop"
    assert store.get(key)["realized_r"] == pytest.approx(-1.025)

    second = decision + pd.Timedelta(days=1)
    later_order = {**order, "decision_ts": second,
                   "expiry_ts": second + pd.Timedelta(minutes=3)}
    later_forming = {"ts": second, "ask_o": 100., "bid_o": 99.9}
    eng._create_signal({"module": tiktok_a.__name__}, tiktok_a, later_order,
                       later_forming, "USATECHIDXUSD")
    later_key = f"USATECHIDXUSD:{tiktok_a.NAME}:{second.isoformat()}"
    eng.reminder((second + pd.Timedelta(minutes=3)).to_pydatetime())
    assert store.get(later_key)["status"] == "expired"
    assert any("EXPIRED" in message for message in messages)
    store.close()


def test_dynamic_exit_is_saved_and_announced_once():
    module = types.ModuleType("tiktok_dynamic_test")
    module.NAME = "TikTok B first-candle trend"
    module.SYMBOLS = ("USATECHIDXUSD",)
    module.RESOLUTION = "MINUTE"
    exit_at = pd.Timestamp("2022-01-11T15:00Z")
    module.orders = lambda _bars: [{"decision_ts": exit_at - pd.Timedelta(days=1),
                                    "side": 1, "stop": 98., "tp": None,
                                    "exit_ts": exit_at}]
    import sys
    sys.modules[module.__name__] = module
    eng, store, messages = _tiktok_engine(module)
    key = f"USATECHIDXUSD:{module.NAME}:{(exit_at-pd.Timedelta(days=1)).isoformat()}"
    store.insert({"signal_key": key, "symbol": "USATECHIDXUSD", "setup": module.NAME,
                  "side": 1, "decision_ts": (exit_at-pd.Timedelta(days=1)).isoformat(),
                  "entry_ts": (exit_at-pd.Timedelta(days=1)).isoformat(), "entry_price": 100.,
                  "initial_stop": 98., "stop": 98., "planned_risk": 2., "status": "open",
                  "created_at": "test"})
    frame = _bars([exit_at - pd.Timedelta(minutes=1)])
    eng._apply_updates({"module": module.__name__}, module, frame,
                       exit_at - pd.Timedelta(minutes=1), "USATECHIDXUSD")
    assert store.get(key)["planned_exit_ts"] == exit_at.isoformat()
    n = len(messages)
    eng._apply_updates({"module": module.__name__}, module, frame,
                       exit_at - pd.Timedelta(minutes=1), "USATECHIDXUSD")
    assert len(messages) == n
    assert any("EXIT NOW" in message for message in messages)
    store.close()


def test_missing_capital_credentials_returns_cleanly_without_telegram(monkeypatch, tmp_path, capsys):
    config_path = tmp_path / "live.toml"
    config_path.write_text("mode = 'live'\n")
    class NoCredentials:
        credentials_present = False
    monkeypatch.setattr(engine, "CONFIG_PATH", config_path)
    monkeypatch.setattr(engine, "CapitalClient", NoCredentials)
    monkeypatch.setattr(engine, "TelegramClient", lambda: pytest.fail("Telegram should not initialize"))
    assert engine.run_live() is None
    assert capsys.readouterr().out == "Capital credentials present: no; live engine not started.\n"


def test_resolved_epic_is_cached_without_rewriting_live_toml(tmp_path):
    config_path = tmp_path / "live.toml"
    source = 'mode = "live"\n[[instruments]]\nsymbol = "USATECHIDXUSD"\nsearch_term = "Nasdaq 100"\nepic = ""\nhours = "cme_equity"\n'
    config_path.write_text(source)
    config = {"instruments": [{"symbol": "USATECHIDXUSD", "search_term": "Nasdaq 100", "epic": "", "hours": "cme_equity"}]}
    epics_path = tmp_path / "data/live/epics.json"
    client = types.SimpleNamespace(search_market=lambda _term: {"epic": "IX.D.NASDAQ.CASH"})
    result = engine._resolve_instruments(client, config, epics_path)
    assert result["instruments"][0]["epic"] == "IX.D.NASDAQ.CASH"
    assert json.loads(epics_path.read_text()) == {"USATECHIDXUSD": "IX.D.NASDAQ.CASH"}
    assert config_path.read_text() == source
    config2 = {"instruments": [{"symbol": "USATECHIDXUSD", "search_term": "Nasdaq 100", "epic": "", "hours": "cme_equity"}]}
    cached = engine._resolve_instruments(types.SimpleNamespace(
        search_market=lambda _term: pytest.fail("cached epic should be reused")), config2, epics_path)
    assert cached["instruments"][0]["epic"] == "IX.D.NASDAQ.CASH"


def test_capital_check_prints_only_epic_bars_and_latest_without_telegram(tmp_path, capsys):
    config_path = tmp_path / "live.toml"
    source = 'mode = "live"\n[[instruments]]\nsymbol = "USATECHIDXUSD"\nsearch_term = "Nasdaq 100"\nepic = ""\nhours = "cme_equity"\n'
    config_path.write_text(source)
    bars = _bars([pd.Timestamp("2022-01-03T15:00Z")])
    client = types.SimpleNamespace(
        credentials_present=True,
        login=lambda: None,
        search_market=lambda _term: {"epic": "IX.D.NASDAQ.CASH"},
        prices=lambda *_args, **_kwargs: bars,
    )
    engine.run_check(client, config_path=config_path, epics_path=tmp_path / "epics.json")
    output = capsys.readouterr().out
    assert output.startswith("credentials present: yes\n")
    assert "epic: IX.D.NASDAQ.CASH; bars: 1; latest: 2022-01-03T15:00:00+00:00" in output
    assert "Telegram" not in output and "token" not in output.lower()
    assert config_path.read_text() == source


def test_b_market_signal_message_derives_stop_from_risk_when_stop_is_none():
    order = {"side": -1, "entry_type": "market", "risk_distance": 40.0, "stop": None,
             "exit_rule": "Bot will message when to exit", "confidence": "low"}
    text = engine.format_signal("USATECHIDXUSD", tiktok_b, order, 15000.0)
    assert "SL: 15,040.0" in text and "SHORT" in text


def test_b_update_gate_runs_on_hour_closes_and_first_bar_after_a_gap():
    gate = lambda ts: tiktok_b.should_update(pd.DataFrame(), pd.Timestamp(ts), phase="update")
    assert gate("2022-02-02T21:59Z") and gate("2022-02-02T23:00Z")
    assert not gate("2022-02-02T23:01Z") and not gate("2022-02-02T21:14Z")


def test_us_calendar_skips_holidays_and_half_days_only():
    from msd.live.strategies.us_calendar import skip_day
    for day in ("2022-01-17", "2022-06-20", "2022-07-04", "2022-11-25", "2025-12-24", "2026-07-03"):
        assert skip_day(date.fromisoformat(day)), day
    for day in ("2022-01-18", "2021-12-31", "2026-11-16"):
        assert not skip_day(date.fromisoformat(day)), day
