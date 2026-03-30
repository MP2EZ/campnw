"""Batch enrichment via the Anthropic Message Batches API.

Submits all enrichment requests (tags + vibe + description) as a single batch,
polls for completion, and writes results back to the registry.

Usage:
    .venv/bin/python3 -m pnw_campsites enrich --batch --limit 1370
"""

from __future__ import annotations

import json
import logging
import time

from pnw_campsites.enrichment.llm_tags import VALID_TAGS, TagExtractionResult, _truncate
from pnw_campsites.registry.db import CampgroundRegistry
from pnw_campsites.registry.models import Campground

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompt builder — single prompt per campground for tags + vibe + description
# ---------------------------------------------------------------------------


def _build_prompt(cg: Campground) -> str:
    """Build a combined enrichment prompt for one campground."""
    description = cg.notes or cg.name
    size_hint = f"Sites: {cg.total_sites}" if cg.total_sites else ""
    existing_tags = f"Existing tags: {', '.join(cg.tags)}" if cg.tags else ""

    return (
        "Extract structured metadata for this campground. Return ONLY a JSON "
        "object with these keys:\n\n"
        f'- "tags": array of tags from this list: {json.dumps(VALID_TAGS)}\n'
        '  Only include tags clearly supported by the description.\n'
        '- "vibe": One sentence (max 100 chars) capturing the feel or character.\n'
        '- "elevator_pitch": One sentence (max 120 chars) for a search result card.\n'
        '- "description_rewrite": 2-3 sentences (max 350 chars) for an expanded view.\n'
        '- "best_for": Short label (max 50 chars) for who this campground suits.\n\n'
        f"Campground: {cg.name}\n"
        f"State: {cg.state}\n"
        f"{existing_tags}\n"
        f"{size_hint}\n"
        f"Description: {description[:2000]}\n\n"
        "Only reference features explicitly stated. No invented amenities. "
        "Return ONLY the JSON object."
    )


# ---------------------------------------------------------------------------
# Batch submission
# ---------------------------------------------------------------------------


def build_batch_requests(campgrounds: list[Campground]) -> list[dict]:
    """Build the list of batch request objects."""
    requests = []
    for cg in campgrounds:
        requests.append({
            "custom_id": f"{cg.booking_system.value}:{cg.facility_id}",
            "params": {
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 500,
                "messages": [
                    {"role": "user", "content": _build_prompt(cg)},
                ],
            },
        })
    return requests


def submit_batch(api_key: str, campgrounds: list[Campground]) -> str:
    """Submit a batch of enrichment requests. Returns batch_id."""
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    requests = build_batch_requests(campgrounds)

    _logger.info("Submitting batch of %d requests...", len(requests))
    batch = client.messages.batches.create(requests=requests)

    _logger.info("Batch %s submitted (%d requests)", batch.id, len(requests))
    return batch.id


# ---------------------------------------------------------------------------
# Polling
# ---------------------------------------------------------------------------


def poll_batch(api_key: str, batch_id: str, poll_interval: int = 10) -> dict:
    """Poll until batch completes. Returns the batch object as dict."""
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)

    while True:
        batch = client.messages.batches.retrieve(batch_id)
        counts = batch.request_counts
        _logger.info(
            "Batch %s: %s | succeeded=%d errored=%d expired=%d",
            batch_id, batch.processing_status,
            counts.succeeded, counts.errored, counts.expired,
        )

        if batch.processing_status == "ended":
            return {
                "id": batch.id,
                "status": batch.processing_status,
                "succeeded": counts.succeeded,
                "errored": counts.errored,
                "expired": counts.expired,
            }

        time.sleep(poll_interval)


# ---------------------------------------------------------------------------
# Result processing
# ---------------------------------------------------------------------------


