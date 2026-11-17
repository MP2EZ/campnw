"""Historical pattern extraction — per-campground booking tips.

Tips come from cancellations, not from final night statuses: a night that has
passed always ends as Reserved, so "how often a night was open" only measures
when we last looked. A cancellation is a Reserved -> Available transition
before the night. Statuses that are not online bookings (first-come-first-
served, not reservable, closed, not yet released) are reported as excluded and
never count as booked.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from collections import Counter
from datetime import date, datetime
from statistics import median

from pnw_campsites.monitor.db import WatchDB
from pnw_campsites.monitor.pacific import pacific_today
from pnw_campsites.registry.models import BookingSystem

_logger = logging.getLogger(__name__)

MIN_OBSERVATION_DAYS = 30
# Tips describe the past season, so they stop when polling stops.
MAX_DATA_AGE_DAYS = 30
MIN_BOOKED_SITE_NIGHTS = 200
MIN_HELD_HOURS = 1.0

_RESERVABLE = ("Available", "Reserved")
_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")
# The lead-time bucket edges, which tips quote as "3 to 7 days".
_BUCKET_NUMBERS = {"0", "2", "3", "7", "8", "30", "31"}
_EXCLUDED = {
    "Open": "first_come_first_served",
    "Not Reservable": "not_reservable",
    "Not Reservable Management": "not_reservable",
    "Not Available": "not_reservable",
    "Closed": "closed",
    "NYR": "not_yet_released",
}
_WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday",
             "Friday", "Saturday", "Sunday"]
_LEAD_BUCKETS = ((2, "0-2"), (7, "3-7"), (30, "8-30"))

# docs/BRAND.md: no manufactured urgency, no monitoring language, and no claims
# the data cannot back (a full campground, an instant fill).
_BANNED = re.compile(
    r"!|sell(s|ing)? out|sold out|fully booked|100%|instant|immediately"
    r"|act fast|hurry|don'?t miss|before (it'?s|they'?re) gone|snag|grab"
    r"|alert|monitor|data|observ|polling|guarantee",
    re.IGNORECASE,
)


def _lead_bucket(days: int) -> str:
    for limit, label in _LEAD_BUCKETS:
        if days <= limit:
            return label
    return "31+"


def _hours_between(start: str, end: str) -> float:
    delta = datetime.fromisoformat(end) - datetime.fromisoformat(start)
    return delta.total_seconds() / 3600


def _months(first: date, last: date) -> str:
    if (first.year, first.month) == (last.year, last.month):
        return f"{first:%B %Y}"
    if first.year == last.year:
        return f"{first:%B} to {last:%B %Y}"
    return f"{first:%B %Y} to {last:%B %Y}"


def _duration(hours: float) -> str:
    if hours < 2:
        return f"{round(hours * 60)} minutes"
    if hours < 48:
        return f"{round(hours)} hours"
    return f"{round(hours / 24)} days"


def _pct(part: int, whole: int) -> float:
    return round(part / whole * 100, 1) if whole else 0.0


def get_availability_summary(
    db: WatchDB, campground_id: str, today: date | None = None,
) -> dict | None:
    """Cancellation stats for one campground, or None when too thin or stale.

    Only nights inside the checked window count: they were watched up to
    arrival, so a short-notice cancellation could have been seen for each.
    """
    today = today or pacific_today()
    first_seen, last_seen = db._conn.execute(
        "SELECT MIN(first_seen), MAX(last_seen) FROM availability_daily"
        " WHERE campground_id=?",
        (campground_id,),
    ).fetchone()
    if not first_seen:
        return None
    first_seen, last_seen = first_seen[:10], last_seen[:10]
    last_day = date.fromisoformat(last_seen)
    if (last_day - date.fromisoformat(first_seen)).days < MIN_OBSERVATION_DAYS:
        return None
    if (today - last_day).days > MAX_DATA_AGE_DAYS:
        return None

    excluded: Counter[str] = Counter()
    for r in db._conn.execute(
        "SELECT status, COUNT(*) AS n FROM availability_daily"
        " WHERE campground_id=? AND date <= ? GROUP BY status",
        (campground_id, last_seen),
    ):
        if r["status"] not in _RESERVABLE:
            excluded[_EXCLUDED.get(r["status"], "other")] += r["n"]

    # Final statuses can't be the denominator: a booked night that reopened
    # can end up first-come-first-served. Count nights booked at some point.
    booked_by_weekday: Counter[str] = Counter()
    first_night = last_night = ""
    for r in db._conn.execute(
        "SELECT CAST(strftime('%w', date) AS INTEGER) AS dow, COUNT(*) AS n,"
        " MIN(date) AS first_night, MAX(date) AS last_night FROM ("
        "  SELECT DISTINCT site_id, date FROM status_transitions"
        "  WHERE campground_id=? AND date <= ? AND new_status='Reserved'"
        ") GROUP BY dow",
        (campground_id, last_seen),
    ):
        booked_by_weekday[_WEEKDAYS[(r["dow"] - 1) % 7]] = r["n"]
        first_night = min(first_night or r["first_night"], r["first_night"])
        last_night = max(last_night, r["last_night"])
    booked = sum(booked_by_weekday.values())
    if booked < MIN_BOOKED_SITE_NIGHTS:
        return None

    # Filtered in SQL and streamed: a busy campground has 100k+ transitions,
    # and holding them all in Python OOM-killed the 512MB prod machine.
    cancellations = db._conn.execute(
        "SELECT site_id, date, observed_at, prev_at, next_status, next_at FROM ("
        "  SELECT site_id, date, old_status, new_status, observed_at,"
        "   LAG(observed_at) OVER w AS prev_at,"
        "   LEAD(new_status) OVER w AS next_status,"
        "   LEAD(observed_at) OVER w AS next_at"
        "  FROM status_transitions WHERE campground_id=? AND date <= ?"
        "  WINDOW w AS (PARTITION BY site_id, date ORDER BY observed_at)"
        ") WHERE old_status='Reserved' AND new_status='Available'",
        (campground_id, last_seen),
    )

    reopened: set[tuple[str, str]] = set()
    reopened_by_weekday: Counter[str] = Counter()
    by_lead: Counter[str] = Counter()
    hours_open: list[float] = []
    for t in cancellations:
        night = date.fromisoformat(t["date"][:10])
        lead = (night - date.fromisoformat(t["observed_at"][:10])).days
        if lead < 0:
            continue
        # A cart hold shows as Reserved and drops back within minutes.
        if t["prev_at"] and _hours_between(t["prev_at"], t["observed_at"]) < MIN_HELD_HOURS:
            continue
        by_lead[_lead_bucket(lead)] += 1
        if (t["site_id"], t["date"]) not in reopened:
            reopened.add((t["site_id"], t["date"]))
            reopened_by_weekday[night.strftime("%A")] += 1
        if t["next_status"] == "Reserved":
            hours_open.append(_hours_between(t["observed_at"], t["next_at"]))

    total = sum(by_lead.values())
    first, last = date.fromisoformat(first_night[:10]), date.fromisoformat(last_night[:10])
    return {
        "months": _months(first, last),
        "booked_site_nights": booked,
        "pct_of_booked_site_nights_that_reopened": _pct(len(reopened), booked),
        "pct_of_booked_site_nights_that_reopened_by_night_of_week": {
            d: _pct(reopened_by_weekday[d], booked_by_weekday[d])
            for d in _WEEKDAYS if booked_by_weekday[d]
        },
        "cancellations": total,
        "pct_of_cancellations_by_days_before_arrival": {
            label: _pct(by_lead[label], total)
            for label in ("0-2", "3-7", "8-30", "31+")
        },
        "median_time_a_reopened_site_stayed_open": (
            _duration(median(hours_open)) if hours_open else None
        ),
        "excluded_site_nights_not_booked_online": dict(excluded),
    }


_PROMPT = """\
You write booking tips for the public page of {name} on Campable, a campsite \
search site. Readers are campers deciding when to look for a site.

