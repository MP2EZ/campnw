"""Shared PostHog Python client for server-side analytics."""

import logging
import os

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


# ---------------------------------------------------------------------------
# Anthropic clients
# ---------------------------------------------------------------------------

# Model ids were bare literals at 16 call sites. Named here so a model bump is
# one edit rather than sixteen, and so a typo fails at import rather than at
# request time.
HAIKU_MODEL = "claude-haiku-4-5-20251001"
SONNET_MODEL = "claude-sonnet-4-20250514"


def get_anthropic_client(api_key: str):
    """Return an AsyncAnthropic wrapped for PostHog LLM observability.

    Falls back to the plain SDK when the PostHog integration is unavailable —
    `posthog.ai` is an optional extra, and PostHog raises ValueError when it is
    installed but not configured.

    This block was copy-pasted at 16 call sites across 12 modules, and the
    except clause had already drifted: most caught (ImportError, ValueError),
    three caught ImportError alone and so raised on an unconfigured PostHog
    instead of degrading to the plain client.
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
