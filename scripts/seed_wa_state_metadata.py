#!/usr/bin/env python3
"""
Seed the registry with site/loop names for every WA State Park.

GoingToCamp's availability API returns no human-readable site identifiers —
only opaque integer IDs. This seeder fetches the per-park site list and
loop list from two undocumented metadata endpoints, caching them in the
wa_state_sites and wa_state_loops tables. The search engine then resolves
real names ("L03 · Lower Loop A") at availability-resolve time.

Re-run quarterly (sites get renamed/added rarely enough that this cadence is
fine), from a residential IP: GoingToCamp's WAF blocks Fly. A writing run also
exports every seeded row to the JSON fixture that prod imports at startup
(registry/wa_site_fixture.py), so commit the fixture afterwards.

The May 2026 run seeded only the first 25 parks alphabetically (through Fort
Townsend). The later parks most likely hit a GoingToCamp block mid-run, and the
seeder printed each error, skipped the park and still exited 0. Failed parks now
back off and retry, and any park still failing makes the run exit 1.

Usage:
    python scripts/seed_wa_state_metadata.py                 # all WA parks
    python scripts/seed_wa_state_metadata.py --dry-run       # preview, no writes
    python scripts/seed_wa_state_metadata.py --limit 5       # first N parks
    python scripts/seed_wa_state_metadata.py --only-missing  # parks with no sites yet
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

# Add src to path for direct script execution
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from pnw_campsites.providers.errors import RateLimitedError, WAFBlockedError
from pnw_campsites.providers.goingtocamp import GoingToCampClient
from pnw_campsites.registry.db import CampgroundRegistry
from pnw_campsites.registry.models import BookingSystem
from pnw_campsites.registry.wa_site_fixture import FIXTURE_PATH, export_wa_site_fixture

PARK_DELAY_S = 2.0
# A WAF block or 429 usually lifts within a minute or two; anything else
# (timeout, 5xx after the client's own retry) gets the same backoff.
RETRY_DELAYS_S = (30.0, 90.0)


def _extract_loops(maps: list[dict]) -> list[dict]:
    """Pull leaf loop maps from a park's full map tree.

    A leaf loop is any map under the park that has a localized title — the
    loop name. Excludes the root park map (which has no title) and any
    intermediate region maps that come back in the same response.
    """
    loops = []
    for m in maps:
        lv = m.get("localizedValues", [])
        title = lv[0].get("title") if lv else None
        if not title:
            continue
        loops.append({
            "map_id": m["mapId"],
            "title": title,
            "description": (lv[0].get("description") or "") if lv else "",
        })
    return loops


def _extract_sites(resources: dict) -> list[dict]:
    """Pull sites from /api/resourcelocation/resources response.

    Each site gets the first (and usually only) loop_map_id from its mapIds.
    The diagnostic across 7 diverse parks confirmed 0 sites in multiple loops
    (clean 1:N), with ~0.18% orphans having empty mapIds — those get NULL.

    Also captures per-site capacity (~96% populated) and allowedEquipment
    (~91%); ~4% of sites are special types (marine tents, picnic shelters)
    that report None for these fields.
    """
    sites = []
    for resource in resources.values():
        lv = resource.get("localizedValues", [])
        name = lv[0].get("name") if lv else None
        if not name:
            continue
        map_ids = resource.get("mapIds") or []
        sites.append({
            "resource_id": resource["resourceId"],
            "name": name,
            "loop_map_id": map_ids[0] if map_ids else None,
            "max_capacity": resource.get("maxCapacity"),
            "min_capacity": resource.get("minCapacity"),
            "allowed_equipment": resource.get("allowedEquipment") or [],
        })
    return sites


async def _fetch_park(client: GoingToCampClient, park_id: int) -> tuple[list, dict]:
    for delay in (*RETRY_DELAYS_S, None):
        try:
            maps = await client.get_park_maps(park_id)
            await asyncio.sleep(PARK_DELAY_S / 2)
            return maps, await client.get_park_resources(park_id)
        except (WAFBlockedError, RateLimitedError, OSError, ValueError) as e:
            if delay is None:
                raise
            print(f"      {type(e).__name__}: {e}; retrying in {delay:.0f}s")
            await asyncio.sleep(delay)


async def seed(
    dry_run: bool = False, limit: int | None = None, only_missing: bool = False,
) -> int:
    """Seed WA parks. Returns the number of parks that failed."""
    with CampgroundRegistry() as registry:
        wa_parks = [
            cg for cg in registry.list_all(enabled_only=False)
            if cg.booking_system == BookingSystem.WA_STATE
        ]
        wa_parks.sort(key=lambda cg: cg.name)
        if only_missing:
            seeded = {
                row[0] for row in registry._conn.execute(
                    "SELECT DISTINCT park_facility_id FROM wa_state_sites"
                )
            }
            wa_parks = [cg for cg in wa_parks if cg.facility_id not in seeded]
        if limit:
            wa_parks = wa_parks[:limit]

        total = len(wa_parks)
        print(f"Enriching {total} WA State Parks "
              f"({'DRY RUN' if dry_run else 'WRITING'})")

        failed: list[str] = []
        async with GoingToCampClient() as client:
            for i, park in enumerate(wa_parks, start=1):
                try:
                    maps, resources = await _fetch_park(client, int(park.facility_id))
                    loops = _extract_loops(maps)
                    sites = _extract_sites(resources)
                except Exception as e:
                    print(f"  [{i}/{total}] {park.name}: ERROR {type(e).__name__}: {e}")
                    failed.append(park.name)
                    continue

                orphans = sum(1 for s in sites if s["loop_map_id"] is None)
                print(f"  [{i}/{total}] {park.name}: "
                      f"{len(sites)} sites, {len(loops)} loops"
                      + (f", {orphans} orphans" if orphans else ""))
                if not sites:
                    failed.append(park.name)

                if not dry_run and sites:
                    registry.bulk_upsert_wa_loops(park.facility_id, loops)
                    registry.bulk_upsert_wa_sites(park.facility_id, sites)

                await asyncio.sleep(PARK_DELAY_S / 2)

        if not dry_run:
            loop_count, site_count = export_wa_site_fixture(registry._conn)
            print(f"\nDone. Exported {site_count} sites, {loop_count} loops "
                  f"to {FIXTURE_PATH}")
        if failed:
            print(f"\n{len(failed)} park(s) failed or had no sites: {', '.join(failed)}")
        return len(failed)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Cache human site/loop names for WA State Parks"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview counts without writing to database",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only process the first N parks (for iteration)",
    )
    parser.add_argument(
        "--only-missing",
        action="store_true",
        help="Skip parks that already have sites (resume an interrupted run)",
    )
    args = parser.parse_args()
    failed = asyncio.run(
        seed(dry_run=args.dry_run, limit=args.limit, only_missing=args.only_missing)
    )
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
