"""Trip planner chat routes."""

from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from starlette.responses import Response

from pnw_campsites.routes.deps import (
    SESSION_COOKIE,
    get_client_ip,
    get_engine,
    get_registry,
)

router = APIRouter(prefix="/api/plan", tags=["planner"])

# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------

# Simple in-memory rate limiter: session -> (date, count)
_plan_rate_limit: dict[str, tuple[str, int]] = {}
_PLAN_DAILY_LIMIT = 5


def _check_plan_rate_limit(session_key: str) -> bool:
    """Return True if request is allowed, False if daily limit exceeded."""
    from datetime import date

    today = date.today().isoformat()
    existing = _plan_rate_limit.get(session_key)
    if existing is None or existing[0] != today:
        _plan_rate_limit[session_key] = (today, 1)
        return True
    day, count = existing
    if count >= _PLAN_DAILY_LIMIT:
        return False
    _plan_rate_limit[session_key] = (day, count + 1)
    return True


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class PlanMessage(BaseModel):
    role: str = Field(..., pattern=r"^(user|assistant)$")
    content: str = Field(..., max_length=10_000)


class PlanChatRequest(BaseModel):
    messages: list[PlanMessage] = Field(..., min_length=1, max_length=50)


class PlanChatResponse(BaseModel):
    role: str
    content: str
    tool_calls: list[dict] = []


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/chat", response_model=PlanChatResponse)
async def plan_chat(body: PlanChatRequest, request: Request, response: Response):
    from pnw_campsites.planner.agent import chat

    engine = get_engine()
    registry = get_registry()
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise HTTPException(status_code=503, detail="Trip planner not configured")

    # Rate limit by session token or IP
    session_key = request.cookies.get(SESSION_COOKIE) or get_client_ip(request)
    if not _check_plan_rate_limit(session_key):
        raise HTTPException(
            status_code=429,
            detail=f"Trip planner limit: {_PLAN_DAILY_LIMIT} conversations per day",
        )

    msgs = [m.model_dump() for m in body.messages]
    result = await chat(msgs, engine, registry, api_key)
    return PlanChatResponse(**result)


@router.post("/chat/stream")
async def plan_chat_stream(body: PlanChatRequest, request: Request):
    from pnw_campsites.planner.agent import chat_stream

    engine = get_engine()
    registry = get_registry()
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise HTTPException(status_code=503, detail="Trip planner not configured")

    session_key = request.cookies.get(SESSION_COOKIE) or get_client_ip(request)
    if not _check_plan_rate_limit(session_key):
        raise HTTPException(
            status_code=429,
            detail=f"Trip planner limit: {_PLAN_DAILY_LIMIT} conversations per day",
        )

    msgs = [m.model_dump() for m in body.messages]

    async def event_generator():
        async for event_json in chat_stream(msgs, engine, registry, api_key):
            yield f"data: {event_json}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
