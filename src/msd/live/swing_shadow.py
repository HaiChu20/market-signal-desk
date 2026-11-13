"""Frozen swing v1 shadow job for 07:00 Europe/Helsinki, before the 07:00 UTC entry."""
from __future__ import annotations

import argparse
import csv
import multiprocessing
import os
from pathlib import Path
import tempfile

import numpy as np
import pandas as pd

from msd.data import dukascopy
from msd.live.binance import BinanceSpotFeed
from msd.live.telegram import TelegramClient
from msd.research import swing_stage1 as s1

MARKETS = tuple(s1.TRADED)
LOOKBACK_DAYS = 400
REFRESH_DAYS = 21
REFRESH_TIMEOUT_SECONDS = 10 * 60
LOG_COLUMNS = (
    "run_ts", "market", "contract", "signal_close", "data_last_ts", "stale",
    "state", "side", "entry_ts", "entry_price", "sl", "tp", "cap_session_end",
    "unrealised_R", "exit_ts", "exit_reason", "net_R", "trade_signal_close",
    "plan_entry_ts", "reference_price", "atr", "sl_distance", "tp_distance",
    "plan_sl", "plan_tp", "refresh_error",
)
BACKTEST_LINE = "Backtest: DEV +0.16R per trade; final +0.04R on 88 trades."
CONFIDENCE_LINE = ("Confidence: low (rule-based; DEV +0.16R per trade, "
                   "final +0.04R on 88 trades).")
TELEGRAM_COLUMNS = ("sent_at", "event_id", "market", "event_type", "reference")


def latest_ny_close(now: pd.Timestamp) -> pd.Timestamp:
    """Latest weekday 17:00 New York close at or before now."""
    stamp = pd.Timestamp(now)
    stamp = stamp.tz_localize("UTC") if stamp.tzinfo is None else stamp.tz_convert("UTC")
    local = stamp.tz_convert(s1.NY)
    day = local.normalize()
    for offset in range(8):
        candidate_day = day - pd.Timedelta(days=offset)
        candidate = candidate_day + pd.Timedelta(hours=17)
        if candidate.weekday() < 5 and candidate <= local:
            return candidate.tz_convert("UTC")
    raise AssertionError("no completed New York close found")


def is_stale(last_bar: pd.Timestamp, now: pd.Timestamp) -> bool:
    """Minute timestamps are opens, so 16:59 covers the 17:00 close."""
    last = pd.Timestamp(last_bar)
    last = last.tz_localize("UTC") if last.tzinfo is None else last.tz_convert("UTC")
    return last + pd.Timedelta(minutes=1) < latest_ny_close(now)


def _latest_local_bar(directory: Path) -> pd.Timestamp | None:
    paths = sorted(directory.glob("[0-9][0-9][0-9][0-9]-[0-9][0-9].parquet"))
    for path in reversed(paths):
        frame = pd.read_parquet(path, columns=["ts"])
        if len(frame):
            return pd.to_datetime(frame.ts, utc=True).max()
    return None


def _write_binance_backfill(root: Path, rows: list[dict]) -> None:
    if not rows:
        return
    incoming = pd.DataFrame(rows).sort_values("ts")
    incoming["ts"] = pd.to_datetime(incoming.ts, utc=True)
    for month, part in incoming.groupby(incoming.ts.dt.strftime("%Y-%m")):
        path = root / "bars/binance_spot/BTCUSDT" / f"{month}.parquet"
        if path.exists():
            prior = pd.read_parquet(path)
            frame = pd.concat([prior, part], ignore_index=True)
        else:
            frame = part.copy()
        frame["ts"] = pd.to_datetime(frame.ts, utc=True)
        frame = frame.sort_values("ts").drop_duplicates("ts", keep="last").reset_index(drop=True)
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".parquet", delete=False) as handle:
            temporary = Path(handle.name)
        try:
            frame.to_parquet(temporary, index=False)
            os.replace(temporary, path)
        finally:
            if temporary.exists():
                temporary.unlink()


