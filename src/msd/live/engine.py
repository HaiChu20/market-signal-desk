"""Strategy-agnostic full-day paper signal engine."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import importlib
import os
import re
from pathlib import Path
import sqlite3
import sys
import time
import tomllib
import types
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from msd.backtest import evaluate_bar, ratchet_stop, simulate
from msd.data import load
from msd.data.dukascopy import COLUMNS
from msd.live.capital import CapitalClient
from msd.live.store import SignalStore
from msd.live.telegram import TelegramClient

NY = ZoneInfo("America/New_York")
CONFIG_PATH = Path("live.toml")
STATE_PATH = Path("data/live/state.db")
HEARTBEAT_PATH = Path("data/live/heartbeat")
RESOLUTION = {"MINUTE": pd.Timedelta(minutes=1), "HOUR": pd.Timedelta(hours=1), "DAY": pd.Timedelta(days=1)}


def market_open(now: datetime | pd.Timestamp, hours: str) -> bool:
    if hours == "24x7":
        return True
    if hours != "cme_equity":
        raise ValueError(f"unknown market hours: {hours}")
    local = pd.Timestamp(now).to_pydatetime().astimezone(NY)
    weekday, minute = local.weekday(), local.hour * 60 + local.minute
    if weekday == 5 or (weekday == 6 and minute < 18 * 60):
        return False
    if weekday == 4 and minute >= 17 * 60:
        return False
    return not (17 * 60 <= minute < 18 * 60)


def _utc(value) -> pd.Timestamp:
    stamp = pd.Timestamp(value)
    return stamp.tz_localize("UTC") if stamp.tzinfo is None else stamp.tz_convert("UTC")


def _module(entry: dict):
    module = importlib.import_module(entry["module"])
    for name in ("NAME", "SYMBOLS", "RESOLUTION", "orders"):
        if not hasattr(module, name):
            raise ValueError(f"strategy {entry['module']} lacks {name}")
    if module.RESOLUTION not in RESOLUTION:
        raise ValueError(f"unsupported strategy resolution {module.RESOLUTION}")
    return module


def _strategy_orders(module, bars: pd.DataFrame) -> list[dict]:
    """Use the strategy's complete causal history as the single source of truth."""
    return module.orders(bars)


def format_signal(symbol: str, module, order: dict, entry_price: float) -> str:
    side = int(order["side"])
    pair = {"USATECHIDXUSD": "US100", "USA500IDXUSD": "US500", "BTCUSDT": "BTCUSDT"}.get(symbol, symbol)
    sl = float(order["stop"])
    tp = order.get("tp")
    distance = abs(entry_price - sl)
    optional = lambda value, fmt: "n/a" if value is None else fmt.format(value)
    confidence = optional(order.get("confidence"), "{:.0%}")
    size = optional(order.get("size"), "{:.2f}")
    note = str(order.get("note") or "").strip()
    suffix = f" | {module.NAME}" + (f" {note}" if note else "")
    tp_text = "n/a" if tp is None else f"{float(tp):.2f} (+{abs(float(tp)-entry_price):.2f})"
    return (f"{'🟢' if side > 0 else '🔴'} {'LONG' if side > 0 else 'SHORT'} {pair} | Entry ≈ {entry_price:.2f} "
            f"| SL {sl:.2f} (−{distance:.2f}) | TP {tp_text} "
            f"| Confidence {confidence} | Size {size}×{suffix}")


class StaleDataAlarm:
    def __init__(self, timeout=timedelta(minutes=5)):
        self.timeout, self.stale = timeout, False

    def update(self, now, last_bar, active):
        stale = bool(active and (last_bar is None or now - last_bar > self.timeout))
        if stale and not self.stale:
            self.stale = True
            return "stale"
        if not stale and self.stale:
            self.stale = False
            return "recovered"
        return None


