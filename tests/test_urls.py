"""Tests for URL builder functions."""

from datetime import date

from pnw_campsites.urls import (
    recgov_availability_url,
    recgov_campground_url,
    recgov_campsite_booking_url,
    wa_state_availability_url,
    wa_state_park_url,
)


class TestRecgovCampgroundUrl:
    """Tests for recgov_campground_url."""

    def test_basic_url_structure(self):
        """URL contains correct base and facility_id."""
        url = recgov_campground_url("232465")
        assert url == "https://www.recreation.gov/camping/campgrounds/232465"

    def test_different_facility_ids(self):
        """URL works with various facility IDs."""
        for facility_id in ["100", "999999", "42"]:
            url = recgov_campground_url(facility_id)
            assert f"/campgrounds/{facility_id}" in url
            assert url.startswith("https://www.recreation.gov/")


class TestRecgovAvailabilityUrl:
    """Tests for recgov_availability_url."""

    def test_without_date(self):
        """URL without start_date has no query params."""
        url = recgov_availability_url("232465")
        assert url == (
            "https://www.recreation.gov/camping/campgrounds/232465/availability"
        )
        assert "?" not in url

    def test_with_date(self):
        """URL with start_date includes startDate query parameter."""
        start_date = date(2026, 6, 15)
        url = recgov_availability_url("232465", start_date=start_date)
        assert "startDate=2026-06-15" in url
        assert url == (
            "https://www.recreation.gov/camping/campgrounds/"
            "232465/availability?startDate=2026-06-15"
        )

    def test_date_format_iso(self):
        """Date parameter uses ISO format (YYYY-MM-DD)."""
        start_date = date(2026, 3, 1)
        url = recgov_availability_url("100", start_date=start_date)
        assert "startDate=2026-03-01" in url

    def test_none_date_treated_as_no_date(self):
        """Explicitly passing None for date produces no query params."""
        url = recgov_availability_url("232465", start_date=None)
        assert "?" not in url


class TestRecgovCampsitBookingUrl:
    """Tests for recgov_campsite_booking_url."""

    def test_basic_structure(self):
        """URL contains campsite_id and date parameters."""
        start = date(2026, 6, 15)
        end = date(2026, 6, 17)
        url = recgov_campsite_booking_url("232465", "999", start, end)
        assert "https://www.recreation.gov/camping/campsites/999" in url
        assert "startDate=2026-06-15" in url
        assert "endDate=2026-06-17" in url
        assert "facilityId=232465" in url

    def test_parameter_order(self):
        """URL parameters are in expected order."""
        start = date(2026, 7, 1)
        end = date(2026, 7, 3)
        url = recgov_campsite_booking_url("100", "50", start, end)
        expected = (
            "https://www.recreation.gov/camping/campsites/50"
            "?startDate=2026-07-01"
            "&endDate=2026-07-03"
            "&facilityId=100"
        )
        assert url == expected

    def test_date_formats_iso(self):
        """Both dates use ISO format."""
        start = date(2026, 12, 25)
        end = date(2026, 12, 27)
        url = recgov_campsite_booking_url("999", "777", start, end)
        assert "startDate=2026-12-25" in url
        assert "endDate=2026-12-27" in url

    def test_single_night_booking(self):
        """Consecutive dates work (checkout same day as next checkin)."""
        start = date(2026, 8, 10)
        end = date(2026, 8, 11)
        url = recgov_campsite_booking_url("232465", "1", start, end)
        assert "startDate=2026-08-10" in url
        assert "endDate=2026-08-11" in url


class TestWaStateParkUrl:
    """Tests for wa_state_park_url."""

    def test_basic_structure(self):
        """URL contains resourceLocationId parameter."""
        url = wa_state_park_url("-2147483624")
        assert url == (
            "https://washington.goingtocamp.com/create-booking/results"
            "?resourceLocationId=-2147483624"
        )

    def test_positive_resource_ids(self):
        """Works with positive resource IDs."""
        url = wa_state_park_url("123456")
        assert "resourceLocationId=123456" in url

    def test_negative_resource_ids(self):
        """Works with negative resource IDs (WA State Parks)."""
        url = wa_state_park_url("-999")
        assert "resourceLocationId=-999" in url


class TestWaStateAvailabilityUrl:
    """Tests for wa_state_availability_url."""

    def test_without_dates(self):
        """URL without dates has only resourceLocationId."""
        url = wa_state_availability_url("-2147483624")
        assert url == (
            "https://washington.goingtocamp.com/create-booking/results"
            "?resourceLocationId=-2147483624"
        )
        assert "searchTime" not in url
        assert "endDate" not in url

    def test_with_start_date_only(self):
        """URL with start_date includes searchTime parameter."""
        start = date(2026, 6, 15)
        url = wa_state_availability_url("-2147483624", start_date=start)
        assert "searchTime=2026-06-15" in url
        assert "resourceLocationId=-2147483624" in url
        assert "endDate" not in url

    def test_with_end_date_only(self):
        """URL with end_date includes endDate parameter."""
        end = date(2026, 6, 20)
        url = wa_state_availability_url("-2147483624", end_date=end)
        assert "endDate=2026-06-20" in url
        assert "resourceLocationId=-2147483624" in url
        assert "searchTime" not in url

    def test_with_both_dates(self):
        """URL with both dates includes both parameters."""
        start = date(2026, 6, 15)
        end = date(2026, 6, 20)
        url = wa_state_availability_url("-2147483624", start_date=start, end_date=end)
        assert "searchTime=2026-06-15" in url
        assert "endDate=2026-06-20" in url
        assert "resourceLocationId=-2147483624" in url

    def test_parameter_order_with_both_dates(self):
        """Parameters appear in expected order."""
        start = date(2026, 7, 1)
        end = date(2026, 7, 5)
        url = wa_state_availability_url("-123", start_date=start, end_date=end)
        expected = (
            "https://washington.goingtocamp.com/create-booking/results"
            "?resourceLocationId=-123"
            "&searchTime=2026-07-01"
            "&endDate=2026-07-05"
        )
        assert url == expected

    def test_none_dates_ignored(self):
        """Explicitly passing None for dates produces no params."""
        url = wa_state_availability_url(
            "-2147483624", start_date=None, end_date=None
        )
        assert url == (
            "https://washington.goingtocamp.com/create-booking/results"
            "?resourceLocationId=-2147483624"
        )
