#!/usr/bin/env python3
"""
Pre-compute accurate drive times from known bases using Mapbox Matrix API.

Replaces haversine estimates with real road-network routing for all
campgrounds in the registry. Results stored in the drive_times table.

Usage:
    python scripts/compute_drive_times.py                    # All 12 bases
    python scripts/compute_drive_times.py --base seattle     # Single base
    python scripts/compute_drive_times.py --dry-run          # Preview only
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from dotenv import load_dotenv

load_dotenv()

from pnw_campsites.geo import KNOWN_BASES
from pnw_campsites.mapbox import get_drive_times_matrix
from pnw_campsites.registry.db import CampgroundRegistry


async def compute_for_base(
    registry: CampgroundRegistry,
    base_name: str,
    base_coords: tuple[float, float],
    dry_run: bool = False,
) -> int:
    """Compute drive times from one base to all campgrounds."""
    all_cg = registry.list_all()
    with_coords = [cg for cg in all_cg if cg.latitude != 0.0 and cg.longitude != 0.0]

    if not with_coords:
        print(f"  [{base_name}] No campgrounds with coordinates found.")
        return 0

    destinations = [
        (f"{cg.booking_system.value}:{cg.facility_id}", cg.latitude, cg.longitude)
        for cg in with_coords
    ]

    print(f"  [{base_name}] Routing {len(destinations)} campgrounds...")
    results = await get_drive_times_matrix(base_coords, destinations)

    now = datetime.now().isoformat()
    rows = []
    no_route = 0
    for cg in with_coords:
        key = f"{cg.booking_system.value}:{cg.facility_id}"
        if key in results:
            data = results[key]
            rows.append({
                "base_name": base_name,
                "booking_system": cg.booking_system.value,
                "facility_id": cg.facility_id,
                "drive_minutes": data["drive_minutes"],
                "drive_miles": data["drive_miles"],
                "source": "mapbox",
                "computed_at": now,
            })
        else:
            no_route += 1

    if dry_run:
        print(f"  [{base_name}] Would upsert {len(rows)} rows ({no_route} no-route)")
        # Show a few examples
        for row in rows[:3]:
            print(f"    {row['booking_system']}:{row['facility_id']} = {row['drive_minutes']} min")
    else:
        registry.upsert_drive_times(rows)
        print(f"  [{base_name}] Upserted {len(rows)} rows ({no_route} no-route)")

    return len(rows)


async def main_async(bases: list[str], dry_run: bool) -> None:
    if not os.getenv("MAPBOX_ACCESS_TOKEN"):
        print("Error: MAPBOX_ACCESS_TOKEN not set in environment")
        sys.exit(1)

    with CampgroundRegistry() as registry:
        total = 0
        for i, base_name in enumerate(bases):
            coords = KNOWN_BASES[base_name]
            try:
                count = await compute_for_base(registry, base_name, coords, dry_run)
                total += count
            except Exception as e:
                print(f"  [{base_name}] FAILED: {e}")
                continue
            # Pause between bases to avoid rate limits
            if i < len(bases) - 1:
                await asyncio.sleep(5)

        action = "Would upsert" if dry_run else "Upserted"
        print(f"\n{action} {total} total drive times across {len(bases)} bases.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Pre-compute drive times using Mapbox Matrix API"
    )
    parser.add_argument(
        "--base",
        choices=list(KNOWN_BASES.keys()),
        help="Compute for a single base only (default: all)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview without writing to DB",
    )
    args = parser.parse_args()

    bases = [args.base] if args.base else list(KNOWN_BASES.keys())
    asyncio.run(main_async(bases, args.dry_run))


if __name__ == "__main__":
    main()
