"""Provider degradation reaches the client: per-source warning counts and the stream warnings frame."""

from __future__ import annotations

from pnw_campsites.registry.models import BookingSystem, Campground
from pnw_campsites.routes import search as search_routes
from pnw_campsites.search import engine as engine_mod
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
        """`count` describes the source the warning names (3 rec.gov, 1 WA)."""
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
    """The SSE stream carries the aggregated warnings to the client."""

    def test_stream_yields_a_warnings_event(self, api_client, monkeypatch):
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

        assert '"type": "warnings"' in body
        # The message names the source that actually failed.
        assert "Oregon State Parks" in body
        assert "WA State Parks" not in body
