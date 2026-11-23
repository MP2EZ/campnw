"""Shared dependency getters for route modules.

All getters use lazy imports to avoid circular imports — the singletons
live in ``pnw_campsites.api`` and are initialized during the FastAPI
lifespan.
"""

from __future__ import annotations

import os
import re
import uuid
from ipaddress import ip_address, ip_network
from sqlite3 import IntegrityError

from fastapi import Request
from starlette.responses import Response

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SESSION_COOKIE = "campnw_session"
_FACILITY_ID_RE = re.compile(r"[-\w]{1,30}")  # use .fullmatch

# https://www.cloudflare.com/ips/ (fetched 2026-11-19)
_CLOUDFLARE_NETWORKS = tuple(ip_network(n) for n in (
    "173.245.48.0/20", "103.21.244.0/22", "103.22.200.0/22", "103.31.4.0/22",
    "141.101.64.0/18", "108.162.192.0/18", "190.93.240.0/20", "188.114.96.0/20",
    "197.234.240.0/22", "198.41.128.0/17", "162.158.0.0/15", "104.16.0.0/13",
    "104.24.0.0/14", "172.64.0.0/13", "131.0.72.0/22",
    "2400:cb00::/32", "2606:4700::/32", "2803:f800::/32", "2405:b500::/32",
    "2405:8100::/32", "2a06:98c0::/29", "2c0f:f248::/32",
))

# ---------------------------------------------------------------------------
# Singleton accessors (lazy import to break circular dependency)
# ---------------------------------------------------------------------------


def get_registry():
    import pnw_campsites.api as _api
    return _api._registry


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
    """Extract user_id from Supabase Bearer token, auto-provisioning if needed."""
    from pnw_campsites.auth import decode_supabase_jwt

    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return None

    token = auth_header[7:]
    result = decode_supabase_jwt(token)
    if not result:
        return None
    supabase_id, email = result

    db = get_watch_db()
    user = db.get_user_by_supabase_id(supabase_id)
    if user:
        return user.id

    # Auto-provision local user on first authenticated request
    from pnw_campsites.monitor.db import User

    try:
        new_user = db.create_user(User(
            email=email,
            password_hash="",
            supabase_id=supabase_id,
        ))
    except IntegrityError:
        # Race condition: another request already created this user
        user = db.get_user_by_supabase_id(supabase_id)
        return user.id if user else None

    # Migrate anonymous watches if session cookie is present
    session_token = request.cookies.get(SESSION_COOKIE)
    if session_token:
        db.migrate_watches_to_user(session_token, new_user.id)

    return new_user.id


def get_current_user_obj(request: Request):
    """Return the full User object for the current request, or None.

    Wraps get_current_user (which returns just the id) for callers that
    need subscription_status, stripe_customer_id, or email — typically
    billing routes and entitlement checks. Same auto-provisioning
    semantics as get_current_user.
    """
    user_id = get_current_user(request)
    if user_id is None:
        return None
    return get_watch_db().get_user_by_id(user_id)


def get_session_token(request: Request, response: Response) -> str:
    """Get or create a session token cookie for anonymous watch ownership."""
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
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


def _from_cloudflare(ip: str) -> bool:
    try:
        addr = ip_address(ip)
    except ValueError:
        return False
    return any(addr in net for net in _CLOUDFLARE_NETWORKS)


def get_client_ip(request: Request) -> str:
    """Real client IP for rate limiting.

    Fly-Client-IP is the peer that connected to Fly, which for campable.co is
    a Cloudflare edge shared by many users. CF-Connecting-IP names the real
    client, but anyone can send it straight to campnw.fly.dev, so it counts
    only when the peer is in a Cloudflare range. X-Forwarded-For is never
    used: its first entry is whatever the client sent.
    """
    fly_ip = request.headers.get("Fly-Client-IP", "").strip()
    if not fly_ip:
        return request.client.host if request.client else "unknown"
    cf_ip = request.headers.get("CF-Connecting-IP", "").strip()
    if cf_ip and _from_cloudflare(fly_ip):
        return cf_ip
    return fly_ip
