"""Rec.gov "Open" past the arrival window is stay continuation, not FCFS.

Rec.gov marks the nights just past a campground's arrival window as Open:
nobody can arrive on them, they can only be booked as the tail of a stay
that arrives inside the window. Kirk Creek (233116), fetched 2026-11-07 for
May 2027: Reserved/Available to May 6-7, Open (with Reserved continuation
stays) to May 19, NYR from May 20. Kalaloch's cached May 2026 payload has
the same shape on every short-window site.
"""

from __future__ import annotations

from datetime import date, timedelta

from pnw_campsites.search.engine import SearchQuery, _process_availability
from tests.conftest import (
    make_campground,
    make_campground_availability,
    make_campsite_availability,
)

_CODES = {
    "A": "Available",
    "R": "Reserved",
    "O": "Open",
    "N": "NYR",
    "n": "Not Reservable",
    "x": "Not Available",
    "C": "Closed",
}


def _site(pattern: str, start: date = date(2027, 5, 1), campsite_id: str = "1"):
    """One site whose nights from ``start`` follow ``pattern`` (one letter a night)."""
    return make_campsite_availability(
        campsite_id=campsite_id,
        dates_status={
            f"{start + timedelta(days=i)}T00:00:00Z": _CODES[c]
            for i, c in enumerate(pattern)
        },
    )


# Real Kirk Creek rows, May 2027 as fetched 2026-11-07.
KIRK_030 = "RAARRRRROOOOOOOOOOONNNNNNNNNNNN"
KIRK_002 = "nnnnnnnnnnnnnnnnnnnnnnnnnnnnnnn"


class TestContinuationDates:
    def test_open_run_into_nyr_is_continuation(self) -> None:
        site = _site(KIRK_030)
        assert sorted(d[:10] for d in site.continuation_dates()) == [
            f"2027-05-{day:02d}" for day in range(9, 20)
        ]

    def test_reserved_continuation_stays_do_not_break_the_run(self) -> None:
        site = _site("ROROORN")
        assert sorted(d[:10] for d in site.continuation_dates()) == [
            "2027-05-02", "2027-05-04", "2027-05-05",
        ]

    def test_open_without_nyr_after_it_is_not_continuation(self) -> None:
        assert _site("OOOOOOO").continuation_dates() == set()
        assert _site("OOOxNNN").continuation_dates() == set()


class TestIsFcfs:
    def test_month_past_the_window_is_not_fcfs(self) -> None:
        """The month after the window holds only Open then NYR: not walk-up."""
        assert _site("OOOOOOOONNNNNNNNNNNNNNNNNNNNNN", date(2027, 6, 1)).is_fcfs is False

    def test_all_open_is_still_fcfs(self) -> None:
        assert _site("OOOOOOOOOOOOOOOOOOOOOOOOOOOOOO").is_fcfs is True

    def test_walk_up_open_not_followed_by_nyr_is_still_fcfs(self) -> None:
        """ReserveAmerica WALK_UP maps to Open and never runs into NYR."""
        assert _site("OOOOxxxOOO").is_fcfs is True

    def test_fcfs_open_before_an_unrelated_break_is_still_fcfs(self) -> None:
        assert _site("OOOCCOONNN").is_fcfs is True

    def test_not_reservable_is_still_fcfs(self) -> None:
        assert _site(KIRK_002).is_fcfs is True


class TestProcessAvailability:
    def test_continuation_sites_do_not_count_as_fcfs(self) -> None:
        june = date(2027, 6, 1)
        avail = make_campground_availability(campsites={
            "1": _site("OOOOOOOONNNNNNNNNNNNNNNNNNNNNN", june, "1"),
            "2": _site("ROOOOOOONNNNNNNNNNNNNNNNNNNNNN", june, "2"),
            "3": _site("OOOOOOOOOOOOOOOOOOOOOOOOOOOOOO", june, "3"),
        })
        query = SearchQuery(
            start_date=june, end_date=date(2027, 6, 7), include_fcfs=True,
        )

        result = _process_availability(make_campground(), avail, query)

        assert result.fcfs_sites == 1
        assert [w.campsite_id for w in result.available_windows] == ["3"]
