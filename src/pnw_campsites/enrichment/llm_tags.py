"""LLM-based tag extraction from campground descriptions."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from pydantic import BaseModel, field_validator

_logger = logging.getLogger(__name__)


def _truncate(text: str, max_len: int) -> str:
    """Truncate text at the last sentence or word boundary within max_len."""
    if len(text) <= max_len:
        return text
    # Try to cut at last sentence boundary
    truncated = text[:max_len]
    last_period = truncated.rfind(". ")
    if last_period > max_len // 2:
        return truncated[: last_period + 1]
    # Fall back to last word boundary
    last_space = truncated.rfind(" ")
    if last_space > 0:
        return truncated[:last_space] + "..."
    return truncated[:max_len]


# Shared by the sync and batch prompts. BRAND.md: no outdoor-lifestyle
# marketing copy; the user is already a camper.
COPY_RULES = (
    "Rules: State facts given above and nothing else. No invented amenities, "
    "views or activities. No mood or quality words (peaceful, serene, "
    "tranquil, scenic, stunning, pristine, cozy, charming, rustic charm, "
    "convenient, perfect, ideal, haven, retreat, escape, getaway, nestled, "
    "gem). No audience labels (lovers, enthusiasts, seekers, families "
    "wanting). Never say that information is limited or unavailable."
)


VALID_TAGS = [
    # Location / setting
    "lakeside",
    "riverside",
    "beach",       # includes former oceanfront
    "old-growth",
    "forest",
    "alpine",
    "desert",
    "backcountry",
    "remote",
    # Accommodation type
    "rv-friendly",
    "tent-only",
    "walk-in",
    "pull-through",
    "group-sites",
    "dispersed",
    # Activities
    "trails",
    "swimming",
    "fishing",
    "boating",
    "boat-launch",  # a boat ramp, not boat-only access (see boat-in)
    "boat-in",      # only reachable by boat; no road access
    "equestrian",  # includes former horse-camp
    "climbing",
    "winter-camping",
    # Amenities / features
    "pet-friendly",
    "kid-friendly",
    "accessible",
    "campfire",
    "shade",
    "hot-springs",
    "waterfall",
]

# Tags renamed/merged — map old names to new canonical names
_TAG_RENAMES = {
    "oceanfront": "beach",
    "horse-camp": "equestrian",
    "scenic": None,    # removed: too generic
    "glacier": None,   # removed: zero usage
    "volcanic": None,  # removed: 1 usage, too specific
    "bear-box": None,  # removed: safety feature, not a search criterion
    "meadow": None,    # removed: 2 usages, too generic
}


class TagExtractionResult(BaseModel):
    tags: list[str]

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v):
        result = []
        for t in v:
            if t in VALID_TAGS:
                result.append(t)
            elif t in _TAG_RENAMES and _TAG_RENAMES[t] is not None:
                result.append(_TAG_RENAMES[t])
            # else: drop removed/unknown tags
        return list(dict.fromkeys(result))  # dedupe preserving order


async def extract_tags(
    name: str,
    description: str,
    api_key: str,
) -> list[str]:
    """Extract structured tags from a campground description using Claude."""
    from pnw_campsites.posthog_client import HAIKU_MODEL, get_anthropic_client

    if not description or len(description.strip()) < 20:
        return []

    client = get_anthropic_client(api_key)

    prompt = f"""Extract campground attribute tags from this description.

Campground: {name}
Description: {description[:2000]}

Return a JSON object with a "tags" array containing only tags from this list:
{json.dumps(VALID_TAGS)}

Tag definitions that are easy to confuse:
- boat-in: only reachable by boat or kayak; no road access (marine-park islands).
- boat-launch: has a boat ramp. Does not mean boat-in.
- walk-in: a hike from the car. Does not mean boat-in.
- beach: a real sand or pebble beach (saltwater or a lake swim beach). Not a river bank.

