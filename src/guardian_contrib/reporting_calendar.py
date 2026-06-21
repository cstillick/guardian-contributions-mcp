"""Reporting calendar — Hard Rule 1: never hardcode the continuing window.

Oklahoma's statewide primary is the 3rd Tuesday of June. The continuing window
runs from (Pre-Primary period end + 1 day) through the primary election day.

The Pre-Primary period itself should be read off an actual pulled PDF (Rule 3),
not assumed; build_calendar() accepts it and only falls back to a documented
default when none is supplied.
"""
from __future__ import annotations

import calendar as _cal
import datetime as dt
from dataclasses import dataclass


def primary_date(year: int) -> dt.date:
    """3rd Tuesday of June for the given year (OK statewide primary)."""
    june = _cal.Calendar().itermonthdates(year, 6)
    tuesdays = [d for d in june if d.month == 6 and d.weekday() == _cal.TUESDAY]
    return tuesdays[2]


# Documented per-cycle defaults (override by reading a real Pre-Primary PDF).
_PRE_PRIMARY_DEFAULTS: dict[int, tuple[dt.date, dt.date]] = {
    2026: (dt.date(2026, 4, 1), dt.date(2026, 6, 1)),
}


@dataclass(frozen=True)
class ReportingCalendar:
    year: int
    primary_date: dt.date
    pre_primary_start: dt.date
    pre_primary_end: dt.date
    continuing_start: dt.date
    continuing_end: dt.date
    primary_confirmed: bool = False  # set True once confirmed via web lookup (Rule 1)

    def to_dict(self) -> dict:
        return {
            "year": self.year,
            "primary_date": self.primary_date.isoformat(),
            "primary_confirmed": self.primary_confirmed,
            "pre_primary_period": {
                "start": self.pre_primary_start.isoformat(),
                "end": self.pre_primary_end.isoformat(),
            },
            "continuing_window": {
                "start": self.continuing_start.isoformat(),
                "end": self.continuing_end.isoformat(),
            },
        }


def build_calendar(
    year: int,
    pre_primary_period: tuple[dt.date, dt.date] | None = None,
    primary_confirmed: bool = False,
) -> ReportingCalendar:
    primary = primary_date(year)
    if pre_primary_period is None:
        pre_primary_period = _PRE_PRIMARY_DEFAULTS.get(year)
    if pre_primary_period is None:
        raise ValueError(
            f"No Pre-Primary period for {year}; supply it from a pulled PDF (Rule 3)."
        )
    pp_start, pp_end = pre_primary_period
    return ReportingCalendar(
        year=year,
        primary_date=primary,
        pre_primary_start=pp_start,
        pre_primary_end=pp_end,
        continuing_start=pp_end + dt.timedelta(days=1),
        continuing_end=primary,
        primary_confirmed=primary_confirmed,
    )
