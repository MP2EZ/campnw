"""Oregon State Parks (ReserveAmerica) provider.

Uses curl_cffi to fetch the unified www.reserveamerica.com availability pages.
The site is a React SSR app with Redux state embedded in a <script> tag.
Each request returns a 14-day availability window for 20 campsites.

For date ranges > 14 days, multiple requests are made in 14-day windows. A
search passes the nights it asks about, and only windows holding one of them
are fetched (``window_cover``).
Requests run on the provider thread pool, one at a time, and the client spaces
them app-wide with a shared limiter: no thread is held between requests.
"""

from __future__ import annotations

import contextvars
import functools
import json
import logging
import os
import re
import time
from collections.abc import Iterable
from datetime import date, timedelta

from curl_cffi import requests as curl_requests

from pnw_campsites.providers.blocking import MinIntervalLimiter, run_blocking
from pnw_campsites.providers.errors import (
    FacilityNotFoundError,
    RateLimitedError,
    WAFBlockedError,
)
from pnw_campsites.registry.models import (
    AvailabilityStatus,
    CampgroundAvailability,
    CampsiteAvailability,
)
from pnw_campsites.search.site_fit import fit_from_ra_attributes

logger = logging.getLogger(__name__)

BASE_URL = "https://www.reserveamerica.com"

# RA availability grid statuses → our enum
_STATUS_MAP: dict[str, AvailabilityStatus] = {
    "AVAILABLE": AvailabilityStatus.AVAILABLE,
    "RESERVED": AvailabilityStatus.RESERVED,
    "NOT_AVAILABLE": AvailabilityStatus.NOT_AVAILABLE,
    "NOT_RESERVABLE": AvailabilityStatus.NOT_RESERVABLE,
    "WALK_UP": AvailabilityStatus.OPEN,  # walk-up = FCFS
    "CLOSED": AvailabilityStatus.CLOSED,
}

# Max days per SSR page load
_WINDOW_DAYS = 14
# Records per page: RA's maximum for `recordsPerPage` (its default is 20).
# Pages are 0-based `pageNumber`; RA ignores a `page` param.
_PAGE_SIZE = 50
# Minimum spacing between request starts, across every search and the poller.
# 1.0 = 1 req/s. Prod reaches ReserveAmerica only through its dedicated Fly
# egress IP, and a block there takes out every Oregon park, so raise this only
# deliberately (2 req/s roughly halves Oregon search time; see PR #241).
_MIN_INTERVAL_ENV = "RESERVEAMERICA_MIN_INTERVAL_S"
_DEFAULT_MIN_INTERVAL_S = 1.0


def window_cover(nights: Iterable[date], end: date) -> list[tuple[date, date]]:
    """Fewest 14-day windows holding every night, as (arrival, departure).

    Each window starts at the first night not yet covered, so a month of
    weekends from the 1st takes two windows where 1st-to-end takes three.
    A window never runs past ``end``.
    """
    windows: list[tuple[date, date]] = []
    covered_through: date | None = None
    for night in sorted(set(nights)):
        if covered_through is not None and night <= covered_through:
            continue
        covered_through = night + timedelta(days=_WINDOW_DAYS - 1)
        windows.append((night, min(covered_through, end)))
    return windows


def _range_windows(start: date, end: date) -> list[tuple[date, date]]:
    windows = []
    while start <= end:
        windows.append((start, min(start + timedelta(days=_WINDOW_DAYS - 1), end)))
        start += timedelta(days=_WINDOW_DAYS)
    return windows


def _min_interval() -> float:
    raw = os.getenv(_MIN_INTERVAL_ENV)
    if raw is None:
        return _DEFAULT_MIN_INTERVAL_S
    try:
        return max(0.0, float(raw))
    except ValueError:
        logger.warning("Ignoring %s=%r: not a number", _MIN_INTERVAL_ENV, raw)
        return _DEFAULT_MIN_INTERVAL_S

# Regex to extract the Redux state JSON blob from the HTML
_REDUX_RE = re.compile(r'(\{"application"\s*:\s*\{.+\})\s*</script>')

# Attribute IDs for min/max occupants
_ATTR_MIN_PEOPLE = 111
_ATTR_MAX_PEOPLE = 12
# Attribute IDs for site fit (seen on Oregon parks, 2026-11-07)
_ATTR_MAX_VEHICLE_FT = 109  # "Maximum Vehicle Length"
_ATTR_ELECTRIC = 218  # "Electricity Hookup" (amps)
_ATTR_CATEGORIES = 99999  # "Looking For Category": Tent / RV / Trailer Site


