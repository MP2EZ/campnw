"""Tests for URL builder functions."""

from datetime import date

from pnw_campsites.urls import (
    or_state_availability_url,
    or_state_campsite_booking_url,
    recgov_availability_url,
    recgov_campground_url,
    recgov_campsite_booking_url,
    wa_state_availability_url,
    wa_state_park_url,
)


class TestRecgovCampgroundUrl:
    def test_basic_url_structure(self):
        assert recgov_campground_url("232465") == (
            "https://www.recreation.gov/camping/campgrounds/232465"
        )


class TestRecgovAvailabilityUrl:
    def test_without_date(self):
        assert recgov_availability_url("232465") == (
            "https://www.recreation.gov/camping/campgrounds/232465/availability"
        )

    def test_with_date(self):
        url = recgov_availability_url("232465", start_date=date(2026, 6, 15))
        assert url == (
            "https://www.recreation.gov/camping/campgrounds/"
            "232465/availability?startDate=2026-06-15"
        )


class TestRecgovCampsitBookingUrl:
    def test_parameter_order(self):
        url = recgov_campsite_booking_url("100", "50", date(2026, 7, 1), date(2026, 7, 3))
        assert url == (
            "https://www.recreation.gov/camping/campsites/50"
            "?startDate=2026-07-01"
            "&endDate=2026-07-03"
            "&facilityId=100"
        )


class TestWaStateParkUrl:
    def test_basic_structure(self):
        assert wa_state_park_url("-2147483624") == (
            "https://washington.goingtocamp.com/create-booking/results"
            "?resourceLocationId=-2147483624"
        )


class TestWaStateAvailabilityUrl:
    def test_without_dates(self):
        assert wa_state_availability_url("-2147483624") == (
            "https://washington.goingtocamp.com/create-booking/results"
            "?resourceLocationId=-2147483624"
        )

    def test_with_start_date_only(self):
        url = wa_state_availability_url("-2147483624", start_date=date(2026, 6, 15))
        assert "searchTime=2026-06-15" in url
        assert "endDate" not in url

    def test_with_end_date_only(self):
        url = wa_state_availability_url("-2147483624", end_date=date(2026, 6, 20))
        assert "endDate=2026-06-20" in url
        assert "searchTime" not in url

    def test_parameter_order_with_both_dates(self):
        url = wa_state_availability_url(
            "-123", start_date=date(2026, 7, 1), end_date=date(2026, 7, 5)
        )
        assert url == (
            "https://washington.goingtocamp.com/create-booking/results"
            "?resourceLocationId=-123"
            "&searchTime=2026-07-01"
            "&endDate=2026-07-05"
        )


class TestOrStateAvailabilityUrl:
    def test_without_dates(self):
        assert or_state_availability_url("402178", "fort-stevens-state-park") == (
            "https://www.reserveamerica.com/explore/"
            "fort-stevens-state-park/OR/402178/campsite-availability"
        )

    def test_with_start_date(self):
        url = or_state_availability_url(
            "402334", "jessie-m-honeyman-memorial-state-park",
            start_date=date(2026, 7, 1),
        )
        assert url == (
            "https://www.reserveamerica.com/explore/"
            "jessie-m-honeyman-memorial-state-park/OR/402334/"
            "campsite-availability?arrivalDate=2026-07-01"
        )


class TestOrStateCampsitBookingUrl:
    def test_full_url(self):
        url = or_state_campsite_booking_url(
            "402178", "fort-stevens-state-park", "3171",
            date(2026, 6, 15), date(2026, 6, 17),
        )
        assert url == (
            "https://www.reserveamerica.com/explore/"
            "fort-stevens-state-park/OR/402178/3171/campsite-booking"
            "?arrivalDate=2026-06-15"
            "&departureDate=2026-06-17"
        )
