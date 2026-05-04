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


class TestBuildToolUseBlocks:
    """Test _build_tool_use_blocks() helper."""

    def test_builds_blocks_from_accumulated_data(self):
        from pnw_campsites.planner.agent import _build_tool_use_blocks

        active = {
            0: {
                "id": "tool_abc",
                "name": "search_campgrounds",
                "input_json": '{"state": "WA", "start_date": "2026-06-01"}',
            },
        }
        blocks = _build_tool_use_blocks(active)

        assert len(blocks) == 1
        assert blocks[0]["type"] == "tool_use"
        assert blocks[0]["id"] == "tool_abc"
        assert blocks[0]["name"] == "search_campgrounds"
        assert blocks[0]["input"]["state"] == "WA"

    def test_empty_input_json(self):
        from pnw_campsites.planner.agent import _build_tool_use_blocks

        active = {0: {"id": "t1", "name": "geocode_address", "input_json": ""}}
        blocks = _build_tool_use_blocks(active)

        assert blocks[0]["input"] == {}

    def test_malformed_json_falls_back_to_empty(self):
        from pnw_campsites.planner.agent import _build_tool_use_blocks

        active = {0: {"id": "t1", "name": "search", "input_json": "{bad json"}}
        blocks = _build_tool_use_blocks(active)

        assert blocks[0]["input"] == {}

    def test_multiple_blocks_sorted_by_index(self):
        from pnw_campsites.planner.agent import _build_tool_use_blocks

        active = {
            2: {"id": "t2", "name": "get_drive_time", "input_json": "{}"},
            0: {"id": "t1", "name": "search_campgrounds", "input_json": "{}"},
        }
        blocks = _build_tool_use_blocks(active)

        assert len(blocks) == 2
        assert blocks[0]["name"] == "search_campgrounds"
        assert blocks[1]["name"] == "get_drive_time"


class TestOpenStream:
    """Test _open_stream() uses create(stream=True)."""

    @pytest.mark.asyncio
    async def test_returns_async_iterable(self):
        """_open_stream returns whatever create(stream=True) resolves to."""
        from pnw_campsites.planner.agent import _open_stream

        mock_stream = AsyncMock()
        mock_stream.__aiter__ = lambda self: self
        mock_stream.__anext__ = AsyncMock(side_effect=StopAsyncIteration())

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_stream)

        await _open_stream(mock_client, model="test")
        # Should have passed stream=True
        mock_client.messages.create.assert_called_once()
        call_kwargs = mock_client.messages.create.call_args[1]
        assert call_kwargs["stream"] is True

    @pytest.mark.asyncio
    async def test_posthog_wrapper_async_generator(self):
        """PostHog wrapper: create(stream=True) returns async generator."""
        from pnw_campsites.planner.agent import _open_stream

        async def mock_gen():
            yield MagicMock(type="message_delta")

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_gen())

        result = await _open_stream(mock_client, model="test")
        events = [e async for e in result]
        assert len(events) == 1


def _make_stream_events(text="Hello world", stop_reason="end_turn"):
    """Create a list of mock streaming events for a text-only response."""
    text_delta = MagicMock()
    text_delta.type = "content_block_delta"
    text_delta.delta = MagicMock(type="text_delta", text=text)
    text_delta.index = 0

    msg_delta = MagicMock()
    msg_delta.type = "message_delta"
    msg_delta.delta = MagicMock(stop_reason=stop_reason)

    return [text_delta, msg_delta]


