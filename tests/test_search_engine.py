"""Tests for the search engine discovery logic."""

from __future__ import annotations

from datetime import date

from pnw_campsites.search.engine import (
    LONG_WEEKEND,
    WEEKDAYS,
    WEEKEND,
    SearchQuery,
    _find_consecutive_windows,
    _process_availability,
    days,
    next_weekend,
    this_weekend,
)


class TestFindConsecutiveWindows:
    """Test _find_consecutive_windows pure function."""

    def test_single_available_date_min_nights_one(self) -> None:
        """Single available date with min_nights=1 yields 1 window."""
        site = make_campsite_availability(
            dates_status={"2026-06-01T00:00:00.000Z": "Available"}
        )
        windows = _find_consecutive_windows(
            site, date(2026, 6, 1), date(2026, 6, 30), min_nights=1
        )

        assert len(windows) == 1
        assert windows[0].start_date == "2026-06-01"
        assert windows[0].end_date == "2026-06-01"
        assert windows[0].nights == 1

    def test_single_available_date_min_nights_two(self) -> None:
        """Single available date with min_nights=2 yields no windows."""
        site = make_campsite_availability(
            dates_status={"2026-06-01T00:00:00.000Z": "Available"}
        )
        windows = _find_consecutive_windows(
            site, date(2026, 6, 1), date(2026, 6, 30), min_nights=2
        )

        assert len(windows) == 0

    def test_three_consecutive_dates_min_nights_two(self) -> None:
        """Three consecutive available dates with min_nights=2 yields 1 window."""
        site = make_campsite_availability(
            dates_status={
                "2026-06-01T00:00:00.000Z": "Available",
                "2026-06-02T00:00:00.000Z": "Available",
                "2026-06-03T00:00:00.000Z": "Available",
            }
        )
        windows = _find_consecutive_windows(
            site, date(2026, 6, 1), date(2026, 6, 30), min_nights=2
        )

        assert len(windows) == 1
        assert windows[0].start_date == "2026-06-01"
        assert windows[0].end_date == "2026-06-03"
        assert windows[0].nights == 3

    def test_gap_in_dates_splits_windows(self) -> None:
        """Gap in available dates creates separate windows."""
        site = make_campsite_availability(
            dates_status={
                "2026-06-01T00:00:00.000Z": "Available",
                "2026-06-02T00:00:00.000Z": "Available",
                "2026-06-03T00:00:00.000Z": "Reserved",
                "2026-06-04T00:00:00.000Z": "Available",
                "2026-06-05T00:00:00.000Z": "Available",
            }
        )
        windows = _find_consecutive_windows(
            site, date(2026, 6, 1), date(2026, 6, 30), min_nights=2
        )

        assert len(windows) == 2
        assert windows[0].start_date == "2026-06-01"
        assert windows[0].end_date == "2026-06-02"
        assert windows[1].start_date == "2026-06-04"
        assert windows[1].end_date == "2026-06-05"

    def test_gap_creates_single_day_window_below_threshold(self) -> None:
        """Single-day gap between longer runs still gets filtered."""
        site = make_campsite_availability(
            dates_status={
                "2026-06-01T00:00:00.000Z": "Available",
                "2026-06-02T00:00:00.000Z": "Available",
                "2026-06-03T00:00:00.000Z": "Reserved",
                "2026-06-04T00:00:00.000Z": "Available",
            }
        )
        windows = _find_consecutive_windows(
            site, date(2026, 6, 1), date(2026, 6, 30), min_nights=2
        )

        # Only the first run meets min_nights=2
        assert len(windows) == 1
        assert windows[0].start_date == "2026-06-01"
        assert windows[0].end_date == "2026-06-02"

    def test_day_of_week_filter_weekend_only(self) -> None:
        """Day-of-week filter (Fri-Sun) only keeps weekend dates."""
        # June 2026: 1=Mon, 2=Tue, 3=Wed, 4=Thu, 5=Fri, 6=Sat, 7=Sun
        site = make_campsite_availability(
            dates_status={
                "2026-06-01T00:00:00.000Z": "Available",  # Mon
                "2026-06-02T00:00:00.000Z": "Available",  # Tue
                "2026-06-05T00:00:00.000Z": "Available",  # Fri
                "2026-06-06T00:00:00.000Z": "Available",  # Sat
                "2026-06-07T00:00:00.000Z": "Available",  # Sun
            }
        )
        windows = _find_consecutive_windows(
            site,
            date(2026, 6, 1),
            date(2026, 6, 30),
            min_nights=2,
            days_of_week={4, 5, 6},  # Fri, Sat, Sun
        )

        # Only Fri-Sun window survives filtering
        assert len(windows) == 1
        assert windows[0].start_date == "2026-06-05"
        assert windows[0].end_date == "2026-06-07"
        assert windows[0].nights == 3

    def test_day_of_week_filter_breaks_at_boundary(self) -> None:
        """Day-of-week filter breaks consecutive run at day boundary."""
        # June: 5=Fri, 6=Sat, 7=Sun, 8=Mon, 9=Tue, 10=Wed, 11=Thu, 12=Fri, 13=Sat
        site = make_campsite_availability(
            dates_status={
                "2026-06-05T00:00:00.000Z": "Available",  # Fri
                "2026-06-06T00:00:00.000Z": "Available",  # Sat
                "2026-06-07T00:00:00.000Z": "Available",  # Sun
                "2026-06-08T00:00:00.000Z": "Available",  # Mon (not in dow)
                "2026-06-09T00:00:00.000Z": "Available",  # Tue (not in dow)
                "2026-06-12T00:00:00.000Z": "Available",  # Fri
                "2026-06-13T00:00:00.000Z": "Available",  # Sat
            }
        )
        windows = _find_consecutive_windows(
            site,
            date(2026, 6, 1),
            date(2026, 6, 30),
            min_nights=2,
            days_of_week={4, 5, 6},  # Fri, Sat, Sun only
        )

        # Should find 2 windows: first Fri-Sun and second Fri-Sat
        assert len(windows) == 2
        assert windows[0].start_date == "2026-06-05"
        assert windows[0].end_date == "2026-06-07"
        assert windows[1].start_date == "2026-06-12"
        assert windows[1].end_date == "2026-06-13"

    def test_all_dates_outside_range_empty(self) -> None:
        """Dates outside requested range yield no windows."""
        site = make_campsite_availability(
            dates_status={
                "2026-06-01T00:00:00.000Z": "Available",
                "2026-06-02T00:00:00.000Z": "Available",
            }
        )
        windows = _find_consecutive_windows(
            site, date(2026, 7, 1), date(2026, 7, 31), min_nights=1
        )

        assert len(windows) == 0

    def test_empty_available_dates_empty_windows(self) -> None:
        """Site with no available dates yields no windows."""
        site = make_campsite_availability(
            dates_status={
                "2026-06-01T00:00:00.000Z": "Reserved",
                "2026-06-02T00:00:00.000Z": "Reserved",
            }
        )
        windows = _find_consecutive_windows(
            site, date(2026, 6, 1), date(2026, 6, 30), min_nights=1
        )

        assert len(windows) == 0

    def test_min_nights_seven_with_exactly_seven_consecutive(self) -> None:
        """Seven consecutive dates with min_nights=7 yields 1 window."""
        site = make_campsite_availability(
            dates_status={
                "2026-06-01T00:00:00.000Z": "Available",
                "2026-06-02T00:00:00.000Z": "Available",
                "2026-06-03T00:00:00.000Z": "Available",
                "2026-06-04T00:00:00.000Z": "Available",
                "2026-06-05T00:00:00.000Z": "Available",
                "2026-06-06T00:00:00.000Z": "Available",
                "2026-06-07T00:00:00.000Z": "Available",
            }
        )
        windows = _find_consecutive_windows(
            site, date(2026, 6, 1), date(2026, 6, 30), min_nights=7
        )

        assert len(windows) == 1
        assert windows[0].nights == 7

    def test_min_nights_seven_with_six_consecutive_empty(self) -> None:
        """Six consecutive dates with min_nights=7 yields no windows."""
        site = make_campsite_availability(
            dates_status={
                "2026-06-01T00:00:00.000Z": "Available",
                "2026-06-02T00:00:00.000Z": "Available",
                "2026-06-03T00:00:00.000Z": "Available",
                "2026-06-04T00:00:00.000Z": "Available",
                "2026-06-05T00:00:00.000Z": "Available",
                "2026-06-06T00:00:00.000Z": "Available",
            }
        )
        windows = _find_consecutive_windows(
            site, date(2026, 6, 1), date(2026, 6, 30), min_nights=7
        )

        assert len(windows) == 0

    def test_multiple_separate_runs_in_same_month(self) -> None:
        """Multiple separate runs properly detected."""
        site = make_campsite_availability(
            dates_status={
                "2026-06-01T00:00:00.000Z": "Available",
                "2026-06-02T00:00:00.000Z": "Available",
                "2026-06-05T00:00:00.000Z": "Available",
                "2026-06-06T00:00:00.000Z": "Available",
                "2026-06-10T00:00:00.000Z": "Available",
                "2026-06-11T00:00:00.000Z": "Available",
            }
        )
        windows = _find_consecutive_windows(
            site, date(2026, 6, 1), date(2026, 6, 30), min_nights=2
        )

        assert len(windows) == 3

    def test_dates_spanning_month_boundary(self) -> None:
        """Dates spanning month boundary (June 28 → July 3) work correctly."""
        site = make_campsite_availability(
            dates_status={
                "2026-06-28T00:00:00.000Z": "Available",
                "2026-06-29T00:00:00.000Z": "Available",
                "2026-06-30T00:00:00.000Z": "Available",
                "2026-07-01T00:00:00.000Z": "Available",
                "2026-07-02T00:00:00.000Z": "Available",
                "2026-07-03T00:00:00.000Z": "Available",
            }
        )
        windows = _find_consecutive_windows(
            site, date(2026, 6, 25), date(2026, 7, 5), min_nights=2
        )

        assert len(windows) == 1
        assert windows[0].start_date == "2026-06-28"
        assert windows[0].end_date == "2026-07-03"
        assert windows[0].nights == 6

    def test_fcfs_site_no_available_status_empty_windows(self) -> None:
        """FCFS site (no Available status) yields no windows."""
        site = make_campsite_availability(
            dates_status={
                "2026-06-01T00:00:00.000Z": "Open",
                "2026-06-02T00:00:00.000Z": "Open",
                "2026-06-03T00:00:00.000Z": "Not Reservable",
            }
        )
        windows = _find_consecutive_windows(
            site, date(2026, 6, 1), date(2026, 6, 30), min_nights=1
        )

        assert len(windows) == 0

    def test_site_fields_carried_through_to_window(self) -> None:
        """Site metadata (name, loop, type, max_people) in AvailableWindow."""
        site = make_campsite_availability(
            campsite_id="test-123",
            site="B045",
            loop="Loop B",
            campsite_type="GROUP NONELECTRIC",
            max_people=12,
            dates_status={"2026-06-01T00:00:00.000Z": "Available"},
        )
        windows = _find_consecutive_windows(
            site, date(2026, 6, 1), date(2026, 6, 30), min_nights=1
        )

        assert len(windows) == 1
        assert windows[0].campsite_id == "test-123"
        assert windows[0].site_name == "B045"
        assert windows[0].loop == "Loop B"
        assert windows[0].campsite_type == "GROUP NONELECTRIC"
        assert windows[0].max_people == 12

    def test_window_with_no_date_range_constraints(self) -> None:
        """Windows found when start/end dates are None (check all)."""
        site = make_campsite_availability(
            dates_status={
                "2026-06-01T00:00:00.000Z": "Available",
                "2026-06-02T00:00:00.000Z": "Available",
            }
        )
        windows = _find_consecutive_windows(
            site, start_date=None, end_date=None, min_nights=1
        )

        assert len(windows) == 1
        assert windows[0].nights == 2


