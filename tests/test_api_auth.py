"""Integration tests for auth API endpoints with Supabase JWT."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import jwt as pyjwt
import pytest
from fastapi.testclient import TestClient

import pnw_campsites.api as api_module

# Must match the secret set in conftest.py autouse fixture
_TEST_SECRET = "test-supabase-jwt-secret-that-is-at-least-32-characters"


def _make_jwt(
    supabase_id: str | None = None,
    email: str = "test@example.com",
    expired: bool = False,
    role: str = "authenticated",
    aud: str = "authenticated",
) -> str:
    sub = supabase_id or str(uuid.uuid4())
    exp = datetime.now(UTC) + (timedelta(days=-1) if expired else timedelta(hours=1))
    payload = {
        "sub": sub, "email": email, "role": role, "aud": aud,
        "exp": exp, "iat": datetime.now(UTC),
    }
    return pyjwt.encode(payload, _TEST_SECRET, algorithm="HS256")


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def client(api_client: TestClient) -> TestClient:
    return api_client


# ---------------------------------------------------------------------------
# Auto-provisioning
# ---------------------------------------------------------------------------


class TestAutoProvisioning:
    """First authenticated request creates local user."""

    def test_first_request_creates_user(self, client: TestClient):
        sub = str(uuid.uuid4())
        token = _make_jwt(supabase_id=sub, email="alice@example.com")
        resp = client.get("/api/auth/me", headers=_auth_headers(token))
        assert resp.status_code == 200
        user = resp.json()["user"]
        assert user["email"] == "alice@example.com"
        assert "id" in user

    def test_second_request_reuses_user(self, client: TestClient):
        sub = str(uuid.uuid4())
        token = _make_jwt(supabase_id=sub, email="bob@example.com")
        resp1 = client.get("/api/auth/me", headers=_auth_headers(token))
        resp2 = client.get("/api/auth/me", headers=_auth_headers(token))
        assert resp1.json()["user"]["id"] == resp2.json()["user"]["id"]

    def test_provisioned_user_has_supabase_id(self, client: TestClient):
        sub = str(uuid.uuid4())
        token = _make_jwt(supabase_id=sub)
        client.get("/api/auth/me", headers=_auth_headers(token))
        user = api_module._watch_db.get_user_by_supabase_id(sub)
        assert user is not None
        assert user.supabase_id == sub

    def test_different_supabase_ids_create_different_users(self, client: TestClient):
        token1 = _make_jwt(email="user1@example.com")
        token2 = _make_jwt(email="user2@example.com")
        resp1 = client.get("/api/auth/me", headers=_auth_headers(token1))
        resp2 = client.get("/api/auth/me", headers=_auth_headers(token2))
        assert resp1.json()["user"]["id"] != resp2.json()["user"]["id"]


# ---------------------------------------------------------------------------
# GET /api/auth/me
# ---------------------------------------------------------------------------


class TestGetMe:

    def test_valid_bearer_returns_profile(self, client: TestClient):
        token = _make_jwt(email="test@example.com")
        resp = client.get("/api/auth/me", headers=_auth_headers(token))
        assert resp.status_code == 200
        assert resp.json()["user"]["email"] == "test@example.com"

    def test_no_token_returns_401(self, client: TestClient):
        resp = client.get("/api/auth/me")
        assert resp.status_code == 401

    def test_invalid_token_returns_401(self, client: TestClient):
        resp = client.get(
            "/api/auth/me",
            headers={"Authorization": "Bearer invalid_token_xyz"},
        )
        assert resp.status_code == 401

    def test_expired_token_returns_401(self, client: TestClient):
        token = _make_jwt(expired=True)
        resp = client.get("/api/auth/me", headers=_auth_headers(token))
        assert resp.status_code == 401

    def test_deleted_user_returns_401(self, client: TestClient):
        sub = str(uuid.uuid4())
        token = _make_jwt(supabase_id=sub)
        # Provision user
        resp = client.get("/api/auth/me", headers=_auth_headers(token))
        user_id = resp.json()["user"]["id"]
        # Delete from DB
        api_module._watch_db.delete_user(user_id)
        # Next request re-provisions (auto-provisioning creates new user)
        resp2 = client.get("/api/auth/me", headers=_auth_headers(token))
        assert resp2.status_code == 200
        assert resp2.json()["user"]["id"] != user_id

    def test_response_includes_all_fields(self, client: TestClient):
        token = _make_jwt(email="fields@example.com")
        resp = client.get("/api/auth/me", headers=_auth_headers(token))
        user = resp.json()["user"]
        expected_fields = {
            "id", "email", "display_name", "home_base",
            "default_state", "default_nights", "default_from",
            "recommendations_enabled", "preferred_tags", "onboarding_complete",
        }
        assert expected_fields <= set(user.keys())


# ---------------------------------------------------------------------------
# PATCH /api/auth/me
# ---------------------------------------------------------------------------


class TestUpdateMe:

    def test_update_display_name(self, client: TestClient):
        token = _make_jwt()
        client.get("/api/auth/me", headers=_auth_headers(token))
        resp = client.patch(
            "/api/auth/me",
            json={"display_name": "New Name"},
            headers=_auth_headers(token),
        )
        assert resp.status_code == 200
        assert resp.json()["user"]["display_name"] == "New Name"

    def test_update_multiple_fields(self, client: TestClient):
        token = _make_jwt()
        client.get("/api/auth/me", headers=_auth_headers(token))
        resp = client.patch(
            "/api/auth/me",
            json={
                "home_base": "Seattle, WA",
                "default_state": "WA",
                "default_nights": 3,
            },
            headers=_auth_headers(token),
        )
        assert resp.status_code == 200
        user = resp.json()["user"]
        assert user["home_base"] == "Seattle, WA"
        assert user["default_state"] == "WA"
        assert user["default_nights"] == 3

    def test_without_auth_returns_401(self, client: TestClient):
        resp = client.patch("/api/auth/me", json={"display_name": "Nope"})
        assert resp.status_code == 401

    def test_ignores_none_fields(self, client: TestClient):
        token = _make_jwt()
        client.get("/api/auth/me", headers=_auth_headers(token))
        client.patch(
            "/api/auth/me",
            json={"display_name": "Original"},
            headers=_auth_headers(token),
        )
        resp = client.patch(
            "/api/auth/me",
            json={"display_name": None, "home_base": "Portland"},
            headers=_auth_headers(token),
        )
        user = resp.json()["user"]
        assert user["display_name"] == "Original"
        assert user["home_base"] == "Portland"


# ---------------------------------------------------------------------------
# DELETE /api/auth/me
# ---------------------------------------------------------------------------


class TestDeleteMe:

    @patch("pnw_campsites.routes.auth._delete_supabase_user", new_callable=AsyncMock)
    def test_delete_removes_user(self, mock_delete, client: TestClient):
        sub = str(uuid.uuid4())
        token = _make_jwt(supabase_id=sub)
        client.get("/api/auth/me", headers=_auth_headers(token))
        user_id = client.get("/api/auth/me", headers=_auth_headers(token)).json()["user"]["id"]

        resp = client.delete("/api/auth/me", headers=_auth_headers(token))
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

        # Verify local user is deleted
        assert api_module._watch_db.get_user_by_id(user_id) is None
        # Verify Supabase admin delete was called
        mock_delete.assert_called_once_with(sub)

    def test_without_auth_returns_401(self, client: TestClient):
        resp = client.delete("/api/auth/me")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Anonymous watch migration
# ---------------------------------------------------------------------------


class TestAnonymousWatchMigration:

    def test_anonymous_watches_migrate_on_first_auth(self, client: TestClient):
        """Anonymous watches migrate to user on first authenticated request."""
        # Create anonymous watch
        watch_resp = client.post(
            "/api/watches",
            json={
                "facility_id": "333333",
                "name": "Anonymous Watch",
                "start_date": "2026-06-01",
                "end_date": "2026-06-15",
            },
        )
        assert watch_resp.status_code == 200
        watch_id = watch_resp.json()["id"]

        # Verify watch is anonymous
        watch_before = api_module._watch_db.get_watch(watch_id)
        assert watch_before.session_token != ""
        assert watch_before.user_id is None

        # Authenticate (first request triggers auto-provisioning + migration)
        token = _make_jwt(email="migrator@example.com")
        resp = client.get("/api/auth/me", headers=_auth_headers(token))
        user_id = resp.json()["user"]["id"]

        # Verify watch is now owned by user
        watch_after = api_module._watch_db.get_watch(watch_id)
        assert watch_after.user_id == user_id
        assert watch_after.session_token == ""

    def test_multiple_anonymous_watches_all_migrate(self, client: TestClient):
        """All anonymous watches from the session migrate together."""
        watch_ids = []
        for i in range(3):
            resp = client.post(
                "/api/watches",
                json={
                    "facility_id": f"555{i}",
                    "name": f"Watch {i}",
                    "start_date": "2026-06-01",
                    "end_date": "2026-06-15",
                },
            )
            watch_ids.append(resp.json()["id"])

        token = _make_jwt(email="multi@example.com")
        resp = client.get("/api/auth/me", headers=_auth_headers(token))
        user_id = resp.json()["user"]["id"]

        for watch_id in watch_ids:
            watch = api_module._watch_db.get_watch(watch_id)
            assert watch.user_id == user_id
            assert watch.session_token == ""

    def test_migration_is_idempotent(self, client: TestClient):
        """Second auth request doesn't break already-migrated watches."""
        watch_resp = client.post(
            "/api/watches",
            json={
                "facility_id": "666666",
                "name": "Idempotent Watch",
                "start_date": "2026-06-01",
                "end_date": "2026-06-15",
            },
        )
        watch_id = watch_resp.json()["id"]

        token = _make_jwt()
        # First auth — migrates
        client.get("/api/auth/me", headers=_auth_headers(token))
        # Second auth — should not break
        resp = client.get("/api/auth/me", headers=_auth_headers(token))
        assert resp.status_code == 200

        watch = api_module._watch_db.get_watch(watch_id)
        assert watch.user_id is not None


