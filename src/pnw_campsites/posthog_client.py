"""Shared PostHog Python client for server-side analytics."""

import logging
import os

import httpx
from posthog import Posthog

logger = logging.getLogger(__name__)

_client: Posthog | None = None


def get_posthog_client() -> Posthog | None:
    """Get or create the PostHog client. Returns None if no token configured."""
    global _client
    if _client is not None:
        return _client
    token = os.getenv("POSTHOG_PROJECT_TOKEN") or os.getenv("VITE_PUBLIC_POSTHOG_PROJECT_TOKEN", "")
    if not token:
        return None
    _client = Posthog(
        token,
        host=os.getenv("POSTHOG_HOST", "https://eu.i.posthog.com"),
        enable_exception_autocapture=True,
    )
    return _client


def capture_event(
    distinct_id: str,
    event: str,
    properties: dict | None = None,
    set_properties: dict | None = None,
) -> None:
    """Emit a server-side product event. Never raises.

    `distinct_id` must be `str(user.id)` — the same value the browser passes to
    posthog.identify() — or the server and client events land on two different
    people for the same human.

    Analytics is never load-bearing: a PostHog outage must not fail the caller
    (in particular it must not 500 a Stripe webhook, which would trigger
    redelivery of an event we already processed).
    """
    client = get_posthog_client()
    if client is None:
        return
    try:
        payload = dict(properties or {})
        if set_properties:
            payload["$set"] = set_properties
        client.capture(distinct_id=distinct_id, event=event, properties=payload)
    except Exception:
        logger.warning("PostHog capture failed for event %s", event, exc_info=True)


async def delete_person(distinct_id: str) -> bool:
    """Delete the PostHog person behind `distinct_id`, with its events and
    recordings. Never raises; returns True when PostHog accepted it.

    Needs a personal API key with the person:write scope and the numeric
    project id. Skipped when either is unset (local dev). PostHog queues the
    deletion and returns 202.
    """
    key = os.getenv("POSTHOG_PERSONAL_API_KEY", "")
    project_id = os.getenv("POSTHOG_PROJECT_ID", "")
    if not key or not project_id:
        logger.warning("PostHog person delete skipped: admin API not configured")
        return False
    url = f"{_api_host()}/api/projects/{project_id}/persons/bulk_delete/"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                url,
                headers={"Authorization": f"Bearer {key}"},
                json={
                    "distinct_ids": [distinct_id],
                    "delete_events": True,
                    "delete_recordings": True,
                },
            )
        resp.raise_for_status()
    except httpx.HTTPError:
        logger.error("PostHog person delete failed for user %s", distinct_id, exc_info=True)
        return False
    return True


def _api_host() -> str:
    """The private API host for this project's region.

    POSTHOG_HOST is the ingestion host (eu.i.posthog.com); the REST API lives
    on eu.posthog.com.
    """
    host = os.getenv("POSTHOG_API_HOST") or os.getenv("POSTHOG_HOST", "https://eu.i.posthog.com")
    return host.rstrip("/").replace(".i.posthog.com", ".posthog.com")


# ---------------------------------------------------------------------------
# Anthropic clients
# ---------------------------------------------------------------------------

HAIKU_MODEL = "claude-haiku-4-5-20251001"
SONNET_MODEL = "claude-sonnet-4-20250514"


def get_anthropic_client(api_key: str):
    """Return an AsyncAnthropic wrapped for PostHog LLM observability.

    Falls back to the plain SDK when the PostHog integration is unavailable —
    `posthog.ai` is an optional extra, and PostHog raises ValueError when it is
    installed but not configured.
    """
    try:
        from posthog.ai.anthropic import AsyncAnthropic

        return AsyncAnthropic(api_key=api_key, posthog_client=get_posthog_client())
    except (ImportError, ValueError):
        import anthropic

        return anthropic.AsyncAnthropic(api_key=api_key)


def get_sync_anthropic_client(api_key: str):
    """Synchronous counterpart to `get_anthropic_client` (batch enrichment)."""
    try:
        from posthog.ai.anthropic import Anthropic

        return Anthropic(api_key=api_key, posthog_client=get_posthog_client())
    except (ImportError, ValueError):
        import anthropic

        return anthropic.Anthropic(api_key=api_key)
