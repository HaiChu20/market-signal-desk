"""Public Binance spot trades and best quotes aggregated into closed minute bars."""
from __future__ import annotations

import json
import time
from urllib.parse import urlencode
from urllib.request import urlopen

import numpy as np
import pandas as pd
from websockets.exceptions import ConnectionClosed
from websockets.sync.client import connect

SYMBOLS = ("BTCUSDT", "ETHUSDT")
REST = "https://data-api.binance.vision/api/v3/klines"
WS = "wss://stream.binance.com:9443/stream?streams={}@trade/{}@bookTicker"
FIELDS = ("o", "h", "l", "c")


class BinanceMinuteBarBuilder:
    """Build executable bid/ask OHLC from Level 1 quotes and trade volume."""
    def __init__(self):
        self.minute = None
        self.row = None
        self.last_quote = None

    def _start(self, minute):
        self.minute = minute
        self.row = {"ts": minute, "volume": 0.0, "quote_volume": 0.0,
                    "trades": 0, "taker_buy_base": 0.0, "taker_buy_quote": 0.0}
        if self.last_quote is not None:
            self._quote("bid", self.last_quote[0])
            self._quote("ask", self.last_quote[1])

    def _quote(self, side: str, price: float):
        for field in FIELDS:
            key = f"{side}_{field}"
            if field == "o" and key not in self.row:
                self.row[key] = price
            elif field == "h":
                self.row[key] = max(self.row.get(key, price), price)
            elif field == "l":
                self.row[key] = min(self.row.get(key, price), price)
            elif field == "c":
                self.row[key] = price

    def update(self, event: dict, *, received_at) -> list[dict]:
        kind = event.get("e")
        if kind == "trade":
            stamp = pd.Timestamp(int(event["T"]), unit="ms", tz="UTC")
        elif "b" in event and "a" in event:
            stamp = pd.Timestamp(received_at)
            stamp = stamp.tz_localize("UTC") if stamp.tzinfo is None else stamp.tz_convert("UTC")
        else:
            return []
        minute = stamp.floor("min")
        closed = []
        if self.minute is None:
            self._start(minute)
        elif minute > self.minute:
            if all(f"{side}_{field}" in self.row for side in ("bid", "ask") for field in FIELDS):
                closed.append(dict(self.row))
            self._start(minute)
        elif minute < self.minute:
            return []
        if kind == "trade":
            quantity = float(event["q"])
            quote = quantity * float(event["p"])
            self.row["volume"] += quantity
            self.row["quote_volume"] += quote
            self.row["trades"] += 1
            if not bool(event.get("m", False)):
                self.row["taker_buy_base"] += quantity
                self.row["taker_buy_quote"] += quote
        else:
            bid, ask = float(event["b"]), float(event["a"])
            if not np.isfinite([bid, ask]).all() or bid <= 0 or ask <= bid:
                raise ValueError("invalid Binance best bid/ask")
            self._quote("bid", bid)
            self._quote("ask", ask)
            self.last_quote = (bid, ask)
        return closed


def parse_kline(values) -> dict:
    """Spot OHLC is single price; bid/ask remain equal until a spread model is applied."""
    if isinstance(values, dict):
        opened = values["t"]
        prices = {field: float(values[field]) for field in FIELDS}
        volume = float(values["v"])
        extras = {"quote_volume": float(values["q"]), "trades": int(values["n"]),
                  "taker_buy_base": float(values["V"]), "taker_buy_quote": float(values["Q"])}
    else:
        opened = values[0]
        prices = dict(zip(FIELDS, map(float, values[1:5])))
        volume = float(values[5])
        extras = {"quote_volume": float(values[7]), "trades": int(values[8]),
                  "taker_buy_base": float(values[9]), "taker_buy_quote": float(values[10])}
    row = {"ts": pd.Timestamp(int(opened), unit="ms", tz="UTC"), "volume": volume, **extras}
    for side in ("bid", "ask"):
        for field in FIELDS:
            row[f"{side}_{field}"] = prices[field]
    return row


