"""Not-yet-released (NYR) nights must not read as "fully booked".

A June 2027 search run on 2026-11-06 returned nothing from Recreation.gov
because June wasn't released, and the engine treated NYR like any other
unavailable status — so users concluded everything was full.
"""

from __future__ import annotations

import json
from datetime import date, timedelta

from pnw_campsites.providers.goingtocamp import GoingToCampClient
from pnw_campsites.registry.models import BookingSystem, CampgroundAvailability
from pnw_campsites.search.engine import (
    CampgroundResult,
    NotReleasedSummary,
    SearchEngine,
    SearchQuery,
    StreamDiagnosisEvent,
    StreamNotReleasedEvent,
    _process_availability,
    summarize_not_released,
)
from pnw_campsites.search.release import format_release_range
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
        # Fri-Sat run, then Monday: which nights, not just how many.
        assert [(x.start, x.end, x.releases_on) for x in r.not_released_ranges] == [
            (date(2099, 6, 5), date(2099, 6, 6), date(2098, 12, 5)),
        ]

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


def _result(source=BookingSystem.RECGOV, nights=0, first=None, last=None):
    return CampgroundResult(
        campground=make_campground(booking_system=source),
        not_released_nights=nights, releases_on=first, releases_through=last,
    )


class TestSummarizeNotReleased:
    def test_counts_campgrounds_and_spans_first_to_last_release(self) -> None:
        s = summarize_not_released([
            _result(nights=4, first=date(2026, 12, 4), last=date(2026, 12, 25)),
            _result(nights=2, first=date(2026, 12, 5), last=date(2026, 12, 6)),
            _result(BookingSystem.WA_STATE, nights=3),  # no rule: no dates
            _result(),  # released
        ])
        assert s.campgrounds == 3
        assert s.releases_on_earliest == date(2026, 12, 4)
        assert s.releases_on_latest == date(2026, 12, 25)

    def test_nothing_unreleased(self) -> None:
        s = summarize_not_released([_result()])
        assert (s.campgrounds, s.releases_on_earliest, s.releases_on_latest) == (0, None, None)


class TestFormatReleaseRange:
    def test_formats(self) -> None:
        # Matches the frontend's formatDateRange (web/src/lib/dates.ts).
        assert format_release_range(date(2026, 12, 4), date(2026, 12, 4)) == "Dec 4"
        assert format_release_range(date(2026, 12, 4), date(2026, 12, 25)) == "Dec 4 – 25"
        assert format_release_range(date(2026, 12, 28), date(2027, 1, 3)) == "Dec 28 – Jan 3"


class TestDiagnosisNotReleased:
    def _engine(self):
        from unittest.mock import MagicMock

        return SearchEngine(registry=MagicMock())

    def test_not_released_outranks_fully_booked(self) -> None:
        q = _query(date(2027, 6, 4), date(2027, 6, 27))
        summary = NotReleasedSummary(
            campgrounds=18,
            releases_on_earliest=date(2026, 12, 4),
            releases_on_latest=date(2026, 12, 27),
        )
        diagnosis, chips = self._engine()._diagnose_zero_results(
            q, registry_matches=40, distance_filtered=0, checked=20,
            all_unavailable=20, not_released=summary,
        )
        assert diagnosis.binding_constraint == "not_released"
        assert "fully booked" not in diagnosis.explanation
        assert "18 of 20" in diagnosis.explanation
        assert "Dec 4 – 27" in diagnosis.explanation
        assert any(c.action == "watch" for c in chips)

    def test_copy_reads_naturally_when_none_are_released(self) -> None:
        q = _query(date(2027, 6, 4), date(2027, 6, 6))
        explain = lambda n, checked: self._engine()._diagnose_zero_results(  # noqa: E731
            q, registry_matches=checked, distance_filtered=0, checked=checked,
            all_unavailable=checked, not_released=NotReleasedSummary(campgrounds=n),
        )[0].explanation
        assert explain(1, 1) == "This campground hasn't released these dates for booking yet."
        assert explain(3, 3) == (
            "None of the 3 campgrounds have released these dates for booking yet."
        )

    def test_without_a_release_date_it_still_says_not_released(self) -> None:
        q = _query(date(2027, 9, 4), date(2027, 9, 6))
        diagnosis, _ = self._engine()._diagnose_zero_results(
            q, registry_matches=5, distance_filtered=0, checked=5,
            all_unavailable=5, not_released=NotReleasedSummary(campgrounds=2),
        )
        assert diagnosis.binding_constraint == "not_released"
        assert "2 of 5" in diagnosis.explanation
        assert "opens" not in diagnosis.explanation

    def test_fully_booked_unchanged_when_everything_is_released(self) -> None:
        q = _query(date(2027, 6, 4), date(2027, 6, 6))
        diagnosis, _ = self._engine()._diagnose_zero_results(
            q, registry_matches=5, distance_filtered=0, checked=5,
            all_unavailable=5, not_released=NotReleasedSummary(campgrounds=0),
        )
        assert diagnosis.binding_constraint == "dates"


