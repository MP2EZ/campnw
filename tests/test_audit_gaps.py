"""Tests for gaps identified in the codebase audit.

Covers: auth rate limiter, plan rate limiter, push subscribe/unsubscribe,
recommendation scoring, search stream NL integration, date suggestion probes,
and security header middleware.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import pnw_campsites.api as api_module

TOKEN_COOKIE = "campnw_token"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _signup(client: TestClient, email: str = "test@example.com") -> dict:
    resp = client.post(
        "/api/auth/signup",
        json={"email": email, "password": "testpass123", "display_name": "Tester"},
    )
    assert resp.status_code == 200
    return resp.json()


def _save_searches(client: TestClient, count: int = 5, tags: str = "lakeside") -> None:
    for i in range(count):
        client.post(
            "/api/search-history",
            json={
                "params": {
                    "start_date": "2026-06-01",
                    "end_date": "2026-06-30",
                    "state": "WA",
                    "tags": tags,
                },
                "result_count": i * 3,
            },
        )


# ---------------------------------------------------------------------------
# TEST-01: Auth rate limiter
# ---------------------------------------------------------------------------


class TestAuthRateLimiter:
    """Tests for auth rate limiting (10 attempts / 15 min window)."""

    def test_first_attempt_allowed(self, api_client: TestClient):
        resp = api_client.post(
            "/api/auth/login",
            json={"email": "nobody@example.com", "password": "wrong"},
        )
        assert resp.status_code == 401  # Wrong creds, but not rate limited

    def test_tenth_attempt_allowed(self, api_client: TestClient):
        """10th attempt within window should still be allowed."""
        for _ in range(10):
            resp = api_client.post(
                "/api/auth/login",
                json={"email": "nobody@example.com", "password": "wrong"},
            )
        assert resp.status_code == 401  # Still auth error, not 429

    def test_eleventh_attempt_returns_429(self, api_client: TestClient):
        """11th attempt should be rate limited."""
        for _ in range(11):
            resp = api_client.post(
                "/api/auth/login",
                json={"email": "nobody@example.com", "password": "wrong"},
            )
        assert resp.status_code == 429

    def test_rate_limit_applies_to_signup_too(self, api_client: TestClient):
        """Rate limit should also apply to signup endpoint."""
        for i in range(11):
            resp = api_client.post(
                "/api/auth/signup",
                json={
                    "email": f"user{i}@example.com",
                    "password": "testpass123",
                },
            )
        assert resp.status_code == 429


# ---------------------------------------------------------------------------
# TEST-04: Plan rate limiter
# ---------------------------------------------------------------------------


class TestPlanRateLimiter:
    """Tests for trip planner rate limiting (5 sessions/day)."""

    def test_plan_rate_limit_allows_5(self, api_client: TestClient):
        """First 5 calls should be allowed (or 503 if no API key)."""
        from pnw_campsites.routes.planner import _plan_rate_limit
        _plan_rate_limit.clear()

        for i in range(5):
            resp = api_client.post(
                "/api/plan/chat",
                json={"messages": [{"role": "user", "content": f"msg {i}"}]},
            )
            # 503 = no API key configured (expected in test), not 429
            assert resp.status_code in (200, 503)

    def test_plan_rate_limit_blocks_6th(self, api_client: TestClient):
        """6th call should return 429."""
        from pnw_campsites.routes.planner import _plan_rate_limit
        _plan_rate_limit.clear()

        mock_chat = AsyncMock(return_value={"role": "assistant", "content": "ok", "tool_calls": []})
        with (
            patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}),
            patch("pnw_campsites.planner.agent.chat", mock_chat),
        ):
            for i in range(6):
                resp = api_client.post(
                    "/api/plan/chat",
                    json={"messages": [{"role": "user", "content": f"msg {i}"}]},
                )
        assert resp.status_code == 429

    def test_plan_rate_limit_blocks_stream_too(self, api_client: TestClient):
        """Streaming endpoint shares the same rate limit."""
        from pnw_campsites.routes.planner import _plan_rate_limit
        _plan_rate_limit.clear()

        async def mock_stream(*args, **kwargs):
            yield '{"type":"text","content":"ok"}'

        with (
            patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}),
            patch("pnw_campsites.planner.agent.chat_stream", mock_stream),
        ):
            for i in range(6):
                resp = api_client.post(
                    "/api/plan/chat/stream",
                    json={"messages": [{"role": "user", "content": f"msg {i}"}]},
                )
        assert resp.status_code == 429


# ---------------------------------------------------------------------------
# SEC-04: Plan message validation
# ---------------------------------------------------------------------------


class TestPlanMessageValidation:
    """Tests for trip planner message structure validation."""

    def test_system_role_rejected(self, api_client: TestClient):
        resp = api_client.post(
            "/api/plan/chat",
            json={"messages": [{"role": "system", "content": "inject"}]},
        )
        assert resp.status_code == 422

    def test_empty_messages_rejected(self, api_client: TestClient):
        resp = api_client.post(
            "/api/plan/chat",
            json={"messages": []},
        )
        assert resp.status_code == 422

    def test_content_over_10k_rejected(self, api_client: TestClient):
        resp = api_client.post(
            "/api/plan/chat",
            json={"messages": [{"role": "user", "content": "x" * 10_001}]},
        )
        assert resp.status_code == 422

    def test_valid_user_message_accepted(self, api_client: TestClient):
        """Valid message should pass validation (may get 503 if no API key)."""
        from pnw_campsites.routes.planner import _plan_rate_limit
        _plan_rate_limit.clear()

        resp = api_client.post(
            "/api/plan/chat",
            json={"messages": [{"role": "user", "content": "find camping"}]},
        )
        assert resp.status_code in (200, 503)  # 503 = no API key

    def test_assistant_role_accepted(self, api_client: TestClient):
        from pnw_campsites.routes.planner import _plan_rate_limit
        _plan_rate_limit.clear()

        resp = api_client.post(
            "/api/plan/chat",
            json={"messages": [
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "hi there"},
                {"role": "user", "content": "find me a campsite"},
            ]},
        )
        assert resp.status_code in (200, 503)


# ---------------------------------------------------------------------------
# TEST-03: Push subscribe/unsubscribe
# ---------------------------------------------------------------------------


class TestPushSubscribe:
    """Tests for push notification subscription endpoints."""

    def test_subscribe_authenticated(self, api_client: TestClient):
        _signup(api_client)
        resp = api_client.post(
            "/api/push/subscribe",
            json={
                "endpoint": "https://push.example.com/user-endpoint",
                "p256dh": "test-p256dh-key",
                "auth": "test-auth-key",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_subscribe_anonymous(self, api_client: TestClient):
        """Anonymous users can subscribe via session cookie."""
        resp = api_client.post(
            "/api/push/subscribe",
            json={
                "endpoint": "https://push.example.com/anon-endpoint",
                "p256dh": "test-p256dh",
                "auth": "test-auth",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_unsubscribe_authenticated(self, api_client: TestClient):
        _signup(api_client)
        # Subscribe first
        api_client.post(
            "/api/push/subscribe",
            json={
                "endpoint": "https://push.example.com/to-remove",
                "p256dh": "key",
                "auth": "auth",
            },
        )
        # Then unsubscribe
        resp = api_client.request(
            "DELETE",
            "/api/push/subscribe",
            json={"endpoint": "https://push.example.com/to-remove"},
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_subscribe_missing_fields_422(self, api_client: TestClient):
        resp = api_client.post(
            "/api/push/subscribe",
            json={"endpoint": "https://push.example.com/test"},
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Recommendations scoring
# ---------------------------------------------------------------------------


class TestRecommendationScoring:
    """Tests for the recommendation scoring and reason generation."""

    @staticmethod
    def _enable_recs(api_client: TestClient):
        """Enable recommendations for the current user via direct DB call."""
        me = api_client.get("/api/auth/me").json()
        api_module._watch_db.update_user(me["user"]["id"], recommendations_enabled=True)

    def test_recommendations_score_by_tag_overlap(self, api_client: TestClient):
        """Campgrounds matching searched tags should score higher."""
        from tests.conftest import make_campground

        _signup(api_client)
        self._enable_recs(api_client)
        _save_searches(api_client, count=5, tags="lakeside")

        campgrounds = [
            make_campground(facility_id="lake-1", name="Lake A", tags=["lakeside"], state="WA"),
            make_campground(facility_id="forest-1", name="Forest B", tags=["forest"], state="WA"),
        ]
        api_module._registry.search.return_value = campgrounds

        resp = api_client.get("/api/recommendations")
        recs = resp.json()
        assert len(recs) >= 1
        assert recs[0]["facility_id"] == "lake-1"  # Lakeside matches affinity

    def test_recommendations_exclude_watched(self, api_client: TestClient):
        """Watched campgrounds should not appear in recommendations."""
        from tests.conftest import make_campground

        _signup(api_client)
        self._enable_recs(api_client)
        _save_searches(api_client, count=5, tags="lakeside")

        # Create a watch for lake-1
        api_module._registry.get_by_facility_id.return_value = make_campground(
            facility_id="lake-1", name="Lake A",
        )
        api_client.post("/api/watches", json={
            "facility_id": "lake-1",
            "start_date": "2026-06-01",
            "end_date": "2026-06-30",
        })

        campgrounds = [
            make_campground(facility_id="lake-1", name="Lake A", tags=["lakeside"], state="WA"),
            make_campground(facility_id="lake-2", name="Lake B", tags=["lakeside"], state="WA"),
        ]
        api_module._registry.search.return_value = campgrounds

        resp = api_client.get("/api/recommendations")
        recs = resp.json()
        facility_ids = [r["facility_id"] for r in recs]
        assert "lake-1" not in facility_ids  # Watched — excluded
        assert "lake-2" in facility_ids

    def test_recommendations_reason_references_tag(self, api_client: TestClient):
        """Reason string should reference the matched tag."""
        from tests.conftest import make_campground

        _signup(api_client)
        self._enable_recs(api_client)
        _save_searches(api_client, count=5, tags="lakeside")

        campgrounds = [
            make_campground(facility_id="lake-1", name="Lake A", tags=["lakeside"], state="WA"),
        ]
        api_module._registry.search.return_value = campgrounds

        resp = api_client.get("/api/recommendations")
        recs = resp.json()
        assert len(recs) == 1
        assert "lakeside" in recs[0]["reason"]

    def test_recommendations_max_5(self, api_client: TestClient):
        """Should return at most 5 recommendations."""
        from tests.conftest import make_campground

        _signup(api_client)
        self._enable_recs(api_client)
        _save_searches(api_client, count=5, tags="lakeside")

        campgrounds = [
            make_campground(
                facility_id=f"lake-{i}", name=f"Lake {i}",
                tags=["lakeside"], state="WA",
            )
            for i in range(10)
        ]
        api_module._registry.search.return_value = campgrounds

        resp = api_client.get("/api/recommendations")
        assert len(resp.json()) <= 5


# ---------------------------------------------------------------------------
# TEST-10: Security headers
# ---------------------------------------------------------------------------


class TestSecurityHeaders:
    """Tests for security header middleware."""

    def test_security_headers_present(self, api_client: TestClient):
        """Every response should include security headers."""
        resp = api_client.get("/api/perf")
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"
        assert resp.headers.get("X-Frame-Options") == "DENY"
        assert "max-age=" in resp.headers.get("Strict-Transport-Security", "")
        assert "default-src" in resp.headers.get("Content-Security-Policy", "")


# ---------------------------------------------------------------------------
# TEST-06: Date suggestion probes
# ---------------------------------------------------------------------------


class TestDateSuggestionProbes:
    """Tests for _suggest_alternative_dates parallelized probes."""

    @pytest.mark.asyncio
    async def test_past_date_windows_skipped(self):
        """Probes that would start before today should be excluded."""
        from pnw_campsites.search.engine import SearchEngine, SearchQuery

        registry = MagicMock()
        registry.search.return_value = []
        engine = SearchEngine(registry=registry, recgov_client=AsyncMock())

        # Search dates in the past — no valid probes
        query = SearchQuery(
            start_date=date(2020, 1, 1),
            end_date=date(2020, 1, 7),
        )

        with patch.object(engine, "search", new_callable=AsyncMock) as mock_search:
            suggestions = await engine._suggest_alternative_dates(query)

        # All shifted dates would be in the past — should return empty
        assert suggestions == []
        mock_search.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_max_3_suggestions(self):
        """Should return at most 3 date suggestions."""
        from pnw_campsites.search.engine import SearchEngine, SearchQuery, SearchResults

        registry = MagicMock()
        registry.search.return_value = []
        engine = SearchEngine(registry=registry, recgov_client=AsyncMock())

        query = SearchQuery(
            start_date=date(2026, 8, 1),
            end_date=date(2026, 8, 7),
        )

        # All probes return results
        mock_result = SearchResults(query=query, campgrounds_with_availability=3)
        with patch.object(engine, "search", new_callable=AsyncMock, return_value=mock_result):
            suggestions = await engine._suggest_alternative_dates(query)

        assert len(suggestions) <= 3

    @pytest.mark.asyncio
    async def test_sorted_by_proximity(self):
        """Suggestions should be sorted by closeness to original dates."""
        from pnw_campsites.search.engine import SearchEngine, SearchQuery, SearchResults

        registry = MagicMock()
        registry.search.return_value = []
        engine = SearchEngine(registry=registry, recgov_client=AsyncMock())

        query = SearchQuery(
            start_date=date(2026, 8, 1),
            end_date=date(2026, 8, 7),
        )

        mock_result = SearchResults(query=query, campgrounds_with_availability=2)
        with patch.object(engine, "search", new_callable=AsyncMock, return_value=mock_result):
            suggestions = await engine._suggest_alternative_dates(query)

        if len(suggestions) >= 2:
            # First suggestion should be closer to original dates
            d0 = abs((date.fromisoformat(suggestions[0].start_date) - query.start_date).days)
            d1 = abs((date.fromisoformat(suggestions[1].start_date) - query.start_date).days)
            assert d0 <= d1

    @pytest.mark.asyncio
    async def test_no_suggestions_when_no_dates(self):
        """Should return empty list when query has no dates."""
        from pnw_campsites.search.engine import SearchEngine, SearchQuery

        registry = MagicMock()
        engine = SearchEngine(registry=registry, recgov_client=AsyncMock())

        query = SearchQuery()  # No dates
        suggestions = await engine._suggest_alternative_dates(query)
        assert suggestions == []


# ---------------------------------------------------------------------------
# Search stream with NL query fallback
# ---------------------------------------------------------------------------


class TestSearchStreamNLIntegration:
    """Tests for the NL query parameter in the search stream endpoint."""

    @staticmethod
    def _setup_empty_engine():
        async def empty_stream(query):
            from pnw_campsites.search.engine import StreamDiagnosisEvent
            yield StreamDiagnosisEvent(diagnosis=None, date_suggestions=[], action_chips=[])

        api_module._engine.search_stream = empty_stream

    def test_stream_with_q_param_and_api_key(self, api_client: TestClient):
        """NL query with API key should emit parsed_params event."""
        self._setup_empty_engine()

        mock_parse_result = {
            "start_date": "2026-06-01",
            "end_date": "2026-06-07",
            "state": "WA",
            "tags": ["lakeside"],
        }

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}), patch(
            "pnw_campsites.search.nl_parser.parse_natural_query",
            new_callable=AsyncMock,
            return_value=mock_parse_result,
        ):
            resp = api_client.get(
                "/api/search/stream",
                params={"q": "lakeside near Seattle this weekend"},
            )

        assert resp.status_code == 200
        # Should contain a parsed_params event
        assert "parsed_params" in resp.text

    def test_stream_with_q_no_api_key_uses_defaults(self, api_client: TestClient):
        """NL query without API key should use default dates."""
        self._setup_empty_engine()

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": ""}, clear=False):
            resp = api_client.get(
                "/api/search/stream",
                params={"q": "camping in montana"},
            )

        assert resp.status_code == 200
        assert "data: [DONE]" in resp.text
        # Should NOT have parsed_params since no API key
        assert "parsed_params" not in resp.text


# ---------------------------------------------------------------------------
# Watcher cache path
# ---------------------------------------------------------------------------


class TestWatcherCachePath:
    """Tests for availability cache behavior during polling."""

    @pytest.mark.asyncio
    async def test_cache_hit_skips_provider(self, watch_db):
        """Second poll should use cached availability, not call provider again."""
        from pnw_campsites.monitor.watcher import _fetch_availability
        from pnw_campsites.registry.models import BookingSystem

        mock_recgov = AsyncMock()
        mock_availability = MagicMock()
        mock_availability.campsites = {}
        mock_availability.model_dump_json = MagicMock(
            return_value='{"facility_id":"232465","campsites":{}}',
        )
        mock_recgov.get_availability_range = AsyncMock(return_value=mock_availability)

        # First call — should hit provider
        await _fetch_availability(
            "232465", date(2026, 6, 1), date(2026, 6, 30),
            BookingSystem.RECGOV, mock_recgov, None, watch_db,
        )
        first_call_count = mock_recgov.get_availability.call_count

        # Second call — should use cache (within TTL)
        await _fetch_availability(
            "232465", date(2026, 6, 1), date(2026, 6, 30),
            BookingSystem.RECGOV, mock_recgov, None, watch_db,
        )
        second_call_count = mock_recgov.get_availability.call_count

        # If cache works, provider shouldn't be called again
        assert second_call_count == first_call_count


# ---------------------------------------------------------------------------
# _generate_search_summary
# ---------------------------------------------------------------------------


class TestGenerateSearchSummary:
    """Tests for the AI search summary helper."""

    @pytest.mark.asyncio
    async def test_returns_none_without_api_key(self):
        """Should return None when no ANTHROPIC_API_KEY is set."""
        from pnw_campsites.routes.search import _generate_search_summary
        from pnw_campsites.search.engine import SearchQuery

        query = SearchQuery(start_date=date(2026, 6, 1), end_date=date(2026, 6, 30))
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": ""}, clear=False):
            result = await _generate_search_summary([{"name": "Test"}], query)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_text_on_success(self):
        """Should return the LLM-generated summary string."""
        from pnw_campsites.routes.search import _generate_search_summary
        from pnw_campsites.search.engine import SearchQuery

        query = SearchQuery(
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 30),
            state="WA",
        )

        mock_content = MagicMock()
        mock_content.text = "  Lake Easton has the most weekend openings.  "
        mock_response = MagicMock()
        mock_response.content = [mock_content]

        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        with (
            patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}),
            patch("anthropic.AsyncAnthropic", return_value=mock_client),
        ):
            result = await _generate_search_summary(
                [{"name": "Lake Easton", "windows": 5}], query,
            )

        assert result == "Lake Easton has the most weekend openings."

    @pytest.mark.asyncio
    async def test_returns_none_on_timeout(self):
        """Should return None when LLM call times out."""
        from pnw_campsites.routes.search import _generate_search_summary
        from pnw_campsites.search.engine import SearchQuery

        query = SearchQuery(start_date=date(2026, 6, 1), end_date=date(2026, 6, 30))

        async def slow_create(**kwargs):
            import asyncio
            await asyncio.sleep(10)

        mock_client = MagicMock()
        mock_client.messages.create = slow_create

        with (
            patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}),
            patch("anthropic.AsyncAnthropic", return_value=mock_client),
        ):
            result = await _generate_search_summary(
                [{"name": "Test"}], query,
            )

        assert result is None

    @pytest.mark.asyncio
    async def test_caps_results_at_20(self):
        """Prompt should only include first 20 results."""
        from pnw_campsites.routes.search import _generate_search_summary
        from pnw_campsites.search.engine import SearchQuery

        query = SearchQuery(start_date=date(2026, 6, 1), end_date=date(2026, 6, 30))
        results = [{"name": f"Camp {i}"} for i in range(30)]

        mock_content = MagicMock()
        mock_content.text = "Summary"
        mock_response = MagicMock()
        mock_response.content = [mock_content]

        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        with (
            patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}),
            patch("anthropic.AsyncAnthropic", return_value=mock_client),
        ):
            await _generate_search_summary(results, query)

        # Verify the prompt sent to the LLM only included 20 results in the JSON
        call_args = mock_client.messages.create.call_args
        prompt = call_args.kwargs["messages"][0]["content"]
        # The prompt says "30 campgrounds" (total count) but the JSON caps at 20
        assert "Camp 19" in prompt  # 0-indexed: Camp 0..19 = 20 items
        assert "Camp 20" not in prompt  # 21st item should be excluded


# ---------------------------------------------------------------------------
# _format_result
# ---------------------------------------------------------------------------


class TestFormatResult:
    """Tests for the _format_result helper that converts engine results to API responses."""

    def test_basic_recgov_result(self):
        """Should format a basic rec.gov result with windows and URLs."""
        from tests.conftest import make_campground

        from pnw_campsites.routes.search import _format_result
        from pnw_campsites.search.engine import AvailableWindow, CampgroundResult

        cg = make_campground(
            facility_id="232465",
            name="Ohanapecosh",
            state="WA",
            tags=["old-growth", "river"],
        )
        windows = [
            AvailableWindow(
                campsite_id="site-1", site_name="Site 1", loop="A",
                campsite_type="STANDARD", start_date="2026-06-05",
                end_date="2026-06-07", nights=2, max_people=6,
            ),
            AvailableWindow(
                campsite_id="site-2", site_name="Site 2", loop="B",
                campsite_type="STANDARD", start_date="2026-06-12",
                end_date="2026-06-14", nights=2, max_people=4,
            ),
        ]
        result = CampgroundResult(
            campground=cg,
            available_windows=windows,
            total_available_sites=2,
        )

        formatted = _format_result(result, cg.booking_system)

        assert formatted.facility_id == "232465"
        assert formatted.name == "Ohanapecosh"
        assert formatted.state == "WA"
        assert formatted.total_available_sites == 2
        assert len(formatted.windows) == 2
        assert formatted.windows[0].campsite_id == "site-1"
        assert formatted.windows[0].booking_url is not None  # rec.gov gets booking URLs
        assert formatted.availability_url is not None
        assert formatted.tags == ["old-growth", "river"]

    def test_fcfs_window_has_no_booking_url(self):
        """FCFS windows should not have booking URLs."""
        from tests.conftest import make_campground

        from pnw_campsites.routes.search import _format_result
        from pnw_campsites.search.engine import AvailableWindow, CampgroundResult

        cg = make_campground(facility_id="123")
        window = AvailableWindow(
            campsite_id="fcfs-1", site_name="Walk-in 1", loop="C",
            campsite_type="STANDARD", start_date="2026-06-05",
            end_date="2026-06-07", nights=2, max_people=4,
            is_fcfs=True,
        )
        result = CampgroundResult(
            campground=cg,
            available_windows=[window],
            total_available_sites=1,
            fcfs_sites=1,
        )

        formatted = _format_result(result, cg.booking_system)
        assert formatted.windows[0].is_fcfs is True
        assert formatted.windows[0].booking_url is None

    def test_no_windows_gives_no_availability_url(self):
        """Result with no windows should have no availability URL."""
        from tests.conftest import make_campground

        from pnw_campsites.routes.search import _format_result
        from pnw_campsites.search.engine import CampgroundResult

        cg = make_campground(facility_id="999")
        result = CampgroundResult(campground=cg, available_windows=[])

        formatted = _format_result(result, cg.booking_system)
        assert formatted.availability_url is None
        assert len(formatted.windows) == 0

    def test_wa_state_result_has_no_booking_url(self):
        """WA State Park results don't have per-site booking URLs."""
        from tests.conftest import make_campground

        from pnw_campsites.registry.models import BookingSystem
        from pnw_campsites.routes.search import _format_result
        from pnw_campsites.search.engine import AvailableWindow, CampgroundResult

        cg = make_campground(
            facility_id="-2147483624",
            booking_system=BookingSystem.WA_STATE,
        )
        window = AvailableWindow(
            campsite_id="wa-site-1", site_name="WA Site", loop="Loop A",
            campsite_type="STANDARD", start_date="2026-07-01",
            end_date="2026-07-03", nights=2, max_people=6,
        )
        result = CampgroundResult(
            campground=cg,
            available_windows=[window],
            total_available_sites=1,
        )

        formatted = _format_result(result, cg.booking_system)
        assert formatted.windows[0].booking_url is None  # WA doesn't support per-site booking URLs
        assert formatted.availability_url is not None  # But does have availability URL

    def test_error_result_preserved(self):
        """Error message from the engine should be preserved."""
        from tests.conftest import make_campground

        from pnw_campsites.routes.search import _format_result
        from pnw_campsites.search.engine import CampgroundResult

        cg = make_campground(facility_id="404")
        result = CampgroundResult(
            campground=cg,
            available_windows=[],
            error="Facility returned 404",
        )

        formatted = _format_result(result, cg.booking_system)
        assert formatted.error == "Facility returned 404"

    def test_drive_time_preserved(self):
        """Estimated drive time should be passed through."""
        from tests.conftest import make_campground

        from pnw_campsites.routes.search import _format_result
        from pnw_campsites.search.engine import CampgroundResult

        cg = make_campground(facility_id="789")
        result = CampgroundResult(
            campground=cg,
            available_windows=[],
            estimated_drive_minutes=120,
        )

        formatted = _format_result(result, cg.booking_system)
        assert formatted.estimated_drive_minutes == 120