class BinanceSpotFeed:
    def __init__(self, symbol: str, *, opener=urlopen, connector=connect, clock=time.time):
        if symbol not in SYMBOLS:
            raise ValueError(f"unsupported public spot symbol: {symbol}")
        self.symbol, self.opener, self.connector, self.clock = symbol, opener, connector, clock

    def backfill(self, after: pd.Timestamp | None, *, now: pd.Timestamp | None = None,
                 limit: int = 1000) -> list[dict]:
        """Fetch all missing completed minutes, paging when the gap exceeds 1000."""
        cutoff = pd.Timestamp(now) if now is not None else pd.Timestamp(self.clock(), unit="s", tz="UTC")
        cutoff = cutoff.tz_localize("UTC") if cutoff.tzinfo is None else cutoff.tz_convert("UTC")
        complete_before = cutoff.floor("min")
        cursor = None if after is None else pd.Timestamp(after).floor("min") + pd.Timedelta(minutes=1)
        if cursor is not None:
            cursor = cursor.tz_localize("UTC") if cursor.tzinfo is None else cursor.tz_convert("UTC")
            after = cursor - pd.Timedelta(minutes=1)
        output = []
        while cursor is None or cursor < complete_before:
            query = {"symbol": self.symbol, "interval": "1m", "limit": min(limit, 1000)}
            if cursor is not None:
                query["startTime"] = int(cursor.timestamp() * 1000)
            with self.opener(f"{REST}?{urlencode(query)}", timeout=20) as response:
                batch = json.loads(response.read())
            if not isinstance(batch, list) or not batch:
                break
            rows = [parse_kline(item) for item in batch]
            fresh = [row for row in rows if row["ts"] < complete_before and
                     (after is None or row["ts"] > after)]
            if cursor is not None and fresh and fresh[0]["ts"] != cursor:
                raise RuntimeError("Binance REST backfill has a minute gap")
            if any(right["ts"] != left["ts"] + pd.Timedelta(minutes=1)
                   for left, right in zip(fresh, fresh[1:])):
                raise RuntimeError("Binance REST backfill has an internal minute gap")
            output.extend(fresh)
            next_cursor = rows[-1]["ts"] + pd.Timedelta(minutes=1)
            if next_cursor >= complete_before or len(batch) < query["limit"]:
                break
            if cursor is not None and next_cursor <= cursor:
                raise RuntimeError("Binance backfill did not advance")
            cursor = next_cursor
        return sorted({row["ts"]: row for row in output}.values(), key=lambda row: row["ts"])

    def stream(self, on_closed, *, last: pd.Timestamp | None = None,
               stop=None, retry_seconds: float = 5.0):
        """Reconnect after transport failures; REST fills every closed-bar gap."""
        while stop is None or not stop.is_set():
            try:
                for row in self.backfill(last):
                    on_closed(row)
                    last = row["ts"]
                name = self.symbol.lower()
                builder = BinanceMinuteBarBuilder()
                with self.connector(WS.format(name, name), open_timeout=20) as socket:
                    while stop is None or not stop.is_set():
                        message = json.loads(socket.recv(timeout=70))
                        # Compatibility with recorded kline fixtures; production
                        # uses only the combined trade and bookTicker streams.
                        kline = message.get("k") or {}
                        if kline:
                            rows = [parse_kline(kline)] if kline.get("x") else []
                        else:
                            event = message.get("data", message)
                            received = pd.Timestamp(self.clock(), unit="s", tz="UTC")
                            rows = builder.update(event, received_at=received)
                        for row in rows:
                            if last is not None and row["ts"] <= last:
                                continue
                            # A reconnect can skip minutes even if the socket resumes.
                            if last is not None and row["ts"] > last + pd.Timedelta(minutes=1):
                                for missing in self.backfill(last):
                                    if missing["ts"] >= row["ts"]:
                                        break
                                    on_closed(missing)
                                    last = missing["ts"]
                                if row["ts"] != last + pd.Timedelta(minutes=1):
                                    raise RuntimeError("Binance websocket gap remains after REST backfill")
                            on_closed(row)
                            last = row["ts"]
            except (OSError, TimeoutError, ValueError, RuntimeError, ConnectionClosed):
                if stop is not None and stop.is_set():
                    return
                time.sleep(retry_seconds)


class CapitalIndexFeed:
    """Broker Level 1 interface placeholder; construction never logs in."""
    def stream(self, *_args, **_kwargs):
        raise NotImplementedError("Index live feed awaits Capital.com credentials and review")
