"""CLI entry point: python -m pnw_campsites <command>"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import date

from dotenv import load_dotenv

from pnw_campsites.providers.recgov import RecGovClient
from pnw_campsites.registry.db import CampgroundRegistry
from pnw_campsites.search.engine import (
    SearchEngine,
    SearchQuery,
    days,
    next_weekend,
    this_weekend,
)
from pnw_campsites.urls import recgov_availability_url, recgov_campsite_booking_url


def _parse_dates(date_str: str) -> tuple[date, date]:
    """Parse date range: 'YYYY-MM-DD:YYYY-MM-DD' or 'this-weekend' etc."""
    if date_str == "this-weekend":
        return this_weekend()
    if date_str == "next-weekend":
        return next_weekend()
    if ":" in date_str:
        start, end = date_str.split(":")
        return date.fromisoformat(start), date.fromisoformat(end)
    # Single date — treat as one-day range
    d = date.fromisoformat(date_str)
    return d, d


def _parse_days(days_str: str) -> set[int]:
    """Parse day names: 'thu,fri,sat,sun' or presets like 'weekend'."""
    presets = {
        "weekend": {4, 5, 6},
        "long-weekend": {3, 4, 5, 6},
        "weekdays": {0, 1, 2, 3, 4},
    }
    if days_str in presets:
        return presets[days_str]
    return days(*days_str.split(","))


def _format_results(results, show_urls: bool = True) -> None:
    """Print search results in a clean, readable format."""
    print(f"Searched {results.campgrounds_checked} campgrounds")
    print(f"Found availability at {results.campgrounds_with_availability} campgrounds")

    if not results.has_availability:
        print("\nNo availability found for this search.")
        return

    print()
    for r in results.results:
        if r.error:
            print(f"[ERROR] {r.campground.name}: {r.error}")
            continue
        if r.total_available_sites == 0:
            continue

        cg = r.campground
        # Summary line with FCFS context
        parts = [f"{r.total_available_sites} reservable"]
        if r.fcfs_sites:
            parts.append(f"{r.fcfs_sites} FCFS")
        summary = ", ".join(parts)
        print(f"=== {cg.name} ({cg.state}) — {summary} ===")
        if show_urls:
            reservable_windows = [w for w in r.available_windows if not w.is_fcfs]
            start = (
                date.fromisoformat(reservable_windows[0].start_date)
                if reservable_windows else None
            )
            print(f"  Book: {recgov_availability_url(cg.facility_id, start)}")

        # Group windows by site
        by_site: dict[str, list] = {}
        for w in r.available_windows:
            by_site.setdefault(w.site_name, []).append(w)

        for site_name, windows in sorted(by_site.items()):
            w0 = windows[0]
            if w0.is_fcfs:
                print(
                    f"  Site {site_name} ({w0.loop}, {w0.campsite_type})"
                    " — FCFS, not bookable online"
                )
            else:
                print(f"  Site {site_name} ({w0.loop}, {w0.campsite_type}, max {w0.max_people}p)")
                for w in windows:
                    d = date.fromisoformat(w.start_date)
                    day_name = d.strftime("%a")
                    print(f"    {day_name} {w.start_date} → {w.end_date} ({w.nights}n)")
        print()


async def cmd_search(args: argparse.Namespace) -> None:
    """Run a discovery search."""
    load_dotenv()
    api_key = os.getenv("RIDB_API_KEY")
    if not api_key:
        print("ERROR: RIDB_API_KEY not set in .env")
        sys.exit(1)

    start_date, end_date = _parse_dates(args.dates)
    days_of_week = _parse_days(args.days) if args.days else None

    query = SearchQuery(
        state=args.state,
        start_date=start_date,
        end_date=end_date,
        min_consecutive_nights=args.nights,
        days_of_week=days_of_week,
        tags=args.tags.split(",") if args.tags else None,
        max_drive_minutes=args.max_drive,
        name_like=args.name,
        include_group_sites=not args.no_groups,
        include_fcfs=args.include_fcfs,
        max_people=args.people,
        max_campgrounds=args.limit,
    )

    registry = CampgroundRegistry()
    async with RecGovClient(ridb_api_key=api_key) as client:
        engine = SearchEngine(registry, client)
        results = await engine.search(query)

    _format_results(results)
    registry.close()


async def cmd_check(args: argparse.Namespace) -> None:
    """Check a specific campground."""
    load_dotenv()
    api_key = os.getenv("RIDB_API_KEY")
    if not api_key:
        print("ERROR: RIDB_API_KEY not set in .env")
        sys.exit(1)

    start_date, end_date = _parse_dates(args.dates)

    registry = CampgroundRegistry()
    async with RecGovClient(ridb_api_key=api_key) as client:
        engine = SearchEngine(registry, client)
        result = await engine.check_specific(
            facility_id=args.facility_id,
            start_date=start_date,
            end_date=end_date,
            min_nights=args.nights,
        )

    cg = result.campground
    print(f"{cg.name} (facility_id={cg.facility_id})")
    print(f"Book: {recgov_availability_url(cg.facility_id, start_date)}")

    if result.error:
        print(f"Error: {result.error}")
    elif result.total_available_sites == 0:
        print("No availability found.")
    else:
        print(f"{result.total_available_sites} sites with availability:\n")
        by_site: dict[str, list] = {}
        for w in result.available_windows:
            by_site.setdefault(w.site_name, []).append(w)

        for site_name, windows in sorted(by_site.items()):
            w0 = windows[0]
            print(f"  Site {site_name} ({w0.loop}, {w0.campsite_type}, max {w0.max_people}p)")
            for w in windows:
                d = date.fromisoformat(w.start_date)
                day_name = d.strftime("%a")
                book_url = recgov_campsite_booking_url(
                    cg.facility_id, w.campsite_id, d,
                    date.fromisoformat(w.end_date),
                )
                print(f"    {day_name} {w.start_date} → {w.end_date} ({w.nights}n)")
                print(f"      Book: {book_url}")

    registry.close()


async def cmd_list(args: argparse.Namespace) -> None:
    """List campgrounds in the registry."""
    registry = CampgroundRegistry()
    results = registry.search(
        state=args.state,
        tags=args.tags.split(",") if args.tags else None,
        max_drive_minutes=args.max_drive,
        name_like=args.name,
    )
    print(f"Found {len(results)} campgrounds:\n")
    for cg in results:
        tags = f" [{', '.join(cg.tags)}]" if cg.tags else ""
        drive = f" ~{cg.drive_minutes_from_base}min" if cg.drive_minutes_from_base else ""
        print(f"  {cg.name} ({cg.state}, id={cg.facility_id}){drive}{tags}")
    registry.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="pnw_campsites",
        description="PNW campsite discovery and monitoring",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # --- search ---
    p_search = sub.add_parser("search", help="Search for available campsites")
    p_search.add_argument("--dates", required=True,
                          help="Date range: YYYY-MM-DD:YYYY-MM-DD or this-weekend/next-weekend")
    p_search.add_argument("--state", help="Filter by state: WA, OR, ID")
    p_search.add_argument("--nights", type=int, default=2,
                          help="Minimum consecutive nights (default: 2)")
    p_search.add_argument("--days", help="Days of week: thu,fri,sat,sun or weekend/long-weekend")
    p_search.add_argument("--tags", help="Comma-separated tags: lakeside,river,kid-friendly")
    p_search.add_argument("--max-drive", type=int, help="Max drive minutes from Bellevue")
    p_search.add_argument("--name", help="Filter by campground name (substring match)")
    p_search.add_argument("--people", type=int, help="Min site capacity")
    p_search.add_argument("--no-groups", action="store_true", help="Exclude group sites")
    p_search.add_argument("--include-fcfs", action="store_true",
                          help="Include FCFS (first-come-first-served) site details")
    p_search.add_argument("--limit", type=int, default=20,
                          help="Max campgrounds to check (default: 20)")

    # --- check ---
    p_check = sub.add_parser("check", help="Check a specific campground")
    p_check.add_argument("facility_id", help="Recreation.gov facility ID")
    p_check.add_argument("--dates", required=True,
                         help="Date range: YYYY-MM-DD:YYYY-MM-DD or this-weekend/next-weekend")
    p_check.add_argument("--nights", type=int, default=1,
                         help="Minimum consecutive nights (default: 1)")

    # --- list ---
    p_list = sub.add_parser("list", help="List campgrounds in the registry")
    p_list.add_argument("--state", help="Filter by state")
    p_list.add_argument("--tags", help="Comma-separated tags to filter by")
    p_list.add_argument("--max-drive", type=int, help="Max drive minutes from Bellevue")
    p_list.add_argument("--name", help="Filter by name (substring match)")

    args = parser.parse_args()

    if args.command == "search":
        asyncio.run(cmd_search(args))
    elif args.command == "check":
        asyncio.run(cmd_check(args))
    elif args.command == "list":
        asyncio.run(cmd_list(args))


if __name__ == "__main__":
    main()
