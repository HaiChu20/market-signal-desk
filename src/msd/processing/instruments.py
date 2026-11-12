"""Measured Stage 9 session and label specifications.

Session endpoints are empirical quote-window endpoints from completed local
Dukascopy months.  They are deliberately separate from exchange marketing
hours: HTF bars must not bridge recurring vendor no-quote windows.
"""
from __future__ import annotations

from dataclasses import dataclass


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
