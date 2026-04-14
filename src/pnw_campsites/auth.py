"""Supabase JWT validation via JWKS (asymmetric ES256)."""

from __future__ import annotations

import logging
import os

import jwt
from jwt import PyJWKClient

log = logging.getLogger(__name__)

_jwks_client: PyJWKClient | None = None


def _get_jwks_client() -> PyJWKClient:
    """Lazily create a JWKS client for the Supabase project."""
    global _jwks_client
    if _jwks_client is None:
        url = os.getenv("SUPABASE_URL")
        if not url:
            if os.getenv("FLY_APP_NAME"):
                raise RuntimeError(
                    "SUPABASE_URL must be set in production. "
                    "Set it to your Supabase project URL (https://<ref>.supabase.co)."
                )
            log.warning("SUPABASE_URL not set — JWT validation will reject all tokens")
            # Return a client with a dummy URL; all validations will fail gracefully
            url = "https://placeholder.supabase.co"
        jwks_url = f"{url}/auth/v1/.well-known/jwks.json"
        _jwks_client = PyJWKClient(jwks_url, cache_keys=True, lifespan=3600)
    return _jwks_client


def decode_supabase_jwt(token: str) -> tuple[str, str] | None:
    """Decode a Supabase JWT and return (sub, email), or None."""
    try:
        client = _get_jwks_client()
        signing_key = client.get_signing_key_from_jwt(token)
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
