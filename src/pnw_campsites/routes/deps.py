"""Shared dependency getters for route modules.

All getters use lazy imports to avoid circular imports — the singletons
live in ``pnw_campsites.api`` and are initialized during the FastAPI
lifespan.
"""

from __future__ import annotations

import re

from fastapi import Request
from starlette.responses import Response

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SESSION_COOKIE = "campnw_session"
_FACILITY_ID_RE = re.compile(r"^[-\w]{1,30}$")

# ---------------------------------------------------------------------------
# Singleton accessors (lazy import to break circular dependency)
# ---------------------------------------------------------------------------


def get_registry():
    import pnw_campsites.api as _api
    return _api._registry


def get_recgov():
    import pnw_campsites.api as _api
    return _api._recgov


def get_goingtocamp():
    import pnw_campsites.api as _api
    return _api._goingtocamp


def get_reserveamerica():
    import pnw_campsites.api as _api
    return _api._reserveamerica


def get_engine():
    import pnw_campsites.api as _api
    return _api._engine


def get_watch_db():
    import pnw_campsites.api as _api
    return _api._watch_db


def get_poll_state():
    import pnw_campsites.api as _api
    return _api._poll_state


def get_search_timings():
    import pnw_campsites.api as _api
    return _api._search_timings


# ---------------------------------------------------------------------------
# Auth / session helpers
# ---------------------------------------------------------------------------


def get_current_user(request: Request) -> int | None:
    """Extract user_id from JWT cookie, or None if anonymous."""
    from pnw_campsites.auth import TOKEN_COOKIE, decode_jwt

    token = request.cookies.get(TOKEN_COOKIE)
    if not token:
        return None
    return decode_jwt(token)


def get_session_token(request: Request, response: Response) -> str:
    """Get or create a session token cookie for anonymous watch ownership."""
    import uuid

    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        import os

        token = str(uuid.uuid4())
        is_prod = bool(os.getenv("FLY_APP_NAME"))
        response.set_cookie(
            SESSION_COOKIE, token,
            max_age=90 * 24 * 3600,  # 90 days
            httponly=True,
            secure=is_prod,
            samesite="lax",
        )
    return token


def get_client_ip(request: Request) -> str:
    """Extract real client IP, preferring X-Forwarded-For behind a proxy."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
