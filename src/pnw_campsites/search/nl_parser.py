"""Natural language search query parser using Claude Haiku tool_use."""

from __future__ import annotations

import json
import logging
from datetime import date, timedelta

_logger = logging.getLogger(__name__)

# JSON schema for the structured extraction tool
_SEARCH_PARAMS_TOOL = {
    "name": "set_search_params",
    "description": (
        "Extract structured campsite search parameters from the user's "
        "natural language query. Only set fields that are clearly implied "
        "by the query. Leave ambiguous or unmentioned fields unset."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "start_date": {
                "type": "string",
                "description": "Start date in YYYY-MM-DD format",
            },
            "end_date": {
                "type": "string",
                "description": "End date in YYYY-MM-DD format",
            },
            "state": {
                "type": "string",
                "enum": ["WA", "OR", "ID", "MT", "WY", "CA"],
                "description": "State filter",
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Tags to filter by. Map user vocabulary to these: "
                    "lakeside, riverside, beach, old-growth, forest, alpine, "
                    "desert, backcountry, remote, rv-friendly, tent-only, "
                    "walk-in, pull-through, group-sites, dispersed, trails, "
                    "swimming, fishing, boating, boat-launch, equestrian, "
                    "climbing, winter-camping, pet-friendly, kid-friendly, "
                    "accessible, campfire, shade, hot-springs, waterfall. "
                    "Examples: 'waterfront'→lakeside/riverside/beach, "
                    "'dog-friendly'→pet-friendly, 'quiet'→remote/walk-in, "
                    "'RV'→rv-friendly"
                ),
            },
            "from_location": {
                "type": "string",
                "description": (
                    "Origin city for drive time. Known bases: seattle, "
                    "bellevue, portland, spokane, bellingham, moscow, "
                    "bozeman, missoula, jackson, sacramento, reno, bend. "
                    "For 'near X' where X is a campground/park/mountain, "
                    "do NOT set this — set name_like instead."
                ),
            },
            "max_drive_minutes": {
                "type": "integer",
                "description": "Max drive time in minutes from origin",
            },
            "name_like": {
                "type": "string",
                "description": (
                    "Campground name substring filter. Use when the user "
                    "mentions a specific campground, park, or area name "
                    "(e.g. 'Rainier', 'Olympic', 'Yellowstone')."
                ),
            },
            "min_consecutive_nights": {
                "type": "integer",
                "description": "Minimum consecutive nights (default 2)",
            },
            "days_of_week": {
                "type": "string",
                "description": (
                    "Day-of-week filter as comma-separated numbers "
                    "(0=Mon through 6=Sun). 'weekend'→'4,5,6', "
                    "'weekday'→'0,1,2,3,4'. Only set if user specifies."
                ),
            },
        },
        "required": [],
    },
}


def _build_system_prompt(today: date) -> str:
    """Build the system prompt with today's date for relative date resolution."""
    # Calculate useful reference dates
    this_friday = today + timedelta(days=(4 - today.weekday()) % 7)
    if this_friday <= today:
        this_friday += timedelta(days=7)
    next_friday = this_friday + timedelta(days=7)

    return (
        "You are a search query parser for a campsite availability tool "
        "covering WA, OR, ID, MT, WY, and Northern California.\n\n"
        f"Today is {today.isoformat()} ({today.strftime('%A')}).\n"
        f"This coming Friday: {this_friday.isoformat()}\n"
        f"Next Friday: {next_friday.isoformat()}\n\n"
        "Parse the user's natural language query into structured search "
        "parameters using the set_search_params tool. Rules:\n"
        "- 'this weekend' = this Fri-Sun\n"
        "- 'next weekend' = next Fri-Sun\n"
        "- 'July 4th weekend' / 'Labor Day' = resolve to actual dates "
        f"in {today.year} (or {today.year + 1} if already past)\n"
        "- 'next month' = 1st to last day of the following month\n"
        "- 'late August' = Aug 15 to Aug 31\n"
        "- 'summer' = Jun 15 to Sep 15\n"
        "- If no dates mentioned, use a 30-day window starting 2 weeks out\n"
        "- If user says 'near Portland' set from_location='portland'\n"
        "- If user says 'near Rainier' set name_like='rainier' (it's a park)\n"
        "- Map informal terms to tags (see tool description)\n"
        "- Be conservative: only set fields the query clearly implies\n"
        "- Always call the tool, even for simple queries"
    )


async def parse_natural_query(
    query: str,
    api_key: str,
    today: date | None = None,
) -> dict:
    """Parse a natural language query into structured search params.

    Returns a dict of parsed params (only keys that were extracted).
    On failure, returns {"name_like": query} as fallback.
    """
    from pnw_campsites.posthog_client import get_posthog_client

    today = today or date.today()
    try:
        from posthog.ai.anthropic import AsyncAnthropic
        client = AsyncAnthropic(api_key=api_key, posthog_client=get_posthog_client())
    except ImportError:
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=api_key)

    try:
        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            system=_build_system_prompt(today),
            tools=[_SEARCH_PARAMS_TOOL],
            tool_choice={"type": "tool", "name": "set_search_params"},
            messages=[{"role": "user", "content": query}],
        )

        # Extract tool_use block
        for block in response.content:
            if block.type == "tool_use" and block.name == "set_search_params":
                params = block.input
                # Filter out empty/null values
                result = {
                    k: v for k, v in params.items()
                    if v is not None and v != "" and v != []
                }
                _logger.info("NL parse: %r -> %s", query, json.dumps(result))
                return result

        # No tool_use block found
        _logger.warning("NL parse: no tool_use in response for %r", query)
        return {"name_like": query}

    except Exception as e:
        _logger.warning("NL parse failed for %r: %s", query, e)
        return {"name_like": query}