class OutageAlerts:
    def __init__(self, send, realert=timedelta(hours=1)):
        self.send, self.realert = send, realert
        self.started = self.last_alert = None

    def failure(self, exc, now):
        message = re.sub(r"https?://\S+", "<url>", str(exc))
        for variable in ("CAPITAL_API_KEY", "CAPITAL_IDENTIFIER", "CAPITAL_PASSWORD", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
            secret = os.getenv(variable)
            if secret:
                message = message.replace(secret, "<redacted>")
        print(f"{type(exc).__name__}: {message}", flush=True)
        if self.started is None:
            self.started = now
        if self.last_alert is None or now - self.last_alert >= self.realert:
            self.send("Feed outage; reconnecting")
            self.last_alert = now

    def recovered(self):
        if self.started is not None:
            self.send("Feed recovered")
            self.started = self.last_alert = None


class SignalEngine:
    def __init__(self, store, send, *, instruments=(), strategies=(), mode="paper"):
        if mode not in ("paper", "live"):
            raise ValueError("mode must be paper or live")
        self.store, self._send = store, send
        self.instruments = {item["symbol"]: item for item in instruments}
        self.strategies = [(entry, _module(entry)) for entry in strategies if entry.get("enabled", False)]
        configured = set(self.instruments)
        for entry, module in self.strategies:
            missing = sorted(set(module.SYMBOLS) - configured)
            if missing:
                raise ValueError(f"enabled strategy {entry['module']} requires unconfigured instrument(s): {', '.join(missing)}")
        self.mode = mode
        self.bars: dict[tuple[str, str], pd.DataFrame] = {}
        self.last_processed: dict[tuple[str, str], pd.Timestamp] = {}
        self.alarm: dict[str, StaleDataAlarm] = {}

    def send(self, message):
        self._send(("📝 PAPER " if self.mode == "paper" else "") + message)

    def _strategy_bars(self, symbol, module):
        return self.bars.get((symbol, module.RESOLUTION), pd.DataFrame(columns=COLUMNS))

    def process_completed(self, symbol: str, resolution: str, bar: dict):
        key = (symbol, resolution)
        row = dict(bar)
        row["ts"] = _utc(row["ts"])
        last = self.last_processed.get(key)
        if last is not None and row["ts"] <= last:
            return
        frame = self.bars.get(key)
        one = pd.DataFrame([row], columns=COLUMNS)
        frame = one if frame is None else pd.concat([frame, one], ignore_index=True)
        frame = frame.drop_duplicates("ts", keep="last").sort_values("ts").reset_index(drop=True)
        self.bars[key] = frame
        self._check_exits(symbol, resolution, row)
        for entry, module in self.strategies:
            if symbol not in module.SYMBOLS or module.RESOLUTION != resolution:
                continue
            self._apply_updates(entry, module, frame, row["ts"], symbol)
        self.last_processed[key] = row["ts"]
        self.store.set_state(f"last_processed:{symbol}:{resolution}", row["ts"].isoformat())

    def process_forming(self, symbol: str, resolution: str, forming: dict):
        forming_ts = _utc(forming["ts"])
        for entry, module in self.strategies:
            if symbol not in module.SYMBOLS or module.RESOLUTION != resolution:
                continue
            bars = self._strategy_bars(symbol, module)
            if bars.empty:
                continue
            completed_ts = _utc(bars.ts.iloc[-1])
            if forming_ts <= completed_ts:
                continue
            for order in _strategy_orders(module, bars):
                if _utc(order["decision_ts"]) != completed_ts:
                    continue
                self._create_signal(entry, module, order, forming, symbol)

    def _validate(self, entry, module, order, entry_price):
        valid = False
        try:
            side = int(order.get("side", 0))
            stop_value = order.get("stop")
            tp_value = order.get("tp")
            valid = (side in (-1, 1) and order.get("entry_type", "market") == "market"
                     and stop_value is not None and np.isfinite(float(entry_price))
                     and np.isfinite(float(stop_value)))
            if tp_value is not None:
                valid = valid and np.isfinite(float(tp_value))
            if valid:
                valid = side * (float(entry_price) - float(stop_value)) > 0
                if tp_value is not None:
                    valid = valid and side * (float(tp_value) - float(entry_price)) > 0
        except (TypeError, ValueError, OverflowError):
            valid = False
        if not valid:
            print(f"Rejected invalid order from {entry['module']} at {order.get('decision_ts')}", flush=True)
            day = _utc(order["decision_ts"]).date().isoformat()
            flag = f"invalid:{module.NAME}:{day}"
            if not self.store.get_state(flag):
                self.send(f"Invalid order rejected: {module.NAME}")
                self.store.set_state(flag, "1")
        return valid

    def _create_signal(self, entry, module, order, forming, symbol):
        symbol, side = str(symbol), int(order["side"])
        entry_price = float(forming["ask_o"] if side > 0 else forming["bid_o"])
        if not self._validate(entry, module, order, entry_price):
            return
        decision = _utc(order["decision_ts"])
        key = f"{symbol}:{module.NAME}:{decision.isoformat()}"
        risk = abs(entry_price - float(order["stop"]))
        opposite = self.store.connection.execute(
            "SELECT signal_key,side FROM signals WHERE symbol=? AND setup=? AND status='open'",
            (symbol, module.NAME)).fetchall()
        for old_key, old_side in opposite:
            if int(old_side) == -side:
                self.store.update(old_key, status="flip", exit_ts=decision.isoformat(), exit_price=entry_price,
                                  realized_r=None)
                self.send(f"EXIT now {symbol} ({module.NAME} flip)")
        stop = float(order["stop"])
        values = {"signal_key": key, "symbol": symbol, "setup": module.NAME, "side": side,
                  "decision_ts": decision.isoformat(), "entry_ts": _utc(forming["ts"]).isoformat(),
                  "entry_price": entry_price, "initial_stop": stop, "stop": stop,
                  "take_profit": order.get("tp"), "planned_exit_ts": None if order.get("exit_ts") is None else _utc(order["exit_ts"]).isoformat(),
                  "planned_risk": risk, "notional": order.get("size"), "confidence": order.get("confidence"),
                  "status": "open", "created_at": datetime.now(timezone.utc).isoformat()}
        if self.store.insert(values):
            self.send(format_signal(symbol, module, order, entry_price))

    def _apply_updates(self, entry, module, bars, through, symbol):
        for order in _strategy_orders(module, bars):
            decision = _utc(order["decision_ts"])
            if decision > through:
                continue
            key = f"{symbol}:{module.NAME}:{decision.isoformat()}"
            saved = self.store.get(key)
            if not saved or saved["status"] != "open":
                continue
            path = order.get("stop_path") or {}
            if not isinstance(path, dict):
                continue
            updates = sorted((_utc(ts), float(level)) for ts, level in path.items() if _utc(ts) == through)
            if not updates:
                continue
            side = int(saved["side"])
            new_stop = ratchet_stop(side, float(saved["stop"]), updates[-1][1])
            if np.isclose(new_stop, float(saved["stop"]), atol=1e-12):
                continue
            self.store.update(key, stop=new_stop)
            self.send(f"Move SL to {new_stop:.2f} ({module.NAME})")

    def _check_exits(self, symbol, resolution, bar):
        ts = _utc(bar["ts"])
        self.store.connection.row_factory = sqlite3.Row
        rows = self.store.connection.execute("SELECT * FROM signals WHERE symbol=? AND status='open'", (symbol,)).fetchall()
        for raw in rows:
            row = dict(raw)
            if _utc(row["entry_ts"]) > ts:
                continue
            side, stop = int(row["side"]), float(row["stop"])
            deadline = row.get("planned_exit_ts")
            time_exit = deadline is not None and ts >= _utc(deadline)
            _active_stop, reason, price = evaluate_bar(
                side, stop, row.get("take_profit"), bar, time_exit=time_exit, time_at_open=time_exit)
            if reason is None:
                continue
            risk = max(float(row["planned_risk"] or 0), 1e-12)
            realized = side * (price - float(row["entry_price"])) / risk
            self.store.update(row["signal_key"], status=reason, exit_ts=ts.isoformat(), exit_price=price, realized_r=realized)
            self.send(f"{symbol} {reason.upper()} hit at {price:.2f}; realized {realized:.2f}R")

    def reminder(self, now: datetime):
        now_ts = pd.Timestamp(now).tz_convert("UTC")
        self.store.connection.row_factory = sqlite3.Row
        rows = self.store.connection.execute("SELECT * FROM signals WHERE status='open' AND planned_exit_ts IS NOT NULL").fetchall()
        for raw in rows:
            row = dict(raw)
            end = _utc(row["planned_exit_ts"])
            flag = f"reminded:{row['signal_key']}"
            if end - pd.Timedelta(minutes=5) <= now_ts < end and not self.store.get_state(flag):
                self.send(f"Exit by {end.isoformat()} ({row['symbol']} {row['setup']})")
                self.store.set_state(flag, "1")

    def daily_summary(self, now):
        now = now.astimezone(timezone.utc)
        day = now.date().isoformat()
        if now.strftime("%H:%M") < "21:15" or self.store.get_state("daily_summary") == day:
            return
        rows = self.store.for_date(day)
        resolved = [r for r in rows if r["realized_r"] is not None]
        self.send(f"Daily summary {day}: {len(rows)} signals, {len(resolved)} resolved, realized {sum(r['realized_r'] for r in resolved):.2f}R")
        self.store.set_state("daily_summary", day)

    def check_stale(self, now, last_bar, hours):
        alarm = self.alarm.setdefault(hours, StaleDataAlarm())
        state = alarm.update(now, last_bar, market_open(now, hours))
        if state:
            self.send("⚠️ Data stale >5 minutes" if state == "stale" else "✅ Data feed recovered")


def _history(client, epic, resolution, start, end):
    step = {"MINUTE": timedelta(hours=12), "HOUR": timedelta(days=30), "DAY": timedelta(days=500)}[resolution]
    frames, cursor = [], start
    while cursor < end:
        stop = min(cursor + step, end)
        frame = client.prices(epic, resolution, cursor, stop, 1000)
        if not frame.empty:
            frames.append(frame)
        cursor = stop
    return pd.concat(frames, ignore_index=True).sort_values("ts").drop_duplicates("ts", keep="last").reset_index(drop=True) if frames else pd.DataFrame(columns=COLUMNS)


def process_poll_cycle(engine: SignalEngine, client, strategies, instruments, now: datetime):
    """Process completed bars once, then inspect the currently forming bar."""
    now = now.astimezone(timezone.utc)
    for entry in (item for item in strategies if item.get("enabled", False)):
        module = _module(entry)
        for symbol in module.SYMBOLS:
            resolution = module.RESOLUTION
            instrument = next((item for item in instruments if item["symbol"] == symbol), None)
            if instrument is None:
                raise ValueError(f"enabled strategy {entry['module']} requires unconfigured instrument {symbol}")
            delta = RESOLUTION[resolution]
            forming_ts = pd.Timestamp(now).floor(delta)
            completed_through = forming_ts - delta
            key = (symbol, resolution)
            last = engine.last_processed.get(key)
            if last is None:
                saved = engine.store.get_state(f"last_processed:{symbol}:{resolution}")
                if saved:
                    last = _utc(saved)
                    engine.last_processed[key] = last
            since = last.to_pydatetime() if last is not None else (now - timedelta(days=10 if resolution == "DAY" else 2))
            fresh = _history(client, instrument["epic"], resolution, since, now)
            mask = fresh.ts <= completed_through
            if last is not None:
                mask &= fresh.ts > last
            for bar in fresh.loc[mask].to_dict("records"):
                engine.process_completed(symbol, resolution, bar)
            forming = fresh[fresh.ts == forming_ts]
            if not forming.empty:
                engine.process_forming(symbol, resolution, forming.iloc[-1].to_dict())
            latest = engine.last_processed.get(key)
            if latest is not None:
                engine.check_stale(now, latest.to_pydatetime(), instrument["hours"])
    engine.reminder(now)
    engine.daily_summary(now)

def _resolve_instruments(client, config, path=CONFIG_PATH):
    for item in config.get("instruments", []):
        if not item.get("epic"):
            market = client.search_market(item["search_term"])
            if not market.get("epic"):
                raise RuntimeError(f"market not found for {item['symbol']}")
            item["epic"] = market["epic"]
    lines = [f'mode = "{config.get("mode", "paper")}"', ""]
    for item in config.get("instruments", []):
        lines += ["[[instruments]]"]
        lines += [f'{key} = "{str(item.get(key, "")).replace(chr(34), "")}"' for key in ("symbol", "search_term", "epic", "hours")]
        lines.append("")
    for entry in config.get("strategies", []):
        lines += ["[[strategies]]", f'module = "{entry["module"]}"', f'enabled = {str(bool(entry.get("enabled", False))).lower()}', ""]
    path.write_text("\n".join(lines))
    return config


def _seed_history(engine, client, strategies, instruments, now):
    """Load indicator warmup without replaying historical signals as new alerts."""
    for entry in (item for item in strategies if item.get("enabled", False)):
        module = _module(entry)
        resolution = module.RESOLUTION
        delta = RESOLUTION[resolution]
        lookback = {"MINUTE": timedelta(days=42), "HOUR": timedelta(days=120), "DAY": timedelta(days=1000)}[resolution]
        forming = pd.Timestamp(now).floor(delta)
        complete_through = forming - delta
        for symbol in module.SYMBOLS:
            instrument = next((item for item in instruments if item["symbol"] == symbol), None)
            if instrument is None:
                raise ValueError(f"enabled strategy {entry['module']} requires unconfigured instrument {symbol}")
            history = _history(client, instrument["epic"], resolution, now - lookback, now)
            history = history[history.ts <= complete_through].reset_index(drop=True)
            key = (symbol, resolution)
            saved = engine.store.get_state(f"last_processed:{symbol}:{resolution}")
            if saved:
                last = _utc(saved)
                history = history[history.ts <= last].reset_index(drop=True)
            else:
                last = history.ts.iloc[-1] if not history.empty else None
                if last is not None:
                    engine.store.set_state(f"last_processed:{symbol}:{resolution}", last.isoformat())
            engine.bars[key] = history
            if last is not None:
                engine.last_processed[key] = last


def _now_utc():
    return datetime.now(timezone.utc)


def create_engine(config, store, send):
    instruments = config.get("instruments", [])
    strategies = config.get("strategies", [])
    engine = SignalEngine(store, send, instruments=instruments, strategies=strategies,
                          mode=config.get("mode", "paper"))
    engine.send("Market Signal Desk started — no strategies enabled" if not engine.strategies else "Market Signal Desk started")
    return engine


def run_live():
    config = tomllib.loads(CONFIG_PATH.read_text())
    instruments = config.get("instruments", [])
    strategies = config.get("strategies", [])
    client, telegram = CapitalClient(), TelegramClient()
    print(f"credentials present: {'yes' if client.credentials_present and telegram.credentials_present else 'no'}", flush=True)
    store = SignalStore(STATE_PATH)
    try:
        engine = create_engine(config, store, telegram.send_message if telegram.credentials_present else print)
    except ValueError as exc:
        store.close()
        raise SystemExit(f"Invalid live configuration: {exc}") from None
    if not engine.strategies:
        while True:
            HEARTBEAT_PATH.parent.mkdir(parents=True, exist_ok=True)
            HEARTBEAT_PATH.write_text(_now_utc().isoformat())
            time.sleep(60)
    if not client.credentials_present:
        raise SystemExit("Capital credentials missing")
    try:
        _resolve_instruments(client, config)
        _seed_history(engine, client, strategies, instruments, _now_utc())
    except Exception as exc:
        print(f"Startup failed: {type(exc).__name__}: {exc}", flush=True)
        store.close()
        raise SystemExit(1) from None
    outage = OutageAlerts(engine.send)
    while True:
        try:
            process_poll_cycle(engine, client, strategies, instruments, _now_utc())
            HEARTBEAT_PATH.parent.mkdir(parents=True, exist_ok=True)
            HEARTBEAT_PATH.write_text(_now_utc().isoformat())
            outage.recovered()
            time.sleep(max(1, 60 - _now_utc().second + 5))
        except KeyboardInterrupt:
            break
        except Exception as exc:
            outage.failure(exc, _now_utc())
            time.sleep(60)
    store.close()


class _MemoryClient:
    def __init__(self, bars):
        self.bars = bars.reset_index(drop=True)
        self.ns = self.bars.ts.astype("datetime64[ns, UTC]").astype("int64").to_numpy()
    def prices(self, _epic, _resolution, start, end, max_bars=1000):
        left = np.searchsorted(self.ns, pd.Timestamp(start).value, side="left")
        right = np.searchsorted(self.ns, pd.Timestamp(end).value, side="right")
        return self.bars.iloc[left:min(right, left + max_bars)].reset_index(drop=True)


def verify_bars(module, symbol: str, bars: pd.DataFrame, window_start=None, window_end=None, hours=None):
    bars = bars.sort_values("ts").reset_index(drop=True)
    if symbol not in module.SYMBOLS:
        raise ValueError(f"strategy {module.NAME} does not support requested symbol {symbol}")
    configured = []
    try:
        configured = tomllib.loads(CONFIG_PATH.read_text()).get("instruments", [])
    except OSError:
        pass
    selected = next((item for item in configured if item.get("symbol") == symbol), None)
    hours = hours or (selected.get("hours") if selected else None) or ("cme_equity" if symbol in {"USATECHIDXUSD", "USA500IDXUSD"} else "24x7")
    # Restrict a multi-symbol strategy to the symbol requested by the verifier.
    proxy_name = f"_msd_verify_{module.__name__}_{symbol}"
    proxy = types.ModuleType(proxy_name)
    proxy.NAME, proxy.SYMBOLS, proxy.RESOLUTION, proxy.orders = module.NAME, (symbol,), module.RESOLUTION, module.orders
    if hasattr(module, "WARMUP"):
        proxy.WARMUP = module.WARMUP
    old_module = sys.modules.get(proxy_name)
    sys.modules[proxy_name] = proxy
    entry = {"module": proxy_name, "enabled": True}
    instrument = {"symbol": symbol, "epic": "LOCAL", "hours": hours}
    store = SignalStore(":memory:")
    messages = []
    engine = SignalEngine(store, messages.append, instruments=[instrument], strategies=[entry])
    fake = _MemoryClient(bars)
    delta = RESOLUTION[module.RESOLUTION]
    window_start = None if window_start is None else _utc(window_start)
    window_end = None if window_end is None else _utc(window_end)
    replay_bars = bars
    if window_start is not None:
        seed = bars[bars.ts < window_start].reset_index(drop=True)
        if not seed.empty:
            key = (symbol, module.RESOLUTION)
            engine.bars[key] = seed
            engine.last_processed[key] = seed.ts.iloc[-1]
            store.set_state(f"last_processed:{symbol}:{module.RESOLUTION}", seed.ts.iloc[-1].isoformat())
        replay_bars = bars[bars.ts >= window_start].reset_index(drop=True)
    cleared = window_start is None
    for stamp in replay_bars.ts:
        process_poll_cycle(engine, fake, [entry], [instrument], (stamp + pd.Timedelta(seconds=5)).to_pydatetime())
    if not replay_bars.empty:
        process_poll_cycle(engine, fake, [entry], [instrument], (replay_bars.ts.iloc[-1] + delta + pd.Timedelta(seconds=5)).to_pydatetime())
    orders = module.orders(bars)
    simulated = simulate(bars, orders)
    expected = {f"{symbol}:{module.NAME}:{_utc(order['decision_ts']).isoformat()}": (i, order)
                for i, order in enumerate(orders) if _utc(order["decision_ts"]) + delta < bars.ts.iloc[-1] + delta
                and (window_start is None or _utc(order["decision_ts"]) >= window_start)
                and (window_end is None or _utc(order["decision_ts"]) < window_end)}
    actual_rows = store.connection.execute("SELECT signal_key,side,initial_stop,take_profit,status,exit_price,entry_ts,entry_price,decision_ts FROM signals").fetchall()
    actual = {row[0]: row for row in actual_rows if (window_start is None or _utc(row[8]) >= window_start)
              and (window_end is None or _utc(row[8]) < window_end)}
    mismatches = []
    for key, (order_ix, order) in expected.items():
        row = actual.get(key)
        if row is None or row[1] != int(order["side"]) or not np.isclose(row[2], float(order["stop"])) or (row[3] is None) != (order.get("tp") is None):
            mismatches.append(("signal", key))
            continue
        if order.get("tp") is not None and not np.isclose(row[3], float(order["tp"])):
            mismatches.append(("tp", key))
        position = int(np.searchsorted(bars.ts.astype("datetime64[ns, UTC]").astype("int64").to_numpy(), _utc(order["decision_ts"]).value, side="right"))
        if position >= len(bars) or _utc(row[6]) != _utc(bars.ts.iloc[position]):
            mismatches.append(("entry_ts", key))
        elif not np.isclose(float(row[7]), float(bars.iloc[position].ask_o if int(order["side"]) > 0 else bars.iloc[position].bid_o)):
            mismatches.append(("entry_price", key))
        trade = simulated[simulated.order_id == order_ix]
        if not trade.empty:
            expected_exit = trade.iloc[0]
            # A simulator time exit at the final supplied bar is a dataset boundary,
            # not an observed live exit; compare only exits before that boundary.
            if not (expected_exit.exit_reason == "time" and expected_exit.exit_ts == bars.ts.iloc[-1]):
                if row[4] != expected_exit.exit_reason or row[5] is None or not np.isclose(row[5], expected_exit.exit_price):
                    mismatches.append(("exit", key, row[4], expected_exit.exit_reason))
    extras = set(actual) - set(expected)
    mismatches.extend(("extra", key) for key in extras)
    expected_ids = {order_id for order_id, _order in expected.values()}
    simulated_window = simulated[simulated.order_id.isin(expected_ids)] if not simulated.empty else simulated
    result = {"symbol": symbol, "orders": len(expected), "signals": len(actual), "simulated": len(simulated_window),
              "mismatches": len(mismatches), "details": mismatches, "messages": messages}
    store.close()
    if old_module is None:
        sys.modules.pop(proxy_name, None)
    else:
        sys.modules[proxy_name] = old_module
    return result

def run_check():
    config = tomllib.loads(CONFIG_PATH.read_text())
    client, telegram = CapitalClient(), TelegramClient()
    print(f"credentials present: {'yes' if client.credentials_present else 'no'}")
    if not client.credentials_present:
        raise SystemExit("Capital credentials missing")
    instruments = config.get("instruments", [])
    _resolve_instruments(client, config)
    now = _now_utc()
    for item in instruments:
        bars = _history(client, item["epic"], "MINUTE", now - timedelta(minutes=120), now)
        print(f"{item['symbol']} epic resolved; bars={len(bars)}; latest={bars.ts.iloc[-1] if len(bars) else 'none'}")
    if telegram.credentials_present:
        telegram.send_message("check OK")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--replay", nargs=2, metavar=("START", "END"))
    parser.add_argument("--symbol")
    parser.add_argument("--strategy")
    parser.add_argument("--verify-live", nargs=4, metavar=("MODULE", "SYMBOL", "START", "END"))
    args = parser.parse_args()
    if args.check:
        run_check()
    elif args.verify_live:
        module = importlib.import_module(args.verify_live[0])
        start, end = pd.Timestamp(args.verify_live[2], tz="UTC"), pd.Timestamp(args.verify_live[3], tz="UTC")
        warm_days = {"MINUTE": 42, "HOUR": 120, "DAY": 1000}[module.RESOLUTION]
        bars = load(args.verify_live[1], (start-pd.Timedelta(days=warm_days)).date().isoformat(), end.date().isoformat())
        print(verify_bars(module, args.verify_live[1], bars, start, end))
    elif args.replay:
        if not (args.symbol and args.strategy):
            parser.error("--replay requires --symbol and --strategy")
        module = importlib.import_module(args.strategy)
        start, end = pd.Timestamp(args.replay[0], tz="UTC"), pd.Timestamp(args.replay[1], tz="UTC")
        warm_days = {"MINUTE": 42, "HOUR": 120, "DAY": 1000}[module.RESOLUTION]
        bars = load(args.symbol, (start-pd.Timedelta(days=warm_days)).date().isoformat(), end.date().isoformat())
        result = verify_bars(module, args.symbol, bars, start, end)
        for message in result.pop("messages"):
            print(message)
        print(result)
    elif args.dry_run:
        if not (args.symbol and args.strategy):
            parser.error("--dry-run requires --symbol and --strategy")
        module = importlib.import_module(args.strategy)
        end = pd.Timestamp.now(tz="UTC").floor("D")
        start = end - pd.Timedelta(days=1)
        warm_days = {"MINUTE": 42, "HOUR": 120, "DAY": 1000}[module.RESOLUTION]
        bars = load(args.symbol, (start-pd.Timedelta(days=warm_days)).date().isoformat(), end.date().isoformat())
        result = verify_bars(module, args.symbol, bars, start, end)
        for message in result.pop("messages"):
            print(message)
        print(result)
    else:
        run_live()


if __name__ == "__main__":
    main()
