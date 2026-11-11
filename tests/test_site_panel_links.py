"""Per-window booking links and capacity for the v1.48 site panel (P3b).

A window's end_date is its last night. Booking sites want the checkout day,
so every per-site link sends end_date + 1.
"""

from __future__ import annotations

from datetime import date

from pnw_campsites.registry.models import BookingSystem
from pnw_campsites.routes.search import _format_result
from pnw_campsites.search.engine import (
    AvailableWindow,
    CampgroundResult,
    SearchEngine,
    SearchQuery,
    _process_availability,
)
from pnw_campsites.urls import wa_state_site_booking_url
from tests.conftest import (
    make_campground,
    make_campground_availability,
    make_campsite_availability,
)

GTC = "https://washington.goingtocamp.com/create-booking/results"


def _window(**overrides) -> AvailableWindow:
    fields = dict(
        campsite_id="80633", site_name="001", loop="A", campsite_type="STANDARD",
        start_date="2027-01-08", end_date="2027-01-09", nights=2, max_people=8,
    )
    fields.update(overrides)
    return AvailableWindow(**fields)


def _formatted(campground, window):
    result = CampgroundResult(
        campground=campground, available_windows=[window], total_available_sites=1,
    )
    return _format_result(result, campground.booking_system).windows[0]


class TestWaSiteBookingUrl:
    def test_opens_the_sites_loop_with_dates_and_nights(self):
        url = wa_state_site_booking_url(
            "-2147483624", -2147483614, date(2027, 1, 8), date(2027, 1, 10),
        )
        assert url == (
            f"{GTC}?mapId=-2147483614&resourceLocationId=-2147483624"
            "&searchTabGroupId=0&bookingCategoryId=0"
            "&startDate=2027-01-08&endDate=2027-01-10&nights=2&isReserving=true"
        )

    def test_without_a_loop_it_still_sends_the_dates(self):
        url = wa_state_site_booking_url("-2147483624", None, date(2027, 1, 8), date(2027, 1, 9))
        assert "mapId" not in url
        assert "resourceLocationId=-2147483624" in url
        assert "startDate=2027-01-08&endDate=2027-01-09&nights=1" in url


class TestWindowBookingUrls:
    def test_recgov_end_date_is_the_checkout_day(self):
        w = _formatted(make_campground(facility_id="234502"), _window())
        assert "startDate=2027-01-08&endDate=2027-01-10" in w.booking_url

    def test_reserveamerica_departure_is_the_checkout_day(self):
        cg = make_campground(
            facility_id="402178", booking_system=BookingSystem.OR_STATE,
            booking_url_slug="fort-stevens-state-park",
        )
        w = _formatted(cg, _window(campsite_id="14271"))
        assert w.booking_url.endswith(
            "/402178/14271/campsite-booking?arrivalDate=2027-01-08&departureDate=2027-01-10",
        )

    def test_wa_window_links_to_its_loop(self):
        cg = make_campground(facility_id="-2147483624", booking_system=BookingSystem.WA_STATE)
        w = _formatted(cg, _window(loop_map_id=-2147483614))
        assert w.booking_url == wa_state_site_booking_url(
            "-2147483624", -2147483614, date(2027, 1, 8), date(2027, 1, 10),
        )

    def test_capacity_known_rides_on_the_window(self):
        assert _formatted(make_campground(), _window()).max_people_known is True
        assert _formatted(make_campground(), _window(max_people_known=False)).max_people_known is False


class TestEngineCarriesSiteFacts:
    QUERY = SearchQuery(start_date=date(2026, 6, 1), end_date=date(2026, 6, 30))

    def test_wa_enrichment_sets_the_loop_map_and_windows_keep_it(self, registry):
        registry.bulk_upsert_wa_loops("-5", [{"map_id": -9, "title": "Main", "description": ""}])
        registry.bulk_upsert_wa_sites(
            "-5", [{"resource_id": -27, "name": "27", "loop_map_id": -9, "max_capacity": None,
                    "allowed_equipment": []}],
        )
        campsite = make_campsite_availability(campsite_id="-27", site="-27")
        campsite.max_people_known = False
        availability = make_campground_availability("-5", {"-27": campsite})

        SearchEngine(registry=registry)._enrich_wa_availability("-5", availability)

        wa = make_campground(facility_id="-5", booking_system=BookingSystem.WA_STATE)
        [window] = _process_availability(wa, availability, self.QUERY).available_windows
        assert window.loop_map_id == -9
        assert window.max_people_known is False
