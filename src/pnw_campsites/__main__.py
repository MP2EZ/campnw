"""CLI entry point: python -m pnw_campsites <command>"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import date

from dotenv import load_dotenv

from pnw_campsites.geo import format_drive_time
from pnw_campsites.monitor.db import Watch, WatchDB
from pnw_campsites.monitor.notify import notify_console, notify_ntfy
from pnw_campsites.monitor.watcher import poll_all
from pnw_campsites.providers.goingtocamp import GoingToCampClient
from pnw_campsites.providers.recgov import RecGovClient
from pnw_campsites.registry.db import CampgroundRegistry
from pnw_campsites.registry.models import BookingSystem
from pnw_campsites.search.engine import (
    SearchEngine,
    SearchQuery,
    days,
    next_weekend,
    this_weekend,
)
from pnw_campsites.urls import (
    recgov_availability_url,
    recgov_campsite_booking_url,
    wa_state_availability_url,
)


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

    warning_messages = {
        "rate_limited": "rec.gov rate limit — try fewer results or wait a minute",
        "waf_blocked": "WA State Parks blocked requests — try again later",
        "unavailable": "service issue",
    }
    for w in results.warnings:
        msg = warning_messages.get(w.kind, w.kind)
        print(f"Note: {w.count} campground(s) skipped ({msg})")

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
        # Summary line with FCFS context and drive time
        parts = [f"{r.total_available_sites} reservable"]
        if r.estimated_drive_minutes is not None:
            parts.insert(0, format_drive_time(r.estimated_drive_minutes))
        if r.fcfs_sites:
            parts.append(f"{r.fcfs_sites} FCFS")
        summary = ", ".join(parts)
        source = "WA Parks" if cg.booking_system == BookingSystem.WA_STATE else cg.state
        print(f"=== {cg.name} ({source}) — {summary} ===")
        if show_urls:
            reservable_windows = [w for w in r.available_windows if not w.is_fcfs]
            start = (
                date.fromisoformat(reservable_windows[0].start_date)
                if reservable_windows else None
            )
            if cg.booking_system == BookingSystem.WA_STATE:
                end = (
                    date.fromisoformat(reservable_windows[-1].end_date)
                    if reservable_windows else None
                )
                print(f"  Book: {wa_state_availability_url(cg.facility_id, start, end)}")
            else:
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


def _parse_booking_system(value: str | None) -> BookingSystem | None:
    """Parse --source flag to a BookingSystem."""
    if not value:
        return None
    mapping = {
        "recgov": BookingSystem.RECGOV,
        "wa-state": BookingSystem.WA_STATE,
        "wa_state": BookingSystem.WA_STATE,
    }
    result = mapping.get(value.lower())
    if result is None:
        print(f"ERROR: Unknown source '{value}'. Options: recgov, wa-state")
        sys.exit(1)
    return result


async def cmd_search(args: argparse.Namespace) -> None:
    """Run a discovery search."""
    load_dotenv()
    booking_system = _parse_booking_system(getattr(args, "source", None))

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
        from_location=getattr(args, "from_location", None),
        name_like=args.name,
        include_group_sites=not args.no_groups,
        include_fcfs=args.include_fcfs,
        max_people=args.people,
        max_campgrounds=args.limit,
        booking_system=booking_system,
    )

    # Determine which providers to initialize
    need_recgov = booking_system in (None, BookingSystem.RECGOV)
    need_goingtocamp = booking_system in (None, BookingSystem.WA_STATE)

    api_key = os.getenv("RIDB_API_KEY") if need_recgov else None
    if need_recgov and not api_key:
        if booking_system is None:
            # Searching all sources — proceed without rec.gov
            print("Note: RIDB_API_KEY not set; searching WA State Parks only")
            need_recgov = False
        else:
            print("ERROR: RIDB_API_KEY not set in .env")
            sys.exit(1)

    registry = CampgroundRegistry()
    recgov = RecGovClient(ridb_api_key=api_key) if need_recgov and api_key else None
    goingtocamp = GoingToCampClient() if need_goingtocamp else None

    try:
        if recgov:
            await recgov.__aenter__()
        if goingtocamp:
            await goingtocamp.__aenter__()

        engine = SearchEngine(registry, recgov, goingtocamp)
        results = await engine.search(query)
    finally:
        if recgov:
            await recgov.__aexit__(None, None, None)
        if goingtocamp:
            await goingtocamp.__aexit__(None, None, None)

    _format_results(results)
    registry.close()


async def cmd_check(args: argparse.Namespace) -> None:
    """Check a specific campground."""
    load_dotenv()
    booking_system = _parse_booking_system(getattr(args, "source", None))

    start_date, end_date = _parse_dates(args.dates)

    is_wa_state = booking_system == BookingSystem.WA_STATE

    if not is_wa_state:
        api_key = os.getenv("RIDB_API_KEY")
        if not api_key:
            print("ERROR: RIDB_API_KEY not set in .env")
            sys.exit(1)

    registry = CampgroundRegistry()
    recgov = None
    goingtocamp = None

    try:
        if is_wa_state:
            goingtocamp = GoingToCampClient()
            await goingtocamp.__aenter__()
        else:
            recgov = RecGovClient(ridb_api_key=api_key)
            await recgov.__aenter__()

        engine = SearchEngine(registry, recgov, goingtocamp)
        result = await engine.check_specific(
            facility_id=args.facility_id,
            start_date=start_date,
            end_date=end_date,
            min_nights=args.nights,
            booking_system=booking_system,
        )
    finally:
        if recgov:
            await recgov.__aexit__(None, None, None)
        if goingtocamp:
            await goingtocamp.__aexit__(None, None, None)

    cg = result.campground
    print(f"{cg.name} (facility_id={cg.facility_id})")
    if is_wa_state:
        print(f"Book: {wa_state_availability_url(cg.facility_id, start_date, end_date)}")
    else:
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
                if not is_wa_state:
                    book_url = recgov_campsite_booking_url(
                        cg.facility_id, w.campsite_id, d,
                        date.fromisoformat(w.end_date),
                    )
                    print(f"    {day_name} {w.start_date} → {w.end_date} ({w.nights}n)")
                    print(f"      Book: {book_url}")
                else:
                    print(f"    {day_name} {w.start_date} → {w.end_date} ({w.nights}n)")

    registry.close()


async def cmd_list(args: argparse.Namespace) -> None:
    """List campgrounds in the registry."""
    booking_system = _parse_booking_system(getattr(args, "source", None))
    registry = CampgroundRegistry()
    results = registry.search(
        state=args.state,
        tags=args.tags.split(",") if args.tags else None,
        max_drive_minutes=args.max_drive,
        name_like=args.name,
        booking_system=booking_system,
    )
    print(f"Found {len(results)} campgrounds:\n")
    for cg in results:
        tags = f" [{', '.join(cg.tags)}]" if cg.tags else ""
        drive = f" ~{cg.drive_minutes_from_base}min" if cg.drive_minutes_from_base else ""
        source = f" [{cg.booking_system.value}]" if not booking_system else ""
        print(f"  {cg.name} ({cg.state}, id={cg.facility_id}){drive}{tags}{source}")
    registry.close()


async def cmd_watch_add(args: argparse.Namespace) -> None:
    """Add a campground watch."""
    start_date, end_date = _parse_dates(args.dates)
    days_of_week = list(_parse_days(args.days)) if args.days else None

    # Look up name from registry if possible
    name = args.name or ""
    if not name:
        registry = CampgroundRegistry()
        cg = registry.get_by_facility_id(args.facility_id)
        name = cg.name if cg else f"Facility {args.facility_id}"
        registry.close()

    watch = Watch(
        facility_id=args.facility_id,
        name=name,
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        min_nights=args.nights,
        days_of_week=days_of_week,
        notify_topic=args.ntfy_topic or "",
    )

    with WatchDB() as db:
        saved = db.add_watch(watch)
    print(f"Watch #{saved.id} added: {saved.name}")
    print(f"  Dates: {saved.start_date} → {saved.end_date}")
    if days_of_week:
        print(f"  Days: {args.days}")
    print(f"  Min nights: {saved.min_nights}")
    if saved.notify_topic:
        print(f"  Notify: ntfy topic '{saved.notify_topic}'")
    else:
        print("  Notify: console only (use --ntfy-topic to enable push)")


def cmd_watch_remove(args: argparse.Namespace) -> None:
    """Remove a watch."""
    with WatchDB() as db:
        if db.remove_watch(args.watch_id):
            print(f"Watch #{args.watch_id} removed.")
        else:
            print(f"Watch #{args.watch_id} not found.")


def cmd_watch_list(_args: argparse.Namespace) -> None:
    """List all watches."""
    with WatchDB() as db:
        watches = db.list_watches(enabled_only=False)

    if not watches:
        print("No watches configured. Add one with: watch add <facility_id> --dates ...")
        return

    print(f"{len(watches)} watch(es):\n")
    for w in watches:
        status = "enabled" if w.enabled else "disabled"
        days_str = ""
        if w.days_of_week:
            day_names = {0: "Mon", 1: "Tue", 2: "Wed", 3: "Thu",
                         4: "Fri", 5: "Sat", 6: "Sun"}
            days_str = f" [{','.join(day_names[d] for d in w.days_of_week)}]"
        notify = f" → ntfy:{w.notify_topic}" if w.notify_topic else ""
        print(
            f"  #{w.id} {w.name} ({w.facility_id}) "
            f"{w.start_date}→{w.end_date} "
            f"{w.min_nights}n{days_str} [{status}]{notify}"
        )


async def cmd_watch_poll(args: argparse.Namespace) -> None:
    """Poll all watches and report/notify on changes."""
    load_dotenv()
    api_key = os.getenv("RIDB_API_KEY")
    if not api_key:
        print("ERROR: RIDB_API_KEY not set in .env")
        sys.exit(1)

    watch_db = WatchDB()
    async with RecGovClient(ridb_api_key=api_key) as client:
        results = await poll_all(client, watch_db)

    changes_found = 0
    for result in results:
        if result.error:
            print(f"[ERROR] {result.watch.name}: {result.error}")
            continue

        if result.has_changes:
            changes_found += len(result.changes)
            notify_console(result)

            # Send push notification if configured
            if result.watch.notify_topic:
                await notify_ntfy(result.watch.notify_topic, result)

    if changes_found == 0:
        print(f"Polled {len(results)} watch(es). No new availability.")
    else:
        print(f"Polled {len(results)} watch(es). {changes_found} new site(s) found.")

    watch_db.close()


async def cmd_enrich(args: argparse.Namespace) -> None:
    """Enrich registry campgrounds with LLM-extracted tags."""
    load_dotenv()
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY not set in .env")
        sys.exit(1)

    from pnw_campsites.enrichment.llm_tags import enrich_registry

    enriched = await enrich_registry(
        api_key=api_key, limit=args.limit, dry_run=args.dry_run
    )
    print(f"Enriched {enriched} campground(s).")


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
    p_search.add_argument("--max-drive", type=int,
                          help="Max drive minutes from origin (use with --from)")
    p_search.add_argument("--from", dest="from_location",
                          help="Origin: seattle, bellevue, portland, spokane, or address")
    p_search.add_argument("--name", help="Filter by campground name (substring match)")
    p_search.add_argument("--people", type=int, help="Min site capacity")
    p_search.add_argument("--no-groups", action="store_true", help="Exclude group sites")
    p_search.add_argument("--include-fcfs", action="store_true",
                          help="Include FCFS (first-come-first-served) site details")
    p_search.add_argument("--limit", type=int, default=20,
                          help="Max campgrounds to check (default: 20)")
    p_search.add_argument("--source", help="Booking system: recgov, wa-state (default: all)")

    # --- check ---
    p_check = sub.add_parser("check", help="Check a specific campground")
    p_check.add_argument("facility_id", help="Recreation.gov facility ID")
    p_check.add_argument("--dates", required=True,
                         help="Date range: YYYY-MM-DD:YYYY-MM-DD or this-weekend/next-weekend")
    p_check.add_argument("--nights", type=int, default=1,
                         help="Minimum consecutive nights (default: 1)")
    p_check.add_argument("--source", help="Booking system: recgov, wa-state (default: recgov)")

    # --- list ---
    p_list = sub.add_parser("list", help="List campgrounds in the registry")
    p_list.add_argument("--state", help="Filter by state")
    p_list.add_argument("--tags", help="Comma-separated tags to filter by")
    p_list.add_argument("--max-drive", type=int, help="Max drive minutes from Bellevue")
    p_list.add_argument("--name", help="Filter by name (substring match)")
    p_list.add_argument("--source", help="Booking system: recgov, wa-state (default: all)")

    # --- watch ---
    p_watch = sub.add_parser("watch", help="Monitor campgrounds for changes")
    watch_sub = p_watch.add_subparsers(dest="watch_command", required=True)

    p_wa = watch_sub.add_parser("add", help="Add a campground watch")
    p_wa.add_argument("facility_id", help="Recreation.gov facility ID")
    p_wa.add_argument("--dates", required=True,
                       help="Date range to monitor: YYYY-MM-DD:YYYY-MM-DD")
    p_wa.add_argument("--nights", type=int, default=1,
                       help="Minimum consecutive nights (default: 1)")
    p_wa.add_argument("--days",
                       help="Days of week: thu,fri,sat,sun or weekend/long-weekend")
    p_wa.add_argument("--name", help="Override campground name")
    p_wa.add_argument("--ntfy-topic",
                       help="ntfy topic for push notifications")

    p_wr = watch_sub.add_parser("remove", help="Remove a watch")
    p_wr.add_argument("watch_id", type=int, help="Watch ID to remove")

    watch_sub.add_parser("list", help="List all watches")
    watch_sub.add_parser("poll", help="Poll all watches for changes")

    # --- enrich ---
    p_enrich = sub.add_parser("enrich", help="Enrich registry with LLM-extracted tags")
    p_enrich.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Max campgrounds to enrich (default: 50)",
    )
    p_enrich.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview enrichments without saving",
    )

    args = parser.parse_args()

    if args.command == "search":
        asyncio.run(cmd_search(args))
    elif args.command == "check":
        asyncio.run(cmd_check(args))
    elif args.command == "list":
        asyncio.run(cmd_list(args))
    elif args.command == "watch":
        if args.watch_command == "add":
            asyncio.run(cmd_watch_add(args))
        elif args.watch_command == "remove":
            cmd_watch_remove(args)
        elif args.watch_command == "list":
            cmd_watch_list(args)
        elif args.watch_command == "poll":
            asyncio.run(cmd_watch_poll(args))
    elif args.command == "enrich":
        asyncio.run(cmd_enrich(args))


if __name__ == "__main__":
    main()
