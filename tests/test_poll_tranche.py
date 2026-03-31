"""Tests for _poll_tranche and poll_all with template watches."""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pnw_campsites.monitor.db import Watch, WatchDB
from pnw_campsites.monitor.watcher import poll_all, poll_watch
from pnw_campsites.registry.models import BookingSystem, CampgroundAvailability


def _mock_availability(facility_id: str = "232465"):
    """Return a real Pydantic model so model_dump_json works for caching."""
    return CampgroundAvailability(
        facility_id=facility_id,
        campsites={},
    )


class TestPollWatch:
    @pytest.mark.asyncio
    async def test_poll_recgov_watch(self, watch_db):
        """poll_watch calls recgov provider for RECGOV watches."""
        watch = watch_db.add_watch(Watch(
            facility_id="232465", name="Test",
            start_date="2026-06-01", end_date="2026-06-30",
        ))
        mock_recgov = AsyncMock()
        mock_recgov.get_availability_range = AsyncMock(
            return_value=_mock_availability(),
        )
        result = await poll_watch(
            watch, mock_recgov, None, watch_db,
        )
        assert result.error is None
        mock_recgov.get_availability_range.assert_called_once()

    @pytest.mark.asyncio
    async def test_poll_or_state_watch(self, watch_db):
        """poll_watch calls reserveamerica for OR_STATE watches."""
        from tests.conftest import make_campground

        watch = watch_db.add_watch(Watch(
            facility_id="409402", name="OR Park",
            start_date="2026-06-01", end_date="2026-06-30",
        ))
        registry = MagicMock()
        cg = make_campground(
            facility_id="409402",
            booking_system=BookingSystem.OR_STATE,
        )
        registry.get_by_facility_id.return_value = cg

        mock_ra = AsyncMock()
        mock_ra.get_availability = AsyncMock(
            return_value=_mock_availability("409402"),
        )
        result = await poll_watch(
            watch, None, None, watch_db,
            registry=registry,
            reserveamerica=mock_ra,
        )
        assert result.error is None
        mock_ra.get_availability.assert_called_once()

    @pytest.mark.asyncio
    async def test_poll_or_state_without_client_raises(self, watch_db):
        """poll_watch returns error if OR_STATE watch but no RA client."""
        from tests.conftest import make_campground

        watch = watch_db.add_watch(Watch(
            facility_id="409402", name="OR Park",
            start_date="2026-06-01", end_date="2026-06-30",
        ))
        registry = MagicMock()
        cg = make_campground(
            facility_id="409402",
            booking_system=BookingSystem.OR_STATE,
        )
        registry.get_by_facility_id.return_value = cg

        result = await poll_watch(
            watch, None, None, watch_db,
            registry=registry,
            reserveamerica=None,
        )
        assert result.error is not None
        assert "ReserveAmerica" in result.error


class TestPollAllWithTemplateWatches:
    @pytest.mark.asyncio
    async def test_template_watch_expands(self, watch_db):
        """poll_all expands template watches into virtual single watches."""
        watch = watch_db.add_watch(Watch(
            facility_id="",
            name="WA Lakeside",
            start_date="2026-06-01",
            end_date="2026-06-30",
            watch_type="template",
            search_params='{"state": "WA", "tags": ["lakeside"]}',
        ))

        from tests.conftest import make_campground
        cg_a = make_campground(facility_id="aaa", drive_minutes_from_base=60)
        cg_b = make_campground(facility_id="bbb", drive_minutes_from_base=120)
        registry = MagicMock()
        registry.search.return_value = [cg_a, cg_b]
        # poll_watch calls get_by_facility_id to determine booking system —
        # return real Campground objects so booking_system.value is a string,
        # not a MagicMock (which would crash SQLite bind).
        registry.get_by_facility_id.side_effect = lambda fid: {
            "aaa": cg_a, "bbb": cg_b,
        }.get(fid)

        mock_recgov = AsyncMock()
        mock_recgov.get_availability_range = AsyncMock(
            return_value=_mock_availability(),
        )

        results = await poll_all(
            mock_recgov, None, watch_db, registry,
        )
        # Should have polled 2 expanded campgrounds
        assert mock_recgov.get_availability_range.call_count == 2

    @pytest.mark.asyncio
    async def test_single_watch_not_expanded(self, watch_db):
        """poll_all doesn't expand single watches."""
        watch = watch_db.add_watch(Watch(
            facility_id="232465",
            name="Ohanapecosh",
            start_date="2026-06-01",
            end_date="2026-06-30",
            watch_type="single",
        ))

        mock_recgov = AsyncMock()
        mock_recgov.get_availability_range = AsyncMock(
            return_value=_mock_availability(),
        )

        results = await poll_all(
            mock_recgov, None, watch_db, None,
        )
        assert mock_recgov.get_availability_range.call_count == 1