Numbers for nights in {months}:
{summary}

Units: a site-night is one site for one night. A cancellation is a booked \
site-night that came back open before the night. By night of week, \
"Tuesday": 70.7 means 70.7% of booked Tuesday site-nights reopened at least \
once. Percentages are already computed: quote them as given and do not \
compute new ones. Excluded \
site-nights are first-come-first-served, not reservable online, closed or not \
yet released: they are not bookings and say nothing about demand.

Rules:
- Use only these numbers. Every tip states at least one of them. Compare \
only what the numbers compare.
- Don't name the campground; the page is about it.
- Say "{months}" in each tip; never present the numbers as current.
- Say "most" only for a share over 50%; otherwise "the largest share".
- Never say the campground sells out, is full or fully booked, or fills \
instantly. Never call excluded site-nights booked.
- No urgency or pressure: no "book immediately", "act fast", "don't miss", no \
exclamation marks. A number can carry urgency on its own.
- No generic advice (book early, plan ahead, try other campgrounds) and no \
mention of data, monitoring or observation.
- Declarative and calm, like: "In June to August 2026, 40% of cancellations \
came 3 to 7 days before arrival."

Return a JSON array of 0 to 3 tips, each one sentence under 160 characters. \
Return [] if the numbers do not support a useful tip. No preamble."""


def _summary_numbers(value: object) -> set[str]:
    if isinstance(value, dict):
        return set().union(*(_summary_numbers(v) for v in value.values()), set())
    if isinstance(value, bool) or value is None:
        return set()
    if isinstance(value, float):
        return {str(value), str(round(value)), str(value).removesuffix(".0")}
    if isinstance(value, int):
        return {str(value), f"{value:,}"}
    return set(_NUMBER.findall(str(value)))


def _keep(tip: object, summary: dict) -> bool:
    """Drop tips with hype, or with a number the summary doesn't contain."""
    if not isinstance(tip, str) or len(tip) > 200 or _BANNED.search(tip):
        return False
    numbers = set(_NUMBER.findall(tip))
    if not numbers <= _summary_numbers(summary) | _BUCKET_NUMBERS:
        return False
    # The year and the bucket edges alone don't make a tip data-backed.
    return bool(numbers - _BUCKET_NUMBERS - set(_NUMBER.findall(summary["months"])))