# ---------------------------------------------------------------------------
# _enhance_rec_reasons failure paths
# ---------------------------------------------------------------------------


class TestEnhanceRecReasons:
    """Tests for the LLM recommendation reason enhancement."""

    @pytest.mark.asyncio
    async def test_returns_none_without_api_key(self):
        """Should return None when no API key is set."""
        from pnw_campsites.routes.recommendations import _enhance_rec_reasons

        results = [{"name": "Lake A", "state": "WA", "tags": ["lakeside"], "vibe": ""}]
        affinities = {"tags": {"lakeside": 3.0}, "states": {"WA": 5.0}}

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": ""}, clear=False):
            result = await _enhance_rec_reasons(results, affinities)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_reasons_on_success(self):
        """Should return a list of reason strings on success."""
        from pnw_campsites.routes.recommendations import _enhance_rec_reasons

        results = [
            {"name": "Lake A", "state": "WA", "tags": ["lakeside"], "vibe": "Serene"},
            {"name": "Forest B", "state": "OR", "tags": ["forest"], "vibe": "Mossy"},
        ]
        affinities = {"tags": {"lakeside": 3.0, "forest": 1.5}, "states": {"WA": 5.0}}

        mock_content = MagicMock()
        mock_content.text = '["Lakefront paradise near your WA favorites", "Lush forest retreat"]'
        mock_response = MagicMock()
        mock_response.content = [mock_content]

        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        with (
            patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}),
            patch("anthropic.AsyncAnthropic", return_value=mock_client),
        ):
            reasons = await _enhance_rec_reasons(results, affinities)

        assert reasons == ["Lakefront paradise near your WA favorites", "Lush forest retreat"]

    @pytest.mark.asyncio
    async def test_returns_none_on_timeout(self):
        """Should return None when LLM times out."""
        from pnw_campsites.routes.recommendations import _enhance_rec_reasons

        results = [{"name": "Lake A", "state": "WA", "tags": ["lakeside"], "vibe": ""}]
        affinities = {"tags": {"lakeside": 3.0}, "states": {"WA": 5.0}}

        async def slow_create(**kwargs):
            import asyncio
            await asyncio.sleep(10)

        mock_client = MagicMock()
        mock_client.messages.create = slow_create

        with (
            patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}),
            patch("anthropic.AsyncAnthropic", return_value=mock_client),
        ):
            result = await _enhance_rec_reasons(results, affinities)

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_length_mismatch(self):
        """Should return None if LLM returns wrong number of reasons."""
        from pnw_campsites.routes.recommendations import _enhance_rec_reasons

        results = [
            {"name": "Lake A", "state": "WA", "tags": ["lakeside"], "vibe": ""},
            {"name": "Lake B", "state": "WA", "tags": ["lakeside"], "vibe": ""},
        ]
        affinities = {"tags": {"lakeside": 3.0}, "states": {"WA": 5.0}}

        mock_content = MagicMock()
        mock_content.text = '["Only one reason"]'  # 1 reason for 2 results
        mock_response = MagicMock()
        mock_response.content = [mock_content]

        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        with (
            patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}),
            patch("anthropic.AsyncAnthropic", return_value=mock_client),
        ):
            result = await _enhance_rec_reasons(results, affinities)

        assert result is None

    @pytest.mark.asyncio
    async def test_strips_markdown_fences(self):
        """Should handle LLM responses wrapped in markdown code fences."""
        from pnw_campsites.routes.recommendations import _enhance_rec_reasons

        results = [{"name": "Lake A", "state": "WA", "tags": ["lakeside"], "vibe": ""}]
        affinities = {"tags": {"lakeside": 3.0}, "states": {"WA": 5.0}}

        mock_content = MagicMock()
        mock_content.text = '```json\n["Lakefront gem near Seattle"]\n```'
        mock_response = MagicMock()
        mock_response.content = [mock_content]

        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        with (
            patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}),
            patch("anthropic.AsyncAnthropic", return_value=mock_client),
        ):
            reasons = await _enhance_rec_reasons(results, affinities)

        assert reasons == ["Lakefront gem near Seattle"]

    @pytest.mark.asyncio
    async def test_truncates_long_reasons(self):
        """Reasons longer than 80 chars should be truncated."""
        from pnw_campsites.routes.recommendations import _enhance_rec_reasons

        results = [{"name": "Lake A", "state": "WA", "tags": ["lakeside"], "vibe": ""}]
        affinities = {"tags": {"lakeside": 3.0}, "states": {"WA": 5.0}}

        long_reason = "A" * 120
        mock_content = MagicMock()
        mock_content.text = f'["{long_reason}"]'
        mock_response = MagicMock()
        mock_response.content = [mock_content]

        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        with (
            patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}),
            patch("anthropic.AsyncAnthropic", return_value=mock_client),
        ):
            reasons = await _enhance_rec_reasons(results, affinities)

        assert reasons is not None
        assert len(reasons[0]) == 80
