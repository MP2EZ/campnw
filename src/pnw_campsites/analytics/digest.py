"""Weekly search analytics digest — aggregates search history into insights."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta

_logger = logging.getLogger(__name__)


def get_search_analytics(watch_db, since_days: int = 7) -> dict:
    """Aggregate search_history for the last N days.

    Returns a dict with analytics data, or empty dict if insufficient data.
    """
    since = (datetime.now() - timedelta(days=since_days)).isoformat()

    conn = watch_db._conn
    rows = conn.execute(
        "SELECT params, result_count, searched_at FROM search_history "
        "WHERE searched_at >= ? ORDER BY searched_at DESC",
        (since,),
    ).fetchall()

    if not rows:
        return {}

    total = len(rows)
    zero_results = sum(1 for _, rc, _ in rows if rc == 0)

    # Aggregate by state, tags, from_location
    state_counts: dict[str, int] = {}
    tag_counts: dict[str, int] = {}
    location_counts: dict[str, int] = {}

    for params_json, _, _ in rows:
        try:
            p = json.loads(params_json) if isinstance(params_json, str) else params_json
        except (json.JSONDecodeError, TypeError):
            continue

        state = p.get("state")
        if state:
            state_counts[state] = state_counts.get(state, 0) + 1

        tags = p.get("tags", "")
        if tags:
            for tag in tags.split(","):
                tag = tag.strip()
                if tag:
                    tag_counts[tag] = tag_counts.get(tag, 0) + 1

        loc = p.get("from_location") or p.get("from")
        if loc:
            location_counts[loc] = location_counts.get(loc, 0) + 1

    return {
        "period_days": since_days,
        "total_searches": total,
        "zero_result_searches": zero_results,
        "zero_result_rate": round(zero_results / total * 100, 1) if total else 0,
        "states": dict(sorted(state_counts.items(), key=lambda x: -x[1])),
        "tags": dict(sorted(tag_counts.items(), key=lambda x: -x[1])[:10]),
        "locations": dict(sorted(location_counts.items(), key=lambda x: -x[1])),
    }


def format_digest(analytics: dict) -> str:
    """Format analytics dict into a human-readable text report."""
    if not analytics:
        return "No searches recorded this week."

    lines = [
        f"campable Weekly Digest ({analytics['period_days']}-day window)",
        f"{'=' * 40}",
        f"Total searches: {analytics['total_searches']}",
        f"Zero-result rate: {analytics['zero_result_rate']}%"
        f" ({analytics['zero_result_searches']}/{analytics['total_searches']})",
        "",
    ]

    if analytics["states"]:
        lines.append("States searched:")
        for state, count in analytics["states"].items():
            lines.append(f"  {state}: {count}")
        lines.append("")

    if analytics["tags"]:
        lines.append("Top tags:")
        for tag, count in list(analytics["tags"].items())[:5]:
            lines.append(f"  {tag}: {count}")
        lines.append("")

    if analytics["locations"]:
        lines.append("Search origins:")
        for loc, count in analytics["locations"].items():
            lines.append(f"  {loc}: {count}")

    return "\n".join(lines)


async def generate_weekly_digest(watch_db) -> str:
    """Generate the weekly digest report. Returns formatted text."""
    analytics = get_search_analytics(watch_db)

    if not analytics or analytics.get("total_searches", 0) < 10:
        _logger.info(
            "Skipping digest: only %d searches",
            analytics.get("total_searches", 0) if analytics else 0,
        )
        return format_digest(analytics)

    report = format_digest(analytics)

    # Optionally enhance with Haiku narrative
    try:
        import os

        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        if api_key:
            from pnw_campsites.posthog_client import get_posthog_client

            try:
                from posthog.ai.anthropic import AsyncAnthropic
                client = AsyncAnthropic(api_key=api_key, posthog_client=get_posthog_client())
            except (ImportError, ValueError):
                import anthropic
                client = anthropic.AsyncAnthropic(api_key=api_key)
            prompt = (
                "Analyze this weekly search data for a campsite tool and "
                "write 3-5 bullet points of actionable product insights. "
                "Focus on: unmet demand, popular vs underserved areas, "
                "and any surprising patterns.\n\n"
                f"{json.dumps(analytics, indent=2)}"
            )
            response = await client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=300,
                messages=[{"role": "user", "content": prompt}],
            )
            insights = response.content[0].text.strip()
            report += f"\n\nAI Insights:\n{insights}"
    except Exception as e:
        _logger.warning("Digest AI enhancement failed: %s", e)

    return report
