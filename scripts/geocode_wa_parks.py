#!/usr/bin/env python3
"""
Geocode WA State Park campgrounds that lack coordinates.

Queries Nominatim for each park's lat/lon and updates the registry.
Rate-limited to 1 req/sec per Nominatim usage policy.

Usage:
    python scripts/geocode_wa_parks.py              # Update registry
    python scripts/geocode_wa_parks.py --dry-run     # Preview only
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import UTC, datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from pnw_campsites.geo import geocode_address
from pnw_campsites.registry.db import CampgroundRegistry


async def geocode_parks(dry_run: bool = False) -> None:
    with CampgroundRegistry() as registry:
        all_cg = registry.list_all()
        missing = [
            cg for cg in all_cg
            if cg.booking_system.value == "wa_state" and cg.latitude == 0.0
        ]

        if not missing:
            print("All WA State Parks already have coordinates.")
            return

        print(f"Found {len(missing)} WA State Parks without coordinates.\n")

        success = 0
        failed = []

        for cg in missing:
            query = f"{cg.name}, Washington State Park"
            try:
                lat, lon = await geocode_address(query)
                if dry_run:
                    print(f"  [DRY RUN] {cg.name} -> ({lat:.4f}, {lon:.4f})")
                else:
                    registry._conn.execute(
                        "UPDATE campgrounds SET latitude=?, longitude=?, updated_at=? "
                        "WHERE booking_system=? AND facility_id=?",
                        (lat, lon, datetime.now(UTC).isoformat(),
                         cg.booking_system.value, cg.facility_id),
                    )
                    registry._conn.commit()
                    print(f"  {cg.name} -> ({lat:.4f}, {lon:.4f})")
                success += 1
            except (ValueError, Exception) as e:
                print(f"  FAILED: {cg.name} — {e}")
                failed.append(cg.name)

            await asyncio.sleep(1.0)  # Nominatim rate limit

        print(f"\nGeocoded: {success}/{len(missing)}")
        if failed:
            print(f"Failed ({len(failed)}): {', '.join(failed)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Geocode WA State Parks")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    args = parser.parse_args()
    asyncio.run(geocode_parks(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
