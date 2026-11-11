"""Public spot close-of-bar signal loop. Ungraded methods remain shadow-only."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
import time

import numpy as np
import pandas as pd

from msd.live.binance import BinanceSpotFeed, SYMBOLS
from msd.live.model_serving import load_artifact, order_from_event
from msd.live.online_features import OnlineFeatures
from msd.live.telegram import TelegramClient

QUALIFIED_GRADES = {"✅", "🧪"}
DEFAULT_STATE = Path("data/live/shadow.sqlite3")
HEARTBEAT = Path("data/live/heartbeat")


def _json_default(value):
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, np.generic):
        return value.item()
    raise TypeError(f"cannot serialize {type(value).__name__}")


def format_signal(symbol: str, event: dict, order: dict, *, model_version: str,
                  expected_net_R: float) -> str:
    """Show calibrated TP-first probability and separately modeled net return."""
    p = float(order["confidence"])
    side = int(order["side"])
    entry = float(order["entry_price"] if order["entry_type"] == "limit" else event["price"])
    sl, tp = float(order["stop"]), float(order["tp"])
    if not (0 <= p <= 1 and abs(entry - sl) > 0 and
            np.isfinite([entry, sl, tp, expected_net_R]).all()):
        raise ValueError("invalid executable signal")
    entry_text = (f"LIMIT {entry:.2f}"
                  if order["entry_type"] == "limit" else f"MARKET ~{entry:.2f}")
    expiry = order.get("expiry_ts")
    valid = f" | valid until {pd.Timestamp(expiry).isoformat()}" if expiry is not None else ""
    return (f"{symbol} | {'BUY' if side > 0 else 'SELL'} {entry_text} | SL {sl:.2f} | TP {tp:.2f}"
            f"{valid} | Confidence {p:.1%} P(TP first) | Expected net R {expected_net_R:+.2f}"
            f" | {event['method']} | model {model_version}")


class QualifiedModels:
    """Fail closed: artifact and independent report card must both be present."""
    def __init__(self, root: Path = Path("models/live")):
        self.root = Path(root)
        self._models = {}

    def get(self, symbol: str, method: str):
        key = (symbol, method)
        if key in self._models:
            return self._models[key]
        directory = self.root / symbol / method
        card_path = directory / "report_card.json"
        manifest_path = directory / "manifest.json"
        if not (card_path.exists() and manifest_path.exists()):
            return None
        card = json.loads(card_path.read_text())
        if card.get("grade") not in QUALIFIED_GRADES or card.get("method") != method or card.get("symbol") != symbol:
            return None
        manifest = json.loads(manifest_path.read_text())
        policy = manifest.get("live_policy")
        if not isinstance(policy, dict) or not {"side", "candidate_kind", "entry_type"} <= policy.keys():
            return None
        artifact = load_artifact(directory)
        grid = artifact.calibration.get("expected_net_R")
        calibrated = artifact.calibration["calibrated"]
        if (not isinstance(grid, list) or len(grid) != len(calibrated) or
                not np.isfinite(grid).all() or any(a >= b for a, b in zip(calibrated, calibrated[1:]))):
            return None
        if card.get("config_hash") != artifact.config_hash:
            return None
        self._models[key] = (artifact, policy)
        return self._models[key]


class ShadowLoop:
    """Replayable candidate logger; only qualified models may send alerts."""
    def __init__(self, symbol: str, state_path: Path, *, history: pd.DataFrame | None = None,
                 models: QualifiedModels | None = None, telegram: TelegramClient | None = None,
                 output=print):
        if symbol not in SYMBOLS:
            raise ValueError("public spot loop supports BTCUSDT and ETHUSDT")
        self.symbol = symbol
        self.online = OnlineFeatures(symbol, history)
        self.models = models or QualifiedModels()
        self.telegram = telegram or TelegramClient()
        self.output = output
        self.connection = sqlite3.connect(state_path)
        self.connection.execute("CREATE TABLE IF NOT EXISTS candidates (symbol TEXT, method TEXT, ts TEXT, "
                                "event_json TEXT NOT NULL, message TEXT NOT NULL, status TEXT NOT NULL, "
                                "PRIMARY KEY(symbol, method, ts, event_json))")
        self.connection.execute("CREATE TABLE IF NOT EXISTS checkpoints (symbol TEXT PRIMARY KEY, ts TEXT NOT NULL)")
        self.connection.commit()

    def last_timestamp(self):
        row = self.connection.execute("SELECT ts FROM checkpoints WHERE symbol=?", (self.symbol,)).fetchone()
        return pd.Timestamp(row[0]) if row else None

    def process(self, bar: dict):
        stamp = pd.Timestamp(bar["ts"])
        last = self.last_timestamp()
        if last is not None and stamp <= last:
            return []
        if last is not None and stamp != last + pd.Timedelta(minutes=1):
            raise ValueError("missing completed bar before signal evaluation")
        result = self.online.update(bar)
        messages = []
        dispatch = []
        for event in result.events:
            method = event["method"]
            model = self.models.get(self.symbol, method)
            status = "PRELIMINARY"
            if model is None:
                # A candidate is an offline detector event, not a predicted trade.
                sides = event.get("side_candidates", [event.get("side")])
                side_text = "/".join("BUY" if side == 1 else "SELL" for side in sides)
                message = (f"PRELIMINARY {self.symbol} | {side_text} candidate near {float(event['price']):.2f}"
                           f" | {method} | {pd.Timestamp(event['known_at']).isoformat()}"
                           " | no qualified model")
            else:
                artifact, policy = model
                side = int(policy["side"])
                if policy["entry_type"] != event.get("entry_type", "market"):
                    raise ValueError("qualified model entry policy conflicts with detector event")
                order = order_from_event(artifact, result.features, event, result.levels,
                                         side=side, candidate_kind=policy["candidate_kind"],
                                         entry_type=policy["entry_type"],
                                         limit_price=event.get("limit_price"), expiry_ts=event.get("expiry_at"))
                if order is None:
                    continue
                expected_net_R = float(np.interp(order["confidence"], artifact.calibration["calibrated"],
                                                 artifact.calibration["expected_net_R"]))
                message = format_signal(self.symbol, event, order, model_version=artifact.config_hash,
                                        expected_net_R=expected_net_R)
                status = "QUALIFIED"
            serialized = json.dumps(event, default=_json_default, sort_keys=True)
            cursor = self.connection.execute("INSERT OR IGNORE INTO candidates VALUES (?,?,?,?,?,?)",
                                             (self.symbol, method, stamp.isoformat(), serialized, message, status))
            if cursor.rowcount:
                messages.append(message)
                dispatch.append((status, message))
        self.connection.execute("INSERT INTO checkpoints VALUES (?,?) ON CONFLICT(symbol) DO UPDATE SET ts=excluded.ts",
                                (self.symbol, stamp.isoformat()))
        self.connection.commit()
        for status, message in dispatch:
            self.output(message)
            if status == "QUALIFIED" and self.telegram.credentials_present:
                self.telegram.send_message(message)
        return messages

    def close(self):
        self.connection.close()


def run(symbols=SYMBOLS, *, state_path=DEFAULT_STATE, heartbeat=HEARTBEAT):
    """Seed a causal warmup, then stream only newly closed minutes."""
    import threading
    state_path = Path(state_path)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    heartbeat = Path(heartbeat)
    heartbeat.parent.mkdir(parents=True, exist_ok=True)
    stop = threading.Event()

    def worker(symbol):
        feed = BinanceSpotFeed(symbol)
        now = pd.Timestamp.now(tz="UTC")
        # Seven days supplies the current shadow warmup; a qualified production
        # model should only be enabled after its own training-window audit.
        history = feed.backfill(now - pd.Timedelta(days=7), now=now)
        if not history:
            raise RuntimeError(f"no completed Binance bars for {symbol}")
        loop = ShadowLoop(symbol, state_path, history=pd.DataFrame(history[:-1]))
        last = loop.last_timestamp()
        if last is None:
            loop.process(history[-1])
            last = history[-1]["ts"]
        else:
            if last < history[0]["ts"] - pd.Timedelta(minutes=1):
                raise RuntimeError(f"saved {symbol} checkpoint is older than REST warmup")
            # Restore exactly the historical prefix through the checkpoint.
            loop.online = OnlineFeatures(symbol, pd.DataFrame([row for row in history if row["ts"] <= last]))
            for row in history:
                if row["ts"] > last:
                    loop.process(row)
            last = loop.last_timestamp()
        try:
            feed.stream(loop.process, last=last, stop=stop)
        finally:
            loop.close()

    threads = [threading.Thread(target=worker, args=(symbol,), daemon=True) for symbol in symbols]
    for thread in threads:
        thread.start()
    try:
        while all(thread.is_alive() for thread in threads):
            heartbeat.write_text(pd.Timestamp.now(tz="UTC").isoformat())
            time.sleep(30)
    except KeyboardInterrupt:
        stop.set()
    if any(not thread.is_alive() for thread in threads) and not stop.is_set():
        raise RuntimeError("Binance shadow worker stopped")
    for thread in threads:
        thread.join(timeout=10)


def main():
    parser = argparse.ArgumentParser(description="Public Binance closed-bar shadow signal loop")
    parser.add_argument("--symbols", nargs="+", choices=SYMBOLS, default=list(SYMBOLS))
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    args = parser.parse_args()
    run(args.symbols, state_path=args.state)


if __name__ == "__main__":
    main()
