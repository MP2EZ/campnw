"""WA State Parks (GoingToCamp) API client.

Uses curl_cffi to bypass Azure WAF via Chrome TLS fingerprint impersonation.
The GoingToCamp API is hierarchical: maps contain links to child maps, and
availability data lives at the leaf level with individual campsite resources.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from datetime import date, timedelta

from curl_cffi import requests as curl_requests

from pnw_campsites.providers.errors import RateLimitedError, WAFBlockedError
from pnw_campsites.registry.models import (
    AvailabilityStatus,
    CampgroundAvailability,
    CampsiteAvailability,
)
from pnw_campsites.search.release import wa_release_date

BASE_URL = "https://washington.goingtocamp.com"

logger = logging.getLogger(__name__)

# After the park index fails to load, re-raise that failure for this long
# instead of re-fetching /api/maps once per park in a search fan-out.
INDEX_RETRY_SECONDS = 60

# Resource category IDs from GoingToCamp
CAMPSITE_CATEGORY = -2147483648
GROUP_CATEGORY = -2147483643
OVERFLOW_CATEGORY = -2147483647

# Equipment category for standard (non-group) sites
NON_GROUP_EQUIPMENT = -32768

# GoingToCamp availability values → our status enum
_AVAILABILITY_MAP: dict[int, AvailabilityStatus] = {
    0: AvailabilityStatus.AVAILABLE,
    1: AvailabilityStatus.RESERVED,
    2: AvailabilityStatus.CLOSED,
    3: AvailabilityStatus.NOT_RESERVABLE,
    4: AvailabilityStatus.NOT_RESERVABLE_MGMT,
    5: AvailabilityStatus.NYR,
}

# Statuses GoingToCamp reports for nights past the 9-month window that only
# mean "released": Available (nobody can arrive yet) and Reserved (the tail of
# a stay that arrived in time). Closed / not-reservable describe the site.
_WINDOW_STATUSES = {AvailabilityStatus.AVAILABLE, AvailabilityStatus.RESERVED}


class GoingToCampClient:
    """Async client for WA State Parks via GoingToCamp API."""

    def __init__(self) -> None:
        self._session: curl_requests.Session | None = None
        # resourceLocationId → park-level childMapId (from /api/maps links)
        self._park_map_ids: dict[int, int] = {}
        self._index_lock = threading.Lock()
        self._index_error: Exception | None = None
        self._index_failed_at = 0.0

    async def __aenter__(self) -> GoingToCampClient:
        self._session = curl_requests.Session(impersonate="chrome131")
        # The server enters this client during app startup. A blocked or failed
        # index load must not fail startup; availability calls retry it.
        try:
            await asyncio.to_thread(self._ensure_park_index_sync)
        except Exception as exc:
            logger.warning(
                "GoingToCamp park index unavailable at startup: %s: %s",
                type(exc).__name__, exc,
            )
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._session:
            self._session.close()
            self._session = None

    def _ensure_park_index_sync(self) -> None:
        """Build resourceLocationId → park mapId index from the maps hierarchy.

        Each top-level map has mapLinks with resourceLocationId and childMapId.
        The childMapId is the park-specific map that contains loop/area sub-maps.

        No-op once loaded. On failure, raises — and keeps raising the same
        error without refetching for INDEX_RETRY_SECONDS.
        """
        if self._park_map_ids:
            return
        with self._index_lock:
            if self._park_map_ids:
                return
            if (
                self._index_error is not None
                and time.monotonic() - self._index_failed_at < INDEX_RETRY_SECONDS
            ):
                raise self._index_error.with_traceback(None)
            # Built aside and swapped in whole: readers skip the lock once the
            # index is non-empty, so filling it in place would let them act on
            # a half-built index, and a response that broke mid-loop would
            # leave a partial one that never got rebuilt.
            index: dict[int, int] = {}
            try:
                maps = self._get_sync("/api/maps")
                for m in maps:
                    for link in m.get("mapLinks", []):
                        rl_id = link.get("resourceLocationId")
                        child_map = link.get("childMapId")
                        if rl_id is not None and child_map is not None:
                            index[rl_id] = child_map
            except Exception as exc:
                self._index_error = exc
                self._index_failed_at = time.monotonic()
                raise
            self._index_error = None
            self._park_map_ids = index

    async def _get(self, path: str, params: dict | None = None) -> dict | list:
        """GET with WAF bypass, run in thread to avoid blocking the event loop."""
        return await asyncio.to_thread(self._get_sync, path, params)

    def _get_sync(self, path: str, params: dict | None = None) -> dict | list:
        assert self._session is not None
        for attempt in range(2):
            resp = self._session.get(f"{BASE_URL}{path}", params=params, timeout=30)
            if resp.status_code == 403:
                raise WAFBlockedError("GoingToCamp WAF blocked the request")
            if resp.status_code == 429:
                raise RateLimitedError("GoingToCamp rate limited the request")
            if resp.status_code >= 500 and attempt == 0:
                time.sleep(1)
                continue
            resp.raise_for_status()
            return resp.json()
        resp.raise_for_status()
        return resp.json()

    # -------------------------------------------------------------------
    # Park locations
    # -------------------------------------------------------------------

    async def get_locations(self) -> list[dict]:
        """Get all WA State Park locations with their resource categories."""
        return await self._get("/api/resourceLocation")

    async def get_campground_locations(self) -> list[dict]:
        """Get only locations that have campsite resources."""
        locations = await self.get_locations()
        return [
            loc
            for loc in locations
            if CAMPSITE_CATEGORY in loc.get("resourceCategoryIds", [])
        ]

    # -------------------------------------------------------------------
    # Site/loop metadata (for one-time enrichment)
    # -------------------------------------------------------------------

    async def get_park_resources(self, resource_location_id: int) -> dict:
        """Fetch every site (resource) for a park keyed by resource_id.

        Each value contains localizedValues[0].name (the human site label
        like "L03" or "MT8") and mapIds (the loop maps the site belongs to).
        Used by the one-time site/loop name enrichment seeder.
        """
        return await self._get(
            "/api/resourcelocation/resources",
            params={"resourceLocationId": resource_location_id},
        )

    async def get_park_maps(self, resource_location_id: int) -> list[dict]:
        """Fetch all maps for a park, including leaf loop maps.

        Each leaf map has localizedValues[0].title ("Lower Loop A") and
        a description ("Sites 79-145..."). Used by the one-time site/loop
        name enrichment seeder.
        """
        return await self._get(
            "/api/maps",
            params={"resourceLocationId": resource_location_id},
        )

    # -------------------------------------------------------------------
    # Availability
    # -------------------------------------------------------------------

    async def get_availability(
        self,
        resource_location_id: int,
        start_date: date,
        end_date: date,
    ) -> CampgroundAvailability:
        """Fetch per-site availability for a WA State Park.

        Looks up the park's dedicated map from the pre-built index, then
        traverses child maps to collect all campsite availability.
        """
        return await asyncio.to_thread(
            self._get_availability_sync,
            resource_location_id,
            start_date,
            end_date,
        )

    def _get_availability_sync(
        self,
        resource_location_id: int,
        start_date: date,
        end_date: date,
    ) -> CampgroundAvailability:
        facility_id = str(resource_location_id)

        self._ensure_park_index_sync()
        park_map_id = self._park_map_ids.get(resource_location_id)
        if not park_map_id:
            return CampgroundAvailability(facility_id=facility_id, campsites={})

        # Collect all resources from the park's map hierarchy
        all_resources: dict[str, list[dict]] = {}
        self._collect_resources(park_map_id, start_date, end_date, all_resources)

        campsites = self._build_campsites(all_resources, start_date, end_date)
        return CampgroundAvailability(facility_id=facility_id, campsites=campsites)

    def _collect_resources(
        self,
        map_id: int,
        start_date: date,
        end_date: date,
        out: dict[str, list[dict]],
        depth: int = 0,
    ) -> None:
        """Recursively traverse map hierarchy collecting site availability."""
        if depth > 5:  # safety limit
            return

        data = self._fetch_map_availability(map_id, start_date, end_date)

        # Leaf level — has actual site resources
        for res_id, day_list in data.get("resourceAvailabilities", {}).items():
            out[str(res_id)] = day_list

        # Non-leaf — follow child maps
        for child_map_id in data.get("mapLinkAvailabilities", {}):
            self._collect_resources(
                int(child_map_id), start_date, end_date, out, depth + 1
            )

    def _fetch_map_availability(
        self,
        map_id: int,
        start_date: date,
        end_date: date,
    ) -> dict:
        """Fetch availability for a single map node."""
        params = {
            "mapId": map_id,
            "bookingCategoryId": 0,
            "startDate": start_date.isoformat(),
            "endDate": end_date.isoformat(),
            "isReserving": "true",
            "getDailyAvailability": "true",
            "partySize": 1,
            "equipmentCategoryId": NON_GROUP_EQUIPMENT,
            "subEquipmentCategoryId": NON_GROUP_EQUIPMENT,
            "filterData": "[]",
        }
        return self._get_sync("/api/availability/map", params)

    def _build_campsites(
        self,
        resources: dict[str, list[dict]],
        start_date: date,
        end_date: date,
        today: date | None = None,
    ) -> dict[str, CampsiteAvailability]:
        """Convert GoingToCamp resource availability to CampsiteAvailability models.

        GoingToCamp's daily availability ignores WA's 9-month arrival window,
        so nights past it are rewritten to NYR here, where every consumer
        (search, check, watches) reads them.
        """
        campsites: dict[str, CampsiteAvailability] = {}
        num_days = (end_date - start_date).days + 1
        today = today or date.today()

        for res_id, day_list in resources.items():
            availabilities: dict[str, AvailabilityStatus] = {}
            for i, day_data in enumerate(day_list):
                if i >= num_days:
                    break
                day = start_date + timedelta(days=i)
                iso_key = f"{day.isoformat()}T00:00:00.000Z"
                raw_val = day_data["availability"] if isinstance(day_data, dict) else day_data
                status = _AVAILABILITY_MAP.get(raw_val, AvailabilityStatus.NOT_AVAILABLE)
                if status in _WINDOW_STATUSES and wa_release_date(day) > today:
                    status = AvailabilityStatus.NYR
                availabilities[iso_key] = status

            campsites[res_id] = CampsiteAvailability(
                campsite_id=res_id,
                # Bare resource_id; engine enriches with cached human name from
                # wa_state_sites if the metadata seeder has populated it.
                site=str(res_id),
                loop="",
                campsite_type="STANDARD",
                type_of_use="Overnight",
                min_num_people=0,
                max_num_people=8,  # default; GoingToCamp doesn't expose per-site capacity
                max_people_known=False,
                availabilities=availabilities,
            )

        return campsites
