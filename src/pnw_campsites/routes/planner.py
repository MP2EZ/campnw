"""Trip planner chat routes."""

from __future__ import annotations

import contextlib
import json
import os
import re
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from starlette.responses import Response

from pnw_campsites import billing
from pnw_campsites.routes.deps import (
    check_ip_quota,
    get_client_ip,
    get_current_user,
    get_current_user_obj,
    get_engine,
    get_registry,
    get_session_token,
    get_watch_db,
)

router = APIRouter(prefix="/api/plan", tags=["planner"])

# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------

# Simple in-memory rate limiter: IP -> (date, count)
_plan_rate_limit: dict[str, tuple[str, int]] = {}
_PLAN_DAILY_LIMIT = 5

# Anonymous conversation starts per client IP per month. Dropping the
# session cookie mints a fresh token with a zero count, so the per-token cap
# alone doesn't hold. Looser than the per-token cap to allow a few people
# behind one shared address.
_anon_plan_sessions: dict[str, tuple[str, int]] = {}
_ANON_IP_MONTHLY_SESSIONS = 10

# Total characters of history sent to Claude per request. Older turns past
# it are dropped: the planner re-sends the whole context on every tool
# iteration, so a long forged history multiplies the cost of one request.
_HISTORY_CHAR_BUDGET = 40_000


def _check_plan_rate_limit(ip: str) -> bool:
    """Return True if request is allowed, False if daily limit exceeded."""
    return check_ip_quota(_plan_rate_limit, ip, _PLAN_DAILY_LIMIT)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class PlanMessage(BaseModel):
    role: str = Field(..., pattern=r"^(user|assistant)$")
    content: str = Field(..., max_length=10_000)


class PlanChatRequest(BaseModel):
    messages: list[PlanMessage] = Field(..., min_length=1, max_length=50)
    # Issued by the server on a conversation's first turn (X-Plan-Conversation).
    conversation_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{32}$")


def _trim_history(messages: list[PlanMessage], budget: int) -> list[PlanMessage]:
    """The most recent turns that fit in `budget` chars, starting with a user turn.

    The last message is always kept, cut to the budget if it alone exceeds it.
    """
    kept: list[PlanMessage] = []
    used = 0
    for msg in reversed(messages):
        if used + len(msg.content) > budget:
            break
        kept.append(msg)
        used += len(msg.content)
    kept.reverse()
    while kept and kept[0].role != "user":
        kept.pop(0)
    if not kept:
        last = messages[-1]
        return [PlanMessage(role=last.role, content=last.content[:budget])]
    return kept


# ---------------------------------------------------------------------------
# Tier-based session gating
# ---------------------------------------------------------------------------


def _check_planner_session_limit(
    body: PlanChatRequest, request: Request, response: Response,
) -> str:
    """Enforce the per-month planner cap on conversation starts; return the
    conversation id.

    A request continues a conversation only when it presents an id this
    user or session was issued. The client supplies the whole history, so
    its shape proves nothing. Anything else is a new conversation and
    counts. Free: 3/month. Pro: 20/month. Anonymous sessions are counted by
    session_token and, since that cookie can be dropped, by client IP.
    Raises HTTPException 402 with the same machine-readable shape as the
    watch cap.
    """
    db = get_watch_db()
    user = get_current_user_obj(request)
    user_id = user.id if user else None
    token = get_session_token(request, response) if user is None else ""

    if body.conversation_id and db.planner_conversation_exists(
        body.conversation_id, user_id=user_id, session_token=token,
    ):
        return body.conversation_id

    limit = billing.planner_session_limit(user)
    current = db.count_planner_sessions_this_month(
        user_id=user_id, session_token=token,
    )
    over = current >= limit or (
        user is None
        and not check_ip_quota(
            _anon_plan_sessions, get_client_ip(request),
            _ANON_IP_MONTHLY_SESSIONS, period=datetime.now().strftime("%Y-%m"),
        )
    )
    if over:
        raise HTTPException(
            status_code=402,
            detail={
                "error": "planner_session_limit_reached",
                "limit": limit,
                "current": max(current, limit),
                "upgrade_url": "/pricing",
            },
        )
    return db.log_planner_session(user_id=user_id, session_token=token)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/chat/stream")
async def plan_chat_stream(body: PlanChatRequest, request: Request, response: Response):
    from pnw_campsites.planner.agent import chat_stream

    engine = get_engine()
    registry = get_registry()
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise HTTPException(status_code=503, detail="Trip planner not configured")

    if not _check_plan_rate_limit(get_client_ip(request)):
        raise HTTPException(
            status_code=429,
            detail=f"Trip planner limit: {_PLAN_DAILY_LIMIT} conversations per day",
        )

    conversation_id = _check_planner_session_limit(body, request, response)

    user_id = get_current_user(request)
    ph_distinct_id = str(user_id) if user_id else None
    msgs = [
        m.model_dump()
        for m in _trim_history(body.messages, _HISTORY_CHAR_BUDGET)
    ]

    async def event_generator():
        async for event_json in chat_stream(
            msgs, engine, registry, api_key,
            posthog_distinct_id=ph_distinct_id,
        ):
            yield f"data: {event_json}\n\n"
        yield "data: [DONE]\n\n"

    stream = StreamingResponse(event_generator(), media_type="text/event-stream")
    # The cap's session cookie was set on the injected response, which a
    # returned response replaces. Without it every anonymous request gets a
    # fresh token and the monthly cap never applies.
    stream.raw_headers.extend(
        (k, v) for k, v in response.raw_headers if k == b"set-cookie"
    )
    stream.headers["X-Plan-Conversation"] = conversation_id
    return stream


# ---------------------------------------------------------------------------
# Save as Trip
# ---------------------------------------------------------------------------


class SaveTripRequest(BaseModel):
    """Extract campgrounds from a planner conversation and save as a trip."""

    messages: list[PlanMessage] = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=200)


def _extract_campgrounds_from_messages(messages: list[dict]) -> list[dict]:
    """Extract unique facility_ids from tool_call results in conversation."""
    seen = set()
    campgrounds = []
    for msg in messages:
        for tc in msg.get("tool_calls", []):
            result_str = tc.get("result", "")
            if not result_str:
                continue
            try:
                result = json.loads(result_str)
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

    msgs = [m.model_dump() for m in body.messages]
    campgrounds = _extract_campgrounds_from_messages(msgs)

    # Infer date range from messages (simple: find YYYY-MM-DD patterns)
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
