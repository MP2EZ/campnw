"""Provider degradation must reach the client (audit ANLT-06).

The warning pipeline was dead from the middle outward:

  - engine.search() aggregates per-source SearchWarnings — correctly.
  - /api/search serialises them, and PR #136 made the copy name the source
    that actually failed.
  - Nothing calls /api/search. `searchCampsites` is exported from api.ts and
    imported by no one.
  - The UI uses search_stream, whose frames were diagnosis / parsed_params /
    progress / result / summary only. No warning frame existed, so the client
    hardcoded `warnings: []`.

So during the live ReserveAmerica outage (#131) the product showed users
nothing, and #136's careful per-source messages were unreachable.

These tests pin the aggregation (including a count bug the audit flagged) and
the stream frame that carries it.
"""

from __future__ import annotations

from pnw_campsites.registry.models import BookingSystem, Campground
from pnw_campsites.search.engine import CampgroundResult, aggregate_warnings


def _result(source: BookingSystem, error: str | None) -> CampgroundResult:
    return CampgroundResult(
        campground=Campground(
            facility_id="1", name="X", booking_system=source, state="WA",
        ),
        error=error,
    )


class TestAggregateWarnings:
    def test_counts_are_per_source_not_the_combined_total(self):
        """`count` must describe the source the warning names.

        The aggregation used `sum(sources.values())` — the total across every
        source — for each per-source warning, so a rate limit hitting 3
        rec.gov and 1 WA campground told the user "4" for both.
        """
        results = [
            _result(BookingSystem.RECGOV, "rate_limited"),
            _result(BookingSystem.RECGOV, "rate_limited"),
            _result(BookingSystem.RECGOV, "rate_limited"),
            _result(BookingSystem.WA_STATE, "rate_limited"),
        ]
        by_source = {w.source: w.count for w in aggregate_warnings(results)}
        assert by_source == {"recgov": 3, "wa_state": 1}

    def test_separates_kinds(self):
        results = [
            _result(BookingSystem.OR_STATE, "waf_blocked"),
            _result(BookingSystem.OR_STATE, "waf_blocked"),
            _result(BookingSystem.RECGOV, "rate_limited"),
        ]
        got = {(w.kind, w.source): w.count for w in aggregate_warnings(results)}
        assert got == {
            ("waf_blocked", "or_state"): 2,
            ("rate_limited", "recgov"): 1,
        }

    def test_healthy_results_produce_no_warnings(self):
        assert aggregate_warnings([_result(BookingSystem.RECGOV, None)]) == []

    def test_empty_input(self):
        assert aggregate_warnings([]) == []


class TestStreamEmitsWarnings:
    """The SSE stream must carry warnings; otherwise the whole pipeline above
    it is unreachable no matter how correct it is."""

    def test_stream_yields_a_warnings_event(self, api_client, monkeypatch):
        from pnw_campsites.routes import search as search_routes
        from pnw_campsites.search import engine as engine_mod

        async def fake_stream(query):
            yield _result(BookingSystem.OR_STATE, "waf_blocked")
            yield engine_mod.StreamWarningsEvent(
                warnings=[
                    engine_mod.SearchWarning(
                        kind="waf_blocked", count=2, source="or_state",
                    )
                ]
            )

        class FakeEngine:
            search_stream = staticmethod(fake_stream)

        # routes/search.py imports get_engine by name, so the binding to
        # patch is the one in that module, not the one in deps.
        monkeypatch.setattr(search_routes, "get_engine", lambda: FakeEngine())

        resp = api_client.get(
            "/api/search/stream",
            params={"start_date": "2026-06-01", "end_date": "2026-06-30"},
        )
        assert resp.status_code == 200
        body = resp.text

        assert '"type": "warnings"' in body, (
            "the stream emitted no warnings frame, so provider degradation is "
            "invisible to the UI regardless of how well the message reads"
        )
        # The message must name the source that actually failed (PR #136).
        assert "Oregon State Parks" in body
        assert "WA State Parks" not in body
