"""Tests for natural language search query parser."""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pnw_campsites.search.nl_parser import (
    _SEARCH_PARAMS_TOOL,
    _build_system_prompt,
    parse_natural_query,
)

# ---------------------------------------------------------------------------
# System prompt tests
# ---------------------------------------------------------------------------


class TestBuildSystemPrompt:
    """Tests for the system prompt builder."""

    def test_includes_today_date(self):
        prompt = _build_system_prompt(date(2026, 3, 28))
        assert "2026-03-28" in prompt

    def test_includes_day_of_week(self):
        prompt = _build_system_prompt(date(2026, 3, 28))
        assert "Saturday" in prompt

    def test_includes_this_friday(self):
        """This Friday from a Saturday should be the NEXT Friday."""
        prompt = _build_system_prompt(date(2026, 3, 28))  # Saturday
        # Next Friday = April 3
        assert "2026-04-03" in prompt

    def test_includes_next_friday(self):
        """Next Friday should be 7 days after this Friday."""
        prompt = _build_system_prompt(date(2026, 3, 28))  # Saturday
        # This Friday = Apr 3, Next Friday = Apr 10
        assert "2026-04-10" in prompt

    def test_friday_from_friday(self):
        """On a Friday, 'this Friday' should be the NEXT Friday (not today)."""
        prompt = _build_system_prompt(date(2026, 4, 3))  # Friday
        # Should resolve to Apr 10, not today
        assert "2026-04-10" in prompt

    def test_includes_valid_states(self):
        prompt = _build_system_prompt(date(2026, 6, 1))
        for state in ("WA", "OR", "ID", "MT", "WY"):
            assert state in prompt
        assert "California" in prompt

    def test_includes_date_inference_rules(self):
        prompt = _build_system_prompt(date(2026, 6, 1))
        assert "this weekend" in prompt.lower()
        assert "next weekend" in prompt.lower()
        assert "july 4th" in prompt.lower() or "labor day" in prompt.lower()


# ---------------------------------------------------------------------------
# Tool schema tests
# ---------------------------------------------------------------------------


class TestToolSchema:
    """Tests for the search params tool schema."""

    def test_schema_has_required_fields(self):
        props = _SEARCH_PARAMS_TOOL["input_schema"]["properties"]
        assert "start_date" in props
        assert "end_date" in props
        assert "state" in props
        assert "tags" in props
        assert "from_location" in props
        assert "name_like" in props

    def test_state_enum_includes_new_states(self):
        props = _SEARCH_PARAMS_TOOL["input_schema"]["properties"]
        enum = props["state"]["enum"]
        assert "MT" in enum
        assert "WY" in enum
        assert "CA" in enum

    def test_no_required_fields(self):
        """All fields should be optional for NL parsing."""
        required = _SEARCH_PARAMS_TOOL["input_schema"].get("required", [])
        assert required == []

    def test_tags_description_mentions_mapping(self):
        """Tag description should include vocabulary mapping hints."""
        props = _SEARCH_PARAMS_TOOL["input_schema"]["properties"]
        desc = props["tags"]["description"]
        assert "waterfront" in desc
        assert "dog-friendly" in desc


# ---------------------------------------------------------------------------
# Parse function tests (mocked Anthropic client)
# ---------------------------------------------------------------------------


def _mock_tool_response(tool_input: dict):
    """Create a mock Anthropic response with a tool_use block."""
    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.name = "set_search_params"
    tool_block.input = tool_input

    response = MagicMock()
    response.content = [tool_block]
    return response


