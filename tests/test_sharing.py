"""Tests for watch/trip sharing via UUID links."""

from __future__ import annotations

from unittest.mock import MagicMock

from fastapi.testclient import TestClient

import pnw_campsites.api as api_module


def _signup(client: TestClient, email: str = "share@test.com") -> dict:
    resp = client.post(
        "/api/auth/signup",
        json={"email": email, "password": "testpass123"},
    )
    assert resp.status_code == 200
    return resp.json()


def _create_watch(client: TestClient) -> dict:
    from tests.conftest import make_campground
    api_module._registry.get_by_facility_id.return_value = make_campground(
        facility_id="232465", name="Ohanapecosh",
    )
    resp = client.post("/api/watches", json={
        "facility_id": "232465",
        "start_date": "2026-06-01",
        "end_date": "2026-06-30",
    })
    assert resp.status_code == 200
    return resp.json()


def _create_trip(client: TestClient) -> dict:
    resp = client.post("/api/trips", json={"name": "Share Test Trip"})
    assert resp.status_code == 200
    return resp.json()


class TestSharing:
    def test_create_share_for_watch(self, api_client: TestClient):
        _signup(api_client)
        watch = _create_watch(api_client)
        resp = api_client.post("/api/shares", json={"watch_id": watch["id"]})
        assert resp.status_code == 200
        data = resp.json()
        assert "uuid" in data
        assert "expires_at" in data

    def test_create_share_for_trip(self, api_client: TestClient):
        _signup(api_client)
        trip = _create_trip(api_client)
        resp = api_client.post("/api/shares", json={"trip_id": trip["id"]})
        assert resp.status_code == 200
        assert "uuid" in resp.json()

    def test_create_share_unauthenticated(self, api_client: TestClient):
        resp = api_client.post("/api/shares", json={"watch_id": 1})
        assert resp.status_code == 401

    def test_create_share_no_target(self, api_client: TestClient):
        _signup(api_client)
        resp = api_client.post("/api/shares", json={})
        assert resp.status_code == 422

    def test_view_shared_watch(self, api_client: TestClient):
        _signup(api_client)
        watch = _create_watch(api_client)
        share = api_client.post("/api/shares", json={"watch_id": watch["id"]}).json()

        # View without auth
        api_client.post("/api/auth/logout")
        resp = api_client.get(f"/api/shared/{share['uuid']}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "watch"
        assert data["watch"]["facility_id"] == "232465"

    def test_view_shared_trip(self, api_client: TestClient):
        _signup(api_client)
        trip = _create_trip(api_client)
        api_client.post(
            f"/api/trips/{trip['id']}/campgrounds",
            json={"facility_id": "232465", "name": "Ohanapecosh"},
        )
        share = api_client.post("/api/shares", json={"trip_id": trip["id"]}).json()

        api_client.post("/api/auth/logout")
        resp = api_client.get(f"/api/shared/{share['uuid']}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "trip"
        assert len(data["trip"]["campgrounds"]) == 1

    def test_view_nonexistent_link_404(self, api_client: TestClient):
        resp = api_client.get("/api/shared/doesnotexist")
        assert resp.status_code == 404

    def test_revoke_shared_link(self, api_client: TestClient):
        _signup(api_client)
        watch = _create_watch(api_client)
        share = api_client.post("/api/shares", json={"watch_id": watch["id"]}).json()

        # Revoke
        resp = api_client.delete(f"/api/shares/{share['uuid']}")
        assert resp.status_code == 200

        # View should fail
        resp = api_client.get(f"/api/shared/{share['uuid']}")
        assert resp.status_code == 410

    def test_revoke_other_users_link_404(self, api_client: TestClient):
        _signup(api_client, "user1@test.com")
        watch = _create_watch(api_client)
        share = api_client.post("/api/shares", json={"watch_id": watch["id"]}).json()

        api_client.post("/api/auth/logout")
        _signup(api_client, "user2@test.com")
        resp = api_client.delete(f"/api/shares/{share['uuid']}")
        assert resp.status_code == 404

    def test_share_other_users_watch_404(self, api_client: TestClient):
        _signup(api_client, "owner@test.com")
        watch = _create_watch(api_client)
        api_client.post("/api/auth/logout")
        _signup(api_client, "attacker@test.com")
        resp = api_client.post("/api/shares", json={"watch_id": watch["id"]})
        assert resp.status_code == 404
