"""Tests for historical pattern extraction and booking tips."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import pnw_campsites.api as api_module
from pnw_campsites.analytics.patterns import (
    MIN_OBSERVATION_DAYS,
    extract_booking_tips,
    get_availability_summary,
)


def _seed_history(watch_db, campground_id: str = "232465", days: int = 40):
    """Seed synthetic availability_daily data."""
    base = date(2026, 1, 1)
    records = []
    for d in range(days):
        dt = base + timedelta(days=d)
        observed = (datetime(2026, 1, 1) + timedelta(days=d)).isoformat()
        # Weekdays more available, weekends mostly reserved
        status = "Available" if dt.weekday() < 5 else "Reserved"
        records.append((campground_id, "site-1", dt.isoformat(), status, "recgov", observed, observed, 1))
    watch_db._conn.executemany(
        "INSERT INTO availability_daily"
        " (campground_id, site_id, date, status, source,"
        "  first_seen, last_seen, observation_count)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        records,
    )
    watch_db._conn.commit()


class TestAvailabilitySummary:
    def test_returns_none_for_insufficient_data(self, watch_db):
        _seed_history(watch_db, days=10)
        result = get_availability_summary(watch_db, "232465")
        assert result is None

    def test_returns_summary_with_enough_data(self, watch_db):
        _seed_history(watch_db, days=40)
        result = get_availability_summary(watch_db, "232465")
        assert result is not None
        assert result["observation_days"] >= MIN_OBSERVATION_DAYS
        assert "day_of_week_availability" in result
        assert result["fill_rate_pct"] >= 0

    def test_weekday_rates_higher_than_weekend(self, watch_db):
        _seed_history(watch_db, days=40)
        result = get_availability_summary(watch_db, "232465")
        assert result is not None
        rates = result["day_of_week_availability"]
        # Weekdays should have higher availability than weekends
        weekday_avg = sum(rates.get(d, 0) for d in ["Monday", "Tuesday", "Wednesday"]) / 3
        weekend_avg = sum(rates.get(d, 0) for d in ["Saturday", "Sunday"]) / 2
        assert weekday_avg > weekend_avg

    def test_returns_none_for_unknown_campground(self, watch_db):
        assert get_availability_summary(watch_db, "nonexistent") is None


class TestExtractBookingTips:
    @pytest.mark.asyncio
    async def test_returns_empty_for_insufficient_data(self, watch_db):
        _seed_history(watch_db, days=10)
        tips = await extract_booking_tips(watch_db, "232465")
        assert tips == []

    @pytest.mark.asyncio
    async def test_returns_basic_tip_without_api_key(self, watch_db):
        _seed_history(watch_db, days=40)
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": ""}):
            tips = await extract_booking_tips(watch_db, "232465")
        assert len(tips) >= 1
        assert any("Weekday" in t or "availability" in t.lower() for t in tips)

    @pytest.mark.asyncio
    async def test_returns_llm_tips_with_api_key(self, watch_db):
        _seed_history(watch_db, days=40)
        mock_content = MagicMock()
        mock_content.text = '["Book midweek for best selection", "Weekends fill fast"]'
        mock_response = MagicMock()
        mock_response.content = [mock_content]
        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        with (
            patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}),
            patch("anthropic.AsyncAnthropic", return_value=mock_client),
        ):
            tips = await extract_booking_tips(watch_db, "232465", "Ohanapecosh")
        assert len(tips) == 2
        assert "midweek" in tips[0]

    @pytest.mark.asyncio
    async def test_truncates_long_tips(self, watch_db):
        _seed_history(watch_db, days=40)
        mock_content = MagicMock()
        mock_content.text = f'["{"A" * 300}"]'
        mock_response = MagicMock()
        mock_response.content = [mock_content]
        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        with (
            patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}),
            patch("anthropic.AsyncAnthropic", return_value=mock_client),
        ):
            tips = await extract_booking_tips(watch_db, "232465")
        assert len(tips[0]) <= 200


class TestBookingTipsEndpoint:
    def test_tips_endpoint_returns_empty_for_unknown(self, api_client: TestClient):
        api_module._registry.get_by_facility_id.return_value = None
        resp = api_client.get("/api/campgrounds/unknown/tips")
        assert resp.status_code == 200
        assert resp.json()["tips"] == []

    def test_tips_endpoint_returns_cached_tips(self, api_client: TestClient):
        from tests.conftest import make_campground
        cg = make_campground(facility_id="232465", booking_tips='["Tip 1", "Tip 2"]')
        api_module._registry.get_by_facility_id.return_value = cg
        resp = api_client.get("/api/campgrounds/232465/tips")
        assert resp.status_code == 200
        data = resp.json()
        assert data["tips"] == ["Tip 1", "Tip 2"]
