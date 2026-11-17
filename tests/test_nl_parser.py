"""Tests for natural language search query parser."""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

from pnw_campsites.search.nl_parser import (
    _SEARCH_PARAMS_TOOL,
    _build_system_prompt,
    parse_natural_query,
)


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


class TestToolSchema:
    def test_no_required_fields(self):
        """All fields should be optional for NL parsing."""
        required = _SEARCH_PARAMS_TOOL["input_schema"].get("required", [])
        assert required == []


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
