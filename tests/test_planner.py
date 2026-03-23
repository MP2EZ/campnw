"""Tests for the trip planner module (tools + API endpoints)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from pnw_campsites.planner.tools import TOOLS, execute_tool
from pnw_campsites.search.engine import SearchResults

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
