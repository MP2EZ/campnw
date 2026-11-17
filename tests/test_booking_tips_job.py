"""The weekly job that rewrites booking tips on campground pages."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pnw_campsites.api as api_module


async def test_job_refreshes_tips_with_app_databases():
    db, registry = MagicMock(), MagicMock()
    refresh = AsyncMock(return_value=3)
    with (
        patch.object(api_module, "_watch_db", db),
        patch.object(api_module, "_registry", registry),
        patch("pnw_campsites.analytics.patterns.refresh_all_tips", refresh),
    ):
        await api_module._refresh_booking_tips()
    refresh.assert_awaited_once_with(db, registry)


async def test_job_without_db_is_a_noop():
    refresh = AsyncMock()
    with (
        patch.object(api_module, "_watch_db", None),
        patch("pnw_campsites.analytics.patterns.refresh_all_tips", refresh),
    ):
        await api_module._refresh_booking_tips()
    refresh.assert_not_awaited()
