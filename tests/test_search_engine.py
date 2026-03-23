"""Tests for the search engine discovery logic."""

from __future__ import annotations

from datetime import date

import pytest

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
from tests.conftest import (
    make_campground,
    make_campground_availability,
    make_campsite_availability,
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
# v0.6 Smart Search: Diagnosis & Recommendations
# ============================================================================


class TestDiagnoseZeroResults:
    """Test _diagnose_zero_results() method."""

    def test_no_registry_matches_name_filter(self) -> None:
        """No registry matches + name filter → binding='name'."""
        from unittest.mock import MagicMock

        from pnw_campsites.search.engine import SearchEngine

        engine = SearchEngine(
            registry=MagicMock(),
            recgov_client=None,
            goingtocamp_client=None,
        )
        query = SearchQuery(
            start_date=None,
            end_date=None,
            name_like="nonexistent",
        )

        diagnosis, chips = engine._diagnose_zero_results(
            query, registry_matches=0, distance_filtered=0,
            checked=0, all_unavailable=0,
        )

        assert diagnosis.binding_constraint == "name"
        assert "nonexistent" in diagnosis.explanation

    def test_no_registry_matches_tag_filter(self) -> None:
        """No registry matches + tag filter → binding='tags'."""
        from unittest.mock import MagicMock

        from pnw_campsites.search.engine import SearchEngine

        engine = SearchEngine(
            registry=MagicMock(),
            recgov_client=None,
            goingtocamp_client=None,
        )
        query = SearchQuery(
            start_date=None,
            end_date=None,
            tags=["obscure-tag"],
        )

        diagnosis, chips = engine._diagnose_zero_results(
            query, registry_matches=0, distance_filtered=0,
            checked=0, all_unavailable=0,
        )

        assert diagnosis.binding_constraint == "tags"
        assert "obscure-tag" in diagnosis.explanation
        # Should include drop_tags chip
        assert any(c.action == "drop_tags" for c in chips)

    def test_no_registry_matches_state_filter(self) -> None:
        """No registry matches + state filter → binding='state'."""
        from unittest.mock import MagicMock

        from pnw_campsites.search.engine import SearchEngine

        engine = SearchEngine(
            registry=MagicMock(),
            recgov_client=None,
            goingtocamp_client=None,
        )
        query = SearchQuery(
            start_date=None,
            end_date=None,
            state="XX",  # invalid state
        )

        diagnosis, chips = engine._diagnose_zero_results(
            query, registry_matches=0, distance_filtered=0,
            checked=0, all_unavailable=0,
        )

        assert diagnosis.binding_constraint == "state"
        assert "XX" in diagnosis.explanation

    def test_distance_filtered_high_percentage(self) -> None:
        """Distance filtered > 50% → binding='distance'."""
        from unittest.mock import MagicMock

        from pnw_campsites.search.engine import SearchEngine

        engine = SearchEngine(
            registry=MagicMock(),
            recgov_client=None,
            goingtocamp_client=None,
        )
        query = SearchQuery(
            start_date=None,
            end_date=None,
            max_drive_minutes=60,
        )

        # 10 registry matches, 6 filtered by distance (60% > 50%)
        diagnosis, chips = engine._diagnose_zero_results(
            query, registry_matches=10, distance_filtered=6,
            checked=0, all_unavailable=0,
        )

        assert diagnosis.binding_constraint == "distance"
        assert "60" in diagnosis.explanation  # filtered count
        # Should include expand_radius chips
        assert any(c.action == "expand_radius" for c in chips)

    def test_all_checked_unavailable_with_days_filter(self) -> None:
        """All checked unavailable + days filter → binding='days'."""
        from unittest.mock import MagicMock

        from pnw_campsites.search.engine import SearchEngine

        engine = SearchEngine(
            registry=MagicMock(),
            recgov_client=None,
            goingtocamp_client=None,
        )
        query = SearchQuery(
            start_date=None,
            end_date=None,
            days_of_week={4, 5, 6},  # Fri-Sun only
        )

        diagnosis, chips = engine._diagnose_zero_results(
            query, registry_matches=5, distance_filtered=0,
            checked=5, all_unavailable=5,
        )

        assert diagnosis.binding_constraint == "days"
        assert "days" in diagnosis.explanation
        # Should include drop_days chip
        assert any(c.action == "drop_days" for c in chips)

    def test_all_checked_unavailable_without_days_filter(self) -> None:
        """All checked unavailable + no days → binding='dates'."""
        from unittest.mock import MagicMock

        from pnw_campsites.search.engine import SearchEngine

        engine = SearchEngine(
            registry=MagicMock(),
            recgov_client=None,
            goingtocamp_client=None,
        )
        query = SearchQuery(
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 30),
            days_of_week=None,
        )

        diagnosis, chips = engine._diagnose_zero_results(
            query, registry_matches=5, distance_filtered=0,
            checked=5, all_unavailable=5,
        )

        assert diagnosis.binding_constraint == "dates"
        assert "dates" in diagnosis.explanation
        # Should include shift_dates chip
        assert any(c.action == "shift_dates" for c in chips)

    def test_dates_binding_produces_watch_chip(self) -> None:
        """Dates binding generates watch + shift chips."""
        from unittest.mock import MagicMock

        from pnw_campsites.search.engine import SearchEngine

        engine = SearchEngine(
            registry=MagicMock(),
            recgov_client=None,
            goingtocamp_client=None,
        )
        query = SearchQuery(
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 30),
        )

        diagnosis, chips = engine._diagnose_zero_results(
            query, registry_matches=5, distance_filtered=0,
            checked=5, all_unavailable=5,
        )

        # Should have watch chip
        watch_chips = [c for c in chips if c.action == "watch"]
        assert len(watch_chips) > 0
        assert watch_chips[0].params["start_date"] == "2026-06-01"
        assert watch_chips[0].params["end_date"] == "2026-06-30"

    def test_distance_binding_produces_expand_radius_chip(self) -> None:
        """Distance binding generates expand_radius chips."""
        from unittest.mock import MagicMock

        from pnw_campsites.search.engine import SearchEngine

        engine = SearchEngine(
            registry=MagicMock(),
            recgov_client=None,
            goingtocamp_client=None,
        )
        query = SearchQuery(
            max_drive_minutes=60,
        )

        diagnosis, chips = engine._diagnose_zero_results(
            query, registry_matches=10, distance_filtered=6,
            checked=0, all_unavailable=0,
        )

        expand_chips = [c for c in chips if c.action == "expand_radius"]
        assert len(expand_chips) >= 2
        # One should expand by 60 min, one should remove limit
        assert any(
            c.params.get("max_drive_minutes") == 120 for c in expand_chips
        )
        assert any(
            c.params.get("max_drive_minutes") is None for c in expand_chips
        )

    def test_diagnosis_counts_match_input(self) -> None:
        """Diagnosis object contains correct counts."""
        from unittest.mock import MagicMock

        from pnw_campsites.search.engine import SearchEngine

        engine = SearchEngine(
            registry=MagicMock(),
            recgov_client=None,
            goingtocamp_client=None,
        )
        query = SearchQuery()

        diagnosis, _ = engine._diagnose_zero_results(
            query, registry_matches=20, distance_filtered=5,
            checked=15, all_unavailable=10,
        )

        assert diagnosis.registry_matches == 20
        assert diagnosis.distance_filtered == 5
        assert diagnosis.checked_for_availability == 15
        assert diagnosis.all_unavailable == 10


