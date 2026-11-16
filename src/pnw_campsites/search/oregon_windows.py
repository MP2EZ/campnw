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

from dataclasses import dataclass
from datetime import date, datetime

from pnw_campsites.providers.reserveamerica import window_cover
from pnw_campsites.registry.models import CampgroundAvailability


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
