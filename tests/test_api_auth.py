"""Integration tests for auth API endpoints."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import pnw_campsites.api as api_module
from pnw_campsites.auth import TOKEN_COOKIE
from pnw_campsites.monitor.db import WatchDB


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    """FastAPI TestClient with temp WatchDB."""
    # Patch sqlite3.connect to disable thread check for testing
    original_connect = sqlite3.connect

    def patched_connect(path, *args, **kwargs):
        kwargs.setdefault("check_same_thread", False)
        return original_connect(path, *args, **kwargs)

    with patch("sqlite3.connect", patched_connect):
        # Create fresh DB for this test
        db_path = tmp_path / "test_watches.db"
        db = WatchDB(db_path)

        # Patch module-level globals
        api_module._watch_db = db
        registry_mock = MagicMock()
        registry_mock.get_by_facility_id.return_value = None
        api_module._registry = registry_mock

        # Create TestClient with base_url that uses https to satisfy secure=True
        test_client = TestClient(
            api_module.app,
            raise_server_exceptions=True,
            base_url="https://testserver",
        )

        yield test_client

        # Cleanup
        db.close()


class TestSignup:
    """Tests for POST /api/auth/signup."""

    def test_signup_creates_user_and_sets_cookie(self, client: TestClient):
        """Signup should create user and set token cookie."""
        response = client.post(
            "/api/auth/signup",
            json={
                "email": "alice@example.com",
                "password": "secure_pass_123",
                "display_name": "Alice",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["user"]["email"] == "alice@example.com"
        assert data["user"]["display_name"] == "Alice"
        assert "id" in data["user"]

        # Verify token cookie is set
        assert TOKEN_COOKIE in response.cookies
        token = response.cookies[TOKEN_COOKIE]
        assert token  # Non-empty

        # Verify user can be retrieved from DB
        user = api_module._watch_db.get_user_by_email("alice@example.com")
        assert user is not None
        assert user.email == "alice@example.com"

    def test_signup_with_duplicate_email_returns_409(self, client: TestClient):
        """Signup with existing email should return 409 Conflict."""
        # First signup
        client.post(
            "/api/auth/signup",
            json={
                "email": "bob@example.com",
                "password": "secure_pass_123",
            },
        )

        # Duplicate email
        response = client.post(
            "/api/auth/signup",
            json={
                "email": "bob@example.com",
                "password": "different_pass_123",
            },
        )

        assert response.status_code == 409
        assert "Email already registered" in response.json()["detail"]

    def test_signup_with_short_password_returns_422(self, client: TestClient):
        """Signup with password < 8 chars should return 422."""
        response = client.post(
            "/api/auth/signup",
            json={
                "email": "charlie@example.com",
                "password": "short",
            },
        )

        assert response.status_code == 422

    def test_signup_with_invalid_email_returns_422(self, client: TestClient):
        """Signup with invalid email should return 422."""
        response = client.post(
            "/api/auth/signup",
            json={
                "email": "not-an-email",
                "password": "secure_pass_123",
            },
        )

        assert response.status_code == 422

    def test_signup_response_includes_all_user_fields(
        self, client: TestClient
    ):
        """Signup response should include all expected user fields."""
        response = client.post(
            "/api/auth/signup",
            json={
                "email": "dave@example.com",
                "password": "secure_pass_123",
                "display_name": "Dave",
            },
        )

        user = response.json()["user"]
        assert "id" in user
        assert "email" in user
        assert "display_name" in user
        assert "home_base" in user
        assert "default_state" in user
        assert "default_nights" in user
        assert "default_from" in user


class TestLogin:
    """Tests for POST /api/auth/login."""

    def test_login_with_valid_credentials_returns_user_and_cookie(
        self, client: TestClient
    ):
        """Login with correct password should return user and set cookie."""
        # Create user first
        signup_response = client.post(
            "/api/auth/signup",
            json={
                "email": "eve@example.com",
                "password": "my_password_123",
            },
        )
        assert signup_response.status_code == 200

        # Login
        login_response = client.post(
            "/api/auth/login",
            json={
                "email": "eve@example.com",
                "password": "my_password_123",
            },
        )

        assert login_response.status_code == 200
        user = login_response.json()["user"]
        assert user["email"] == "eve@example.com"

        # Verify cookie is set
        assert TOKEN_COOKIE in login_response.cookies

    def test_login_with_wrong_password_returns_401(self, client: TestClient):
        """Login with incorrect password should return 401."""
        # Create user
        client.post(
            "/api/auth/signup",
            json={
                "email": "frank@example.com",
                "password": "correct_password_123",
            },
        )

        # Login with wrong password
        response = client.post(
            "/api/auth/login",
            json={
                "email": "frank@example.com",
                "password": "wrong_password_123",
            },
        )

        assert response.status_code == 401
        assert "Invalid email or password" in response.json()["detail"]

    def test_login_with_nonexistent_email_returns_401(self, client: TestClient):
        """Login with non-existent email should return 401."""
        response = client.post(
            "/api/auth/login",
            json={
                "email": "nonexistent@example.com",
                "password": "any_password_123",
            },
        )

        assert response.status_code == 401
        assert "Invalid email or password" in response.json()["detail"]

    def test_login_with_case_insensitive_email(self, client: TestClient):
        """Login should be case-insensitive for email."""
        # Create user with lowercase
        client.post(
            "/api/auth/signup",
            json={
                "email": "grace@example.com",
                "password": "password_123",
            },
        )

        # Login with uppercase
        response = client.post(
            "/api/auth/login",
            json={
                "email": "GRACE@EXAMPLE.COM",
                "password": "password_123",
            },
        )

        assert response.status_code == 200
        assert response.json()["user"]["email"] == "grace@example.com"


class TestGetMe:
    """Tests for GET /api/auth/me."""

    def test_get_me_with_valid_cookie_returns_user(self, client: TestClient):
        """GET /me with valid token cookie should return user."""
        # Sign up and get token
        signup = client.post(
            "/api/auth/signup",
            json={
                "email": "henry@example.com",
                "password": "password_123",
                "display_name": "Henry",
            },
        )
        assert signup.status_code == 200

        # TestClient should auto-persist cookies from signup
        response = client.get("/api/auth/me")
        assert response.status_code == 200, response.text
        user = response.json()["user"]
        assert user["email"] == "henry@example.com"
        assert user["display_name"] == "Henry"

    def test_get_me_without_cookie_returns_401(self, client: TestClient):
        """GET /me without auth cookie should return 401."""
        response = client.get("/api/auth/me")
        assert response.status_code == 401
        assert "Not authenticated" in response.json()["detail"]

    def test_get_me_with_invalid_token_returns_401(self, client: TestClient):
        """GET /me with invalid token cookie should return 401."""
        client.cookies.set(TOKEN_COOKIE, "invalid_token_xyz")
        response = client.get("/api/auth/me")
        assert response.status_code == 401

    def test_get_me_after_user_deleted_returns_401(self, client: TestClient):
        """GET /me should return 401 if user was deleted."""
        # Signup and get ID
        signup = client.post(
            "/api/auth/signup",
            json={
                "email": "iris@example.com",
                "password": "password_123",
            },
        )
        user_id = signup.json()["user"]["id"]

        # Manually delete user from DB
        api_module._watch_db.delete_user(user_id)

        # GET /me should now fail
        response = client.get("/api/auth/me")
        assert response.status_code == 401


class TestUpdateMe:
    """Tests for PATCH /api/auth/me."""

    def test_update_me_updates_display_name(self, client: TestClient):
        """PATCH /me should update display_name."""
        client.post(
            "/api/auth/signup",
            json={
                "email": "jack@example.com",
                "password": "password_123",
                "display_name": "Jack",
            },
        )

        response = client.patch(
            "/api/auth/me",
            json={"display_name": "Jack the Ripper"},
        )

        assert response.status_code == 200
        assert response.json()["user"]["display_name"] == "Jack the Ripper"

    def test_update_me_updates_home_base(self, client: TestClient):
        """PATCH /me should update home_base."""
        client.post(
            "/api/auth/signup",
            json={
                "email": "karen@example.com",
                "password": "password_123",
            },
        )

        response = client.patch(
            "/api/auth/me",
            json={"home_base": "Seattle, WA"},
        )

        assert response.status_code == 200
        assert response.json()["user"]["home_base"] == "Seattle, WA"

    def test_update_me_without_auth_returns_401(self, client: TestClient):
        """PATCH /me without auth should return 401."""
        response = client.patch(
            "/api/auth/me",
            json={"display_name": "Unauthorized"},
        )

        assert response.status_code == 401

    def test_update_me_with_multiple_fields(self, client: TestClient):
        """PATCH /me should update multiple fields at once."""
        client.post(
            "/api/auth/signup",
            json={
                "email": "liam@example.com",
                "password": "password_123",
            },
        )

        response = client.patch(
            "/api/auth/me",
            json={
                "display_name": "Liam Updated",
                "home_base": "Portland, OR",
                "default_state": "OR",
                "default_nights": 3,
            },
        )

        assert response.status_code == 200
        user = response.json()["user"]
        assert user["display_name"] == "Liam Updated"
        assert user["home_base"] == "Portland, OR"
        assert user["default_state"] == "OR"
        assert user["default_nights"] == 3

    def test_update_me_ignores_none_fields(self, client: TestClient):
        """PATCH /me should ignore None fields."""
        client.post(
            "/api/auth/signup",
            json={
                "email": "mia@example.com",
                "password": "password_123",
                "display_name": "Mia Original",
            },
        )

        response = client.patch(
            "/api/auth/me",
            json={
                "display_name": None,
                "home_base": "New Base",
            },
        )

        assert response.status_code == 200
        user = response.json()["user"]
        # display_name should remain unchanged
        assert user["display_name"] == "Mia Original"
        # home_base should be updated
        assert user["home_base"] == "New Base"


class TestLogout:
    """Tests for POST /api/auth/logout."""

    def test_logout_clears_cookie(self, client: TestClient):
        """POST /logout should clear token cookie."""
        # Login
        client.post(
            "/api/auth/signup",
            json={
                "email": "noah@example.com",
                "password": "password_123",
            },
        )

        # Logout
        response = client.post("/api/auth/logout")
        assert response.status_code == 200
        assert response.json()["ok"] is True

        # Cookie should be cleared from client jar
        assert TOKEN_COOKIE not in client.cookies

    def test_after_logout_me_returns_401(self, client: TestClient):
        """After logout, GET /me should return 401."""
        client.post(
            "/api/auth/signup",
            json={
                "email": "olivia@example.com",
                "password": "password_123",
            },
        )

        client.post("/api/auth/logout")

        response = client.get("/api/auth/me")
        assert response.status_code == 401


class TestDeleteMe:
    """Tests for DELETE /api/auth/me."""

    def test_delete_me_deletes_user_and_clears_cookie(self, client: TestClient):
        """DELETE /me should delete user and clear cookie."""
        signup = client.post(
            "/api/auth/signup",
            json={
                "email": "peter@example.com",
                "password": "password_123",
            },
        )
        user_id = signup.json()["user"]["id"]

        response = client.delete("/api/auth/me")
        assert response.status_code == 200
        assert response.json()["ok"] is True

        # Verify user is deleted from DB
        user = api_module._watch_db.get_user_by_id(user_id)
        assert user is None

        # Cookie should be cleared from client jar
        assert TOKEN_COOKIE not in client.cookies

    def test_delete_me_without_auth_returns_401(self, client: TestClient):
        """DELETE /me without auth should return 401."""
        response = client.delete("/api/auth/me")
        assert response.status_code == 401

    def test_after_delete_me_subsequent_calls_return_401(
        self, client: TestClient
    ):
        """After DELETE /me, subsequent auth calls should return 401."""
        client.post(
            "/api/auth/signup",
            json={
                "email": "quinn@example.com",
                "password": "password_123",
            },
        )

        client.delete("/api/auth/me")

        # GET /me should now fail
        response = client.get("/api/auth/me")
        assert response.status_code == 401


class TestAuthWithWatches:
    """Integration tests: Auth + watches."""

    def test_create_watch_as_authenticated_user(self, client: TestClient):
        """Authenticated user can create watch and it's owned by user."""
        # Signup
        signup = client.post(
            "/api/auth/signup",
            json={
                "email": "romeo@example.com",
                "password": "password_123",
            },
        )
        user_id = signup.json()["user"]["id"]

        # Create watch
        watch_response = client.post(
            "/api/watches",
            json={
                "facility_id": "123456",
                "name": "Test Campground",
                "start_date": "2026-06-01",
                "end_date": "2026-06-15",
                "min_nights": 2,
            },
        )

        assert watch_response.status_code == 200
        watch = watch_response.json()
        watch_id = watch["id"]

        # Verify watch is owned by user
        stored_watch = api_module._watch_db.get_watch(watch_id)
        assert stored_watch.user_id == user_id
        assert stored_watch.session_token == ""

    def test_list_watches_returns_only_user_watches(self, client: TestClient):
        """List watches should return only authenticated user's watches."""
        # User A signup and create watch
        client.post(
            "/api/auth/signup",
            json={
                "email": "sierra@example.com",
                "password": "password_123",
            },
        )

        watch_a = client.post(
            "/api/watches",
            json={
                "facility_id": "111111",
                "name": "Watch A",
                "start_date": "2026-06-01",
                "end_date": "2026-06-15",
            },
        )
        assert watch_a.status_code == 200

        # List watches for user A
        list_response = client.get("/api/watches")
        assert list_response.status_code == 200
        watches = list_response.json()
        assert len(watches) == 1
        assert watches[0]["facility_id"] == "111111"

    def test_cannot_delete_others_watch(self, client: TestClient):
        """User should not be able to delete another user's watch."""
        # User A: signup and create watch
        client.post(
            "/api/auth/signup",
            json={
                "email": "tina@example.com",
                "password": "password_123",
            },
        )

        watch_response = client.post(
            "/api/watches",
            json={
                "facility_id": "222222",
                "name": "Tina's Watch",
                "start_date": "2026-06-01",
                "end_date": "2026-06-15",
            },
        )
        watch_id = watch_response.json()["id"]

        # User B: signup
        client.post("/api/auth/logout")  # Logout A
        client.post(
            "/api/auth/signup",
            json={
                "email": "uma@example.com",
                "password": "password_123",
            },
        )

        # User B tries to delete A's watch
        delete_response = client.delete(f"/api/watches/{watch_id}")
        assert delete_response.status_code == 200
        assert delete_response.json()["ok"] is False

        # Watch should still exist
        stored = api_module._watch_db.get_watch(watch_id)
        assert stored is not None


