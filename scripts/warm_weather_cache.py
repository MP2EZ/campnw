#!/usr/bin/env python3
"""
Warm the weather normals cache from Visual Crossing API.

Each single-day query costs 1 record against the free-tier quota (1,000/day).
Automatically progresses through sample days: 15 → 1 → 8 → 22.
Just re-run the same command and it picks up where it left off.

    python scripts/warm_weather_cache.py                      # auto-progress
    python scripts/warm_weather_cache.py --state WA           # WA only
    python scripts/warm_weather_cache.py --limit 50           # cap at 50
    python scripts/warm_weather_cache.py --dry-run            # preview
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import UTC, datetime

from dotenv import load_dotenv

# Add src to path for direct script execution
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from pnw_campsites.providers.weather import SEASON_MONTHS, VisualCrossingClient
from pnw_campsites.registry.db import CampgroundRegistry

STATE_PRIORITY = {"WA": 0, "OR": 1, "ID": 2, "MT": 3, "WY": 4, "CA": 5}
SAMPLE_DAYS = [15, 1, 8, 22]  # Progressive tiers


def _find_work(
    registry: CampgroundRegistry,
    unique_campgrounds: list,
) -> list[tuple[int, list]]:
    """Find the next sample day with incomplete campgrounds.

    Returns list of (sample_day, campgrounds_to_fetch) for the first
    incomplete tier. Returns empty list if all tiers are complete.
    """
    for sample_day in SAMPLE_DAYS:
        # Find all fully-cached coordinates for this day in one query
        cached_coords = set()
        for row in registry._conn.execute(
            "SELECT lat_2dp, lon_2dp FROM weather_normals "
            "WHERE day = ? AND month BETWEEN 4 AND 10 "
            "GROUP BY lat_2dp, lon_2dp HAVING COUNT(DISTINCT month) >= ?",
            [sample_day, len(SEASON_MONTHS)],
        ).fetchall():
            cached_coords.add((row[0], row[1]))

        to_fetch = [
            cg for cg in unique_campgrounds
            if (round(cg.latitude, 2), round(cg.longitude, 2)) not in cached_coords
        ]
        if to_fetch:
            return [(sample_day, to_fetch)]
    return []


async def warm(
    api_key: str,
    *,
    state: str | None = None,
    limit: int = 1000,
    dry_run: bool = False,
) -> None:
    registry = CampgroundRegistry()

    # Get campgrounds, optionally filtered by state
    campgrounds = registry.search(state=state) if state else registry.list_all()
    campgrounds.sort(key=lambda cg: STATE_PRIORITY.get(cg.state, 99))

    # Dedup by rounded coordinates
    seen_coords: set[tuple[float, float]] = set()
    unique_campgrounds = []
    for cg in campgrounds:
        if not cg.latitude or not cg.longitude:
            continue
        key = (round(cg.latitude, 2), round(cg.longitude, 2))
        if key in seen_coords:
            continue
        seen_coords.add(key)
        unique_campgrounds.append(cg)

    # Find next incomplete tier
    work = _find_work(registry, unique_campgrounds)
    if not work:
        print(f"Registry: {len(campgrounds)} campgrounds")
        print(f"Unique coordinates: {len(unique_campgrounds)}")
        print(f"All {len(SAMPLE_DAYS)} tiers complete (days {SAMPLE_DAYS}). Nothing to do.")
        return

    sample_day, to_fetch = work[0]
    to_fetch = to_fetch[:limit]

    # Report tier status (single query per tier instead of per-campground)
    tier_status = []
    for sd in SAMPLE_DAYS:
        row = registry._conn.execute(
            "SELECT COUNT(DISTINCT lat_2dp || ',' || lon_2dp) FROM weather_normals "
            "WHERE day = ? AND month BETWEEN 4 AND 10 "
            "GROUP BY lat_2dp, lon_2dp HAVING COUNT(DISTINCT month) >= ?",
            [sd, len(SEASON_MONTHS)],
        ).fetchall()
        tier_status.append(f"day {sd}: {len(row)}/{len(unique_campgrounds)}")

    print(f"Registry: {len(campgrounds)} campgrounds")
    print(f"Unique coordinates: {len(unique_campgrounds)}")
    print(f"Tier progress: {', '.join(tier_status)}")
    print(f"Current pass: day {sample_day} ({len(to_fetch)} to fetch)", flush=True)

    if dry_run:
        for cg in to_fetch[:20]:
            print(f"  [dry-run] {cg.state} | {cg.name} ({cg.latitude}, {cg.longitude})")
        if len(to_fetch) > 20:
            print(f"  ... and {len(to_fetch) - 20} more")
        return

    async with VisualCrossingClient(api_key) as client:
        fetched = 0
        errors = 0
        for i, cg in enumerate(to_fetch, 1):
            if i > 1:
                await asyncio.sleep(2.0)
            # Build targets: only months not yet cached for this exact day
            lat_2dp = round(cg.latitude, 2)
            lon_2dp = round(cg.longitude, 2)
            cached_months = {
                r[0] for r in registry._conn.execute(
                    "SELECT month FROM weather_normals "
                    "WHERE lat_2dp = ? AND lon_2dp = ? AND day = ? "
                    "AND month BETWEEN 4 AND 10",
                    [lat_2dp, lon_2dp, sample_day],
                ).fetchall()
            }
            targets = [
                (m, sample_day)
                for m in SEASON_MONTHS
                if m not in cached_months
            ]
            if not targets:
                continue

            print(f"  [{i}/{len(to_fetch)}] {cg.state} | {cg.name} ({len(targets)} months) ... ", end="", flush=True)
            normals, rate_limited = await client.fetch_normals(cg.latitude, cg.longitude, targets)

            if normals:
                rows = [
                    {
                        "lat_2dp": round(cg.latitude, 2),
                        "lon_2dp": round(cg.longitude, 2),
                        "month": n["month"],
                        "day": n["day"],
                        "temp_high_f": n["temp_high_f"],
                        "temp_low_f": n["temp_low_f"],
                        "precip_pct": n["precip_pct"],
                        "fetched_at": datetime.now(UTC).isoformat(),
                    }
                    for n in normals
                ]
                registry.upsert_weather_normals(rows)
                fetched += 1
                print(f"{len(normals)} months cached")
            else:
                errors += 1
                print("FAILED")

            if rate_limited:
                print(f"\n  Rate limited after {fetched} campgrounds ({len(to_fetch) - i} remaining).")
                print("  Run again tomorrow to continue.")
                break

    print(f"\nDone: {fetched} fetched, {errors} errors")


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Warm weather normals cache")
    parser.add_argument("--dry-run", action="store_true", help="Preview without fetching")
    parser.add_argument("--state", type=str, help="Filter by state (e.g. WA)")
    parser.add_argument("--limit", type=int, default=1000, help="Max campgrounds to fetch")
    args = parser.parse_args()

    api_key = os.getenv("VISUAL_CROSSING_API_KEY")
    if not api_key and not args.dry_run:
        print("Error: VISUAL_CROSSING_API_KEY not set in environment or .env")
        sys.exit(1)

    asyncio.run(warm(api_key or "", state=args.state, limit=args.limit, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
