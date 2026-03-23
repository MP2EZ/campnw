"""Notification dispatch for availability changes."""

from __future__ import annotations

import json
import os
from datetime import date

import httpx

from pnw_campsites.monitor.watcher import AvailabilityChange, PollResult
from pnw_campsites.urls import recgov_availability_url


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


def _urgency_prefix(urgency: int) -> str:
    """Return an emoji prefix based on urgency level."""
    if urgency >= 3:
        return "\U0001f525 "  # fire
    if urgency <= 1:
        return ""
    return ""


def format_poll_result(result: PollResult) -> str:
    """Format a poll result with changes into a notification message."""
    watch = result.watch
    url = recgov_availability_url(
        watch.facility_id,
        date.fromisoformat(watch.start_date),
    )

    # Use LLM-enriched context message if available
    context_msg = ""
    urgency = 2
    if result.changes and result.changes[0].context_message:
        context_msg = result.changes[0].context_message
        urgency = result.changes[0].urgency

    if context_msg:
        prefix = _urgency_prefix(urgency)
        lines = [
            f"{prefix}{context_msg}",
            "",
            f"{len(result.changes)} site(s) with new dates:",
            "",
        ]
    else:
        lines = [
            f"New availability at {watch.name}!",
            f"{len(result.changes)} site(s) with new dates:",
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
    url = recgov_availability_url(
        result.watch.facility_id,
        date.fromisoformat(result.watch.start_date),
    )

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
    url = recgov_availability_url(
        result.watch.facility_id,
        date.fromisoformat(result.watch.start_date),
    )

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


async def notify_web_push(
    subscription: dict,  # {endpoint, keys: {p256dh, auth}}
    result: PollResult,
) -> None:
    """Send a web push notification."""
    from pywebpush import WebPushException, webpush

    vapid_private_key = os.getenv("VAPID_PRIVATE_KEY", "")
    vapid_claims_email = os.getenv("VAPID_CLAIMS_EMAIL", "")
    if not vapid_private_key:
        return

    payload = json.dumps({
        "title": f"Campsite Alert: {result.watch.name}",
        "body": f"{len(result.changes)} new site(s) available",
        "url": "/",
    })

    try:
        webpush(
            subscription_info=subscription,
            data=payload,
            vapid_private_key=vapid_private_key,
            vapid_claims={"sub": f"mailto:{vapid_claims_email}"},
        )
    except WebPushException as e:
        if hasattr(e, "response") and e.response and e.response.status_code in (404, 410):
            # Subscription expired — caller should clean up
            raise
        raise