def refresh_market(data_root: Path, market: str, now: pd.Timestamp) -> None:
    """Refresh only the recent window using the existing public-data clients."""
    stamp = pd.Timestamp(now)
    stamp = stamp.tz_localize("UTC") if stamp.tzinfo is None else stamp.tz_convert("UTC")
    start = (stamp - pd.Timedelta(days=REFRESH_DAYS)).date()
    # A Dukascopy UTC-day candle file is only available after that UTC day ends.
    end = (stamp - pd.Timedelta(days=1)).date()
    if market == "BTCUSDT":
        directory = data_root / "bars/binance_spot/BTCUSDT"
        latest = _latest_local_bar(directory)
        floor = pd.Timestamp(start, tz="UTC") - pd.Timedelta(minutes=1)
        after = max(latest, floor) if latest is not None else floor
        rows = BinanceSpotFeed(market).backfill(after, now=stamp)
        _write_binance_backfill(data_root, rows)
    else:
        dukascopy.download(
            market, start, end, root=data_root / "bars/dukascopy", workers=2
        )


def _refresh_worker(data_root: Path, market: str, now: pd.Timestamp, connection) -> None:
    try:
        refresh_market(data_root, market, now)
        connection.send("")
    except Exception as exc:
        connection.send(f"{type(exc).__name__}: {exc}")
    finally:
        connection.close()


def refresh_with_timeout(data_root: Path, market: str, now: pd.Timestamp,
                         timeout_seconds: float = REFRESH_TIMEOUT_SECONDS,
                         _worker=_refresh_worker) -> None:
    """Run one refresh in an isolated process with a hard wall-clock limit."""
    context = multiprocessing.get_context("spawn")
    receive, send = context.Pipe(duplex=False)
    process = context.Process(target=_worker, args=(data_root, market, now, send))
    process.start()
    send.close()
    process.join(timeout_seconds)
    if process.is_alive():
        process.terminate()
        process.join(5)
        if process.is_alive():
            process.kill()
            process.join()
        receive.close()
        raise TimeoutError(f"{market} refresh exceeded {timeout_seconds:g} seconds")
    try:
        error = receive.recv() if receive.poll() else ""
    except EOFError:
        error = ""
    receive.close()
    if error:
        raise RuntimeError(error)
    if process.exitcode != 0:
        raise RuntimeError(f"{market} refresh process exited {process.exitcode}")


def _side_text(side: int | str | None) -> str:
    if side in (1, "1", 1.0):
        return "LONG"
    if side in (-1, "-1", -1.0):
        return "SHORT"
    return ""