def _parse_json_response(text: str) -> dict | None:
    """Parse JSON from Claude's response, handling markdown fences."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        text = text.rsplit("```", 1)[0].strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def process_results(
    api_key: str,
    batch_id: str,
    registry: CampgroundRegistry,
    dry_run: bool = False,
) -> dict:
    """Process batch results and write to registry. Returns stats."""
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)

    stats = {"succeeded": 0, "errored": 0, "skipped": 0}

    for result in client.messages.batches.results(batch_id):
        custom_id = result.custom_id  # "recgov:232465"
        parts = custom_id.split(":", 1)
        facility_id = parts[1] if len(parts) == 2 else custom_id

        if result.result.type != "succeeded":
            _logger.warning(
                "Failed: %s — %s",
                custom_id, getattr(result.result, "error", "unknown"),
            )
            stats["errored"] += 1
            continue

        text = result.result.message.content[0].text
        data = _parse_json_response(text)
        if not data:
            _logger.warning("JSON parse failed for %s", custom_id)
            stats["errored"] += 1
            continue

        # Find campground in registry
        cg = registry.get_by_facility_id(facility_id)
        if not cg:
            _logger.warning("Campground not found: %s", custom_id)
            stats["skipped"] += 1
            continue

        # Extract and validate tags
        raw_tags = data.get("tags", [])
        try:
            validated = TagExtractionResult(tags=raw_tags)
            tags = validated.tags
        except Exception:
            tags = [t for t in raw_tags if t in VALID_TAGS]

        # Extract descriptions with truncation
        vibe = _truncate(data.get("vibe", ""), 100)
        pitch = _truncate(data.get("elevator_pitch", ""), 120)
        desc = _truncate(data.get("description_rewrite", ""), 350)
        best = _truncate(data.get("best_for", ""), 50)

        if dry_run:
            _logger.info(
                "DRY RUN: %s -> tags=%s pitch=%s",
                cg.name, tags, pitch,
            )
            stats["succeeded"] += 1
            continue

        # Write to registry
        if tags:
            merged = list(dict.fromkeys(cg.tags + tags))  # dedupe
            registry.update_tags(cg.id, merged)

        if vibe:
            registry.update_vibe(cg.id, vibe)

        if pitch or desc or best:
            registry.update_description(cg.id, pitch, desc, best)

        _logger.info("Enriched: %s -> %d tags, pitch=%s", cg.name, len(tags), pitch[:60])
        stats["succeeded"] += 1

    return stats


# ---------------------------------------------------------------------------
# Top-level batch enrichment
# ---------------------------------------------------------------------------


async def enrich_registry_batch(
    registry_path: str | None = None,
    api_key: str | None = None,
    limit: int = 1370,
    dry_run: bool = False,
    batch_id: str | None = None,
) -> int:
    """Enrich campgrounds via the Batch API.

    If batch_id is provided, skip submission and just poll/process results.
    Returns count of successfully enriched campgrounds.
    """
    import os

    api_key = api_key or os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        _logger.error("ANTHROPIC_API_KEY not set")
        return 0

    registry = (
        CampgroundRegistry(registry_path) if registry_path else CampgroundRegistry()
    )

    if not batch_id:
        # Find campgrounds needing enrichment
        all_cgs = registry.search(enabled_only=True)
        candidates = [
            cg for cg in all_cgs
            if not cg.tags or not cg.elevator_pitch
        ][:limit]

        if not candidates:
            _logger.info("No campgrounds need enrichment")
            registry.close()
            return 0

        _logger.info("Submitting batch for %d campgrounds...", len(candidates))

        if dry_run:
            # In dry-run, just show what would be submitted
            for cg in candidates:
                _logger.info("Would enrich: %s (%s)", cg.name, cg.facility_id)
            registry.close()
            return len(candidates)

        batch_id = submit_batch(api_key, candidates)
        print(f"Batch submitted: {batch_id}")
        print("Polling for completion...")

    # Poll for completion
    result = poll_batch(api_key, batch_id)
    print(
        f"Batch complete: {result['succeeded']} succeeded, "
        f"{result['errored']} errored, {result['expired']} expired"
    )

    # Process results
    stats = process_results(api_key, batch_id, registry, dry_run=dry_run)
    registry.close()

    print(
        f"Processed: {stats['succeeded']} enriched, "
        f"{stats['errored']} errors, {stats['skipped']} skipped"
    )
    return stats["succeeded"]
