"""Tests for template watch creation, expansion, and polling."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

import pnw_campsites.api as api_module
from pnw_campsites.monitor.expand import expand_template
from tests.conftest import make_campground, signup_and_auth

EMAIL = "template@test.com"


class TestExpandTemplate:
    """Unit tests for expand_template."""

    def test_expands_matching_campgrounds(self):
        registry = MagicMock()
        registry.search.return_value = [
            make_campground(facility_id="aaa", drive_minutes_from_base=60),
            make_campground(facility_id="bbb", drive_minutes_from_base=120),
        ]
        result = expand_template('{"state": "WA"}', registry)
        assert [c.facility_id for c in result] == ["aaa", "bbb"]

    def test_caps_at_20(self):
        registry = MagicMock()
        registry.search.return_value = [
            make_campground(facility_id=str(i), drive_minutes_from_base=i * 10)
            for i in range(30)
        ]
        result = expand_template('{"state": "WA"}', registry)
        assert len(result) == 20

    def test_sorts_by_drive_time(self):
        registry = MagicMock()
        registry.search.return_value = [
            make_campground(facility_id="far", drive_minutes_from_base=300),
            make_campground(facility_id="close", drive_minutes_from_base=30),
            make_campground(facility_id="mid", drive_minutes_from_base=120),
        ]
        result = expand_template('{"state": "WA"}', registry)
        assert [c.facility_id for c in result] == ["close", "mid", "far"]

    def test_invalid_json_returns_empty(self):
        registry = MagicMock()
        assert expand_template("not json", registry) == []

    def test_empty_params_returns_all(self):
        registry = MagicMock()
        registry.search.return_value = [make_campground(facility_id="x")]
        result = expand_template("{}", registry)
        assert [c.facility_id for c in result] == ["x"]

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
        _, headers = signup_and_auth(api_client, EMAIL, display_name="")
        resp = api_client.post("/api/watches", json={
            "start_date": "2026-07-01",
            "end_date": "2026-07-31",
            "watch_type": "template",
            "search_params": {"state": "WA", "tags": ["lakeside"]},
            "name": "WA Lakeside",
        }, headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["watch_type"] == "template"
        assert data["search_params"]["state"] == "WA"

    def test_template_without_search_params_fails(self, api_client: TestClient):
        _, headers = signup_and_auth(api_client, EMAIL, display_name="")
        resp = api_client.post("/api/watches", json={
            "start_date": "2026-07-01",
            "end_date": "2026-07-31",
            "watch_type": "template",
        }, headers=headers)
        assert resp.status_code == 422

    def test_single_watch_without_facility_id_fails(self, api_client: TestClient):
        _, headers = signup_and_auth(api_client, EMAIL, display_name="")
        resp = api_client.post("/api/watches", json={
            "start_date": "2026-07-01",
            "end_date": "2026-07-31",
            "watch_type": "single",
        }, headers=headers)
        assert resp.status_code == 422

    def test_template_watch_appears_in_list(self, api_client: TestClient):
        _, headers = signup_and_auth(api_client, EMAIL, display_name="")
        api_client.post("/api/watches", json={
            "start_date": "2026-07-01",
            "end_date": "2026-07-31",
            "watch_type": "template",
            "search_params": {"state": "OR"},
            "name": "OR Pattern",
        }, headers=headers)
        resp = api_client.get("/api/watches", headers=headers)
        watches = resp.json()
        assert any(w["watch_type"] == "template" for w in watches)

    def test_single_watch_still_works(self, api_client: TestClient):
        _, headers = signup_and_auth(api_client, EMAIL, display_name="")
        api_module._registry.get_by_facility_id.return_value = make_campground(
            facility_id="232465",
        )
        resp = api_client.post("/api/watches", json={
            "facility_id": "232465",
            "start_date": "2026-07-01",
            "end_date": "2026-07-31",
        }, headers=headers)
        assert resp.status_code == 200
        assert resp.json()["watch_type"] == "single"


class TestWatchInputBounds:
    """SEC-05: watch input is bounded and anonymous creation is capped."""

    def _post(self, client, headers=None, **fields):
        body = {"start_date": "2026-07-01", "end_date": "2026-07-31", **fields}
        return client.post("/api/watches", json=body, headers=headers or {})

    def test_template_requires_sign_in(self, api_client: TestClient):
        resp = self._post(api_client, watch_type="template",
                          search_params={"state": "WA"})
        assert resp.status_code == 401

    @pytest.mark.parametrize("params", [
        {"state": "WA", "evil": "x"},
        {"tags": [f"t{i}" for i in range(11)]},
        {"tags": ["x" * 41]},
        {"max_drive": 0},
        {"max_drive": 100_000},
        {"name": "n" * 101},
        {"state": "Washington"},
    ])
    def test_search_params_are_validated(self, api_client: TestClient, params):
        _, headers = signup_and_auth(api_client, EMAIL, display_name="")
        resp = self._post(api_client, headers, watch_type="template",
                          search_params=params)
        assert resp.status_code == 422

    def test_search_params_stored_without_unset_keys(self, api_client: TestClient):
        _, headers = signup_and_auth(api_client, EMAIL, display_name="")
        resp = self._post(api_client, headers, watch_type="template",
                          search_params={"state": "WA", "max_drive": 120})
        assert resp.json()["search_params"] == {"state": "WA", "max_drive": 120}

    @pytest.mark.parametrize("days", [[7], [-1], [0, 1, 2, 3, 4, 5, 6, 0]])
    def test_days_of_week_bounded(self, api_client: TestClient, days):
        resp = self._post(api_client, facility_id="232465", days_of_week=days)
        assert resp.status_code == 422

    def test_anonymous_creation_capped_per_ip(self, api_client: TestClient, monkeypatch):
        """Dropping the session cookie resets the per-token watch cap, so
        anonymous creation is also counted per client IP."""
        import pnw_campsites.routes.watches as watches_mod

        monkeypatch.setattr(watches_mod, "_ANON_WATCH_DAILY_LIMIT", 2)
        api_module._registry.get_by_facility_id.return_value = make_campground(
            facility_id="232465",
        )
        codes = []
        for i in range(3):
            api_client.cookies.clear()
            codes.append(self._post(
                api_client, facility_id="232465", start_date=f"2026-07-0{i + 1}",
            ).status_code)
        assert codes == [200, 200, 429]