# Requests made by the get_availability call running in this task. Each park
# runs in its own task, so concurrent parks don't share a count.
_park_requests: contextvars.ContextVar[list[int] | None] = contextvars.ContextVar(
    "_park_requests", default=None,
)


def _log_park_fetch(fn):
    """One INFO line per park: requests, seconds and outcome. Also on a
    timeout (the search cancels the park), which is when it matters most."""

    @functools.wraps(fn)
    async def wrapper(self, park_id, *args, **kwargs):
        count = [0]
        token = _park_requests.set(count)
        started = time.monotonic()
        outcome = "cancelled"
        try:
            result = await fn(self, park_id, *args, **kwargs)
            outcome = f"{len(result.campsites)} sites"
            return result
        except Exception as exc:
            outcome = type(exc).__name__
            raise
        finally:
            _park_requests.reset(token)
            logger.info(
                "ReserveAmerica %s: %d requests in %.1fs (%s)",
                park_id, count[0], time.monotonic() - started, outcome,
            )

    return wrapper


class ReserveAmericaClient:
    """Client for Oregon State Parks via the unified ReserveAmerica site."""

    def __init__(self) -> None:
        self._session: curl_requests.Session | None = None
        self._limiter = MinIntervalLimiter(_min_interval())

    async def __aenter__(self) -> ReserveAmericaClient:
        self._session = curl_requests.Session(impersonate="chrome131")
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._session:
            self._session.close()
            self._session = None

    async def _fetch(
        self,
        park_id: str,
        slug: str,
        state: str,
        start_date: date,
        end_date: date,
        page: int = 0,
    ) -> tuple[list[dict], int]:
        queued = time.monotonic()
        await self._limiter.wait()
        sent = time.monotonic()
        try:
            return await run_blocking(
                self._fetch_window, park_id, slug, state, start_date, end_date, page,
            )
        finally:
            count = _park_requests.get()
            if count is not None:
                count[0] += 1
            logger.debug(
                "ReserveAmerica %s %s page %d: %.2fs (%.2fs waiting on the limiter)",
                park_id, start_date, page, time.monotonic() - sent, sent - queued,
            )

    @_log_park_fetch
    async def get_availability(
        self,
        park_id: str,
        slug: str,
        state: str,
        start_date: date,
        end_date: date,
        *,
        nights: Iterable[date] | None = None,
    ) -> CampgroundAvailability:
        """Fetch per-site availability for an Oregon State Park.

        Makes one request per page of each 14-day window in the date range,
        or, given ``nights``, of each window ``window_cover`` picks for them.
        """
        all_campsites: dict[str, CampsiteAvailability] = {}
        windows = (
            window_cover(nights, end_date) if nights is not None
            else _range_windows(start_date, end_date)
        )
        for window_start, window_end in windows:
            page = 0
            while True:
                records, total = await self._fetch(
                    park_id, slug, state, window_start, window_end, page,
                )

                for rec in records:
                    site_id = str(rec["id"])
                    avail_dict = _parse_availability_grid(rec.get("availabilityGrid", []))

                    if site_id in all_campsites:
                        all_campsites[site_id].availabilities.update(avail_dict)
                    else:
                        all_campsites[site_id] = _record_to_campsite(rec, avail_dict)

                page += 1
                if not records or page * _PAGE_SIZE >= total:
                    break

        return CampgroundAvailability(
            facility_id=park_id,
            campsites=all_campsites,
        )

    async def ping(self, park_id: str, slug: str, state: str) -> int:
        """Cheap liveness probe — one request, no availability grid parsing.

        ``get_availability`` walks 14-day windows and parses a ~2MB Redux blob
        per page, which is far too expensive for a health check. This exercises
        the same session, TLS impersonation and WAF path in a single request.

        Returns the total record count reported by the search payload.
        """
        today = date.today()
        records, total = await self._fetch(
            park_id, slug, state, today, today + timedelta(days=1),
        )
        if not records and total == 0:
            raise ValueError(f"ReserveAmerica returned no records for park {park_id}")
        return total

    def _fetch_window(
        self,
        park_id: str,
        slug: str,
        state: str,
        start_date: date,
        end_date: date,
        page: int = 0,
    ) -> tuple[list[dict], int]:
        """Fetch one page (0-based) of a 14-day window. Blocking.

        Returns (records, totalRecords)."""
        assert self._session is not None

        url = (
            f"{BASE_URL}/explore/{slug}/{state}/{park_id}"
            f"/campsite-availability"
        )
        params: dict[str, str | int] = {
            "arrivalDate": start_date.isoformat(),
            "departureDate": end_date.isoformat(),
            "recordsPerPage": _PAGE_SIZE,
        }
        if page:
            params["pageNumber"] = page

        for attempt in range(2):
            try:
                resp = self._session.get(url, params=params, timeout=30)
            except Exception as e:
                if attempt == 0:
                    time.sleep(2)
                    continue
                raise WAFBlockedError(f"ReserveAmerica request failed: {e}") from e

            if resp.status_code == 403:
                raise WAFBlockedError("ReserveAmerica WAF blocked the request")
            if resp.status_code == 404:
                raise FacilityNotFoundError(
                    f"Park {park_id} not found on ReserveAmerica"
                )
            if resp.status_code == 429:
                raise RateLimitedError("ReserveAmerica rate limit hit")
            if resp.status_code >= 500 and attempt == 0:
                time.sleep(2)
                continue
            resp.raise_for_status()

            return _extract_records(resp.text)

        # Final attempt already raised
        resp.raise_for_status()
        return [], 0


