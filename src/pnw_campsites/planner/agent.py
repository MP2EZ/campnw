"""Conversational trip planner agent using Claude with tool-use."""

from __future__ import annotations

import logging

from pnw_campsites.registry.db import CampgroundRegistry
from pnw_campsites.search.engine import SearchEngine

from .tools import TOOLS, execute_tool

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT_TEMPLATE = """\
You are campnw's trip planner for the Pacific Northwest (WA, OR, ID).
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

    import anthropic

    today = _date.today()
    system_prompt = _SYSTEM_PROMPT_TEMPLATE.format(
        today=today.isoformat(),
        weekday=today.strftime("%A"),
    )

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
