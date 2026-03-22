"""WA State Parks (GoingToCamp) API client.

Uses curl_cffi to bypass Azure WAF via Chrome TLS fingerprint impersonation.
The GoingToCamp API is hierarchical: maps contain links to child maps, and
availability data lives at the leaf level with individual campsite resources.
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta

from curl_cffi import requests as curl_requests

from pnw_campsites.registry.models import (
    AvailabilityStatus,
    CampgroundAvailability,
    CampsiteAvailability,
)

BASE_URL = "https://washington.goingtocamp.com"

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


class GoingToCampClient:
    """Async client for WA State Parks via GoingToCamp API."""

    def __init__(self) -> None:
        self._session: curl_requests.Session | None = None
        # resourceLocationId → park-level childMapId (from /api/maps links)
        self._park_map_ids: dict[int, int] = {}

    async def __aenter__(self) -> GoingToCampClient:
        self._session = curl_requests.Session(impersonate="chrome131")
        await self._load_park_map_index()
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._session:
            self._session.close()
            self._session = None

    async def _load_park_map_index(self) -> None:
        """Build resourceLocationId → park mapId index from the maps hierarchy.

        Each top-level map has mapLinks with resourceLocationId and childMapId.
        The childMapId is the park-specific map that contains loop/area sub-maps.
        """
        maps = await self._get("/api/maps")
        for m in maps:
            for link in m.get("mapLinks", []):
                rl_id = link.get("resourceLocationId")
                child_map = link.get("childMapId")
                if rl_id is not None and child_map is not None:
                    self._park_map_ids[rl_id] = child_map

    async def _get(self, path: str, params: dict | None = None) -> dict | list:
        """GET with WAF bypass, run in thread to avoid blocking the event loop."""
        return await asyncio.to_thread(self._get_sync, path, params)

    def _get_sync(self, path: str, params: dict | None = None) -> dict | list:
        assert self._session is not None
        resp = self._session.get(f"{BASE_URL}{path}", params=params, timeout=30)
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
        assert self._session is not None
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
        resp = self._session.get(
            f"{BASE_URL}/api/availability/map", params=params, timeout=30
        )
        resp.raise_for_status()
        return resp.json()

    def _build_campsites(
        self,
        resources: dict[str, list[dict]],
        start_date: date,
        end_date: date,
    ) -> dict[str, CampsiteAvailability]:
        """Convert GoingToCamp resource availability to CampsiteAvailability models."""
        campsites: dict[str, CampsiteAvailability] = {}
        num_days = (end_date - start_date).days + 1

        for res_id, day_list in resources.items():
            availabilities: dict[str, AvailabilityStatus] = {}
            for i, day_data in enumerate(day_list):
                if i >= num_days:
                    break
                day = start_date + timedelta(days=i)
                iso_key = f"{day.isoformat()}T00:00:00.000Z"
                raw_val = day_data["availability"] if isinstance(day_data, dict) else day_data
                availabilities[iso_key] = _AVAILABILITY_MAP.get(
                    raw_val, AvailabilityStatus.NOT_AVAILABLE
                )

            campsites[res_id] = CampsiteAvailability(
                campsite_id=res_id,
                site=f"WA-{res_id}",
                loop="",
                campsite_type="STANDARD",
                type_of_use="Overnight",
                min_num_people=0,
                max_num_people=8,  # default; GoingToCamp doesn't expose per-site capacity
                availabilities=availabilities,
            )

        return campsites
