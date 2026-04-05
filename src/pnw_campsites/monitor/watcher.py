"""Watch/diff engine — polls watched campgrounds and detects new availability."""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime

from pnw_campsites.monitor.db import Snapshot, Watch, WatchDB
from pnw_campsites.providers.goingtocamp import GoingToCampClient
from pnw_campsites.providers.recgov import RecGovClient
from pnw_campsites.providers.reserveamerica import ReserveAmericaClient
from pnw_campsites.registry.db import CampgroundRegistry
from pnw_campsites.registry.models import (
    AvailabilityStatus,
    BookingSystem,
    CampgroundAvailability,
)

_logger = logging.getLogger(__name__)


@dataclass
class AvailabilityChange:
    """A newly-available site detected by the watcher."""

    watch: Watch
    site_id: str
    site_name: str
    loop: str
    campsite_type: str
    new_dates: list[str]  # ISO date strings that just became available
    max_people: int
    context_message: str = ""  # LLM-enriched message
    urgency: int = 2  # 1=low, 2=medium, 3=high


@dataclass
class PollResult:
    """Result of polling a single watch."""

    watch: Watch
    changes: list[AvailabilityChange] = field(default_factory=list)
    current_available: int = 0  # total available sites right now
    error: str | None = None

    @property
    def has_changes(self) -> bool:
        return len(self.changes) > 0


async def _fetch_availability(
    facility_id: str,
    start: date,
    end: date,
    booking_system: BookingSystem,
    recgov: RecGovClient | None,
    goingtocamp: GoingToCampClient | None,
    watch_db: WatchDB,
    reserveamerica: ReserveAmericaClient | None = None,
) -> CampgroundAvailability:
    """Fetch availability from the right provider, using cache."""
    source = booking_system.value
    month_key = start.strftime("%Y-%m")

    # Check cache
    cached = watch_db.get_cached_availability(
        facility_id, month_key, source,
    )
    if cached:
        return CampgroundAvailability.model_validate_json(cached)

    # Fetch from provider
    if booking_system == BookingSystem.WA_STATE:
        if not goingtocamp:
            raise RuntimeError("GoingToCamp client not available")
        avail = await goingtocamp.get_availability(
            int(facility_id), start, end,
        )
    elif booking_system == BookingSystem.OR_STATE:
        if not reserveamerica:
            raise RuntimeError("ReserveAmerica client not available")
        avail = await reserveamerica.get_availability(
            facility_id, start, end,
        )
    else:
        if not recgov:
            raise RuntimeError("RecGov client not available")
        avail = await recgov.get_availability_range(
            facility_id, start, end,
        )

    # Store in cache
    watch_db.set_cached_availability(
        facility_id, month_key, avail.model_dump_json(), source,
    )

    return avail


