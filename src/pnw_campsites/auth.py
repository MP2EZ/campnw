"""Supabase JWT validation via JWKS (asymmetric ES256)."""

from __future__ import annotations

import logging
import os

import jwt
from jwt import PyJWKClient
from jwt.exceptions import PyJWKClientConnectionError, PyJWKClientError

log = logging.getLogger(__name__)

# PyJWKClient's default is 30s. On a `kid` miss it performs a *synchronous*
# urllib fetch from whatever thread calls it, so an un-capped timeout is a
# 30-second event-loop stall in the auth path.
_JWKS_TIMEOUT_SECONDS = 3

# get_signing_key_from_jwt refreshes the whole JWK set whenever it sees an
# unrecognised `kid`, and PyJWT's internal lru_cache does not cache failures —
# so a stream of tokens carrying random `kid` headers triggers a fresh blocking
# fetch every time and can pin the single worker. Remember rejected kids so the
# second garbage token costs nothing.
_MAX_REJECTED_KIDS = 512
_rejected_kids: set[str] = set()

_jwks_client: PyJWKClient | None = None


def jwks_url() -> str:
    """Resolve the Supabase JWKS endpoint for this environment.

    Shared with the dependency health sweep (``pnw_campsites.health``) so the
    probe can never check a different URL than the one that validates real
    tokens.
    """
    url = os.getenv("SUPABASE_URL")
    if not url:
        if os.getenv("FLY_APP_NAME"):
            raise RuntimeError(
                "SUPABASE_URL must be set in production. "
                "Set it to your Supabase project URL (https://<ref>.supabase.co)."
            )
        log.warning("SUPABASE_URL not set — JWT validation will reject all tokens")
        # Fall back to a dummy URL; all validations will fail gracefully
        url = "https://placeholder.supabase.co"
    return f"{url.rstrip('/')}/auth/v1/.well-known/jwks.json"


def _get_jwks_client() -> PyJWKClient:
    """Lazily create a JWKS client for the Supabase project."""
    global _jwks_client
    if _jwks_client is None:
        _jwks_client = PyJWKClient(
            jwks_url(),
            cache_keys=True,
            lifespan=3600,
            timeout=_JWKS_TIMEOUT_SECONDS,
        )
    return _jwks_client


def warm_jwks_client() -> None:
    """Fetch the JWK set once at startup so no request pays for the cold fetch.

    Best-effort: a failure here just means the first request does what it did
    before.
    """
    try:
        _get_jwks_client().get_jwk_set()
    except Exception as exc:
        log.warning("JWKS warm-up failed (will retry on first request): %s", exc)


def decode_supabase_jwt(token: str) -> tuple[str, str] | None:
    """Decode a Supabase JWT and return (sub, email), or None."""
    try:
        kid = jwt.get_unverified_header(token).get("kid")
        if kid and kid in _rejected_kids:
            return None

        client = _get_jwks_client()
        try:
            signing_key = client.get_signing_key_from_jwt(token)
        except PyJWKClientConnectionError:
            # The JWK set could not be fetched at all, so we learned nothing
            # about this kid. Caching it here would turn a transient Supabase
            # blip into a permanent auth outage for every user holding a key
            # minted after the last successful fetch. Note this must be caught
            # before PyJWKClientError — it is a subclass.
            raise
        except PyJWKClientError:
            # The set was fetched and genuinely does not contain this kid.
            # Remember it so a stream of garbage tokens doesn't trigger a
            # blocking refetch each time.
            if kid:
                if len(_rejected_kids) >= _MAX_REJECTED_KIDS:
                    _rejected_kids.clear()
                _rejected_kids.add(kid)
            raise
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["ES256", "HS256"],
            audience="authenticated",
            leeway=30,
        )
        if payload.get("role") != "authenticated":
            return None
        sub = payload.get("sub")
        if not isinstance(sub, str):
            return None
        return sub, payload.get("email", "")
    except (jwt.InvalidTokenError, jwt.ExpiredSignatureError, ValueError, Exception) as exc:
        log.debug("JWT validation failed: %s", exc)
        return None
