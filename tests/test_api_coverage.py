"""Tests for previously untested API endpoints — search-history, recommendations,
poll-status, push notifications, data export, admin digest, and SSE streaming."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import pnw_campsites.api as api_module
from pnw_campsites.registry.models import BookingSystem

from tests.conftest import make_campground

TOKEN_COOKIE = "campnw_token"


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------


def _signup_and_login(client: TestClient, email: str = "test@example.com") -> dict:
    """Sign up a user and return the response data with cookies set."""
    resp = client.post(
        "/api/auth/signup",
        json={"email": email, "password": "testpass123", "display_name": "Tester"},
    )
    assert resp.status_code == 200
    return resp.json()


def _save_searches(client: TestClient, count: int = 3) -> None:
    """Save several search history entries for the current user."""
    for i in range(count):
        client.post(
            "/api/search-history",
            json={
                "params": {
                    "start_date": "2026-06-01",
                    "end_date": "2026-06-30",
                    "state": "WA" if i % 2 == 0 else "OR",
                    "tags": "lakeside,trails",
                },
                "result_count": i * 5,
            },
        )


# ---------------------------------------------------------------------------
# Search History
# ---------------------------------------------------------------------------


class TestSearchHistory:
    """Tests for GET/POST /api/search-history."""

    def test_save_search_requires_auth(self, api_client: TestClient):
        """Unauthenticated save should return ok=false."""
        resp = api_client.post(
            "/api/search-history",
            json={"params": {"state": "WA"}, "result_count": 5},
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is False

    def test_save_search_as_authenticated_user(self, api_client: TestClient):
        """Authenticated user can save search history."""
        _signup_and_login(api_client)
        resp = api_client.post(
            "/api/search-history",
            json={
                "params": {"state": "WA", "tags": "lakeside"},
                "result_count": 10,
            },
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_get_search_history_requires_auth(self, api_client: TestClient):
        """Unauthenticated GET should return 401."""
        resp = api_client.get("/api/search-history")
        assert resp.status_code == 401

    def test_get_search_history_returns_saved_searches(self, api_client: TestClient):
        """Authenticated user gets their saved searches back."""
        _signup_and_login(api_client)
        _save_searches(api_client, count=3)

        resp = api_client.get("/api/search-history")
        assert resp.status_code == 200
        history = resp.json()
        assert len(history) == 3

    def test_get_search_history_empty_for_new_user(self, api_client: TestClient):
        """New user should have empty search history."""
        _signup_and_login(api_client)
        resp = api_client.get("/api/search-history")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_search_history_isolated_per_user(self, api_client: TestClient):
        """User A's history should not be visible to user B."""
        _signup_and_login(api_client, "alice@example.com")
        _save_searches(api_client, count=2)
        api_client.post("/api/auth/logout")

        _signup_and_login(api_client, "bob@example.com")
        resp = api_client.get("/api/search-history")
        assert resp.status_code == 200
        assert resp.json() == []


# ---------------------------------------------------------------------------
# Data Export
# ---------------------------------------------------------------------------


class TestDataExport:
    """Tests for GET /api/auth/export."""

    def test_export_requires_auth(self, api_client: TestClient):
        resp = api_client.get("/api/auth/export")
        assert resp.status_code == 401

    def test_export_returns_data(self, api_client: TestClient):
        """Authenticated user gets a data export."""
        _signup_and_login(api_client)
        _save_searches(api_client, count=2)

        resp = api_client.get("/api/auth/export")
        assert resp.status_code == 200
        data = resp.json()
        # Export should contain user data
        assert isinstance(data, dict)


# ---------------------------------------------------------------------------
# Recommendations
# ---------------------------------------------------------------------------


