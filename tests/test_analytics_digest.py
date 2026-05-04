"""Tests for the search analytics digest module."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pnw_campsites.analytics.digest import (
    format_digest,
    generate_weekly_digest,
    get_search_analytics,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_mock_db(searches: list[dict] | None = None):
    """Create a mock WatchDB with an in-memory SQLite connection."""
    conn = sqlite3.connect(":memory:")
    conn.execute("""
        CREATE TABLE search_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            params TEXT NOT NULL,
            result_count INTEGER DEFAULT 0,
            searched_at TEXT NOT NULL
        )
    """)

    if searches:
        for s in searches:
            conn.execute(
                "INSERT INTO search_history (user_id, params, result_count, searched_at) "
                "VALUES (?, ?, ?, ?)",
                (
                    s.get("user_id", 1),
                    json.dumps(s.get("params", {})),
                    s.get("result_count", 0),
                    s.get("searched_at", datetime.now().isoformat()),
                ),
            )
        conn.commit()

    mock_db = MagicMock()
    mock_db._conn = conn
    return mock_db


def _recent_iso(days_ago: int = 0) -> str:
    return (datetime.now() - timedelta(days=days_ago)).isoformat()


# ---------------------------------------------------------------------------
# get_search_analytics tests
# ---------------------------------------------------------------------------


class TestGetSearchAnalytics:
    """Tests for aggregating search history data."""

    def test_empty_db_returns_empty(self):
        db = _create_mock_db()
        result = get_search_analytics(db)
        assert result == {}

    def test_counts_total_searches(self):
        db = _create_mock_db([
            {"params": {"state": "WA"}, "searched_at": _recent_iso(1)},
            {"params": {"state": "OR"}, "searched_at": _recent_iso(2)},
            {"params": {"state": "WA"}, "searched_at": _recent_iso(3)},
        ])
        result = get_search_analytics(db)
        assert result["total_searches"] == 3

    def test_counts_zero_results(self):
        db = _create_mock_db([
            {"params": {}, "result_count": 5, "searched_at": _recent_iso(1)},
            {"params": {}, "result_count": 0, "searched_at": _recent_iso(2)},
            {"params": {}, "result_count": 0, "searched_at": _recent_iso(3)},
        ])
        result = get_search_analytics(db)
        assert result["zero_result_searches"] == 2
        assert result["zero_result_rate"] == 66.7

    def test_aggregates_by_state(self):
        db = _create_mock_db([
            {"params": {"state": "WA"}, "searched_at": _recent_iso(1)},
            {"params": {"state": "WA"}, "searched_at": _recent_iso(2)},
            {"params": {"state": "OR"}, "searched_at": _recent_iso(3)},
        ])
        result = get_search_analytics(db)
        assert result["states"]["WA"] == 2
        assert result["states"]["OR"] == 1

    def test_aggregates_by_tags(self):
        db = _create_mock_db([
            {"params": {"tags": "lakeside,fishing"}, "searched_at": _recent_iso(1)},
            {"params": {"tags": "lakeside"}, "searched_at": _recent_iso(2)},
            {"params": {"tags": "trails"}, "searched_at": _recent_iso(3)},
        ])
        result = get_search_analytics(db)
        assert result["tags"]["lakeside"] == 2
        assert result["tags"]["fishing"] == 1
        assert result["tags"]["trails"] == 1

    def test_aggregates_locations(self):
        db = _create_mock_db([
            {"params": {"from_location": "seattle"}, "searched_at": _recent_iso(1)},
            {"params": {"from_location": "seattle"}, "searched_at": _recent_iso(2)},
            {"params": {"from_location": "portland"}, "searched_at": _recent_iso(3)},
        ])
        result = get_search_analytics(db)
        assert result["locations"]["seattle"] == 2
        assert result["locations"]["portland"] == 1

    def test_excludes_old_searches(self):
        """Searches older than the window should be excluded."""
        db = _create_mock_db([
            {"params": {"state": "WA"}, "searched_at": _recent_iso(1)},
            {"params": {"state": "OR"}, "searched_at": _recent_iso(10)},
        ])
        result = get_search_analytics(db, since_days=7)
        assert result["total_searches"] == 1
        assert "OR" not in result.get("states", {})

    def test_handles_missing_params(self):
        """Searches with empty/null params shouldn't crash."""
        db = _create_mock_db([
            {"params": {}, "searched_at": _recent_iso(1)},
            {"params": {"state": "WA"}, "searched_at": _recent_iso(2)},
        ])
        result = get_search_analytics(db)
        assert result["total_searches"] == 2

    def test_tags_limited_to_top_10(self):
        """Should only return top 10 tags."""
        searches = []
        for i in range(15):
            searches.append({
                "params": {"tags": f"tag-{i}"},
                "searched_at": _recent_iso(1),
            })
        db = _create_mock_db(searches)
        result = get_search_analytics(db)
        assert len(result["tags"]) <= 10

    def test_states_sorted_by_frequency(self):
        db = _create_mock_db([
            {"params": {"state": "OR"}, "searched_at": _recent_iso(1)},
            {"params": {"state": "WA"}, "searched_at": _recent_iso(1)},
            {"params": {"state": "WA"}, "searched_at": _recent_iso(2)},
            {"params": {"state": "WA"}, "searched_at": _recent_iso(3)},
        ])
        result = get_search_analytics(db)
        states = list(result["states"].keys())
        assert states[0] == "WA"

    def test_handles_from_alias(self):
        """Some params use 'from' instead of 'from_location'."""
        db = _create_mock_db([
            {"params": {"from": "bozeman"}, "searched_at": _recent_iso(1)},
        ])
        result = get_search_analytics(db)
        assert result["locations"]["bozeman"] == 1


