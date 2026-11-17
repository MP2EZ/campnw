"""Availability history for a fixed set of campgrounds, independent of watches.

Booking tips (analytics/patterns.py) are built from availability_daily and
status_transitions. Those used to be written only by the watch poller, so
history covered only campgrounds someone watched, and only for the watch's
dates. Prod's history stopped on 2026-07-31 when the seed watches' April start
month aged out of rec.gov's window. This job keeps a steady series for
high-demand campgrounds whether or not anyone watches them.

It polls every 15 minutes, matching the data the tips were designed on: at the
busiest parks a reopened site stays open for a median of 45-105 minutes, so a
slower cadence misses most cancellations.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

from pnw_campsites.monitor.db import WatchDB
from pnw_campsites.monitor.pacific import pacific_today
from pnw_campsites.providers.errors import RateLimitedError
from pnw_campsites.providers.recgov import RecGovClient

_logger = logging.getLogger(__name__)

# High-demand rec.gov campgrounds. The first six have history from 2026, so
# their series continue. Rec.gov only: GoingToCamp blocks prod's IP (#167).
HISTORY_FACILITIES: tuple[str, ...] = (
    "232464",  # Kalaloch, WA
    "232465",  # Ohanapecosh, WA
    "232466",  # Cougar Rock, WA
    "232868",  # Oak Fork (Timothy Lake), OR
    "233858",  # Stanley Lake, ID
    "233136",  # Anthony Lake, OR
    "232866",  # Gone Creek (Timothy Lake), OR
    "232867",  # Hoodview (Timothy Lake), OR
    "232831",  # Trillium Lake, OR
    "232493",  # Fish Creek (Glacier NP), MT
    "232492",  # St. Mary (Glacier NP), MT
    "232358",  # Outlet (Redfish Lake), ID
    "232050",  # Glacier View (Redfish Lake), ID
    "232450",  # Lower Pines (Yosemite), CA
)

# Most cancellations come within 30 days of arrival (85-88% in the 2026 data).
# 90 days also catches the earlier ones without polling the whole 6-month window.
HISTORY_DAYS_AHEAD = 90


def history_months(today: date, days_ahead: int = HISTORY_DAYS_AHEAD) -> list[date]:
    """First of each month from this month through today + days_ahead.

    Never a past month: rec.gov answers 400 for months about three months old,
    and that is what stopped prod's history on 2026-07-31.
    """
    month = today.replace(day=1)
    last = (today + timedelta(days=days_ahead)).replace(day=1)
    months = []
    while month <= last:
        months.append(month)
        month = (month + timedelta(days=32)).replace(day=1)
    return months


async def record_history(
    recgov: RecGovClient,
    watch_db: WatchDB,
    today: date | None = None,
    facilities: tuple[str, ...] | None = None,
) -> int:
    """Fetch each facility's upcoming months and record them. Returns rows written.

    One month at a time, sequentially: peak memory is one month's payload, and
    a failed month (a 404, a 400, a timeout) costs only that month. A rate
    limit stops the cycle; the next one tries again.

    Fetches bypass availability_cache. A cached payload would be recorded with
    a fresh observed_at and shift the transition times the tips measure.
    """
    today = today or pacific_today()
    facilities = HISTORY_FACILITIES if facilities is None else facilities
    first_night = today.isoformat()
    written = failed = 0

    for facility_id in facilities:
        for month in history_months(today):
            try:
                avail = await recgov.get_availability(facility_id, month)
            except RateLimitedError:
                _logger.warning("History: rec.gov rate-limited; cycle stopped")
                return written
            except Exception as e:
                failed += 1
                _logger.warning(
                    "History: %s %s failed: %r", facility_id, f"{month:%Y-%m}", e,
                )
                continue
            # Past nights no longer change in a way the tips use.
            records = [
                (site_id, night[:10], status.value)
                for site_id, site in avail.campsites.items()
                for night, status in site.availabilities.items()
                if night[:10] >= first_night
            ]
            watch_db.record_availability_history(facility_id, records, "recgov")
            written += len(records)

    _logger.info(
        "History: %d rows for %d campgrounds, %d month fetch(es) failed",
        written, len(facilities), failed,
    )
    return written
