"""Pacific time, where the campgrounds are. Watch dates are local nights."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

PACIFIC = ZoneInfo("America/Los_Angeles")


def pacific_now() -> datetime:
    return datetime.now(PACIFIC)


def pacific_today() -> date:
    return pacific_now().date()
