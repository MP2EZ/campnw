"""LLM-based tag extraction from campground descriptions."""

from __future__ import annotations

import json
import logging

from pydantic import BaseModel, field_validator

_logger = logging.getLogger(__name__)

VALID_TAGS = [
    "lakeside",
    "riverside",
    "beach",
    "oceanfront",
    "old-growth",
    "forest",
    "alpine",
    "meadow",
    "desert",
    "pet-friendly",
    "rv-friendly",
    "tent-only",
    "walk-in",
    "trails",
    "swimming",
    "fishing",
    "boating",
    "climbing",
    "shade",
    "scenic",
    "remote",
    "kid-friendly",
    "hot-springs",
    "waterfall",
    "glacier",
    "volcanic",
    "bear-box",
    "group-sites",
    "horse-camp",
    "accessible",
]


class TagExtractionResult(BaseModel):
    tags: list[str]

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v):
        return [t for t in v if t in VALID_TAGS]


async def extract_tags(
    name: str,
    description: str,
    api_key: str,
) -> list[str]:
    """Extract structured tags from a campground description using Claude."""
    import anthropic

    if not description or len(description.strip()) < 20:
        return []

    client = anthropic.AsyncAnthropic(api_key=api_key)

    prompt = f"""Extract campground attribute tags from this description.

Campground: {name}
Description: {description[:2000]}

Return a JSON object with a "tags" array containing only tags from this list:
{json.dumps(VALID_TAGS)}

Only include tags that are clearly supported by the description. Be conservative.
Return ONLY the JSON object, nothing else."""

    try:
        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )

        text = response.content[0].text.strip()
        # Parse JSON from response
        try:
            result = TagExtractionResult.model_validate_json(text)
            return result.tags
        except Exception:
            # Try extracting JSON from markdown code block
            if "```" in text:
                json_str = text.split("```")[1]
                if json_str.startswith("json"):
                    json_str = json_str[4:]
                result = TagExtractionResult.model_validate_json(json_str.strip())
                return result.tags
            return []
    except anthropic.APIError as e:
        _logger.warning("Anthropic API error for %s: %s", name, e)
        return []


async def generate_vibe(
    name: str,
    tags: list[str],
    site_count: int | None,
    description: str,
    api_key: str,
) -> str:
    """Generate a one-sentence campground character description."""
    import anthropic

    client = anthropic.AsyncAnthropic(api_key=api_key)

    size_hint = f" It has {site_count} sites." if site_count else ""
    tag_hint = f" Tags: {', '.join(tags)}." if tags else ""

    prompt = (
        f"Write a single sentence (max 80 characters) capturing the feel, character,"
        f" or who this campground is best for.\n\n"
        f"Campground: {name}\n"
        f"Description: {description[:2000]}\n"
        f"{tag_hint}{size_hint}\n\n"
        f"Return ONLY the sentence, no quotes, no explanation."
    )

    try:
        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=100,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text.strip().strip('"').strip("'")
        # Enforce 80-char limit
        if len(text) > 80:
            text = text[:77] + "..."
        return text
    except Exception as e:
        _logger.warning("Vibe generation failed for %s: %s", name, e)
        return ""


async def enrich_registry(
    registry_path: str | None = None,
    api_key: str | None = None,
    limit: int = 50,
    dry_run: bool = False,
) -> int:
    """Enrich campgrounds that lack tags. Returns count enriched."""
    import os

    from pnw_campsites.registry.db import CampgroundRegistry

    api_key = api_key or os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        _logger.error("ANTHROPIC_API_KEY not set")
        return 0

    registry = (
        CampgroundRegistry(registry_path) if registry_path else CampgroundRegistry()
    )

    # Get campgrounds needing enrichment
    all_cgs = registry.search(enabled_only=True)
    candidates = [cg for cg in all_cgs if not cg.tags or len(cg.tags) == 0][
        :limit
    ]

    _logger.info(
        "Found %d campgrounds needing enrichment (limit %d)",
        len(candidates),
        limit,
    )

    enriched = 0
    for cg in candidates:
        # Use description from notes field or name
        description = cg.notes or cg.name
        tags = await extract_tags(cg.name, description, api_key)

        if dry_run:
            _logger.info("DRY RUN: %s -> %s", cg.name, tags)
            enriched += 1
            continue

        if tags:
            # Merge with existing tags
            merged = list(set(cg.tags + tags))
            registry.update_tags(cg.id, merged)
            _logger.info("Enriched: %s -> %s", cg.name, merged)
            enriched += 1

    # Generate vibes for campgrounds that lack them
    all_cgs = registry.search(enabled_only=True)
    vibe_candidates = [cg for cg in all_cgs if not cg.vibe][:limit]

    _logger.info(
        "Found %d campgrounds needing vibes (limit %d)",
        len(vibe_candidates),
        limit,
    )

    for cg in vibe_candidates:
        description = cg.notes or cg.name
        vibe = await generate_vibe(
            cg.name, cg.tags, cg.total_sites, description, api_key,
        )

        if dry_run:
            _logger.info("DRY RUN vibe: %s -> %s", cg.name, vibe)
            continue

        if vibe:
            registry.update_vibe(cg.id, vibe)
            _logger.info("Vibe: %s -> %s", cg.name, vibe)

    registry.close()
    return enriched
