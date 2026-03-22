"""Recreation.gov API clients — RIDB metadata and availability."""

from __future__ import annotations

import asyncio
from datetime import date

import httpx

from pnw_campsites.providers.errors import FacilityNotFoundError, RateLimitedError
from pnw_campsites.registry.models import (
    CampgroundAvailability,
    CampsiteAvailability,
    RIDBFacility,
)

RIDB_BASE = "https://ridb.recreation.gov/api/v1"
AVAILABILITY_BASE = "https://www.recreation.gov/api/camps/availability/campground"

BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

# RIDB rate limit: 50 req/min — enforce with semaphore + delay
_RIDB_RATE_DELAY = 1.2  # seconds between requests (~50/min)


class RecGovClient:
    """Async client for Recreation.gov APIs."""

    def __init__(self, ridb_api_key: str) -> None:
        self._ridb_api_key = ridb_api_key
        self._ridb_client = httpx.AsyncClient(
            base_url=RIDB_BASE,
            headers={"accept": "application/json", "apikey": ridb_api_key},
            timeout=15.0,
        )
        self._availability_client = httpx.AsyncClient(
            headers={
                "User-Agent": BROWSER_USER_AGENT,
                "Accept": "application/json",
            },
            timeout=15.0,
        )
        self._ridb_lock = asyncio.Lock()

    async def close(self) -> None:
        await self._ridb_client.aclose()
        await self._availability_client.aclose()

    async def __aenter__(self) -> RecGovClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    # -------------------------------------------------------------------
    # RIDB Metadata
    # -------------------------------------------------------------------

    async def _ridb_get(self, path: str, params: dict | None = None) -> dict:
        """Rate-limited GET against the RIDB API."""
        async with self._ridb_lock:
            resp = await self._ridb_client.get(path, params=params)
            resp.raise_for_status()
            await asyncio.sleep(_RIDB_RATE_DELAY)
            return resp.json()

    async def get_facilities(
        self,
        state: str,
        activity: str = "CAMPING",
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[RIDBFacility], int]:
        """Fetch campground facilities from RIDB.

        Returns (facilities, total_count).
        """
        data = await self._ridb_get(
            "/facilities",
            params={
                "state": state,
                "activity": activity,
                "limit": limit,
                "offset": offset,
            },
        )
        total = data.get("METADATA", {}).get("RESULTS", {}).get("TOTAL_COUNT", 0)
        facilities = [RIDBFacility.model_validate(f) for f in data.get("RECDATA", [])]
        return facilities, total

    async def get_all_facilities(
        self,
        state: str,
        activity: str = "CAMPING",
    ) -> list[RIDBFacility]:
        """Fetch all campground facilities for a state, paginating automatically."""
        all_facilities: list[RIDBFacility] = []
        offset = 0
        page_size = 50

        while True:
            facilities, total = await self.get_facilities(
                state=state, activity=activity, limit=page_size, offset=offset
            )
            all_facilities.extend(facilities)
            offset += page_size
            if offset >= total:
                break

        return all_facilities

    async def get_facility_campsites(self, facility_id: str) -> list[dict]:
        """Fetch campsite metadata for a facility from RIDB."""
        data = await self._ridb_get(f"/facilities/{facility_id}/campsites")
        return data.get("RECDATA", [])

    # -------------------------------------------------------------------
    # Availability (undocumented endpoint)
    # -------------------------------------------------------------------

    async def get_availability(
        self,
        facility_id: str,
        month: date,
    ) -> CampgroundAvailability:
        """Fetch per-site availability for a campground for a given month.

        Args:
            facility_id: Rec.gov facility ID (e.g. "232464" for Ohanapecosh).
            month: Any date — will be normalized to the 1st of that month.
        """
        start_date = month.replace(day=1).strftime("%Y-%m-01T00:00:00.000Z")
        url = f"{AVAILABILITY_BASE}/{facility_id}/month"
        params = {"start_date": start_date}

        for attempt in range(2):
            resp = await self._availability_client.get(url, params=params)
            if resp.status_code == 404:
                raise FacilityNotFoundError(f"Facility {facility_id} not found")
            if resp.status_code == 429:
                if attempt == 0:
                    await asyncio.sleep(2)
                    continue
                raise RateLimitedError(f"Rate limited fetching {facility_id}")
            if resp.status_code >= 500 and attempt == 0:
                await asyncio.sleep(1)
                continue
            resp.raise_for_status()
            break

        data = resp.json()

        campsites: dict[str, CampsiteAvailability] = {}
        for site_id, site_data in data.get("campsites", {}).items():
            campsites[site_id] = CampsiteAvailability.model_validate(site_data)

        return CampgroundAvailability(facility_id=facility_id, campsites=campsites)

    async def get_availability_range(
        self,
        facility_id: str,
        start_month: date,
        end_month: date,
    ) -> CampgroundAvailability:
        """Fetch availability across multiple months and merge results.

        Useful for queries spanning month boundaries (e.g. "any weekend in June-July").
        """
        months: list[date] = []
        current = start_month.replace(day=1)
        end = end_month.replace(day=1)
        while current <= end:
            months.append(current)
            # Advance to next month
            if current.month == 12:
                current = current.replace(year=current.year + 1, month=1)
            else:
                current = current.replace(month=current.month + 1)

        results = await asyncio.gather(
            *(self.get_availability(facility_id, m) for m in months)
        )

        # Merge all months into one CampgroundAvailability
        merged_campsites: dict[str, CampsiteAvailability] = {}
        for result in results:
            for site_id, site in result.campsites.items():
                if site_id in merged_campsites:
                    merged_campsites[site_id].availabilities.update(site.availabilities)
                else:
                    merged_campsites[site_id] = site

        return CampgroundAvailability(facility_id=facility_id, campsites=merged_campsites)
