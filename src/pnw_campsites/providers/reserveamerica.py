"""Oregon State Parks (ReserveAmerica) provider.

Uses curl_cffi to fetch the unified www.reserveamerica.com availability pages.
The site is a React SSR app with Redux state embedded in a <script> tag.
Each request returns a 14-day availability window for 20 campsites.

For date ranges > 14 days, multiple requests are made in 14-day windows.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from datetime import date, timedelta

from curl_cffi import requests as curl_requests

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
# Records per page (RA default)
_PAGE_SIZE = 20

# Regex to extract the Redux state JSON blob from the HTML
_REDUX_RE = re.compile(r'(\{"application"\s*:\s*\{.+\})\s*</script>')

# Attribute IDs for min/max occupants
_ATTR_MIN_PEOPLE = 111
_ATTR_MAX_PEOPLE = 12


class ReserveAmericaClient:
    """Client for Oregon State Parks via the unified ReserveAmerica site."""

    def __init__(self) -> None:
        self._session: curl_requests.Session | None = None

    async def __aenter__(self) -> ReserveAmericaClient:
        self._session = curl_requests.Session(impersonate="chrome131")
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._session:
            self._session.close()
            self._session = None

    async def get_availability(
        self,
        park_id: str,
        slug: str,
        state: str,
        start_date: date,
        end_date: date,
    ) -> CampgroundAvailability:
        """Fetch per-site availability for an Oregon State Park.

        Makes one request per 14-day window in the date range.
        """
        return await asyncio.to_thread(
            self._get_availability_sync,
            park_id, slug, state, start_date, end_date,
        )

    def _get_availability_sync(
        self,
        park_id: str,
        slug: str,
        state: str,
        start_date: date,
        end_date: date,
    ) -> CampgroundAvailability:
        all_campsites: dict[str, CampsiteAvailability] = {}

        # Break date range into 14-day windows
        window_start = start_date
        while window_start <= end_date:
            window_end = min(window_start + timedelta(days=_WINDOW_DAYS - 1), end_date)

            # Paginate within each window (20 records per page)
            page = 1
            while True:
                records, total = self._fetch_window(
                    park_id, slug, state, window_start, window_end, page=page,
                )

                for rec in records:
                    site_id = str(rec["id"])
                    avail_dict = _parse_availability_grid(rec.get("availabilityGrid", []))

                    if site_id in all_campsites:
                        all_campsites[site_id].availabilities.update(avail_dict)
                    else:
                        all_campsites[site_id] = _record_to_campsite(rec, avail_dict)

                fetched_so_far = _PAGE_SIZE * page
                if not records or fetched_so_far >= total:
                    break
                page += 1
                time.sleep(1.0)  # rate limit between pages

            window_start = window_end + timedelta(days=1)

            # Rate limit between windows
            if window_start <= end_date:
                time.sleep(1.0)

        return CampgroundAvailability(
            facility_id=park_id,
            campsites=all_campsites,
        )

    def _fetch_window(
        self,
        park_id: str,
        slug: str,
        state: str,
        start_date: date,
        end_date: date,
        page: int = 1,
    ) -> tuple[list[dict], int]:
        """Fetch one page of a 14-day window. Returns (records, totalRecords)."""
        assert self._session is not None

        url = (
            f"{BASE_URL}/explore/{slug}/{state}/{park_id}"
            f"/campsite-availability"
        )
        params: dict[str, str | int] = {
            "arrivalDate": start_date.isoformat(),
            "departureDate": end_date.isoformat(),
        }
        if page > 1:
            params["page"] = page

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


def _get_attribute_value(record: dict, attr_id: int) -> str | None:
    """Extract an attribute value from a record's details."""
    attrs = record.get("details", {}).get("attributes", [])
    for attr in attrs:
        if attr.get("id") == attr_id:
            vals = attr.get("value", [])
            return vals[0] if vals else None
    return None


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
        availabilities=availabilities,
    )