def _nyr_engine(registry):
    """Engine over one rec.gov campground whose whole June 2099 is NYR."""
    from unittest.mock import AsyncMock

    registry.upsert(make_campground(facility_id="233116", state="CA"))
    june = {f"2099-06-{d:02d}": "NYR" for d in range(1, 31)}
    recgov = AsyncMock()
    recgov.get_availability_range = AsyncMock(
        return_value=_avail(_site("1", june), _site("2", june)),
    )
    return SearchEngine(registry=registry, recgov_client=recgov)


class TestSearchReportsNotReleased:
    async def test_search_summarizes_campgrounds_it_did_not_return(self, registry) -> None:
        results = await _nyr_engine(registry).search(
            _query(date(2099, 6, 4), date(2099, 6, 27), max_campgrounds=5),
        )
        assert results.results == []  # no availability: not a result
        assert results.not_released.campgrounds == 1
        assert results.not_released.releases_on_earliest == date(2098, 12, 4)
        assert results.not_released.releases_on_latest == date(2098, 12, 27)
        assert results.diagnosis.binding_constraint == "not_released"
        assert "Dec 4 – 27" in results.diagnosis.explanation

    async def test_stream_emits_a_not_released_event_then_the_diagnosis(self, registry) -> None:
        events = [
            e async for e in _nyr_engine(registry).search_stream(
                _query(date(2099, 6, 4), date(2099, 6, 27), max_campgrounds=5),
            )
        ]
        kinds = [type(e).__name__ for e in events]
        assert kinds.index("StreamNotReleasedEvent") < kinds.index("StreamDiagnosisEvent")
        summary = next(e for e in events if isinstance(e, StreamNotReleasedEvent)).summary
        assert summary.campgrounds == 1
        diagnosis = next(e for e in events if isinstance(e, StreamDiagnosisEvent)).diagnosis
        assert diagnosis.binding_constraint == "not_released"


class TestApiCarriesNotReleased:
    """Both /api/search and the SSE stream must carry the fields."""

    SUMMARY = NotReleasedSummary(
        campgrounds=18,
        releases_on_earliest=date(2026, 12, 4),
        releases_on_latest=date(2026, 12, 27),
    )

    def _patch_engine(self, monkeypatch, engine) -> None:
        from pnw_campsites.routes import search as search_routes

        monkeypatch.setattr(search_routes, "get_engine", lambda: engine)

    def test_search_endpoint(self, api_client, monkeypatch) -> None:
        from pnw_campsites.search.engine import SearchResults
        from pnw_campsites.search.release import NotReleasedRange

        partly = _result(nights=3, first=date(2026, 12, 25), last=date(2026, 12, 27))
        partly.total_available_sites = 1
        partly.not_released_ranges = [
            NotReleasedRange(date(2027, 6, 25), date(2027, 6, 27), date(2026, 12, 25)),
        ]

        class FakeEngine:
            async def search(self, query):
                return SearchResults(
                    query=query, results=[partly], campgrounds_checked=20,
                    campgrounds_with_availability=1, not_released=TestApiCarriesNotReleased.SUMMARY,
                )

        self._patch_engine(monkeypatch, FakeEngine())
        body = api_client.get(
            "/api/search", params={"start_date": "2027-06-04", "end_date": "2027-06-27"},
        ).json()
        assert body["not_released_campgrounds"] == 18
        assert body["releases_on_earliest"] == "2026-12-04"
        assert body["releases_on_latest"] == "2026-12-27"
        assert body["results"][0]["not_released_nights"] == 3
        assert body["results"][0]["releases_on"] == "2026-12-25"
        assert body["results"][0]["not_released_ranges"] == [
            {"start": "2027-06-25", "end": "2027-06-27", "releases_on": "2026-12-25"},
        ]

    def test_stream_emits_a_not_released_frame(self, api_client, monkeypatch) -> None:
        async def fake_stream(query):
            yield StreamNotReleasedEvent(summary=TestApiCarriesNotReleased.SUMMARY)

        class FakeEngine:
            search_stream = staticmethod(fake_stream)

        self._patch_engine(monkeypatch, FakeEngine())
        resp = api_client.get(
            "/api/search/stream",
            params={"start_date": "2027-06-04", "end_date": "2027-06-27"},
        )
        frames = [
            json.loads(line[6:]) for line in resp.text.splitlines()
            if line.startswith("data: {")
        ]
        assert {
            "type": "not_released",
            "not_released_campgrounds": 18,
            "releases_on_earliest": "2026-12-04",
            "releases_on_latest": "2026-12-27",
        } in frames