# ---------------------------------------------------------------------------
# format_digest tests
# ---------------------------------------------------------------------------


class TestFormatDigest:
    """Tests for formatting analytics into readable text."""

    def test_empty_analytics(self):
        result = format_digest({})
        assert "No searches" in result

    def test_includes_total(self):
        analytics = {
            "period_days": 7,
            "total_searches": 42,
            "zero_result_searches": 5,
            "zero_result_rate": 11.9,
            "states": {"WA": 30, "OR": 12},
            "tags": {"lakeside": 10},
            "locations": {"seattle": 25},
        }
        result = format_digest(analytics)
        assert "42" in result
        assert "WA" in result
        assert "lakeside" in result
        assert "seattle" in result

    def test_includes_zero_result_rate(self):
        analytics = {
            "period_days": 7,
            "total_searches": 10,
            "zero_result_searches": 3,
            "zero_result_rate": 30.0,
            "states": {},
            "tags": {},
            "locations": {},
        }
        result = format_digest(analytics)
        assert "30.0%" in result

    def test_handles_empty_sections(self):
        analytics = {
            "period_days": 7,
            "total_searches": 5,
            "zero_result_searches": 0,
            "zero_result_rate": 0,
            "states": {},
            "tags": {},
            "locations": {},
        }
        result = format_digest(analytics)
        assert "5" in result
        assert "States" not in result  # empty section omitted


# ---------------------------------------------------------------------------
# generate_weekly_digest tests
# ---------------------------------------------------------------------------


class TestGenerateWeeklyDigest:
    """Tests for the full digest generation pipeline."""

    @pytest.mark.asyncio
    async def test_skips_when_too_few_searches(self):
        """Should skip AI enhancement when <10 searches."""
        db = _create_mock_db([
            {"params": {"state": "WA"}, "searched_at": _recent_iso(1)},
            {"params": {"state": "OR"}, "searched_at": _recent_iso(2)},
        ])
        result = await generate_weekly_digest(db)
        assert "2" in result  # Should still format basic stats
        # No AI insights since < 10 searches

    @pytest.mark.asyncio
    async def test_includes_ai_insights_when_enough_data(self):
        """Should include AI insights when ≥10 searches."""
        searches = [
            {"params": {"state": "WA"}, "searched_at": _recent_iso(0)}
            for _ in range(12)
        ]
        db = _create_mock_db(searches)

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="- Users mostly search WA\n- Consider adding more tags")]

        with (
            patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}),
            patch("posthog.ai.anthropic.AsyncAnthropic") as mock_cls,
        ):
            mock_client = AsyncMock()
            mock_cls.return_value = mock_client
            mock_client.messages.create.return_value = mock_response

            result = await generate_weekly_digest(db)

        assert "AI Insights" in result
        assert "Users mostly search WA" in result

    @pytest.mark.asyncio
    async def test_graceful_degradation_on_api_failure(self):
        """Should return basic report if AI enhancement fails."""
        searches = [
            {"params": {"state": "WA"}, "searched_at": _recent_iso(0)}
            for _ in range(12)
        ]
        db = _create_mock_db(searches)

        with patch("posthog.ai.anthropic.AsyncAnthropic") as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value = mock_client
            mock_client.messages.create.side_effect = Exception("API down")

            result = await generate_weekly_digest(db)

        assert "12" in result  # Basic stats still present
        assert "AI Insights" not in result

    @pytest.mark.asyncio
    async def test_empty_db_returns_message(self):
        db = _create_mock_db()
        result = await generate_weekly_digest(db)
        assert "No searches" in result
