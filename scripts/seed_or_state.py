#!/usr/bin/env python3
"""
Seed the campground registry with Oregon State Parks from ReserveAmerica.

Uses a curated list of known park IDs + slugs, then fetches metadata
(name, coordinates, total sites) from the RA availability page.

Usage:
    python scripts/seed_or_state.py             # Seed all OR State Parks
    python scripts/seed_or_state.py --dry-run   # Preview without writing
    python scripts/seed_or_state.py --probe     # Discover parks by probing ID range
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time

from curl_cffi import requests as cffi_requests

# Add src to path for direct script execution
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from pnw_campsites.registry.db import CampgroundRegistry
from pnw_campsites.registry.models import BookingSystem, Campground

# Regex to extract Redux state from RA SSR HTML
_REDUX_RE = re.compile(r'(\{"application":\{.+\})\s*</script>')

# Curated list of Oregon State Parks with camping on ReserveAmerica.
# Format: (park_id, slug)
# Slugs are from the RA URL: /explore/{slug}/OR/{park_id}/campsite-availability
OR_PARKS: list[tuple[str, str]] = [
    # Sourced from stateparks.oregon.gov reservation links (2026-03-28)
    ("402126", "beverly-beach-state-park"),
    ("402130", "devils-lake-state-recreation-area"),
    ("402146", "cape-lookout-state-park"),
    ("402155", "beachside-state-recreation-site"),
    ("402165", "south-beach-state-park"),
    ("402178", "fort-stevens-state-park"),
    ("402191", "nehalem-bay-state-park"),
    ("402235", "silver-falls-state-park"),
    ("402241", "detroit-lake-state-recreation-area"),
    ("402247", "benson-state-recreation-area"),
    ("402251", "dabney-state-recreation-area"),
    ("402257", "guy--w-talbot-state-park"),
    ("402267", "memaloose-state-park"),
    ("402284", "milo-mciver-state-park"),
    ("402294", "ll-stub-stewart-memorial-state-park"),
    ("402334", "jessie-m-honeyman-memorial-state-park"),
    ("402343", "umpqua-lighthouse-state-park"),
    ("402346", "william-m-tugman-state-park"),
    ("402348", "carl-g-washburne-memorial-state-park"),
    ("402363", "valley-of-the-rogue-state-park"),
    ("402382", "sunset-bay-state-park"),
    ("402385", "cape-blanco-state-park"),
    ("402388", "humbug-mountain-state-park"),
    ("402398", "bullards-beach-state-park"),
    ("402446", "cove-palisades-state-park"),
    ("402450", "jasper-point-state-park"),
    ("402461", "prineville-reservoir-state-park"),
    ("402465", "deschutes-river-state-recreation-area"),
    ("402479", "lapine-state-park"),
    ("402486", "tumalo-state-park"),
    ("402488", "collier-memorial-state-park"),
    ("402499", "emigrant-springs-state-heritage-area"),
    ("405202", "maud-williamson-state-recreation-site"),
    ("405203", "sarah-helmick-state-recreation-site"),
    ("405209", "willamette-mission-state-park"),
    ("405213", "champoeg-state-heritage-area"),
    ("405214", "molalla-river-state-park"),
    ("405225", "elijah-bristow-state-park"),
    ("405228", "fall-creek-state-recreation-area"),
    ("405229", "jasper-state-recreation-site"),
    ("405231", "lowell-state-recreation-site"),
    ("405326", "alfred-a-loeb-state-park"),
    ("405331", "harris-beach-state-park"),
    ("405408", "wallowa-lake-state-park"),
    ("405413", "farewell-bend-state-recreation-area"),
    ("405415", "lake-owyhee-state-park"),
    ("405422", "clyde-holliday-state-recreation-site"),
    ("405428", "unity-lake-state-recreation-site"),
    ("409102", "cottonwood-canyon-state-park"),
    ("409402", "ainsworth-state-park"),
    ("409502", "viento-state-park"),
    ("410302", "touvelle-state-recreation-site"),
    ("411602", "arizona-beach-state-rec-area"),
]


def fetch_park_metadata(
    park_id: str, slug: str, session: cffi_requests.Session,
) -> dict | None:
    """Fetch park name, coordinates, and total sites from RA availability page."""
    url = (
        f"https://www.reserveamerica.com/explore/{slug}/OR/{park_id}"
        f"/campsite-availability"
    )
    try:
        resp = session.get(url, timeout=30)
        if resp.status_code != 200:
            return None

        match = _REDUX_RE.search(resp.text)
        if not match:
            return None

        data = json.loads(match.group(1))
        fac = data.get("backend", {}).get("facility", {}).get("facility", {})
        total = (
            data.get("backend", {})
            .get("productSearch", {})
            .get("searchResults", {})
            .get("totalRecords", 0)
        )

        coords = fac.get("coordinates", {})
        return {
            "name": fac.get("name", slug.replace("-", " ").title()),
            "latitude": coords.get("latitude", 0.0),
            "longitude": coords.get("longitude", 0.0),
            "total_sites": total,
        }
    except Exception as e:
        print(f"  Error fetching {park_id}: {e}")
        return None


def probe_id_range(
    start: int, end: int, session: cffi_requests.Session,
) -> list[tuple[str, str, dict]]:
    """Probe a range of RA park IDs to discover valid Oregon parks."""
    found: list[tuple[str, str, dict]] = []
    for pid in range(start, end + 1):
        # Try the facility page directly — RA redirects if slug is wrong
        url = (
            f"https://www.reserveamerica.com/explore/park/OR/{pid}"
            f"/campsite-availability"
        )
        try:
            resp = session.get(url, timeout=15, allow_redirects=True)
            if resp.status_code != 200:
                continue

            # Extract slug from redirect URL
            final_url = str(resp.url)
            slug_match = re.search(r"/explore/([^/]+)/OR/", final_url)
            if not slug_match:
                continue
            slug = slug_match.group(1)

            match = _REDUX_RE.search(resp.text)
            if not match:
                continue

            data = json.loads(match.group(1))
            fac = data.get("backend", {}).get("facility", {}).get("facility", {})
            name = fac.get("name", "")
            if not name:
                continue

            total = (
                data.get("backend", {})
                .get("productSearch", {})
                .get("searchResults", {})
                .get("totalRecords", 0)
            )
            coords = fac.get("coordinates", {})

            meta = {
                "name": name,
                "latitude": coords.get("latitude", 0.0),
                "longitude": coords.get("longitude", 0.0),
                "total_sites": total,
            }
            found.append((str(pid), slug, meta))
            print(f"  FOUND: {pid} → {name} ({slug}), {total} sites")
        except Exception:
            pass

        time.sleep(0.5)  # be polite

        # Progress indicator every 50 IDs
        if (pid - start) % 50 == 0 and pid != start:
            print(f"  Probed {pid - start}/{end - start} IDs...")

    return found


def seed(dry_run: bool = False, probe: bool = False) -> None:
    session = cffi_requests.Session(impersonate="chrome131")

    if probe:
        print("Probing RA park ID range 402100-402250 for Oregon parks...")
        found = probe_id_range(402100, 402250, session)
        print(f"\nFound {len(found)} parks")
        for pid, slug, meta in found:
            print(f'    ("{pid}", "{slug}"),  # {meta["name"]}, {meta["total_sites"]} sites')
        session.close()
        return

    campgrounds: list[Campground] = []
    total = len(OR_PARKS)

    for i, (park_id, slug) in enumerate(OR_PARKS):
        print(f"[{i + 1}/{total}] Fetching {slug} ({park_id})...", end=" ")
        meta = fetch_park_metadata(park_id, slug, session)

        if meta:
            cg = Campground(
                facility_id=park_id,
                name=meta["name"],
                booking_system=BookingSystem.OR_STATE,
                state="OR",
                latitude=meta["latitude"],
                longitude=meta["longitude"],
                total_sites=meta["total_sites"],
                booking_url_slug=slug,
                enabled=True,
            )
            campgrounds.append(cg)
            print(f"✓ {meta['name']} ({meta['total_sites']} sites)")
        else:
            print("✗ failed")

        # Rate limit
        if i < total - 1:
            time.sleep(1.0)

    session.close()

    campgrounds.sort(key=lambda c: c.name)
    print(f"\nSuccessfully fetched {len(campgrounds)}/{total} parks")

    if dry_run:
        print("\n[DRY RUN] Would insert these parks:")
        for cg in campgrounds:
            print(
                f"  {cg.name} (id={cg.facility_id}, slug={cg.booking_url_slug}, "
                f"sites={cg.total_sites}, lat={cg.latitude:.4f}, lon={cg.longitude:.4f})"
            )
        return

    with CampgroundRegistry() as registry:
        count = registry.bulk_upsert(campgrounds)
        total_all = registry.count(enabled_only=False)
        print(f"\nInserted/updated {count} OR State Parks. Registry now has {total_all} total.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed Oregon State Parks from ReserveAmerica"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview results without writing to database",
    )
    parser.add_argument(
        "--probe",
        action="store_true",
        help="Probe RA park ID range to discover parks",
    )
    args = parser.parse_args()
    seed(dry_run=args.dry_run, probe=args.probe)


if __name__ == "__main__":
    main()
