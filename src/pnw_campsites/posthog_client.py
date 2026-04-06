"""Shared PostHog Python client for server-side LLM analytics."""

import os

from posthog import Posthog

_client: Posthog | None = None


def get_posthog_client() -> Posthog | None:
    """Get or create the PostHog client. Returns None if no token configured."""
    global _client
    if _client is not None:
        return _client
    token = os.getenv("POSTHOG_PROJECT_TOKEN", "")
    if not token:
        return None
    _client = Posthog(
        token,
        host=os.getenv("POSTHOG_HOST", "https://eu.i.posthog.com"),
    )
    return _client