def analyze_market(bars: pd.DataFrame, market: str, now: pd.Timestamp,
                   refresh_error: str = "") -> tuple[dict, str]:
    """Replay one market and return its audit row and human-readable block."""
    now = pd.Timestamp(now)
    now = now.tz_localize("UTC") if now.tzinfo is None else now.tz_convert("UTC")
    ts = pd.DatetimeIndex(pd.to_datetime(bars.ts, utc=True))
    expected_close = latest_ny_close(now)
    stale = is_stale(ts[-1], now) or bool(refresh_error)
    period = s1.Period(data_start=ts[0], end=now.floor("min") + pd.Timedelta(minutes=1))
    first_year = int(ts[0].tz_convert(s1.NY).year) - 1
    daily = s1.daily_bars(bars, period=period)
    signal = s1.signals(daily, first_year)
    eligible = signal[signal.end <= expected_close]
    if eligible.empty:
        raise ValueError(f"{market}: no completed daily signal row")
    latest = eligible.iloc[-1]
    rows, _, open_trades = s1.replay_market(
        bars, market, primary_only=True, period=period, setups=("S3",),
        first_year=first_year,
    )
    open_trade = open_trades.get(("S3", 2.0, 3.0))
    mid_close = float((bars.bid_c.iloc[-1] + bars.ask_c.iloc[-1]) / 2)
    record = {column: "" for column in LOG_COLUMNS}
    record.update({
        "run_ts": now.isoformat(), "market": market, "contract": s1.TRADED[market],
        "signal_close": expected_close.isoformat(), "data_last_ts": ts[-1].isoformat(),
        "stale": str(stale).lower(), "refresh_error": refresh_error,
    })
    record["_replay_rows"] = rows
    record["_open_trade"] = open_trade
    record["_current_price"] = mid_close
    detail = ""
    flat = open_trade is None
    if open_trade is not None:
        unrealised = open_trade["side"] * (mid_close - open_trade["entry_price"]) / open_trade["risk"]
        record.update({
            "state": "OPEN", "side": open_trade["side"],
            "entry_ts": open_trade["entry_ts"], "entry_price": open_trade["entry_price"],
            "sl": open_trade["stop"], "tp": open_trade["target"],
            "cap_session_end": open_trade["cap_session_end"],
            "unrealised_R": unrealised, "trade_signal_close": open_trade["signal_end"],
        })
        detail = (f"OPEN {_side_text(open_trade['side'])} from {open_trade['entry_ts']} "
                  f"@ {open_trade['entry_price']:.2f}; SL {open_trade['stop']:.2f}; "
                  f"TP {open_trade['target']:.2f}; cap session {open_trade['cap_session_end']}; "
                  f"unrealised {unrealised:+.2f}R (gross).")
    else:
        previous_close = eligible.end.iloc[-2] if len(eligible) > 1 else ts[0] - pd.Timedelta(minutes=1)
        recent = [row for row in rows if pd.Timestamp(row["exit_ts"]) > previous_close]
        if recent:
            exited = max(recent, key=lambda row: row["exit_ts"])
            record.update({
                "state": "EXITED", "side": exited["side"],
                "entry_ts": exited["entry_ts"], "exit_ts": exited["exit_ts"],
                "exit_reason": exited["exit"], "net_R": exited["net_R"],
                "trade_signal_close": exited["signal_end"],
            })
            detail = (f"JUST EXITED {_side_text(exited['side'])}: {exited['exit']} at "
                      f"{exited['exit_ts']}, {exited['net_R']:+.2f}R net.")
        else:
            record["state"] = "FLAT"
            detail = "FLAT."

    plan = ""
    if stale:
        plan = (f"STALE: last bar {ts[-1].isoformat()} does not cover the latest 17:00 New York "
                f"close ({expected_close.isoformat()}); no new trade plan issued.")
    elif flat and int(latest.S3) != 0 and np.isfinite(latest.atr):
        side = int(latest.S3)
        risk = float(2 * latest.atr)
        tp_distance = 3 * risk
        entry = s1.entry_time(latest.end)
        sl = mid_close - side * risk
        tp = mid_close + side * tp_distance
        record.update({
            "side": side, "plan_entry_ts": entry.isoformat(),
            "reference_price": mid_close, "atr": float(latest.atr),
            "sl_distance": risk, "tp_distance": tp_distance,
            "plan_sl": sl, "plan_tp": tp,
        })
        plan = (f"NEW {_side_text(side)} plan: enter {entry.isoformat()} at the 07:00 UTC bar; "
                f"spot reference {mid_close:.2f}; ATR {latest.atr:.2f}; SL distance {risk:.2f} points; "
                f"TP distance {tp_distance:.2f} points; spot-equivalent SL {sl:.2f}, TP {tp:.2f}. "
                "On futures, set SL and TP from the actual fill price using those distances.")
    elif not stale:
        plan = "No new plan while the trade is open." if not flat else "No S3 plan from the latest close."

    error_text = f" Refresh error: {refresh_error}." if refresh_error else ""
    message = (f"{s1.TRADED[market]} ({market}) — signal close {expected_close.isoformat()}\n"
               f"{detail}\n{plan}{error_text}")
    return record, message


