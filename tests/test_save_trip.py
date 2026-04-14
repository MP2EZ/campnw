"""Tests for saving planner conversations as trips."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta

import jwt as pyjwt
from fastapi.testclient import TestClient

from pnw_campsites.routes.planner import _extract_campgrounds_from_messages

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
    token = _make_jwt(email="plansave@test.com")
    headers = _auth_headers(token)
    resp = client.get("/api/auth/me", headers=headers)
    assert resp.status_code == 200
    return resp.json(), headers


class TestExtractCampgrounds:
    """Unit tests for _extract_campgrounds_from_messages."""

    def test_extracts_from_search_results(self):
        msgs = [
            {
                "role": "assistant",
                "content": "Here are some options.",
                "tool_calls": [{
                    "name": "search_campgrounds",
                    "result": json.dumps({
                        "found": 2,
                        "campgrounds": [
                            {"facility_id": "232465", "name": "Ohanapecosh", "booking_system": "recgov"},
                            {"facility_id": "232466", "name": "White River", "booking_system": "recgov"},
                        ],
                    }),
                }],
            },
        ]
        result = _extract_campgrounds_from_messages(msgs)
        assert len(result) == 2
        assert result[0]["facility_id"] == "232465"
        assert result[1]["facility_id"] == "232466"

    def test_extracts_from_check_availability(self):
        msgs = [
            {
                "role": "assistant",
                "content": "Checking availability.",
                "tool_calls": [{
                    "name": "check_availability",
                    "result": json.dumps({
                        "facility_id": "232465",
                        "name": "Ohanapecosh",
                        "booking_system": "recgov",
                    }),
                }],
            },
        ]
        result = _extract_campgrounds_from_messages(msgs)
        assert len(result) == 1
        assert result[0]["facility_id"] == "232465"

    def test_deduplicates_facility_ids(self):
        msgs = [
            {
                "role": "assistant",
                "content": "Search.",
                "tool_calls": [{
                    "name": "search_campgrounds",
                    "result": json.dumps({
                        "campgrounds": [
                            {"facility_id": "232465", "name": "Ohanapecosh"},
                        ],
                    }),
                }],
            },
            {
                "role": "assistant",
                "content": "Check.",
                "tool_calls": [{
                    "name": "check_availability",
                    "result": json.dumps({"facility_id": "232465", "name": "Ohanapecosh"}),
                }],
            },
        ]
        result = _extract_campgrounds_from_messages(msgs)
        assert len(result) == 1

    def test_handles_empty_messages(self):
        assert _extract_campgrounds_from_messages([]) == []

    def test_handles_messages_without_tool_calls(self):
        msgs = [
            {"role": "user", "content": "find camping"},
            {"role": "assistant", "content": "I can help!"},
        ]
        assert _extract_campgrounds_from_messages(msgs) == []


class TestSaveTripEndpoint:
    def test_save_trip_authenticated(self, api_client: TestClient):
        _, headers = _signup(api_client)
        resp = api_client.post("/api/plan/save-trip", json={
            "name": "Summer Camping",
            "messages": [
                {"role": "user", "content": "Find camping June 2026-06-01 to 2026-06-07"},
                {"role": "assistant", "content": "Found some spots."},
            ],
        }, headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Summer Camping"
        assert data["trip_id"] is not None

    def test_save_trip_unauthenticated(self, api_client: TestClient):
        resp = api_client.post("/api/plan/save-trip", json={
            "name": "Fail",
            "messages": [{"role": "user", "content": "hi"}],
        })
        assert resp.status_code == 401

    def test_save_trip_extracts_dates(self, api_client: TestClient):
        _, headers = _signup(api_client)
        resp = api_client.post("/api/plan/save-trip", json={
            "name": "Date Test",
            "messages": [
                {"role": "user", "content": "camping 2026-07-01 to 2026-07-14"},
            ],
        }, headers=headers)
        trip_id = resp.json()["trip_id"]
        # Verify the trip has the inferred dates
        trip = api_client.get(f"/api/trips/{trip_id}", headers=headers).json()
        assert trip["start_date"] == "2026-07-01"
        assert trip["end_date"] == "2026-07-14"
