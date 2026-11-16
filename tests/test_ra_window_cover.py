"""ReserveAmerica returns 14 nights per request (checked live 2026-11-15:
asking for 28 still gives a 14-entry grid), and Oregon requests share an
app-wide 1 req/s limit. A month of weekends was fetched as three windows
from the 1st, so the last window paid a full set of pages for two or three
weekday nights nobody asked about. Covering only the requested nights,
each window starting at the first night not yet covered, needs two.
"""

from __future__ import annotations

import asyncio
from datetime import date
from unittest.mock import AsyncMock, MagicMock

from pnw_campsites.providers.reserveamerica import ReserveAmericaClient, window_cover
from pnw_campsites.registry.models import BookingSystem, Campground, CampgroundAvailability
from pnw_campsites.search.engine import SearchEngine, SearchQuery, _requested_nights
from tests.test_provider_reserveamerica import _make_record, _make_redux_html

FRI_SAT_SUN = {4, 5, 6}


def _nights(start: date, end: date, days: set[int] | None = None) -> list[date]:
    return _requested_nights(SearchQuery(start_date=start, end_date=end, days_of_week=days))


class TestWindowCover:
    def test_no_nights_no_windows(self) -> None:
        assert window_cover([], date(2027, 3, 31)) == []

    def test_a_short_stay_is_one_window(self) -> None:
        nights = [date(2027, 7, 2), date(2027, 7, 3)]
        assert window_cover(nights, date(2027, 7, 4)) == [
            (date(2027, 7, 2), date(2027, 7, 4)),
        ]

    def test_march_weekends_need_two_windows_not_three(self) -> None:
        nights = _nights(date(2027, 3, 1), date(2027, 3, 31), FRI_SAT_SUN)
        assert window_cover(nights, date(2027, 3, 31)) == [
            (date(2027, 3, 5), date(2027, 3, 18)),
            (date(2027, 3, 19), date(2027, 3, 31)),
        ]

    def test_february_weekends_stay_at_two(self) -> None:
        nights = _nights(date(2027, 2, 1), date(2027, 2, 28), FRI_SAT_SUN)
        assert window_cover(nights, date(2027, 2, 28)) == [
            (date(2027, 2, 5), date(2027, 2, 18)),
            (date(2027, 2, 19), date(2027, 2, 28)),
        ]

    def test_every_night_of_a_month_still_needs_three(self) -> None:
        nights = _nights(date(2027, 3, 1), date(2027, 3, 31))
        assert window_cover(nights, date(2027, 3, 31)) == [
            (date(2027, 3, 1), date(2027, 3, 14)),
            (date(2027, 3, 15), date(2027, 3, 28)),
            (date(2027, 3, 29), date(2027, 3, 31)),
        ]

    def test_every_requested_night_is_covered(self) -> None:
        for days in ({4}, {5}, {4, 5}, FRI_SAT_SUN, {0, 3}, None):
            nights = _nights(date(2027, 1, 1), date(2027, 4, 30), days)
            cover = window_cover(nights, date(2027, 4, 30))
            for n in nights:
                assert any(s <= n <= e for s, e in cover), (days, n)
            for s, e in cover:
                assert (e - s).days <= 13

    def test_far_apart_nights_get_separate_windows(self) -> None:
        nights = [date(2027, 7, 1), date(2027, 8, 1)]
        assert window_cover(nights, date(2027, 8, 1)) == [
            (date(2027, 7, 1), date(2027, 7, 14)),
            (date(2027, 8, 1), date(2027, 8, 1)),
        ]

    def test_unsorted_and_duplicate_nights(self) -> None:
        nights = [date(2027, 7, 3), date(2027, 7, 2), date(2027, 7, 3)]
        assert window_cover(nights, date(2027, 7, 3)) == [
            (date(2027, 7, 2), date(2027, 7, 3)),
        ]