def append_records(path: Path, records: list[dict]) -> int:
    """Allow a fresh row to supersede stale audit history, never the reverse."""
    existing: dict[tuple[str, str], set[bool]] = {}
    if path.exists():
        with path.open(newline="") as handle:
            for row in csv.DictReader(handle):
                key = (row["market"], row["signal_close"])
                existing.setdefault(key, set()).add(row.get("stale", "").lower() == "true")
    fresh = []
    for row in records:
        key = (row["market"], row["signal_close"])
        stale = str(row.get("stale", "")).lower() == "true"
        prior = existing.get(key, set())
        if False in prior or (stale and True in prior):
            continue
        fresh.append(row)
        existing.setdefault(key, set()).add(stale)
    if not fresh:
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not path.exists() or path.stat().st_size == 0
    with path.open("a", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=LOG_COLUMNS, lineterminator="\n",
                                extrasaction="ignore")
        if write_header:
            writer.writeheader()
        writer.writerows(fresh)
    return len(fresh)


def _event_id(market: str, event_type: str, reference: str) -> str:
    return f"{market}|{event_type}|{reference}"


def _dual_time(value: str | pd.Timestamp) -> str:
    stamp = pd.Timestamp(value)
    stamp = stamp.tz_localize("UTC") if stamp.tzinfo is None else stamp.tz_convert("UTC")
    return f"{stamp.isoformat()} UTC / {stamp.tz_convert('Europe/Helsinki').isoformat()} Helsinki"


def _open_text(record: dict) -> str:
    entry = float(record["entry_price"])
    stop = float(record["sl"])
    target = float(record["tp"])
    return (f"{record['contract']} OPEN {_side_text(record['side'])}: entry {record['entry_ts']} "
            f"at spot {entry:.2f}; SL {stop:.2f} ({abs(entry-stop):.2f} points); "
            f"TP {target:.2f} ({abs(target-entry):.2f} points); "
            f"unrealised {float(record['unrealised_R']):+.2f}R; "
            f"30-session cap {record['cap_session_end']}.")


def _new_text(record: dict) -> str:
    return (f"NEW {record['contract']} {_side_text(record['side'])}\n"
            f"Entry: {_dual_time(record['plan_entry_ts'])} at the 07:00 UTC bar\n"
            f"Spot reference: {float(record['reference_price']):.2f}\n"
            f"SL: {float(record['sl_distance']):.2f} points; spot-equivalent "
            f"{float(record['plan_sl']):.2f}\n"
            f"TP: {float(record['tp_distance']):.2f} points; spot-equivalent "
            f"{float(record['plan_tp']):.2f}\n"
            "On futures, set SL and TP from the actual fill price using those distances.\n"
            f"{CONFIDENCE_LINE}\n"
            f"{BACKTEST_LINE}")


def _late_entry_text(record: dict) -> str:
    entry = float(record["entry_price"])
    stop = float(record["sl"])
    target = float(record["tp"])
    return (f"LATE ENTRY {record['contract']} {_side_text(record['side'])}\n"
            f"Original entry: {_dual_time(record['entry_ts'])} at spot {entry:.2f}\n"
            f"Current spot: {float(record['_current_price']):.2f}; "
            f"unrealised {float(record['unrealised_R']):+.2f}R\n"
            f"SL: {abs(entry-stop):.2f} points; spot level {stop:.2f}\n"
            f"TP: {abs(target-entry):.2f} points; spot level {target:.2f}\n"
            "This trade is already open in the rule replay; you may enter late or skip it. "
            "If entering, set SL and TP from the actual futures fill using the distances.\n"
            f"{CONFIDENCE_LINE}\n{BACKTEST_LINE}")


def _exit_text(record: dict) -> str:
    reason = str(record["exit_reason"]).upper()
    if reason == "CAP":
        return (f"ACTION: {record['contract']} CAP EXIT — close the position manually now. "
                f"Entry {record['entry_ts']}; model exit {record['exit_ts']}; "
                f"result {float(record['net_R']):+.2f}R net.")
    return (f"INFO: {record['contract']} EXIT {reason} at {record['exit_ts']}; "
            f"result {float(record['net_R']):+.2f}R net. "
            "The broker protective order fills this exit; no manual close action.")


def _stale_text(record: dict) -> str:
    detail = f" Refresh error: {record['refresh_error']}." if record.get("refresh_error") else ""
    return (f"STALE {record['contract']}: data does not cover signal close "
            f"{record['signal_close']}; no new plan issued.{detail}")


