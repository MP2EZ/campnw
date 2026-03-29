"""Discovery engine — translates flexible queries into registry + availability results."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import date, timedelta

from pnw_campsites.geo import estimated_drive_minutes, geocode_address, is_known_base, resolve_base
from pnw_campsites.providers.errors import FacilityNotFoundError, RateLimitedError, WAFBlockedError
from pnw_campsites.providers.goingtocamp import GoingToCampClient
from pnw_campsites.providers.recgov import RecGovClient
from pnw_campsites.providers.reserveamerica import ReserveAmericaClient
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
    from_location: str | None = None  # known base name or address
    from_coords: tuple[float, float] | None = None  # resolved (lat, lon)
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
    estimated_drive_minutes: int | None = None
    error: str | None = None


@dataclass
class SearchWarning:
    """Aggregated warning from a search (e.g., rate limits, WAF blocks)."""

    kind: str  # "rate_limited", "waf_blocked", "unavailable"
    count: int
    source: str  # "recgov", "wa_state"


@dataclass
class SearchDiagnosis:
    """Analysis of why a search returned zero results."""

    registry_matches: int
    distance_filtered: int
    checked_for_availability: int
    all_unavailable: int
    binding_constraint: str  # "tags", "state", "distance", "dates", "days", "name"
    explanation: str


@dataclass
class DateSuggestion:
    """An alternative date window with availability."""

    start_date: str
    end_date: str
    campgrounds_with_availability: int
    reason: str


@dataclass
class ActionChip:
    """A one-tap action to modify search constraints."""

    action: str  # "shift_dates", "drop_days", "expand_radius", "watch", etc.
    label: str
    params: dict


@dataclass
class SearchResults:
    """Complete results from a discovery search."""

    query: SearchQuery
    results: list[CampgroundResult] = field(default_factory=list)
    campgrounds_checked: int = 0
    campgrounds_with_availability: int = 0
    warnings: list[SearchWarning] = field(default_factory=list)
    diagnosis: SearchDiagnosis | None = None
    date_suggestions: list[DateSuggestion] = field(default_factory=list)
    action_chips: list[ActionChip] = field(default_factory=list)

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
        reserveamerica_client: ReserveAmericaClient | None = None,
    ) -> None:
        self._registry = registry
        self._recgov = recgov_client
        self._goingtocamp = goingtocamp_client
        self._reserveamerica = reserveamerica_client

    async def search(
        self, query: SearchQuery, *, _skip_diagnosis: bool = False,
    ) -> SearchResults:
        """Run a discovery search: filter registry, then check availability."""
        # Step 1: Filter registry — search all providers if no specific system
        campgrounds = self._registry.search(
            state=query.state,
            tags=query.tags,
            booking_system=query.booking_system,
            name_like=query.name_like,
        )
        registry_count = len(campgrounds)

        # Step 1b: Resolve origin and filter/sort by distance
        from_coords = query.from_coords
        if not from_coords and query.from_location:
            if is_known_base(query.from_location):
                from_coords = resolve_base(query.from_location)
            else:
                from_coords = await geocode_address(query.from_location)
            query.from_coords = from_coords

        drive_times: dict[str, int] = {}  # facility_id -> minutes
        if from_coords:
            for cg in campgrounds:
                if cg.latitude and cg.longitude:
                    drive_times[cg.facility_id] = estimated_drive_minutes(
                        from_coords[0], from_coords[1],
                        cg.latitude, cg.longitude,
                    )

            # Filter by max drive time
            pre_distance_count = len(campgrounds)
            if query.max_drive_minutes:
                campgrounds = [
                    cg for cg in campgrounds
                    if drive_times.get(cg.facility_id, 9999)
                    <= query.max_drive_minutes
                ]
            distance_filtered = pre_distance_count - len(campgrounds)

            # Sort by distance (closest first)
            campgrounds.sort(
                key=lambda cg: drive_times.get(cg.facility_id, 9999)
            )
        else:
            distance_filtered = 0

        # Limit per source — each source gets max_campgrounds slots so
        # the client-side source filter always has a full set to show.
        # When a specific booking_system is requested, just cap globally.
        if not query.booking_system:
            by_source: dict[str, list] = {}
            for cg in campgrounds:
                by_source.setdefault(cg.booking_system.value, []).append(cg)
            campgrounds = []
            for source_cgs in by_source.values():
                campgrounds.extend(source_cgs[: query.max_campgrounds])
            # Re-sort by distance after merging
            if from_coords:
                campgrounds.sort(
                    key=lambda cg: drive_times.get(
                        cg.facility_id, 9999,
                    )
                )
        else:
            campgrounds = campgrounds[: query.max_campgrounds]

        if not campgrounds:
            empty_results = SearchResults(query=query)
            if not _skip_diagnosis:
                diagnosis, chips = self._diagnose_zero_results(
                    query, registry_count, distance_filtered, 0, 0,
                )
                empty_results.diagnosis = diagnosis
                empty_results.action_chips = chips
                empty_results.date_suggestions = (
                    await self._suggest_alternative_dates(query)
                )
            return empty_results

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
        batch_delay = 0.3  # seconds between batches
        all_results: list[CampgroundResult] = []
        search_start = time.monotonic()

        for i in range(0, len(campgrounds), batch_size):
            if i > 0:
                await asyncio.sleep(batch_delay)
            batch = campgrounds[i : i + batch_size]
            tasks = [
                self._check_campground(cg, start_month, end_month, query)
                for cg in batch
            ]
            batch_results = await asyncio.gather(*tasks)
            all_results.extend(batch_results)

        search_elapsed = time.monotonic() - search_start
        rate_limited = sum(1 for r in all_results if r.error == "rate_limited")
        logger = logging.getLogger("pnw_campsites.search")
        logger.info(
            "Search: %d campgrounds in %.1fs (batch=%d, delay=%.1fs) "
            "| %d rate_limited | %d with availability",
            len(campgrounds),
            search_elapsed,
            batch_size,
            batch_delay,
            rate_limited,
            sum(1 for r in all_results if r.total_available_sites > 0),
        )

        # Step 4: Attach drive times to results
        if drive_times:
            for r in all_results:
                fid = r.campground.facility_id
                if fid in drive_times:
                    r.estimated_drive_minutes = drive_times[fid]

        # Step 5: Aggregate errors into warnings, filter out error-only results
        error_counts: dict[str, dict[str, int]] = {}  # error_kind -> source -> count
        for r in all_results:
            if r.error:
                source = r.campground.booking_system.value
                error_counts.setdefault(r.error, {})
                error_counts[r.error][source] = error_counts[r.error].get(source, 0) + 1

        warnings = [
            SearchWarning(kind=kind, count=sum(sources.values()), source=src)
            for kind, sources in error_counts.items()
            for src, _ in sources.items()
        ]

        campgrounds_with_availability = sum(
            1 for r in all_results if r.total_available_sites > 0
        )

        results = SearchResults(
            query=query,
            results=[
                r for r in all_results
                if r.total_available_sites > 0 or r.fcfs_sites > 0
            ],
            campgrounds_checked=len(all_results),
            campgrounds_with_availability=campgrounds_with_availability,
            warnings=warnings,
        )

        # Diagnose zero-result searches
        if campgrounds_with_availability == 0 and not _skip_diagnosis:
            all_unavailable = sum(
                1 for r in all_results
                if r.total_available_sites == 0 and not r.error
            )
            diagnosis, chips = self._diagnose_zero_results(
                query, registry_count, distance_filtered,
                len(all_results), all_unavailable,
            )
            results.diagnosis = diagnosis
            results.action_chips = chips
            # Wire in "Try nearby" chips for name searches
            if query.name_like:
                similar_chips = self._suggest_similar_campgrounds(query)
                results.action_chips.extend(similar_chips)
            results.date_suggestions = (
                await self._suggest_alternative_dates(query)
            )

        # Sort by distance if filtering by location, otherwise by availability
        if from_coords:
            results.results.sort(
                key=lambda r: r.estimated_drive_minutes or 9999
            )
        else:
            results.results.sort(
                key=lambda r: r.total_available_sites, reverse=True
            )

        return results

    def _diagnose_zero_results(
        self,
        query: SearchQuery,
        registry_matches: int,
        distance_filtered: int,
        checked: int,
        all_unavailable: int,
    ) -> tuple[SearchDiagnosis, list[ActionChip]]:
        """Analyze why a search returned zero results and suggest actions."""
        chips: list[ActionChip] = []

        if registry_matches == 0 and query.name_like:
            binding = "name"
            explanation = (
                f'No campgrounds matching "{query.name_like}" in the registry'
            )
        elif registry_matches == 0 and query.tags:
            binding = "tags"
            tag_str = ", ".join(query.tags)
            explanation = f"No campgrounds with tags: {tag_str}"
            chips.append(ActionChip(
                action="drop_tags", label="Search without tags",
                params={},
            ))
        elif registry_matches == 0 and query.state:
            binding = "state"
            explanation = (
                f"No campgrounds found in {query.state}"
            )
        elif (
            distance_filtered > 0
            and registry_matches > 0
            and distance_filtered > registry_matches * 0.5
        ):
            binding = "distance"
            explanation = (
                f"{distance_filtered} of {registry_matches} campgrounds "
                f"exceeded {query.max_drive_minutes} min drive limit"
            )
            new_limit = (query.max_drive_minutes or 0) + 60
            chips.append(ActionChip(
                action="expand_radius",
                label=f"Expand to {new_limit} min",
                params={"max_drive_minutes": new_limit},
            ))
            chips.append(ActionChip(
                action="expand_radius",
                label="Remove drive limit",
                params={"max_drive_minutes": None},
            ))
        elif all_unavailable == checked and checked > 0:
            if query.days_of_week:
                binding = "days"
                explanation = (
                    f"Checked {checked} campgrounds — all fully booked "
                    f"on selected days"
                )
                chips.append(ActionChip(
                    action="drop_days", label="Try any day",
                    params={"days_of_week": None},
                ))
            else:
                binding = "dates"
                explanation = (
                    f"Checked {checked} campgrounds — all fully booked "
                    f"for these dates"
                )
            if query.start_date and query.end_date:
                span = (query.end_date - query.start_date).days
                new_start = query.start_date - timedelta(days=7)
                new_end = query.end_date + timedelta(days=7)
                chips.append(ActionChip(
                    action="shift_dates",
                    label=f"Expand to {span + 14} days",
                    params={
                        "start_date": new_start.isoformat(),
                        "end_date": new_end.isoformat(),
                    },
                ))
        else:
            binding = "unknown"
            explanation = "No results found"

        # Always include a watch chip when dates are specified
        if query.start_date and query.end_date:
            chips.append(ActionChip(
                action="watch", label="Set a watch",
                params={
                    "start_date": query.start_date.isoformat(),
                    "end_date": query.end_date.isoformat(),
                },
            ))

        diagnosis = SearchDiagnosis(
            registry_matches=registry_matches,
            distance_filtered=distance_filtered,
            checked_for_availability=checked,
            all_unavailable=all_unavailable,
            binding_constraint=binding,
            explanation=explanation,
        )
        return diagnosis, chips

    async def _suggest_alternative_dates(
        self, query: SearchQuery, max_suggestions: int = 3,
    ) -> list[DateSuggestion]:
        """Probe nearby date windows for availability."""
        if not query.start_date or not query.end_date:
            return []

        span = (query.end_date - query.start_date).days
        shifts = [
            (7, "1 week later"),
            (14, "2 weeks later"),
            (-7, "1 week earlier"),
        ]

        suggestions: list[DateSuggestion] = []
        for delta_days, reason in shifts:
            shifted_start = query.start_date + timedelta(days=delta_days)
            shifted_end = shifted_start + timedelta(days=span)
            # Don't suggest dates in the past
            if shifted_start < date.today():
                continue

            shifted_query = SearchQuery(
                start_date=shifted_start,
                end_date=shifted_end,
                state=query.state,
                tags=query.tags,
                max_drive_minutes=query.max_drive_minutes,
                from_location=query.from_location,
                from_coords=query.from_coords,
                name_like=query.name_like,
                booking_system=query.booking_system,
                min_consecutive_nights=query.min_consecutive_nights,
                include_group_sites=query.include_group_sites,
                max_people=query.max_people,
                days_of_week=query.days_of_week,
                max_campgrounds=5,
            )
            shifted_results = await self.search(
                shifted_query, _skip_diagnosis=True,
            )
            if shifted_results.campgrounds_with_availability > 0:
                suggestions.append(DateSuggestion(
                    start_date=shifted_start.isoformat(),
                    end_date=shifted_end.isoformat(),
                    campgrounds_with_availability=(
                        shifted_results.campgrounds_with_availability
                    ),
                    reason=reason,
                ))
            if len(suggestions) >= max_suggestions:
                break

        # Sort by proximity to original dates
        suggestions.sort(
            key=lambda s: abs(
                (date.fromisoformat(s.start_date) - query.start_date).days
            ),
        )
        return suggestions

    def _suggest_similar_campgrounds(
        self, query: SearchQuery,
    ) -> list[ActionChip]:
        """Find similar campgrounds for name-based searches with no results."""
        if not query.name_like:
            return []

        # Get the first matching campground from registry (even if unavailable)
        matches = self._registry.search(name_like=query.name_like)
        if not matches:
            return []

        similar = self._registry.find_similar(
            matches[0], state=query.state, limit=2,
        )
        if not similar:
            return []

        names = [cg.name for cg in similar]
        facility_ids = [cg.facility_id for cg in similar]
        return [ActionChip(
            action="try_nearby",
            label=f"Try {', '.join(names)}",
            params={"facility_ids": facility_ids, "names": names},
        )]

    async def search_stream(
        self, query: SearchQuery
    ) -> AsyncIterator[CampgroundResult]:
        """Stream search results as each batch completes."""
        # Reuse the same setup as search() — registry filter + distance
        campgrounds = self._registry.search(
            state=query.state,
            tags=query.tags,
            booking_system=query.booking_system,
            name_like=query.name_like,
        )

        from_coords = query.from_coords
        if not from_coords and query.from_location:
            if is_known_base(query.from_location):
                from_coords = resolve_base(query.from_location)
            else:
                from_coords = await geocode_address(query.from_location)
            query.from_coords = from_coords

        drive_times: dict[str, int] = {}
        if from_coords:
            for cg in campgrounds:
                if cg.latitude and cg.longitude:
                    drive_times[cg.facility_id] = estimated_drive_minutes(
                        from_coords[0], from_coords[1],
                        cg.latitude, cg.longitude,
                    )
            if query.max_drive_minutes:
                campgrounds = [
                    cg for cg in campgrounds
                    if drive_times.get(cg.facility_id, 9999)
                    <= query.max_drive_minutes
                ]
            campgrounds.sort(
                key=lambda cg: drive_times.get(cg.facility_id, 9999)
            )

        # Limit per source (same logic as search())
        if not query.booking_system:
            by_src: dict[str, list] = {}
            for cg in campgrounds:
                by_src.setdefault(
                    cg.booking_system.value, [],
                ).append(cg)
            campgrounds = []
            for src_cgs in by_src.values():
                campgrounds.extend(
                    src_cgs[: query.max_campgrounds]
                )
            if from_coords:
                campgrounds.sort(
                    key=lambda cg: drive_times.get(
                        cg.facility_id, 9999,
                    )
                )
        else:
            campgrounds = campgrounds[: query.max_campgrounds]

        if not campgrounds:
            return

        if query.start_date and query.end_date:
            start_month = query.start_date
            end_month = query.end_date
        elif query.start_date:
            start_month = query.start_date
            end_month = query.start_date
        else:
            today = date.today()
            start_month = today
            end_month = today.replace(
                month=today.month + 1 if today.month < 12 else 1,
                year=today.year if today.month < 12 else today.year + 1,
            )

        batch_size = 5
        batch_delay = 0.3

        for i in range(0, len(campgrounds), batch_size):
            if i > 0:
                await asyncio.sleep(batch_delay)
            batch = campgrounds[i : i + batch_size]
            tasks = [
                self._check_campground(cg, start_month, end_month, query)
                for cg in batch
            ]
            batch_results = await asyncio.gather(*tasks)
            for r in batch_results:
                if drive_times:
                    fid = r.campground.facility_id
                    if fid in drive_times:
                        r.estimated_drive_minutes = drive_times[fid]
                # Only yield results with availability or FCFS
                if r.total_available_sites > 0 or r.fcfs_sites > 0:
                    yield r

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
            elif campground.booking_system == BookingSystem.OR_STATE:
                if not self._reserveamerica:
                    return CampgroundResult(
                        campground=campground,
                        error="ReserveAmerica client not configured",
                    )
                availability = await self._reserveamerica.get_availability(
                    campground.facility_id,
                    campground.booking_url_slug,
                    campground.state,
                    start_month,
                    end_month,
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
        except FacilityNotFoundError:
            # Silently drop — bad registry entry, no availability to show
            return CampgroundResult(campground=campground)
        except RateLimitedError:
            return CampgroundResult(campground=campground, error="rate_limited")
        except WAFBlockedError:
            return CampgroundResult(campground=campground, error="waf_blocked")
        except Exception:
            return CampgroundResult(campground=campground, error="unavailable")

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