class TestParseNaturalQuery:
    """Tests for parse_natural_query with mocked API calls."""

    @pytest.mark.asyncio
    async def test_basic_tag_extraction(self):
        """'lakeside camping' should extract lakeside tag."""
        mock_response = _mock_tool_response({
            "start_date": "2026-04-11",
            "end_date": "2026-05-11",
            "tags": ["lakeside"],
        })

        with patch("posthog.ai.anthropic.AsyncAnthropic") as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value = mock_client
            mock_client.messages.create.return_value = mock_response

            result = await parse_natural_query(
                "lakeside camping", "test-key", today=date(2026, 3, 28),
            )

        assert result["tags"] == ["lakeside"]
        assert "start_date" in result
        assert "end_date" in result

    @pytest.mark.asyncio
    async def test_state_extraction(self):
        """'camping in Oregon' should extract state=OR."""
        mock_response = _mock_tool_response({
            "state": "OR",
            "start_date": "2026-04-11",
            "end_date": "2026-05-11",
        })

        with patch("posthog.ai.anthropic.AsyncAnthropic") as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value = mock_client
            mock_client.messages.create.return_value = mock_response

            result = await parse_natural_query(
                "camping in Oregon", "test-key", today=date(2026, 3, 28),
            )

        assert result["state"] == "OR"

    @pytest.mark.asyncio
    async def test_location_extraction(self):
        """'near Portland' should extract from_location."""
        mock_response = _mock_tool_response({
            "from_location": "portland",
            "start_date": "2026-04-11",
            "end_date": "2026-05-11",
        })

        with patch("posthog.ai.anthropic.AsyncAnthropic") as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value = mock_client
            mock_client.messages.create.return_value = mock_response

            result = await parse_natural_query(
                "camping near Portland", "test-key", today=date(2026, 3, 28),
            )

        assert result["from_location"] == "portland"

    @pytest.mark.asyncio
    async def test_name_extraction(self):
        """'Rainier campgrounds' should extract name_like."""
        mock_response = _mock_tool_response({
            "name_like": "rainier",
            "start_date": "2026-06-01",
            "end_date": "2026-06-30",
        })

        with patch("posthog.ai.anthropic.AsyncAnthropic") as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value = mock_client
            mock_client.messages.create.return_value = mock_response

            result = await parse_natural_query(
                "Rainier campgrounds in June", "test-key",
                today=date(2026, 3, 28),
            )

        assert result["name_like"] == "rainier"

    @pytest.mark.asyncio
    async def test_multiple_tags(self):
        """Complex query should extract multiple tags."""
        mock_response = _mock_tool_response({
            "tags": ["pet-friendly", "lakeside"],
            "state": "WA",
            "start_date": "2026-07-03",
            "end_date": "2026-07-06",
        })

        with patch("posthog.ai.anthropic.AsyncAnthropic") as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value = mock_client
            mock_client.messages.create.return_value = mock_response

            result = await parse_natural_query(
                "dog-friendly lakeside spot in WA July 4th weekend",
                "test-key", today=date(2026, 3, 28),
            )

        assert "pet-friendly" in result["tags"]
        assert "lakeside" in result["tags"]
        assert result["state"] == "WA"

    @pytest.mark.asyncio
    async def test_drive_time_extraction(self):
        """'within 2 hours' should extract max_drive_minutes."""
        mock_response = _mock_tool_response({
            "from_location": "seattle",
            "max_drive_minutes": 120,
            "start_date": "2026-04-11",
            "end_date": "2026-05-11",
        })

        with patch("posthog.ai.anthropic.AsyncAnthropic") as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value = mock_client
            mock_client.messages.create.return_value = mock_response

            result = await parse_natural_query(
                "camping within 2 hours of Seattle",
                "test-key", today=date(2026, 3, 28),
            )

        assert result["max_drive_minutes"] == 120
        assert result["from_location"] == "seattle"

    @pytest.mark.asyncio
    async def test_nights_extraction(self):
        """'3 night trip' should extract min_consecutive_nights."""
        mock_response = _mock_tool_response({
            "min_consecutive_nights": 3,
            "start_date": "2026-06-01",
            "end_date": "2026-06-30",
        })

        with patch("posthog.ai.anthropic.AsyncAnthropic") as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value = mock_client
            mock_client.messages.create.return_value = mock_response

            result = await parse_natural_query(
                "3 night camping trip in June", "test-key",
                today=date(2026, 3, 28),
            )

        assert result["min_consecutive_nights"] == 3

    @pytest.mark.asyncio
    async def test_weekend_filter(self):
        """'weekend camping' should extract days_of_week."""
        mock_response = _mock_tool_response({
            "days_of_week": "4,5,6",
            "start_date": "2026-04-11",
            "end_date": "2026-05-11",
        })

        with patch("posthog.ai.anthropic.AsyncAnthropic") as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value = mock_client
            mock_client.messages.create.return_value = mock_response

            result = await parse_natural_query(
                "weekend camping spots", "test-key",
                today=date(2026, 3, 28),
            )

        assert result["days_of_week"] == "4,5,6"

    @pytest.mark.asyncio
    async def test_empty_values_filtered(self):
        """None and empty values should be stripped from result."""
        mock_response = _mock_tool_response({
            "start_date": "2026-06-01",
            "end_date": "2026-06-30",
            "state": None,
            "tags": [],
            "from_location": "",
        })

        with patch("posthog.ai.anthropic.AsyncAnthropic") as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value = mock_client
            mock_client.messages.create.return_value = mock_response

            result = await parse_natural_query(
                "camping in June", "test-key", today=date(2026, 3, 28),
            )

        assert "state" not in result
        assert "tags" not in result
        assert "from_location" not in result
        assert "start_date" in result

    @pytest.mark.asyncio
    async def test_fallback_on_api_error(self):
        """API failure should fall back to name_like."""
        with patch("posthog.ai.anthropic.AsyncAnthropic") as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value = mock_client
            mock_client.messages.create.side_effect = Exception("API down")

            result = await parse_natural_query(
                "lakeside camping", "test-key", today=date(2026, 3, 28),
            )

        assert result == {"name_like": "lakeside camping"}

    @pytest.mark.asyncio
    async def test_fallback_on_no_tool_use(self):
        """Response without tool_use block should fall back."""
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "I can help with that"

        response = MagicMock()
        response.content = [text_block]

        with patch("posthog.ai.anthropic.AsyncAnthropic") as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value = mock_client
            mock_client.messages.create.return_value = response

            result = await parse_natural_query(
                "help me find camping", "test-key", today=date(2026, 3, 28),
            )

        assert result == {"name_like": "help me find camping"}

    @pytest.mark.asyncio
    async def test_uses_haiku_model(self):
        """Should use Haiku, not Sonnet."""
        mock_response = _mock_tool_response({"start_date": "2026-06-01", "end_date": "2026-06-30"})

        with patch("posthog.ai.anthropic.AsyncAnthropic") as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value = mock_client
            mock_client.messages.create.return_value = mock_response

            await parse_natural_query("camping", "test-key", today=date(2026, 3, 28))

            call_kwargs = mock_client.messages.create.call_args[1]
            assert "haiku" in call_kwargs["model"]

    @pytest.mark.asyncio
    async def test_forces_tool_use(self):
        """Should use tool_choice to force set_search_params."""
        mock_response = _mock_tool_response({"start_date": "2026-06-01", "end_date": "2026-06-30"})

        with patch("posthog.ai.anthropic.AsyncAnthropic") as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value = mock_client
            mock_client.messages.create.return_value = mock_response

            await parse_natural_query("camping", "test-key", today=date(2026, 3, 28))

            call_kwargs = mock_client.messages.create.call_args[1]
            assert call_kwargs["tool_choice"]["type"] == "tool"
            assert call_kwargs["tool_choice"]["name"] == "set_search_params"

    @pytest.mark.asyncio
    async def test_passes_today_in_system_prompt(self):
        """System prompt should include today's date."""
        mock_response = _mock_tool_response({"start_date": "2026-06-01", "end_date": "2026-06-30"})

        with patch("posthog.ai.anthropic.AsyncAnthropic") as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value = mock_client
            mock_client.messages.create.return_value = mock_response

            await parse_natural_query(
                "camping", "test-key", today=date(2026, 7, 15),
            )

            call_kwargs = mock_client.messages.create.call_args[1]
            assert "2026-07-15" in call_kwargs["system"]

    @pytest.mark.asyncio
    async def test_new_state_montana(self):
        """MT should be accepted as a valid state."""
        mock_response = _mock_tool_response({
            "state": "MT",
            "start_date": "2026-07-01",
            "end_date": "2026-07-14",
        })

        with patch("posthog.ai.anthropic.AsyncAnthropic") as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value = mock_client
            mock_client.messages.create.return_value = mock_response

            result = await parse_natural_query(
                "camping near Glacier National Park",
                "test-key", today=date(2026, 3, 28),
            )

        assert result["state"] == "MT"