def next_scheduled_run(now: pd.Timestamp) -> pd.Timestamp:
    stamp = pd.Timestamp(now)
    stamp = stamp.tz_localize("UTC") if stamp.tzinfo is None else stamp.tz_convert("UTC")
    local = stamp.tz_convert("Europe/Helsinki")
    candidate = local.normalize() + pd.Timedelta(hours=7)
    if candidate <= local:
        candidate = local.normalize() + pd.DateOffset(days=1) + pd.Timedelta(hours=7)
    return candidate.tz_convert("UTC")


def _cap_warning_due(record: dict, now: pd.Timestamp) -> bool:
    return (record.get("state") == "OPEN" and bool(record.get("cap_session_end")) and
            pd.Timestamp(record["cap_session_end"]) <= next_scheduled_run(now))


def _cap_warning_text(record: dict) -> str:
    return (f"ACTION: {record['contract']} reaches its 30-session cap before the next run. "
            f"Close the position at {_dual_time(record['cap_session_end'])}.")


def _entry_was_announced(sent_ids: set[str], market: str, entry: str) -> bool:
    return (_event_id(market, "ENTRY", entry) in sent_ids or
            _event_id(market, "NEW", entry) in sent_ids)


def telegram_events(records: list[dict], now: pd.Timestamp, *,
                    sent_ids: set[str] | None = None,
                    connected_at: pd.Timestamp | None = None,
                    include_late: bool = True) -> list[dict]:
    sent_ids = sent_ids or set()
    events = []
    for record in records:
        market = str(record["market"])
        if record.get("plan_entry_ts") and str(record.get("stale", "")).lower() != "true":
            reference = str(record["plan_entry_ts"])
            events.append({"event_id": _event_id(market, "ENTRY", reference),
                           "market": market, "event_type": "NEW", "reference": reference,
                           "text": _new_text(record)})
        replay_rows = record.get("_replay_rows")
        if replay_rows is not None:
            for trade in replay_rows:
                if connected_at is not None and pd.Timestamp(trade["exit_ts"]) <= connected_at:
                    continue
                reason = str(trade["exit"]).upper()
                event_type = f"EXIT_{reason}"
                reference = str(trade["entry_ts"])
                exit_record = {"contract": record["contract"], "entry_ts": trade["entry_ts"],
                               "exit_ts": trade["exit_ts"], "exit_reason": trade["exit"],
                               "net_R": trade["net_R"]}
                events.append({"event_id": _event_id(market, event_type, reference),
                               "market": market, "event_type": event_type, "reference": reference,
                               "text": _exit_text(exit_record)})
        elif record.get("state") == "EXITED":
            reason = str(record.get("exit_reason", "")).upper()
            event_type = f"EXIT_{reason}"
            reference = str(record["entry_ts"])
            events.append({"event_id": _event_id(market, event_type, reference),
                           "market": market, "event_type": event_type, "reference": reference,
                           "text": _exit_text(record)})
        if (include_late and record.get("state") == "OPEN" and record.get("_open_trade") and
                not _entry_was_announced(sent_ids, market, str(record["entry_ts"]))):
            reference = str(record["entry_ts"])
            events.append({"event_id": _event_id(market, "ENTRY", reference),
                           "market": market, "event_type": "LATE_ENTRY", "reference": reference,
                           "text": _late_entry_text(record)})
        if _cap_warning_due(record, now):
            reference = str(record["entry_ts"])
            events.append({"event_id": _event_id(market, "CAP_WARNING", reference),
                           "market": market, "event_type": "CAP_WARNING", "reference": reference,
                           "text": _cap_warning_text(record)})
        if str(record.get("stale", "")).lower() == "true":
            reference = str(record["signal_close"])
            events.append({"event_id": _event_id(market, "STALE", reference),
                           "market": market, "event_type": "STALE", "reference": reference,
                           "text": _stale_text(record)})
    local = pd.Timestamp(now).tz_convert("Europe/Helsinki")
    if local.weekday() == 0:
        reference = local.date().isoformat()
        open_lines = [_open_text(record) for record in records if record.get("state") == "OPEN"]
        text = (f"Swing v1 weekly heartbeat — {reference}\nOpen trades:\n" +
                ("\n".join(open_lines) if open_lines else "None."))
        events.append({"event_id": _event_id("ALL", "HEARTBEAT", reference),
                       "market": "ALL", "event_type": "HEARTBEAT", "reference": reference,
                       "text": text})
    return events


