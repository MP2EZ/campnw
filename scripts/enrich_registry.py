#!/usr/bin/env python3
"""
Enrich the campground registry with data from RIDB and GoingToCamp.

- RIDB: per-campsite attributes → auto-generated tags, parent rec area → region
- GoingToCamp: park-level amenities → tags, descriptions

Usage:
    python scripts/enrich_registry.py              # Enrich all
    python scripts/enrich_registry.py --source recgov   # RIDB only
    python scripts/enrich_registry.py --source wa-state  # GoingToCamp only
    python scripts/enrich_registry.py --dry-run     # Preview without writing
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time

from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from pnw_campsites.providers.recgov import RecGovClient
from pnw_campsites.registry.db import CampgroundRegistry
from pnw_campsites.registry.models import BookingSystem

# ---------------------------------------------------------------------------
# RIDB attribute → tag mapping
# ---------------------------------------------------------------------------

# Site-level attributes that generate campground-level tags
# We scan all sites at a campground — if ANY site has the attribute, the
# campground gets the tag.
RIDB_ATTRIBUTE_TAGS = {
    # Proximity to water
    "Proximity to Water": {
        "Riverfront": "riverside",
        "Lakefront": "lakeside",
        "Stream": "riverside",
        "On River": "riverside",
        "On Lake": "lakeside",
        "Island": "waterfront",
        "Ocean": "ocean",
        "Bay": "waterfront",
    },
    # Shade
    "Shade": {
        "Yes": "shade",
    },
    # Pets
    "Pets Allowed": {
        "Yes": "pet-friendly",
    },
    # Campfire
    "Campfire Allowed": {
        "Yes": "campfire",
    },
    # Driveway entry (for RV)
    "Driveway Entry": {
        "Pull-Through": "pull-through",
    },
}

# If a campground has any site with RV or Trailer in permitted equipment
RV_EQUIPMENT_NAMES = {"RV", "Trailer"}

# Campsite types that indicate tent-only
TENT_ONLY_TYPES = {"TENT ONLY NONELECTRIC", "TENT ONLY ELECTRIC", "WALK TO"}


async def enrich_recgov(registry: CampgroundRegistry, dry_run: bool = False) -> None:
    """Enrich rec.gov campgrounds with RIDB campsite attributes and metadata."""
    load_dotenv()
    api_key = os.getenv("RIDB_API_KEY")
    if not api_key:
        print("ERROR: RIDB_API_KEY not set in .env")
        return

    campgrounds = registry.search(booking_system=BookingSystem.RECGOV)
    print(f"Enriching {len(campgrounds)} rec.gov campgrounds from RIDB...")

    async with RecGovClient(ridb_api_key=api_key) as client:
        enriched = 0
        for i, cg in enumerate(campgrounds):
            try:
                sites = await client.get_facility_campsites(cg.facility_id)
            except Exception as e:
                print(f"  Skip {cg.name}: {e}")
                continue

            if not sites:
                continue

            # Collect tags from site attributes
            tags = set(cg.tags)  # preserve existing tags
            has_rv = False
            has_tent_only = False
            total_sites = len(sites)

            for site in sites:
                # Check attributes
                for attr in site.get("ATTRIBUTES", []):
                    attr_name = attr.get("AttributeName", "")
                    attr_value = attr.get("AttributeValue", "")
                    if attr_name in RIDB_ATTRIBUTE_TAGS:
                        tag = RIDB_ATTRIBUTE_TAGS[attr_name].get(attr_value)
                        if tag:
                            tags.add(tag)

                # Check equipment
                for eq in site.get("PERMITTEDEQUIPMENT", []):
                    if eq.get("EquipmentName") in RV_EQUIPMENT_NAMES:
                        has_rv = True

                # Check site type
                site_type = site.get("CampsiteType", "")
                if site_type in TENT_ONLY_TYPES:
                    has_tent_only = True

            if has_rv:
                tags.add("rv-friendly")
            if has_tent_only and not has_rv:
                tags.add("tent-only")

            new_tags = sorted(tags)
            changed = new_tags != sorted(cg.tags) or total_sites != cg.total_sites

            if changed:
                if dry_run:
                    added = set(new_tags) - set(cg.tags)
                    if added:
                        print(f"  {cg.name}: +{added}")
                else:
                    registry.update_tags(cg.id, new_tags)
                    if total_sites != cg.total_sites:
                        registry._conn.execute(
                            "UPDATE campgrounds SET total_sites=? WHERE id=?",
                            (total_sites, cg.id),
                        )
                        registry._conn.commit()
                enriched += 1

            if (i + 1) % 25 == 0:
                print(f"  Processed {i + 1}/{len(campgrounds)}...")

    print(f"Enriched {enriched}/{len(campgrounds)} rec.gov campgrounds")


# ---------------------------------------------------------------------------
# GoingToCamp amenity → tag mapping
# ---------------------------------------------------------------------------

import re

# Extract tags from park descriptions via keyword matching
DESCRIPTION_KEYWORD_TAGS: list[tuple[str, str]] = [
    (r"\blake\b", "lakeside"),
    (r"\briver\b", "riverside"),
    (r"\bocean\b|saltwater|shoreline|beach", "beach"),
    (r"\btrail", "trails"),
    (r"\bswim", "swimming"),
    (r"\bfish", "fishing"),
    (r"\bboat\b|boat launch|kayak", "boat-launch"),
    (r"\bplayground\b|kid|children", "kid-friendly"),
    (r"\bold.growth|ancient", "old-growth"),
    (r"\bwaterfall", "waterfall"),
    (r"\bhorse|equestrian", "equestrian"),
    (r"\bADA|wheelchair|accessible", "accessible"),
]


async def enrich_goingtocamp(
    registry: CampgroundRegistry, dry_run: bool = False
) -> None:
    """Enrich WA State Parks with data from GoingToCamp resourceLocation."""
    from pnw_campsites.providers.goingtocamp import GoingToCampClient

    campgrounds = registry.search(booking_system=BookingSystem.WA_STATE)
    print(f"Enriching {len(campgrounds)} WA State Parks from GoingToCamp...")

    async with GoingToCampClient() as client:
        # Fetch all park locations
        locations = await client.get_locations()

        # Index locations by resourceLocationId
        loc_by_id: dict[int, dict] = {}
        for loc in locations:
            loc_id = loc.get("resourceLocationId")
            if loc_id:
                loc_by_id[loc_id] = loc

        enriched = 0
        for cg in campgrounds:
            loc = loc_by_id.get(int(cg.facility_id))
            if not loc:
                continue

            tags = set(cg.tags)

            # Extract description
            description = ""
            localized = loc.get("localizedValues", [])
            if localized:
                description = localized[0].get("description", "")

            # Extract tags from description keywords
            if description:
                for pattern, tag in DESCRIPTION_KEYWORD_TAGS:
                    if re.search(pattern, description, re.IGNORECASE):
                        tags.add(tag)

            # Extract region from address
            region = ""
            address = loc.get("localizedValues", [{}])[0]
            city = address.get("city", "")
            if city:
                region = f"{city}, WA"

            new_tags = sorted(tags)
            changed = (
                new_tags != sorted(cg.tags)
                or (region and region != cg.region)
                or (description and not cg.notes)
            )

            if changed:
                if dry_run:
                    added = set(new_tags) - set(cg.tags)
                    info = []
                    if added:
                        info.append(f"+{added}")
                    if region and region != cg.region:
                        info.append(f"region={region}")
                    print(f"  {cg.name}: {', '.join(info)}")
                else:
                    registry.update_tags(cg.id, new_tags)
                    updates = []
                    params = []
                    if region and not cg.region:
                        updates.append("region=?")
                        params.append(region)
                    if description and not cg.notes:
                        # Store first 500 chars of description as notes
                        updates.append("notes=?")
                        params.append(description[:500])
                    if updates:
                        params.append(cg.id)
                        registry._conn.execute(
                            f"UPDATE campgrounds SET {', '.join(updates)} WHERE id=?",
                            params,
                        )
                        registry._conn.commit()
                enriched += 1

    print(f"Enriched {enriched}/{len(campgrounds)} WA State Parks")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def main(source: str | None, dry_run: bool) -> None:
    registry = CampgroundRegistry()

    if source in (None, "recgov"):
        await enrich_recgov(registry, dry_run)

    if source in (None, "wa-state"):
        await enrich_goingtocamp(registry, dry_run)

    if not dry_run:
        # Checkpoint WAL
        import sqlite3

        conn = sqlite3.connect(str(registry._db_path))
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.close()
        print("Registry checkpointed.")

    registry.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Enrich campground registry")
    parser.add_argument(
        "--source",
        choices=["recgov", "wa-state"],
        help="Enrich a single source (default: all)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without writing",
    )
    args = parser.parse_args()
    asyncio.run(main(args.source, args.dry_run))