class TestChatStream:
    @pytest.mark.asyncio
    async def test_simple_text_stream(self):
        """chat_stream() yields text events and a done event."""
        from pnw_campsites.planner.agent import chat_stream

        stream_events = _make_stream_events("Hello world")

        mock_stream = AsyncMock()
        mock_stream.__aiter__ = lambda self: self
        mock_stream.__anext__ = AsyncMock(
            side_effect=[*stream_events, StopAsyncIteration()],
        )

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_stream)

        events = []
        with patch("posthog.ai.anthropic.AsyncAnthropic", return_value=mock_client):
            async for event_json in chat_stream(
                [{"role": "user", "content": "hello"}],
                engine=MagicMock(),
                registry=MagicMock(),
                api_key="test-key",
            ):
                events.append(json.loads(event_json))

        types = [e["type"] for e in events]
        assert "text" in types
        assert "done" in types
        done_event = next(e for e in events if e["type"] == "done")
        assert done_event["content"] == "Hello world"

    @pytest.mark.asyncio
    async def test_stream_via_posthog_wrapper(self):
        """chat_stream() works when PostHog wrapper returns async generator."""
        from pnw_campsites.planner.agent import chat_stream

        stream_events = _make_stream_events("PH wrapped")

        async def mock_gen():
            for event in stream_events:
                yield event

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_gen())

        events = []
        with patch("posthog.ai.anthropic.AsyncAnthropic", return_value=mock_client):
            async for event_json in chat_stream(
                [{"role": "user", "content": "hello"}],
                engine=MagicMock(),
                registry=MagicMock(),
                api_key="test-key",
            ):
                events.append(json.loads(event_json))

        types = [e["type"] for e in events]
        assert "text" in types
        assert "done" in types
        done_event = next(e for e in events if e["type"] == "done")
        assert done_event["content"] == "PH wrapped"

    @pytest.mark.asyncio
    async def test_stream_with_tool_calls(self):
        """chat_stream() handles tool_use blocks from streaming events."""
        from pnw_campsites.planner.agent import chat_stream

        # First stream: tool call
        tool_block_start = MagicMock()
        tool_block_start.type = "content_block_start"
        tool_block_start.index = 0
        content_block = MagicMock(type="tool_use", id="tool_1")
        content_block.name = "search_campgrounds"  # .name is reserved in MagicMock
        tool_block_start.content_block = content_block

        tool_input_delta = MagicMock()
        tool_input_delta.type = "content_block_delta"
        tool_input_delta.index = 0
        tool_input_delta.delta = MagicMock(
            type="input_json_delta",
            partial_json='{"start_date": "2026-06-01", "end_date": "2026-06-07"}',
        )

        tool_msg_delta = MagicMock()
        tool_msg_delta.type = "message_delta"
        tool_msg_delta.delta = MagicMock(stop_reason="tool_use")

        # Second stream: final text response
        final_events = _make_stream_events("Found 2 campgrounds.")

        call_count = [0]

        async def mock_create_stream(**kwargs):
            call_count[0] += 1
            async def gen():
                if call_count[0] == 1:
                    for e in [tool_block_start, tool_input_delta, tool_msg_delta]:
                        yield e
                else:
                    for e in final_events:
                        yield e
            return gen()

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(side_effect=mock_create_stream)

        mock_tool_result = json.dumps({
            "found": 2, "total_checked": 10, "campgrounds": [],
        })

        events = []
        with (
            patch("posthog.ai.anthropic.AsyncAnthropic", return_value=mock_client),
            patch(
                "pnw_campsites.planner.agent.execute_tool",
                AsyncMock(return_value=mock_tool_result),
            ),
        ):
            async for event_json in chat_stream(
                [{"role": "user", "content": "find camping"}],
                engine=MagicMock(),
                registry=MagicMock(),
                api_key="test-key",
            ):
                events.append(json.loads(event_json))

        types = [e["type"] for e in events]
        assert "tool_start" in types
        assert "tool_result" in types
        assert "text" in types
        assert "done" in types

        tool_result_evt = next(e for e in events if e["type"] == "tool_result")
        assert tool_result_evt["name"] == "search_campgrounds"
        assert "Found 2" in tool_result_evt["summary"]

    @pytest.mark.asyncio
    async def test_stream_error_yields_error_event(self):
        """chat_stream() yields an error event on API failure."""
        from pnw_campsites.planner.agent import chat_stream

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(side_effect=Exception("API down"))

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
        # SEC-06: error messages are sanitized — no raw exception details
        assert "Something went wrong" in events[0]["message"]
        assert "API down" not in events[0]["message"]
