"""Tests for the timing middleware and /api/perf endpoint."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

import pnw_campsites.api as api_module


class TestPerfEndpoint:
    """Tests for GET /api/perf."""

    def test_perf_no_data_returns_message(self, api_client: TestClient):
        """When no searches have been recorded, returns a message."""
        api_module._search_timings.clear()
        response = api_client.get("/api/perf")
        assert response.status_code == 200
        assert response.json() == {"message": "No data yet"}

    def test_perf_with_samples_returns_stats(self, api_client: TestClient):
        """With recorded timings, returns p50/p95/p99/mean/count."""
        api_module._search_timings.clear()
        for ms in [100, 200, 300, 400, 500]:
            api_module._search_timings.append(ms)

        response = api_client.get("/api/perf")
        data = response.json()

        assert data["count"] == 5
        assert data["p50_ms"] == 300
        assert data["mean_ms"] == 300
        assert data["target_ms"] == 4000
        # With <20 samples, p95 falls back to max
        assert data["p95_ms"] == 500

    def test_perf_p95_uses_percentile_with_enough_samples(self, api_client: TestClient):
        """With 20+ samples, p95 uses actual 95th percentile index."""
        api_module._search_timings.clear()
        # 20 values: 100, 200, ..., 2000
        for i in range(1, 21):
            api_module._search_timings.append(i * 100)

        response = api_client.get("/api/perf")
        data = response.json()

        assert data["count"] == 20
        # sorted[int(20 * 0.95)] = sorted[19] = 2000
        assert data["p95_ms"] == 2000

    def test_perf_p99_fallback_under_100_samples(self, api_client: TestClient):
        """With <100 samples, p99 falls back to max value."""
        api_module._search_timings.clear()
        for i in range(50):
            api_module._search_timings.append(i * 10)

        response = api_client.get("/api/perf")
        data = response.json()

        assert data["count"] == 50
        # <100 samples → p99 = max
        assert data["p99_ms"] == 490


class TestTimingMiddleware:
    """Tests for the Server-Timing header middleware."""

    def test_server_timing_header_on_any_request(self, api_client: TestClient):
        """All responses include Server-Timing header."""
        response = api_client.get("/api/perf")
        assert "server-timing" in response.headers
        assert response.headers["server-timing"].startswith("total;dur=")

    def test_search_requests_recorded_in_timings(self, api_client: TestClient):
        """Requests to /api/search paths get recorded in _search_timings."""
        api_module._search_timings.clear()
        mock_results = MagicMock()
        mock_results.results = []
        mock_results.campgrounds_checked = 0
        mock_results.diagnosis = None
        api_module._engine.search = AsyncMock(return_value=mock_results)

        api_client.get("/api/search?start_date=2026-06-01&end_date=2026-06-30&state=WA")

        assert len(api_module._search_timings) >= 1

    def test_non_search_requests_not_recorded(self, api_client: TestClient):
        """Non-search requests don't add to _search_timings."""
        api_module._search_timings.clear()

        api_client.get("/api/perf")

        assert len(api_module._search_timings) == 0
