"""LLM-enriched notification messages."""

from __future__ import annotations

import logging
import os
from datetime import date

from pnw_campsites.enrichment.llm_tags import parse_llm_json

_logger = logging.getLogger(__name__)


def _fallback_message(campground_name: str, site_count: int) -> str:
    """Simple fallback when LLM enrichment is unavailable."""
    sites = "site" if site_count == 1 else "sites"
    return f"{site_count} {sites} open at {campground_name}"


async def enrich_notification(
    campground_name: str,
    site_count: int,
    dates: list[str],
    api_key: str | None = None,
) -> str:
    """Generate a contextual notification message.

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
        'Return ONLY a JSON object: {"message": "..."}'
    )

    try:
        from pnw_campsites.posthog_client import HAIKU_MODEL, get_anthropic_client

        client = get_anthropic_client(api_key)
        response = await client.messages.create(
            model=HAIKU_MODEL,
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
            posthog_privacy_mode=True,
        )

        text = response.content[0].text.strip()
        data = parse_llm_json(text)
        if data is None:
            _logger.warning("Could not parse LLM response: %s", text[:200])
            return _fallback_message(campground_name, site_count)

        message = data.get("message", "")
        if not message or not isinstance(message, str):
            return _fallback_message(campground_name, site_count)

        return message

    except Exception as e:
        _logger.warning(
            "LLM enrichment failed for %s: %s", campground_name, e,
        )
        return _fallback_message(campground_name, site_count)
