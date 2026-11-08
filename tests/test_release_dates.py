"""When a not-yet-released (NYR) night opens for booking, per booking system."""

from __future__ import annotations

from datetime import date

from pnw_campsites.registry.models import BookingSystem
from pnw_campsites.search.release import (
    recgov_release_date,
    release_date,
    wa_release_date,
)


class TestRecgovReleaseDate:
    """Recreation.gov: rolling 6-month window, same day-of-month, 7 am PT."""

    def test_same_day_six_months_earlier(self) -> None:
        assert recgov_release_date(date(2027, 6, 4)) == date(2026, 12, 4)

    def test_month_end_clamps_to_last_day_of_shorter_month(self) -> None:
        """Aug 29–31 have no matching day in February.

        Recreation.gov doesn't document this case. Clamping to Feb 28 is the
        earlier of the two plausible dates (the other is Mar 1), so a user
        told to show up then is never late for a high-demand release.
        """
        assert recgov_release_date(date(2027, 8, 31)) == date(2027, 2, 28)
        assert recgov_release_date(date(2027, 8, 29)) == date(2027, 2, 28)
        assert recgov_release_date(date(2027, 8, 28)) == date(2027, 2, 28)

    def test_month_end_in_a_leap_year_clamps_to_feb_29(self) -> None:
        assert recgov_release_date(date(2028, 8, 31)) == date(2028, 2, 29)
        assert recgov_release_date(date(2028, 8, 30)) == date(2028, 2, 29)

    def test_month_end_into_thirty_day_months(self) -> None:
        # Dec 31 → Jun 30, Mar 31 → Sep 30 (previous year)
        assert recgov_release_date(date(2027, 12, 31)) == date(2027, 6, 30)
        assert recgov_release_date(date(2027, 3, 31)) == date(2026, 9, 30)

    def test_crosses_the_year_boundary(self) -> None:
        assert recgov_release_date(date(2027, 1, 15)) == date(2026, 7, 15)
        assert recgov_release_date(date(2027, 6, 30)) == date(2026, 12, 30)
        assert recgov_release_date(date(2027, 7, 1)) == date(2027, 1, 1)


class TestWaReleaseDate:
    """WA State Parks: arrivals open 9 months ahead, same day-of-month."""

    def test_same_day_nine_months_earlier(self) -> None:
        # Probed 2026-11-06/07: Aug 6 2027 arrivals were bookable on Nov 6.
        assert wa_release_date(date(2027, 8, 6)) == date(2026, 11, 6)

    def test_crosses_the_year_boundary(self) -> None:
        assert wa_release_date(date(2027, 9, 30)) == date(2026, 12, 30)
        assert wa_release_date(date(2027, 10, 1)) == date(2027, 1, 1)

    def test_month_end_clamps_to_last_day_of_shorter_month(self) -> None:
        # Nov 29–30 have no matching day in February, Aug 31 none in November.
        assert wa_release_date(date(2027, 11, 30)) == date(2027, 2, 28)
        assert wa_release_date(date(2027, 11, 29)) == date(2027, 2, 28)
        assert wa_release_date(date(2027, 11, 28)) == date(2027, 2, 28)
        assert wa_release_date(date(2027, 8, 31)) == date(2026, 11, 30)

    def test_month_end_in_a_leap_year_clamps_to_feb_29(self) -> None:
        assert wa_release_date(date(2028, 11, 30)) == date(2028, 2, 29)


class TestReleaseDate:
    """Dispatch by booking system, refusing dates the data contradicts."""

    TODAY = date(2026, 11, 6)

    def test_dispatches_per_booking_system(self) -> None:
        night = date(2027, 8, 20)
        assert release_date(BookingSystem.RECGOV, night, self.TODAY) == date(2027, 2, 20)
        assert release_date(BookingSystem.WA_STATE, night, self.TODAY) == date(2026, 11, 20)

    def test_systems_without_a_rule_return_none(self) -> None:
        # ReserveAmerica has no NYR status.
        night = date(2027, 9, 4)
        assert release_date(BookingSystem.OR_STATE, night, self.TODAY) is None
        assert release_date(BookingSystem.FCFS, night, self.TODAY) is None

    def test_rule_date_in_the_past_means_the_rule_does_not_apply(self) -> None:
        """A night that is still NYR after its rule date was released must use
        a different window (some rec.gov campgrounds release 2 weeks or 12
        months out, or in whole-month blocks). Say nothing rather than give a
        date that has already gone by.
        """
        # The rule says Jun 1 2026 — long past, yet the night is NYR.
        assert release_date(BookingSystem.RECGOV, date(2026, 12, 1), self.TODAY) is None
        assert release_date(BookingSystem.RECGOV, date(2027, 5, 5), self.TODAY) is None
        # A Deception Pass loop is NYR all of Aug 2027, inside WA's window.
        assert release_date(BookingSystem.WA_STATE, date(2027, 8, 1), self.TODAY) is None

    def test_release_today_is_still_reported(self) -> None:
        # Releases at 7 am PT today; the search may run before then.
        assert release_date(BookingSystem.RECGOV, date(2027, 5, 6), self.TODAY) == self.TODAY