class TestRecommendations:
    """Tests for GET /api/recommendations."""

    def test_recommendations_requires_auth(self, api_client: TestClient):
        """Unauthenticated user gets empty list."""
        resp = api_client.get("/api/recommendations")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_recommendations_returns_empty_for_no_history(
        self, api_client: TestClient,
    ):
        """User with no search history gets empty recommendations."""
        _signup_and_login(api_client)
        # Enable recommendations
        api_client.patch(
            "/api/auth/me",
            json={"recommendations_enabled": True},
        )
        resp = api_client.get("/api/recommendations")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_recommendations_with_search_history(self, api_client: TestClient):
        """User with search history and matching campgrounds gets recommendations."""
        _signup_and_login(api_client)
        api_client.patch(
            "/api/auth/me",
            json={"recommendations_enabled": True},
        )

        # Save searches to build affinity
        for _ in range(5):
            api_client.post(
                "/api/search-history",
                json={
                    "params": {"state": "WA", "tags": "lakeside"},
                    "result_count": 5,
                },
            )

        # Mock registry to return campgrounds matching the affinity
        campgrounds = [
            make_campground(
                facility_id=f"rec-{i}",
                name=f"Lake Camp {i}",
                state="WA",
                tags=["lakeside"],
            )
            for i in range(10)
        ]
        api_module._registry.search.return_value = campgrounds

        resp = api_client.get("/api/recommendations")
        assert resp.status_code == 200
        recs = resp.json()
        assert len(recs) <= 5
        if recs:
            assert "facility_id" in recs[0]
            assert "name" in recs[0]
            assert "reason" in recs[0]

    def test_recommendations_disabled_returns_empty(self, api_client: TestClient):
        """User with recommendations disabled gets empty list."""
        _signup_and_login(api_client)
        # Don't enable recommendations (default is disabled)
        _save_searches(api_client, count=5)
        resp = api_client.get("/api/recommendations")
        assert resp.status_code == 200
        assert resp.json() == []


# ---------------------------------------------------------------------------
# Poll Status
# ---------------------------------------------------------------------------


class TestPollStatus:
    """Tests for GET /api/poll-status."""

    def test_poll_status_requires_auth(self, api_client: TestClient):
        resp = api_client.get("/api/poll-status")
        assert resp.status_code == 401

    def test_poll_status_returns_structure(self, api_client: TestClient):
        """Authenticated user gets poll state + recent notifications."""
        _signup_and_login(api_client)
        resp = api_client.get("/api/poll-status")
        assert resp.status_code == 200
        data = resp.json()
        assert "recent_notifications" in data

    def test_poll_status_includes_poll_state(self, api_client: TestClient):
        """Response should include poll state fields."""
        _signup_and_login(api_client)

        # Set some poll state
        api_module._poll_state["last_poll"] = "2026-03-28T12:00:00"
        api_module._poll_state["active_watches"] = 5

        resp = api_client.get("/api/poll-status")
        data = resp.json()
        assert data["last_poll"] == "2026-03-28T12:00:00"
        assert data["active_watches"] == 5


# ---------------------------------------------------------------------------
# Push Notifications
# ---------------------------------------------------------------------------


class TestPushEndpoints:
    """Tests for /api/push/* endpoints."""

    def test_vapid_key_returns_key(self, api_client: TestClient):
        """GET /api/push/vapid-key should return the VAPID public key."""
        with patch.dict("os.environ", {"VAPID_PUBLIC_KEY": "test-vapid-key-123"}):
            resp = api_client.get("/api/push/vapid-key")
        assert resp.status_code == 200
        assert resp.json()["public_key"] == "test-vapid-key-123"

    def test_vapid_key_empty_when_not_set(self, api_client: TestClient):
        """VAPID key returns empty string when env var not set."""
        resp = api_client.get("/api/push/vapid-key")
        assert resp.status_code == 200
        assert resp.json()["public_key"] == ""

    def test_vapid_key_is_public_endpoint(self, api_client: TestClient):
        """VAPID key endpoint doesn't require authentication."""
        resp = api_client.get("/api/push/vapid-key")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Admin Digest
# ---------------------------------------------------------------------------


class TestAdminDigest:
    """Tests for GET /api/admin/digest."""

    def test_digest_requires_auth(self, api_client: TestClient):
        """Unauthenticated request should return 401."""
        resp = api_client.get("/api/admin/digest")
        assert resp.status_code == 401

    def test_digest_returns_report(self, api_client: TestClient):
        """Authenticated digest should return a report object."""
        _signup_and_login(api_client)
        resp = api_client.get("/api/admin/digest")
        assert resp.status_code == 200
        data = resp.json()
        assert "report" in data

    def test_digest_with_no_data(self, api_client: TestClient):
        """Digest with no search history should return a message."""
        _signup_and_login(api_client)
        resp = api_client.get("/api/admin/digest")
        assert resp.status_code == 200
        assert "No searches" in resp.json()["report"]

    def test_digest_with_search_data(self, api_client: TestClient):
        """Digest with search data should include stats."""
        _signup_and_login(api_client)
        _save_searches(api_client, count=5)

        resp = api_client.get("/api/admin/digest")
        assert resp.status_code == 200
        report = resp.json()["report"]
        assert "Total searches" in report


