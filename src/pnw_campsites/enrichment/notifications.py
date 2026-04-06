"""LLM-enriched notification messages with urgency scoring."""

from __future__ import annotations

import json
import logging
import os
from datetime import date

_logger = logging.getLogger(__name__)


def _fallback_message(campground_name: str, site_count: int) -> tuple[str, int]:
    """Simple fallback when LLM enrichment is unavailable."""
    sites = "site" if site_count == 1 else "sites"
    return f"{site_count} {sites} open at {campground_name}", 2


async def enrich_notification(
    campground_name: str,
    site_count: int,
    dates: list[str],
    api_key: str | None = None,
) -> tuple[str, int]:
    """Generate contextual notification message + urgency score.

    Returns (message, urgency) where urgency is 1-3:
    - 3: high demand (weekend/holiday, rare opening)
    - 2: standard availability
    - 1: low demand (midweek, off-season)

    Falls back to simple message on any failure.
    """
    api_key = api_key or os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        return _fallback_message(campground_name, site_count)

    today = date.today().isoformat()
    dates_str = ", ".join(dates[:14])
    if len(dates) > 14:
        dates_str += f" (+{len(dates) - 14} more)"

    prompt = (
        "Generate a campsite availability notification. Voice rules:\n"
        "- Declarative, not interrogative. Lead with site count and campground name.\n"
        "- Always include: campground name, site count, and date context.\n"
        "- Include timing context: weekend vs midweek, how soon, holiday.\n"
        "- Urgency comes from data (weekend proximity, rarity), not exclamation marks.\n"
        "- Never say 'Availability Alert', 'Uh oh!', 'Great news!', or 'Exciting!'.\n"
        "- Never use 'snag', 'grab', or 'score'. Use 'book' or 'reserve'.\n"
        "- No emoji prefixes. No exclamation marks.\n"
        "- 1-2 sentences max. Be specific, not generic.\n\n"
        f"Campground: {campground_name}\n"
        f"Sites available: {site_count}\n"
        f"Dates: {dates_str}\n"
        f"Today's date: {today}\n\n"
        "Rate urgency 1-3 (1=low demand/midweek/off-season, "
        "2=normal, 3=high demand/weekend/holiday/rare).\n"
        'Return ONLY a JSON object: {"message": "...", "urgency": N}'
    )

    try:
        from pnw_campsites.posthog_client import get_posthog_client

        try:
            from posthog.ai.anthropic import AsyncAnthropic
            client = AsyncAnthropic(api_key=api_key, posthog_client=get_posthog_client())
        except (ImportError, ValueError):
            import anthropic
            client = anthropic.AsyncAnthropic(api_key=api_key)
        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )

        text = response.content[0].text.strip()

        # Try parsing JSON directly
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            # Try extracting from markdown code block
            if "```" in text:
                json_str = text.split("```")[1]
                if json_str.startswith("json"):
                    json_str = json_str[4:]
                data = json.loads(json_str.strip())
            else:
                _logger.warning("Could not parse LLM response: %s", text[:200])
                return _fallback_message(campground_name, site_count)

        message = data.get("message", "")
        urgency = data.get("urgency", 2)

        if not message or not isinstance(message, str):
            return _fallback_message(campground_name, site_count)

        # Clamp urgency to valid range
        urgency = max(1, min(3, int(urgency)))

        return message, urgency

    except Exception as e:
        _logger.warning(
            "LLM enrichment failed for %s: %s", campground_name, e,
        )
        return _fallback_message(campground_name, site_count)
