"""Chronological one-position-per-symbol gate for executable candidates."""
from __future__ import annotations

import pandas as pd


def gate_open_signals(signals: pd.DataFrame) -> pd.DataFrame:
    """Admit an entry only after the previous label window closes plus one minute."""
    if signals.empty:
        return signals.copy()
    selected = []
    next_open: dict[str, pd.Timestamp] = {}
    for index, row in signals.sort_values(["known_at", "event_key"]).iterrows():
        symbol = str(row.sym)
        known = pd.Timestamp(row.known_at)
        known = known.tz_localize("UTC") if known.tzinfo is None else known.tz_convert("UTC")
        if known < next_open.get(symbol, pd.Timestamp.min.tz_localize("UTC")):
            continue
        close = pd.Timestamp(row.label_end_ts)
        close = close.tz_localize("UTC") if close.tzinfo is None else close.tz_convert("UTC")
        selected.append(index)
        next_open[symbol] = close + pd.Timedelta(minutes=1)
    return signals.loc[selected].reset_index(drop=True)
