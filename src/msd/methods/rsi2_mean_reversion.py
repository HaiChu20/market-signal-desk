"""#39 RSI(2): emit a causal event on the first available feature row that
observes a newly completed daily bar, when daily RSI(2) < 10 and the close is
above daily EMA(200). For indices, the CME daily bar closes at 17:00 ET, but
Dukascopy has a quote gap before that close; the event therefore appears on the
first bar after the gap, and its usual two-bar-delayed entry is at the reopen.
At most one event per instrument-day; it is long-only.
"""
from __future__ import annotations

import pandas as pd

NAME = "rsi2_mean_reversion"
SYMBOLS = ("USATECHIDXUSD", "USA500IDXUSD")
RSI_PERIOD = 2
RSI_THRESHOLD = 10.0


def detect(features: pd.DataFrame, levels: pd.DataFrame, bars: pd.DataFrame) -> list[dict]:
    if features.empty:
        return []
    columns = set(features.columns)
    rsi = f"1d_rsi{RSI_PERIOD}" if f"1d_rsi{RSI_PERIOD}" in columns else f"rsi{RSI_PERIOD}"
    ema = "1d_ema200_distance_atr" if "1d_ema200_distance_atr" in columns else None
    if rsi not in columns or ema is None:
        return []
    daily_close = "1d_bar_known_at"
    if daily_close not in columns:
        return []
    completed = features[daily_close]
    new_daily_bar = completed.notna() & completed.ne(completed.shift())
    selected = features[new_daily_bar & (features[rsi] < RSI_THRESHOLD) & (features[ema] > 0)]
    selected = selected.merge(bars[["ts", "bid_c", "ask_c"]], on="ts", how="left", validate="one_to_one")
    return [{"ts": row.ts, "sym": "", "side": 1, "price": float((row.bid_c+row.ask_c)/2),
             "natural_sl": None, "natural_tp": None, "method": NAME, "known_at": row.known_at}
            for row in selected.itertuples(index=False)]

from .requirements import required_features, market_for
REQUIRED_FEATURES = required_features(NAME)
MARKETS = market_for(NAME)
