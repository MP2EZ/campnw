"""Conversational trip planner agent using Claude with tool-use."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator

from pnw_campsites.registry.db import CampgroundRegistry
from pnw_campsites.search.engine import SearchEngine

from .tools import TOOLS, execute_tool

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT_TEMPLATE = """\
You are campable's trip planner for the Pacific Northwest and beyond (WA, OR, ID, MT, WY, CA).
Today is {today} ({weekday}).

CORE PRINCIPLE: Act, don't ask. Resolve what you can and search immediately.
- "this weekend" = the coming Friday-Sunday. You know today's date — calculate it.
- "in June" = June 1 to June 30 of the current/next year.
- "near Rainier" = search with name "rainier" or tags relevant to the area.
- No origin specified = default to seattle for drive times.
- No nights specified = default to 2.
Only ask if genuinely ambiguous (e.g., no dates AND no location at all).

RULES:
- ONLY recommend campgrounds from tool results. Never from memory.
- Search first, present results. Don't ask for info you can infer.
- One search call is usually enough.

RESPONSE STYLE:
- Start with a one-line summary like "Found 4 lakeside campgrounds this weekend:"
- No "I'd be happy to help" or "Great question!" — just the summary + results.
- Use **bold** for campground names. No markdown headers for short responses.
- Each campground: name, drive time, tags, available dates, [Book](url).
- Keep it tight — 1-2 lines per campground.
- Bullet lists: max 4 items. Combine related things. Avoid long enumerated lists.
- For trip plans: use short paragraphs, not a bullet per activity.
- When recommending campgrounds, ALSO include a JSON block at the END of your response
  wrapped in ```itinerary fences. This is used to render visual cards. Format:
  ```itinerary
  [{{"name": "Campground Name", "facility_id": "232465", "booking_system": "recgov",
    "dates": "Jun 15-17", "nights": 2, "drive_minutes": 57,
    "sites_available": 4, "booking_url": "https://...", "tags": ["lakeside"]}}]
  ```
  Only include this for campgrounds from tool results. Never fabricate IDs.

TOOLS:
- search_campgrounds: main search. Always set from_location (default: seattle).
- check_availability: specific facility by ID.
- get_drive_time / geocode_address: multi-stop itineraries.

Dates must be YYYY-MM-DD in tool calls."""

_MAX_TOOL_ITERATIONS = 5


async def chat(
    messages: list[dict],
    engine: SearchEngine,
    registry: CampgroundRegistry,
    api_key: str,
) -> dict:
    """Process one conversation turn.

    Args:
        messages: Full conversation history in Anthropic message format.
        engine: Initialized SearchEngine with provider clients.
        registry: CampgroundRegistry for detail lookups.
        api_key: Anthropic API key.

    Returns:
        dict with keys: role, content, tool_calls (list of call summaries for UI).
    """
    from datetime import date as _date

    from pnw_campsites.posthog_client import get_posthog_client

    today = _date.today()
    system_prompt = _SYSTEM_PROMPT_TEMPLATE.format(
        today=today.isoformat(),
        weekday=today.strftime("%A"),
    )

    try:
        from posthog.ai.anthropic import AsyncAnthropic
        client = AsyncAnthropic(api_key=api_key, posthog_client=get_posthog_client())
    except ImportError:
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=api_key)
    tool_call_log: list[dict] = []
    current_messages = list(messages)

    for _iteration in range(_MAX_TOOL_ITERATIONS):
        response = await client.messages.create(
            model="claude-sonnet-4-20250514",
            system=system_prompt,
            messages=current_messages,
            tools=TOOLS,  # type: ignore[arg-type]
            max_tokens=4096,
        )

        # Final text response — no more tool calls
        if response.stop_reason != "tool_use":
            return {
                "role": "assistant",
                "content": _extract_text(response.content),
                "tool_calls": tool_call_log,
            }

        # Collect tool_use blocks
        tool_use_blocks = [b for b in response.content if b.type == "tool_use"]
        if not tool_use_blocks:
            return {
                "role": "assistant",
                "content": _extract_text(response.content),
                "tool_calls": tool_call_log,
            }

        # Append assistant turn with tool_use blocks
        current_messages.append({
            "role": "assistant",
            "content": response.content,
        })

        # Execute tools and collect results
        tool_results = []
        for block in tool_use_blocks:
            logger.info("Tool call: %s  input=%s", block.name, block.input)
            result_str = await execute_tool(block.name, block.input, engine, registry)

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": result_str,
            })
            tool_call_log.append({
                "name": block.name,
                "input": block.input,
                "result_summary": _summarize_result(block.name, result_str),
            })

        # Return results to Claude
        current_messages.append({"role": "user", "content": tool_results})

    # Exceeded iteration cap — get a final response without tools
    logger.warning("Trip planner hit max tool iterations (%d)", _MAX_TOOL_ITERATIONS)
    final = await client.messages.create(
        model="claude-sonnet-4-20250514",
        system=system_prompt,
        messages=current_messages,
        max_tokens=1024,
    )
    return {
        "role": "assistant",
        "content": _extract_text(final.content),
        "tool_calls": tool_call_log,
    }


async def _open_stream(client, **kwargs) -> AsyncIterator:
    """Open a streaming API call, handling both PostHog-wrapped and native clients.

    The PostHog AI wrapper's .stream() returns an async generator (via coroutine),
    while the native Anthropic .stream() returns an AsyncMessageStreamManager
    (context manager). This helper normalises both to an async iterator of events.
    """
    result = client.messages.stream(**kwargs)

    # Native Anthropic: returns AsyncMessageStreamManager (context manager)
    if hasattr(result, "__aenter__"):
        ctx = await result.__aenter__()
        return ctx.__aiter__()

    # PostHog wrapper: stream() is a coroutine returning an async generator
    if hasattr(result, "__await__"):
        return await result

    # Already an async iterator
    return result


def _build_tool_use_blocks(active_tool_blocks: dict[int, dict]) -> list[dict]:
    """Reconstruct tool_use content blocks from accumulated streaming data."""
    blocks = []
    for _idx, info in sorted(active_tool_blocks.items()):
        input_data = {}
        if info["input_json"]:
            try:
                input_data = json.loads(info["input_json"])
            except json.JSONDecodeError:
                logger.warning("Failed to parse tool input JSON for %s", info["name"])
        blocks.append({
            "type": "tool_use",
            "id": info["id"],
            "name": info["name"],
            "input": input_data,
        })
    return blocks


async def chat_stream(
    messages: list[dict],
    engine: SearchEngine,
    registry: CampgroundRegistry,
    api_key: str,
) -> AsyncIterator[str]:
    """Stream one conversation turn as SSE-formatted JSON event strings.

    Yields JSON strings, each representing one event:
      {"type": "text", "content": "..."}
      {"type": "tool_start", "name": "search_campgrounds"}
      {"type": "tool_result", "name": "...", "summary": "..."}
      {"type": "done", "content": "...", "tool_calls": [...]}
      {"type": "error", "message": "..."}
    """
    from datetime import date as _date

    from pnw_campsites.posthog_client import get_posthog_client

    today = _date.today()
    system_prompt = _SYSTEM_PROMPT_TEMPLATE.format(
        today=today.isoformat(),
        weekday=today.strftime("%A"),
    )

    try:
        from posthog.ai.anthropic import AsyncAnthropic
        client = AsyncAnthropic(api_key=api_key, posthog_client=get_posthog_client())
    except ImportError:
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=api_key)
    tool_call_log: list[dict] = []
    current_messages = list(messages)
    final_text = ""

    for _iteration in range(_MAX_TOOL_ITERATIONS):
        # Accumulate the full text response for this iteration
        iter_text_parts: list[str] = []
        # Track tool_use blocks being assembled (id -> {name, input_json})
        active_tool_blocks: dict[int, dict] = {}
        stop_reason: str | None = None

        try:
            event_stream = await _open_stream(
                client,
                model="claude-sonnet-4-20250514",
                system=system_prompt,
                messages=current_messages,
                tools=TOOLS,  # type: ignore[arg-type]
                max_tokens=4096,
            )
            async for event in event_stream:
                if event.type == "content_block_start":
                    block = event.content_block
                    if block.type == "tool_use":
                        # Signal that a tool call is starting
                        active_tool_blocks[event.index] = {
                            "id": block.id,
                            "name": block.name,
                            "input_json": "",
                        }
                        yield json.dumps({"type": "tool_start", "name": block.name})

                elif event.type == "content_block_delta":
                    delta = event.delta
                    if delta.type == "text_delta":
                        iter_text_parts.append(delta.text)
                        yield json.dumps({"type": "text", "content": delta.text})
                    elif delta.type == "input_json_delta":
                        if event.index in active_tool_blocks:
                            active_tool_blocks[event.index]["input_json"] += (
                                delta.partial_json
                            )

                elif event.type == "message_delta":
                    stop_reason = getattr(event.delta, "stop_reason", None)

        except Exception as exc:
            logger.error("Streaming API call failed (iteration %d): %s", _iteration, exc)
            yield json.dumps({"type": "error", "message": str(exc)})
            return

        final_text = "".join(iter_text_parts)

        # Build tool_use content blocks from accumulated JSON
        tool_use_blocks = _build_tool_use_blocks(active_tool_blocks)

        # No tool calls — we're done
        if stop_reason != "tool_use" or not tool_use_blocks:
            yield json.dumps({
                "type": "done",
                "content": final_text,
                "tool_calls": tool_call_log,
            })
            return

        # Build content list for conversation history (text + tool_use blocks)
        content: list = []
        if final_text:
            content.append({"type": "text", "text": final_text})
        content.extend(tool_use_blocks)

        # Append assistant turn to conversation
        current_messages.append({"role": "assistant", "content": content})

        # Execute tools and yield results
        tool_results = []
        for block in tool_use_blocks:
            logger.info("Tool call (stream): %s  input=%s", block["name"], block.get("input"))
            try:
                result_str = await execute_tool(
                    block["name"], block.get("input", {}), engine, registry
                )
            except Exception as exc:
                logger.warning("Tool %s failed during stream: %s", block["name"], exc)
                result_str = json.dumps({"error": str(exc)})
                yield json.dumps({
                    "type": "error",
                    "message": f"Tool {block['name']} failed: {exc}",
                })

            summary = _summarize_result(block["name"], result_str)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block["id"],
                "content": result_str,
            })
            tool_call_log.append({
                "name": block["name"],
                "input": block.get("input", {}),
                "result_summary": summary,
            })
            yield json.dumps({"type": "tool_result", "name": block["name"], "summary": summary})

        # Return results to Claude and loop
        current_messages.append({"role": "user", "content": tool_results})

    # Exceeded iteration cap — get a final response without tools
    logger.warning("Trip planner stream hit max tool iterations (%d)", _MAX_TOOL_ITERATIONS)
    try:
        event_stream = await _open_stream(
            client,
            model="claude-sonnet-4-20250514",
            system=system_prompt,
            messages=current_messages,
            max_tokens=1024,
        )
        final_parts: list[str] = []
        async for event in event_stream:
            if event.type == "content_block_delta" and event.delta.type == "text_delta":
                final_parts.append(event.delta.text)
                yield json.dumps({"type": "text", "content": event.delta.text})
        yield json.dumps({
            "type": "done",
            "content": "".join(final_parts),
            "tool_calls": tool_call_log,
        })
    except Exception as exc:
        logger.error("Final fallback stream failed: %s", exc)
        yield json.dumps({"type": "error", "message": str(exc)})


def _extract_text(content: list) -> str:
    """Extract concatenated text from a content block list."""
    parts = [block.text for block in content if hasattr(block, "type") and block.type == "text"]
    return "\n".join(parts).strip()


def _summarize_result(tool_name: str, result_str: str) -> str:
    """Short human-readable summary of a tool result for UI display."""
    import json

    try:
        data = json.loads(result_str)
    except Exception:
        return "completed"

    if "error" in data:
        return f"Error: {data['error']}"

    if tool_name == "search_campgrounds":
        found = data.get("found", 0)
        checked = data.get("total_checked", 0)
        return f"Found {found} campground(s) with availability (checked {checked})"

    if tool_name == "check_availability":
        sites = data.get("available_sites", 0)
        name = data.get("name", "campground")
        return f"{name}: {sites} available site(s)"

    if tool_name == "get_drive_time":
        return f"Drive time: {data.get('readable', '?')}"

    if tool_name == "get_campground_detail":
        return f"Detail: {data.get('name', data.get('facility_id', '?'))}"

    if tool_name == "geocode_address":
        lat = data.get("lat")
        lon = data.get("lon")
        return f"Coordinates: {lat:.4f}, {lon:.4f}" if lat and lon else "Geocoded"

    return "completed"