def _extract_records(html: str) -> tuple[list[dict], int]:
    """Parse Redux state from HTML and return (records, totalRecords)."""
    match = _REDUX_RE.search(html)
    if not match:
        logger.warning("Could not find Redux state in ReserveAmerica HTML")
        return [], 0

    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError:
        logger.warning("Failed to parse ReserveAmerica Redux state JSON")
        return [], 0

    search_results = (
        data.get("backend", {})
        .get("productSearch", {})
        .get("searchResults", {})
    )

    records = search_results.get("records", [])
    total_records = search_results.get("totalRecords", 0)
    return records, total_records


def _parse_availability_grid(
    grid: list[dict],
) -> dict[str, AvailabilityStatus]:
    """Convert RA availabilityGrid to our date→status dict."""
    avail: dict[str, AvailabilityStatus] = {}
    for entry in grid:
        dt = entry.get("date")
        status_str = entry.get("status", "NOT_AVAILABLE")
        if dt:
            iso_key = f"{dt}T00:00:00.000Z"
            avail[iso_key] = _STATUS_MAP.get(
                status_str, AvailabilityStatus.NOT_AVAILABLE
            )
    return avail


def _get_attribute_values(record: dict, attr_id: int) -> list[str] | None:
    """Extract an attribute's values from a record's details, None if absent."""
    attrs = record.get("details", {}).get("attributes", [])
    for attr in attrs:
        if attr.get("id") == attr_id:
            return attr.get("value") or []
    return None


def _get_attribute_value(record: dict, attr_id: int) -> str | None:
    """Extract an attribute's first value from a record's details."""
    vals = _get_attribute_values(record, attr_id)
    return vals[0] if vals else None


def _record_to_campsite(
    record: dict,
    availabilities: dict[str, AvailabilityStatus],
) -> CampsiteAvailability:
    """Convert an RA record to a CampsiteAvailability."""
    site_id = str(record["id"])
    site_name = record.get("name", site_id)
    details = record.get("details", {})
    loop = details.get("loopName", "")
    prod_grp = record.get("prodGrpName", "STANDARD")
    type_of_use = record.get("prodInfo", {}).get("typeOfUseLabel", "Overnight")

    min_people_str = _get_attribute_value(record, _ATTR_MIN_PEOPLE)
    max_people_str = _get_attribute_value(record, _ATTR_MAX_PEOPLE)
    min_people = int(min_people_str) if min_people_str else 0
    max_people = int(max_people_str) if max_people_str else 8

    return CampsiteAvailability(
        campsite_id=site_id,
        site=site_name,
        loop=loop,
        campsite_type=prod_grp,
        type_of_use=type_of_use,
        min_num_people=min_people,
        max_num_people=max_people,
        max_people_known=bool(max_people_str),
        availabilities=availabilities,
        fit=fit_from_ra_attributes(
            prod_grp,
            _get_attribute_values(record, _ATTR_CATEGORIES),
            _get_attribute_value(record, _ATTR_MAX_VEHICLE_FT),
            _get_attribute_value(record, _ATTR_ELECTRIC),
        ),
    )
