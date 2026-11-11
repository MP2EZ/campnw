"""Watch/diff engine — polls watched campgrounds and detects new availability."""

from __future__ import annotations

import asyncio
import dataclasses
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from zoneinfo import ZoneInfo

from pnw_campsites.monitor.db import Snapshot, Watch, WatchDB
from pnw_campsites.monitor.stays import new_stay_nights, stay_starts
from pnw_campsites.providers.errors import RateLimitedError, WAFBlockedError
from pnw_campsites.providers.goingtocamp import GoingToCampClient
from pnw_campsites.providers.recgov import RecGovClient
from pnw_campsites.providers.reserveamerica import ReserveAmericaClient
from pnw_campsites.registry.db import CampgroundRegistry
from pnw_campsites.registry.models import (
    AvailabilityStatus,
    BookingSystem,
    CampgroundAvailability,
)
from pnw_campsites.search.engine import enrich_wa_availability
from pnw_campsites.search.who import site_fits
from pnw_campsites.urls import availability_url

_logger = logging.getLogger(__name__)

_PACIFIC = ZoneInfo("America/Los_Angeles")

# A provider that answers with one of these is refusing us, not failing on one
# park. Stop asking it for the rest of the cycle; the next cycle tries again.
_BLOCK_ERRORS = (WAFBlockedError, RateLimitedError)


def pacific_today() -> date:
    """Today where the campgrounds are. A watch's dates are local nights."""
    return datetime.now(_PACIFIC).date()


def resolve_booking_system(
    facility_id: str, stored: str, registry: CampgroundRegistry | None,
) -> str:
    """The provider a watch's facility belongs to.

    Watches used to be saved with the column default 'recgov' whatever the
    park, so a stored 'recgov' is a default, not a fact; any other value was
    set on purpose. GoingToCamp resourceLocationIds are negative and no rec.gov
    or ReserveAmerica id is (checked against the registry 2026-11-07), which
    settles WA parks the registry doesn't list.
    """
    if stored != BookingSystem.RECGOV:
        return stored
    if registry is not None:
        systems = registry.booking_systems_for(facility_id)
        if BookingSystem.RECGOV not in systems and len(systems) == 1:
            return systems[0].value
    if facility_id.startswith("-"):
        return BookingSystem.WA_STATE.value
    return stored


