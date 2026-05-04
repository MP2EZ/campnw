"""
Tag taxonomy audit — single Sonnet call to analyze and improve the tag vocabulary.

Usage:
    ANTHROPIC_API_KEY=sk-... .venv/bin/python3 scripts/audit_tags.py
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys


def get_tag_data(db_path: str = "data/registry.db") -> dict:
    """Pull tag frequency and sample campgrounds from registry."""
    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT name, state, tags FROM campgrounds WHERE tags != '[]'"
    ).fetchall()
    conn.close()

    tag_counts: dict[str, int] = {}
    tag_samples: dict[str, list[str]] = {}
    for name, state, tags_json in rows:
        for tag in json.loads(tags_json):
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
            samples = tag_samples.setdefault(tag, [])
            if len(samples) < 3:
                samples.append(f"{name} ({state})")

    return {
        "tag_counts": dict(
            sorted(tag_counts.items(), key=lambda x: -x[1])
        ),
        "tag_samples": tag_samples,
        "total_campgrounds_with_tags": len(rows),
    }


def main() -> None:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: Set ANTHROPIC_API_KEY environment variable")
        sys.exit(1)

    import anthropic

    from pnw_campsites.enrichment.llm_tags import VALID_TAGS

    data = get_tag_data()

    prompt = f"""Analyze this campground tag taxonomy and recommend improvements.

## Current LLM-extraction vocabulary ({len(VALID_TAGS)} tags)
{json.dumps(VALID_TAGS, indent=2)}

## Tags actually in use (from both LLM extraction and RIDB attribute mapping)
{json.dumps(data["tag_counts"], indent=2)}

## Sample campgrounds per tag
{json.dumps(data["tag_samples"], indent=2)}

## Context
- {data["total_campgrounds_with_tags"]} campgrounds have tags (of ~794 total)
- Tags are used for: search filtering, recommendation affinity scoring, NL search mapping
- Some tags came from RIDB attribute mapping (campfire, pull-through, boat-launch, equestrian) and aren't in the LLM vocabulary
- Users search using natural language ("dog-friendly lakeside spot") — tags should map to user vocabulary

## Analysis requested
1. **Tags to ADD to VALID_TAGS** — tags already in use from RIDB mapping that should be in the LLM vocabulary (so LLM extraction also finds them), plus any gaps in the user search vocabulary
2. **Tags to MERGE** — semantically overlapping tags that should be consolidated
3. **Tags to REMOVE** — tags that are too rare to be useful for filtering, or too generic
4. **Tags missing** — concepts users would search for that have no tag representation
5. **Revised VALID_TAGS list** — the final recommended canonical list

Be specific and actionable. Keep the list practical (30-45 tags max). These are for a PNW camping tool — prioritize tags that help differentiate campgrounds for weekend trip planning."""

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )

    print("=" * 60)
    print("TAG TAXONOMY AUDIT RESULTS")
    print("=" * 60)
    print()
    print(response.content[0].text)


if __name__ == "__main__":
    main()
