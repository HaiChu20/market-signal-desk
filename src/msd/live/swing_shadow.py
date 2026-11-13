"""Daily shadow message and append-only audit log for the frozen swing v1 rule."""
from __future__ import annotations

import argparse
import csv
import os
from pathlib import Path
import tempfile

import numpy as np
import pandas as pd

from msd.data import dukascopy
from msd.live.binance import BinanceSpotFeed
from msd.research import swing_stage1 as s1

MARKETS = tuple(s1.TRADED)
LOOKBACK_DAYS = 400
REFRESH_DAYS = 21
LOG_COLUMNS = (
    "run_ts", "market", "contract", "signal_close", "data_last_ts", "stale",
    "state", "side", "entry_ts", "entry_price", "sl", "tp", "cap_session_end",
    "unrealised_R", "exit_ts", "exit_reason", "net_R", "trade_signal_close",
    "plan_entry_ts", "reference_price", "atr", "sl_distance", "tp_distance",
    "plan_sl", "plan_tp", "refresh_error",
)
BACKTEST_LINE = "Backtest: DEV +0.16R per trade; final +0.04R on 88 trades."


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
    end = stamp.date()
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
    stale = is_stale(ts[-1], now)
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
    """Append unseen market/signal-close snapshots without rewriting history."""
    seen = set()
    if path.exists():
        with path.open(newline="") as handle:
            seen = {(row["market"], row["signal_close"]) for row in csv.DictReader(handle)}
    fresh = [row for row in records if (row["market"], row["signal_close"]) not in seen]
    if not fresh:
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not path.exists() or path.stat().st_size == 0
    with path.open("a", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=LOG_COLUMNS, lineterminator="\n")
        if write_header:
            writer.writeheader()
        writer.writerows(fresh)
    return len(fresh)


def run(data_root: Path = Path("data"), shadow_root: Path = Path("data/shadow"), *,
        now: pd.Timestamp | None = None, refresh: bool = True) -> str:
    now = pd.Timestamp.now(tz="UTC") if now is None else pd.Timestamp(now)
    now = now.tz_localize("UTC") if now.tzinfo is None else now.tz_convert("UTC")
    records, blocks = [], []
    start = now - pd.Timedelta(days=LOOKBACK_DAYS)
    for market in MARKETS:
        error = ""
        if refresh:
            try:
                refresh_market(data_root, market, now)
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
    message = ("Swing v1 SHADOW — no orders sent\n" + BACKTEST_LINE + "\n\n" +
               "\n\n".join(blocks) + f"\n\nAudit rows appended: {appended}.")
    shadow_root.mkdir(parents=True, exist_ok=True)
    (shadow_root / "swing_v1_latest.txt").write_text(message + "\n")
    return message


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--shadow-root", type=Path, default=Path("data/shadow"))
    parser.add_argument("--no-refresh", action="store_true", help="use local bars only")
    args = parser.parse_args()
    print(run(args.data_root, args.shadow_root, refresh=not args.no_refresh))


if __name__ == "__main__":
    main()
