"""Historical pattern extraction — per-campground booking tips."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from collections import Counter
from datetime import date

from pnw_campsites.monitor.db import WatchDB

_logger = logging.getLogger(__name__)

MIN_OBSERVATION_DAYS = 30


def get_availability_summary(
    db: WatchDB, campground_id: str,
) -> dict | None:
    """Aggregate availability_history into per-campground stats.

    Returns None if fewer than MIN_OBSERVATION_DAYS of data.
    """
    rows = db._conn.execute(
        "SELECT date, status, observed_at FROM availability_history"
        " WHERE campground_id=? ORDER BY date",
        (campground_id,),
    ).fetchall()

    if not rows:
        return None

    # Count unique observation dates
    observed_dates = {r["observed_at"][:10] for r in rows}
    if len(observed_dates) < MIN_OBSERVATION_DAYS:
        return None

    # Day-of-week availability rates
    day_available = Counter()
    day_total = Counter()
    for r in rows:
        try:
            d = date.fromisoformat(r["date"][:10])
        except ValueError:
            continue
        dow = d.strftime("%A")  # Monday, Tuesday, etc.
        day_total[dow] += 1
        if r["status"] == "Available":
            day_available[dow] += 1

    day_rates = {}
    for dow in ["Monday", "Tuesday", "Wednesday", "Thursday",
                "Friday", "Saturday", "Sunday"]:
        total = day_total.get(dow, 0)
        if total > 0:
            day_rates[dow] = round(day_available.get(dow, 0) / total * 100)

    # Overall fill rate
    total = sum(day_total.values())
    available = sum(day_available.values())
    fill_rate = round((1 - available / total) * 100) if total else 0

    return {
        "campground_id": campground_id,
        "observation_days": len(observed_dates),
        "total_records": len(rows),
        "fill_rate_pct": fill_rate,
        "day_of_week_availability": day_rates,
        "data_through": max(observed_dates),
    }


async def extract_booking_tips(
    db: WatchDB, campground_id: str, campground_name: str = "",
) -> list[str]:
    """Generate 2-4 booking tips from availability_history via Haiku."""
    summary = get_availability_summary(db, campground_id)
    if not summary:
        return []

    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        # Return a basic tip from the data without LLM
        best_day = min(
            summary["day_of_week_availability"].items(),
            key=lambda x: x[1],
            default=None,
        )
        if best_day:
            return [f"Weekday availability is higher — {best_day[0]}s have the most openings."]
        return []

    import anthropic

    client = anthropic.AsyncAnthropic(api_key=api_key)

    prompt = (
        f"Generate 2-4 concise booking tips for {campground_name or campground_id} "
        "based on these availability patterns. Each tip should be 1 sentence, "
        "actionable, and reference specific days or patterns.\n\n"
        f"Data: {json.dumps(summary)}\n\n"
        "Return a JSON array of strings. No preamble."
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
        text = response.content[0].text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        tips = json.loads(text)
        if isinstance(tips, list):
            return [str(t)[:200] for t in tips[:4]]
    except Exception:
        pass
    return []


async def refresh_all_tips(db: WatchDB, registry) -> int:
    """Batch job: refresh booking tips for all campgrounds with enough data.

    Returns count of campgrounds updated.
    """
    # Get campgrounds with availability history
    rows = db._conn.execute(
        "SELECT DISTINCT campground_id FROM availability_history"
    ).fetchall()

    updated = 0
    for row in rows:
        cg_id = row["campground_id"]
        cg = registry.get_by_facility_id(cg_id)
        name = cg.name if cg else ""

        tips = await extract_booking_tips(db, cg_id, name)
        if tips and cg:
            registry.update_booking_tips(cg.id, json.dumps(tips))
            updated += 1

    _logger.info("Refreshed booking tips for %d campgrounds", updated)
    return updated
