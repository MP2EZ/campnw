"""Authentication routes — signup, login, logout, profile, export."""

from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from starlette.responses import Response

from pnw_campsites.auth import (
    TOKEN_COOKIE,
    TOKEN_MAX_AGE,
    create_jwt,
    hash_password,
    verify_password,
)
from pnw_campsites.monitor.db import User
from pnw_campsites.routes.deps import (
    SESSION_COOKIE,
    get_client_ip,
    get_current_user,
    get_watch_db,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])

# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class SignupRequest(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(default="", max_length=100)

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError("Invalid email")
        return v.strip().lower()


class LoginRequest(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=128)


class UpdateProfileRequest(BaseModel):
    display_name: str | None = Field(default=None, max_length=100)
    home_base: str | None = Field(default=None, max_length=200)
    default_state: str | None = Field(default=None, max_length=2)
    default_nights: int | None = Field(default=None, ge=1, le=14)
    default_from: str | None = Field(default=None, max_length=200)
    recommendations_enabled: bool | None = None
    preferred_tags: list[str] | None = None
    onboarding_complete: bool | None = None


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------

# In-memory auth rate limiter: ip -> (window_start, count)
_auth_rate_limit: dict[str, tuple[float, int]] = {}
_AUTH_WINDOW_SECONDS = 900  # 15 minutes
_AUTH_MAX_ATTEMPTS = 10
_auth_last_cleanup: float = 0.0


def _check_auth_rate_limit(request: Request) -> None:
    """Raise 429 if auth attempts from this IP exceed threshold."""
    global _auth_last_cleanup
    ip = get_client_ip(request)
    now = time.monotonic()

    # Evict expired entries every 60s to prevent unbounded growth
    if now - _auth_last_cleanup > 60:
        stale = [k for k, (ws, _) in _auth_rate_limit.items() if now - ws > _AUTH_WINDOW_SECONDS]
        for k in stale:
            del _auth_rate_limit[k]
        _auth_last_cleanup = now

    existing = _auth_rate_limit.get(ip)
    if existing is None or (now - existing[0]) > _AUTH_WINDOW_SECONDS:
        _auth_rate_limit[ip] = (now, 1)
        return
    window_start, count = existing
    if count >= _AUTH_MAX_ATTEMPTS:
        raise HTTPException(status_code=429, detail="Too many attempts, try again later")
    _auth_rate_limit[ip] = (window_start, count + 1)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _set_auth_cookie(response: Response, user_id: int) -> None:
    import os

    token = create_jwt(user_id)
    is_prod = bool(os.getenv("FLY_APP_NAME"))
    response.set_cookie(
        TOKEN_COOKIE, token,
        max_age=TOKEN_MAX_AGE,
        httponly=True,
        secure=is_prod,
        samesite="lax",
    )


def _user_to_dict(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "home_base": user.home_base,
        "default_state": user.default_state,
        "default_nights": user.default_nights,
        "default_from": user.default_from,
        "recommendations_enabled": user.recommendations_enabled,
        "preferred_tags": user.preferred_tags or [],
        "onboarding_complete": user.onboarding_complete,
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/signup")
async def signup(body: SignupRequest, request: Request, response: Response):
    db = get_watch_db()
    _check_auth_rate_limit(request)
    existing = db.get_user_by_email(body.email)
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    user = db.create_user(User(
        email=body.email,
        password_hash=hash_password(body.password),
        display_name=body.display_name,
    ))

    # Migrate anonymous watches to this new account
    session_token = request.cookies.get(SESSION_COOKIE)
    if session_token:
        db.migrate_watches_to_user(session_token, user.id)

    _set_auth_cookie(response, user.id)
    return {"user": _user_to_dict(user)}


@router.post("/login")
async def login(body: LoginRequest, request: Request, response: Response):
    db = get_watch_db()
    _check_auth_rate_limit(request)
    from datetime import datetime

    user = db.get_user_by_email(body.email)
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    db.update_user(user.id, last_login_at=datetime.now().isoformat())

    # Migrate any anonymous watches from current session
    session_token = request.cookies.get(SESSION_COOKIE)
    if session_token:
        db.migrate_watches_to_user(session_token, user.id)

    _set_auth_cookie(response, user.id)
    return {"user": _user_to_dict(user)}


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie(TOKEN_COOKIE)
    return {"ok": True}


@router.get("/me")
async def get_me(request: Request):
    db = get_watch_db()
    user_id = get_current_user(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user = db.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return {"user": _user_to_dict(user)}


@router.patch("/me")
async def update_me(body: UpdateProfileRequest, request: Request):
    db = get_watch_db()
    user_id = get_current_user(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    user = db.update_user(user_id, **updates)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {"user": _user_to_dict(user)}


@router.delete("/me")
async def delete_me(request: Request, response: Response):
    db = get_watch_db()
    user_id = get_current_user(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    db.delete_user(user_id)
    response.delete_cookie(TOKEN_COOKIE)
    return {"ok": True}


@router.get("/export")
async def export_data(request: Request):
    db = get_watch_db()
    user_id = get_current_user(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    data = db.get_user_export(user_id)
    return data
