"""Release reminders (v1.48 D9): a push on the morning a stay opens for booking.

A reminder is a watch with watch_type "release" and `releases_on`, the day its
first night opens. The poller skips it. At 6:55 am Pacific that day the
scheduler pushes once, then turns it into an ordinary cancellation watch for
the same stay, filters and all.
"""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Literal
from zoneinfo import ZoneInfo

PACIFIC = ZoneInfo("America/Los_Angeles")

# Five minutes before Recreation.gov's 7:00 am PT release, so the camper is at
# the booking page when it opens.
REMIND_AT = time(6, 55)

Action = Literal["wait", "push", "convert"]


def pacific_now() -> datetime:
    return datetime.now(PACIFIC)


def reminder_action(releases_on: date, now: datetime) -> Action:
    """What a reminder should do at `now`.

    "push" from 6:55 am Pacific on release day until midnight, so a scheduler
    that missed 6:55 (a deploy, a restart) still sends it that day. Once the
    day has passed the push would be stale, so the reminder only converts.
    """
    local = now.astimezone(PACIFIC)
    today = local.date()
    if today < releases_on or (today == releases_on and local.time() < REMIND_AT):
        return "wait"
    return "push" if today == releases_on else "convert"


def release_problem(
    releases_on: str | None, start_date: str, now: datetime,
) -> str | None:
    """Why a reminder for a stay can't be created, or None if it can.

    A reminder must be able to fire: its release day still ahead of the
    6:55 am push, and no later than the stay's first night.
    """
    if not releases_on:
        return "releases_on_required"
    try:
        released = date.fromisoformat(releases_on)
    except ValueError:
        return "releases_on_invalid"
    if released > date.fromisoformat(start_date):
        return "releases_on_invalid"
    if reminder_action(released, now) != "wait":
        return "already_released"
    return None