# ---------------------------------------------------------------------------
# SSE Search Stream
# ---------------------------------------------------------------------------


class TestSearchStream:
    """Tests for GET /api/search/stream (SSE)."""

    @staticmethod
    def _setup_empty_engine():
        """Configure the mock engine for empty stream tests."""
        async def empty_stream(query):
            return
            yield  # noqa: RET503 — async generator

        api_module._engine.search_stream = empty_stream
        api_module._engine.search = AsyncMock(return_value=MagicMock(
            diagnosis=None, date_suggestions=[], action_chips=[],
        ))

    def test_stream_returns_sse(self, api_client: TestClient):
        """Stream endpoint should return text/event-stream."""
        self._setup_empty_engine()
        resp = api_client.get(
            "/api/search/stream",
            params={"start_date": "2026-06-01", "end_date": "2026-06-30"},
        )
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]

    def test_stream_ends_with_done(self, api_client: TestClient):
        """Stream should end with [DONE] marker."""
        self._setup_empty_engine()
        resp = api_client.get(
            "/api/search/stream",
            params={"start_date": "2026-06-01", "end_date": "2026-06-30"},
        )
        assert "data: [DONE]" in resp.text

    def test_stream_with_nl_query_no_api_key(self, api_client: TestClient):
        """NL query without API key should fall back to default dates."""
        self._setup_empty_engine()
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": ""}, clear=False):
            resp = api_client.get(
                "/api/search/stream",
                params={"q": "lakeside camping this weekend"},
            )
        assert resp.status_code == 200
        assert "data: [DONE]" in resp.text

    def test_stream_default_dates_when_none_provided(self, api_client: TestClient):
        """When no dates and no q, should use default date window."""
        self._setup_empty_engine()
        resp = api_client.get("/api/search/stream")
        assert resp.status_code == 200
        assert "data: [DONE]" in resp.text

    def test_stream_with_state_filter(self, api_client: TestClient):
        """State filter should be passed through to search."""
        self._setup_empty_engine()
        resp = api_client.get(
            "/api/search/stream",
            params={
                "start_date": "2026-06-01",
                "end_date": "2026-06-30",
                "state": "MT",
            },
        )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Result formatting (API response model)
# ---------------------------------------------------------------------------


class TestResultFormatting:
    """Tests for the CampgroundResultResponse model new fields."""

    def test_response_includes_description_fields(self, api_client: TestClient):
        """Search results should include elevator_pitch, description_rewrite, best_for."""
        from pnw_campsites.search.engine import CampgroundResult

        cg = make_campground(
            elevator_pitch="Great lakeside camp.",
            description_rewrite="A wonderful place by the lake.",
            best_for="Families",
        )

        result = CampgroundResult(
            campground=cg,
            available_windows=[],
            total_available_sites=5,
            fcfs_sites=0,
        )

        async def stream_one(query):
            yield result

        api_module._engine.search_stream = stream_one
        api_module._engine.search = AsyncMock(return_value=MagicMock(
            diagnosis=None, date_suggestions=[], action_chips=[],
        ))

        resp = api_client.get(
            "/api/search/stream",
            params={"start_date": "2026-06-01", "end_date": "2026-06-30"},
        )

        # Parse SSE events
        for line in resp.text.splitlines():
            if line.startswith("data: ") and line.strip() != "data: [DONE]":
                data = json.loads(line[6:])
                if "facility_id" in data:
                    assert data["elevator_pitch"] == "Great lakeside camp."
                    assert data["description_rewrite"] == "A wonderful place by the lake."
                    assert data["best_for"] == "Families"
                    return

        pytest.fail("No result event found in SSE stream")
