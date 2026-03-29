"""Notification quality feedback loop — monthly analysis of notification effectiveness."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime

from pnw_campsites.monitor.db import WatchDB

_logger = logging.getLogger(__name__)

MIN_NOTIFICATIONS = 50


def get_notification_stats(db: WatchDB, month: str) -> dict | None:
    """Compute notification stats for a given month (YYYY-MM).

    Returns None if insufficient data.
    """
    start = f"{month}-01"
    # End of month: safe to use month+"-32" since SQLite compares strings
    end = f"{month}-32"

    rows = db._conn.execute(
        "SELECT channel, status, changes_count, sent_at"
        " FROM notification_log"
        " WHERE sent_at >= ? AND sent_at < ?"
        " ORDER BY sent_at",
        (start, end),
    ).fetchall()

    if len(rows) < MIN_NOTIFICATIONS:
        return None

    total = len(rows)
    by_channel: dict[str, int] = {}
    by_status: dict[str, int] = {}
    total_changes = 0

    for r in rows:
        ch = r["channel"]
        st = r["status"]
        by_channel[ch] = by_channel.get(ch, 0) + 1
        by_status[st] = by_status.get(st, 0) + 1
        total_changes += r["changes_count"] or 0

    return {
        "month": month,
        "total_notifications": total,
        "total_changes_reported": total_changes,
        "by_channel": by_channel,
        "by_status": by_status,
        "sent_rate": round(by_status.get("sent", 0) / total * 100) if total else 0,
    }


async def generate_quality_report(db: WatchDB, month: str) -> dict | None:
    """Generate a notification quality report for the given month.

    Stores result in analytics_digests table.
    """
    stats = get_notification_stats(db, month)
    if not stats:
        _logger.info(
            "Skipping notification quality for %s: insufficient data", month,
        )
        return None

    analysis = await _analyze_with_haiku(stats)

    # Store in analytics_digests
    now = datetime.now().isoformat()
    report = {
        "stats": stats,
        "analysis": analysis,
        "generated_at": now,
    }

    db._conn.execute(
        "INSERT OR REPLACE INTO analytics_digests"
        " (digest_type, period, content, generated_at)"
        " VALUES (?, ?, ?, ?)",
        ("notification_quality", month, json.dumps(report), now),
    )
    db._conn.commit()

    _logger.info("Generated notification quality report for %s", month)
    return report


async def _analyze_with_haiku(stats: dict) -> str | None:
    """Call Haiku to analyze notification patterns."""
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        return None

    import anthropic

    client = anthropic.AsyncAnthropic(api_key=api_key)

    prompt = (
        "Analyze these campsite notification statistics and suggest "
        "2-3 specific improvements to notification timing, content, or "
        "targeting. Be concise and actionable.\n\n"
        f"Stats: {json.dumps(stats)}\n\n"
        "No preamble. Just the suggestions."
    )

    try:
        response = await asyncio.wait_for(
            client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=300,
                messages=[{"role": "user", "content": prompt}],
            ),
            timeout=3.0,
        )
        return response.content[0].text.strip()
    except Exception:
        return None
