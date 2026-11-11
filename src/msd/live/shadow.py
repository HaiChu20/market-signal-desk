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
from msd.live.signal_policy import SignalPolicy
from msd.live.telegram import TelegramClient
from msd.methods.common import exit_candidates
from msd.research.decision import choose

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
                  expected_net_R: float, valid_until=None, chase_band=None) -> str:
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
    deadline = valid_until if valid_until is not None else expiry
    valid = f" | valid until {pd.Timestamp(deadline).isoformat()}" if deadline is not None else ""
    band = (f" | don't chase outside {chase_band[0]:.2f}–{chase_band[1]:.2f}"
            if chase_band is not None else "")
    return (f"PAPER {symbol} | {'BUY' if side > 0 else 'SELL'} {entry_text} | SL {sl:.2f} | TP {tp:.2f}"
            f"{valid}{band} | Confidence {p:.1%} P(TP first) | Expected net R {expected_net_R:+.2f}"
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
        if not isinstance(policy, dict) or not {"side", "candidate_kind", "entry_type", "cost_R", "financing_R"} <= policy.keys():
            return None
        if (not np.isfinite([policy["cost_R"], policy["financing_R"]]).all() or
                float(policy["cost_R"]) < 0 or float(policy["financing_R"]) < 0):
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
                 output=print, policy: SignalPolicy | None = None, blackout=None,
                 clock=None, replay: bool = False):
        if symbol not in SYMBOLS:
            raise ValueError("public spot loop supports BTCUSDT and ETHUSDT")
        self.symbol = symbol
        self.online = OnlineFeatures(symbol, history)
        self.models = models or QualifiedModels()
        self.telegram = telegram or TelegramClient()
        self.output = output
        self.policy = policy or SignalPolicy()
        self.blackout = blackout or (lambda _symbol, _stamp: False)
        self.clock = clock or (lambda: pd.Timestamp.now(tz="UTC"))
        self.replay = replay
        self.connection = sqlite3.connect(state_path)
        self.connection.execute("CREATE TABLE IF NOT EXISTS candidates (symbol TEXT, method TEXT, ts TEXT, "
                                "event_json TEXT NOT NULL, message TEXT NOT NULL, status TEXT NOT NULL, "
                                "PRIMARY KEY(symbol, method, ts, event_json))")
        self.connection.execute("CREATE TABLE IF NOT EXISTS checkpoints (symbol TEXT PRIMARY KEY, ts TEXT NOT NULL)")
        self.connection.execute("CREATE TABLE IF NOT EXISTS bar_audit (symbol TEXT, ts TEXT, reason TEXT NOT NULL, "
                                "detail TEXT NOT NULL, signal TEXT, PRIMARY KEY(symbol, ts))")
        self.connection.execute("CREATE TABLE IF NOT EXISTS positions (symbol TEXT PRIMARY KEY, status TEXT NOT NULL, "
                                "side INTEGER NOT NULL, entry_type TEXT NOT NULL, entry_ts TEXT NOT NULL, "
                                "limit_price REAL, expiry_ts TEXT, stop REAL NOT NULL, tp REAL NOT NULL, "
                                "planned_end_ts TEXT NOT NULL, fill_ts TEXT, label_end_ts TEXT)")
        self.connection.commit()

    def last_timestamp(self):
        row = self.connection.execute("SELECT ts FROM checkpoints WHERE symbol=?", (self.symbol,)).fetchone()
        return pd.Timestamp(row[0]) if row else None

    def _advance_position(self, bar: dict):
        row = self.connection.execute("SELECT status,side,entry_type,entry_ts,limit_price,expiry_ts,stop,tp,"
                                      "planned_end_ts,fill_ts,label_end_ts FROM positions WHERE symbol=?",
                                      (self.symbol,)).fetchone()
        if row is None or row[-1] is not None:
            return
        status, side, entry_type, entry_ts, limit_price, expiry_ts, stop, tp, planned_end, fill_ts, _ = row
        ts = pd.Timestamp(bar["ts"])
        if ts < pd.Timestamp(entry_ts):
            return
        if status == "pending":
            if expiry_ts is not None and ts >= pd.Timestamp(expiry_ts):
                self.connection.execute("UPDATE positions SET status='expired',label_end_ts=? WHERE symbol=?",
                                        (ts.isoformat(), self.symbol))
                return
            filled = entry_type == "market" or (bar["ask_l"] <= limit_price if side > 0
                                                  else bar["bid_h"] >= limit_price)
            if not filled:
                return
            self.connection.execute("UPDATE positions SET status='filled',fill_ts=? WHERE symbol=?",
                                    (ts.isoformat(), self.symbol))
            fill_ts = ts.isoformat()
        low = float(bar["bid_l"] if side > 0 else bar["ask_l"])
        high = float(bar["bid_h"] if side > 0 else bar["ask_h"])
        stop_hit = low <= stop if side > 0 else high >= stop
        tp_hit = high >= tp if side > 0 else low <= tp
        # Limit fill bars activate the stop only; ambiguous later bars stop first.
        if stop_hit or (tp_hit and not (entry_type == "limit" and ts == pd.Timestamp(fill_ts))) or ts >= pd.Timestamp(planned_end):
            self.connection.execute("UPDATE positions SET status='closed',label_end_ts=? WHERE symbol=?",
                                    (ts.isoformat(), self.symbol))

    def _position_busy(self, ts: pd.Timestamp) -> bool:
        row = self.connection.execute("SELECT label_end_ts FROM positions WHERE symbol=?", (self.symbol,)).fetchone()
        return bool(row and (row[0] is None or ts <= pd.Timestamp(row[0])))

    def _edge_order(self, artifact, policy: dict, event: dict, features: pd.Series, levels: pd.DataFrame):
        if not {"candidate_sl_ATR", "candidate_tp_R"}.issubset(artifact.feature_dtypes):
            return None
        side = int(policy["side"])
        if side not in event.get("side_candidates", [event.get("side")]):
            return None
        if policy["entry_type"] != event.get("entry_type", "market"):
            return None
        atr = float(features.get("1m_atr14", np.nan))
        if not np.isfinite(atr) or atr <= 0:
            return None
        entry = float(event.get("limit_price", event["price"]))
        oriented = {**event, "side": side}
        rows = []
        by_kind = {}
        for candidate in exit_candidates(oriented, levels, atr):
            sl, tp = candidate["sl"], candidate["tp"]
            if sl is None or tp is None or not np.isfinite([sl, tp]).all():
                continue
            risk = abs(entry - sl)
            if risk <= 0 or side * (entry - sl) <= 0 or side * (tp - entry) <= 0:
                continue
            enriched = features.copy()
            enriched["candidate_sl_ATR"] = risk / atr
            enriched["candidate_tp_R"] = abs(tp - entry) / risk
            p = artifact.probability(enriched)
            rows.append({"event_key": "current", "kind": candidate["kind"], "p": p,
                         "TP_R": enriched["candidate_tp_R"], "price": entry, "sl": sl,
                         "cost_R": float(policy["cost_R"]),
                         "financing_R": float(policy["financing_R"])})
            by_kind[candidate["kind"]] = enriched
        if len(rows) < 3:
            return None
        selected = choose(pd.DataFrame(rows), threshold=self.policy.edge_threshold)
        if selected.empty or selected.iloc[0]["kind"] != policy["candidate_kind"]:
            return None
        chosen = selected.iloc[0]
        enriched = by_kind[chosen["kind"]]
        order = order_from_event(artifact, enriched, event, levels, side=side,
                                 candidate_kind=chosen["kind"], min_probability=0,
                                 entry_type=policy["entry_type"],
                                 limit_price=event.get("limit_price"), expiry_ts=event.get("expiry_at"))
        expected = float(np.interp(order["confidence"], artifact.calibration["calibrated"],
                                   artifact.calibration["expected_net_R"]))
        if expected <= self.policy.edge_threshold:
            return None
        return order, expected

    def process(self, bar: dict):
        stamp = pd.Timestamp(bar["ts"])
        last = self.last_timestamp()
        if last is not None and stamp <= last:
            return []
        if last is not None and stamp != last + pd.Timedelta(minutes=1):
            raise ValueError("missing completed bar before signal evaluation")
        result = self.online.update(bar)
        self._advance_position(bar)
        data_detail = self.policy.data_reason(self.online.bars, self.clock(), replay=self.replay)
        messages = []
        reasons = []
        emitted = None
        for event in result.events:
            method = event["method"]
            sides = event.get("side_candidates", [event.get("side")])
            side_text = "/".join("BUY" if side == 1 else "SELL" for side in sides)
            message = (f"PRELIMINARY {self.symbol} | {side_text} candidate near {float(event['price']):.2f}"
                       f" | {method} | {pd.Timestamp(event['known_at']).isoformat()}")
            status = "PRELIMINARY"
            if data_detail:
                reasons.append("data")
            elif emitted is not None:
                reasons.append("position")
            else:
                model = self.models.get(self.symbol, method)
                if model is None:
                    reasons.append("model")
                else:
                    artifact, model_policy = model
                    decision = self._edge_order(artifact, model_policy, event,
                                                result.features, result.levels)
                    if decision is None:
                        reasons.append("edge")
                    elif self._position_busy(stamp):
                        reasons.append("position")
                    elif self.blackout(self.symbol, stamp):
                        reasons.append("blackout")
                    else:
                        order, expected_net_R = decision
                        entry_ts = stamp + pd.Timedelta(minutes=2)
                        valid_until = entry_ts + pd.Timedelta(minutes=self.policy.valid_minutes)
                        if order.get("expiry_ts") is not None:
                            valid_until = min(valid_until, pd.Timestamp(order["expiry_ts"]))
                        atr = float(result.features["1m_atr14"])
                        signal_price = float(event["price"])
                        band = (signal_price - self.policy.chase_atr * atr,
                                signal_price + self.policy.chase_atr * atr)
                        message = format_signal(self.symbol, event, order,
                                                model_version=artifact.config_hash,
                                                expected_net_R=expected_net_R,
                                                valid_until=valid_until, chase_band=band)
                        status = "EMITTED"
                        emitted = message
                        reasons.append("emitted")
                        self.connection.execute("INSERT OR REPLACE INTO positions VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                                                (self.symbol, "pending", int(order["side"]), order["entry_type"],
                                                 entry_ts.isoformat(), order.get("entry_price"),
                                                 pd.Timestamp(order["expiry_ts"]).isoformat()
                                                 if order.get("expiry_ts") is not None else None,
                                                 float(order["stop"]), float(order["tp"]),
                                                 (entry_ts + pd.Timedelta(minutes=self.policy.max_hold_minutes)).isoformat(),
                                                 None, None))
            serialized = json.dumps(event, default=_json_default, sort_keys=True)
            cursor = self.connection.execute("INSERT OR IGNORE INTO candidates VALUES (?,?,?,?,?,?)",
                                             (self.symbol, method, stamp.isoformat(), serialized, message, status))
            if cursor.rowcount:
                messages.append(message)
        reason = ("data" if data_detail else "no_setup" if not result.events else
                  next((code for code in ("emitted", "blackout", "position", "edge", "model")
                        if code in reasons), "model"))
        audit = {"symbol": self.symbol, "ts": stamp.isoformat(), "reason": reason,
                 "detail": data_detail or "", "events": len(result.events)}
        if emitted is not None:
            audit["signal"] = emitted
        new_audit = self.connection.execute("INSERT OR IGNORE INTO bar_audit VALUES (?,?,?,?,?)",
                                            (self.symbol, stamp.isoformat(), reason, audit["detail"], emitted)).rowcount
        self.connection.execute("INSERT INTO checkpoints VALUES (?,?) ON CONFLICT(symbol) DO UPDATE SET ts=excluded.ts",
                                (self.symbol, stamp.isoformat()))
        self.connection.commit()
        if new_audit:
            self.output(json.dumps(audit, sort_keys=True))
        if emitted is not None and self.telegram.credentials_present:
            self.telegram.send_message(emitted)
        return messages

    def close(self):
        self.connection.close()


