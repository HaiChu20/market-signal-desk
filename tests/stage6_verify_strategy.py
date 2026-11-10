"""Test-only causal breakout used by the local verify-live acceptance run."""
from __future__ import annotations

import numpy as np
import pandas as pd

NAME = "stage6_verify_breakout60"
SYMBOLS = ("USATECHIDXUSD",)
RESOLUTION = "MINUTE"
LOOKBACK = 60
MAX_HOLD = pd.Timedelta(hours=4)
WARMUP = pd.Timedelta(hours=6)
_CACHE = {"first": None, "last": None, "length": 0, "orders": [], "locked_until": None, "tail_hash": None}


def _full( bars: pd.DataFrame) -> list[dict]:
    high, low, close = (bars[f"bid_{field}"].to_numpy(float) for field in ("h", "l", "c"))
    result, locked_until = [], None
    for i in range(LOOKBACK, len(bars)):
        decision = bars.ts.iloc[i]
        resistance = float(high[i-LOOKBACK:i].max())
        if close[i] <= resistance or close[i-1] > resistance:
            continue
        stop = float(low[i-LOOKBACK:i].min())
        if stop >= close[i] or (locked_until is not None and decision < locked_until):
            continue
        risk = close[i] - stop
        deadline = decision + MAX_HOLD
        path, trailing = {}, stop
        for j in range(i + 1, min(len(bars), i + 1 + int(MAX_HOLD / pd.Timedelta(minutes=1)))):
            if bars.ts.iloc[j] >= deadline:
                break
            trailing = max(trailing, float(low[j-LOOKBACK:j].min()))
            path[bars.ts.iloc[j]] = trailing
        result.append({"decision_ts": decision, "side": 1, "stop": stop,
                       "tp": close[i] + 2 * risk, "exit_ts": deadline,
                       "stop_path": path, "note": "test breakout"})
        locked_until = deadline
    return result


def orders(bars: pd.DataFrame) -> list[dict]:
    """Incremental test implementation; results equal recomputing the same prefix."""
    if bars.empty:
        return []
    tail_hash = int(pd.util.hash_pandas_object(bars.tail(8), index=False).sum())
    first, last, length = bars.ts.iloc[0], bars.ts.iloc[-1], len(bars)
    if (_CACHE["first"] == first and _CACHE["last"] == last and _CACHE["length"] == length
            and _CACHE["tail_hash"] == tail_hash):
        return _CACHE["orders"]
    can_extend = (_CACHE["first"] == first and length > _CACHE["length"]
                  and _CACHE["length"] > LOOKBACK
                  and bars.ts.iloc[_CACHE["length"] - 1] == _CACHE["last"]
                  and _CACHE["tail_hash"] == int(pd.util.hash_pandas_object(
                      bars.iloc[_CACHE["length"]-8:_CACHE["length"]].tail(8), index=False).sum()))
    if not can_extend:
        result = _full(bars)
        locked = result[-1]["exit_ts"] if result else None
    else:
        result = [dict(order, stop_path=dict(order["stop_path"])) for order in _CACHE["orders"]]
        locked = _CACHE["locked_until"]
        high = bars.bid_h.to_numpy(float)
        low = bars.bid_l.to_numpy(float)
        close = bars.bid_c.to_numpy(float)
        for j in range(_CACHE["length"] - 1, len(bars)):
            stamp = bars.ts.iloc[j]
            for order in result:
                if order["decision_ts"] < stamp < order["exit_ts"]:
                    previous = max([float(order["stop"]), *map(float, order["stop_path"].values())])
                    candidate = float(low[j-LOOKBACK:j].min()) if j >= LOOKBACK else float("nan")
                    if np.isfinite(candidate):
                        order["stop_path"][stamp] = max(previous, candidate)
            if j < LOOKBACK:
                continue
            resistance = float(high[j-LOOKBACK:j].max())
            if close[j] <= resistance or close[j-1] > resistance:
                continue
            stop = float(low[j-LOOKBACK:j].min())
            if stop >= close[j] or (locked is not None and stamp < locked):
                continue
            risk = close[j] - stop
            deadline = stamp + MAX_HOLD
            result.append({"decision_ts": stamp, "side": 1, "stop": stop,
                           "tp": close[j] + 2 * risk, "exit_ts": deadline,
                           "stop_path": {}, "note": "test breakout"})
            locked = deadline
    _CACHE.update(first=first, last=last, length=length, orders=result,
                  locked_until=locked, tail_hash=tail_hash)
    return result