def connected_message(records: list[dict], now: pd.Timestamp | None = None) -> str:
    lines = ["Swing v1 CONNECTED", BACKTEST_LINE]
    for record in records:
        state = str(record.get("state", "UNKNOWN"))
        if state == "OPEN":
            lines.append(_open_text(record))
        elif state == "EXITED":
            lines.append(f"{record['contract']} current state: FLAT; {_exit_text(record)}")
        else:
            lines.append(f"{record['contract']} current state: {state}.")
        if record.get("plan_entry_ts") and str(record.get("stale", "")).lower() != "true":
            lines.append(_new_text(record))
        if str(record.get("stale", "")).lower() == "true":
            lines.append(_stale_text(record))
        if now is not None and _cap_warning_due(record, now):
            lines.append(_cap_warning_text(record))
    return "\n".join(lines)


def _sent_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def _sent_ids(path: Path) -> set[str]:
    return {row["event_id"] for row in _sent_rows(path)}


def _connected_at(path: Path) -> pd.Timestamp | None:
    rows = [row for row in _sent_rows(path) if row["event_type"] == "CONNECTED"]
    return pd.Timestamp(rows[0]["sent_at"]) if rows else None


def _connected_entry_markers(records: list[dict]) -> list[dict]:
    markers = []
    for record in records:
        reference = (record.get("entry_ts") if record.get("state") == "OPEN"
                     else record.get("plan_entry_ts"))
        if not reference:
            continue
        markers.append({"event_id": _event_id(str(record["market"]), "ENTRY", str(reference)),
                        "market": str(record["market"]), "event_type": "ENTRY_CONNECTED",
                        "reference": str(reference)})
    return markers


def _append_sent(path: Path, events: list[dict], now: pd.Timestamp) -> None:
    if not events:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not path.exists() or path.stat().st_size == 0
    with path.open("a", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=TELEGRAM_COLUMNS, lineterminator="\n")
        if write_header:
            writer.writeheader()
        for event in events:
            writer.writerow({"sent_at": now.isoformat(),
                             **{key: event[key] for key in TELEGRAM_COLUMNS[1:]}})


def _redacted_error(error: Exception, client) -> str:
    message = f"{type(error).__name__}: {error}"
    for secret in (getattr(client, "token", ""), getattr(client, "chat_id", "")):
        if secret:
            message = message.replace(str(secret), "[REDACTED]")
    return message


def deliver_telegram(records: list[dict], shadow_root: Path, now: pd.Timestamp,
                     client=None) -> list[str]:
    """Send accepted events once; failures remain unrecorded for the next run."""
    client = client or TelegramClient()
    history = shadow_root / "telegram_sent.csv"
    sent = _sent_ids(history)
    statuses = []
    if not sent:
        connected = {"event_id": _event_id("ALL", "CONNECTED", "initial"),
                     "market": "ALL", "event_type": "CONNECTED", "reference": "initial",
                     "text": connected_message(records, now)}
        events = telegram_events(records, now, sent_ids=set(), connected_at=now,
                                 include_late=False)
        try:
            client.send_message(connected["text"])
            accepted = [connected, *events, *_connected_entry_markers(records)]
            unique = {event["event_id"]: event for event in accepted}
            _append_sent(history, list(unique.values()), now)
            statuses.append("Telegram: CONNECTED accepted.")
        except Exception as exc:
            statuses.append(f"Telegram send failed; will retry: {_redacted_error(exc, client)}")
        return statuses
    events = telegram_events(records, now, sent_ids=sent,
                             connected_at=_connected_at(history))
    for event in events:
        if event["event_id"] in sent:
            continue
        try:
            client.send_message(event["text"])
            _append_sent(history, [event], now)
            sent.add(event["event_id"])
            statuses.append(f"Telegram: {event['event_type']} accepted for {event['market']}.")
        except Exception as exc:
            statuses.append(f"Telegram send failed; will retry: {_redacted_error(exc, client)}")
    return statuses


