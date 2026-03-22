"""Integration tests for non-auth API endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

import pnw_campsites.api as api_module
from pnw_campsites.api import SESSION_COOKIE
from pnw_campsites.registry.models import BookingSystem
from pnw_campsites.search.engine import (
    AvailableWindow,
    CampgroundResult,
    SearchResults,
)
from tests.conftest import make_campground


class TestTrackEndpoint:
    """Tests for POST /api/track."""

    def test_track_valid_event_returns_ok_true(self, api_client: TestClient):
        """POST /api/track with valid event should return ok=true."""
        response = api_client.post(
            "/api/track",
            json={"event": "card_expand", "facility_id": "232465"},
        )

        assert response.status_code == 200
        assert response.json() == {"ok": True}

    def test_track_unknown_event_returns_ok_false(self, api_client: TestClient):
        """POST /api/track with unknown event should return ok=false."""
        response = api_client.post(
            "/api/track",
            json={"event": "unknown_event", "facility_id": "232465"},
        )

        assert response.status_code == 200
        assert response.json() == {"ok": False}

    def test_track_book_click_event(self, api_client: TestClient):
        """POST /api/track with book_click event should succeed."""
        response = api_client.post(
            "/api/track",
            json={
                "event": "book_click",
                "facility_id": "232465",
                "site": "A001",
            },
        )

        assert response.status_code == 200
        assert response.json() == {"ok": True}

    def test_track_search_event(self, api_client: TestClient):
        """POST /api/track with search event should succeed."""
        response = api_client.post(
            "/api/track",
            json={
                "event": "search",
                "source": "recgov",
                "type": "find",
            },
        )

        assert response.status_code == 200
        assert response.json() == {"ok": True}

    def test_track_oversized_body_returns_ok_false(self, api_client: TestClient):
        """POST /api/track with body >4KB should return ok=false."""
        large_data = "x" * 5000
        response = api_client.post(
            "/api/track",
            json={"event": "search", "data": large_data},
        )

        assert response.status_code == 200
        assert response.json() == {"ok": False}

    def test_track_non_dict_body_returns_ok_false(self, api_client: TestClient):
        """POST /api/track with non-dict body should return ok=false."""
        response = api_client.post(
            "/api/track",
            json=["list", "not", "dict"],
        )

        assert response.status_code == 200
        assert response.json() == {"ok": False}


class TestCampgroundsEndpoint:
    """Tests for GET /api/campgrounds."""

    def test_campgrounds_returns_empty_list(self, api_client: TestClient):
        """GET /api/campgrounds with no registry data returns empty list."""
        response = api_client.get("/api/campgrounds")

        assert response.status_code == 200
        assert response.json() == []

    def test_campgrounds_with_state_filter(self, api_client: TestClient):
        """GET /api/campgrounds?state=WA calls registry.search with state."""
        # Mock registry to return a campground
        cg = make_campground(state="WA", facility_id="123")
        api_module._registry.search.return_value = [cg]

        response = api_client.get("/api/campgrounds?state=WA")

        assert response.status_code == 200
        results = response.json()
        assert len(results) == 1
        assert results[0]["state"] == "WA"
        api_module._registry.search.assert_called()

    def test_campgrounds_with_source_filter(self, api_client: TestClient):
        """GET /api/campgrounds?source=wa_state calls registry with booking_system."""
        cg = make_campground(
            booking_system=BookingSystem.WA_STATE,
            facility_id="-2147483624",
        )
        api_module._registry.search.return_value = [cg]

        response = api_client.get("/api/campgrounds?source=wa_state")

        assert response.status_code == 200
        results = response.json()
        assert len(results) == 1
        assert results[0]["booking_system"] == "wa_state"

    def test_campgrounds_response_includes_required_fields(
        self, api_client: TestClient
    ):
        """GET /api/campgrounds response should have all required CampgroundResponse fields."""
        cg = make_campground(facility_id="999", name="Test Camp")
        api_module._registry.search.return_value = [cg]

        response = api_client.get("/api/campgrounds")

        assert response.status_code == 200
        results = response.json()
        result = results[0]
        assert result["facility_id"] == "999"
        assert result["name"] == "Test Camp"
        assert result["state"] == "WA"
        assert result["booking_system"] == "recgov"
        assert "latitude" in result
        assert "longitude" in result
        assert "tags" in result


class TestSearchEndpoint:
    """Tests for GET /api/search."""

    def test_search_valid_params_returns_results(self, api_client: TestClient):
        """GET /api/search with valid params should return 200."""
        cg = make_campground(facility_id="232465", name="Ohanapecosh")
        window = AvailableWindow(
            campsite_id="123456",
            site_name="A001",
            loop="Loop A",
            campsite_type="STANDARD NONELECTRIC",
            start_date="2026-06-01",
            end_date="2026-06-03",
            nights=2,
            max_people=6,
        )
        result = CampgroundResult(
            campground=cg,
            available_windows=[window],
            total_available_sites=1,
        )
        search_results = SearchResults(
            query=None,
            results=[result],
            campgrounds_checked=1,
            campgrounds_with_availability=1,
        )
        api_module._engine.search = AsyncMock(return_value=search_results)

        response = api_client.get(
            "/api/search?start_date=2026-06-01&end_date=2026-06-30"
        )

        assert response.status_code == 200
        data = response.json()
        assert "campgrounds_checked" in data
        assert "campgrounds_with_availability" in data
        assert "results" in data
        assert len(data["results"]) == 1

    def test_search_missing_start_date_returns_422(self, api_client: TestClient):
        """GET /api/search without start_date should return 422."""
        response = api_client.get("/api/search?end_date=2026-06-30")

        assert response.status_code == 422

    def test_search_missing_end_date_returns_422(self, api_client: TestClient):
        """GET /api/search without end_date should return 422."""
        response = api_client.get("/api/search?start_date=2026-06-01")

        assert response.status_code == 422

    def test_search_limit_capped_at_50(self, api_client: TestClient):
        """GET /api/search with limit=100 should reject (le=50 constraint)."""
        response = api_client.get(
            "/api/search?start_date=2026-06-01&end_date=2026-06-30&limit=100"
        )

        # FastAPI le constraint should reject values > 50
        assert response.status_code == 422

    def test_search_with_source_filter(self, api_client: TestClient):
        """GET /api/search?source=wa_state should filter by booking system."""
        cg = make_campground(booking_system=BookingSystem.WA_STATE)
        result = CampgroundResult(campground=cg)
        search_results = SearchResults(
            query=None,
            results=[result],
            campgrounds_checked=1,
        )
        api_module._engine.search = AsyncMock(return_value=search_results)

        response = api_client.get(
            "/api/search?start_date=2026-06-01&end_date=2026-06-30&source=wa_state"
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["results"]) == 1

    def test_search_with_days_of_week(self, api_client: TestClient):
        """GET /api/search?days_of_week=5,6 should filter by weekend days."""
        cg = make_campground()
        result = CampgroundResult(campground=cg)
        search_results = SearchResults(
            query=None,
            results=[result],
            campgrounds_checked=1,
        )
        api_module._engine.search = AsyncMock(return_value=search_results)

        response = api_client.get(
            "/api/search?start_date=2026-06-01&end_date=2026-06-30&days_of_week=5,6"
        )

        assert response.status_code == 200
        assert response.json()["results"] is not None

    def test_search_with_state_filter(self, api_client: TestClient):
        """GET /api/search?state=OR should include state in query."""
        cg = make_campground(state="OR")
        result = CampgroundResult(campground=cg)
        search_results = SearchResults(
            query=None,
            results=[result],
            campgrounds_checked=1,
        )
        api_module._engine.search = AsyncMock(return_value=search_results)

        response = api_client.get(
            "/api/search?start_date=2026-06-01&end_date=2026-06-30&state=OR"
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["results"]) == 1
        assert data["results"][0]["state"] == "OR"

    def test_search_response_structure(self, api_client: TestClient):
        """GET /api/search response should match SearchResponse schema."""
        cg = make_campground()
        window = AvailableWindow(
            campsite_id="123",
            site_name="A001",
            loop="Loop A",
            campsite_type="STANDARD",
            start_date="2026-06-01",
            end_date="2026-06-02",
            nights=1,
            max_people=6,
        )
        result = CampgroundResult(
            campground=cg,
            available_windows=[window],
            total_available_sites=1,
        )
        search_results = SearchResults(
            query=None,
            results=[result],
            campgrounds_checked=1,
            campgrounds_with_availability=1,
        )
        api_module._engine.search = AsyncMock(return_value=search_results)

        response = api_client.get(
            "/api/search?start_date=2026-06-01&end_date=2026-06-30"
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data["campgrounds_checked"], int)
        assert isinstance(data["campgrounds_with_availability"], int)
        assert isinstance(data["results"], list)
        assert isinstance(data.get("warnings", []), list)


class TestCheckEndpoint:
    """Tests for GET /api/check/{facility_id}."""

    def test_check_valid_facility_id_returns_result(self, api_client: TestClient):
        """GET /api/check/232465 with valid params should return result."""
        cg = make_campground(facility_id="232465")
        window = AvailableWindow(
            campsite_id="123",
            site_name="A001",
            loop="Loop A",
            campsite_type="STANDARD",
            start_date="2026-06-01",
            end_date="2026-06-02",
            nights=1,
            max_people=6,
        )
        result = CampgroundResult(
            campground=cg,
            available_windows=[window],
            total_available_sites=1,
        )
        api_module._engine.check_specific = AsyncMock(return_value=result)

        response = api_client.get(
            "/api/check/232465?start_date=2026-06-01&end_date=2026-06-30"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["facility_id"] == "232465"
        assert data["name"] == "Test Campground"

    def test_check_invalid_facility_id_returns_400(self, api_client: TestClient):
        """GET /api/check/invalid!id should return 400."""
        response = api_client.get(
            "/api/check/invalid!id?start_date=2026-06-01&end_date=2026-06-30"
        )

        assert response.status_code == 400
        assert "Invalid facility_id" in response.json()["detail"]

    def test_check_missing_start_date_returns_422(self, api_client: TestClient):
        """GET /api/check/232465 without start_date should return 422."""
        response = api_client.get("/api/check/232465?end_date=2026-06-30")

        assert response.status_code == 422

    def test_check_missing_end_date_returns_422(self, api_client: TestClient):
        """GET /api/check/232465 without end_date should return 422."""
        response = api_client.get("/api/check/232465?start_date=2026-06-01")

        assert response.status_code == 422

    def test_check_with_source_filter(self, api_client: TestClient):
        """GET /api/check/232465?source=wa_state should specify booking system."""
        cg = make_campground(
            facility_id="232465",
            booking_system=BookingSystem.WA_STATE,
        )
        result = CampgroundResult(campground=cg)
        api_module._engine.check_specific = AsyncMock(return_value=result)

        response = api_client.get(
            "/api/check/232465?start_date=2026-06-01&end_date=2026-06-30&source=wa_state"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["booking_system"] == "wa_state"

    def test_check_with_hyphenated_facility_id(self, api_client: TestClient):
        """GET /api/check/-2147483624 should accept hyphenated IDs."""
        cg = make_campground(facility_id="-2147483624")
        result = CampgroundResult(campground=cg)
        api_module._engine.check_specific = AsyncMock(return_value=result)

        response = api_client.get(
            "/api/check/-2147483624?start_date=2026-06-01&end_date=2026-06-30"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["facility_id"] == "-2147483624"


class TestWatchCRUDEndpoints:
    """Tests for watch CRUD endpoints (non-auth)."""

    def test_create_watch_creates_watch_with_session_cookie(
        self, api_client: TestClient
    ):
        """POST /api/watches should create watch and set session cookie."""
        response = api_client.post(
            "/api/watches",
            json={
                "facility_id": "232465",
                "name": "My Watch",
                "start_date": "2026-06-01",
                "end_date": "2026-06-30",
                "min_nights": 2,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["facility_id"] == "232465"
        assert data["name"] == "My Watch"
        assert data["id"]

        # Verify session cookie is set
        assert SESSION_COOKIE in api_client.cookies

    def test_create_watch_without_name_uses_registry(
        self, api_client: TestClient
    ):
        """POST /api/watches without name should look up from registry."""
        cg = make_campground(facility_id="232465", name="Ohanapecosh")
        api_module._registry.get_by_facility_id.return_value = cg

        response = api_client.post(
            "/api/watches",
            json={
                "facility_id": "232465",
                "start_date": "2026-06-01",
                "end_date": "2026-06-30",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Ohanapecosh"

    def test_create_watch_without_name_fallback(self, api_client: TestClient):
        """POST /api/watches without name and no registry match should use fallback."""
        api_module._registry.get_by_facility_id.return_value = None

        response = api_client.post(
            "/api/watches",
            json={
                "facility_id": "unknown",
                "start_date": "2026-06-01",
                "end_date": "2026-06-30",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "Facility" in data["name"]

    def test_create_watch_invalid_facility_id_returns_422(
        self, api_client: TestClient
    ):
        """POST /api/watches with invalid facility_id should return 422."""
        response = api_client.post(
            "/api/watches",
            json={
                "facility_id": "invalid!@#",
                "start_date": "2026-06-01",
                "end_date": "2026-06-30",
            },
        )

        assert response.status_code == 422

    def test_create_watch_duplicate_returns_409(self, api_client: TestClient):
        """POST /api/watches with duplicate watch should return 409."""
        # Create first watch
        api_client.post(
            "/api/watches",
            json={
                "facility_id": "232465",
                "start_date": "2026-06-01",
                "end_date": "2026-06-30",
            },
        )

        # Try to create duplicate
        response = api_client.post(
            "/api/watches",
            json={
                "facility_id": "232465",
                "start_date": "2026-06-01",
                "end_date": "2026-06-30",
            },
        )

        assert response.status_code == 409
        assert "Watch already exists" in response.json()["detail"]

    def test_list_watches_returns_session_watches(self, api_client: TestClient):
        """GET /api/watches should return watches for current session."""
        # Create watch
        api_client.post(
            "/api/watches",
            json={
                "facility_id": "111",
                "start_date": "2026-06-01",
                "end_date": "2026-06-30",
            },
        )

        # List watches
        response = api_client.get("/api/watches")

        assert response.status_code == 200
        watches = response.json()
        assert len(watches) == 1
        assert watches[0]["facility_id"] == "111"

    def test_list_watches_empty_list(self, api_client: TestClient):
        """GET /api/watches with no watches should return empty list."""
        response = api_client.get("/api/watches")

        assert response.status_code == 200
        assert response.json() == []

    def test_delete_own_watch_returns_ok_true(self, api_client: TestClient):
        """DELETE /api/watches/{id} own watch should return ok=true."""
        # Create watch
        create_response = api_client.post(
            "/api/watches",
            json={
                "facility_id": "232465",
                "start_date": "2026-06-01",
                "end_date": "2026-06-30",
            },
        )
        watch_id = create_response.json()["id"]

        # Delete watch
        response = api_client.delete(f"/api/watches/{watch_id}")

        assert response.status_code == 200
        assert response.json()["ok"] is True

        # Verify watch is gone
        list_response = api_client.get("/api/watches")
        assert len(list_response.json()) == 0

    def test_delete_nonexistent_watch_returns_ok_false(
        self, api_client: TestClient
    ):
        """DELETE /api/watches/{id} nonexistent should return ok=false."""
        response = api_client.delete("/api/watches/99999")

        assert response.status_code == 200
        assert response.json()["ok"] is False

    def test_toggle_watch_toggles_enabled(self, api_client: TestClient):
        """PATCH /api/watches/{id}/toggle should toggle enabled state."""
        # Create watch
        create_response = api_client.post(
            "/api/watches",
            json={
                "facility_id": "232465",
                "start_date": "2026-06-01",
                "end_date": "2026-06-30",
            },
        )
        watch_id = create_response.json()["id"]
        initial_enabled = create_response.json()["enabled"]

        # Toggle
        response = api_client.patch(f"/api/watches/{watch_id}/toggle")

        assert response.status_code == 200
        assert response.json()["ok"] is True
        assert response.json()["enabled"] == (not initial_enabled)

    def test_toggle_nonexistent_watch_returns_ok_false(
        self, api_client: TestClient
    ):
        """PATCH /api/watches/{id}/toggle nonexistent should return ok=false."""
        response = api_client.patch("/api/watches/99999/toggle")

        assert response.status_code == 200
        assert response.json()["ok"] is False

    def test_watch_response_includes_all_fields(self, api_client: TestClient):
        """POST /api/watches response should include all WatchResponse fields."""
        response = api_client.post(
            "/api/watches",
            json={
                "facility_id": "232465",
                "name": "Test Watch",
                "start_date": "2026-06-01",
                "end_date": "2026-06-30",
                "min_nights": 2,
                "days_of_week": [4, 5, 6],
                "notify_topic": "my-topic",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert "facility_id" in data
        assert "name" in data
        assert "start_date" in data
        assert "end_date" in data
        assert "min_nights" in data
        assert "days_of_week" in data
        assert "notify_topic" in data
        assert "enabled" in data
        assert "created_at" in data

    def test_watch_days_of_week_preserved(self, api_client: TestClient):
        """Watch should preserve days_of_week array."""
        response = api_client.post(
            "/api/watches",
            json={
                "facility_id": "232465",
                "start_date": "2026-06-01",
                "end_date": "2026-06-30",
                "days_of_week": [4, 5, 6],
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["days_of_week"] == [4, 5, 6]