class TestProcessAvailability:
    """Test _process_availability pure function."""

    def test_basic_one_campground_two_sites_mixed(self) -> None:
        """Basic case: 1 campground, 2 sites, mixed availability."""
        cg = make_campground(facility_id="232465")
        site1 = make_campsite_availability(
            campsite_id="1",
            dates_status={
                "2026-06-01T00:00:00.000Z": "Available",
                "2026-06-02T00:00:00.000Z": "Available",
            },
        )
        site2 = make_campsite_availability(
            campsite_id="2",
            dates_status={
                "2026-06-01T00:00:00.000Z": "Reserved",
                "2026-06-02T00:00:00.000Z": "Reserved",
            },
        )
        avail = make_campground_availability(
            facility_id="232465", campsites={"1": site1, "2": site2}
        )
        query = SearchQuery(
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 30),
            min_consecutive_nights=1,
        )

        result = _process_availability(cg, avail, query)

        assert result.total_sites == 2
        assert result.total_available_sites == 1  # only site1
        assert len(result.available_windows) == 1
        assert result.available_windows[0].campsite_id == "1"

    def test_group_site_exclusion_when_not_included(self) -> None:
        """GROUP site excluded when include_group_sites=False."""
        cg = make_campground()
        site_standard = make_campsite_availability(
            campsite_id="1",
            campsite_type="STANDARD NONELECTRIC",
            dates_status={"2026-06-01T00:00:00.000Z": "Available"},
        )
        site_group = make_campsite_availability(
            campsite_id="2",
            campsite_type="GROUP NONELECTRIC",
            dates_status={"2026-06-01T00:00:00.000Z": "Available"},
        )
        avail = make_campground_availability(
            campsites={"1": site_standard, "2": site_group}
        )
        query = SearchQuery(
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 30),
            min_consecutive_nights=1,
            include_group_sites=False,
        )

        result = _process_availability(cg, avail, query)

        assert result.total_sites == 2
        assert result.total_available_sites == 1
        assert result.available_windows[0].campsite_id == "1"

    def test_group_site_inclusion_when_requested(self) -> None:
        """GROUP site included when include_group_sites=True."""
        cg = make_campground()
        site_group = make_campsite_availability(
            campsite_id="2",
            campsite_type="GROUP NONELECTRIC",
            dates_status={"2026-06-01T00:00:00.000Z": "Available"},
        )
        avail = make_campground_availability(campsites={"2": site_group})
        query = SearchQuery(
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 30),
            min_consecutive_nights=1,
            include_group_sites=True,
        )

        result = _process_availability(cg, avail, query)

        assert result.total_available_sites == 1

    def test_fcfs_sites_counting(self) -> None:
        """FCFS sites counted separately in fcfs_sites field."""
        cg = make_campground()
        site_fcfs = make_campsite_availability(
            campsite_id="1",
            dates_status={
                "2026-06-01T00:00:00.000Z": "Open",
                "2026-06-02T00:00:00.000Z": "Open",
            },
        )
        avail = make_campground_availability(campsites={"1": site_fcfs})
        query = SearchQuery(
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 30),
            include_fcfs=False,
        )

        result = _process_availability(cg, avail, query)

        assert result.fcfs_sites == 1
        assert result.total_available_sites == 0

    def test_fcfs_inclusion_creates_window_spanning_date_range(self) -> None:
        """FCFS site included creates single window spanning date range."""
        cg = make_campground()
        site_fcfs = make_campsite_availability(
            campsite_id="1",
            dates_status={
                "2026-06-01T00:00:00.000Z": "Open",
                "2026-06-15T00:00:00.000Z": "Open",
            },
        )
        avail = make_campground_availability(campsites={"1": site_fcfs})
        query = SearchQuery(
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 30),
            include_fcfs=True,
        )

        result = _process_availability(cg, avail, query)

        assert result.total_available_sites == 1
        assert len(result.available_windows) == 1
        assert result.available_windows[0].is_fcfs is True
        assert result.available_windows[0].start_date == "2026-06-01"
        assert result.available_windows[0].end_date == "2026-06-30"
        assert result.available_windows[0].nights == 0  # unknown for FCFS

    def test_all_reserved_total_available_sites_zero(self) -> None:
        """All reserved sites yields total_available_sites=0."""
        cg = make_campground()
        site1 = make_campsite_availability(
            campsite_id="1",
            dates_status={"2026-06-01T00:00:00.000Z": "Reserved"},
        )
        site2 = make_campsite_availability(
            campsite_id="2",
            dates_status={"2026-06-01T00:00:00.000Z": "Reserved"},
        )
        avail = make_campground_availability(campsites={"1": site1, "2": site2})
        query = SearchQuery(
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 30),
        )

        result = _process_availability(cg, avail, query)

        assert result.total_available_sites == 0
        assert len(result.available_windows) == 0

    def test_empty_campground_zero_sites(self) -> None:
        """Campground with 0 sites."""
        cg = make_campground()
        avail = make_campground_availability(campsites={})
        query = SearchQuery(
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 30),
        )

        result = _process_availability(cg, avail, query)

        assert result.total_sites == 0
        assert result.total_available_sites == 0

    def test_mixed_group_standard_fcfs_sites(self) -> None:
        """Mixture of group, standard, and FCFS sites handled correctly."""
        cg = make_campground()
        site_standard = make_campsite_availability(
            campsite_id="1",
            campsite_type="STANDARD",
            dates_status={"2026-06-01T00:00:00.000Z": "Available"},
        )
        site_group = make_campsite_availability(
            campsite_id="2",
            campsite_type="GROUP",
            dates_status={"2026-06-01T00:00:00.000Z": "Available"},
        )
        site_fcfs = make_campsite_availability(
            campsite_id="3",
            dates_status={"2026-06-01T00:00:00.000Z": "Open"},
        )
        avail = make_campground_availability(
            campsites={"1": site_standard, "2": site_group, "3": site_fcfs}
        )
        query = SearchQuery(
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 30),
            include_group_sites=False,
            include_fcfs=True,
        )

        result = _process_availability(cg, avail, query)

        assert result.total_sites == 3
        assert result.fcfs_sites == 1
        assert result.total_available_sites == 2  # standard + fcfs
        assert len(result.available_windows) == 2

    def test_days_of_week_filter_passes_through(self) -> None:
        """Day-of-week filter applied to window finding."""
        cg = make_campground()
        # June 5=Fri, 6=Sat, 7=Sun, 8=Mon
        site = make_campsite_availability(
            campsite_id="1",
            dates_status={
                "2026-06-05T00:00:00.000Z": "Available",  # Fri
                "2026-06-06T00:00:00.000Z": "Available",  # Sat
                "2026-06-07T00:00:00.000Z": "Available",  # Sun
                "2026-06-08T00:00:00.000Z": "Available",  # Mon
            },
        )
        avail = make_campground_availability(campsites={"1": site})
        query = SearchQuery(
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 30),
            min_consecutive_nights=2,
            days_of_week={4, 5, 6},  # Fri-Sun
        )

        result = _process_availability(cg, avail, query)

        assert len(result.available_windows) == 1
        assert result.available_windows[0].start_date == "2026-06-05"
        assert result.available_windows[0].end_date == "2026-06-07"

    def test_capacity_filter_excludes_undersized_sites(self) -> None:
        """max_people filter excludes sites below capacity."""
        cg = make_campground()
        site_small = make_campsite_availability(
            campsite_id="1",
            max_people=4,
            dates_status={"2026-06-01T00:00:00.000Z": "Available"},
        )
        site_large = make_campsite_availability(
            campsite_id="2",
            max_people=6,
            dates_status={"2026-06-01T00:00:00.000Z": "Available"},
        )
        avail = make_campground_availability(campsites={"1": site_small, "2": site_large})
        query = SearchQuery(
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 30),
            max_people=5,
        )

        result = _process_availability(cg, avail, query)

        assert result.total_available_sites == 1
        assert result.available_windows[0].campsite_id == "2"

    def test_total_available_sites_counts_unique_sites(self) -> None:
        """total_available_sites counts unique sites with windows."""
        cg = make_campground()
        site1 = make_campsite_availability(
            campsite_id="1",
            dates_status={
                "2026-06-01T00:00:00.000Z": "Available",
                "2026-06-02T00:00:00.000Z": "Available",
            },
        )
        avail = make_campground_availability(campsites={"1": site1})
        query = SearchQuery(
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 30),
            min_consecutive_nights=1,
        )

        result = _process_availability(cg, avail, query)

        # Single site with 2-night window = 1 unique site
        assert result.total_available_sites == 1
        # But 1 window (not 2)
        assert len(result.available_windows) == 1