def heal_booking_systems(
    watch_db: WatchDB,
    registry: CampgroundRegistry | None,
    watches: list[Watch] | None = None,
) -> int:
    """Store the right provider on watches saved under 'recgov' by default.

    Idempotent. Runs at startup over every watch (paused ones included) and
    on each poll cycle over the watches it loads. Returns how many changed.
    """
    if watches is None:
        watches = watch_db.list_watches(enabled_only=False)
    healed = 0
    for watch in watches:
        if watch.watch_type == "template":
            continue
        resolved = resolve_booking_system(
            watch.facility_id, watch.booking_system, registry,
        )
        if resolved != watch.booking_system:
            watch.booking_system = resolved
            watch_db.update_watch_booking_system(watch.id, resolved)
            healed += 1
    return healed


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
    booking_url: str = ""  # availability page on the watch's own booking site

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

    # Serve from cache only if the cached payload covers [start, end]. Keying
    # on the start month alone let a narrow payload answer a wider request,
    # which silently returned incomplete availability.
    cached = watch_db.get_cached_availability(
        facility_id, source, range_start=start, range_end=end,
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

    # Record the range this payload actually covers so a later wider request
    # doesn't mistake it for a superset.
    watch_db.set_cached_availability(
        facility_id, month_key, avail.model_dump_json(), source,
        range_start=start, range_end=end,
    )

    return avail


async def poll_watch(
    watch: Watch,
    recgov: RecGovClient | None,
    goingtocamp: GoingToCampClient | None,
    watch_db: WatchDB,
    registry: CampgroundRegistry | None = None,
    reserveamerica: ReserveAmericaClient | None = None,
    blocked: set[str] | None = None,
) -> PollResult:
    """Poll a single watch: fetch availability, diff, store snapshot.

    `blocked` is the poll cycle's set of providers that refused a request;
    their watches are skipped, and a refusal here adds to it unlogged (poll_all
    logs one line per provider).
    """
    result = PollResult(watch=watch)
    if blocked is not None and watch.booking_system in blocked:
        result.error = f"{watch.booking_system} refused requests this cycle"
        return result

    try:
        booking_system = BookingSystem(watch.booking_system)
        start = date.fromisoformat(watch.start_date)
        end = date.fromisoformat(watch.end_date)
        slug = ""
        if booking_system == BookingSystem.OR_STATE and registry:
            cg = registry.get_by_facility_id(watch.facility_id, booking_system)
            slug = cg.booking_url_slug if cg else ""
        result.booking_url = availability_url(
            watch.facility_id, booking_system, start, end, slug=slug,
        )

        availability = await _fetch_availability(
            watch.facility_id, start, end,
            booking_system, recgov, goingtocamp, watch_db,
            reserveamerica=reserveamerica,
        )
        if booking_system == BookingSystem.WA_STATE and registry:
            # Site names and fit from the seeded cache, as search does.
            enrich_wa_availability(registry, watch.facility_id, availability)

        # Build current snapshot: site_id -> [available dates]
        current: dict[str, list[str]] = {}
        site_meta: dict[str, dict] = {}
        days_filter = (
            set(watch.days_of_week) if watch.days_of_week else None
        )
        history_records: list[tuple[str, str, str]] = []

        for site_id, site in availability.campsites.items():
            available_dates = []
            # A site that doesn't fit the watch's filters never alerts, so it
            # stays out of the snapshot. Unknown fit passes (search/who.py).
            fits = not watch.has_site_filters or site_fits(
                site, booking_system,
                people=watch.min_people, equipment=watch.equipment,
                rig_length=watch.rig_length, site_types=watch.site_types,
            )
            for dt, status in site.availabilities.items():
                d = date.fromisoformat(dt[:10])
                # Record all statuses for history
                history_records.append(
                    (site_id, dt[:10], status.value)
                )
                if not fits or status != AvailabilityStatus.AVAILABLE:
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

        # A site counts, and alerts, only for runs of min_nights consecutive
        # nights. The snapshot still keeps every open night (its format is
        # unchanged), so a later night that completes a stay diffs against it.
        result.current_available = sum(
            1 for dates in current.values() if stay_starts(dates, watch.min_nights)
        )

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
            new_dates = new_stay_nights(
                dates, prev.get(site_id, []), watch.min_nights,
            )
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
                        new_dates=new_dates,
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

    except _BLOCK_ERRORS as e:
        result.error = repr(e)
        if blocked is None:
            _logger.warning("Poll failed for watch %s: %r", watch.id, e)
        else:
            blocked.add(watch.booking_system)
    except Exception as e:
        result.error = repr(e)
        _logger.warning(
            "Poll failed for watch %s (%s): %r", watch.id, watch.booking_system, e,
        )

    return result


def _from_today(watch: Watch, today: date) -> Watch | None:
    """The watch's dates from today on, or None once its last night is past."""
    try:
        start = date.fromisoformat(watch.start_date)
        end = date.fromisoformat(watch.end_date)
    except ValueError:
        return watch  # poll_watch reports the bad date as this watch's error
    if end < today:
        return None
    if start < today:
        return dataclasses.replace(watch, start_date=today.isoformat())
    return watch


async def poll_all(
    recgov: RecGovClient | None,
    goingtocamp: GoingToCampClient | None,
    watch_db: WatchDB,
    registry: CampgroundRegistry | None = None,
    tranche: int | None = None,
    reserveamerica: ReserveAmericaClient | None = None,
    tier_filter: str = "all",
    today: date | None = None,
) -> list[PollResult]:
    """Poll all enabled watches, grouping by facility to minimize API calls.

    Watches whose last night is before `today` (Pacific) are skipped, not
    changed: they stay enabled and listed, and the API reports them expired.
    A watch that has partly passed is polled from today on.

    Args:
        tranche: If set (0 or 1), only poll watches where id % 2 == tranche.
                 Used to split polling into two offset cycles.
        tier_filter: "all" (default), "pro", or "free". v1.4 uses "pro" for
                 the 5-min Pro-only tranche and "free" for the existing
                 15-min tranches so Pro watches aren't double-polled.
    """
    from pnw_campsites.monitor.expand import expand_template

    today = today or pacific_today()
    watches = watch_db.list_watches_for_polling(tier=tier_filter)
    # Release reminders wait for their release day (monitor/reminders.py);
    # their nights aren't bookable yet, so there is nothing to poll.
    watches = [w for w in watches if w.watch_type != "release"]
    if tranche is not None:
        watches = [w for w in watches if w.id % 2 == tranche]
    watches = [w for w in (_from_today(w, today) for w in watches) if w]
    heal_booking_systems(watch_db, registry, watches)

    # Expand template watches into virtual single watches
    expanded: list[Watch] = []
    for watch in watches:
        if watch.watch_type == "template" and watch.search_params and registry:
            for cg in expand_template(watch.search_params, registry):
                virtual = Watch(
                    id=watch.id,
                    facility_id=cg.facility_id,
                    name=watch.name,
                    start_date=watch.start_date,
                    end_date=watch.end_date,
                    min_nights=watch.min_nights,
                    days_of_week=watch.days_of_week,
                    notify_topic=watch.notify_topic,
                    user_id=watch.user_id,
                    notification_channel=watch.notification_channel,
                    enabled=True,
                    booking_system=cg.booking_system.value,
                    watch_type="single",  # poll as single
                    min_people=watch.min_people,
                    equipment=watch.equipment,
                    rig_length=watch.rig_length,
                    site_types=watch.site_types,
                )
                expanded.append(virtual)
        else:
            expanded.append(watch)

    # Group watches by facility to share availability data
    by_facility: dict[tuple[str, str], list[Watch]] = defaultdict(list)
    for watch in expanded:
        by_facility[(watch.booking_system, watch.facility_id)].append(watch)
    blocked: set[str] = set()

    # Pre-warm cache: for each facility, fetch the widest date range needed
    # so individual poll_watch calls all hit cache
    sem = asyncio.Semaphore(3)

    async def prefetch_facility(key: tuple[str, str], watches: list[Watch]) -> None:
        """Fetch availability once for the widest date range across watches."""
        source, fid = key
        starts = [date.fromisoformat(w.start_date) for w in watches]
        ends = [date.fromisoformat(w.end_date) for w in watches]
        wide_start, wide_end = min(starts), max(ends)
        async with sem:
            if source in blocked:
                return
            try:
                await asyncio.wait_for(
                    _fetch_availability(
                        fid, wide_start, wide_end, BookingSystem(source),
                        recgov, goingtocamp, watch_db,
                        reserveamerica=reserveamerica,
                    ),
                    timeout=15.0,
                )
            except _BLOCK_ERRORS:
                blocked.add(source)
            except Exception as exc:
                _logger.debug("Prefetch for %s failed (will retry per-watch): %s", fid, exc)

    # Only prefetch facilities with multiple watches (single-watch facilities
    # get fetched normally in poll_watch)
    multi_facility_tasks = [
        prefetch_facility(key, watches)
        for key, watches in by_facility.items()
        if len(watches) > 1
    ]
    if multi_facility_tasks:
        await asyncio.gather(*multi_facility_tasks)

    # Poll all watches (cache is warm for multi-watch facilities)
    async def poll_limited(watch: Watch) -> PollResult:
        async with sem:
            try:
                return await asyncio.wait_for(
                    poll_watch(
                        watch, recgov, goingtocamp, watch_db, registry,
                        reserveamerica=reserveamerica, blocked=blocked,
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

    for source in sorted(blocked):
        skipped = sum(1 for r in results if r.error and r.watch.booking_system == source)
        _logger.warning(
            "%s refused requests (WAF block or rate limit): %d watch(es) not "
            "polled this cycle", source, skipped,
        )
    return list(results)
