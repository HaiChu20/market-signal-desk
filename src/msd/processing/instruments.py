"""Measured Stage 9 session and label specifications.

Session endpoints are empirical quote-window endpoints from completed local
Dukascopy months.  They are deliberately separate from exchange marketing
hours: HTF bars must not bridge recurring vendor no-quote windows.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class InstrumentSpec:
    timezone: str
    session_open_minute: int | None
    session_close_minute: int | None
    label_class: str
    financing_per_night: float
    measured_through: str | None
    point_scale: int | None

    @property
    def session_ready(self) -> bool:
        return self.session_open_minute is not None and self.session_close_minute is not None


STAGE9_INSTRUMENTS: dict[str, InstrumentSpec] = {
    "USA30IDXUSD": InstrumentSpec("America/New_York", 18 * 60, 16 * 60 + 15, "index", .0002, "2026-10", 1000),
    "DEUIDXEUR": InstrumentSpec("Europe/Berlin", 0, 22 * 60 + 15, "index", .0002, "2026-10", 1000),
    "GBRIDXGBP": InstrumentSpec("Europe/London", 23 * 60, 21 * 60 + 15, "index", .0002, "2024-12", 1000),
    # No completed local month exists yet.  Keeping the endpoint unset makes a
    # premature production build fail rather than borrowing another index's hours.
    "JPNIDXJPY": InstrumentSpec("Asia/Tokyo", None, None, "index", .0002, None, None),
    "XAGUSD": InstrumentSpec("America/New_York", 18 * 60, 17 * 60, "metal", .00015, "2026-10", 1000),
    "EURUSD": InstrumentSpec("America/New_York", 17 * 60, 17 * 60, "fx", .00015, "2026-10", 100000),
    "USDJPY": InstrumentSpec("America/New_York", 17 * 60, 17 * 60, "fx", .00015, "2026-10", 1000),
    "GBPUSD": InstrumentSpec("America/New_York", 17 * 60, 17 * 60, "fx", .00015, "2026-10", 100000),
    "LIGHTCMDUSD": InstrumentSpec("America/New_York", 18 * 60, 17 * 60, "energy", .0002, "2026-10", 1000),
    "BRENTCMDUSD": InstrumentSpec("Europe/London", 0, 22 * 60, "energy", .0002, "2026-10", 1000),
}


def instrument_spec(symbol: str) -> InstrumentSpec:
    return STAGE9_INSTRUMENTS[symbol]


def label_parameters(symbol: str) -> tuple[str, float]:
    spec = instrument_spec(symbol)
    # The current kernel uses weekday deadlines/17:00-NY financing boundaries
    # for every non-crypto class.  The descriptive class remains available for
    # later class-specific financing without changing the Stage 9 config.
    return spec.label_class, spec.financing_per_night


def active_session_mask(timestamps: pd.Series, symbol: str) -> np.ndarray:
    """DST-aware measured quote-session mask, including weekday closure."""
    spec = instrument_spec(symbol)
    if not spec.session_ready:
        raise ValueError(f"{symbol} session is pending measurement from a completed local month")
    local = pd.to_datetime(timestamps, utc=True).dt.tz_convert(spec.timezone)
    minute = local.dt.hour * 60 + local.dt.minute
    opened, closed = int(spec.session_open_minute), int(spec.session_close_minute)
    if opened == closed:
        open_day = pd.to_datetime(local.dt.date) - pd.to_timedelta((minute < opened).astype(int), unit="D")
    elif opened < closed:
        active = (minute >= opened) & (minute < closed)
        open_day = pd.to_datetime(local.dt.date)
    else:
        active = (minute >= opened) | (minute < closed)
        open_day = pd.to_datetime(local.dt.date) - pd.to_timedelta((minute < closed).astype(int), unit="D")
    duration = 1440 if opened == closed else (closed - opened) % 1440
    trade_day = (open_day + pd.Timedelta(minutes=opened + duration)).dt.day_of_week
    return (active & trade_day.lt(5)).to_numpy() if opened != closed else trade_day.lt(5).to_numpy()


def session_trade_dates(timestamps: pd.Series, symbol: str) -> np.ndarray:
    """Local trade date for event-volume accounting."""
    spec = instrument_spec(symbol)
    if not spec.session_ready:
        raise ValueError(f"{symbol} session is pending measurement from a completed local month")
    local = pd.to_datetime(timestamps, utc=True).dt.tz_convert(spec.timezone)
    minute = local.dt.hour * 60 + local.dt.minute
    opened, closed = int(spec.session_open_minute), int(spec.session_close_minute)
    local_day = pd.to_datetime(local.dt.date)
    if opened == closed:
        open_day = local_day - pd.to_timedelta((minute < opened).astype(int), unit="D")
        duration = 1440
    elif opened < closed:
        open_day, duration = local_day, closed - opened
    else:
        open_day = local_day - pd.to_timedelta((minute < closed).astype(int), unit="D")
        duration = 1440 - opened + closed
    return (open_day + pd.Timedelta(minutes=opened + duration)).to_numpy().astype("datetime64[D]")