class TestDateHelpers:
    """Test date utility functions."""

    def test_days_function_thu_fri(self) -> None:
        """days('thu', 'fri') returns {3, 4}."""
        result = days("thu", "fri")
        assert result == {3, 4}

    def test_days_function_all_weekdays(self) -> None:
        """days with all weekday names."""
        result = days("mon", "tue", "wed", "thu", "fri")
        assert result == {0, 1, 2, 3, 4}

    def test_days_function_case_insensitive(self) -> None:
        """days() handles mixed case."""
        result = days("THU", "Fri", "sUn")
        assert result == {3, 4, 6}

    def test_weekend_constant(self) -> None:
        """WEEKEND constant is {4, 5, 6} (Fri, Sat, Sun)."""
        assert {4, 5, 6} == WEEKEND

    def test_long_weekend_constant(self) -> None:
        """LONG_WEEKEND constant is {3, 4, 5, 6} (Thu-Sun)."""
        assert {3, 4, 5, 6} == LONG_WEEKEND

    def test_weekdays_constant(self) -> None:
        """WEEKDAYS constant is {0, 1, 2, 3, 4} (Mon-Fri)."""
        assert {0, 1, 2, 3, 4} == WEEKDAYS

    def test_this_weekend_returns_valid_date_range(self) -> None:
        """this_weekend() returns (Friday, Sunday) tuple."""
        fri, sun = this_weekend()

        assert isinstance(fri, date)
        assert isinstance(sun, date)
        assert fri <= sun
        # Sunday should be 2 days after Friday
        assert (sun - fri).days == 2
        assert fri.weekday() == 4  # Friday
        assert sun.weekday() == 6  # Sunday

    def test_next_weekend_is_one_week_after_this_weekend(self) -> None:
        """next_weekend() returns dates 7 days after this_weekend()."""
        fri1, sun1 = this_weekend()
        fri2, sun2 = next_weekend()

        assert (fri2 - fri1).days == 7
        assert (sun2 - sun1).days == 7
        assert fri2.weekday() == 4  # Friday
        assert sun2.weekday() == 6  # Sunday


# ============================================================================
# Test data factories (imported from conftest, re-exported for clarity)
# ============================================================================


def make_campground(**overrides):
    """Factory for Campground test data."""
    from tests.conftest import make_campground as _make_campground

    return _make_campground(**overrides)


def make_campsite_availability(**overrides):
    """Factory for CampsiteAvailability test data."""
    from tests.conftest import make_campsite_availability as _make

    return _make(**overrides)


def make_campground_availability(**overrides):
    """Factory for CampgroundAvailability test data."""
    from tests.conftest import make_campground_availability as _make

    return _make(**overrides)
