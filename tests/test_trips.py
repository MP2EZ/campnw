"""Tests for trip CRUD (schema, DB methods, API endpoints)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import pnw_campsites.api as api_module
from pnw_campsites.monitor.db import User


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _signup(client: TestClient, email: str = "trips@example.com") -> dict:
    resp = client.post(
        "/api/auth/signup",
        json={"email": email, "password": "testpass123", "display_name": "Trip Tester"},
    )
    assert resp.status_code == 200
    return resp.json()


def _create_trip(client: TestClient, name: str = "Summer Trip", **kwargs) -> dict:
    resp = client.post(
        "/api/trips",
        json={"name": name, **kwargs},
    )
    assert resp.status_code == 200
    return resp.json()


# ---------------------------------------------------------------------------
# DB-level tests
# ---------------------------------------------------------------------------


class TestTripDB:
    """Tests for WatchDB trip methods."""

    def test_create_trip(self, watch_db):
        user = watch_db.create_user(User(email="u@test.com", password_hash="hash"))
        trip = watch_db.create_trip(user.id, "Test Trip", start_date="2026-06-01")
        assert trip.id is not None
        assert trip.name == "Test Trip"
        assert trip.start_date == "2026-06-01"
        assert trip.user_id == user.id

    def test_get_trip(self, watch_db):
        user = watch_db.create_user(User(email="u@test.com", password_hash="hash"))
        trip = watch_db.create_trip(user.id, "Test")
        fetched = watch_db.get_trip(trip.id)
        assert fetched is not None
        assert fetched.name == "Test"

    def test_get_trip_not_found(self, watch_db):
        assert watch_db.get_trip(9999) is None

    def test_list_trips_by_user(self, watch_db):
        user = watch_db.create_user(User(email="u@test.com", password_hash="hash"))
        watch_db.create_trip(user.id, "Trip A")
        watch_db.create_trip(user.id, "Trip B")
        trips = watch_db.list_trips_by_user(user.id)
        assert len(trips) == 2
        # Ordered by updated_at DESC
        assert trips[0].name == "Trip B"

    def test_update_trip(self, watch_db):
        user = watch_db.create_user(User(email="u@test.com", password_hash="hash"))
        trip = watch_db.create_trip(user.id, "Old Name")
        updated = watch_db.update_trip(trip.id, name="New Name")
        assert updated.name == "New Name"
        assert updated.updated_at > trip.updated_at

    def test_delete_trip(self, watch_db):
        user = watch_db.create_user(User(email="u@test.com", password_hash="hash"))
        trip = watch_db.create_trip(user.id, "Doomed")
        assert watch_db.delete_trip(trip.id) is True
        assert watch_db.get_trip(trip.id) is None

    def test_delete_trip_not_found(self, watch_db):
        assert watch_db.delete_trip(9999) is False

    def test_max_trips_enforced(self, watch_db):
        user = watch_db.create_user(User(email="u@test.com", password_hash="hash"))
        for i in range(10):
            watch_db.create_trip(user.id, f"Trip {i}")
        with pytest.raises(ValueError, match="Maximum"):
            watch_db.create_trip(user.id, "One too many")

    def test_add_campground_to_trip(self, watch_db):
        user = watch_db.create_user(User(email="u@test.com", password_hash="hash"))
        trip = watch_db.create_trip(user.id, "Test")
        cg = watch_db.add_campground_to_trip(
            trip.id, "232465", "recgov", name="Ohanapecosh",
        )
        assert cg.facility_id == "232465"
        assert cg.sort_order == 0

    def test_add_duplicate_campground_fails(self, watch_db):
        import sqlite3
        user = watch_db.create_user(User(email="u@test.com", password_hash="hash"))
        trip = watch_db.create_trip(user.id, "Test")
        watch_db.add_campground_to_trip(trip.id, "232465", "recgov")
        with pytest.raises(sqlite3.IntegrityError):
            watch_db.add_campground_to_trip(trip.id, "232465", "recgov")

    def test_same_facility_different_source_ok(self, watch_db):
        user = watch_db.create_user(User(email="u@test.com", password_hash="hash"))
        trip = watch_db.create_trip(user.id, "Test")
        watch_db.add_campground_to_trip(trip.id, "123", "recgov")
        cg2 = watch_db.add_campground_to_trip(trip.id, "123", "wa_state")
        assert cg2.source == "wa_state"

    def test_remove_campground_from_trip(self, watch_db):
        user = watch_db.create_user(User(email="u@test.com", password_hash="hash"))
        trip = watch_db.create_trip(user.id, "Test")
        watch_db.add_campground_to_trip(trip.id, "232465", "recgov")
        assert watch_db.remove_campground_from_trip(trip.id, "232465", "recgov")
        assert len(watch_db.get_trip_campgrounds(trip.id)) == 0

    def test_remove_nonexistent_campground(self, watch_db):
        user = watch_db.create_user(User(email="u@test.com", password_hash="hash"))
        trip = watch_db.create_trip(user.id, "Test")
        assert watch_db.remove_campground_from_trip(trip.id, "nope") is False

    def test_get_trip_campgrounds_ordered(self, watch_db):
        user = watch_db.create_user(User(email="u@test.com", password_hash="hash"))
        trip = watch_db.create_trip(user.id, "Test")
        watch_db.add_campground_to_trip(trip.id, "aaa", name="First")
        watch_db.add_campground_to_trip(trip.id, "bbb", name="Second")
        watch_db.add_campground_to_trip(trip.id, "ccc", name="Third")
        cgs = watch_db.get_trip_campgrounds(trip.id)
        assert [cg.facility_id for cg in cgs] == ["aaa", "bbb", "ccc"]
        assert [cg.sort_order for cg in cgs] == [0, 1, 2]

    def test_cascade_delete_trip_removes_campgrounds(self, watch_db):
        user = watch_db.create_user(User(email="u@test.com", password_hash="hash"))
        trip = watch_db.create_trip(user.id, "Test")
        watch_db.add_campground_to_trip(trip.id, "232465")
        watch_db.delete_trip(trip.id)
        assert len(watch_db.get_trip_campgrounds(trip.id)) == 0


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------


class TestTripAPI:
    """Tests for /api/trips endpoints."""

    def test_create_trip_authenticated(self, api_client: TestClient):
        _signup(api_client)
        trip = _create_trip(api_client, "Beach Trip", start_date="2026-07-01")
        assert trip["name"] == "Beach Trip"
        assert trip["id"] is not None
        assert trip["campgrounds"] == []

    def test_create_trip_unauthenticated(self, api_client: TestClient):
        resp = api_client.post(
            "/api/trips", json={"name": "Fail"},
        )
        assert resp.status_code == 401

    def test_list_trips(self, api_client: TestClient):
        _signup(api_client)
        _create_trip(api_client, "Trip A")
        _create_trip(api_client, "Trip B")
        resp = api_client.get("/api/trips")
        assert resp.status_code == 200
        trips = resp.json()
        assert len(trips) == 2

    def test_get_trip_detail(self, api_client: TestClient):
        _signup(api_client)
        trip = _create_trip(api_client, "Detail Trip")
        resp = api_client.get(f"/api/trips/{trip['id']}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Detail Trip"
        assert "campgrounds" in data

    def test_get_other_users_trip_404(self, api_client: TestClient):
        _signup(api_client, "user1@test.com")
        trip = _create_trip(api_client, "Private Trip")
        # Log out and create a second user
        api_client.post("/api/auth/logout")
        _signup(api_client, "user2@test.com")
        resp = api_client.get(f"/api/trips/{trip['id']}")
        assert resp.status_code == 404

    def test_update_trip(self, api_client: TestClient):
        _signup(api_client)
        trip = _create_trip(api_client, "Old Name")
        resp = api_client.patch(
            f"/api/trips/{trip['id']}",
            json={"name": "New Name"},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "New Name"

    def test_delete_trip(self, api_client: TestClient):
        _signup(api_client)
        trip = _create_trip(api_client, "Temp")
        resp = api_client.delete(f"/api/trips/{trip['id']}")
        assert resp.status_code == 200
        # Verify gone
        resp = api_client.get(f"/api/trips/{trip['id']}")
        assert resp.status_code == 404

    def test_add_campground_to_trip(self, api_client: TestClient):
        _signup(api_client)
        trip = _create_trip(api_client)
        resp = api_client.post(
            f"/api/trips/{trip['id']}/campgrounds",
            json={"facility_id": "232465", "source": "recgov", "name": "Ohanapecosh"},
        )
        assert resp.status_code == 200
        assert resp.json()["facility_id"] == "232465"

    def test_add_duplicate_campground_409(self, api_client: TestClient):
        _signup(api_client)
        trip = _create_trip(api_client)
        api_client.post(
            f"/api/trips/{trip['id']}/campgrounds",
            json={"facility_id": "232465"},
        )
        resp = api_client.post(
            f"/api/trips/{trip['id']}/campgrounds",
            json={"facility_id": "232465"},
        )
        assert resp.status_code == 409

    def test_remove_campground(self, api_client: TestClient):
        _signup(api_client)
        trip = _create_trip(api_client)
        api_client.post(
            f"/api/trips/{trip['id']}/campgrounds",
            json={"facility_id": "232465"},
        )
        resp = api_client.delete(
            f"/api/trips/{trip['id']}/campgrounds/232465?source=recgov",
        )
        assert resp.status_code == 200

    def test_max_trips_returns_409(self, api_client: TestClient):
        _signup(api_client)
        for i in range(10):
            _create_trip(api_client, f"Trip {i}")
        resp = api_client.post(
            "/api/trips", json={"name": "One too many"},
        )
        assert resp.status_code == 409

    def test_trip_name_required(self, api_client: TestClient):
        _signup(api_client)
        resp = api_client.post("/api/trips", json={"name": ""})
        assert resp.status_code == 422

    def test_list_shows_campground_count(self, api_client: TestClient):
        _signup(api_client)
        trip = _create_trip(api_client)
        api_client.post(
            f"/api/trips/{trip['id']}/campgrounds",
            json={"facility_id": "aaa"},
        )
        api_client.post(
            f"/api/trips/{trip['id']}/campgrounds",
            json={"facility_id": "bbb"},
        )
        resp = api_client.get("/api/trips")
        trips = resp.json()
        assert trips[0]["campground_count"] == 2