Only include tags that are clearly supported by the description. Be conservative.
Return ONLY the JSON object, nothing else."""

    try:
        response = await client.messages.create(
            model=HAIKU_MODEL,
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
            posthog_privacy_mode=True,
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
    except Exception as e:
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
    from pnw_campsites.posthog_client import HAIKU_MODEL, get_anthropic_client

    client = get_anthropic_client(api_key)

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
            model=HAIKU_MODEL,
            max_tokens=150,
            messages=[{"role": "user", "content": prompt}],
            posthog_privacy_mode=True,
        )
        text = response.content[0].text.strip().strip('"').strip("'")
        # Truncate at sentence boundary
        text = _truncate(text, 100)
        return text
    except Exception as e:
        _logger.warning("Vibe generation failed for %s: %s", name, e)
        return ""


async def generate_description(
    name: str,
    tags: list[str],
    total_sites: int | None,
    state: str,
    notes: str,
    api_key: str,
    usage: dict[str, int] | None = None,
) -> dict[str, str]:
    """Generate elevator_pitch, description_rewrite, best_for for a campground.

    Returns dict with keys: elevator_pitch, description_rewrite, best_for.
    Empty dict on failure. ``usage``, when given, accumulates input/output tokens.
    """
    from pnw_campsites.posthog_client import HAIKU_MODEL, get_anthropic_client

    client = get_anthropic_client(api_key)

    tag_str = ", ".join(tags) if tags else "none"
    size_str = f"{total_sites} sites" if total_sites else "unknown"
    source_desc = notes[:2000] if notes else "none"

    # The vibe is earlier LLM output, not a source: feeding it back in carried
    # its marketing tone ("rustic charm", "serene escape") into the new copy.
    prompt = (
        "Write short, plain copy for this campground. Return ONLY a JSON "
        "object with these keys:\n"
        '- "elevator_pitch": One sentence (max 110 chars) for a search result '
        "card. Setting and what is there, from the facts below. Don't repeat "
        "the campground name. With no facts beyond the name and state, just "
        "say what kind of camp it is and where, e.g. \"Horse camp in "
        "California.\"\n"
        '- "description_rewrite": 1-3 sentences (max 350 chars) for the '
        "campground's page. Only facts from below. When the facts are thin, "
        "write one short sentence.\n"
        '- "best_for": What the campground suits, as uses or site types (max '
        '40 chars). Examples: "tent camping, fishing", "horse camping", "group '
        'camping", "RVs and tents". Lowercase. Only uses the tags or '
        'description support; an empty string if none. Never a kind of '
        "person.\n\n"
        f"Campground: {name}\n"
        f"State: {state}\n"
        f"Tags: {tag_str}\n"
        f"Sites: {size_str}\n"
        f"Description: {source_desc}\n\n"
        f"{COPY_RULES} Return ONLY the JSON."
    )

    try:
        response = await client.messages.create(
            model=HAIKU_MODEL,
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}],
            posthog_privacy_mode=True,
        )
        if usage is not None:
            usage["input_tokens"] += response.usage.input_tokens
            usage["output_tokens"] += response.usage.output_tokens
        text = response.content[0].text.strip()
        # Handle markdown code blocks
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        result = json.loads(text)
        # Enforce length limits — truncate at sentence or word boundary
        pitch = _truncate(result.get("elevator_pitch", ""), 120)
        desc = _truncate(result.get("description_rewrite", ""), 350)
        best = _truncate(result.get("best_for", ""), 50)
        return {
            "elevator_pitch": pitch,
            "description_rewrite": desc,
            "best_for": best,
        }
    except Exception as e:
        _logger.warning("Description generation failed for %s: %s", name, e)
        return {}


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

    # Generate descriptions for campgrounds that lack them
    all_cgs = registry.search(enabled_only=True)
    desc_candidates = [cg for cg in all_cgs if not cg.elevator_pitch][:limit]

    _logger.info(
        "Found %d campgrounds needing descriptions (limit %d)",
        len(desc_candidates),
        limit,
    )

    for cg in desc_candidates:
        desc = await generate_description(
            cg.name, cg.tags, cg.total_sites, cg.state, cg.notes, api_key,
        )

        if dry_run:
            _logger.info("DRY RUN desc: %s -> %s", cg.name, desc)
            continue

        if desc:
            registry.update_description(
                cg.id,
                desc.get("elevator_pitch", ""),
                desc.get("description_rewrite", ""),
                desc.get("best_for", ""),
            )
            _logger.info(
                "Description: %s -> %s",
                cg.name, desc.get("elevator_pitch", ""),
            )

    registry.close()
    return enriched


async def regenerate_descriptions(
    registry_path: str | None = None,
    api_key: str | None = None,
    limit: int | None = None,
    dry_run: bool = False,
    export_path: Path | None = None,
    concurrency: int = 8,
) -> tuple[int, int, dict[str, int]]:
    """Rewrite pitch, description and best-for for every enabled campground.

    Unlike ``enrich_registry``, existing copy is overwritten, and tags and vibe
    are left alone. A failed generation keeps the old copy. When ``export_path``
    is set (and not a dry run), the result is exported to the pitch fixture,
    which is how new copy reaches prod.

    Returns (rewritten, failed, token usage).
    """
    import asyncio
    import os

    from pnw_campsites.registry.db import CampgroundRegistry
    from pnw_campsites.registry.pitch_fixture import export_pitch_fixture

    api_key = api_key or os.getenv("ANTHROPIC_API_KEY", "")
    usage = {"input_tokens": 0, "output_tokens": 0}
    if not api_key:
        _logger.error("ANTHROPIC_API_KEY not set")
        return 0, 0, usage

    registry = (
        CampgroundRegistry(registry_path) if registry_path else CampgroundRegistry()
    )
    candidates = registry.search(enabled_only=True)[:limit]
    _logger.info("Rewriting copy for %d campgrounds", len(candidates))
    sem = asyncio.Semaphore(concurrency)

    async def one(cg):
        async with sem:
            return cg, await generate_description(
                cg.name, cg.tags, cg.total_sites, cg.state, cg.notes, api_key,
                usage=usage,
            )

    rewritten = failed = 0
    for fut in asyncio.as_completed([one(cg) for cg in candidates]):
        cg, desc = await fut
        if not desc.get("elevator_pitch"):
            failed += 1
            _logger.warning("No copy generated for %s; keeping the old copy", cg.name)
            continue
        rewritten += 1
        if dry_run:
            _logger.info(
                "DRY RUN %s\n  before: %s | %s\n  after:  %s | %s\n  desc:   %s",
                cg.name, cg.elevator_pitch, cg.best_for,
                desc["elevator_pitch"], desc["best_for"], desc["description_rewrite"],
            )
            continue
        registry.update_description(
            cg.id, desc["elevator_pitch"], desc["description_rewrite"], desc["best_for"],
        )

    if export_path is not None and not dry_run:
        rows = export_pitch_fixture(registry._conn, export_path)
        _logger.info("Exported %d rows to %s", rows, export_path)
    registry.close()
    return rewritten, failed, usage
