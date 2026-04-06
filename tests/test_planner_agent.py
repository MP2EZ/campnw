"""Tests for planner agent chat() and chat_stream() functions."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------


def _text_block(text: str):
    """Create a mock text content block."""
    block = MagicMock()
    block.type = "text"
    block.text = text
    return block


def _tool_use_block(name: str, input_data: dict, block_id: str = "tool_1"):
    """Create a mock tool_use content block."""
    block = MagicMock()
    block.type = "tool_use"
    block.name = name
    block.input = input_data
    block.id = block_id
    return block


def _mock_response(content_blocks, stop_reason="end_turn"):
    """Create a mock Anthropic message response."""
    resp = MagicMock()
    resp.content = content_blocks
    resp.stop_reason = stop_reason
    return resp


# ---------------------------------------------------------------------------
# _extract_text
# ---------------------------------------------------------------------------


class TestExtractText:
    def test_extracts_text_blocks(self):
        from pnw_campsites.planner.agent import _extract_text

        blocks = [_text_block("Hello"), _text_block("world")]
        assert _extract_text(blocks) == "Hello\nworld"

    def test_ignores_non_text_blocks(self):
        from pnw_campsites.planner.agent import _extract_text

        blocks = [_text_block("Hello"), _tool_use_block("search", {})]
        assert _extract_text(blocks) == "Hello"

    def test_empty_content(self):
        from pnw_campsites.planner.agent import _extract_text

        assert _extract_text([]) == ""


# ---------------------------------------------------------------------------
# _summarize_result
# ---------------------------------------------------------------------------


class TestSummarizeResult:
    def test_search_result(self):
        from pnw_campsites.planner.agent import _summarize_result

        data = json.dumps({"found": 3, "total_checked": 20})
        assert _summarize_result("search_campgrounds", data) == \
            "Found 3 campground(s) with availability (checked 20)"

    def test_check_availability(self):
        from pnw_campsites.planner.agent import _summarize_result

        data = json.dumps({"name": "Ohanapecosh", "available_sites": 5})
        assert _summarize_result("check_availability", data) == \
            "Ohanapecosh: 5 available site(s)"

    def test_error_result(self):
        from pnw_campsites.planner.agent import _summarize_result

        data = json.dumps({"error": "Not found"})
        assert _summarize_result("search_campgrounds", data) == "Error: Not found"

    def test_invalid_json(self):
        from pnw_campsites.planner.agent import _summarize_result

        assert _summarize_result("unknown", "not json") == "completed"

    def test_drive_time(self):
        from pnw_campsites.planner.agent import _summarize_result

        data = json.dumps({"readable": "2h 15m"})
        assert _summarize_result("get_drive_time", data) == "Drive time: 2h 15m"

    def test_campground_detail(self):
        from pnw_campsites.planner.agent import _summarize_result

        data = json.dumps({"name": "Kalaloch", "facility_id": "232464"})
        assert _summarize_result("get_campground_detail", data) == "Detail: Kalaloch"

    def test_geocode(self):
        from pnw_campsites.planner.agent import _summarize_result

        data = json.dumps({"lat": 47.6062, "lon": -122.3321})
        result = _summarize_result("geocode_address", data)
        assert "47.6062" in result
        assert "Coordinates" in result


# ---------------------------------------------------------------------------
# chat() — non-streaming
# ---------------------------------------------------------------------------


class TestChat:
    @pytest.mark.asyncio
    async def test_simple_text_response(self):
        """chat() returns text when no tool calls are made."""
        from pnw_campsites.planner.agent import chat

        mock_response = _mock_response(
            [_text_block("Found 3 campgrounds near Seattle.")],
            stop_reason="end_turn",
        )
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        with patch("posthog.ai.anthropic.AsyncAnthropic", return_value=mock_client):
            result = await chat(
                [{"role": "user", "content": "find camping"}],
                engine=MagicMock(),
                registry=MagicMock(),
                api_key="test-key",
            )

        assert result["role"] == "assistant"
        assert "3 campgrounds" in result["content"]
        assert result["tool_calls"] == []

    @pytest.mark.asyncio
    async def test_one_tool_call_loop(self):
        """chat() executes a tool and returns the final response."""
        from pnw_campsites.planner.agent import chat

        # First call: model wants to use a tool
        tool_response = _mock_response(
            [_tool_use_block("search_campgrounds", {"start_date": "2026-06-01", "end_date": "2026-06-07"})],
            stop_reason="tool_use",
        )
        # Second call: model returns text after getting tool result
        text_response = _mock_response(
            [_text_block("Here are your results.")],
            stop_reason="end_turn",
        )

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(side_effect=[tool_response, text_response])

        mock_tool_result = json.dumps({"found": 2, "total_checked": 10, "campgrounds": []})

        with (
            patch("posthog.ai.anthropic.AsyncAnthropic", return_value=mock_client),
            patch("pnw_campsites.planner.agent.execute_tool", AsyncMock(return_value=mock_tool_result)),
        ):
            result = await chat(
                [{"role": "user", "content": "find camping near Seattle"}],
                engine=MagicMock(),
                registry=MagicMock(),
                api_key="test-key",
            )

        assert result["content"] == "Here are your results."
        assert len(result["tool_calls"]) == 1
        assert result["tool_calls"][0]["name"] == "search_campgrounds"

    @pytest.mark.asyncio
    async def test_max_iteration_fallback(self):
        """chat() falls back to text-only response after max iterations."""
        from pnw_campsites.planner.agent import chat

        # Every call returns a tool_use — forces max iterations
        tool_response = _mock_response(
            [_tool_use_block("search_campgrounds", {"start_date": "2026-06-01", "end_date": "2026-06-07"})],
            stop_reason="tool_use",
        )
        # Final fallback (no tools parameter)
        fallback_response = _mock_response(
            [_text_block("I searched multiple times but couldn't find results.")],
            stop_reason="end_turn",
        )

        call_count = [0]
        async def mock_create(**kwargs):
            call_count[0] += 1
            # After 5 tool iterations, the 6th call is the fallback (no tools)
            if "tools" not in kwargs or call_count[0] > 5:
                return fallback_response
            return tool_response

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(side_effect=mock_create)

        mock_tool_result = json.dumps({"found": 0, "total_checked": 0, "campgrounds": []})

        with (
            patch("posthog.ai.anthropic.AsyncAnthropic", return_value=mock_client),
            patch("pnw_campsites.planner.agent.execute_tool", AsyncMock(return_value=mock_tool_result)),
        ):
            result = await chat(
                [{"role": "user", "content": "find camping"}],
                engine=MagicMock(),
                registry=MagicMock(),
                api_key="test-key",
            )

        assert "couldn't find" in result["content"]
        assert len(result["tool_calls"]) == 5  # 5 iterations of tool calls

    @pytest.mark.asyncio
    async def test_no_tool_use_blocks_returns_text(self):
        """chat() returns text if stop_reason is tool_use but no tool blocks found."""
        from pnw_campsites.planner.agent import chat

        # stop_reason says tool_use but content is only text
        weird_response = _mock_response(
            [_text_block("Just text, no tools.")],
            stop_reason="tool_use",
        )

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=weird_response)

        with patch("posthog.ai.anthropic.AsyncAnthropic", return_value=mock_client):
            result = await chat(
                [{"role": "user", "content": "hello"}],
                engine=MagicMock(),
                registry=MagicMock(),
                api_key="test-key",
            )

        assert result["content"] == "Just text, no tools."
        assert result["tool_calls"] == []


# ---------------------------------------------------------------------------
# chat_stream()
# ---------------------------------------------------------------------------


class TestChatStream:
    @pytest.mark.asyncio
    async def test_simple_text_stream(self):
        """chat_stream() yields text events and a done event."""
        from pnw_campsites.planner.agent import chat_stream

        # Mock the streaming context manager
        text_delta = MagicMock()
        text_delta.type = "content_block_delta"
        text_delta.delta = MagicMock(type="text_delta", text="Hello world")
        text_delta.index = 0

        final_message = _mock_response(
            [_text_block("Hello world")],
            stop_reason="end_turn",
        )

        mock_stream = AsyncMock()
        mock_stream.__aiter__ = lambda self: self
        mock_stream.__anext__ = AsyncMock(side_effect=[text_delta, StopAsyncIteration()])
        mock_stream.get_final_message = AsyncMock(return_value=final_message)

        mock_stream_ctx = AsyncMock()
        mock_stream_ctx.__aenter__ = AsyncMock(return_value=mock_stream)
        mock_stream_ctx.__aexit__ = AsyncMock(return_value=False)

        mock_client = AsyncMock()
        mock_client.messages.stream = MagicMock(return_value=mock_stream_ctx)

        events = []
        with patch("posthog.ai.anthropic.AsyncAnthropic", return_value=mock_client):
            async for event_json in chat_stream(
                [{"role": "user", "content": "hello"}],
                engine=MagicMock(),
                registry=MagicMock(),
                api_key="test-key",
            ):
                events.append(json.loads(event_json))

        # Should have a text event and a done event
        types = [e["type"] for e in events]
        assert "text" in types
        assert "done" in types
        done_event = next(e for e in events if e["type"] == "done")
        assert done_event["content"] == "Hello world"

    @pytest.mark.asyncio
    async def test_stream_error_yields_error_event(self):
        """chat_stream() yields an error event on API failure."""
        from pnw_campsites.planner.agent import chat_stream

        mock_stream_ctx = AsyncMock()
        mock_stream_ctx.__aenter__ = AsyncMock(side_effect=Exception("API down"))

        mock_client = AsyncMock()
        mock_client.messages.stream = MagicMock(return_value=mock_stream_ctx)

        events = []
        with patch("posthog.ai.anthropic.AsyncAnthropic", return_value=mock_client):
            async for event_json in chat_stream(
                [{"role": "user", "content": "hello"}],
                engine=MagicMock(),
                registry=MagicMock(),
                api_key="test-key",
            ):
                events.append(json.loads(event_json))

        assert len(events) == 1
        assert events[0]["type"] == "error"
        assert "API down" in events[0]["message"]
