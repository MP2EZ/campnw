"""Tests for the trip planner module (tools + API endpoints)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pnw_campsites.planner.tools import (
    TOOLS,
    _check_availability,
    _geocode_address,
    _get_campground_detail,
    _get_drive_time,
    _search_campgrounds,
    execute_tool,
)
from pnw_campsites.registry.models import BookingSystem
from pnw_campsites.search.engine import (
    AvailableWindow,
    CampgroundResult,
    SearchResults,
)
from tests.conftest import make_campground

# -------------------------------------------------------------------
# Tool structure
# -------------------------------------------------------------------


class TestToolStructure:
    """Validate tool definitions."""

    def test_tools_list_has_five_tools(self):
        assert len(TOOLS) == 5

    def test_expected_tool_names(self):
        names = {t["name"] for t in TOOLS}
        assert names == {
            "search_campgrounds",
            "check_availability",
            "get_drive_time",
            "get_campground_detail",
            "geocode_address",
        }

    def test_tools_have_required_fields(self):
        for tool in TOOLS:
            assert "name" in tool
            assert "description" in tool
            assert "input_schema" in tool
            assert tool["input_schema"]["type"] == "object"


# -------------------------------------------------------------------
# Tool executors
# -------------------------------------------------------------------


class TestSearchTool:
    """Test search_campgrounds executor."""

    @pytest.mark.asyncio
    async def test_search_returns_json(self):
        engine = AsyncMock()
        engine.search = AsyncMock(
            return_value=SearchResults(
                query=MagicMock(),
                results=[],
                campgrounds_checked=5,
                campgrounds_with_availability=0,
            ),
        )

        result = await execute_tool(
            "search_campgrounds",
            {"start_date": "2026-06-01", "end_date": "2026-06-07"},
            engine,
            MagicMock(),
        )

        data = json.loads(result)
        assert "campgrounds" in data
        assert isinstance(data["campgrounds"], list)


class TestDriveTimeTool:
    """Test get_drive_time executor."""

    @pytest.mark.asyncio
    async def test_returns_minutes(self):
        result = await execute_tool(
            "get_drive_time",
            {
                "from_lat": 47.6,
                "from_lon": -122.3,
                "to_lat": 46.75,
                "to_lon": -121.8,
            },
            None,
            None,
        )

        data = json.loads(result)
        assert "drive_minutes" in data
        assert isinstance(data["drive_minutes"], int)
        assert data["drive_minutes"] > 0


class TestDetailTool:
    """Test get_campground_detail executor."""

    @pytest.mark.asyncio
    async def test_not_found_returns_error(self):
        registry = MagicMock()
        registry.get_by_facility_id.return_value = None

        result = await execute_tool(
            "get_campground_detail",
            {"facility_id": "999999"},
            None,
            registry,
        )

        data = json.loads(result)
        assert "error" in data


class TestGeocodeTool:
    """Test geocode_address executor."""

    @pytest.mark.asyncio
    async def test_known_base_no_network(self):
        result = await execute_tool(
            "geocode_address",
            {"address": "seattle"},
            None,
            None,
        )

        data = json.loads(result)
        assert "lat" in data
        assert "lon" in data
        assert abs(data["lat"] - 47.6) < 0.5


class TestUnknownTool:
    """Test unknown tool name."""

    @pytest.mark.asyncio
    async def test_returns_error(self):
        result = await execute_tool(
            "nonexistent_tool",
            {},
            None,
            None,
        )

        data = json.loads(result)
        assert "error" in data


# -------------------------------------------------------------------
# API endpoints
# -------------------------------------------------------------------


class TestPlanChatApi:
    """Test plan chat API endpoints."""

    def test_missing_api_key_returns_503(self, api_client):
        import os
        from unittest.mock import patch

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""}):
            resp = api_client.post(
                "/api/plan/chat",
                json={"messages": [{"role": "user", "content": "hi"}]},
            )
        assert resp.status_code == 503

    def test_stream_missing_api_key_returns_503(self, api_client):
        import os
        from unittest.mock import patch

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""}):
            resp = api_client.post(
                "/api/plan/chat/stream",
                json={"messages": [{"role": "user", "content": "hi"}]},
            )
        assert resp.status_code == 503


# -------------------------------------------------------------------
# Search campgrounds tool implementation tests
# -------------------------------------------------------------------


class TestSearchCampgroundsTool:
    """Test _search_campgrounds() formatting logic."""

    @pytest.mark.asyncio
    async def test_search_with_results_formats_json(self):
        """Search with results returns proper JSON structure."""
        campground = make_campground(
            facility_id="232465",
            name="Ohanapecosh",
            state="WA",
            tags=["lakeside", "old-growth"],
            vibe="Rainier valley oasis",
        )
        window = AvailableWindow(
            campsite_id="123",
            site_name="A001",
            loop="Loop A",
            campsite_type="STANDARD NONELECTRIC",
            start_date="2026-06-01",
            end_date="2026-06-03",
            nights=2,
            max_people=6,
        )
        result = CampgroundResult(
            campground=campground,
            available_windows=[window],
            total_available_sites=1,
            fcfs_sites=0,
        )

        engine = AsyncMock()
        engine.search = AsyncMock(
            return_value=SearchResults(
                query=MagicMock(),
                results=[result],
                campgrounds_checked=20,
                campgrounds_with_availability=1,
            )
        )

        output = await _search_campgrounds(
            {
                "start_date": "2026-06-01",
                "end_date": "2026-06-30",
                "state": "WA",
            },
            engine,
        )

        data = json.loads(output)
        assert data["found"] == 1
        assert data["total_checked"] == 20
        assert len(data["campgrounds"]) == 1
        camp = data["campgrounds"][0]
        assert camp["facility_id"] == "232465"
        assert camp["name"] == "Ohanapecosh"
        assert camp["state"] == "WA"
        assert camp["booking_system"] == "recgov"
        assert "lakeside" in camp["tags"]
        assert camp["available_sites"] == 1
        assert "booking_url" in camp
        assert len(camp["earliest_windows"]) == 1

    @pytest.mark.asyncio
    async def test_search_zero_results_returns_empty_list(self):
        """Search with no results returns empty campgrounds list."""
        engine = AsyncMock()
        engine.search = AsyncMock(
            return_value=SearchResults(
                query=MagicMock(),
                results=[],
                campgrounds_checked=20,
                campgrounds_with_availability=0,
            )
        )

        output = await _search_campgrounds(
            {
                "start_date": "2026-06-01",
                "end_date": "2026-06-30",
            },
            engine,
        )

        data = json.loads(output)
        assert data["found"] == 0
        assert data["campgrounds"] == []

    @pytest.mark.asyncio
    async def test_search_caps_at_five_results(self):
        """Search returns only top 5 results."""
        campgrounds = [
            make_campground(facility_id=f"{i}") for i in range(10)
        ]
        results = [
            CampgroundResult(
                campground=cg,
                available_windows=[],
                total_available_sites=1,
            )
            for cg in campgrounds
        ]

        engine = AsyncMock()
        engine.search = AsyncMock(
            return_value=SearchResults(
                query=MagicMock(),
                results=results,
                campgrounds_checked=20,
                campgrounds_with_availability=10,
            )
        )

        output = await _search_campgrounds(
            {
                "start_date": "2026-06-01",
                "end_date": "2026-06-30",
            },
            engine,
        )

        data = json.loads(output)
        assert data["found"] == 5
        assert len(data["campgrounds"]) == 5

    @pytest.mark.asyncio
    async def test_search_with_wa_state_booking_system(self):
        """Search correctly formats WA State booking system URL."""
        campground = make_campground(
            facility_id="-2147483624",
            booking_system=BookingSystem.WA_STATE,
        )
        result = CampgroundResult(
            campground=campground,
            available_windows=[],
            total_available_sites=1,
        )

        engine = AsyncMock()
        engine.search = AsyncMock(
            return_value=SearchResults(
                query=MagicMock(),
                results=[result],
                campgrounds_checked=1,
                campgrounds_with_availability=1,
            )
        )

        output = await _search_campgrounds(
            {
                "start_date": "2026-06-01",
                "end_date": "2026-06-30",
                "source": "wa_state",
            },
            engine,
        )

        data = json.loads(output)
        assert "goingtocamp.com" in data["campgrounds"][0]["booking_url"]


# -------------------------------------------------------------------
# Check availability tool implementation tests
# -------------------------------------------------------------------


class TestCheckAvailabilityTool:
    """Test _check_availability() formatting logic."""

    @pytest.mark.asyncio
    async def test_check_availability_with_windows(self):
        """Check with windows returns proper JSON."""
        campground = make_campground(
            facility_id="232465",
            name="Test Camp",
            state="WA",
        )
        window = AvailableWindow(
            campsite_id="123",
            site_name="A001",
            loop="Loop A",
            campsite_type="STANDARD",
            start_date="2026-06-01",
            end_date="2026-06-03",
            nights=2,
            max_people=6,
        )
        result = CampgroundResult(
            campground=campground,
            available_windows=[window],
            total_available_sites=1,
            fcfs_sites=0,
        )

        engine = AsyncMock()
        engine.check_specific = AsyncMock(return_value=result)

        registry = MagicMock()
        registry.get_by_facility_id.return_value = campground

        output = await _check_availability(
            {
                "facility_id": "232465",
                "start_date": "2026-06-01",
                "end_date": "2026-06-30",
            },
            engine,
            registry,
        )

        data = json.loads(output)
        assert data["facility_id"] == "232465"
        assert data["name"] == "Test Camp"
        assert data["available_sites"] == 1
        assert data["state"] == "WA"
        assert "booking_url" in data
        assert "site_windows" in data

    @pytest.mark.asyncio
    async def test_check_availability_with_error(self):
        """Check with error returns error in JSON."""
        campground = make_campground(facility_id="232465")
        result = CampgroundResult(
            campground=campground,
            error="rate_limited",
        )

        engine = AsyncMock()
        engine.check_specific = AsyncMock(return_value=result)

        registry = MagicMock()

        output = await _check_availability(
            {
                "facility_id": "232465",
                "start_date": "2026-06-01",
                "end_date": "2026-06-30",
            },
            engine,
            registry,
        )

        data = json.loads(output)
        assert "error" in data
        assert data["error"] == "rate_limited"

    @pytest.mark.asyncio
    async def test_check_availability_caps_site_windows_at_five(self):
        """Check caps site_windows at 5 sites."""
        campground = make_campground()
        windows = [
            AvailableWindow(
                campsite_id=f"{i}",
                site_name=f"Site {i}",
                loop="Loop A",
                campsite_type="STANDARD",
                start_date="2026-06-01",
                end_date="2026-06-03",
                nights=2,
                max_people=6,
            )
            for i in range(10)
        ]
        result = CampgroundResult(
            campground=campground,
            available_windows=windows,
            total_available_sites=10,
        )

        engine = AsyncMock()
        engine.check_specific = AsyncMock(return_value=result)

        registry = MagicMock()

        output = await _check_availability(
            {
                "facility_id": "232465",
                "start_date": "2026-06-01",
                "end_date": "2026-06-30",
            },
            engine,
            registry,
        )

        data = json.loads(output)
        assert len(data["site_windows"]) <= 5


# -------------------------------------------------------------------
# Get drive time tool tests
# -------------------------------------------------------------------


class TestGetDriveTimeTool:
    """Test _get_drive_time() logic (async, falls back to haversine without token)."""

    async def test_get_drive_time_returns_minutes_and_readable(self, monkeypatch):
        """Drive time returns both minutes and readable format."""
        monkeypatch.delenv("MAPBOX_ACCESS_TOKEN", raising=False)
        result_json = await _get_drive_time(
            {
                "from_lat": 47.6,
                "from_lon": -122.3,
                "to_lat": 46.75,
                "to_lon": -121.8,
            }
        )

        data = json.loads(result_json)
        assert "drive_minutes" in data
        assert "readable" in data
        assert isinstance(data["drive_minutes"], int)
        assert data["drive_minutes"] > 0

    async def test_drive_time_readable_format_hours(self, monkeypatch):
        """Readable format includes hours when > 60 minutes."""
        monkeypatch.delenv("MAPBOX_ACCESS_TOKEN", raising=False)
        result_json = await _get_drive_time(
            {
                "from_lat": 47.6,
                "from_lon": -122.3,
                "to_lat": 42.0,
                "to_lon": -121.0,
            }
        )

        data = json.loads(result_json)
        if data["drive_minutes"] >= 60:
            assert "h" in data["readable"]

    async def test_drive_time_readable_format_minutes_only(self, monkeypatch):
        """Readable format is minutes only for short drives."""
        monkeypatch.delenv("MAPBOX_ACCESS_TOKEN", raising=False)
        result_json = await _get_drive_time(
            {
                "from_lat": 47.6,
                "from_lon": -122.3,
                "to_lat": 47.65,
                "to_lon": -122.25,
            }
        )

        data = json.loads(result_json)
        if data["drive_minutes"] < 60:
            assert "m" in data["readable"]
            assert "h" not in data["readable"]


# -------------------------------------------------------------------
# Get campground detail tool tests
# -------------------------------------------------------------------


class TestGetCampgroundDetailTool:
    """Test _get_campground_detail() logic."""

    def test_get_detail_found_returns_all_fields(self):
        """Detail for found campground returns all fields."""
        campground = make_campground(
            facility_id="232465",
            name="Ohanapecosh",
            state="WA",
            region="Mt. Rainier NP",
            latitude=46.75,
            longitude=-121.80,
            tags=["lakeside", "old-growth"],
            vibe="Rainier valley oasis",
            notes="Popular",
            rating=5,
            total_sites=205,
            drive_minutes_from_base=90,
        )

        registry = MagicMock()
        registry.get_by_facility_id.return_value = campground

        result_json = _get_campground_detail(
            {"facility_id": "232465"},
            registry,
        )

        data = json.loads(result_json)
        assert data["facility_id"] == "232465"
        assert data["name"] == "Ohanapecosh"
        assert data["state"] == "WA"
        assert data["region"] == "Mt. Rainier NP"
        assert data["latitude"] == 46.75
        assert data["longitude"] == -121.80
        assert "lakeside" in data["tags"]
        assert data["vibe"] == "Rainier valley oasis"
        assert data["notes"] == "Popular"
        assert data["rating"] == 5
        assert data["total_sites"] == 205
        assert data["drive_minutes_from_seattle"] == 90
        assert data["booking_system"] == "recgov"

    def test_get_detail_not_found_returns_error(self):
        """Detail for missing campground returns error."""
        registry = MagicMock()
        registry.get_by_facility_id.return_value = None

        result_json = _get_campground_detail(
            {"facility_id": "999999"},
            registry,
        )

        data = json.loads(result_json)
        assert "error" in data

    def test_get_detail_with_wa_state_system(self):
        """Detail correctly looks up WA State campground."""
        campground = make_campground(
            facility_id="-2147483624",
            booking_system=BookingSystem.WA_STATE,
        )

        registry = MagicMock()
        registry.get_by_facility_id.return_value = campground

        _get_campground_detail(
            {"facility_id": "-2147483624", "source": "wa_state"},
            registry,
        )

        registry.get_by_facility_id.assert_called_once()
        call_args = registry.get_by_facility_id.call_args
        assert call_args[1]["booking_system"] == BookingSystem.WA_STATE


# -------------------------------------------------------------------
# Geocode address tool tests
# -------------------------------------------------------------------


class TestGeocodeAddressTool:
    """Test _geocode_address() logic."""

    @pytest.mark.asyncio
    async def test_geocode_known_base_no_network(self):
        """Geocoding known base uses resolved coords."""
        result_json = await _geocode_address({"address": "seattle"})

        data = json.loads(result_json)
        assert "lat" in data
        assert "lon" in data
        assert data["source"] == "known_base"
        # Seattle should be roughly at 47.6°N
        assert abs(data["lat"] - 47.6) < 1.0

    @pytest.mark.asyncio
    async def test_geocode_unknown_address_mocked(self):
        """Geocoding unknown address uses nominatim."""
        with patch(
            "pnw_campsites.geo.geocode_address",
            new_callable=AsyncMock,
        ) as mock_geocode:
            mock_geocode.return_value = (47.5, -122.5)

            result_json = await _geocode_address(
                {"address": "Some Random Place"}
            )

            data = json.loads(result_json)
            assert data["lat"] == 47.5
            assert data["lon"] == -122.5
            assert data["source"] == "nominatim"
            mock_geocode.assert_called_once()

    @pytest.mark.asyncio
    async def test_geocode_bellevue_known_base(self):
        """Geocoding 'bellevue' returns known base coords."""
        result_json = await _geocode_address({"address": "bellevue"})

        data = json.loads(result_json)
        assert data["source"] == "known_base"
        # Bellevue is roughly at 47.6°N, 122.2°W
        assert abs(data["lat"] - 47.6) < 0.5
        assert abs(data["lon"] + 122.2) < 0.5


class TestExecuteTool:
    """Tests for execute_tool dispatcher."""

    @pytest.mark.asyncio
    async def test_execute_tool_handles_exception(self):
        """execute_tool catches exceptions and returns error JSON."""
        # Create mocks that will raise
        mock_engine = AsyncMock()
        mock_engine.search.side_effect = ValueError("Intentional error")
        mock_registry = MagicMock()

        result = await execute_tool(
            name="search_campgrounds",
            tool_input={
                "state": "WA",
                "start_date": "2026-06-01",
                "end_date": "2026-06-30",
            },
            engine=mock_engine,
            registry=mock_registry,
        )

        data = json.loads(result)
        assert "error" in data
        assert "Intentional error" in data["error"]

    @pytest.mark.asyncio
    async def test_execute_tool_unknown_tool(self):
        """execute_tool returns error for unknown tool name."""
        mock_engine = MagicMock()
        mock_registry = MagicMock()

        result = await execute_tool(
            name="unknown_tool_xyz",
            tool_input={},
            engine=mock_engine,
            registry=mock_registry,
        )

        data = json.loads(result)
        assert "error" in data
        assert "Unknown tool" in data["error"]
