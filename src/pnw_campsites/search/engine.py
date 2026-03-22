"""Discovery engine — translates flexible queries into registry + availability results."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import date, timedelta

from pnw_campsites.providers.goingtocamp import GoingToCampClient
from pnw_campsites.providers.recgov import RecGovClient
from pnw_campsites.registry.db import CampgroundRegistry
from pnw_campsites.registry.models import (
    BookingSystem,
    Campground,
    CampgroundAvailability,
    CampsiteAvailability,
)


@dataclass
class SearchQuery:
    """Flexible search parameters for campsite discovery."""

    # Date range
    start_date: date | None = None
    end_date: date | None = None

    # Registry filters
    state: str | None = None
    tags: list[str] | None = None
    max_drive_minutes: int | None = None
    name_like: str | None = None
    booking_system: BookingSystem | None = None

    # Availability filters
    min_consecutive_nights: int = 1
    include_group_sites: bool = True
    max_people: int | None = None  # filter sites by capacity
    days_of_week: set[int] | None = None  # 0=Mon, 6=Sun; None means all days
    include_fcfs: bool = False  # include FCFS/not-reservable site details

    # Result limits
    max_campgrounds: int = 20  # limit how many campgrounds to check availability for


@dataclass
class AvailableWindow:
    """A contiguous block of available dates at a specific campsite."""

    campsite_id: str
    site_name: str
    loop: str
    campsite_type: str
    start_date: str  # ISO date string
    end_date: str  # ISO date string
    nights: int
    max_people: int
    is_fcfs: bool = False  # True for FCFS/not-reservable sites


@dataclass
class CampgroundResult:
    """Availability results for a single campground."""

    campground: Campground
    available_windows: list[AvailableWindow] = field(default_factory=list)
    total_available_sites: int = 0
    fcfs_sites: int = 0  # FCFS/not-reservable site count (always counted)
    total_sites: int = 0  # total sites at this campground
    error: str | None = None


@dataclass
class SearchResults:
    """Complete results from a discovery search."""

    query: SearchQuery
    results: list[CampgroundResult] = field(default_factory=list)
    campgrounds_checked: int = 0
    campgrounds_with_availability: int = 0

    @property
    def has_availability(self) -> bool:
        return self.campgrounds_with_availability > 0


def _find_consecutive_windows(
    site: CampsiteAvailability,
    start_date: date | None,
    end_date: date | None,
    min_nights: int,
    days_of_week: set[int] | None = None,
) -> list[AvailableWindow]:
    """Find contiguous available date windows for a campsite.

    Args:
        days_of_week: If set, only consider dates falling on these days
            (0=Monday .. 6=Sunday). Consecutive windows are built from
            the filtered dates, so a Thu-Sun filter (days_of_week={3,4,5,6})
            will only find runs within those days.
    """
    available_dates = sorted(site.available_dates())
    if not available_dates:
        return []

    # Filter to requested date range
    if start_date:
        start_str = start_date.isoformat()
        available_dates = [d for d in available_dates if d[:10] >= start_str]
    if end_date:
        end_str = end_date.isoformat()
        available_dates = [d for d in available_dates if d[:10] <= end_str]

    # Filter to allowed days of week
    if days_of_week is not None:
        available_dates = [
            d for d in available_dates
            if date.fromisoformat(d[:10]).weekday() in days_of_week
        ]

    if not available_dates:
        return []

    # Group into consecutive runs
    windows: list[AvailableWindow] = []
    run_start = available_dates[0]
    run_end = available_dates[0]
    run_length = 1

    for i in range(1, len(available_dates)):
        curr = available_dates[i][:10]
        prev = available_dates[i - 1][:10]

        curr_date = date.fromisoformat(curr)
        prev_date = date.fromisoformat(prev)

        if (curr_date - prev_date).days == 1:
            run_end = available_dates[i]
            run_length += 1
        else:
            if run_length >= min_nights:
                windows.append(
                    AvailableWindow(
                        campsite_id=site.campsite_id,
                        site_name=site.site,
                        loop=site.loop,
                        campsite_type=site.campsite_type,
                        start_date=run_start[:10],
                        end_date=run_end[:10],
                        nights=run_length,
                        max_people=site.max_num_people,
                    )
                )
            run_start = available_dates[i]
            run_end = available_dates[i]
            run_length = 1

    # Don't forget the last run
    if run_length >= min_nights:
        windows.append(
            AvailableWindow(
                campsite_id=site.campsite_id,
                site_name=site.site,
                loop=site.loop,
                campsite_type=site.campsite_type,
                start_date=run_start[:10],
                end_date=run_end[:10],
                nights=run_length,
                max_people=site.max_num_people,
            )
        )

    return windows


def _process_availability(
    campground: Campground,
    availability: CampgroundAvailability,
    query: SearchQuery,
) -> CampgroundResult:
    """Process raw availability into structured results."""
    result = CampgroundResult(campground=campground)
    result.total_sites = len(availability.campsites)
    seen_sites: set[str] = set()
    fcfs_count = 0

    for site_id, site in availability.campsites.items():
        # Always count FCFS sites
        if site.is_fcfs:
            fcfs_count += 1
            if not query.include_fcfs:
                continue
            # For FCFS sites included in results, create a single
            # window spanning the full date range to surface them
            result.available_windows.append(
                AvailableWindow(
                    campsite_id=site.campsite_id,
                    site_name=site.site,
                    loop=site.loop,
                    campsite_type=site.campsite_type,
                    start_date=(query.start_date or date.today()).isoformat(),
                    end_date=(query.end_date or query.start_date or date.today()).isoformat(),
                    nights=0,  # unknown — FCFS
                    max_people=site.max_num_people,
                    is_fcfs=True,
                )
            )
            seen_sites.add(site_id)
            continue

        # Filter group sites
        if not query.include_group_sites and "GROUP" in site.campsite_type.upper():
            continue

        # Filter by capacity
        if query.max_people and site.max_num_people < query.max_people:
            continue

        windows = _find_consecutive_windows(
            site,
            query.start_date,
            query.end_date,
            query.min_consecutive_nights,
            query.days_of_week,
        )

        if windows:
            result.available_windows.extend(windows)
            seen_sites.add(site_id)

    result.total_available_sites = len(seen_sites)
    result.fcfs_sites = fcfs_count
    return result


class SearchEngine:
    """Orchestrates registry filtering + availability checking."""

    def __init__(
        self,
        registry: CampgroundRegistry,
        recgov_client: RecGovClient | None = None,
        goingtocamp_client: GoingToCampClient | None = None,
    ) -> None:
        self._registry = registry
        self._recgov = recgov_client
        self._goingtocamp = goingtocamp_client

    async def search(self, query: SearchQuery) -> SearchResults:
        """Run a discovery search: filter registry, then check availability."""
        # Step 1: Filter registry — search all providers if no specific system requested
        campgrounds = self._registry.search(
            state=query.state,
            tags=query.tags,
            max_drive_minutes=query.max_drive_minutes,
            booking_system=query.booking_system,
            name_like=query.name_like,
        )

        # Limit to avoid hammering the API
        campgrounds = campgrounds[: query.max_campgrounds]

        if not campgrounds:
            return SearchResults(query=query)

        # Step 2: Determine month range from dates
        if query.start_date and query.end_date:
            start_month = query.start_date
            end_month = query.end_date
        elif query.start_date:
            start_month = query.start_date
            end_month = query.start_date
        else:
            # Default: check current month + next month
            today = date.today()
            start_month = today
            end_month = today.replace(
                month=today.month + 1 if today.month < 12 else 1,
                year=today.year if today.month < 12 else today.year + 1,
            )

        # Step 3: Fetch availability in parallel (batched to respect rate limits)
        batch_size = 5  # concurrent availability requests
        all_results: list[CampgroundResult] = []

        for i in range(0, len(campgrounds), batch_size):
            batch = campgrounds[i : i + batch_size]
            tasks = [
                self._check_campground(cg, start_month, end_month, query)
                for cg in batch
            ]
            batch_results = await asyncio.gather(*tasks)
            all_results.extend(batch_results)

        # Step 4: Build search results
        results = SearchResults(
            query=query,
            results=[
                r for r in all_results
                if r.total_available_sites > 0 or r.fcfs_sites > 0 or r.error
            ],
            campgrounds_checked=len(all_results),
            campgrounds_with_availability=sum(
                1 for r in all_results if r.total_available_sites > 0
            ),
        )

        # Sort by number of available sites (most availability first)
        results.results.sort(key=lambda r: r.total_available_sites, reverse=True)

        return results

    async def _check_campground(
        self,
        campground: Campground,
        start_month: date,
        end_month: date,
        query: SearchQuery,
    ) -> CampgroundResult:
        """Check availability for a single campground, dispatching to the right provider."""
        try:
            if campground.booking_system == BookingSystem.WA_STATE:
                if not self._goingtocamp:
                    return CampgroundResult(
                        campground=campground,
                        error="GoingToCamp client not configured",
                    )
                availability = await self._goingtocamp.get_availability(
                    int(campground.facility_id), start_month, end_month
                )
            else:
                if not self._recgov:
                    return CampgroundResult(
                        campground=campground,
                        error="RecGov client not configured",
                    )
                availability = await self._recgov.get_availability_range(
                    campground.facility_id, start_month, end_month
                )
            return _process_availability(campground, availability, query)
        except Exception as e:
            return CampgroundResult(
                campground=campground,
                error=f"Failed to fetch availability: {e}",
            )

    async def check_specific(
        self,
        facility_id: str,
        start_date: date,
        end_date: date,
        min_nights: int = 1,
        booking_system: BookingSystem | None = None,
    ) -> CampgroundResult:
        """Check availability for a specific known campground."""
        campground = self._registry.get_by_facility_id(
            facility_id, booking_system=booking_system or BookingSystem.RECGOV
        )
        if not campground:
            campground = Campground(
                facility_id=facility_id,
                name=f"Facility {facility_id}",
                booking_system=booking_system or BookingSystem.RECGOV,
            )

        query = SearchQuery(
            start_date=start_date,
            end_date=end_date,
            min_consecutive_nights=min_nights,
        )

        return await self._check_campground(
            campground, start_date, end_date, query
        )


# ---------------------------------------------------------------------------
# Date helpers for natural-language-style queries
# ---------------------------------------------------------------------------


def this_weekend() -> tuple[date, date]:
    """Return (Friday, Sunday) for the upcoming weekend."""
    today = date.today()
    days_until_friday = (4 - today.weekday()) % 7
    if days_until_friday == 0 and today.weekday() > 4:
        days_until_friday = 7
    friday = today + timedelta(days=days_until_friday)
    sunday = friday + timedelta(days=2)
    return friday, sunday


def next_weekend() -> tuple[date, date]:
    """Return (Friday, Sunday) for the weekend after this one."""
    fri, sun = this_weekend()
    return fri + timedelta(days=7), sun + timedelta(days=7)


def weekends_in_month(year: int, month: int) -> list[tuple[date, date]]:
    """Return all (Friday, Sunday) pairs in a given month."""
    weekends = []
    d = date(year, month, 1)
    while d.month == month:
        if d.weekday() == 4:  # Friday
            weekends.append((d, d + timedelta(days=2)))
        d += timedelta(days=1)
    return weekends


# Day-of-week presets (Monday=0 .. Sunday=6)
WEEKDAYS = {0, 1, 2, 3, 4}  # Mon-Fri
WEEKEND = {4, 5, 6}  # Fri-Sun
LONG_WEEKEND = {3, 4, 5, 6}  # Thu-Sun


def days(*names: str) -> set[int]:
    """Build a days_of_week set from day names.

    >>> days("thu", "fri", "sat", "sun")
    {3, 4, 5, 6}
    """
    mapping = {
        "mon": 0, "tue": 1, "wed": 2, "thu": 3,
        "fri": 4, "sat": 5, "sun": 6,
    }
    return {mapping[n.lower()[:3]] for n in names}
