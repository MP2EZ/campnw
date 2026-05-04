#!/usr/bin/env python3
"""
Seed the registry with site/loop names for every WA State Park.

GoingToCamp's availability API returns no human-readable site identifiers —
only opaque integer IDs. This seeder fetches the per-park site list and
loop list from two undocumented metadata endpoints, caching them in the
wa_state_sites and wa_state_loops tables. The search engine then resolves
real names ("L03 · Lower Loop A") at availability-resolve time.

One-time enrichment task. Re-run quarterly (sites get renamed/added rarely
enough that this cadence is fine).

Usage:
    python scripts/seed_wa_state_metadata.py                # all WA parks
    python scripts/seed_wa_state_metadata.py --dry-run      # preview, no writes
    python scripts/seed_wa_state_metadata.py --limit 5      # iterate on a small subset
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

# Add src to path for direct script execution
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from pnw_campsites.providers.goingtocamp import GoingToCampClient
from pnw_campsites.registry.db import CampgroundRegistry
from pnw_campsites.registry.models import BookingSystem


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
        })
    return sites


async def seed(dry_run: bool = False, limit: int | None = None) -> None:
    with CampgroundRegistry() as registry:
        wa_parks = [
            cg for cg in registry.list_all(enabled_only=False)
            if cg.booking_system == BookingSystem.WA_STATE
        ]
        wa_parks.sort(key=lambda cg: cg.name)
        if limit:
            wa_parks = wa_parks[:limit]

        total = len(wa_parks)
        print(f"Enriching {total} WA State Parks "
              f"({'DRY RUN' if dry_run else 'WRITING'})")

        async with GoingToCampClient() as client:
            for i, park in enumerate(wa_parks, start=1):
                park_id = int(park.facility_id)
                try:
                    maps = await client.get_park_maps(park_id)
                    resources = await client.get_park_resources(park_id)
                except Exception as e:
                    print(f"  [{i}/{total}] {park.name}: ERROR {e}")
                    continue

                loops = _extract_loops(maps)
                sites = _extract_sites(resources)
                orphans = sum(1 for s in sites if s["loop_map_id"] is None)

                print(f"  [{i}/{total}] {park.name}: "
                      f"{len(sites)} sites, {len(loops)} loops"
                      + (f", {orphans} orphans" if orphans else ""))

                if not dry_run:
                    registry.bulk_upsert_wa_loops(park.facility_id, loops)
                    registry.bulk_upsert_wa_sites(park.facility_id, sites)

                # Polite ~1s rate limit between parks
                await asyncio.sleep(1.0)

        if not dry_run:
            site_count = registry._conn.execute(
                "SELECT COUNT(*) FROM wa_state_sites"
            ).fetchone()[0]
            loop_count = registry._conn.execute(
                "SELECT COUNT(*) FROM wa_state_loops"
            ).fetchone()[0]
            print(f"\nDone. wa_state_sites={site_count}, wa_state_loops={loop_count}")


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
    args = parser.parse_args()
    asyncio.run(seed(dry_run=args.dry_run, limit=args.limit))


if __name__ == "__main__":
    main()
