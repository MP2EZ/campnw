"""Exact dates are arrival → checkout; the checkout is not a night.

Every client that searches with `mode=exact` (the v2 search bar, and v1
before it) sends `end_date` as the checkout day, with `nights` = checkout −
arrival. The engine treated `end_date` as the last night, so an exact
Fri → Sun search also took Sunday night: a site open Sat and Sun nights
matched a Fri → Sun search, and a site open all three came back as a 3-night
window. Flexible ranges (`mode=find`, the CLI, watches) keep `end_date` as
the last night.
"""

from __future__ import annotations

from datetime import date

from pnw_campsites.search.engine import SearchQuery, _process_availability, _requested_nights
from tests.conftest import make_campground, make_campground_availability, make_campsite_availability

FRI, SAT, SUN = "2027-06-04", "2027-06-05", "2027-06-06"


def _site(campsite_id: str, *nights: str):
    return make_campsite_availability(
        campsite_id=campsite_id,
        dates_status={f"{n}T00:00:00.000Z": "Available" for n in nights},
    )


def _windows(query: SearchQuery, *sites):
    avail = make_campground_availability(campsites={s.campsite_id: s for s in sites})
    result = _process_availability(make_campground(), avail, query)
    return sorted((w.campsite_id, w.start_date, w.end_date) for w in result.available_windows)


def _exact() -> SearchQuery:
    return SearchQuery(
        start_date=date(2027, 6, 4), end_date=date(2027, 6, 6),
        min_consecutive_nights=2, end_is_checkout=True,
    )


class TestExactDates:
    def test_last_night_is_the_day_before_checkout(self):
        assert _exact().last_night == date(2027, 6, 5)

    def test_a_site_open_through_sunday_books_only_fri_and_sat(self):
        assert _windows(_exact(), _site("A", FRI, SAT, SUN)) == [("A", FRI, SAT)]

    def test_a_sat_and_sun_site_does_not_match_fri_to_sun(self):
        assert _windows(_exact(), _site("B", SAT, SUN)) == []

    def test_requested_nights_stop_before_checkout(self):
        assert _requested_nights(_exact()) == [date(2027, 6, 4), date(2027, 6, 5)]

    def test_a_one_night_stay_whose_checkout_equals_arrival_still_has_its_night(self):
        q = SearchQuery(start_date=date(2027, 6, 4), end_date=date(2027, 6, 4), end_is_checkout=True)
        assert q.last_night == date(2027, 6, 4)


class TestRangesKeepTheirLastNight:
    def test_a_flexible_range_still_counts_its_end_date_as_a_night(self):
        q = SearchQuery(start_date=date(2027, 6, 4), end_date=date(2027, 6, 6), min_consecutive_nights=2)
        assert q.last_night == date(2027, 6, 6)
        assert _windows(q, _site("B", SAT, SUN)) == [("B", SAT, SUN)]


class TestRoutesPassTheContract:
    def _capture(self, monkeypatch):
        from pnw_campsites.routes import search as search_routes

        seen: list[SearchQuery] = []

        async def fake_stream(query):
            seen.append(query)
            return
            yield

        class FakeEngine:
            search_stream = staticmethod(fake_stream)

        monkeypatch.setattr(search_routes, "get_engine", lambda: FakeEngine())
        return seen

    def test_stream_with_mode_exact_ends_on_the_night_before_checkout(self, api_client, monkeypatch):
        seen = self._capture(monkeypatch)
        api_client.get("/api/search/stream", params={
            "start_date": FRI, "end_date": SUN, "nights": 2, "mode": "exact",
        })
        assert seen[0].last_night == date(2027, 6, 5)

    def test_stream_without_mode_keeps_the_range(self, api_client, monkeypatch):
        seen = self._capture(monkeypatch)
        api_client.get("/api/search/stream", params={"start_date": FRI, "end_date": SUN, "nights": 2})
        assert seen[0].last_night == date(2027, 6, 6)
