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
    get_current_user,
    get_engine,
    get_registry,
    get_watch_db,
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


# ---------------------------------------------------------------------------
# Save as Trip
# ---------------------------------------------------------------------------


class SaveTripRequest(BaseModel):
    """Extract campgrounds from a planner conversation and save as a trip."""

    messages: list[PlanMessage] = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=200)


def _extract_campgrounds_from_messages(messages: list[dict]) -> list[dict]:
    """Extract unique facility_ids from tool_call results in conversation."""
    import json as _json

    seen = set()
    campgrounds = []
    for msg in messages:
        for tc in msg.get("tool_calls", []):
            result_str = tc.get("result", "")
            if not result_str:
                continue
            try:
                result = _json.loads(result_str)
            except (ValueError, TypeError):
                continue
            # search_campgrounds returns {"campgrounds": [...]}
            for cg in result.get("campgrounds", []):
                fid = cg.get("facility_id", "")
                if fid and fid not in seen:
                    seen.add(fid)
                    campgrounds.append({
                        "facility_id": fid,
                        "name": cg.get("name", ""),
                        "source": cg.get("booking_system", "recgov"),
                    })
            # check_availability / get_campground_detail return single facility
            fid = result.get("facility_id", "")
            if fid and fid not in seen:
                seen.add(fid)
                campgrounds.append({
                    "facility_id": fid,
                    "name": result.get("name", ""),
                    "source": result.get("booking_system", "recgov"),
                })
    return campgrounds


@router.post("/save-trip")
async def save_plan_as_trip(body: SaveTripRequest, request: Request):
    user_id = get_current_user(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    db = get_watch_db()

    # Extract campgrounds from tool results in conversation
    msgs = [m.model_dump() for m in body.messages]
    campgrounds = _extract_campgrounds_from_messages(msgs)

    # Infer date range from messages (simple: find YYYY-MM-DD patterns)
    import re
    all_text = " ".join(m.get("content", "") for m in msgs)
    date_matches = sorted(set(re.findall(r"\d{4}-\d{2}-\d{2}", all_text)))
    start_date = date_matches[0] if date_matches else ""
    end_date = date_matches[-1] if date_matches else ""

    try:
        trip = db.create_trip(
            user_id, body.name,
            start_date=start_date,
            end_date=end_date,
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from None

    import contextlib

    for cg in campgrounds:
        with contextlib.suppress(Exception):
            db.add_campground_to_trip(
                trip.id, cg["facility_id"], cg.get("source", "recgov"),
                name=cg.get("name", ""),
            )

    return {
        "trip_id": trip.id,
        "name": trip.name,
        "campground_count": len(campgrounds),
    }
