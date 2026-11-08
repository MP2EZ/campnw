"""The `who` filter (v1.48 D5): does a site take this party and rig?

Pure functions. Unknown (None) always passes: a site the booking system
says nothing about must never drop out of results.
"""

from __future__ import annotations

from pnw_campsites.registry.models import SiteFit

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
