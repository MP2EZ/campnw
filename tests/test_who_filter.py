"""The `who` filter (v1.48 D5): party size, equipment and rig length.

Unknown (None) never drops a site: a park with no type data stays in results.
"""

from __future__ import annotations

from datetime import date

import pytest

from pnw_campsites.registry.models import BookingSystem, SiteFit
from pnw_campsites.search.engine import SearchQuery, _process_availability
from pnw_campsites.search.who import fits_equipment, fits_party
from tests.conftest import (
    make_campground,
    make_campground_availability,
    make_campsite_availability,
)

TENT_ONLY = SiteFit(fits_tent=True, fits_van=False, fits_rv=False)
RV_30 = SiteFit(fits_tent=True, fits_van=True, fits_rv=True, max_rv_ft=30)
RV_ANY_LENGTH = SiteFit(fits_tent=False, fits_van=True, fits_rv=True, max_rv_ft=None)
UNKNOWN = SiteFit()


class TestFitsParty:
    def test_no_party_size_passes(self) -> None:
        assert fits_party(4, None)

    def test_site_big_enough(self) -> None:
        assert fits_party(6, 6)

    def test_site_too_small(self) -> None:
        assert not fits_party(4, 6)

    def test_unknown_capacity_passes(self) -> None:
        assert fits_party(None, 12)


class TestFitsEquipment:
    def test_no_equipment_passes_everything(self) -> None:
        assert fits_equipment(TENT_ONLY, None, None)

    @pytest.mark.parametrize(
        ("fit", "equipment", "expected"),
        [
            (TENT_ONLY, "tent", True),
            (TENT_ONLY, "van", False),
            (TENT_ONLY, "trailer", False),
            (RV_ANY_LENGTH, "tent", False),
            (RV_ANY_LENGTH, "van", True),
            (RV_30, "trailer", True),
        ],
    )
    def test_known_types(self, fit: SiteFit, equipment: str, expected: bool) -> None:
        assert fits_equipment(fit, equipment, None) is expected

    @pytest.mark.parametrize("equipment", ["tent", "van", "trailer"])
    def test_unknown_types_pass(self, equipment: str) -> None:
        assert fits_equipment(UNKNOWN, equipment, 35)

    def test_trailer_within_length(self) -> None:
        assert fits_equipment(RV_30, "trailer", 30)

    def test_trailer_too_long(self) -> None:
        assert not fits_equipment(RV_30, "trailer", 35)

    def test_rv_with_no_stated_length_takes_any_length(self) -> None:
        assert fits_equipment(RV_ANY_LENGTH, "trailer", 40)

    def test_length_ignored_for_non_trailers(self) -> None:
        assert fits_equipment(RV_30, "van", 35)

    def test_unknown_equipment_is_ignored(self) -> None:
        assert fits_equipment(TENT_ONLY, "boat", None)


# ---------------------------------------------------------------------------
# Engine: windows are filtered per site
# ---------------------------------------------------------------------------


def _site(campsite_id: str, *, max_people: int = 6, fit: SiteFit | None = None,
          campsite_type: str = "STANDARD NONELECTRIC"):
    site = make_campsite_availability(
        campsite_id=campsite_id, site=campsite_id, max_people=max_people,
        campsite_type=campsite_type,
    )
    site.fit = fit
    return site


def _window_sites(campground, sites, **who) -> list[str]:
    query = SearchQuery(start_date=date(2026, 6, 1), end_date=date(2026, 6, 30), **who)
    availability = make_campground_availability(
        campground.facility_id, {s.campsite_id: s for s in sites},
    )
    windows = _process_availability(campground, availability, query).available_windows
    return sorted({w.campsite_id for w in windows})


def test_party_size_drops_small_sites() -> None:
    sites = [_site("a", max_people=4), _site("b", max_people=8)]
    assert _window_sites(make_campground(), sites, max_people=6) == ["b"]


def test_unseeded_wa_placeholder_capacity_is_unknown() -> None:
    wa = make_campground(facility_id="-1", booking_system=BookingSystem.WA_STATE)
    site = _site("-5", max_people=8, campsite_type="STANDARD")
    site.max_people_known = False
    assert _window_sites(wa, [site], max_people=12) == ["-5"]


