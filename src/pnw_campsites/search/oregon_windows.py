"""Oregon (ReserveAmerica) availability, cached per 14-day window.

ReserveAmerica answers one 14-night window per request, at most 50 sites a
page, under an app-wide 1 req/s limit. A month search for a big park is 20+
requests, so a search used to lose a park's whole fetch when the deadline cut
it, and could only reuse a cached park for the exact span it was fetched for.

Each finished window is now stored on its own (``ra_window_cache``). A park is
assembled from the fresh windows that hold its requested nights, and only the
nights none of them hold are fetched, so a search for Feb 6-19 uses a fetch of
Feb 5-18 and pays for Feb 19 alone.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import date, datetime

from pnw_campsites.providers.reserveamerica import count_requests, window_cover
from pnw_campsites.registry.models import Campground, CampgroundAvailability

logger = logging.getLogger(__name__)

# How old a stored window may be and still answer a search or a watch poll.
# The same 10 minutes the availability cache has always used.
CACHE_TTL_S = 600.0
# Stale windows are deleted on write, at most this often.
PRUNE_EVERY_S = 60.0


@dataclass(frozen=True)
class CachedWindow:
    arrival: date
    departure: date
    fetched_at: datetime
    availability: CampgroundAvailability

    def holds(self, night: date) -> bool:
        return self.arrival <= night <= self.departure


@dataclass
class Plan:
    use: list[CachedWindow]  # stored windows that answer some requested night
    fetch: list[tuple[date, date]]  # windows to request for the rest


def plan(nights: list[date], rows: list[CachedWindow], end: date) -> Plan:
    """Which stored windows answer the nights, and which windows to fetch.

    Each night is answered by the newest row holding it. Nights no row holds
    get ``window_cover``'s minimal set of windows, clipped at ``end``.
    """
    use: dict[int, CachedWindow] = {}
    missing: list[date] = []
    for night in nights:
        holders = [r for r in rows if r.holds(night)]
        if holders:
            newest = max(holders, key=lambda r: r.fetched_at)
            use[id(newest)] = newest
        else:
            missing.append(night)
    return Plan(
        use=sorted(use.values(), key=lambda r: (r.arrival, r.fetched_at)),
        fetch=window_cover(missing, end),
    )


def merge(facility_id: str, windows: list[CachedWindow]) -> CampgroundAvailability:
    """One park from several windows: every site, every night. Where windows
    overlap, the newer one's status and site details win."""
    campsites = {}
    for window in sorted(windows, key=lambda w: w.fetched_at):
        for site_id, site in window.availability.campsites.items():
            earlier = campsites.get(site_id)
            merged = site.model_copy(deep=True)
            if earlier is not None:
                merged.availabilities = {**earlier.availabilities, **site.availabilities}
            campsites[site_id] = merged
    return CampgroundAvailability(facility_id=facility_id, campsites=campsites)


class OregonWindows:
    """Fetches Oregon parks window by window through the shared window cache.

    Searches and the watch poller both go through here, so a window either of
    them fetched answers the other for ``CACHE_TTL_S``.
    """

    def __init__(self, client, watch_db=None, *, ttl_s: float = CACHE_TTL_S) -> None:
        self._client = client
        self._db = watch_db
        self._ttl_s = ttl_s
        self._pruned_at = float("-inf")

    async def park(
        self, campground: Campground, nights: list[date], end: date,
    ) -> CampgroundAvailability:
        """Availability for ``nights`` at one park. Each window is stored as soon
        as all its pages are in, so a park cut part-way keeps its finished
        windows. A window cut mid-fetch stores nothing."""
        park_id = campground.facility_id
        started = time.monotonic()
        p = plan(nights, self._stored(park_id, nights), end)
        windows = list(p.use)
        outcome = "cancelled"
        with count_requests() as requests:
            try:
                for arrival, departure in p.fetch:
                    fetched_at = datetime.now()
                    availability = await self._client.get_window(
                        park_id, campground.booking_url_slug, campground.state,
                        arrival, departure,
                    )
                    window = CachedWindow(arrival, departure, fetched_at, availability)
                    self._store(park_id, window)
                    windows.append(window)
                result = merge(park_id, windows)
                outcome = f"{len(result.campsites)} sites"
                return result
            except Exception as exc:
                outcome = type(exc).__name__
                raise
            finally:
                logger.info(
                    "ReserveAmerica %s: %d windows (%d cached, %d fetched), "
                    "%d requests in %.1fs (%s)",
                    park_id, len(p.use) + len(p.fetch), len(p.use), len(p.fetch),
                    requests[0], time.monotonic() - started, outcome,
                )

    def _stored(self, park_id: str, nights: list[date]) -> list[CachedWindow]:
        """Fresh stored windows for the nights. A cache problem is a miss."""
        if self._db is None or not nights:
            return []
        try:
            return [
                CachedWindow(a, d, at, CampgroundAvailability.model_validate_json(payload))
                for a, d, at, payload in self._db.get_ra_windows(
                    park_id, min(nights), max(nights), max_age_s=self._ttl_s,
                )
            ]
        except Exception:
            logger.debug("ReserveAmerica window cache read failed", exc_info=True)
            return []

    def _store(self, park_id: str, window: CachedWindow) -> None:
        if self._db is None:
            return
        try:
            self._db.put_ra_window(
                park_id, window.arrival, window.departure,
                window.availability.model_dump_json(), window.fetched_at,
            )
            if time.monotonic() - self._pruned_at >= PRUNE_EVERY_S:
                self._pruned_at = time.monotonic()
                self._db.prune_ra_windows(self._ttl_s)
        except Exception:
            logger.debug("ReserveAmerica window cache write failed", exc_info=True)
