"""Notification dispatch for availability changes."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import date
from typing import TYPE_CHECKING, Protocol
from urllib.parse import urlsplit

import httpx
from pywebpush import webpush

from pnw_campsites.monitor.watcher import AvailabilityChange, PollResult
from pnw_campsites.urls import availability_url

if TYPE_CHECKING:
    from pnw_campsites.monitor.db import WatchDB

_logger = logging.getLogger(__name__)

# Browser push services. The server POSTs to every stored endpoint, so any
# other host would turn a subscription into a server-side request to it.
_PUSH_HOSTS = frozenset({
    "fcm.googleapis.com",                 # Chrome, Edge, Android
    "updates.push.services.mozilla.com",  # Firefox
    "web.push.apple.com",                 # Safari
})
_PUSH_HOST_SUFFIXES = (".notify.windows.com",)  # legacy Edge (WNS)


def is_push_service_endpoint(url: str) -> bool:
    """True for an https URL on a known browser push service."""
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        return False
    host = parts.hostname or ""
    return (
        parts.scheme == "https"
        and port in (None, 443)
        and (host in _PUSH_HOSTS or host.endswith(_PUSH_HOST_SUFFIXES))
    )


def booking_link(result: PollResult) -> str:
    """Availability page on the watch's own booking site."""
    watch = result.watch
    return result.booking_url or availability_url(
        watch.facility_id, watch.booking_system, date.fromisoformat(watch.start_date),
    )


def format_change(change: AvailabilityChange) -> str:
    """Format a single availability change as a human-readable message."""
    dates_str = ", ".join(
        f"{date.fromisoformat(d).strftime('%a %b %d')}" for d in change.new_dates[:5]
    )
    if len(change.new_dates) > 5:
        dates_str += f" +{len(change.new_dates) - 5} more"
    return (
        f"Site {change.site_name} ({change.loop}, max {change.max_people}p): "
        f"{dates_str}"
    )


def format_poll_result(result: PollResult) -> str:
    """Format a poll result with changes into a notification message."""
    watch = result.watch
    url = booking_link(result)

    # Use LLM-enriched context message if available
    context_msg = ""
    if result.changes and result.changes[0].context_message:
        context_msg = result.changes[0].context_message

    if context_msg:
        lines = [
            context_msg,
            "",
            f"{len(result.changes)} site(s) with new dates:",
            "",
        ]
    else:
        sites = "site" if len(result.changes) == 1 else "sites"
        lines = [
            f"{len(result.changes)} {sites} open at {watch.name}",
            "",
        ]

    for change in result.changes[:10]:
        lines.append(f"  {format_change(change)}")
    if len(result.changes) > 10:
        lines.append(f"  ... and {len(result.changes) - 10} more sites")
    lines.append("")
    lines.append(f"Book: {url}")

    return "\n".join(lines)


async def notify_ntfy(
    topic: str,
    result: PollResult,
    server: str = "https://ntfy.sh",
) -> None:
    """Send a notification via ntfy."""
    message = format_poll_result(result)
    url = booking_link(result)

    async with httpx.AsyncClient() as client:
        await client.post(
            f"{server}/{topic}",
            content=message.encode(),
            headers={
                "Title": f"Campsite Alert: {result.watch.name}",
                "Tags": "tent,camping",
                "Click": url,
                "Priority": "high",
            },
        )


async def notify_pushover(
    user_key: str,
    api_token: str,
    result: PollResult,
) -> None:
    """Send a notification via Pushover."""
    message = format_poll_result(result)
    url = booking_link(result)

    async with httpx.AsyncClient() as client:
        await client.post(
            "https://api.pushover.net/1/messages.json",
            data={
                "token": api_token,
                "user": user_key,
                "title": f"Campsite Alert: {result.watch.name}",
                "message": message,
                "url": url,
                "url_title": "View Availability",
                "priority": 1,
            },
        )


def notify_console(result: PollResult) -> None:
    """Print a notification to the console."""
    print(format_poll_result(result))
    print()


def web_push_payload(result: PollResult) -> dict:
    """Payload for web/public/sw.js: {title, body, url}."""
    return {
        "title": f"Campsite Alert: {result.watch.name}",
        "body": f"{len(result.changes)} new site(s) available",
        "url": "/",
    }


async def notify_web_push(
    subscription: dict,  # {endpoint, keys: {p256dh, auth}}
    result: PollResult,
) -> None:
    """Send a web push notification."""
    await send_web_push(subscription, web_push_payload(result))


