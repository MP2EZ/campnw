"""Watch/diff engine — polls watched campgrounds and detects new availability."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

from pnw_campsites.monitor.db import Snapshot, Watch, WatchDB
from pnw_campsites.providers.recgov import RecGovClient
from pnw_campsites.registry.models import AvailabilityStatus


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


async def poll_watch(
    watch: Watch,
    client: RecGovClient,
    watch_db: WatchDB,
) -> PollResult:
    """Poll a single watch: fetch availability, diff, store snapshot."""
    result = PollResult(watch=watch)

    try:
        # Fetch current availability
        start = date.fromisoformat(watch.start_date)
        end = date.fromisoformat(watch.end_date)
        availability = await client.get_availability_range(
            watch.facility_id, start, end
        )

        # Build current snapshot: site_id -> [available dates]
        current: dict[str, list[str]] = {}
        site_meta: dict[str, dict] = {}  # site_id -> metadata for change reports

        days_filter = set(watch.days_of_week) if watch.days_of_week else None

        for site_id, site in availability.campsites.items():
            available_dates = []
            for dt, status in site.availabilities.items():
                if status != AvailabilityStatus.AVAILABLE:
                    continue
                d = date.fromisoformat(dt[:10])
                # Apply date range filter
                if d < start or d > end:
                    continue
                # Apply day-of-week filter
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

        # Get previous snapshot
        prev_snapshot = watch_db.get_latest_snapshot(watch.id)
        prev: dict[str, list[str]] = (
            prev_snapshot.available_sites if prev_snapshot else {}
        )

        # Diff: find newly available dates per site
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
                        campsite_type=meta.get("campsite_type", ""),
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
        result.error = str(e)

    return result


async def poll_all(
    client: RecGovClient,
    watch_db: WatchDB,
) -> list[PollResult]:
    """Poll all enabled watches and return results."""
    watches = watch_db.list_watches(enabled_only=True)
    results: list[PollResult] = []

    for watch in watches:
        result = await poll_watch(watch, client, watch_db)
        results.append(result)

    return results
