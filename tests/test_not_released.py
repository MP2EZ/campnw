"""Not-yet-released (NYR) nights must not read as "fully booked".

A June 2027 search run on 2026-11-06 returned nothing from Recreation.gov
because June wasn't released, and the engine treated NYR like any other
unavailable status — so users concluded everything was full.
"""

from __future__ import annotations

from datetime import date, timedelta

from pnw_campsites.providers.goingtocamp import GoingToCampClient
from pnw_campsites.registry.models import BookingSystem, CampgroundAvailability
from pnw_campsites.search.engine import SearchQuery, _process_availability
from tests.conftest import (
    make_campground,
    make_campground_availability,
    make_campsite_availability,
)


def _site(campsite_id: str, statuses: dict[str, str], **kw):
    return make_campsite_availability(
        campsite_id=campsite_id,
        dates_status={f"{d}T00:00:00.000Z": s for d, s in statuses.items()},
        **kw,
    )


def _avail(*sites):
    return make_campground_availability(
        campsites={s.campsite_id: s for s in sites},
    )


def _query(start: date, end: date, **kw) -> SearchQuery:
    return SearchQuery(start_date=start, end_date=end, **kw)


class TestProcessAvailabilityNotReleased:
    def test_counts_requested_nights_nothing_has_been_released_for(self) -> None:
        # Mirrors Kirk Creek in June 2027: every reservable site NYR, the two
        # FCFS sites "Not Reservable".
        avail = _avail(
            _site("1", {"2099-06-01": "NYR", "2099-06-02": "NYR", "2099-06-03": "NYR"}),
            _site("2", {"2099-06-01": "NYR", "2099-06-02": "NYR", "2099-06-03": "NYR"}),
            _site("3", {
                "2099-06-01": "Not Reservable",
                "2099-06-02": "Not Reservable",
                "2099-06-03": "Not Reservable",
            }),
        )
        r = _process_availability(
            make_campground(), avail, _query(date(2099, 6, 1), date(2099, 6, 2)),
        )
        assert r.not_released_nights == 2  # Jun 3 is outside the request
        assert r.releases_on == date(2098, 12, 1)
        assert r.releases_through == date(2098, 12, 2)
        assert r.total_available_sites == 0

    def test_night_with_any_released_site_is_not_counted(self) -> None:
        # Deception Pass, Aug 2027: one loop NYR all summer, the rest bookable.
        avail = _avail(
            _site("1", {"2099-06-01": "NYR", "2099-06-02": "NYR"}),
            _site("2", {"2099-06-01": "Reserved", "2099-06-02": "Available"}),
        )
        r = _process_availability(
            make_campground(), avail, _query(date(2099, 6, 1), date(2099, 6, 2)),
        )
        assert r.not_released_nights == 0
        assert r.releases_on is None

    def test_only_requested_days_of_week_count(self) -> None:
        # 2099-06-05 is a Friday, 06-06 Saturday, 06-08 Monday.
        avail = _avail(_site("1", {
            "2099-06-05": "NYR", "2099-06-06": "NYR", "2099-06-08": "NYR",
        }))
        r = _process_availability(
            make_campground(), avail,
            _query(date(2099, 6, 5), date(2099, 6, 8), days_of_week={4, 5, 6}),
        )
        assert r.not_released_nights == 2
        assert r.releases_through == date(2098, 12, 6)

    def test_only_sites_that_fit_the_party_count(self) -> None:
        # The site big enough for 10 isn't released; the small one is booked.
        avail = _avail(
            _site("small", {"2099-06-01": "Reserved"}, max_people=4),
            _site("big", {"2099-06-01": "NYR"}, max_people=12),
        )
        q = _query(date(2099, 6, 1), date(2099, 6, 1))
        assert _process_availability(make_campground(), avail, q).not_released_nights == 0
        q.max_people = 10
        assert _process_availability(make_campground(), avail, q).not_released_nights == 1

    def test_no_release_date_when_the_rule_date_has_passed(self) -> None:
        # NYR three weeks out can't be on the 6-month window — that date passed.
        night = date.today() + timedelta(days=21)
        avail = _avail(_site("1", {night.isoformat(): "NYR"}))
        r = _process_availability(make_campground(), avail, _query(night, night))
        assert r.not_released_nights == 1
        assert r.releases_on is None
        assert r.releases_through is None

    def test_wa_search_past_the_nine_month_window(self) -> None:
        # GoingToCamp says Available for every night; on 2098-09-02 only
        # arrivals through 2099-06-02 are open.
        raw = {sid: [{"availability": 0}] * 4 for sid in ("1", "2")}
        sites = GoingToCampClient()._build_campsites(
            raw, date(2099, 6, 1), date(2099, 6, 4), today=date(2098, 9, 2),
        )
        r = _process_availability(
            make_campground(booking_system=BookingSystem.WA_STATE),
            CampgroundAvailability(facility_id="-2147483624", campsites=sites),
            _query(date(2099, 6, 1), date(2099, 6, 4)),
        )
        assert r.not_released_nights == 2
        assert r.releases_on == date(2098, 9, 3)
        assert r.releases_through == date(2098, 9, 4)
        assert {(w.start_date, w.nights) for w in r.available_windows} == {
            ("2099-06-01", 2),
        }

    def test_available_windows_are_unchanged(self) -> None:
        avail = _avail(
            _site("1", {"2099-06-01": "Available", "2099-06-02": "Available"}),
            _site("2", {"2099-06-01": "NYR", "2099-06-02": "NYR"}),
        )
        r = _process_availability(
            make_campground(), avail,
            _query(date(2099, 6, 1), date(2099, 6, 2), min_consecutive_nights=2),
        )
        assert [(w.campsite_id, w.nights) for w in r.available_windows] == [("1", 2)]
        assert r.not_released_nights == 0

