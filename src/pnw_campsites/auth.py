"""Authentication utilities — JWT tokens and password hashing."""

from __future__ import annotations

import os
import secrets
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

# JWT secret: env var > auto-generated (fine for single-instance SQLite app)
_JWT_SECRET: str | None = None

TOKEN_COOKIE = "campnw_token"
TOKEN_MAX_AGE = 30 * 24 * 3600  # 30 days


def _get_secret() -> str:
    global _JWT_SECRET
    if _JWT_SECRET is None:
        env_secret = os.getenv("JWT_SECRET")
        if not env_secret:
            if os.getenv("FLY_APP_NAME"):
                raise RuntimeError(
                    "JWT_SECRET must be set in production. "
                    "Run: fly secrets set JWT_SECRET=\"$(openssl rand -hex 32)\""
                )
            env_secret = secrets.token_hex(32)
        _JWT_SECRET = env_secret
    return _JWT_SECRET


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())


def create_jwt(user_id: int) -> str:
    payload = {
        "sub": str(user_id),
        "exp": datetime.now(UTC) + timedelta(days=30),
        "iat": datetime.now(UTC),
    }
    return jwt.encode(payload, _get_secret(), algorithm="HS256")


def decode_jwt(token: str) -> int | None:
    """Decode a JWT and return the user_id, or None if invalid/expired."""
    try:
        payload = jwt.decode(token, _get_secret(), algorithms=["HS256"])
        sub = payload.get("sub")
        return int(sub) if sub is not None else None
    except (jwt.InvalidTokenError, jwt.ExpiredSignatureError, ValueError):
        return None
