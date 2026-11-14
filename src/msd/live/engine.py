"""Strategy-agnostic full-day paper signal engine."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import importlib
import json
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

from msd.backtest import AMBIGUITY_KEYS, evaluate_bar, ratchet_stop, simulate
from msd.data import load
from msd.data.dukascopy import COLUMNS
from msd.live.capital import CapitalClient
from msd.live.store import SignalStore
from msd.live.telegram import TelegramClient

NY = ZoneInfo("America/New_York")
HELSINKI = ZoneInfo("Europe/Helsinki")
CONFIG_PATH = Path("live.toml")
STATE_PATH = Path("data/live/state.db")
HEARTBEAT_PATH = Path("data/live/heartbeat")
EPICS_PATH = Path("data/live/epics.json")
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
    if getattr(module, "PAIR", None):
        pair = module.PAIR
        marker = "🟢 LONG" if side > 0 else "🔴 SHORT"
        kind = order.get("entry_type", "market")
        if kind == "stop":
            level = float(order["trigger_price"])
            reference = level
            entry_line = f"Stop entry: {level:,.1f}"
        else:
            reference = entry_price
            entry_line = f"Entry: approx. {entry_price:,.1f}"
        risk = float(order.get("risk_distance") or abs(reference - float(order.get("stop", reference))))
        stop = (float(order["stop"]) if order.get("stop") is not None
                else reference - side * risk)
        exit_rule = str(order.get("exit_rule", "Bot will message when to exit; can last days"))
        return (f"{marker} · {module.NAME}\n{pair}\n{entry_line}\n"
                f"SL: {stop:,.1f}\nTP: none · {exit_rule}\n"
                "Confidence: low\nSize: 1 micro contract max")
    sl = float(order["stop"])
    tp = order.get("tp")
    distance = abs(entry_price - sl)
    optional = lambda value, fmt: "n/a" if value is None else fmt.format(value)
    confidence = optional(order.get("confidence"), "{:.0%}")
    if order.get("entry_type", "market") == "limit":
        expiry = _utc(order["expiry_ts"]).isoformat()
        return (f"{'BUY' if side > 0 else 'SELL'} LIMIT {entry_price:.2f} {pair} | "
                f"SL {sl:.2f} | TP {optional(tp, '{:.2f}')} | valid until {expiry} "
                f"| Confidence {confidence} | {module.NAME}")
    size = optional(order.get("size"), "{:.2f}")
    note = str(order.get("note") or "").strip()
    suffix = f" | {module.NAME}" + (f" {note}" if note else "")
    tp_text = "n/a" if tp is None else f"{float(tp):.2f} (+{abs(float(tp)-entry_price):.2f})"
    return (f"{'🟢' if side > 0 else '🔴'} {'LONG' if side > 0 else 'SHORT'} {pair} | Entry ≈ {entry_price:.2f} "
            f"| SL {sl:.2f} (−{distance:.2f}) | TP {tp_text} "
            f"| Confidence {confidence} | Size {size}×{suffix}")


def _local_time(value) -> str:
    return _utc(value).tz_convert(HELSINKI).strftime("%a %d %b, %H:%M")


def _fill_notice(row: dict, price: float, stop: float) -> str:
    if not row["setup"].startswith("TikTok"):
        return f"{row['entry_type'].upper()} FILLED at {price:.2f} {row['symbol']} {row['setup']}"
    marker = "🟢 LONG" if int(row["side"]) > 0 else "🔴 SHORT"
    pair = "US100 / MNQ"
    return (f"✅ FILLED · {marker} · {row['setup']}\n{pair}\n"
            f"Entry: {price:,.1f}\nSL: {stop:,.1f}")


def _expired_notice(row: dict) -> str:
    if row["setup"].startswith("TikTok"):
        return f"⌛ EXPIRED · {row['setup']}\nUS100 / MNQ\nNo entry was triggered."
    return f"{row['entry_type'].upper()} EXPIRED {row['symbol']} {row['setup']}"


def _exit_now_notice(row: dict, exit_ts) -> str:
    if row["setup"].startswith("TikTok"):
        side = "LONG" if int(row["side"]) > 0 else "SHORT"
        return (f"⚠️ EXIT NOW · {row['setup']}\nUS100 / MNQ · {side}\n"
                f"Exit at next minute open · {_local_time(exit_ts)} Helsinki")
    return f"Exit now at {_utc(exit_ts).isoformat()} ({row['symbol']} {row['setup']})"


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
        self._bar_records: dict[tuple[str, str], list[dict]] = {}
        self._frame_dirty: set[tuple[str, str]] = set()
        self.last_processed: dict[tuple[str, str], pd.Timestamp] = {}
        self.alarm: dict[str, StaleDataAlarm] = {}
        self.ambiguity_stats = dict.fromkeys(AMBIGUITY_KEYS, 0)

    def send(self, message):
        self._send(("📝 PAPER " if self.mode == "paper" else "") + message)

    def _strategy_bars(self, symbol, module):
        key = (symbol, module.RESOLUTION)
        if key not in self._bar_records:
            existing = self.bars.get(key, pd.DataFrame(columns=COLUMNS))
            self._bar_records[key] = existing.to_dict("records") if not existing.empty else []
        records = self._bar_records[key]
        if key in self._frame_dirty:
            frame = pd.DataFrame.from_records(records, columns=COLUMNS)
            history_days = getattr(module, "HISTORY_DAYS", None)
            if history_days and not frame.empty:
                cutoff = pd.Timestamp(frame.ts.iloc[-1]) - pd.Timedelta(days=int(history_days))
                self.store.connection.row_factory = sqlite3.Row
                active_entries = self.store.connection.execute(
                    "SELECT entry_ts FROM signals WHERE symbol=? AND setup=? AND status='open' AND entry_ts IS NOT NULL",
                    (symbol, module.NAME),
                ).fetchall()
                if active_entries:
                    active_cutoff = min(_utc(row["entry_ts"]) for row in active_entries) - pd.Timedelta(days=int(history_days))
                    cutoff = min(cutoff, active_cutoff)
                frame = frame[frame.ts >= cutoff].reset_index(drop=True)
            self.store.connection.row_factory = sqlite3.Row
            active = self.store.connection.execute(
                "SELECT * FROM signals WHERE symbol=? AND setup=? AND status='open'",
                (symbol, module.NAME),
            ).fetchall()
            frame.attrs["open_signals"] = [dict(row) for row in active]
            self.bars[key] = frame
            self._frame_dirty.discard(key)
        return self.bars.get(key, pd.DataFrame(columns=COLUMNS))

    def _last_completed_frame(self, symbol, resolution):
        key = (symbol, resolution)
        records = self._bar_records.get(key)
        if records:
            return pd.DataFrame.from_records(records[-1:], columns=COLUMNS)
        return pd.DataFrame(columns=COLUMNS)

    def process_completed(self, symbol: str, resolution: str, bar: dict,
                          seconds: pd.DataFrame | None = None):
        key = (symbol, resolution)
        row = dict(bar)
        row["ts"] = _utc(row["ts"])
        last = self.last_processed.get(key)
        if last is not None and row["ts"] <= last:
            return
        records = self._bar_records.setdefault(key, [])
        if not records:
            existing = self.bars.get(key)
            if existing is not None and not existing.empty:
                records.extend(existing.to_dict("records"))
        records.append(row)
        self._frame_dirty.add(key)
        self._check_exits(symbol, resolution, row, seconds=seconds)
        self._check_pending(symbol, resolution, row)
        for entry, module in self.strategies:
            if symbol not in module.SYMBOLS or module.RESOLUTION != resolution:
                continue
            should_update = getattr(module, "should_update", None)
            gate_bars = self._last_completed_frame(symbol, resolution)
            if should_update is None or should_update(gate_bars, row["ts"], phase="update"):
                frame = self._strategy_bars(symbol, module)
                self._apply_updates(entry, module, frame, row["ts"], symbol)
        self.last_processed[key] = row["ts"]
        self.store.set_state(f"last_processed:{symbol}:{resolution}", row["ts"].isoformat())

    def process_forming(self, symbol: str, resolution: str, forming: dict):
        forming_ts = _utc(forming["ts"])
        for entry, module in self.strategies:
            if symbol not in module.SYMBOLS or module.RESOLUTION != resolution:
                continue
            completed = self._last_completed_frame(symbol, resolution)
            if completed.empty:
                continue
            completed_ts = _utc(completed.ts.iloc[-1])
            if forming_ts <= completed_ts:
                continue
            should_update = getattr(module, "should_update", None)
            if should_update is not None:
                gate_bars = completed
                if not getattr(module, "USES_FORMING_BAR", False) and not should_update(
                    gate_bars, completed_ts, phase="entry"
                ):
                    continue
                if getattr(module, "USES_FORMING_BAR", False) and not should_update(
                    gate_bars, forming_ts, phase="entry"
                ):
                    continue
            bars = self._strategy_bars(symbol, module)
            if getattr(module, "USES_FORMING_BAR", False):
                forming_row = pd.DataFrame([forming], columns=COLUMNS)
                order_bars = pd.concat([bars, forming_row], ignore_index=True)
                decision_ts = forming_ts
            else:
                order_bars = bars
                decision_ts = completed_ts
            for order in _strategy_orders(module, order_bars):
                if _utc(order["decision_ts"]) != decision_ts:
                    continue
                self._create_signal(entry, module, order, forming, symbol)

    def _validate(self, entry, module, order, entry_price):
        valid = False
        try:
            side = int(order.get("side", 0))
            stop_value = order.get("stop")
            tp_value = order.get("tp")
            entry_type = order.get("entry_type", "market")
            risk_distance = order.get("risk_distance")
            if stop_value is None and risk_distance is not None:
                stop_value = float(entry_price) - side * float(risk_distance)
            valid = (side in (-1, 1) and entry_type in {"market", "limit", "stop"}
                     and stop_value is not None and np.isfinite(float(entry_price))
                     and np.isfinite(float(stop_value)))
            if risk_distance is not None:
                valid = valid and np.isfinite(float(risk_distance)) and float(risk_distance) > 0
            if entry_type in {"limit", "stop"}:
                valid = valid and order.get("expiry_ts") is not None
                if valid:
                    valid = _utc(order["expiry_ts"]) > _utc(order["decision_ts"])
            if entry_type == "stop":
                level = order.get("trigger_price")
                valid = valid and level is not None and np.isfinite(float(level))
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
        entry_type = order.get("entry_type", "market")
        entry_price = (order.get("limit_price", order.get("entry_price"))
                       if entry_type == "limit" else
                       order.get("trigger_price") if entry_type == "stop" else
                       forming["ask_o"] if side > 0 else forming["bid_o"])
        if not self._validate(entry, module, order, entry_price):
            return
        entry_price = float(entry_price)
        decision = _utc(order["decision_ts"])
        key = f"{symbol}:{module.NAME}:{decision.isoformat()}"
        risk = float(order.get("risk_distance") or abs(entry_price - float(order["stop"])))
        opposite = self.store.connection.execute(
            "SELECT signal_key,side,status FROM signals WHERE symbol=? AND setup=? AND status IN ('open','pending')",
            (symbol, module.NAME)).fetchall()
        for old_key, old_side, old_status in opposite:
            if int(old_side) == -side:
                if old_status == "pending":
                    self.cancel_pending(old_key)
                else:
                    self.store.update(old_key, status="flip", exit_ts=decision.isoformat(), exit_price=entry_price,
                                      realized_r=None)
                    self.send(f"EXIT now {symbol} ({module.NAME} flip)")
        stop = (entry_price - side * risk if order.get("stop") is None
                else float(order["stop"]))
        pending = entry_type in {"limit", "stop"}
        values = {"signal_key": key, "symbol": symbol, "setup": module.NAME, "side": side,
                  "decision_ts": decision.isoformat(),
                  "entry_ts": None if pending else _utc(forming["ts"]).isoformat(),
                  "entry_price": None if pending else entry_price,
                  "entry_type": entry_type,
                  "limit_price": entry_price if entry_type == "limit" else None,
                  "trigger_price": entry_price if entry_type == "stop" else None,
                  "eligible_ts": _utc(forming["ts"]).isoformat() if pending else None,
                  "expiry_ts": _utc(order["expiry_ts"]).isoformat() if pending else None,
                  "initial_stop": None if pending and order.get("risk_distance") is not None else stop,
                  "stop": None if pending and order.get("risk_distance") is not None else stop,
                  "take_profit": order.get("tp"), "planned_exit_ts": None if order.get("exit_ts") is None else _utc(order["exit_ts"]).isoformat(),
                  "planned_risk": risk, "risk_distance": order.get("risk_distance"),
                  "risk_from_mid": int(bool(order.get("risk_from_mid", False))),
                  "exit_at_close": int(bool(order.get("exit_at_close", False))),
                  "reminder_minutes": int(order.get("reminder_minutes", 5)),
                  "notional": order.get("size"), "confidence": order.get("confidence"),
                  "status": "pending" if pending else "open",
                  "created_at": datetime.now(timezone.utc).isoformat()}
        if self.store.insert(values):
            self.send(format_signal(symbol, module, order, entry_price))

    def cancel_pending(self, signal_key: str) -> bool:
        """Cancel an unfilled limit once, including after a process restart."""
        row = self.store.get(signal_key)
        if not row or row["status"] != "pending":
            return False
        self.store.update(signal_key, status="cancelled")
        self.send(f"LIMIT CANCELLED {row['symbol']} {row['setup']}")
        return True

    def _check_pending(self, symbol, resolution, bar):
        ts = _utc(bar["ts"])
        self.store.connection.row_factory = sqlite3.Row
        rows = self.store.connection.execute(
            "SELECT * FROM signals WHERE symbol=? AND status='pending'", (symbol,)).fetchall()
        for raw in rows:
            row = dict(raw)
            if row["eligible_ts"] is None or ts < _utc(row["eligible_ts"]):
                continue
            if ts >= _utc(row["expiry_ts"]):
                self.store.update(row["signal_key"], status="expired")
                self.send(_expired_notice(row))
                continue
            side = int(row["side"])
            level = float(row["trigger_price"] if row["entry_type"] == "stop" else row["limit_price"])
            if row["entry_type"] == "stop":
                touched = float(bar["ask_h"]) >= level if side > 0 else float(bar["bid_l"]) <= level
            else:
                touched = float(bar["ask_l"]) <= level if side > 0 else float(bar["bid_h"]) >= level
            if not touched:
                continue
            if row["entry_type"] == "stop":
                fill = max(float(bar["ask_o"]), level) if side > 0 else min(float(bar["bid_o"]), level)
            else:
                fill = min(float(bar["ask_o"]), level) if side > 0 else max(float(bar["bid_o"]), level)
            if row.get("risk_distance") is not None:
                risk_entry = fill
                if row.get("risk_from_mid"):
                    half_spread = (float(bar["ask_o"]) - float(bar["bid_o"])) / 2
                    risk_entry = fill - side * half_spread
                stop = risk_entry - side * float(row["risk_distance"])
            else:
                stop = float(row["stop"])
            self.store.update(row["signal_key"], status="open", entry_ts=ts.isoformat(), entry_price=fill,
                              initial_stop=stop, stop=stop)
            self.send(_fill_notice(row, fill, stop))
            if row["entry_type"] == "stop":
                # The trigger candle itself can cross the stop. Research gives the
                # stop priority when trigger and stop are both touched in one bar.
                _, reason, price = evaluate_bar(side, stop, row.get("take_profit"), bar)
            else:
                # Limit fills keep the reference-kernel convention (no TP on the fill bar).
                deadline = row.get("planned_exit_ts")
                time_exit = deadline is not None and ts >= _utc(deadline)
                _, reason, price = evaluate_bar(side, stop, None, bar,
                                                time_exit=time_exit, time_at_open=time_exit,
                                                stop_active=not time_exit)
            if reason is not None:
                risk = float(row["planned_risk"])
                realized = side * (price - fill) / risk
                self.store.update(row["signal_key"], status=reason, exit_ts=ts.isoformat(),
                                  exit_price=price, realized_r=realized)
                self.send(f"{symbol} {reason.upper()} hit at {price:.2f}; realized {realized:.2f}R")

    def _apply_updates(self, entry, module, bars, through, symbol):
        for order in _strategy_orders(module, bars):
            decision = _utc(order["decision_ts"])
            if decision > through:
                continue
            key = f"{symbol}:{module.NAME}:{decision.isoformat()}"
            saved = self.store.get(key)
            if not saved or saved["status"] != "open":
                continue
            planned_exit = order.get("exit_ts")
            if planned_exit is not None:
                planned_exit = _utc(planned_exit).isoformat()
                if saved.get("planned_exit_ts") != planned_exit:
                    self.store.update(
                        key, planned_exit_ts=planned_exit,
                        exit_at_close=int(bool(order.get("exit_at_close", False))),
                        reminder_minutes=int(order.get("reminder_minutes", 0)),
                    )
                    if saved.get("planned_exit_ts") is None:
                        self.send(_exit_now_notice(saved, planned_exit))
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

    def _check_exits(self, symbol, resolution, bar, *, seconds=None):
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
            scheduled_tiktok_exit = bool(row.get("exit_at_close")) or row["setup"].startswith("TikTok B")
            if time_exit and scheduled_tiktok_exit:
                _active_stop, reason, price = evaluate_bar(
                    side, stop, row.get("take_profit"), bar, seconds=seconds,
                    ambiguity_stats=self.ambiguity_stats if seconds is not None else None)
                if reason is None:
                    prefix = "bid" if side > 0 else "ask"
                    price, reason = float(bar[f"{prefix}_{'c' if row.get('exit_at_close') else 'o'}"]), "time"
            else:
                _active_stop, reason, price = evaluate_bar(
                    side, stop, row.get("take_profit"), bar, time_exit=time_exit,
                    time_at_open=time_exit, seconds=seconds,
                    ambiguity_stats=self.ambiguity_stats if seconds is not None else None)
            if reason is None:
                continue
            risk = max(float(row["planned_risk"] or 0), 1e-12)
            realized = side * (price - float(row["entry_price"])) / risk
            self.store.update(row["signal_key"], status=reason, exit_ts=ts.isoformat(), exit_price=price, realized_r=realized)
            if row["setup"].startswith("TikTok"):
                marker = "🛑" if reason == "stop" else "✅"
                side_label = "LONG" if side > 0 else "SHORT"
                self.send(f"{marker} EXIT · {row['setup']}\nUS100 / MNQ · {side_label}\n"
                          f"{reason.upper()} at {price:,.1f} · {_local_time(ts)} Helsinki · {realized:+.2f}R")
            else:
                self.send(f"{symbol} {reason.upper()} hit at {price:.2f}; realized {realized:.2f}R")

    def reminder(self, now: datetime):
        now_ts = pd.Timestamp(now).tz_convert("UTC")
        self.store.connection.row_factory = sqlite3.Row
        rows = self.store.connection.execute("SELECT * FROM signals WHERE status='open' AND planned_exit_ts IS NOT NULL").fetchall()
        for raw in rows:
            row = dict(raw)
            end = _utc(row["planned_exit_ts"])
            flag = f"reminded:{row['signal_key']}"
            remind_minutes = int(row["reminder_minutes"] if row.get("reminder_minutes") is not None else 5)
            if end - pd.Timedelta(minutes=remind_minutes) <= now_ts < end and not self.store.get_state(flag):
                if row["setup"].startswith("TikTok"):
                    self.send(f"⏰ EXIT BY · {row['setup']}\nUS100 / MNQ\n{_local_time(end)} Helsinki")
                else:
                    self.send(f"Exit by {end.isoformat()} ({row['symbol']} {row['setup']})")
                self.store.set_state(flag, "1")
        pending = self.store.connection.execute("SELECT * FROM signals WHERE status='pending'").fetchall()
        for raw in pending:
            row = dict(raw)
            expiry = row.get("expiry_ts")
            if expiry and now_ts >= _utc(expiry):
                self.store.update(row["signal_key"], status="expired")
                self.send(_expired_notice(row))

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

def _resolve_instruments(client, config, path=EPICS_PATH, *, refresh=False):
    try:
        resolved = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        resolved = {}
    for item in config.get("instruments", []):
        if refresh or not item.get("epic"):
            epic = None if refresh else resolved.get(item["symbol"])
            if epic:
                item["epic"] = epic
                continue
            market = client.search_market(item["search_term"])
            if not market.get("epic"):
                raise RuntimeError(f"market not found for {item['symbol']}")
            item["epic"] = market["epic"]
        resolved[item["symbol"]] = item["epic"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(resolved, indent=2, sort_keys=True) + "\n")
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
            engine._bar_records[key] = history.to_dict("records")
            engine._frame_dirty.add(key)
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
    client = CapitalClient()
    if not client.credentials_present:
        print("Capital credentials present: no; live engine not started.", flush=True)
        return
    telegram = TelegramClient()
    print("Capital credentials present: yes", flush=True)
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

def run_check(client=None, *, config_path=CONFIG_PATH, epics_path=EPICS_PATH):
    config = tomllib.loads(config_path.read_text())
    client = client or CapitalClient()
    print(f"credentials present: {'yes' if client.credentials_present else 'no'}")
    if not client.credentials_present:
        return
    instruments = config.get("instruments", [])
    client.login()
    _resolve_instruments(client, config, epics_path, refresh=True)
    now = _now_utc()
    for item in instruments:
        bars = _history(client, item["epic"], "MINUTE", now - timedelta(minutes=120), now)
        latest = bars.ts.iloc[-1].isoformat() if len(bars) else "none"
        print(f"epic: {item['epic']}; bars: {len(bars)}; latest: {latest}")


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