class TestAnonymousWatchMigration:
    """Integration tests: Anonymous watches → Authenticated user."""

    def test_migrate_anonymous_watches_on_signup(self, client: TestClient):
        """Anonymous watches should migrate to user on signup."""
        # Create anonymous watch (no auth)
        watch1 = client.post(
            "/api/watches",
            json={
                "facility_id": "333333",
                "name": "Anonymous Watch",
                "start_date": "2026-06-01",
                "end_date": "2026-06-15",
            },
        )
        assert watch1.status_code == 200
        watch1_id = watch1.json()["id"]

        # Verify watch is anonymous (has session token)
        watch_before = api_module._watch_db.get_watch(watch1_id)
        assert watch_before.session_token != ""
        assert watch_before.user_id is None

        # Signup
        signup = client.post(
            "/api/auth/signup",
            json={
                "email": "victor@example.com",
                "password": "password_123",
            },
        )
        user_id = signup.json()["user"]["id"]

        # Verify watch is now owned by user
        watch_after = api_module._watch_db.get_watch(watch1_id)
        assert watch_after.user_id == user_id
        assert watch_after.session_token == ""

    def test_migrate_anonymous_watches_on_login(self, client: TestClient):
        """Anonymous watches should migrate to user on login."""
        # Create user first
        signup_resp = client.post(
            "/api/auth/signup",
            json={
                "email": "walker@example.com",
                "password": "password_123",
            },
        )
        user_id = signup_resp.json()["user"]["id"]

        # Logout
        client.post("/api/auth/logout")

        # Create anonymous watch
        watch = client.post(
            "/api/watches",
            json={
                "facility_id": "444444",
                "name": "Anon Watch for Login",
                "start_date": "2026-06-01",
                "end_date": "2026-06-15",
            },
        )
        watch_id = watch.json()["id"]

        # Verify it's anonymous
        watch_before = api_module._watch_db.get_watch(watch_id)
        assert watch_before.user_id is None

        # Login with existing user
        client.post(
            "/api/auth/login",
            json={
                "email": "walker@example.com",
                "password": "password_123",
            },
        )

        # Verify watch is now owned by user
        watch_after = api_module._watch_db.get_watch(watch_id)
        assert watch_after.user_id == user_id

    def test_multiple_anonymous_watches_all_migrate(self, client: TestClient):
        """All anonymous watches should migrate to user on signup."""
        # Create multiple anonymous watches
        watch_ids = []
        for i in range(3):
            response = client.post(
                "/api/watches",
                json={
                    "facility_id": f"555{i}",
                    "name": f"Watch {i}",
                    "start_date": "2026-06-01",
                    "end_date": "2026-06-15",
                },
            )
            watch_ids.append(response.json()["id"])

        # Signup
        signup = client.post(
            "/api/auth/signup",
            json={
                "email": "xavier@example.com",
                "password": "password_123",
            },
        )
        user_id = signup.json()["user"]["id"]

        # Verify all watches are now owned by user
        for watch_id in watch_ids:
            watch = api_module._watch_db.get_watch(watch_id)
            assert watch.user_id == user_id
            assert watch.session_token == ""