async def extract_booking_tips(
    db: WatchDB, campground_id: str, campground_name: str = "",
    today: date | None = None,
) -> list[str]:
    """Up to 3 booking tips from cancellation history, via Haiku.

    Without an API key there are no tips: a canned sentence would state a
    pattern nobody checked.
    """
    summary = get_availability_summary(db, campground_id, today)
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not summary or not api_key:
        return []

    from pnw_campsites.posthog_client import HAIKU_MODEL, get_anthropic_client

    client = get_anthropic_client(api_key)
    prompt = _PROMPT.format(
        name=campground_name or campground_id,
        months=summary["months"],
        summary=json.dumps(summary, indent=1),
    )
    try:
        response = await asyncio.wait_for(
            client.messages.create(
                model=HAIKU_MODEL,
                max_tokens=400,
                messages=[{"role": "user", "content": prompt}],
                posthog_privacy_mode=True,
            ),
            timeout=20.0,
        )
        text = response.content[0].text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        tips = json.loads(text)
    except Exception:
        _logger.warning("Booking tips failed for %s", campground_id, exc_info=True)
        return []
    if not isinstance(tips, list):
        return []
    return [t for t in tips if _keep(t, summary)][:3]


async def refresh_all_tips(
    db: WatchDB, registry, today: date | None = None,
) -> int:
    """Batch job: rewrite booking tips for every campground with history.

    A campground whose history is too thin or stale has its tips cleared, so a
    page never shows tips about a season we stopped checking. A failed Haiku
    call keeps the previous tips. Returns the count of campgrounds with tips.
    """
    rows = db._conn.execute(
        "SELECT DISTINCT campground_id, source FROM availability_daily"
    ).fetchall()

    updated = 0
    for row in rows:
        cg = registry.get_by_facility_id(
            row["campground_id"], BookingSystem(row["source"]),
        )
        if not cg:
            continue
        if not get_availability_summary(db, row["campground_id"], today):
            if cg.booking_tips:
                registry.update_booking_tips(cg.id, "")
            continue
        tips = await extract_booking_tips(
            db, row["campground_id"], cg.name, today,
        )
        if tips:
            registry.update_booking_tips(cg.id, json.dumps(tips))
            updated += 1

    _logger.info("Refreshed booking tips for %d campgrounds", updated)
    return updated