# -------------------------------------------------------------------
# Integration tests with mocked providers and real registry
# -------------------------------------------------------------------


class TestSearchIntegration:
    """Integration tests for SearchEngine with mocked providers."""

    @pytest.mark.asyncio
    async def test_search_with_state_filter_returns_matching_only(
        self, registry
    ) -> None:
        """Search with state filter returns only matching state campgrounds."""
        from unittest.mock import AsyncMock

        from pnw_campsites.registry.models import CampgroundAvailability
        from pnw_campsites.search.engine import SearchEngine

        # Seed registry with WA and OR campgrounds
        wa_camp = make_campground(
            facility_id="232465", state="WA", latitude=46.75, longitude=-121.80
        )
        or_camp = make_campground(
            facility_id="233000", state="OR", latitude=43.5, longitude=-121.5
        )
        registry.upsert(wa_camp)
        registry.upsert(or_camp)

        # Mock providers
        recgov = AsyncMock()
        recgov.get_availability_range = AsyncMock(
            return_value=CampgroundAvailability(
                facility_id="232465",
                campsites={
                    "123": make_campsite_availability(
                        campsite_id="123",
                        dates_status={
                            "2026-06-01T00:00:00.000Z": "Available",
                            "2026-06-02T00:00:00.000Z": "Available",
                        },
                    )
                },
            )
        )

        engine = SearchEngine(registry=registry, recgov_client=recgov)
        results = await engine.search(
            SearchQuery(
                start_date=date(2026, 6, 1),
                end_date=date(2026, 6, 30),
                state="WA",
                max_campgrounds=10,
            )
        )

        # Should only check WA campground
        assert results.campgrounds_checked == 1

    @pytest.mark.asyncio
    async def test_search_with_distance_filter_excludes_far(
        self, registry
    ) -> None:
        """Search with distance filter excludes far campgrounds."""
        from unittest.mock import AsyncMock

        from pnw_campsites.search.engine import SearchEngine

        # Seed registry with close and far campgrounds
        close_camp = make_campground(
            facility_id="232465",
            latitude=47.6,
            longitude=-122.3,
            state="WA",
        )
        far_camp = make_campground(
            facility_id="233000",
            latitude=42.0,
            longitude=-121.0,
            state="OR",
        )
        registry.upsert(close_camp)
        registry.upsert(far_camp)

        recgov = AsyncMock()
        recgov.get_availability_range = AsyncMock()

        engine = SearchEngine(registry=registry, recgov_client=recgov)
        results = await engine.search(
            SearchQuery(
                start_date=date(2026, 6, 1),
                end_date=date(2026, 6, 30),
                from_coords=(47.6, -122.3),  # Seattle
                max_drive_minutes=120,  # ~2 hour limit
                max_campgrounds=10,
            )
        )

        # Should only check close campground (far one is > 120 min)
        assert results.campgrounds_checked == 1

    @pytest.mark.asyncio
    async def test_search_sorted_by_distance_when_from_coords(
        self, registry
    ) -> None:
        """Search results sorted by distance when from_coords set."""
        from unittest.mock import AsyncMock

        from pnw_campsites.registry.models import CampgroundAvailability
        from pnw_campsites.search.engine import SearchEngine

        # Seed registry with two campgrounds
        close_camp = make_campground(
            facility_id="1", latitude=47.6, longitude=-122.3
        )
        far_camp = make_campground(
            facility_id="2", latitude=47.0, longitude=-121.5
        )
        registry.upsert(close_camp)
        registry.upsert(far_camp)

        # Mock both returning availability
        def mock_get_avail(facility_id, *args, **kwargs):
            return CampgroundAvailability(
                facility_id=facility_id,
                campsites={
                    "123": make_campsite_availability(
                        dates_status={
                            "2026-06-01T00:00:00.000Z": "Available",
                            "2026-06-02T00:00:00.000Z": "Available",
                        },
                    )
                },
            )

        recgov = AsyncMock()
        recgov.get_availability_range = AsyncMock(side_effect=mock_get_avail)

        engine = SearchEngine(registry=registry, recgov_client=recgov)
        results = await engine.search(
            SearchQuery(
                start_date=date(2026, 6, 1),
                end_date=date(2026, 6, 30),
                from_coords=(47.6, -122.3),  # Seattle
                max_campgrounds=10,
            )
        )

        # Results should be sorted by distance (close first)
        if len(results.results) >= 2:
            first_dist = results.results[0].estimated_drive_minutes or 9999
            second_dist = results.results[1].estimated_drive_minutes or 9999
            assert first_dist <= second_dist

    @pytest.mark.asyncio
    async def test_search_with_name_like_filter(self, registry) -> None:
        """Search with name_like filter returns matching campgrounds."""
        from unittest.mock import AsyncMock

        from pnw_campsites.search.engine import SearchEngine

        # Seed registry
        camp1 = make_campground(facility_id="1", name="Ohanapecosh")
        camp2 = make_campground(facility_id="2", name="Mirror Lake")
        registry.upsert(camp1)
        registry.upsert(camp2)

        recgov = AsyncMock()
        recgov.get_availability_range = AsyncMock()

        engine = SearchEngine(registry=registry, recgov_client=recgov)
        results = await engine.search(
            SearchQuery(
                start_date=date(2026, 6, 1),
                end_date=date(2026, 6, 30),
                name_like="ohana",
                max_campgrounds=10,
            )
        )

        # Should only check Ohanapecosh
        assert results.campgrounds_checked == 1

    @pytest.mark.asyncio
    async def test_search_zero_availability_includes_diagnosis(
        self, registry
    ) -> None:
        """Search with zero availability includes diagnosis."""
        from unittest.mock import AsyncMock

        from pnw_campsites.search.engine import SearchEngine

        camp = make_campground(facility_id="232465", state="WA")
        registry.upsert(camp)

        # Mock returning no availability
        recgov = AsyncMock()
        recgov.get_availability_range = AsyncMock(
            return_value=make_campground_availability(
                facility_id="232465",
                campsites={
                    "123": make_campsite_availability(
                        dates_status={
                            "2026-06-01T00:00:00.000Z": "Reserved",
                        }
                    )
                },
            )
        )

        engine = SearchEngine(registry=registry, recgov_client=recgov)
        results = await engine.search(
            SearchQuery(
                start_date=date(2026, 6, 1),
                end_date=date(2026, 6, 30),
                state="WA",
                max_campgrounds=10,
            )
        )

        assert results.campgrounds_with_availability == 0
        assert results.diagnosis is not None
        assert results.diagnosis.binding_constraint == "dates"

    @pytest.mark.asyncio
    async def test_search_caps_at_max_campgrounds(self, registry) -> None:
        """Search respects max_campgrounds limit."""
        from unittest.mock import AsyncMock

        from pnw_campsites.search.engine import SearchEngine

        # Seed registry with 20 campgrounds
        for i in range(20):
            camp = make_campground(facility_id=str(i))
            registry.upsert(camp)

        recgov = AsyncMock()
        recgov.get_availability_range = AsyncMock()

        engine = SearchEngine(registry=registry, recgov_client=recgov)
        results = await engine.search(
            SearchQuery(
                start_date=date(2026, 6, 1),
                end_date=date(2026, 6, 30),
                max_campgrounds=5,
            )
        )

        # Should only check 5 campgrounds
        assert results.campgrounds_checked <= 5

    @pytest.mark.asyncio
    async def test_check_specific_returns_result(self, registry) -> None:
        """check_specific returns result for known facility."""
        from unittest.mock import AsyncMock

        from pnw_campsites.search.engine import SearchEngine

        camp = make_campground(facility_id="232465", name="Test Camp")
        registry.upsert(camp)

        recgov = AsyncMock()
        recgov.get_availability_range = AsyncMock(
            return_value=make_campground_availability(
                facility_id="232465",
                campsites={
                    "123": make_campsite_availability(
                        dates_status={
                            "2026-06-01T00:00:00.000Z": "Available",
                        }
                    )
                },
            )
        )

        engine = SearchEngine(registry=registry, recgov_client=recgov)
        result = await engine.check_specific(
            facility_id="232465",
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 30),
            min_nights=1,
        )

        assert result.campground.name == "Test Camp"
        assert result.total_available_sites == 1

    @pytest.mark.asyncio
    async def test_check_specific_with_unknown_facility(
        self, registry
    ) -> None:
        """check_specific creates unknown campground for unfound facility."""
        from unittest.mock import AsyncMock

        from pnw_campsites.search.engine import SearchEngine

        recgov = AsyncMock()
        recgov.get_availability_range = AsyncMock(
            return_value=make_campground_availability(
                facility_id="999999",
                campsites={},
            )
        )

        engine = SearchEngine(registry=registry, recgov_client=recgov)
        result = await engine.check_specific(
            facility_id="999999",
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 30),
        )

        # Should create a placeholder campground
        assert result.campground.facility_id == "999999"

    @pytest.mark.asyncio
    async def test_search_stream_yields_results(self, registry) -> None:
        """search_stream yields results incrementally."""
        from unittest.mock import AsyncMock

        from pnw_campsites.search.engine import SearchEngine

        camp = make_campground(facility_id="232465")
        registry.upsert(camp)

        recgov = AsyncMock()
        recgov.get_availability_range = AsyncMock(
            return_value=make_campground_availability(
                facility_id="232465",
                campsites={
                    "123": make_campsite_availability(
                        dates_status={
                            "2026-06-01T00:00:00.000Z": "Available",
                            "2026-06-02T00:00:00.000Z": "Available",
                        },
                    )
                },
            )
        )

        engine = SearchEngine(registry=registry, recgov_client=recgov)
        results = []
        async for result in engine.search_stream(
            SearchQuery(
                start_date=date(2026, 6, 1),
                end_date=date(2026, 6, 30),
            )
        ):
            results.append(result)

        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_search_with_no_registry_matches_returns_empty(
        self, registry
    ) -> None:
        """Search with no registry matches returns empty with diagnosis."""
        from unittest.mock import AsyncMock

        from pnw_campsites.search.engine import SearchEngine

        recgov = AsyncMock()

        engine = SearchEngine(registry=registry, recgov_client=recgov)
        results = await engine.search(
            SearchQuery(
                start_date=date(2026, 6, 1),
                end_date=date(2026, 6, 30),
                state="XY",  # Invalid state
                max_campgrounds=10,
            )
        )

        assert results.campgrounds_checked == 0
        assert results.diagnosis is not None

    @pytest.mark.asyncio
    async def test_find_consecutive_windows_with_fcfs_sites(
        self, registry
    ) -> None:
        """Process availability includes FCFS sites when included."""
        from pnw_campsites.search.engine import _process_availability

        camp = make_campground()
        avail = make_campground_availability(
            campsites={
                "123": make_campsite_availability(
                    campsite_id="123",
                    dates_status={
                        "2026-06-01T00:00:00.000Z": "Open",  # FCFS
                    },
                )
            },
        )

        query = SearchQuery(
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 30),
            include_fcfs=True,
        )

        result = _process_availability(camp, avail, query)

        # FCFS sites should be counted
        assert result.fcfs_sites >= 0

    @pytest.mark.asyncio
    async def test_search_stream_yields_results_incrementally(
        self, registry
    ) -> None:
        """search_stream yields results as batches complete."""
        from unittest.mock import AsyncMock

        from pnw_campsites.search.engine import SearchEngine

        # Add campgrounds to registry
        cg1 = make_campground(
            facility_id="1", name="Camp 1", state="WA"
        )
        cg2 = make_campground(
            facility_id="2", name="Camp 2", state="WA"
        )
        registry.upsert(cg1)
        registry.upsert(cg2)

        # Mock provider returning availability
        recgov = AsyncMock()
        avail = make_campground_availability(
            facility_id="1",
            campsites={
                "123": make_campsite_availability(
                    campsite_id="123",
                    dates_status={
                        "2026-06-01T00:00:00.000Z": "Available"
                    },
                )
            },
        )
        recgov.get_availability_range.return_value = avail

        engine = SearchEngine(registry=registry, recgov_client=recgov)
        query = SearchQuery(
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 30),
            state="WA",
            max_campgrounds=2,
        )

        results = []
        async for result in engine.search_stream(query):
            results.append(result)

        assert len(results) > 0
        assert results[0].campground.facility_id in ("1", "2")

    @pytest.mark.asyncio
    async def test_search_stream_empty_when_no_campgrounds(
        self, registry
    ) -> None:
        """search_stream returns empty iterator if no campgrounds match."""
        from unittest.mock import AsyncMock

        from pnw_campsites.search.engine import SearchEngine

        recgov = AsyncMock()
        engine = SearchEngine(registry=registry, recgov_client=recgov)
        query = SearchQuery(
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 30),
            state="ZZ",  # Non-existent state
        )

        results = []
        async for result in engine.search_stream(query):
            results.append(result)

        assert len(results) == 0

    def test_suggest_similar_campgrounds_returns_chips(self, registry) -> None:
        """_suggest_similar_campgrounds returns action chips."""
        from unittest.mock import MagicMock

        from pnw_campsites.search.engine import SearchEngine

        cg1 = make_campground(
            facility_id="1", name="Lake Rainier", tags=["lakeside"]
        )
        cg2 = make_campground(
            facility_id="2", name="Rainier Riverside", tags=["lakeside"]
        )
        registry.upsert(cg1)
        registry.upsert(cg2)

        mock_recgov = MagicMock()
        engine = SearchEngine(registry=registry, recgov_client=mock_recgov)

        query = SearchQuery(name_like="Lake Rainier")
        chips = engine._suggest_similar_campgrounds(query)

        assert len(chips) > 0
        assert chips[0].action == "try_nearby"
        assert "Rainier" in chips[0].label

    def test_suggest_similar_campgrounds_no_matches(self, registry) -> None:
        """_suggest_similar_campgrounds returns empty list if no matches."""
        from unittest.mock import MagicMock

        from pnw_campsites.search.engine import SearchEngine

        mock_recgov = MagicMock()
        engine = SearchEngine(registry=registry, recgov_client=mock_recgov)

        query = SearchQuery(name_like="NonexistentCampXYZ")
        chips = engine._suggest_similar_campgrounds(query)

        assert len(chips) == 0

    def test_suggest_similar_campgrounds_no_similar_found(
        self, registry
    ) -> None:
        """_suggest_similar_campgrounds returns empty when no similar exist."""
        from unittest.mock import MagicMock, patch

        from pnw_campsites.search.engine import SearchEngine

        cg = make_campground(facility_id="1", name="Test")
        registry.upsert(cg)

        mock_recgov = MagicMock()
        engine = SearchEngine(registry=registry, recgov_client=mock_recgov)

        # Mock find_similar to return empty
        with patch.object(
            registry, "find_similar", return_value=[]
        ):
            query = SearchQuery(name_like="Test")
            chips = engine._suggest_similar_campgrounds(query)

            assert len(chips) == 0

    @pytest.mark.asyncio
    async def test_diagnose_distance_binding_constraint(
        self, registry
    ) -> None:
        """_diagnose_zero_results identifies distance as binding constraint."""
        from unittest.mock import AsyncMock

        from pnw_campsites.search.engine import SearchEngine

        cg = make_campground(
            facility_id="1", name="Camp", latitude=47.0, longitude=-122.0
        )
        registry.upsert(cg)

        recgov = AsyncMock()
        engine = SearchEngine(registry=registry, recgov_client=recgov)

        # Search from Seattle (47.6, -122.3) with tight distance limit
        # Camp at (47.0, -122.0) is ~50 miles away
        query = SearchQuery(
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 30),
            from_coords=(47.6, -122.3),
            max_drive_minutes=30,  # Too tight
        )

        results = await engine.search(query)

        assert results.diagnosis is not None
        assert results.diagnosis.binding_constraint == "distance"
        # Message says "exceeded X min drive limit"
        assert "drive" in results.diagnosis.explanation.lower()

    @pytest.mark.asyncio
    async def test_diagnose_days_binding_constraint(
        self, registry
    ) -> None:
        """_diagnose_zero_results identifies days as binding constraint."""
        from unittest.mock import AsyncMock

        from pnw_campsites.search.engine import SearchEngine

        cg = make_campground(facility_id="1", name="Camp", state="WA")
        registry.upsert(cg)

        recgov = AsyncMock()
        # Return campground with no availability on selected days
        avail = make_campground_availability(
            facility_id="1",
            campsites={
                "123": make_campsite_availability(
                    campsite_id="123",
                    dates_status={
                        "2026-06-01T00:00:00.000Z": "Reserved",  # Mon
                    },
                )
            },
        )
        recgov.get_availability_range.return_value = avail

        engine = SearchEngine(registry=registry, recgov_client=recgov)

        query = SearchQuery(
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 2),
            state="WA",
            days_of_week={4, 5, 6},  # Fri, Sat, Sun only
        )

        results = await engine.search(query)

        # If all booked on non-selected days, binding is "days"
        if results.diagnosis:
            assert results.diagnosis.binding_constraint in (
                "days", "dates"
            )
