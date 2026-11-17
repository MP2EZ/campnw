"""Tests for onboarding: preferred_tags and onboarding_complete fields."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import signup_and_auth

EMAIL = "onboard@test.com"


class TestOnboarding:
    def test_new_user_has_onboarding_incomplete(self, api_client: TestClient):
        _, headers = signup_and_auth(api_client, EMAIL, display_name="")
        me = api_client.get("/api/auth/me", headers=headers).json()["user"]
        assert me["onboarding_complete"] is False
        assert me["preferred_tags"] == []

    def test_set_preferred_tags(self, api_client: TestClient):
        _, headers = signup_and_auth(api_client, EMAIL, display_name="")
        resp = api_client.patch(
            "/api/auth/me",
            json={"preferred_tags": ["lakeside", "trails", "pet-friendly"]},
            headers=headers,
        )
        assert resp.status_code == 200
        user = resp.json()["user"]
        assert user["preferred_tags"] == ["lakeside", "trails", "pet-friendly"]

    def test_mark_onboarding_complete(self, api_client: TestClient):
        _, headers = signup_and_auth(api_client, EMAIL, display_name="")
        resp = api_client.patch(
            "/api/auth/me",
            json={"onboarding_complete": True},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["user"]["onboarding_complete"] is True

    def test_preferred_tags_persists(self, api_client: TestClient):
        _, headers = signup_and_auth(api_client, EMAIL, display_name="")
        api_client.patch(
            "/api/auth/me",
            json={"preferred_tags": ["alpine", "remote"]},
            headers=headers,
        )
        me = api_client.get("/api/auth/me", headers=headers).json()["user"]
        assert me["preferred_tags"] == ["alpine", "remote"]

    def test_full_onboarding_flow(self, api_client: TestClient):
        """Simulate complete onboarding: set home, tags, mark complete."""
        _, headers = signup_and_auth(api_client, EMAIL, display_name="")
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
        _, headers = signup_and_auth(api_client, EMAIL, display_name="")
        resp = api_client.patch(
            "/api/auth/me", json={"onboarding_complete": True},
            headers=headers,
        )
        user = resp.json()["user"]
        assert user["onboarding_complete"] is True
        assert user["preferred_tags"] == []
        assert user["home_base"] == ""