async def poll_watch(
    watch: Watch,
    recgov: RecGovClient | None,
    goingtocamp: GoingToCampClient | None,
    watch_db: WatchDB,
    registry: CampgroundRegistry | None = None,
    reserveamerica: ReserveAmericaClient | None = None,
) -> PollResult:
    """Poll a single watch: fetch availability, diff, store snapshot."""
    result = PollResult(watch=watch)

    try:
        start = date.fromisoformat(watch.start_date)
        end = date.fromisoformat(watch.end_date)

        # Use stored booking system; self-heal from registry if needed
        booking_system = BookingSystem(watch.booking_system)
        if booking_system == BookingSystem.RECGOV and registry:
            cg = registry.get_by_facility_id(watch.facility_id)
            if cg and cg.booking_system != BookingSystem.RECGOV:
                booking_system = cg.booking_system
                watch_db.update_watch_booking_system(
                    watch.id, booking_system.value,
                )

        availability = await _fetch_availability(
            watch.facility_id, start, end,
            booking_system, recgov, goingtocamp, watch_db,
            reserveamerica=reserveamerica,
        )

        # Build current snapshot: site_id -> [available dates]
        current: dict[str, list[str]] = {}
        site_meta: dict[str, dict] = {}
        days_filter = (
            set(watch.days_of_week) if watch.days_of_week else None
        )
        history_records: list[tuple[str, str, str]] = []

        for site_id, site in availability.campsites.items():
            available_dates = []
            for dt, status in site.availabilities.items():
                d = date.fromisoformat(dt[:10])
                # Record all statuses for history
                history_records.append(
                    (site_id, dt[:10], status.value)
                )
                if status != AvailabilityStatus.AVAILABLE:
                    continue
                if d < start or d > end:
                    continue
                if days_filter and d.weekday() not in days_filter:
                    continue
                available_dates.append(dt[:10])

            if available_dates:
                current[site_id] = sorted(available_dates)
                site_meta[site_id] = {
                    "site_name": site.site,
                    "loop": site.loop,
                    "campsite_type": site.campsite_type,
                    "max_people": site.max_num_people,
                }

        result.current_available = len(current)

        # Record availability history (silent, for predictions)
        if history_records:
            source = booking_system.value
            watch_db.record_availability_history(
                watch.facility_id, history_records, source,
            )

        # Diff against previous snapshot
        prev_snapshot = watch_db.get_latest_snapshot(watch.id)
        prev: dict[str, list[str]] = (
            prev_snapshot.available_sites if prev_snapshot else {}
        )

        for site_id, dates in current.items():
            prev_dates = set(prev.get(site_id, []))
            new_dates = [d for d in dates if d not in prev_dates]
            if new_dates:
                meta = site_meta.get(site_id, {})
                result.changes.append(
                    AvailabilityChange(
                        watch=watch,
                        site_id=site_id,
                        site_name=meta.get("site_name", site_id),
                        loop=meta.get("loop", ""),
                        campsite_type=meta.get(
                            "campsite_type", "",
                        ),
                        new_dates=sorted(new_dates),
                        max_people=meta.get("max_people", 0),
                    )
                )

        # Save current snapshot
        now = datetime.now().isoformat()
        watch_db.save_snapshot(
            Snapshot(
                watch_id=watch.id,
                polled_at=now,
                available_sites=current,
            )
        )

    except Exception as e:
        result.error = repr(e)
        _logger.warning("Poll failed for watch %s: %r", watch.id, e)

    return result


async def poll_all(
    recgov: RecGovClient | None,
    goingtocamp: GoingToCampClient | None,
    watch_db: WatchDB,
    registry: CampgroundRegistry | None = None,
    tranche: int | None = None,
    reserveamerica: ReserveAmericaClient | None = None,
) -> list[PollResult]:
    """Poll all enabled watches, grouping by facility to minimize API calls.

    Args:
        tranche: If set (0 or 1), only poll watches where id % 2 == tranche.
                 Used to split polling into two offset cycles.
    """
    from pnw_campsites.monitor.expand import expand_template

    watches = watch_db.list_watches(enabled_only=True)
    if tranche is not None:
        watches = [w for w in watches if w.id % 2 == tranche]

    # Expand template watches into virtual single watches
    expanded: list[Watch] = []
    for watch in watches:
        if watch.watch_type == "template" and watch.search_params and registry:
            facility_ids = expand_template(watch.search_params, registry)
            for fid in facility_ids:
                virtual = Watch(
                    id=watch.id,
                    facility_id=fid,
                    name=watch.name,
                    start_date=watch.start_date,
                    end_date=watch.end_date,
                    min_nights=watch.min_nights,
                    days_of_week=watch.days_of_week,
                    notify_topic=watch.notify_topic,
                    user_id=watch.user_id,
                    notification_channel=watch.notification_channel,
                    enabled=True,
                    watch_type="single",  # poll as single
                )
                expanded.append(virtual)
        else:
            expanded.append(watch)

    # Group watches by facility_id to share availability data
    by_facility: dict[str, list[Watch]] = defaultdict(list)
    for watch in expanded:
        by_facility[watch.facility_id].append(watch)

    # Poll facilities concurrently (max 3 in parallel)
    sem = asyncio.Semaphore(3)

    async def poll_limited(watch: Watch) -> PollResult:
        async with sem:
            try:
                return await asyncio.wait_for(
                    poll_watch(
                        watch, recgov, goingtocamp, watch_db, registry,
                        reserveamerica=reserveamerica,
                    ),
                    timeout=15.0,
                )
            except TimeoutError:
                _logger.warning("Poll timed out for watch %s (%s)", watch.id, watch.name)
                return PollResult(watch=watch, error="Poll timed out (15s)")

    all_watches = [w for ws in by_facility.values() for w in ws]
    results = await asyncio.gather(
        *[poll_limited(w) for w in all_watches],
    )

    return list(results)
