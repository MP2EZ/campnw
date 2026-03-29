"""Tests for template watch creation, expansion, and polling."""

from __future__ import annotations

from unittest.mock import MagicMock

from fastapi.testclient import TestClient

import pnw_campsites.api as api_module
from pnw_campsites.monitor.expand import expand_template


def _signup(client: TestClient) -> dict:
    resp = client.post(
        "/api/auth/signup",
        json={"email": "template@test.com", "password": "testpass123"},
    )
    assert resp.status_code == 200
    return resp.json()


class TestExpandTemplate:
    """Unit tests for expand_template."""

    def test_expands_matching_campgrounds(self):
        from tests.conftest import make_campground
        registry = MagicMock()
        registry.search.return_value = [
            make_campground(facility_id="aaa", drive_minutes_from_base=60),
            make_campground(facility_id="bbb", drive_minutes_from_base=120),
        ]
        result = expand_template('{"state": "WA"}', registry)
        assert result == ["aaa", "bbb"]

    def test_caps_at_20(self):
        from tests.conftest import make_campground
        registry = MagicMock()
        registry.search.return_value = [
            make_campground(facility_id=str(i), drive_minutes_from_base=i * 10)
            for i in range(30)
        ]
        result = expand_template('{"state": "WA"}', registry)
        assert len(result) == 20

    def test_sorts_by_drive_time(self):
        from tests.conftest import make_campground
        registry = MagicMock()
        registry.search.return_value = [
            make_campground(facility_id="far", drive_minutes_from_base=300),
            make_campground(facility_id="close", drive_minutes_from_base=30),
            make_campground(facility_id="mid", drive_minutes_from_base=120),
        ]
        result = expand_template('{"state": "WA"}', registry)
        assert result == ["close", "mid", "far"]

    def test_invalid_json_returns_empty(self):
        registry = MagicMock()
        assert expand_template("not json", registry) == []

    def test_empty_params_returns_all(self):
        from tests.conftest import make_campground
        registry = MagicMock()
        registry.search.return_value = [make_campground(facility_id="x")]
        result = expand_template("{}", registry)
        assert result == ["x"]

    def test_passes_filters_to_registry(self):
        registry = MagicMock()
        registry.search.return_value = []
        expand_template(
            '{"state": "WA", "tags": ["lakeside"], "max_drive": 120}',
            registry,
        )
        registry.search.assert_called_once_with(
            state="WA", tags=["lakeside"], max_drive_minutes=120, name_like=None,
        )


class TestTemplateWatchAPI:
    """Tests for template watch creation via API."""

    def test_create_template_watch(self, api_client: TestClient):
        _signup(api_client)
        resp = api_client.post("/api/watches", json={
            "start_date": "2026-07-01",
            "end_date": "2026-07-31",
            "watch_type": "template",
            "search_params": {"state": "WA", "tags": ["lakeside"]},
            "name": "WA Lakeside",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["watch_type"] == "template"
        assert data["search_params"]["state"] == "WA"

    def test_template_without_search_params_fails(self, api_client: TestClient):
        _signup(api_client)
        resp = api_client.post("/api/watches", json={
            "start_date": "2026-07-01",
            "end_date": "2026-07-31",
            "watch_type": "template",
        })
        assert resp.status_code == 422

    def test_single_watch_without_facility_id_fails(self, api_client: TestClient):
        _signup(api_client)
        resp = api_client.post("/api/watches", json={
            "start_date": "2026-07-01",
            "end_date": "2026-07-31",
            "watch_type": "single",
        })
        assert resp.status_code == 422

    def test_template_watch_appears_in_list(self, api_client: TestClient):
        _signup(api_client)
        api_client.post("/api/watches", json={
            "start_date": "2026-07-01",
            "end_date": "2026-07-31",
            "watch_type": "template",
            "search_params": {"state": "OR"},
            "name": "OR Pattern",
        })
        resp = api_client.get("/api/watches")
        watches = resp.json()
        assert any(w["watch_type"] == "template" for w in watches)

    def test_single_watch_still_works(self, api_client: TestClient):
        from tests.conftest import make_campground
        _signup(api_client)
        api_module._registry.get_by_facility_id.return_value = make_campground(
            facility_id="232465",
        )
        resp = api_client.post("/api/watches", json={
            "facility_id": "232465",
            "start_date": "2026-07-01",
            "end_date": "2026-07-31",
        })
        assert resp.status_code == 200
        assert resp.json()["watch_type"] == "single"
