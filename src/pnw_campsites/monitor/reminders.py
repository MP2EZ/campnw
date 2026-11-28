"""Release reminders: a push on the morning a stay opens for booking.

A reminder is a watch with watch_type "release" and `releases_on`, the day its
first night opens. The poller skips it. At 6:55 am Pacific that day the
scheduler pushes once, then turns it into an ordinary cancellation watch for
the same stay, filters and all.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import date, datetime, time
from typing import TYPE_CHECKING, Literal

from pnw_campsites.monitor.pacific import PACIFIC, pacific_now
from pnw_campsites.posthog_client import capture_event
from pnw_campsites.registry.models import BookingSystem
from pnw_campsites.urls import availability_url

if TYPE_CHECKING:
    from pnw_campsites.monitor.db import Watch, WatchDB
    from pnw_campsites.monitor.notify import Sender


# Five minutes before Recreation.gov's 7:00 am PT release, so the camper is at
# the booking page when it opens.
REMIND_AT = time(6, 55)

Action = Literal["wait", "push", "convert"]


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


def _day(d: date) -> str:
    return f"{d:%a %b} {d.day}"


def reminder_push(watch: Watch) -> dict:
    """The push for a reminder's release morning: {title, body, url}."""
    first = date.fromisoformat(watch.start_date)
    last = date.fromisoformat(watch.end_date)
    # Recreation.gov releases at 7:00 am PT; WA's time of day is unverified.
    when = "at 7:00 am" if watch.booking_system == BookingSystem.RECGOV else "today"
    return {
        "title": f"{watch.name} opens for booking {when}",
        # Nights, first to last, as the results' chips and the sheet label them.
        "body": (
            f"{_day(first)} – {_day(last)}. "
            "After that we'll watch it for cancellations."
        ),
        "url": availability_url(watch.facility_id, watch.booking_system, first, last),
    }


Send = Callable[[dict, dict], Awaitable[None]]


async def run_release_reminders(
    watch_db: WatchDB,
    now: datetime | None = None,
    send: Send | None = None,
    apns_sender: Sender | None = None,
) -> int:
    """Push due reminders and convert them to cancellation watches.

    Runs at 6:55 am PT and at startup. Each due reminder is converted first,
    and pushed only if this run converted it, so it pushes at most once. A
    failed push still leaves a working cancellation watch. A reminder whose
    date can't be read converts silently. Returns how many converted.

    Pushes go to every browser and phone the user registered. Without an
    apns_sender, one is opened for this run when APNs is configured.
    """
    from pnw_campsites.monitor.notify import open_apns_sender

    if send is None:
        from pnw_campsites.monitor.notify import send_web_push as send
    now = now or pacific_now()
    if apns_sender is None:
        async with open_apns_sender() as opened:
            return await _run(watch_db, now, send, opened)
    return await _run(watch_db, now, send, apns_sender)


async def _run(
    watch_db: WatchDB, now: datetime, send: Send, apns_sender: Sender | None,
) -> int:
    converted = 0
    for watch in watch_db.list_release_watches():
        try:
            action = reminder_action(date.fromisoformat(watch.releases_on or ""), now)
        except ValueError:
            action = "convert"
        if action == "wait" or not watch_db.convert_release_watch(watch.id):
            continue
        converted += 1
        if action == "push" and watch.user_id:
            await _push(watch_db, watch, send, apns_sender)
    return converted


def reminder_native(watch: Watch, web: dict) -> dict:
    """APNs payload for a release reminder: the web copy, time-sensitive."""
    return {
        "aps": {
            "alert": {"title": web["title"], "body": web["body"]},
            "sound": "default",
            "interruption-level": "time-sensitive",
            "thread-id": f"watch-{watch.id}",
        },
        "watch_id": watch.id,
        "booking_url": web["url"],
        "path": f"/?alert={watch.id}",
    }


async def _push(
    watch_db: WatchDB, watch: Watch, send: Send, apns_sender: Sender | None,
) -> None:
    from pnw_campsites.monitor.notify import push_to_user

    web = reminder_push(watch)
    sent = await push_to_user(
        watch_db, watch.user_id, web, reminder_native(watch, web),
        sender=apns_sender, collapse_id=f"release-{watch.id}", send_web=send,
    )
    for channel, status in sent:
        watch_db.log_notification(watch.id, channel, status)
        # Same events as the poller's alerts (api._capture_notification).
        capture_event(
            distinct_id=str(watch.user_id),
            event=f"notification_{status}",
            properties={
                "watch_id": watch.id,
                "facility_id": watch.facility_id,
                "channel": channel,
                "source": watch.booking_system,
                "kind": "release_reminder",
            },
        )
