#!/usr/bin/env python3
"""
Seed the campground registry from RIDB.

Pulls all camping facilities for WA, OR, and ID from the Recreation.gov
RIDB API, filters to actual campgrounds, and inserts into the local
SQLite registry.

Usage:
    python scripts/seed_registry.py              # Seed all 3 states
    python scripts/seed_registry.py --state WA   # Seed WA only
    python scripts/seed_registry.py --dry-run     # Preview without writing
"""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys

from dotenv import load_dotenv

# Add src to path for direct script execution
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from pnw_campsites.providers.recgov import RecGovClient
from pnw_campsites.registry.db import CampgroundRegistry
from pnw_campsites.registry.models import BookingSystem, Campground, RIDBFacility

# Patterns that indicate a facility is NOT an actual campground
EXCLUDE_PATTERNS = re.compile(
    r"""
    \b(kitchen|pavilion|picnic|shelter|amphitheater|amphitheatre|
    visitor\s*center|ranger\s*station|ranger\s*district|
    lookout(?:\s*tower)?|cabin(?:\s*rental)?|guard\s*station|
    day\s*use|trailhead|boat\s*ramp|parking|dock|marina|
    office|headquarters|warehouse|storage|
    scenic\s*byway|scenic\s*area|corridor|highway|parkway|greenway|
    interpretive|heritage\s*site|
    ohv\s*area|grassland|
    \bsr\s*\d|\bus\s*highway)\b
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Bounding box — filter out facilities clearly outside the coverage area
# Covers WA/OR/ID + MT/WY/NorCal
REGION_BOUNDS = {
    "min_lat": 37.5,   # NorCal (includes Yosemite at ~37.7N)
    "max_lat": 49.1,   # northern WA border
    "min_lon": -125.0,  # Pacific coast
    "max_lon": -104.0,  # eastern WY border
}

# NorCal latitude cutoff — CA campgrounds south of this are excluded
NORCAL_MIN_LAT = 37.5


def is_campground(facility: RIDBFacility) -> bool:
    """Filter RIDB results to actual campgrounds."""
    name = facility.facility_name

    # Positive signal: names containing "campground" or "camp" are almost
    # always valid — RIDB activity=CAMPING already pre-selects these.
    if (
        not re.search(r"\b(campground|camp)\b", name, re.IGNORECASE)
        and EXCLUDE_PATTERNS.search(name)
    ):
        return False

    # Must have valid coordinates
    if facility.latitude == 0.0 and facility.longitude == 0.0:
        return False

    # Must be within coverage bounding box
    if not (
        REGION_BOUNDS["min_lat"] <= facility.latitude <= REGION_BOUNDS["max_lat"]
        and REGION_BOUNDS["min_lon"]
        <= facility.longitude
        <= REGION_BOUNDS["max_lon"]
    ):
        return False

    # Must be enabled
    return facility.enabled


def facility_to_campground(facility: RIDBFacility, state: str) -> Campground:
    """Convert an RIDB facility to a registry Campground."""
    return Campground(
        facility_id=str(facility.facility_id),
        name=facility.facility_name,
        booking_system=BookingSystem.RECGOV,
        latitude=facility.latitude,
        longitude=facility.longitude,
        state=state,
        enabled=True,
    )


async def fetch_state_facilities(
    client: RecGovClient, state: str
) -> list[RIDBFacility]:
    """Fetch all camping facilities for a state from RIDB."""
    print(f"  Fetching {state} facilities from RIDB...")
    facilities = await client.get_all_facilities(state=state)
    print(f"  Got {len(facilities)} raw facilities for {state}")
    return facilities


async def seed(states: list[str], dry_run: bool = False) -> None:
    load_dotenv()
    api_key = os.getenv("RIDB_API_KEY")
    if not api_key:
        print("ERROR: RIDB_API_KEY not set in .env")
        print("Sign up at https://ridb.recreation.gov (free)")
        sys.exit(1)

    async with RecGovClient(ridb_api_key=api_key) as client:
        all_campgrounds: list[Campground] = []

        for state in states:
            facilities = await fetch_state_facilities(client, state)
            campgrounds = []
            for f in facilities:
                if not is_campground(f):
                    continue
                # NorCal filter: exclude southern CA campgrounds
                if state == "CA" and f.latitude < NORCAL_MIN_LAT:
                    continue
                campgrounds.append(facility_to_campground(f, state))
            excluded = len(facilities) - len(campgrounds)
            print(f"  {state}: {len(campgrounds)} campgrounds ({excluded} filtered out)")
            all_campgrounds.extend(campgrounds)

    print(f"\nTotal: {len(all_campgrounds)} campgrounds across {', '.join(states)}")

    if dry_run:
        print("\n[DRY RUN] Would insert these campgrounds:")
        for cg in sorted(all_campgrounds, key=lambda c: (c.state, c.name)):
            print(f"  [{cg.state}] {cg.name} (facility_id={cg.facility_id})")
        return

    with CampgroundRegistry() as registry:
        count = registry.bulk_upsert(all_campgrounds)
        total = registry.count(enabled_only=False)
        print(f"\nInserted/updated {count} campgrounds. Registry now has {total} total.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed campground registry from RIDB")
    parser.add_argument(
        "--state",
        choices=["WA", "OR", "ID", "MT", "WY", "CA"],
        help="Seed a single state (default: all)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview results without writing to database",
    )
    args = parser.parse_args()

    states = [args.state] if args.state else ["WA", "OR", "ID", "MT", "WY", "CA"]
    asyncio.run(seed(states, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
