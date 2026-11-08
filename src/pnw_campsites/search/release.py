"""When a not-yet-released (NYR) night opens for booking, per booking system.

Recreation.gov and WA State Parks have rules. ReserveAmerica (Oregon) has no
NYR status, so it returns None.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta

from pnw_campsites.registry.models import BookingSystem


def _months_before(d: date, months: int) -> date:
    """Same day-of-month `months` earlier, clamped to that month's last day.

    Recreation.gov doesn't document which day releases e.g. Aug 31 (there is
    no Feb 31). Clamping gives Feb 28, the earlier of the two plausible dates
    (the other is Mar 1), so a user told to show up then is never late for a
    high-demand release.
    """
    year, month0 = divmod(d.year * 12 + d.month - 1 - months, 12)
    month = month0 + 1
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


def recgov_release_date(night: date) -> date:
    """Recreation.gov: most campgrounds release arrivals on a rolling 6-month
    window at 10 am ET / 7 am PT, so a night opens 6 months before, same day.

    Verified 2026-11-06 at Kirk Creek (233116): arrivals through May 6 2027
    were bookable, and nights from May 20 were NYR (the gap is the 14-night
    stay limit, which rec.gov reports as "Open").
    """
    return _months_before(night, 6)


def wa_release_date(night: date) -> date:
    """WA State Parks: "Reservations can be made up to nine months in advance
    of the first date of your trip" (parks.wa.gov, checked 2026-11-07), so a
    night opens for arrival 9 months before, same day.

    GoingToCamp doesn't report this window: nights past it come back
    Available, and its own NYR code marks loops on other schedules. The
    provider applies this rule to its statuses (see goingtocamp.py).

    Probed at Deception Pass, Aug 2027: on Nov 6-7 2026, Aug 6 had 194 sites
    Reserved, the count tapered to 2 on Aug 15 (10-night stays that arrived
    in time) and was 0 from Aug 16. The time of day it opens is unverified.
    """
    return _months_before(night, 9)


_RULES = {
    BookingSystem.RECGOV: recgov_release_date,
    BookingSystem.WA_STATE: wa_release_date,
}


def release_date(
    booking_system: BookingSystem, night: date, today: date,
) -> date | None:
    """The date `night` opens for booking, or None if unknown.

    None when the system has no rule, or when the rule's date has already
    passed: a night still NYR after that must be on a different window (some
    rec.gov campgrounds release 2 weeks out, or in whole-month blocks), and a
    date already gone by would be wrong.
    """
    rule = _RULES.get(booking_system)
    if rule is None:
        return None
    released = rule(night)
    return released if released >= today else None


@dataclass(frozen=True)
class NotReleasedRange:
    """A run of consecutive not-released nights. Each night opens one day
    after the one before it, so night N opens on releases_on + N days."""

    start: date
    end: date
    releases_on: date | None


def not_released_ranges(
    nights: list[date], booking_system: BookingSystem, today: date,
) -> list[NotReleasedRange]:
    """Group sorted not-released nights into ranges, splitting at gaps and
    wherever release dates stop advancing a day per night (month-end
    clamping, or a rule date that has passed)."""
    ranges: list[NotReleasedRange] = []
    prev: tuple[date, date | None] | None = None
    for night in nights:
        released = release_date(booking_system, night, today)
        if prev is not None and ranges:
            prev_night, prev_released = prev
            follows = night == prev_night + timedelta(days=1)
            if prev_released is None or released is None:
                same_rule = prev_released is None and released is None
            else:
                same_rule = released == prev_released + timedelta(days=1)
            if follows and same_rule:
                ranges[-1] = NotReleasedRange(ranges[-1].start, night, ranges[-1].releases_on)
                prev = (night, released)
                continue
        ranges.append(NotReleasedRange(night, night, released))
        prev = (night, released)
    return ranges


def format_release_range(first: date, last: date) -> str:
    """Dec 4, Dec 4 – 25, or Dec 28 – Jan 3 — as the frontend's formatDateRange."""
    start = f"{first:%b} {first.day}"
    if first == last:
        return start
    if (first.year, first.month) == (last.year, last.month):
        return f"{start} – {last.day}"
    return f"{start} – {last:%b} {last.day}"