def test_telegram(client=None) -> str:
    client = client or TelegramClient()
    try:
        client.send_message("Swing v1 Telegram connection test — delivery OK.")
    except Exception as exc:
        raise RuntimeError(f"Telegram test failed: {_redacted_error(exc, client)}") from None
    return "Telegram connection test accepted."


def run(data_root: Path = Path("data"), shadow_root: Path = Path("data/shadow"), *,
        now: pd.Timestamp | None = None, refresh: bool = True,
        send: bool = False, telegram_client=None) -> str:
    now = pd.Timestamp.now(tz="UTC") if now is None else pd.Timestamp(now)
    now = now.tz_localize("UTC") if now.tzinfo is None else now.tz_convert("UTC")
    records, blocks = [], []
    start = now - pd.Timedelta(days=LOOKBACK_DAYS)
    for market in MARKETS:
        error = ""
        if refresh:
            try:
                refresh_with_timeout(data_root, market, now)
            except Exception as exc:  # stale guard below fails closed after transport errors
                error = f"{type(exc).__name__}: {exc}"
        try:
            bars = s1.load_minutes(
                data_root, market,
                period=s1.Period(data_start=start, end=now.floor("min") + pd.Timedelta(minutes=1)),
            )
            record, block = analyze_market(bars, market, now, error)
        except Exception as exc:
            close = latest_ny_close(now)
            record = {column: "" for column in LOG_COLUMNS}
            record.update({
                "run_ts": now.isoformat(), "market": market, "contract": s1.TRADED[market],
                "signal_close": close.isoformat(), "stale": "true", "state": "STALE",
                "refresh_error": error or f"{type(exc).__name__}: {exc}",
            })
            block = (f"{s1.TRADED[market]} ({market}) — STALE\n"
                     f"No new trade plan issued: {record['refresh_error']}")
        records.append(record)
        blocks.append(block)
    appended = append_records(shadow_root / "swing_v1.csv", records)
    planned_entry = s1.entry_time(latest_ny_close(now))
    message = (f"Swing v1 SHADOW — no orders sent | run {now.isoformat()} | "
               f"planned entry {planned_entry.isoformat()} (07:00 UTC)\n" +
               "Intended daily run: 07:00 Europe/Helsinki (05:00 UTC winter / 04:00 UTC summer), "
               "after Dukascopy publishes the prior UTC day.\n" +
               BACKTEST_LINE + "\n\n" +
               "\n\n".join(blocks) + f"\n\nAudit rows appended: {appended}.")
    shadow_root.mkdir(parents=True, exist_ok=True)
    (shadow_root / "swing_v1_latest.txt").write_text(message + "\n")
    if send:
        client = telegram_client or TelegramClient()
        try:
            statuses = deliver_telegram(records, shadow_root, now, client)
        except Exception as exc:
            statuses = [f"Telegram delivery failed; audit preserved: {_redacted_error(exc, client)}"]
        if statuses:
            message += "\n" + "\n".join(statuses)
    return message


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--shadow-root", type=Path, default=Path("data/shadow"))
    parser.add_argument("--no-refresh", action="store_true", help="use local bars only")
    delivery = parser.add_mutually_exclusive_group()
    delivery.add_argument("--send", action="store_true", help="send deduplicated Telegram events")
    delivery.add_argument("--test-telegram", action="store_true",
                          help="send one Telegram connection test and exit")
    args = parser.parse_args()
    if args.test_telegram:
        print(test_telegram())
        return
    print(run(args.data_root, args.shadow_root, refresh=not args.no_refresh, send=args.send))


if __name__ == "__main__":
    main()
