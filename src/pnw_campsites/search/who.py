"""The `who` filter (v1.48 D5): does a site take this party and rig?

Pure functions. Unknown (None) always passes: a site the booking system
says nothing about must never drop out of results.
"""

from __future__ import annotations

from pnw_campsites.registry.models import BookingSystem, CampsiteAvailability, SiteFit
from pnw_campsites.search.site_fit import site_fit_for

EQUIPMENT = ("tent", "van", "trailer")


def fits_party(max_people: int | None, people: int | None) -> bool:
    """False only when the site's known capacity is below the party size."""
    return not (people and max_people is not None and max_people < people)


def fits_equipment(fit: SiteFit, equipment: str | None, rig_length: int | None) -> bool:
    """False only when the site is known not to take the rig.

    `rig_length` (feet) applies to trailers only. An RV site with no stated
    length (`max_rv_ft` None) takes any length.
    """
    if equipment == "tent":
        return fit.fits_tent is not False
    if equipment == "van":
        return fit.fits_van is not False
    if equipment == "trailer":
        if fit.fits_rv is False:
            return False
        return not (rig_length and fit.max_rv_ft is not None and fit.max_rv_ft < rig_length)
    return True


# Watch site-type filter values (v1.48 P3c). A site passes when it has any
# listed feature, or when the booking system doesn't say.
SITE_TYPES = ("hookups", "walk_in")


def fits_site_types(fit: SiteFit, site_types: list[str] | None) -> bool:
    """False only when the site is known to have none of `site_types`."""
    wanted = [t for t in site_types or [] if t in SITE_TYPES]
    return not wanted or any(getattr(fit, t) is not False for t in wanted)


def site_fits(
    site: CampsiteAvailability,
    system: BookingSystem,
    *,
    people: int | None = None,
    equipment: str | None = None,
    rig_length: int | None = None,
    site_types: list[str] | None = None,
) -> bool:
    """The whole `who` check for one site, shared by search and the watch poller.

    A placeholder capacity (`max_people_known` False) counts as unknown.
    """
    capacity = site.max_num_people if site.max_people_known else None
    fit = site_fit_for(site, system)
    return (
        fits_party(capacity, people)
        and fits_equipment(fit, equipment, rig_length)
        and fits_site_types(fit, site_types)
    )