def run(symbols=SYMBOLS, *, state_path=DEFAULT_STATE, heartbeat=HEARTBEAT,
        policy: SignalPolicy | None = None):
    """Seed a causal warmup, then stream only newly closed minutes."""
    import threading
    state_path = Path(state_path)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    heartbeat = Path(heartbeat)
    heartbeat.parent.mkdir(parents=True, exist_ok=True)
    policy = policy or SignalPolicy()
    stop = threading.Event()

    def worker(symbol):
        feed = BinanceSpotFeed(symbol)
        now = pd.Timestamp.now(tz="UTC")
        history = feed.backfill(now - pd.Timedelta(minutes=policy.warmup_minutes + 1), now=now)
        if not history:
            raise RuntimeError(f"no completed Binance bars for {symbol}")
        loop = ShadowLoop(symbol, state_path, history=pd.DataFrame(history[:-1]), policy=policy)
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
    parser.add_argument("--warmup-minutes", type=int, default=SignalPolicy.warmup_minutes)
    parser.add_argument("--spread-low-percentile", type=float, default=SignalPolicy.spread_low_percentile)
    parser.add_argument("--spread-high-percentile", type=float, default=SignalPolicy.spread_high_percentile)
    parser.add_argument("--valid-minutes", type=int, default=SignalPolicy.valid_minutes)
    parser.add_argument("--chase-atr", type=float, default=SignalPolicy.chase_atr)
    args = parser.parse_args()
    policy = SignalPolicy(warmup_minutes=args.warmup_minutes,
                          spread_low_percentile=args.spread_low_percentile,
                          spread_high_percentile=args.spread_high_percentile,
                          valid_minutes=args.valid_minutes, chase_atr=args.chase_atr)
    run(args.symbols, state_path=args.state, policy=policy)


if __name__ == "__main__":
    main()
