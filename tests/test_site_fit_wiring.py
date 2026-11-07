"""Site fit flows from each provider's data to WindowResponse."""

from __future__ import annotations

from datetime import date

from pnw_campsites.providers.reserveamerica import _record_to_campsite
from pnw_campsites.registry.models import BookingSystem, SiteFit
from pnw_campsites.routes.search import _format_result
from pnw_campsites.search.engine import SearchEngine, SearchQuery, _process_availability
from tests.conftest import (
    make_campground,
    make_campground_availability,
    make_campsite_availability,
)
from tests.test_provider_reserveamerica import _make_record
from tests.test_site_fit import FORT_EBEY_7, FORT_EBEY_MAIN

QUERY = SearchQuery(start_date=date(2026, 6, 1), end_date=date(2026, 6, 30))


def _windows(campground, campsite):
    availability = make_campground_availability(
        facility_id=campground.facility_id, campsites={campsite.campsite_id: campsite},
    )
    return _process_availability(campground, availability, QUERY).available_windows


def test_wa_enrichment_sets_fit_from_equipment_and_loop(registry) -> None:
    registry.bulk_upsert_wa_loops(
        "-2147483616", [{"map_id": -1, "title": "Main", "description": FORT_EBEY_MAIN}],
    )
    registry.bulk_upsert_wa_sites(
        "-2147483616",
        [{"resource_id": -27, "name": "27", "loop_map_id": -1, "max_capacity": 8,
          "allowed_equipment": FORT_EBEY_7}],
    )
    campsite = make_campsite_availability(campsite_id="-27", site="-27", campsite_type="STANDARD")
    availability = make_campground_availability("-2147483616", {"-27": campsite})

    SearchEngine(registry=registry)._enrich_wa_availability("-2147483616", availability)

    assert campsite.fit == SiteFit(
        fits_tent=True, fits_van=True, fits_rv=True, max_rv_ft=30, hookups=True, walk_in=False,
    )
    wa = make_campground(facility_id="-2147483616", booking_system=BookingSystem.WA_STATE)
    assert _windows(wa, campsite)[0].fit == campsite.fit


def test_unseeded_wa_site_is_unknown_not_standard() -> None:
    wa = make_campground(facility_id="-1", booking_system=BookingSystem.WA_STATE)
    campsite = make_campsite_availability(campsite_type="STANDARD")
    assert _windows(wa, campsite)[0].fit == SiteFit()


def test_recgov_window_fit_comes_from_campsite_type() -> None:
    campsite = make_campsite_availability(campsite_type="TENT ONLY NONELECTRIC")
    fit = _windows(make_campground(), campsite)[0].fit
    assert (fit.fits_tent, fit.fits_rv, fit.hookups) == (True, False, False)


def test_reserveamerica_record_carries_fit() -> None:
    record = _make_record(prod_grp="STANDARD")
    record["details"]["attributes"] += [
        {"id": 99999, "value": ["RV Site", "Tent Site", "Trailer Site"]},
        {"id": 109, "value": ["38"]},
        {"id": 218, "value": ["30"]},
    ]
    fit = _record_to_campsite(record, {}).fit
    assert (fit.fits_rv, fit.max_rv_ft, fit.hookups) == (True, 38, True)


def test_reserveamerica_record_without_fit_attributes_is_unknown() -> None:
    assert _record_to_campsite(_make_record(), {}).fit == SiteFit()


def test_window_response_has_flat_fit_fields() -> None:
    campsite = make_campsite_availability(campsite_type="RV ELECTRIC")
    cg = make_campground()
    result = _process_availability(
        cg, make_campground_availability(campsites={campsite.campsite_id: campsite}), QUERY,
    )
    window = _format_result(result, cg.booking_system).windows[0].model_dump()
    assert {k: window[k] for k in SiteFit.model_fields} == {
        "fits_tent": None, "fits_van": True, "fits_rv": True,
        "max_rv_ft": None, "hookups": True, "walk_in": False,
    }
