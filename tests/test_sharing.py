"""Tests for watch/trip sharing via UUID links."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import jwt as pyjwt
from fastapi.testclient import TestClient

import pnw_campsites.api as api_module

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


def _signup(client: TestClient, email: str = "share@test.com"):
    """Create user via auto-provisioning and return (user_data, auth_headers)."""
    token = _make_jwt(email=email)
    headers = _auth_headers(token)
    resp = client.get("/api/auth/me", headers=headers)
    assert resp.status_code == 200
    return resp.json(), headers


def _create_watch(client: TestClient, headers: dict) -> dict:
    from tests.conftest import make_campground
    api_module._registry.get_by_facility_id.return_value = make_campground(
        facility_id="232465", name="Ohanapecosh",
    )
    resp = client.post("/api/watches", json={
        "facility_id": "232465",
        "start_date": "2026-06-01",
        "end_date": "2026-06-30",
    }, headers=headers)
    assert resp.status_code == 200
    return resp.json()


def _create_trip(client: TestClient, headers: dict) -> dict:
    resp = client.post("/api/trips", json={"name": "Share Test Trip"}, headers=headers)
    assert resp.status_code == 200
    return resp.json()


class TestSharing:
    def test_create_share_for_watch(self, api_client: TestClient):
        _, headers = _signup(api_client)
        watch = _create_watch(api_client, headers)
        resp = api_client.post("/api/shares", json={"watch_id": watch["id"]}, headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "uuid" in data
        assert "expires_at" in data

    def test_create_share_for_trip(self, api_client: TestClient):
        _, headers = _signup(api_client)
        trip = _create_trip(api_client, headers)
        resp = api_client.post("/api/shares", json={"trip_id": trip["id"]}, headers=headers)
        assert resp.status_code == 200
        assert "uuid" in resp.json()

    def test_create_share_unauthenticated(self, api_client: TestClient):
        resp = api_client.post("/api/shares", json={"watch_id": 1})
        assert resp.status_code == 401

    def test_create_share_no_target(self, api_client: TestClient):
        _, headers = _signup(api_client)
        resp = api_client.post("/api/shares", json={}, headers=headers)
        assert resp.status_code == 422

    def test_view_shared_watch(self, api_client: TestClient):
        _, headers = _signup(api_client)
        watch = _create_watch(api_client, headers)
        share = api_client.post("/api/shares", json={"watch_id": watch["id"]}, headers=headers).json()

        # View without auth (no headers)
        resp = api_client.get(f"/api/shared/{share['uuid']}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "watch"
        assert data["watch"]["facility_id"] == "232465"

    def test_view_shared_trip(self, api_client: TestClient):
        _, headers = _signup(api_client)
        trip = _create_trip(api_client, headers)
        api_client.post(
            f"/api/trips/{trip['id']}/campgrounds",
            json={"facility_id": "232465", "name": "Ohanapecosh"},
            headers=headers,
        )
        share = api_client.post("/api/shares", json={"trip_id": trip["id"]}, headers=headers).json()

        # View without auth (no headers)
        resp = api_client.get(f"/api/shared/{share['uuid']}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "trip"
        assert len(data["trip"]["campgrounds"]) == 1

    def test_view_nonexistent_link_404(self, api_client: TestClient):
        resp = api_client.get("/api/shared/doesnotexist")
        assert resp.status_code == 404

    def test_revoke_shared_link(self, api_client: TestClient):
        _, headers = _signup(api_client)
        watch = _create_watch(api_client, headers)
        share = api_client.post("/api/shares", json={"watch_id": watch["id"]}, headers=headers).json()

        # Revoke
        resp = api_client.delete(f"/api/shares/{share['uuid']}", headers=headers)
        assert resp.status_code == 200

        # View should fail
        resp = api_client.get(f"/api/shared/{share['uuid']}")
        assert resp.status_code == 410

    def test_revoke_other_users_link_404(self, api_client: TestClient):
        _, headers1 = _signup(api_client, "user1@test.com")
        watch = _create_watch(api_client, headers1)
        share = api_client.post("/api/shares", json={"watch_id": watch["id"]}, headers=headers1).json()

        _, headers2 = _signup(api_client, "user2@test.com")
        resp = api_client.delete(f"/api/shares/{share['uuid']}", headers=headers2)
        assert resp.status_code == 404

    def test_share_other_users_watch_404(self, api_client: TestClient):
        _, headers1 = _signup(api_client, "owner@test.com")
        watch = _create_watch(api_client, headers1)
        _, headers2 = _signup(api_client, "attacker@test.com")
        resp = api_client.post("/api/shares", json={"watch_id": watch["id"]}, headers=headers2)
        assert resp.status_code == 404