async def send_web_push(
    subscription: dict,  # {endpoint, keys: {p256dh, auth}}
    payload: dict,  # {title, body, url}, read by web/public/sw.js
) -> None:
    """Send one web push. A no-op when VAPID isn't configured."""
    vapid_private_key = os.getenv("VAPID_PRIVATE_KEY", "")
    vapid_claims_email = os.getenv("VAPID_CLAIMS_EMAIL", "")
    if not vapid_private_key:
        return
    if not is_push_service_endpoint(subscription.get("endpoint", "")):
        return

    # pywebpush is synchronous (requests). In a thread, with a timeout, so a
    # stalled push service can't freeze the event loop and the poller.
    await asyncio.to_thread(
        webpush,
        subscription_info=subscription,
        data=json.dumps(payload),
        vapid_private_key=vapid_private_key,
        vapid_claims={"sub": f"mailto:{vapid_claims_email}"},
        timeout=10,
    )


# ---------------------------------------------------------------------------
# Native (APNs) alerts and fan-out to every device a user registered
# ---------------------------------------------------------------------------

PROVIDER_NAMES = {
    "recgov": "Recreation.gov",
    "wa_state": "WA State Parks",
    "or_state": "Oregon State Parks",
    "id_state": "Idaho State Parks",
}
_TITLE_NAME_MAX = 30


def _day(d: str) -> str:
    return date.fromisoformat(d).strftime("%a %b %d").replace(" 0", " ")


def _nights(dates: list[str]) -> str:
    days = sorted(set(dates))
    if not days:
        return ""
    if len(days) == 1:
        return _day(days[0])
    return f"{_day(days[0])} – {_day(days[-1])}"


def short_name(name: str) -> str:
    name = " ".join(name.split())
    if len(name) <= _TITLE_NAME_MAX:
        return name
    return name[: _TITLE_NAME_MAX - 1].rstrip() + "…"


def native_alert(result: PollResult, campground_name: str) -> dict:
    """APNs payload for a watch that found sites. Built from the registry's
    campground name, not the watch name a user can edit, and nothing about
    the user. Lock-screen text: dates first, then sites, then where to book.
    """
    watch = result.watch
    n = len(result.changes)
    name = short_name(campground_name)
    title = f"{name}: site open" if n == 1 else f"{name}: {n} sites open"
    first = result.changes[0]
    site = f"Site {first.site_name}" + (f" ({first.loop})" if first.loop else "")
    if n > 1:
        site += f" +{n - 1} more"
    dates = _nights([d for c in result.changes for d in c.new_dates])
    provider = PROVIDER_NAMES.get(watch.booking_system, "the booking site")
    return {
        "aps": {
            "alert": {
                "title": title,
                "body": f"{dates} · {site}. Book on {provider}.",
            },
            "sound": "default",
            # Cancellations are exactly what Focus modes should let through.
            "interruption-level": "time-sensitive",
            "thread-id": f"watch-{watch.id}",
        },
        "watch_id": watch.id,
        "booking_url": booking_link(result),
        "path": f"/?alert={watch.id}",
    }


class Sender(Protocol):
    async def send(
        self, token: str, payload: dict, *,
        collapse_id: str | None = None, expires_in: int = 1800,
    ) -> str: ...


@asynccontextmanager
async def open_apns_sender() -> AsyncIterator[Sender | None]:
    """An APNs sender for one job, or None when APNs isn't configured here."""
    from pnw_campsites.monitor import apns

    try:
        config = apns.ApnsConfig.from_env()
    except ValueError as e:
        _logger.error("APNs disabled: %s", e)
        config = None
    if config is None:
        yield None
        return
    async with apns.new_client() as client:
        yield apns.ApnsSender(config, client)


async def push_to_user(
    watch_db: WatchDB,
    user_id: int,
    web_payload: dict,
    native_payload: dict,
    *,
    sender: Sender | None,
    collapse_id: str | None = None,
    send_web: Callable[[dict, dict], Awaitable[None]] | None = None,
) -> list[tuple[str, str]]:
    """Send one alert to every browser and phone the user registered.

    Returns (channel, status) per device. Phones whose token APNs says is dead
    are deleted. Failures are logged without the endpoint or token.
    """
    send_web = send_web or send_web_push
    out: list[tuple[str, str]] = []
    for sub in watch_db.get_push_subscriptions_for_user(user_id):
        subscription = {
            "endpoint": sub["endpoint"],
            "keys": {"p256dh": sub["p256dh"], "auth": sub["auth"]},
        }
        try:
            await send_web(subscription, web_payload)
            out.append(("web_push", "sent"))
        except Exception as e:
            _logger.warning("web push failed for user %s: %s", user_id, type(e).__name__)
            out.append(("web_push", "failed"))
    if sender is not None:
        for token in watch_db.get_device_tokens_for_user(user_id):
            status = await sender.send(token, native_payload, collapse_id=collapse_id)
            if status == "dead":
                watch_db.delete_device_token(token)
            out.append(("apns", "sent" if status == "sent" else "failed"))
    return out
