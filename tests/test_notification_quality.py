"""Tests for notification quality feedback loop."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pnw_campsites.analytics.notification_quality import (
    MIN_NOTIFICATIONS,
    generate_quality_report,
    get_notification_stats,
)


def _seed_notifications(watch_db, month: str = "2026-03", count: int = 60):
    """Seed synthetic notification_log data."""
    # Create a watch to satisfy FK constraint
    from pnw_campsites.monitor.db import Watch
    watch = watch_db.add_watch(Watch(
        facility_id="232465", name="Test", start_date="2026-06-01",
        end_date="2026-06-30",
    ))
    records = []
    for i in range(count):
        day = (i % 28) + 1
        sent_at = f"{month}-{day:02d}T12:00:00"
        channel = "web_push" if i % 3 == 0 else "ntfy"
        status = "sent" if i % 5 != 0 else "failed"
        records.append((watch.id, channel, status, i % 4, sent_at))
    watch_db._conn.executemany(
        "INSERT INTO notification_log"
        " (watch_id, channel, status, changes_count, sent_at)"
        " VALUES (?, ?, ?, ?, ?)",
        records,
    )
    watch_db._conn.commit()


class TestNotificationStats:
    def test_returns_none_for_insufficient_data(self, watch_db):
        _seed_notifications(watch_db, count=10)
        result = get_notification_stats(watch_db, "2026-03")
        assert result is None

    def test_returns_stats_with_enough_data(self, watch_db):
        _seed_notifications(watch_db, count=60)
        result = get_notification_stats(watch_db, "2026-03")
        assert result is not None
        assert result["total_notifications"] == 60
        assert "by_channel" in result
        assert "by_status" in result
        assert result["sent_rate"] >= 0

    def test_channels_counted_correctly(self, watch_db):
        _seed_notifications(watch_db, count=60)
        result = get_notification_stats(watch_db, "2026-03")
        assert "web_push" in result["by_channel"]
        assert "ntfy" in result["by_channel"]
        total = sum(result["by_channel"].values())
        assert total == 60

    def test_wrong_month_returns_none(self, watch_db):
        _seed_notifications(watch_db, month="2026-03", count=60)
        result = get_notification_stats(watch_db, "2026-04")
        assert result is None


class TestGenerateReport:
    @pytest.mark.asyncio
    async def test_skips_insufficient_data(self, watch_db):
        _seed_notifications(watch_db, count=10)
        result = await generate_quality_report(watch_db, "2026-03")
        assert result is None

    @pytest.mark.asyncio
    async def test_generates_report_without_llm(self, watch_db):
        _seed_notifications(watch_db, count=60)
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": ""}):
            result = await generate_quality_report(watch_db, "2026-03")
        assert result is not None
        assert result["stats"]["total_notifications"] == 60
        assert result["analysis"] is None
        # Verify stored in DB
        row = watch_db._conn.execute(
            "SELECT * FROM analytics_digests WHERE digest_type='notification_quality'"
        ).fetchone()
        assert row is not None

    @pytest.mark.asyncio
    async def test_generates_report_with_llm(self, watch_db):
        _seed_notifications(watch_db, count=60)
        mock_content = MagicMock()
        mock_content.text = "Send notifications earlier in the day for better engagement."
        mock_response = MagicMock()
        mock_response.content = [mock_content]
        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        with (
            patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}),
            patch("posthog.ai.anthropic.AsyncAnthropic", return_value=mock_client),
        ):
            result = await generate_quality_report(watch_db, "2026-03")
        assert result is not None
        assert "earlier" in result["analysis"]

    @pytest.mark.asyncio
    async def test_idempotent_upsert(self, watch_db):
        """Running twice for same month should update, not duplicate."""
        _seed_notifications(watch_db, count=60)
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": ""}):
            await generate_quality_report(watch_db, "2026-03")
            await generate_quality_report(watch_db, "2026-03")
        count = watch_db._conn.execute(
            "SELECT COUNT(*) FROM analytics_digests"
            " WHERE digest_type='notification_quality' AND period='2026-03'"
        ).fetchone()[0]
        assert count == 1
