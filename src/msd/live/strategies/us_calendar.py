"""NYSE full holidays and scheduled half days (research skipped these sessions as incomplete)."""
from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache

from pandas.tseries.holiday import (
    AbstractHolidayCalendar, GoodFriday, Holiday, USLaborDay, USMartinLutherKingJr,
    USMemorialDay, USPresidentsDay, USThanksgivingDay, nearest_workday,
)


class _NYSE(AbstractHolidayCalendar):
    rules = [
        Holiday("New Year", month=1, day=1, observance=nearest_workday),
        USMartinLutherKingJr, USPresidentsDay, GoodFriday, USMemorialDay,
        Holiday("Juneteenth", month=6, day=19, start_date="2022-01-01", observance=nearest_workday),
        Holiday("Independence Day", month=7, day=4, observance=nearest_workday),
        USLaborDay, USThanksgivingDay,
        Holiday("Christmas", month=12, day=25, observance=nearest_workday),
    ]


@lru_cache(maxsize=64)
def _year(year: int) -> frozenset[date]:
    full = {ts.date() for ts in _NYSE().holidays(f"{year}-01-01", f"{year}-12-31")}
    half = {d for d in (date(year, 7, 3), date(year, 12, 24)) if d.weekday() < 5}
    thanksgiving = next(d for d in full if d.month == 11)
    half.add(thanksgiving + timedelta(days=1))
    # New Year on Saturday is not observed on Dec 31 by NYSE.
    full.discard(date(year, 12, 31))
    return frozenset(full | (half - full))


def skip_day(day: date) -> bool:
    """True for NYSE full holidays and scheduled early closes."""
    return day in _year(day.year)