# ---------------------------------------------------------------------------
# Auth + watches integration
# ---------------------------------------------------------------------------


class TestAuthWithWatches:

    def test_authenticated_user_creates_owned_watch(self, client: TestClient):
        token = _make_jwt()
        resp = client.get("/api/auth/me", headers=_auth_headers(token))
        user_id = resp.json()["user"]["id"]

        watch_resp = client.post(
            "/api/watches",
            json={
                "facility_id": "123456",
                "name": "My Watch",
                "start_date": "2026-06-01",
                "end_date": "2026-06-15",
                "min_nights": 2,
            },
            headers=_auth_headers(token),
        )
        assert watch_resp.status_code == 200
        watch_id = watch_resp.json()["id"]

        stored = api_module._watch_db.get_watch(watch_id)
        assert stored.user_id == user_id
        assert stored.session_token == ""

    def test_user_cannot_delete_others_watch(self, client: TestClient):
        # User A creates a watch
        token_a = _make_jwt(email="a@example.com")
        client.get("/api/auth/me", headers=_auth_headers(token_a))
        watch_resp = client.post(
            "/api/watches",
            json={
                "facility_id": "222222",
                "name": "User A Watch",
                "start_date": "2026-06-01",
                "end_date": "2026-06-15",
            },
            headers=_auth_headers(token_a),
        )
        watch_id = watch_resp.json()["id"]

        # User B tries to delete it
        token_b = _make_jwt(email="b@example.com")
        client.get("/api/auth/me", headers=_auth_headers(token_b))
        del_resp = client.delete(
            f"/api/watches/{watch_id}",
            headers=_auth_headers(token_b),
        )
        assert del_resp.json()["ok"] is False

        # Watch still exists
        assert api_module._watch_db.get_watch(watch_id) is not None