class TestStreamSendsUnavailableCampgrounds:
    """v1.48 D4: the "Full or not released yet" group lists checked
    campgrounds with nothing to book, so the stream must send them."""

    async def test_engine_attaches_the_result_to_its_progress_event(self, registry) -> None:
        from pnw_campsites.search.engine import StreamProgressEvent

        events = [
            e async for e in _nyr_engine(registry).search_stream(
                _query(date(2099, 6, 4), date(2099, 6, 27), max_campgrounds=5),
            )
        ]
        progress = [e for e in events if isinstance(e, StreamProgressEvent)]
        assert progress and all(e.result is not None for e in progress)
        assert progress[0].result.not_released_ranges

    def test_stream_emits_an_unavailable_frame(self, api_client, monkeypatch) -> None:
        from pnw_campsites.search.engine import StreamProgressEvent
        from pnw_campsites.search.release import NotReleasedRange

        full = _result()
        nyr = _result(nights=2, first=date(2026, 12, 4), last=date(2026, 12, 5))
        nyr.not_released_ranges = [
            NotReleasedRange(date(2027, 6, 4), date(2027, 6, 5), date(2026, 12, 4)),
        ]
        broken = _result()
        broken.error = "waf_blocked"

        async def fake_stream(query):
            yield StreamProgressEvent(checked=1, total=3, result=full)
            yield StreamProgressEvent(checked=2, total=3, result=nyr)
            yield StreamProgressEvent(checked=3, total=3, result=broken)

        class FakeEngine:
            search_stream = staticmethod(fake_stream)

        monkeypatch.setattr(
            __import__("pnw_campsites.routes.search", fromlist=["x"]), "get_engine",
            lambda: FakeEngine(),
        )
        resp = api_client.get(
            "/api/search/stream",
            params={"start_date": "2027-06-04", "end_date": "2027-06-27"},
        )
        frames = [
            json.loads(line[6:]) for line in resp.text.splitlines()
            if line.startswith("data: {")
        ]
        assert [f["checked"] for f in frames if f["type"] == "progress"] == [1, 2, 3]
        unavailable = [f["result"] for f in frames if f["type"] == "unavailable"]
        # An errored check couldn't be checked: it's a warning, not "full".
        assert len(unavailable) == 2
        assert unavailable[0]["windows"] == []
        assert unavailable[1]["not_released_ranges"] == [
            {"start": "2027-06-04", "end": "2027-06-05", "releases_on": "2026-12-04"},
        ]


class TestRangesForCandidateWindows:
    """not_released_ranges / closed_ranges feed v2's per-weekend status, so
    they must not call a weekend "full" when it isn't."""

    def test_a_night_any_site_hasnt_released_is_in_a_range(self) -> None:
        # Denny Creek, June 2027: one site released (and booked), the rest
        # NYR. The strict count says 0; the weekend still isn't "full".
        avail = _avail(
            _site("1", {"2099-06-04": "Reserved", "2099-06-05": "Reserved"}),
            _site("2", {"2099-06-04": "NYR", "2099-06-05": "NYR"}),
        )
        r = _process_availability(
            make_campground(), avail, _query(date(2099, 6, 4), date(2099, 6, 5)),
        )
        assert r.not_released_nights == 0
        assert [(x.start, x.end) for x in r.not_released_ranges] == [
            (date(2099, 6, 4), date(2099, 6, 5)),
        ]

    def test_nights_nothing_can_be_reserved_are_closed(self) -> None:
        # Tinkham in November: no availability data at all. A seasonal
        # closure or first-come-only night is not "full" either.
        avail = _avail(
            _site("1", {"2099-06-04": "Closed", "2099-06-05": "Reserved", "2099-06-06": "Not Reservable"}),
            _site("2", {"2099-06-04": "Not Available"}),
        )
        r = _process_availability(
            make_campground(), avail, _query(date(2099, 6, 4), date(2099, 6, 7)),
        )
        assert [(x.start, x.end) for x in r.closed_ranges] == [
            (date(2099, 6, 4), date(2099, 6, 4)),
            (date(2099, 6, 6), date(2099, 6, 7)),
        ]

    def test_closed_nights_respect_the_searched_days(self) -> None:
        # 2099-06-05 is a Friday, 06-06 Saturday, 06-08 Monday.
        avail = _avail(_site("1", {}))
        r = _process_availability(
            make_campground(), avail,
            _query(date(2099, 6, 5), date(2099, 6, 8), days_of_week={4, 5}),
        )
        assert [(x.start, x.end) for x in r.closed_ranges] == [
            (date(2099, 6, 5), date(2099, 6, 6)),
        ]

    def test_api_sends_closed_ranges(self, api_client, monkeypatch) -> None:
        from pnw_campsites.search.engine import NightRange, SearchResults

        r = _result()
        r.total_available_sites = 1
        r.closed_ranges = [NightRange(date(2026, 11, 13), date(2026, 11, 15))]

        class FakeEngine:
            async def search(self, query):
                return SearchResults(query=query, results=[r], campgrounds_checked=1,
                                     campgrounds_with_availability=1)

        from pnw_campsites.routes import search as search_routes

        monkeypatch.setattr(search_routes, "get_engine", lambda: FakeEngine())
        body = api_client.get(
            "/api/search", params={"start_date": "2026-11-13", "end_date": "2026-11-15"},
        ).json()
        assert body["results"][0]["closed_ranges"] == [{"start": "2026-11-13", "end": "2026-11-15"}]
