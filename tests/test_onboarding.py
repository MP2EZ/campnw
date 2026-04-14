"""Tests for onboarding: preferred_tags and onboarding_complete fields."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import jwt as pyjwt
from fastapi.testclient import TestClient

_TEST_SECRET = "test-supabase-jwt-secret-that-is-at-least-32-characters"


def _make_jwt(email="test@example.com", supabase_id=None):
    sub = supabase_id or str(uuid.uuid4())
    payload = {
        "sub": sub, "email": email, "role": "authenticated", "aud": "authenticated",
        "exp": datetime.now(UTC) + timedelta(hours=1), "iat": datetime.now(UTC),
    }
    return pyjwt.encode(payload, _TEST_SECRET, algorithm="HS256")


def _auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


def _signup(client: TestClient):
    """Create user via auto-provisioning and return (user_data, auth_headers)."""
    token = _make_jwt(email="onboard@test.com")
    headers = _auth_headers(token)
    resp = client.get("/api/auth/me", headers=headers)
    assert resp.status_code == 200
    return resp.json(), headers


class TestOnboarding:
    def test_new_user_has_onboarding_incomplete(self, api_client: TestClient):
        _, headers = _signup(api_client)
        me = api_client.get("/api/auth/me", headers=headers).json()["user"]
        assert me["onboarding_complete"] is False
        assert me["preferred_tags"] == []

    def test_set_preferred_tags(self, api_client: TestClient):
        _, headers = _signup(api_client)
        resp = api_client.patch(
            "/api/auth/me",
            json={"preferred_tags": ["lakeside", "trails", "pet-friendly"]},
            headers=headers,
        )
        assert resp.status_code == 200
        user = resp.json()["user"]
        assert user["preferred_tags"] == ["lakeside", "trails", "pet-friendly"]

    def test_mark_onboarding_complete(self, api_client: TestClient):
        _, headers = _signup(api_client)
        resp = api_client.patch(
            "/api/auth/me",
            json={"onboarding_complete": True},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["user"]["onboarding_complete"] is True

    def test_preferred_tags_persists(self, api_client: TestClient):
        _, headers = _signup(api_client)
        api_client.patch(
            "/api/auth/me",
            json={"preferred_tags": ["alpine", "remote"]},
            headers=headers,
        )
        me = api_client.get("/api/auth/me", headers=headers).json()["user"]
        assert me["preferred_tags"] == ["alpine", "remote"]

    def test_full_onboarding_flow(self, api_client: TestClient):
        """Simulate complete onboarding: set home, tags, mark complete."""
        _, headers = _signup(api_client)
        # Step 1: home base
        api_client.patch("/api/auth/me", json={"home_base": "Seattle, WA"}, headers=headers)
        # Step 2: tags + complete
        resp = api_client.patch("/api/auth/me", json={
            "preferred_tags": ["lakeside", "forest"],
            "onboarding_complete": True,
        }, headers=headers)
        user = resp.json()["user"]
        assert user["home_base"] == "Seattle, WA"
        assert user["preferred_tags"] == ["lakeside", "forest"]
        assert user["onboarding_complete"] is True

    def test_skip_onboarding(self, api_client: TestClient):
        """Skip both steps — just mark complete."""
        _, headers = _signup(api_client)
        resp = api_client.patch(
            "/api/auth/me", json={"onboarding_complete": True},
            headers=headers,
        )
        user = resp.json()["user"]
        assert user["onboarding_complete"] is True
        assert user["preferred_tags"] == []
        assert user["home_base"] == ""
