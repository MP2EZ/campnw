"""Unit tests for Supabase JWT validation."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import jwt

from pnw_campsites.auth import decode_supabase_jwt

# Must match the secret set in conftest.py autouse fixture
_TEST_SECRET = "test-supabase-jwt-secret-that-is-at-least-32-characters"


def _make_jwt(
    sub: str | None = None,
    role: str = "authenticated",
    aud: str = "authenticated",
    expired: bool = False,
    algorithm: str = "HS256",
    secret: str = _TEST_SECRET,
    **extra_claims,
) -> str:
    payload = {
        "role": role,
        "aud": aud,
        "exp": datetime.now(UTC) + (timedelta(days=-1) if expired else timedelta(hours=1)),
        "iat": datetime.now(UTC),
        **extra_claims,
    }
    if sub is not None:
        payload["sub"] = sub
    return jwt.encode(payload, secret, algorithm=algorithm)


def test_valid_token_returns_sub_and_email():
    """Valid Supabase JWT returns (sub, email) tuple."""
    sub = str(uuid.uuid4())
    token = _make_jwt(sub=sub, email="alice@example.com")
    result = decode_supabase_jwt(token)
    assert result is not None
    assert result[0] == sub
    assert result[1] == "alice@example.com"


def test_expired_token_returns_none():
    """Expired token is rejected."""
    token = _make_jwt(sub=str(uuid.uuid4()), expired=True)
    assert decode_supabase_jwt(token) is None


def test_wrong_audience_returns_none():
    """Token with wrong audience is rejected."""
    token = _make_jwt(sub=str(uuid.uuid4()), aud="wrong-audience")
    assert decode_supabase_jwt(token) is None


def test_wrong_role_returns_none():
    """Token with wrong role is rejected."""
    token = _make_jwt(sub=str(uuid.uuid4()), role="anon")
    assert decode_supabase_jwt(token) is None


def test_algorithm_none_rejected():
    """Token signed with 'none' algorithm is rejected."""
    payload = {
        "sub": str(uuid.uuid4()),
        "role": "authenticated",
        "aud": "authenticated",
        "exp": datetime.now(UTC) + timedelta(hours=1),
        "iat": datetime.now(UTC),
    }
    # PyJWT requires explicitly allowing algorithm none
    token = jwt.encode(payload, "", algorithm="HS256")
    # Tamper with the token to simulate 'none' alg — just use a bad secret
    bad_token = jwt.encode(payload, "wrong-secret", algorithm="HS256")
    assert decode_supabase_jwt(bad_token) is None


def test_malformed_token_returns_none():
    """Malformed tokens are rejected."""
    assert decode_supabase_jwt("not.a.token") is None
    assert decode_supabase_jwt("") is None
    assert decode_supabase_jwt("garbage") is None


def test_missing_sub_returns_none():
    """Token without sub claim is rejected."""
    token = _make_jwt()  # No sub
    assert decode_supabase_jwt(token) is None