def test_equipment_drops_known_misfits_and_keeps_unknown() -> None:
    sites = [_site("tent", fit=TENT_ONLY), _site("rv", fit=RV_30), _site("x", fit=UNKNOWN)]
    camp = make_campground(booking_system=BookingSystem.OR_STATE)
    assert _window_sites(camp, sites, equipment="trailer") == ["rv", "x"]
    assert _window_sites(camp, sites, equipment="trailer", rig_length=35) == ["x"]


def test_recgov_type_drives_equipment_filter() -> None:
    sites = [
        _site("t", campsite_type="TENT ONLY NONELECTRIC"),
        _site("r", campsite_type="RV NONELECTRIC"),
    ]
    assert _window_sites(make_campground(), sites, equipment="trailer") == ["r"]


# ---------------------------------------------------------------------------
# Which capacities are placeholders
# ---------------------------------------------------------------------------


def test_ra_capacity_known_only_when_listed() -> None:
    from pnw_campsites.providers.reserveamerica import _record_to_campsite
    from tests.test_provider_reserveamerica import _make_record

    assert _record_to_campsite(_make_record(max_people="6"), {}).max_people_known
    assert not _record_to_campsite(_make_record(max_people=""), {}).max_people_known


def test_wa_enrichment_makes_capacity_known(registry) -> None:
    from pnw_campsites.search.engine import SearchEngine

    registry.bulk_upsert_wa_sites(
        "-9", [{"resource_id": -1, "name": "1", "loop_map_id": None, "max_capacity": 4,
                "allowed_equipment": []}],
    )
    site = _site("-1", max_people=8, campsite_type="STANDARD")
    site.max_people_known = False
    SearchEngine(registry=registry)._enrich_wa_availability(
        "-9", make_campground_availability("-9", {"-1": site}),
    )
    assert (site.max_num_people, site.max_people_known) == (4, True)


# ---------------------------------------------------------------------------
# Routes: /api/search and the stream pass `who` to the engine
# ---------------------------------------------------------------------------


class _CapturingEngine:
    def __init__(self) -> None:
        self.queries: list[SearchQuery] = []

    async def search(self, query):
        from pnw_campsites.search.engine import SearchResults

        self.queries.append(query)
        return SearchResults(query=query)

    async def search_stream(self, query):
        self.queries.append(query)
        return
        yield


@pytest.fixture
def engine(monkeypatch) -> _CapturingEngine:
    from pnw_campsites.routes import search as search_routes

    fake = _CapturingEngine()
    monkeypatch.setattr(search_routes, "get_engine", lambda: fake)
    return fake


DATES = {"start_date": "2027-06-04", "end_date": "2027-06-27"}


@pytest.mark.parametrize("path", ["/api/search", "/api/search/stream"])
def test_route_passes_who(api_client, engine, path) -> None:
    resp = api_client.get(path, params={**DATES, "people": 5, "equipment": "trailer", "rig_length": 30})
    assert resp.status_code == 200
    q = engine.queries[0]
    assert (q.max_people, q.equipment, q.rig_length) == (5, "trailer", 30)


@pytest.mark.parametrize("path", ["/api/search", "/api/search/stream"])
def test_rig_length_only_for_trailers(api_client, engine, path) -> None:
    api_client.get(path, params={**DATES, "equipment": "van", "rig_length": 30})
    assert (engine.queries[0].equipment, engine.queries[0].rig_length) == ("van", None)


def test_route_rejects_unknown_equipment(api_client, engine) -> None:
    assert api_client.get("/api/search", params={**DATES, "equipment": "boat"}).status_code == 422


def test_not_released_counts_only_fitting_sites_but_closed_ignores_who() -> None:
    from pnw_campsites.search.engine import _night_statuses, _not_released_nights

    tent = make_campsite_availability(
        campsite_id="tent", dates_status={"2026-06-01T00:00:00.000Z": "NYR"},
    )
    tent.fit = TENT_ONLY
    avail = make_campground_availability("1", {"tent": tent})
    q = SearchQuery(start_date=date(2026, 6, 1), end_date=date(2026, 6, 1), equipment="trailer")
    assert _not_released_nights(avail, q, BookingSystem.OR_STATE) == []
    any_nyr, closed = _night_statuses(avail, q, BookingSystem.OR_STATE)
    assert (any_nyr, closed) == ([], [])
