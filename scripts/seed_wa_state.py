#!/usr/bin/env python3
"""
Seed the campground registry with WA State Parks from GoingToCamp.

Pulls all park locations with campsite resources from the GoingToCamp API
and inserts them into the local SQLite registry with booking_system=wa_state.

Usage:
    python scripts/seed_wa_state.py             # Seed all WA State Parks
    python scripts/seed_wa_state.py --dry-run   # Preview without writing
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
from pnw_campsites.registry.models import BookingSystem, Campground


def location_to_campground(loc: dict) -> Campground:
    """Convert a GoingToCamp resource location to a registry Campground."""
    name = loc.get("localizedValues", [{}])[0].get("fullName", "Unknown")
    return Campground(
        facility_id=str(loc["resourceLocationId"]),
        name=name,
        booking_system=BookingSystem.WA_STATE,
        state="WA",
        enabled=True,
    )


async def seed(dry_run: bool = False) -> None:
    async with GoingToCampClient() as client:
        locations = await client.get_campground_locations()
        print(f"Found {len(locations)} WA State Parks with campsites")

        campgrounds = [location_to_campground(loc) for loc in locations]

    campgrounds.sort(key=lambda c: c.name)

    if dry_run:
        print("\n[DRY RUN] Would insert these parks:")
        for cg in campgrounds:
            print(f"  {cg.name} (facility_id={cg.facility_id})")
        return

    with CampgroundRegistry() as registry:
        count = registry.bulk_upsert(campgrounds)
        total = registry.count(enabled_only=False)
        print(f"\nInserted/updated {count} WA State Parks. Registry now has {total} total.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed WA State Parks from GoingToCamp")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview results without writing to database",
    )
    args = parser.parse_args()
    asyncio.run(seed(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