class TestProviderUsesTheCover:
    async def test_march_weekends_make_two_requests(self) -> None:
        client = ReserveAmericaClient()
        client._limiter.interval = 0
        client._session = MagicMock()
        client._session.get.return_value = MagicMock(
            status_code=200, text=_make_redux_html([_make_record()], 1),
        )
        nights = _nights(date(2027, 3, 1), date(2027, 3, 31), FRI_SAT_SUN)

        await client.get_availability(
            "402178", "park", "OR", date(2027, 3, 1), date(2027, 3, 31), nights=nights,
        )

        sent = [c.kwargs["params"] for c in client._session.get.call_args_list]
        assert [(p["arrivalDate"], p["departureDate"]) for p in sent] == [
            ("2027-03-05", "2027-03-18"), ("2027-03-19", "2027-03-31"),
        ]

    async def test_without_nights_the_whole_range_is_fetched(self) -> None:
        client = ReserveAmericaClient()
        client._limiter.interval = 0
        client._session = MagicMock()
        client._session.get.return_value = MagicMock(
            status_code=200, text=_make_redux_html([_make_record()], 1),
        )

        await client.get_availability("402178", "park", "OR", date(2027, 3, 1), date(2027, 3, 31))

        assert client._session.get.call_count == 3


def _oregon_engine(watch_db):
    ra = AsyncMock()
    ra.get_availability = AsyncMock(
        return_value=CampgroundAvailability(facility_id="402178", campsites={}),
    )
    eng = SearchEngine(registry=None, reserveamerica_client=ra, watch_db=watch_db)
    cg = Campground(
        facility_id="402178", name="Fort Stevens", booking_system=BookingSystem.OR_STATE,
        state="OR", booking_url_slug="fort-stevens-state-park",
    )
    return eng, ra, cg


class TestEngineFetchesOnlyRequestedNights:
    def test_oregon_fetch_gets_the_requested_nights(self, watch_db) -> None:
        eng, ra, cg = _oregon_engine(watch_db)
        query = SearchQuery(
            start_date=date(2027, 3, 1), end_date=date(2027, 3, 31), days_of_week=FRI_SAT_SUN,
        )
        asyncio.run(eng._check_campground(cg, query.start_date, query.end_date, query))

        assert ra.get_availability.await_args.kwargs["nights"] == _requested_nights(query)

    def test_a_repeat_weekend_search_is_served_from_cache(self, watch_db) -> None:
        eng, ra, cg = _oregon_engine(watch_db)
        query = SearchQuery(
            start_date=date(2027, 3, 1), end_date=date(2027, 3, 31), days_of_week=FRI_SAT_SUN,
        )

        async def run():
            for _ in range(2):
                await eng._check_campground(cg, query.start_date, query.end_date, query)

        asyncio.run(run())
        assert ra.get_availability.await_count == 1

    def test_a_weekend_fetch_never_answers_an_every_night_search(self, watch_db) -> None:
        """The weekend fetch starts Mar 5, so it says nothing about Mar 1-4."""
        eng, ra, cg = _oregon_engine(watch_db)
        weekends = SearchQuery(
            start_date=date(2027, 3, 1), end_date=date(2027, 3, 31), days_of_week=FRI_SAT_SUN,
        )
        every_night = SearchQuery(start_date=date(2027, 3, 1), end_date=date(2027, 3, 31))

        async def run():
            await eng._check_campground(cg, weekends.start_date, weekends.end_date, weekends)
            await eng._check_campground(
                cg, every_night.start_date, every_night.end_date, every_night,
            )

        asyncio.run(run())
        assert ra.get_availability.await_count == 2

    def test_cached_extent_is_what_was_fetched(self, watch_db) -> None:
        eng, _, cg = _oregon_engine(watch_db)
        query = SearchQuery(
            start_date=date(2027, 3, 1), end_date=date(2027, 3, 31), days_of_week=FRI_SAT_SUN,
        )
        asyncio.run(eng._check_campground(cg, query.start_date, query.end_date, query))

        get = watch_db.get_cached_availability
        assert get("402178", "or_state", range_start=date(2027, 3, 5), range_end=date(2027, 3, 31))
        assert not get(
            "402178", "or_state", range_start=date(2027, 3, 4), range_end=date(2027, 3, 31),
        )
