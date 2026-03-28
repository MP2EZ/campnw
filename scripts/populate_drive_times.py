#!/usr/bin/env python3
"""
Populate drive_minutes_from_base for all campgrounds with coordinates.

Uses haversine + terrain multiplier from Seattle, WA (default base).
Pure computation — no API calls, runs in <1 second.

Usage:
    python scripts/populate_drive_times.py              # Update registry
    python scripts/populate_drive_times.py --dry-run     # Preview only
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from pnw_campsites.geo import KNOWN_BASES, estimated_drive_minutes
from pnw_campsites.registry.db import CampgroundRegistry

BASE_LAT, BASE_LON = KNOWN_BASES["seattle"]


def populate(dry_run: bool = False) -> None:
    with CampgroundRegistry() as registry:
        all_cg = registry.list_all()
        with_coords = [cg for cg in all_cg if cg.latitude != 0.0]

        if not with_coords:
            print("No campgrounds with coordinates found.")
            return

        print(f"Computing drive times for {len(with_coords)} campgrounds from Seattle...\n")

        updated = 0
        for cg in with_coords:
            minutes = estimated_drive_minutes(BASE_LAT, BASE_LON, cg.latitude, cg.longitude)

            if dry_run:
                if cg.drive_minutes_from_base != minutes:
                    print(f"  {cg.name} [{cg.state}]: {cg.drive_minutes_from_base} -> {minutes} min")
                    updated += 1
            else:
                if cg.drive_minutes_from_base != minutes:
                    registry._conn.execute(
                        "UPDATE campgrounds SET drive_minutes_from_base=? "
                        "WHERE booking_system=? AND facility_id=?",
                        (minutes, cg.booking_system.value, cg.facility_id),
                    )
                    updated += 1

        if not dry_run:
            registry._conn.commit()

        print(f"{'Would update' if dry_run else 'Updated'}: {updated}/{len(with_coords)} campgrounds")


def main() -> None:
    parser = argparse.ArgumentParser(description="Populate drive times from Seattle")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    args = parser.parse_args()
    populate(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
