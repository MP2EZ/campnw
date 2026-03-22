"""Unit tests for auth module — password hashing and JWT handling."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

import jwt

from pnw_campsites.auth import (
    create_jwt,
    decode_jwt,
    hash_password,
    verify_password,
)


def test_hash_and_verify_correct_password():
    """Password verification succeeds with correct password."""
    password = "SecurePassword123!"
    password_hash = hash_password(password)

    assert verify_password(password, password_hash) is True


def test_verify_wrong_password():
    """Password verification fails with wrong password."""
    password = "SecurePassword123!"
    password_hash = hash_password(password)

    assert verify_password("WrongPassword456!", password_hash) is False


def test_jwt_round_trip():
    """JWT creation and decoding round-trip correctly."""
    user_id = 42
    token = create_jwt(user_id)

    decoded_user_id = decode_jwt(token)
    assert decoded_user_id == user_id


def test_decode_jwt_invalid_token():
    """decode_jwt returns None for invalid token."""
    assert decode_jwt("not.a.token") is None
    assert decode_jwt("") is None
    assert decode_jwt("garbage") is None


def test_decode_jwt_expired_token():
    """decode_jwt returns None for expired token."""
    # Create a token that expires immediately
    user_id = 42
    secret = os.getenv("JWT_SECRET") or "test-secret"

    expired_payload = {
        "sub": str(user_id),
        "exp": datetime.now(UTC) - timedelta(seconds=1),
        "iat": datetime.now(UTC),
    }
    expired_token = jwt.encode(expired_payload, secret, algorithm="HS256")

    assert decode_jwt(expired_token) is None


def test_decode_jwt_malformed_sub():
    """decode_jwt returns None if 'sub' is not a valid int."""
    secret = os.getenv("JWT_SECRET") or "test-secret"

    payload = {
        "sub": "not-an-int",
        "exp": datetime.now(UTC) + timedelta(days=30),
        "iat": datetime.now(UTC),
    }
    token = jwt.encode(payload, secret, algorithm="HS256")

    assert decode_jwt(token) is None


def test_decode_jwt_no_sub():
    """decode_jwt returns None if 'sub' is missing."""
    secret = os.getenv("JWT_SECRET") or "test-secret"

    payload = {
        "exp": datetime.now(UTC) + timedelta(days=30),
        "iat": datetime.now(UTC),
    }
    token = jwt.encode(payload, secret, algorithm="HS256")

    assert decode_jwt(token) is None


def test_hash_password_unique():
    """Hashing the same password twice produces different hashes."""
    password = "SamePassword123!"
    hash1 = hash_password(password)
    hash2 = hash_password(password)

    # Hashes should be different (bcrypt includes salt)
    assert hash1 != hash2
    # But both should verify
    assert verify_password(password, hash1) is True
    assert verify_password(password, hash2) is True
