"""Tests for campground comparison endpoint."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import pnw_campsites.api as api_module


class TestCompare:
    def test_compare_two_campgrounds(self, api_client: TestClient):
        from tests.conftest import make_campground
        cg1 = make_campground(facility_id="aaa", name="Lake Camp", state="WA", tags=["lakeside"])
        cg2 = make_campground(facility_id="bbb", name="Forest Camp", state="WA", tags=["forest"])
        api_module._registry.get_by_facility_id.side_effect = lambda fid, *a, **kw: {
            "aaa": cg1, "bbb": cg2,
        }.get(fid)

        resp = api_client.post("/api/compare", json={
            "facility_ids": ["aaa", "bbb"],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["campgrounds"]) == 2
        assert data["campgrounds"][0]["name"] == "Lake Camp"
        assert data["campgrounds"][1]["name"] == "Forest Camp"
        # No API key in test → narrative is None
        assert data["narrative"] is None

    def test_compare_three_campgrounds(self, api_client: TestClient):
        from tests.conftest import make_campground
        cgs = {f"c{i}": make_campground(facility_id=f"c{i}", name=f"Camp {i}") for i in range(3)}
        api_module._registry.get_by_facility_id.side_effect = lambda fid, *a, **kw: cgs.get(fid)

        resp = api_client.post("/api/compare", json={
            "facility_ids": ["c0", "c1", "c2"],
        })
        assert resp.status_code == 200
        assert len(resp.json()["campgrounds"]) == 3

    def test_compare_one_campground_fails(self, api_client: TestClient):
        resp = api_client.post("/api/compare", json={
            "facility_ids": ["only-one"],
        })
        assert resp.status_code == 422

    def test_compare_four_campgrounds_fails(self, api_client: TestClient):
        resp = api_client.post("/api/compare", json={
            "facility_ids": ["a", "b", "c", "d"],
        })
        assert resp.status_code == 422

    def test_compare_unknown_campground_404(self, api_client: TestClient):
        api_module._registry.get_by_facility_id.return_value = None
        resp = api_client.post("/api/compare", json={
            "facility_ids": ["nope", "also-nope"],
        })
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_narrative_returns_none_without_api_key(self):
        from pnw_campsites.routes.compare import _generate_narrative
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": ""}):
            result = await _generate_narrative([{"name": "A", "state": "WA", "tags": [], "vibe": "", "drive_minutes": 60, "total_sites": 20}], "")
        assert result is None

    @pytest.mark.asyncio
    async def test_narrative_returns_text(self):
        from pnw_campsites.routes.compare import _generate_narrative
        mock_content = MagicMock()
        mock_content.text = "Lake Camp is closer but Forest Camp has better shade."
        mock_response = MagicMock()
        mock_response.content = [mock_content]
        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        with (
            patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}),
            patch("posthog.ai.anthropic.AsyncAnthropic", return_value=mock_client),
        ):
            result = await _generate_narrative(
                [{"name": "A", "state": "WA", "tags": [], "vibe": "", "drive_minutes": 60, "total_sites": 20}],
                "2026-06-01",
            )
        assert "Lake Camp" in result
