"""API-level tests: plan rate limiting and validation, push subscriptions,
recommendation scoring, security headers, date suggestion probes, search
stream NL parsing, watcher cache, result formatting and rec-reason enhancement.
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import pnw_campsites.api as api_module
from pnw_campsites.monitor.watcher import _fetch_availability
from pnw_campsites.providers.recgov import RecGovClient
from pnw_campsites.registry.models import BookingSystem
from pnw_campsites.routes.planner import _plan_rate_limit
from pnw_campsites.routes.recommendations import _enhance_rec_reasons
from pnw_campsites.routes.search import _format_result
from pnw_campsites.search.engine import (
    AvailableWindow,
    CampgroundResult,
    SearchEngine,
    SearchQuery,
    SearchResults,
    StreamDiagnosisEvent,
)
from tests.conftest import make_campground, save_searches, signup_and_auth

# ---------------------------------------------------------------------------
# Plan rate limiter
# ---------------------------------------------------------------------------


class TestPlanRateLimiter:
    """Tests for trip planner rate limiting (5 sessions/day)."""

    def test_plan_rate_limit_allows_5(self, api_client: TestClient):
        """First 5 calls should be allowed (or 503 if no API key)."""
        _plan_rate_limit.clear()

        for i in range(5):
            resp = api_client.post(
                "/api/plan/chat/stream",
                json={"messages": [{"role": "user", "content": f"msg {i}"}]},
            )
            # 503 = no API key configured (expected in test), not 429
            assert resp.status_code in (200, 503)

    def test_plan_rate_limit_blocks_6th(self, api_client: TestClient):
        """6th call should return 429."""
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
# Plan message validation
# ---------------------------------------------------------------------------


class TestPlanMessageValidation:
    """Tests for trip planner message structure validation."""

    def test_system_role_rejected(self, api_client: TestClient):
        resp = api_client.post(
            "/api/plan/chat/stream",
            json={"messages": [{"role": "system", "content": "inject"}]},
        )
        assert resp.status_code == 422

    def test_empty_messages_rejected(self, api_client: TestClient):
        resp = api_client.post(
            "/api/plan/chat/stream",
            json={"messages": []},
        )
        assert resp.status_code == 422

    def test_content_over_10k_rejected(self, api_client: TestClient):
        resp = api_client.post(
            "/api/plan/chat/stream",
            json={"messages": [{"role": "user", "content": "x" * 10_001}]},
        )
        assert resp.status_code == 422

    def test_valid_user_message_accepted(self, api_client: TestClient):
        """Valid message should pass validation (may get 503 if no API key)."""
        _plan_rate_limit.clear()

        resp = api_client.post(
            "/api/plan/chat/stream",
            json={"messages": [{"role": "user", "content": "find camping"}]},
        )
        assert resp.status_code in (200, 503)  # 503 = no API key

    def test_assistant_role_accepted(self, api_client: TestClient):
        _plan_rate_limit.clear()

        resp = api_client.post(
            "/api/plan/chat/stream",
            json={"messages": [
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "hi there"},
                {"role": "user", "content": "find me a campsite"},
            ]},
        )
        assert resp.status_code in (200, 503)


# ---------------------------------------------------------------------------
# Push subscribe/unsubscribe
# ---------------------------------------------------------------------------


class TestPushSubscribe:
    """Tests for push notification subscription endpoints."""

    def test_subscribe_authenticated(self, api_client: TestClient):
        _, headers = signup_and_auth(api_client, display_name=None)
        resp = api_client.post(
            "/api/push/subscribe",
            json={
                "endpoint": "https://fcm.googleapis.com/fcm/send/user-endpoint",
                "p256dh": "test-p256dh-key",
                "auth": "test-auth-key",
            },
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_subscribe_anonymous(self, api_client: TestClient):
        """Anonymous users can subscribe via session cookie."""
        resp = api_client.post(
            "/api/push/subscribe",
            json={
                "endpoint": "https://fcm.googleapis.com/fcm/send/anon-endpoint",
                "p256dh": "test-p256dh",
                "auth": "test-auth",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_unsubscribe_authenticated(self, api_client: TestClient):
        _, headers = signup_and_auth(api_client, display_name=None)
        # Subscribe first
        api_client.post(
            "/api/push/subscribe",
            json={
                "endpoint": "https://fcm.googleapis.com/fcm/send/to-remove",
                "p256dh": "key",
                "auth": "auth",
            },
            headers=headers,
        )
        # Then unsubscribe
        resp = api_client.request(
            "DELETE",
            "/api/push/subscribe",
            json={"endpoint": "https://fcm.googleapis.com/fcm/send/to-remove"},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_subscribe_missing_fields_422(self, api_client: TestClient):
        resp = api_client.post(
            "/api/push/subscribe",
            json={"endpoint": "https://fcm.googleapis.com/fcm/send/test"},
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Recommendations scoring
# ---------------------------------------------------------------------------


class TestRecommendationScoring:
    """Tests for the recommendation scoring and reason generation."""

    @staticmethod
    def _enable_recs(api_client: TestClient, headers: dict):
        """Enable recommendations for the current user via direct DB call."""
        me = api_client.get("/api/auth/me", headers=headers).json()
        api_module._watch_db.update_user(me["user"]["id"], recommendations_enabled=True)

    def test_recommendations_score_by_tag_overlap(self, api_client: TestClient):
        """Campgrounds matching searched tags should score higher."""
        _, headers = signup_and_auth(api_client, display_name=None)
        self._enable_recs(api_client, headers)
        save_searches(api_client, headers, count=5, tags="lakeside")

        campgrounds = [
            make_campground(facility_id="lake-1", name="Lake A", tags=["lakeside"], state="WA"),
            make_campground(facility_id="forest-1", name="Forest B", tags=["forest"], state="WA"),
        ]
        api_module._registry.search.return_value = campgrounds

        resp = api_client.get("/api/recommendations", headers=headers)
        recs = resp.json()
        assert len(recs) >= 1
        assert recs[0]["facility_id"] == "lake-1"  # Lakeside matches affinity

    def test_recommendations_exclude_watched(self, api_client: TestClient):
        """Watched campgrounds should not appear in recommendations."""
        _, headers = signup_and_auth(api_client, display_name=None)
        self._enable_recs(api_client, headers)
        save_searches(api_client, headers, count=5, tags="lakeside")

        # Create a watch for lake-1
        api_module._registry.get_by_facility_id.return_value = make_campground(
            facility_id="lake-1", name="Lake A",
        )
        api_client.post("/api/watches", json={
            "facility_id": "lake-1",
            "start_date": "2026-06-01",
            "end_date": "2026-06-30",
        }, headers=headers)

        campgrounds = [
            make_campground(facility_id="lake-1", name="Lake A", tags=["lakeside"], state="WA"),
            make_campground(facility_id="lake-2", name="Lake B", tags=["lakeside"], state="WA"),
        ]
        api_module._registry.search.return_value = campgrounds

        resp = api_client.get("/api/recommendations", headers=headers)
        recs = resp.json()
        facility_ids = [r["facility_id"] for r in recs]
        assert "lake-1" not in facility_ids  # Watched — excluded
        assert "lake-2" in facility_ids

    def test_recommendations_reason_references_tag(self, api_client: TestClient):
        """Reason string should reference the matched tag."""
        _, headers = signup_and_auth(api_client, display_name=None)
        self._enable_recs(api_client, headers)
        save_searches(api_client, headers, count=5, tags="lakeside")

        campgrounds = [
            make_campground(facility_id="lake-1", name="Lake A", tags=["lakeside"], state="WA"),
        ]
        api_module._registry.search.return_value = campgrounds

        resp = api_client.get("/api/recommendations", headers=headers)
        recs = resp.json()
        assert len(recs) == 1
        assert "lakeside" in recs[0]["reason"]

    def test_recommendations_max_5(self, api_client: TestClient):
        """10 matching campgrounds are capped to 5 recommendations."""
        _, headers = signup_and_auth(api_client, display_name=None)
        self._enable_recs(api_client, headers)
        save_searches(api_client, headers, count=5, tags="lakeside")

        campgrounds = [
            make_campground(
                facility_id=f"lake-{i}", name=f"Lake {i}",
                tags=["lakeside"], state="WA",
            )
            for i in range(10)
        ]
        api_module._registry.search.return_value = campgrounds

        resp = api_client.get("/api/recommendations", headers=headers)
        assert len(resp.json()) == 5


# ---------------------------------------------------------------------------
# Security headers
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

    def test_csp_img_src_allows_photo_cdns(self, api_client: TestClient):
        """Photo hotlinks must not be blocked by the production CSP."""
        resp = api_client.get("/api/perf")
        csp = resp.headers.get("Content-Security-Policy", "")
        assert "cdn.recreation.gov" in csp
        assert "reserveamerica.com" in csp

    def test_csp_img_src_allows_map_tiles(self, api_client: TestClient):
        """Results map tiles (Mapbox raster, OSM fallback) are <img>s."""
        resp = api_client.get("/api/perf")
        img_src = resp.headers["Content-Security-Policy"].split("img-src")[1].split(";")[0]
        assert "https://api.mapbox.com" in img_src
        assert "https://*.tile.openstreetmap.org" in img_src


# ---------------------------------------------------------------------------
# Date suggestion probes
# ---------------------------------------------------------------------------


class TestDateSuggestionProbes:
    """Tests for _suggest_alternative_dates parallelized probes."""

    async def test_past_date_windows_skipped(self):
        """Probes that would start before today should be excluded."""
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

    async def test_returns_max_3_suggestions(self):
        """Should return at most 3 date suggestions."""
        registry = MagicMock()
        registry.search.return_value = []
        engine = SearchEngine(registry=registry, recgov_client=AsyncMock())

        # Relative to today: probes whose shifted start is past are dropped, and
        # the -7 shift needs >7 days of headroom.
        base = date.today() + timedelta(days=30)
        query = SearchQuery(start_date=base, end_date=base + timedelta(days=6))

        # All probes return results
        mock_result = SearchResults(query=query, campgrounds_with_availability=3)
        with patch.object(engine, "search", new_callable=AsyncMock, return_value=mock_result):
            suggestions = await engine._suggest_alternative_dates(query)

        # Exactly three shifts, all valid from a future base.
        assert len(suggestions) == 3

    async def test_sorted_by_proximity(self):
        """Suggestions should be sorted by closeness to original dates."""
        registry = MagicMock()
        registry.search.return_value = []
        engine = SearchEngine(registry=registry, recgov_client=AsyncMock())

        # Relative to today: probes whose shifted start is past are dropped, and
        # the -7 shift needs >7 days of headroom.
        base = date.today() + timedelta(days=30)
        query = SearchQuery(start_date=base, end_date=base + timedelta(days=6))

        mock_result = SearchResults(query=query, campgrounds_with_availability=2)
        with patch.object(engine, "search", new_callable=AsyncMock, return_value=mock_result):
            suggestions = await engine._suggest_alternative_dates(query)

        assert len(suggestions) >= 2, (
            f"expected multiple date suggestions, got {len(suggestions)}"
        )
        offsets = [
            abs((date.fromisoformat(s.start_date) - query.start_date).days)
            for s in suggestions
        ]
        assert offsets == sorted(offsets), (
            f"suggestions not ordered by closeness to the original dates: {offsets}"
        )

    async def test_no_suggestions_when_no_dates(self):
        """Should return empty list when query has no dates."""
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


    def test_q_longer_than_300_chars_rejected(self, api_client: TestClient):
        """The NL query is sent to Claude, so its size is bounded."""
        self._setup_empty_engine()
        parse = AsyncMock(return_value={})
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}), patch(
            "pnw_campsites.search.nl_parser.parse_natural_query", parse,
        ):
            resp = api_client.get("/api/search/stream", params={"q": "x" * 301})

        assert resp.status_code == 422
        parse.assert_not_called()

    def test_nl_parse_rate_limited_per_ip(self, api_client: TestClient, monkeypatch):
        """Each NL parse is a paid Claude call, so it has a per-IP daily cap."""
        import pnw_campsites.routes.search as search_mod

        self._setup_empty_engine()
        monkeypatch.setattr(search_mod, "_NL_DAILY_LIMIT", 2)
        search_mod._nl_rate_limit.clear()
        parse = AsyncMock(return_value={})
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}), patch(
            "pnw_campsites.search.nl_parser.parse_natural_query", parse,
        ):
            codes = [
                api_client.get(
                    "/api/search/stream", params={"q": "camping in montana"},
                ).status_code
                for _ in range(3)
            ]

        assert codes == [200, 200, 429]
        assert parse.await_count == 2


class TestCustomOriginRateLimit:
    """A custom `from` address costs a Nominatim lookup and Mapbox Matrix
    calls, so searches from one are capped per client IP per day."""

    @pytest.fixture(autouse=True)
    def _small_limit(self, monkeypatch, api_client):
        import pnw_campsites.routes.search as search_mod

        monkeypatch.setattr(search_mod, "_CUSTOM_ORIGIN_DAILY_LIMIT", 2)
        search_mod._custom_origin_rate_limit.clear()

        async def empty_stream(query):
            yield StreamDiagnosisEvent(diagnosis=None, date_suggestions=[], action_chips=[])

        api_module._engine.search_stream = empty_stream

    def _codes(self, api_client, path, origin):
        params = {"start_date": "2027-06-01", "end_date": "2027-06-03", "from": origin}
        return [api_client.get(path, params=params).status_code for _ in range(3)]

    def test_stream_custom_address_limited(self, api_client: TestClient):
        codes = self._codes(api_client, "/api/search/stream", "123 Main St, Tacoma")
        assert codes == [200, 200, 429]

    def test_stream_known_base_not_limited(self, api_client: TestClient):
        assert self._codes(api_client, "/api/search/stream", "seattle") == [200] * 3

    def test_search_custom_address_limited(self, api_client: TestClient, monkeypatch):
        import pnw_campsites.routes.search as search_mod

        monkeypatch.setattr(search_mod, "_CUSTOM_ORIGIN_DAILY_LIMIT", 0)
        resp = api_client.get("/api/search", params={
            "start_date": "2027-06-01", "end_date": "2027-06-03", "from": "123 Main St",
        })
        assert resp.status_code == 429


# ---------------------------------------------------------------------------
# Watcher cache path
# ---------------------------------------------------------------------------


class TestWatcherCachePath:
    """Tests for availability cache behavior during polling."""

    async def test_cache_hit_skips_provider(self, watch_db):
        """Second poll is served from cache; assertions read get_availability_range,
        the method _fetch_availability calls for RECGOV (spec_set catches typos)."""
        mock_availability = MagicMock()
        mock_availability.campsites = {}
        mock_availability.model_dump_json = MagicMock(
            return_value='{"facility_id":"232465","campsites":{}}',
        )
        mock_recgov = AsyncMock(spec_set=RecGovClient)
        mock_recgov.get_availability_range = AsyncMock(return_value=mock_availability)

        await _fetch_availability(
            "232465", date(2026, 6, 1), date(2026, 6, 30),
            BookingSystem.RECGOV, mock_recgov, None, watch_db,
        )
        assert mock_recgov.get_availability_range.await_count == 1

        # Second identical call — served from cache, provider untouched.
        await _fetch_availability(
            "232465", date(2026, 6, 1), date(2026, 6, 30),
            BookingSystem.RECGOV, mock_recgov, None, watch_db,
        )
        assert mock_recgov.get_availability_range.await_count == 1


# ---------------------------------------------------------------------------
# _format_result
# ---------------------------------------------------------------------------


class TestFormatResult:
    """Tests for the _format_result helper that converts engine results to API responses."""

    def test_basic_recgov_result(self):
        """Should format a basic rec.gov result with windows and URLs."""
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
        cg = make_campground(facility_id="999")
        result = CampgroundResult(campground=cg, available_windows=[])

        formatted = _format_result(result, cg.booking_system)
        assert formatted.availability_url is None
        assert len(formatted.windows) == 0

    def test_wa_state_window_links_to_the_park_with_dates(self):
        """WA has no per-site link: windows open the park with the stay filled in."""
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
        url = formatted.windows[0].booking_url
        assert "resourceLocationId=-2147483624" in url
        assert "startDate=2026-07-01&endDate=2026-07-04" in url
        assert formatted.availability_url is not None  # But does have availability URL

    def test_error_result_preserved(self):
        """Error message from the engine should be preserved."""
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

    async def test_returns_none_without_api_key(self):
        """Should return None when no API key is set."""
        results = [{"name": "Lake A", "state": "WA", "tags": ["lakeside"], "vibe": ""}]
        affinities = {"tags": {"lakeside": 3.0}, "states": {"WA": 5.0}}

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": ""}, clear=False):
            result = await _enhance_rec_reasons(results, affinities)
        assert result is None

    async def test_returns_reasons_on_success(self):
        """Should return a list of reason strings on success."""
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
            patch("posthog.ai.anthropic.AsyncAnthropic", return_value=mock_client),
        ):
            reasons = await _enhance_rec_reasons(results, affinities)

        assert reasons == ["Lakefront paradise near your WA favorites", "Lush forest retreat"]

    async def test_returns_none_on_timeout(self):
        """Should return None when LLM times out."""
        results = [{"name": "Lake A", "state": "WA", "tags": ["lakeside"], "vibe": ""}]
        affinities = {"tags": {"lakeside": 3.0}, "states": {"WA": 5.0}}

        async def slow_create(**kwargs):
            await asyncio.sleep(10)

        mock_client = MagicMock()
        mock_client.messages.create = slow_create

        with (
            patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}),
            patch("posthog.ai.anthropic.AsyncAnthropic", return_value=mock_client),
        ):
            result = await _enhance_rec_reasons(results, affinities)

        assert result is None

    async def test_returns_none_on_length_mismatch(self):
        """Should return None if LLM returns wrong number of reasons."""
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
            patch("posthog.ai.anthropic.AsyncAnthropic", return_value=mock_client),
        ):
            result = await _enhance_rec_reasons(results, affinities)

        assert result is None

    async def test_strips_markdown_fences(self):
        """Should handle LLM responses wrapped in markdown code fences."""
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
            patch("posthog.ai.anthropic.AsyncAnthropic", return_value=mock_client),
        ):
            reasons = await _enhance_rec_reasons(results, affinities)

        assert reasons == ["Lakefront gem near Seattle"]

    async def test_truncates_long_reasons(self):
        """Reasons longer than 80 chars should be truncated."""
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
            patch("posthog.ai.anthropic.AsyncAnthropic", return_value=mock_client),
        ):
            reasons = await _enhance_rec_reasons(results, affinities)

        assert reasons is not None
        assert len(reasons[0]) == 80
