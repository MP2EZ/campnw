"""FastAPI backend exposing the campsite search library as a REST API."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from contextlib import asynccontextmanager
from datetime import date, datetime
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from starlette.responses import Response

from pnw_campsites.auth import (
    TOKEN_COOKIE,
    TOKEN_MAX_AGE,
    create_jwt,
    decode_jwt,
    hash_password,
    verify_password,
)
from pnw_campsites.monitor.db import User, Watch, WatchDB
from pnw_campsites.providers.goingtocamp import GoingToCampClient
from pnw_campsites.providers.recgov import RecGovClient
from pnw_campsites.registry.db import CampgroundRegistry
from pnw_campsites.registry.models import BookingSystem
from pnw_campsites.search.engine import SearchEngine, SearchQuery
from pnw_campsites.urls import (
    recgov_availability_url,
    recgov_campsite_booking_url,
    wa_state_availability_url,
)

# ---------------------------------------------------------------------------
# App state — initialized in lifespan
# ---------------------------------------------------------------------------

_registry: CampgroundRegistry | None = None
_recgov: RecGovClient | None = None
_goingtocamp: GoingToCampClient | None = None
_engine: SearchEngine | None = None
_watch_db: WatchDB | None = None
_poll_state: dict = {
    "last_poll": None,
    "next_poll": None,
    "active_watches": 0,
    "last_changes": 0,
    "last_errors": 0,
}

# ---------------------------------------------------------------------------
# Subscription tiers
# ---------------------------------------------------------------------------

TIER_FREE = {
    "tier": "free",
    "max_watches": 3,
    "poll_interval_minutes": 15,
    "plan_sessions_per_month": 3,
}
TIER_PRO = {
    "tier": "pro",
    "max_watches": float("inf"),
    "poll_interval_minutes": 5,
    "plan_sessions_per_month": 20,
}


def _get_user_tier(user_id: int | None) -> dict:
    """Return tier config for a user. Defaults to free."""
    if not user_id or not _watch_db:
        return TIER_FREE
    user = _watch_db.get_user_by_id(user_id)
    if not user:
        return TIER_FREE
    if user.subscription_status == "pro":
        return TIER_PRO
    return TIER_FREE


async def _poll_all_watches() -> None:
    """Background job: poll all watches and dispatch notifications."""
    from pnw_campsites.monitor.notify import notify_ntfy, notify_web_push
    from pnw_campsites.monitor.watcher import poll_all

    if not _watch_db:
        return

    _poll_logger.info("Starting watch poll cycle")
    results = await poll_all(
        _recgov, _goingtocamp, _watch_db, _registry,
    )

    # Enrich notifications with LLM context (fire-and-forget, 3s timeout)
    from pnw_campsites.enrichment.notifications import enrich_notification

    for result in results:
        if result.has_changes:
            all_dates: list[str] = []
            for change in result.changes:
                all_dates.extend(change.new_dates)
            try:
                msg, urgency = await asyncio.wait_for(
                    enrich_notification(
                        result.watch.name,
                        len(result.changes),
                        sorted(set(all_dates)),
                    ),
                    timeout=3.0,
                )
            except (TimeoutError, Exception):
                msg = (
                    f"{result.watch.name}: "
                    f"{len(result.changes)} site(s) available"
                )
                urgency = 2
            for change in result.changes:
                change.context_message = msg
                change.urgency = urgency

    total_changes = 0
    total_errors = 0
    for result in results:
        if result.error:
            total_errors += 1
            continue
        if not result.has_changes:
            continue
        total_changes += len(result.changes)
        channel = result.watch.notification_channel or ""
        topic = result.watch.notify_topic
        # Dispatch notification based on channel
        if channel == "ntfy" and topic:
            try:
                await notify_ntfy(topic, result)
                _watch_db.log_notification(
                    result.watch.id, "ntfy", "sent",
                    len(result.changes),
                )
            except Exception as e:
                _poll_logger.warning(
                    "ntfy failed for watch %s: %s",
                    result.watch.id, e,
                )
                _watch_db.log_notification(
                    result.watch.id, "ntfy", "failed",
                )
        elif channel == "web_push" and result.watch.user_id:
            subs = _watch_db.get_push_subscriptions_for_user(result.watch.user_id)
            for sub in subs:
                try:
                    await notify_web_push(
                        {
                            "endpoint": sub["endpoint"],
                            "keys": {"p256dh": sub["p256dh"], "auth": sub["auth"]},
                        },
                        result,
                    )
                    _watch_db.log_notification(
                        result.watch.id, "web_push", "sent", len(result.changes),
                    )
                except Exception as e:
                    _poll_logger.warning(
                        "web_push failed for watch %s: %s",
                        result.watch.id, e,
                    )
                    _watch_db.log_notification(result.watch.id, "web_push", "failed")
        elif topic:
            # Legacy: if notify_topic is set but no channel,
            # treat as ntfy for backward compatibility
            try:
                await notify_ntfy(topic, result)
                _watch_db.log_notification(
                    result.watch.id, "ntfy", "sent",
                    len(result.changes),
                )
            except Exception:
                pass

    _poll_state["last_poll"] = datetime.now().isoformat()
    _poll_state["last_changes"] = total_changes
    _poll_state["last_errors"] = total_errors
    _poll_state["active_watches"] = len(results)
    _poll_logger.info(
        "Poll cycle complete: %d watches, %d changes, %d errors",
        len(results), total_changes, total_errors,
    )


async def _poll_pro_watches() -> None:
    """Background job: poll only Pro-tier watches at higher frequency."""
    from pnw_campsites.monitor.watcher import poll_all

    if not _watch_db:
        return

    pro_watches = _watch_db.list_pro_watches()
    if not pro_watches:
        return

    _poll_logger.info("Pro poll: %d watches", len(pro_watches))
    await poll_all(_recgov, _goingtocamp, _watch_db, _registry, watches=pro_watches)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _registry, _recgov, _goingtocamp, _engine, _watch_db
    load_dotenv()

    _registry = CampgroundRegistry()
    api_key = os.getenv("RIDB_API_KEY")
    if api_key:
        _recgov = RecGovClient(ridb_api_key=api_key)
        await _recgov.__aenter__()

    _goingtocamp = GoingToCampClient()
    await _goingtocamp.__aenter__()

    _engine = SearchEngine(_registry, _recgov, _goingtocamp)
    _watch_db = WatchDB()

    # Start background watch poller (every 15 minutes)
    scheduler = None
    if os.getenv("DISABLE_SCHEDULER") != "1":
        from apscheduler.schedulers.asyncio import AsyncIOScheduler

        scheduler = AsyncIOScheduler()
        scheduler.add_job(
            _poll_all_watches,
            "interval",
            minutes=15,
            id="watch_poller",
            max_instances=1,
            coalesce=True,
        )
        # Pro-tier watches get an additional 5-min poll cycle
        scheduler.add_job(
            _poll_pro_watches,
            "interval",
            minutes=5,
            id="watch_poller_pro",
            max_instances=1,
            coalesce=True,
        )
        scheduler.start()
        next_run = scheduler.get_job("watch_poller").next_run_time
        _poll_state["next_poll"] = (
            next_run.isoformat() if next_run else None
        )
        _poll_logger.info("Watch poller started (15-min interval)")

    yield

    if scheduler:
        scheduler.shutdown(wait=False)

    if _watch_db:
        _watch_db.close()

    if _recgov:
        await _recgov.__aexit__(None, None, None)
    if _goingtocamp:
        await _goingtocamp.__aexit__(None, None, None)
    if _registry:
        _registry.close()


logging.basicConfig(level=logging.INFO)

app = FastAPI(title="PNW Campsites", lifespan=lifespan)

_cors_origins = os.getenv(
    "ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:3000"
).split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_methods=["GET", "POST", "DELETE", "PATCH"],
    allow_headers=["*"],
    allow_credentials=True,
)

# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class WindowResponse(BaseModel):
    campsite_id: str
    site_name: str
    loop: str
    campsite_type: str
    start_date: str
    end_date: str
    nights: int
    max_people: int
    is_fcfs: bool = False
    booking_url: str | None = None


class CampgroundResultResponse(BaseModel):
    facility_id: str
    name: str
    state: str
    booking_system: str
    latitude: float
    longitude: float
    total_available_sites: int
    fcfs_sites: int
    tags: list[str] = []
    vibe: str = ""
    estimated_drive_minutes: int | None = None
    availability_url: str | None = None
    windows: list[WindowResponse]
    error: str | None = None


class SearchWarningResponse(BaseModel):
    kind: str
    count: int
    source: str
    message: str


WARNING_MESSAGES = {
    "rate_limited": (
        "Some results may be missing — recreation.gov is rate limiting."
        " Try a narrower search."
    ),
    "waf_blocked": "WA State Parks results unavailable — the booking site is blocking requests.",
    "unavailable": "Some campgrounds couldn't be checked due to a service issue.",
}


class DiagnosisResponse(BaseModel):
    registry_matches: int
    distance_filtered: int
    checked_for_availability: int
    binding_constraint: str
    explanation: str


class DateSuggestionResponse(BaseModel):
    start_date: str
    end_date: str
    campgrounds_with_availability: int
    reason: str


class ActionChipResponse(BaseModel):
    action: str
    label: str
    params: dict


class SearchResponse(BaseModel):
    campgrounds_checked: int
    campgrounds_with_availability: int
    results: list[CampgroundResultResponse]
    warnings: list[SearchWarningResponse] = []
    diagnosis: DiagnosisResponse | None = None
    date_suggestions: list[DateSuggestionResponse] = []
    action_chips: list[ActionChipResponse] = []


class CampgroundResponse(BaseModel):
    id: int | None
    facility_id: str
    name: str
    booking_system: str
    state: str
    region: str
    latitude: float
    longitude: float
    tags: list[str]
    vibe: str = ""
    drive_minutes_from_base: int | None
    notes: str
    rating: int | None
    total_sites: int | None
    enabled: bool


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_availability_url(
    facility_id: str,
    booking_system: BookingSystem,
    start_date: date | None,
    end_date: date | None = None,
) -> str:
    if booking_system == BookingSystem.WA_STATE:
        return wa_state_availability_url(facility_id, start_date, end_date)
    return recgov_availability_url(facility_id, start_date)


def _build_booking_url(
    facility_id: str,
    campsite_id: str,
    booking_system: BookingSystem,
    start_date: date,
    end_date: date,
) -> str | None:
    if booking_system == BookingSystem.RECGOV:
        return recgov_campsite_booking_url(
            facility_id, campsite_id, start_date, end_date
        )
    return None


def _format_result(r, booking_system: BookingSystem) -> CampgroundResultResponse:
    cg = r.campground
    start = None
    end = None
    reservable = [w for w in r.available_windows if not w.is_fcfs]
    if reservable:
        start = date.fromisoformat(reservable[0].start_date)
        end = date.fromisoformat(reservable[-1].end_date)

    windows = []
    for w in r.available_windows:
        booking_url = None
        if not w.is_fcfs:
            booking_url = _build_booking_url(
                cg.facility_id,
                w.campsite_id,
                cg.booking_system,
                date.fromisoformat(w.start_date),
                date.fromisoformat(w.end_date),
            )
        windows.append(
            WindowResponse(
                campsite_id=w.campsite_id,
                site_name=w.site_name,
                loop=w.loop,
                campsite_type=w.campsite_type,
                start_date=w.start_date,
                end_date=w.end_date,
                nights=w.nights,
                max_people=w.max_people,
                is_fcfs=w.is_fcfs,
                booking_url=booking_url,
            )
        )

    return CampgroundResultResponse(
        facility_id=cg.facility_id,
        name=cg.name,
        state=cg.state,
        booking_system=cg.booking_system.value,
        latitude=cg.latitude,
        longitude=cg.longitude,
        total_available_sites=r.total_available_sites,
        fcfs_sites=r.fcfs_sites,
        tags=cg.tags,
        vibe=cg.vibe,
        estimated_drive_minutes=r.estimated_drive_minutes,
        availability_url=_build_availability_url(
            cg.facility_id, cg.booking_system, start, end
        ) if start else None,
        windows=windows,
        error=r.error,
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


_track_logger = logging.getLogger("pnw_campsites.track")
_poll_logger = logging.getLogger("pnw_campsites.poller")
_search_logger = logging.getLogger("pnw_campsites.api")


ALLOWED_TRACK_EVENTS = {"card_expand", "book_click", "search"}
ALLOWED_TRACK_FIELDS = {"event", "facility_id", "name", "source", "type", "site"}


@app.post("/api/track")
async def track(request: Request):
    """Lightweight event tracking — logs to stdout, no external service."""
    try:
        raw = await request.body()
        if len(raw) > 4096:
            return {"ok": False}
        body = await request.json()
        if not isinstance(body, dict):
            return {"ok": False}
        event = body.get("event")
        if event not in ALLOWED_TRACK_EVENTS:
            return {"ok": False}
        # Only log allowed fields
        safe = {k: str(v)[:200] for k, v in body.items() if k in ALLOWED_TRACK_FIELDS}
        _track_logger.info("event: %s", safe)
    except Exception:
        pass
    return {"ok": True}


@app.get("/api/search", response_model=SearchResponse)
async def search(
    start_date: date = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: date = Query(..., description="End date (YYYY-MM-DD)"),
    state: str | None = Query(None, description="Filter by state: WA, OR, ID"),
    nights: int = Query(2, description="Minimum consecutive nights"),
    mode: str | None = Query(None, description="Search mode: find or exact"),
    days_of_week: str | None = Query(
        None, description="Comma-separated day numbers (0=Mon..6=Sun)"
    ),
    tags: str | None = Query(None, description="Comma-separated tags"),
    max_drive: int | None = Query(None, description="Max drive minutes"),
    from_location: str | None = Query(
        None, alias="from",
        description="Origin: seattle, bellevue, portland, spokane, or address",
    ),
    name: str | None = Query(None, description="Campground name filter"),
    source: str | None = Query(None, description="recgov or wa_state"),
    no_groups: bool = Query(False, description="Exclude group sites"),
    include_fcfs: bool = Query(False, description="Include FCFS sites"),
    limit: int = Query(20, ge=1, le=50, description="Max campgrounds to check"),
):
    days_set = (
        {int(d) for d in days_of_week.split(",")}
        if days_of_week
        else None
    )
    booking_system = BookingSystem(source) if source else None

    query = SearchQuery(
        state=state,
        start_date=start_date,
        end_date=end_date,
        min_consecutive_nights=nights,
        days_of_week=days_set,
        tags=tags.split(",") if tags else None,
        max_drive_minutes=max_drive,
        from_location=from_location,
        name_like=name,
        include_group_sites=not no_groups,
        include_fcfs=include_fcfs,
        max_campgrounds=limit,
        booking_system=booking_system,
    )

    # Redact custom addresses in logs — only log known base names
    _known_bases = {"seattle", "bellevue", "portland", "spokane", "bellingham", "moscow"}
    logged_from = (
        from_location if from_location in _known_bases
        else "[custom]" if from_location else None
    )
    _search_logger.info(
        "API search: mode=%s state=%s source=%s from=%s max_drive=%s "
        "days=%s tags=%s nights=%s name=%s limit=%s",
        mode, state, source, logged_from, max_drive,
        days_of_week, tags, nights, name, limit,
    )

    results = await _engine.search(query)

    return SearchResponse(
        campgrounds_checked=results.campgrounds_checked,
        campgrounds_with_availability=results.campgrounds_with_availability,
        results=[
            _format_result(r, booking_system or BookingSystem.RECGOV)
            for r in results.results
        ],
        warnings=[
            SearchWarningResponse(
                kind=w.kind,
                count=w.count,
                source=w.source,
                message=WARNING_MESSAGES.get(
                    w.kind,
                    "Some campgrounds couldn't be checked.",
                ),
            )
            for w in results.warnings
        ],
        diagnosis=DiagnosisResponse(
            registry_matches=results.diagnosis.registry_matches,
            distance_filtered=results.diagnosis.distance_filtered,
            checked_for_availability=(
                results.diagnosis.checked_for_availability
            ),
            binding_constraint=results.diagnosis.binding_constraint,
            explanation=results.diagnosis.explanation,
        ) if results.diagnosis else None,
        date_suggestions=[
            DateSuggestionResponse(
                start_date=s.start_date,
                end_date=s.end_date,
                campgrounds_with_availability=(
                    s.campgrounds_with_availability
                ),
                reason=s.reason,
            )
            for s in results.date_suggestions
        ],
        action_chips=[
            ActionChipResponse(
                action=c.action,
                label=c.label,
                params=c.params,
            )
            for c in results.action_chips
        ],
    )


@app.get("/api/search/stream")
async def search_stream(
    start_date: date = Query(..., description="Start date"),
    end_date: date = Query(..., description="End date"),
    state: str | None = Query(None),
    nights: int = Query(2),
    mode: str | None = Query(None),
    days_of_week: str | None = Query(None),
    tags: str | None = Query(None),
    max_drive: int | None = Query(None),
    from_location: str | None = Query(None, alias="from"),
    name: str | None = Query(None),
    source: str | None = Query(None),
    no_groups: bool = Query(False),
    include_fcfs: bool = Query(False),
    limit: int = Query(20, ge=1, le=50),
):
    """SSE streaming search — yields results as each batch completes."""
    days_set = (
        {int(d) for d in days_of_week.split(",")} if days_of_week else None
    )
    booking_system = BookingSystem(source) if source else None

    query = SearchQuery(
        state=state,
        start_date=start_date,
        end_date=end_date,
        min_consecutive_nights=nights,
        days_of_week=days_set,
        tags=tags.split(",") if tags else None,
        max_drive_minutes=max_drive,
        from_location=from_location,
        name_like=name,
        include_group_sites=not no_groups,
        include_fcfs=include_fcfs,
        max_campgrounds=limit,
        booking_system=booking_system,
    )

    async def event_generator():
        available_count = 0
        async for result in _engine.search_stream(query):
            data = _format_result(
                result, booking_system or BookingSystem.RECGOV
            )
            yield f"data: {json.dumps(data.model_dump())}\n\n"
            if result.total_available_sites > 0:
                available_count += 1

        # Diagnosis when no reservable availability found
        if available_count == 0:
            full = await _engine.search(query)
            if full.diagnosis or full.date_suggestions:
                meta = {
                    "type": "diagnosis",
                    "diagnosis": (
                        {
                            "registry_matches": full.diagnosis.registry_matches,
                            "distance_filtered": full.diagnosis.distance_filtered,
                            "checked_for_availability": (
                                full.diagnosis.checked_for_availability
                            ),
                            "binding_constraint": (
                                full.diagnosis.binding_constraint
                            ),
                            "explanation": full.diagnosis.explanation,
                        }
                        if full.diagnosis
                        else None
                    ),
                    "date_suggestions": [
                        {
                            "start_date": s.start_date,
                            "end_date": s.end_date,
                            "campgrounds_with_availability": (
                                s.campgrounds_with_availability
                            ),
                            "reason": s.reason,
                        }
                        for s in full.date_suggestions
                    ],
                    "action_chips": [
                        {
                            "action": c.action,
                            "label": c.label,
                            "params": c.params,
                        }
                        for c in full.action_chips
                    ],
                }
                yield f"data: {json.dumps(meta)}\n\n"

        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(), media_type="text/event-stream"
    )


@app.get("/api/check/{facility_id}", response_model=CampgroundResultResponse)
async def check(
    facility_id: str,
    start_date: date = Query(...),
    end_date: date = Query(...),
    nights: int = Query(1),
    source: str | None = Query(None, description="recgov or wa_state"),
):
    if not _FACILITY_ID_RE.match(facility_id):
        raise HTTPException(status_code=400, detail="Invalid facility_id")
    booking_system = BookingSystem(source) if source else None
    result = await _engine.check_specific(
        facility_id=facility_id,
        start_date=start_date,
        end_date=end_date,
        min_nights=nights,
        booking_system=booking_system,
    )
    return _format_result(
        result, booking_system or BookingSystem.RECGOV
    )


@app.get("/api/campgrounds", response_model=list[CampgroundResponse])
async def list_campgrounds(
    state: str | None = Query(None),
    tags: str | None = Query(None),
    max_drive: int | None = Query(None),
    name: str | None = Query(None),
    source: str | None = Query(None),
):
    booking_system = BookingSystem(source) if source else None
    results = _registry.search(
        state=state,
        tags=tags.split(",") if tags else None,
        max_drive_minutes=max_drive,
        name_like=name,
        booking_system=booking_system,
    )
    return [
        CampgroundResponse(
            id=cg.id,
            facility_id=cg.facility_id,
            name=cg.name,
            booking_system=cg.booking_system.value,
            state=cg.state,
            region=cg.region,
            latitude=cg.latitude,
            longitude=cg.longitude,
            tags=cg.tags,
            vibe=cg.vibe,
            drive_minutes_from_base=cg.drive_minutes_from_base,
            notes=cg.notes,
            rating=cg.rating,
            total_sites=cg.total_sites,
            enabled=cg.enabled,
        )
        for cg in results
    ]


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

SESSION_COOKIE = "campnw_session"
_FACILITY_ID_RE = re.compile(r"^[-\w]{1,30}$")


def _get_session_token(request: Request, response: Response) -> str:
    """Get or create a session token cookie for anonymous watch ownership."""
    import uuid

    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        token = str(uuid.uuid4())
        response.set_cookie(
            SESSION_COOKIE, token,
            max_age=90 * 24 * 3600,  # 90 days
            httponly=True,
            secure=True,
            samesite="lax",
        )
    return token


def _get_current_user(request: Request) -> int | None:
    """Extract user_id from JWT cookie, or None if anonymous."""
    token = request.cookies.get(TOKEN_COOKIE)
    if not token:
        return None
    return decode_jwt(token)


def _set_auth_cookie(response: Response, user_id: int) -> None:
    token = create_jwt(user_id)
    response.set_cookie(
        TOKEN_COOKIE, token,
        max_age=TOKEN_MAX_AGE,
        httponly=True,
        secure=True,
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
    }


# ---------------------------------------------------------------------------
# Auth endpoints
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


@app.post("/api/auth/signup")
async def signup(body: SignupRequest, request: Request, response: Response):
    existing = _watch_db.get_user_by_email(body.email)
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    user = _watch_db.create_user(User(
        email=body.email,
        password_hash=hash_password(body.password),
        display_name=body.display_name,
    ))

    # Migrate anonymous watches to this new account
    session_token = request.cookies.get(SESSION_COOKIE)
    if session_token:
        _watch_db.migrate_watches_to_user(session_token, user.id)

    _set_auth_cookie(response, user.id)
    return {"user": _user_to_dict(user)}


@app.post("/api/auth/login")
async def login(body: LoginRequest, request: Request, response: Response):
    from datetime import datetime

    user = _watch_db.get_user_by_email(body.email)
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    _watch_db.update_user(user.id, last_login_at=datetime.now().isoformat())

    # Migrate any anonymous watches from current session
    session_token = request.cookies.get(SESSION_COOKIE)
    if session_token:
        _watch_db.migrate_watches_to_user(session_token, user.id)

    _set_auth_cookie(response, user.id)
    return {"user": _user_to_dict(user)}


@app.post("/api/auth/logout")
async def logout(response: Response):
    response.delete_cookie(TOKEN_COOKIE)
    return {"ok": True}


@app.get("/api/auth/me")
async def get_me(request: Request):
    user_id = _get_current_user(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user = _watch_db.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    tier = _get_user_tier(user_id)
    return {
        "user": _user_to_dict(user),
        "tier": tier["tier"],
        "subscription_status": user.subscription_status,
    }


@app.patch("/api/auth/me")
async def update_me(body: UpdateProfileRequest, request: Request):
    user_id = _get_current_user(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    user = _watch_db.update_user(user_id, **updates)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {"user": _user_to_dict(user)}


@app.delete("/api/auth/me")
async def delete_me(request: Request, response: Response):
    user_id = _get_current_user(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    _watch_db.delete_user(user_id)
    response.delete_cookie(TOKEN_COOKIE)
    return {"ok": True}


@app.get("/api/auth/export")
async def export_data(request: Request):
    user_id = _get_current_user(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    data = _watch_db.get_user_export(user_id)
    return data


@app.get("/api/search-history")
async def search_history(request: Request):
    user_id = _get_current_user(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return _watch_db.get_search_history(user_id)


class SaveSearchRequest(BaseModel):
    params: dict
    result_count: int = Field(default=0, ge=0)


@app.post("/api/search-history")
async def save_search(body: SaveSearchRequest, request: Request):
    user_id = _get_current_user(request)
    if not user_id:
        return {"ok": False}
    _watch_db.save_search(user_id, json.dumps(body.params), body.result_count)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Poll status
# ---------------------------------------------------------------------------


@app.get("/api/poll-status")
async def poll_status(request: Request):
    user_id = _get_current_user(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    recent = _watch_db.get_recent_notifications(limit=10) if _watch_db else []
    return {
        **_poll_state,
        "recent_notifications": recent,
    }


# ---------------------------------------------------------------------------
# Push notification endpoints
# ---------------------------------------------------------------------------


@app.get("/api/push/vapid-key")
async def get_vapid_key():
    """Return the VAPID public key for client-side push subscription setup."""
    key = os.getenv("VAPID_PUBLIC_KEY", "")
    return {"public_key": key}


@app.post("/api/push/subscribe")
async def push_subscribe(body: PushSubscribeRequest, request: Request, response: Response):
    """Register a web push subscription for the current user or session."""
    user_id = _get_current_user(request)
    session_token = request.cookies.get(SESSION_COOKIE, "") if not user_id else ""
    _watch_db.save_push_subscription(
        user_id=user_id,
        session_token=session_token,
        endpoint=body.endpoint,
        p256dh=body.p256dh,
        auth=body.auth,
    )
    return {"ok": True}


@app.delete("/api/push/subscribe")
async def push_unsubscribe(body: PushUnsubscribeRequest, request: Request):
    """Remove a web push subscription (e.g. when the user unsubscribes)."""
    _watch_db.delete_push_subscription(body.endpoint)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Watch CRUD
# ---------------------------------------------------------------------------


class WatchRequest(BaseModel):
    facility_id: str = Field(max_length=30, pattern=r"^[-\w]{1,30}$")
    name: str = Field(default="", max_length=200)
    start_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    end_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    min_nights: int = Field(default=1, ge=1, le=30)
    days_of_week: list[int] | None = None
    notify_topic: str = Field(default="", max_length=64, pattern=r"^[A-Za-z0-9_-]*$")
    notification_channel: str = Field(
        default="", max_length=20, pattern=r"^(ntfy|pushover|web_push|)?$"
    )


class WatchResponse(BaseModel):
    id: int
    facility_id: str
    name: str
    start_date: str
    end_date: str
    min_nights: int
    days_of_week: list[int] | None
    notify_topic: str
    notification_channel: str
    enabled: bool
    created_at: str


class PushSubscribeRequest(BaseModel):
    endpoint: str = Field(max_length=500)
    p256dh: str = Field(max_length=200)
    auth: str = Field(max_length=100)


class PushUnsubscribeRequest(BaseModel):
    endpoint: str = Field(max_length=500)


def _owns_watch(watch: Watch, user_id: int | None, session_token: str) -> bool:
    """Check if the current user/session owns a watch."""
    return (
        (bool(user_id) and watch.user_id == user_id)
        or (bool(session_token) and watch.session_token == session_token)
    )


@app.post("/api/watches", response_model=WatchResponse)
async def create_watch(body: WatchRequest, request: Request, response: Response):
    user_id = _get_current_user(request)
    token = _get_session_token(request, response) if not user_id else ""

    # Look up name from registry if not provided
    name = body.name
    if not name:
        cg = _registry.get_by_facility_id(body.facility_id)
        name = cg.name if cg else f"Facility {body.facility_id}"

    watch = Watch(
        facility_id=body.facility_id,
        name=name,
        start_date=body.start_date,
        end_date=body.end_date,
        min_nights=body.min_nights,
        days_of_week=body.days_of_week,
        notify_topic=body.notify_topic,
        notification_channel=body.notification_channel,
        session_token=token,
        user_id=user_id,
    )
    if _watch_db.has_duplicate_watch(watch):
        raise HTTPException(
            status_code=409, detail="Watch already exists",
        )

    # Enforce watch limit based on subscription tier
    tier = _get_user_tier(user_id)
    if user_id:
        current_count = len(_watch_db.list_watches_by_user(user_id))
    else:
        current_count = len(_watch_db.list_watches_by_session(token))
    if current_count >= tier["max_watches"]:
        raise HTTPException(
            status_code=402,
            detail={
                "error": "watch_limit",
                "limit": tier["max_watches"],
                "current": current_count,
                "tier": tier["tier"],
            },
        )

    saved = _watch_db.add_watch(watch)
    return WatchResponse(
        id=saved.id,
        facility_id=saved.facility_id,
        name=saved.name,
        start_date=saved.start_date,
        end_date=saved.end_date,
        min_nights=saved.min_nights,
        days_of_week=saved.days_of_week,
        notify_topic=saved.notify_topic,
        notification_channel=saved.notification_channel,
        enabled=saved.enabled,
        created_at=saved.created_at,
    )


@app.get("/api/watches", response_model=list[WatchResponse])
async def list_watches(request: Request, response: Response):
    user_id = _get_current_user(request)
    if user_id:
        watches = _watch_db.list_watches_by_user(user_id)
    else:
        token = _get_session_token(request, response)
        watches = _watch_db.list_watches_by_session(token)
    return [
        WatchResponse(
            id=w.id,
            facility_id=w.facility_id,
            name=w.name,
            start_date=w.start_date,
            end_date=w.end_date,
            min_nights=w.min_nights,
            days_of_week=w.days_of_week,
            notify_topic=w.notify_topic,
            notification_channel=w.notification_channel,
            enabled=w.enabled,
            created_at=w.created_at,
        )
        for w in watches
    ]


@app.delete("/api/watches/{watch_id}")
async def delete_watch(watch_id: int, request: Request, response: Response):
    user_id = _get_current_user(request)
    token = request.cookies.get(SESSION_COOKIE, "")
    watch = _watch_db.get_watch(watch_id)
    if not watch or not _owns_watch(watch, user_id, token):
        return {"ok": False, "error": "Not found"}
    _watch_db.remove_watch(watch_id)
    return {"ok": True}


@app.patch("/api/watches/{watch_id}/toggle")
async def toggle_watch(watch_id: int, request: Request, response: Response):
    user_id = _get_current_user(request)
    token = request.cookies.get(SESSION_COOKIE, "")
    watch = _watch_db.get_watch(watch_id)
    if not watch or not _owns_watch(watch, user_id, token):
        return {"ok": False, "error": "Not found"}
    new_state = _watch_db.toggle_enabled(watch_id, token)
    return {"ok": True, "enabled": new_state}


# ---------------------------------------------------------------------------
# Billing
# ---------------------------------------------------------------------------


@app.get("/api/billing/status")
async def billing_status(request: Request, response: Response):
    """Return subscription tier, watch usage, and plan session usage."""
    user_id = _get_current_user(request)
    tier = _get_user_tier(user_id)

    # Count watches
    if user_id:
        current_watches = len(_watch_db.list_watches_by_user(user_id))
    else:
        token = _get_session_token(request, response)
        current_watches = len(_watch_db.list_watches_by_session(token))

    # Count plan sessions this month
    month_start = date.today().replace(day=1).isoformat()
    session_key = request.cookies.get(SESSION_COOKIE) or request.client.host or "anon"
    if user_id and _watch_db:
        plan_used = _watch_db.count_plan_sessions(user_id=user_id, since=month_start)
    elif _watch_db:
        plan_used = _watch_db.count_plan_sessions(
            session_token=session_key, since=month_start,
        )
    else:
        plan_used = 0

    # Grandfathered info
    grandfathered_until = None
    if user_id and _watch_db:
        user = _watch_db.get_user_by_id(user_id)
        if user and user.grandfathered_until:
            grandfathered_until = user.grandfathered_until

    return {
        "tier": tier["tier"],
        "subscription_status": (
            _watch_db.get_user_by_id(user_id).subscription_status
            if user_id and _watch_db
            else "free"
        ),
        "max_watches": tier["max_watches"],
        "current_watches": current_watches,
        "plan_sessions_used": plan_used,
        "plan_sessions_limit": tier["plan_sessions_per_month"],
        "grandfathered_until": grandfathered_until,
    }


@app.post("/api/billing/checkout")
async def billing_checkout(request: Request):
    """Create a Stripe Checkout Session and return the redirect URL."""
    from pnw_campsites.billing import create_checkout_session

    user_id = _get_current_user(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Login required")
    user = _watch_db.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    if user.subscription_status == "pro":
        raise HTTPException(status_code=400, detail="Already subscribed")

    try:
        url, customer_id = create_checkout_session(
            user_id, user.email,
            customer_id=user.stripe_customer_id or None,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    # Save customer ID if newly created
    if customer_id and customer_id != user.stripe_customer_id:
        _watch_db.update_user(user_id, stripe_customer_id=customer_id)

    return {"url": url}


@app.post("/api/billing/portal")
async def billing_portal(request: Request):
    """Create a Stripe Customer Portal session and return the redirect URL."""
    from pnw_campsites.billing import create_portal_session

    user_id = _get_current_user(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Login required")
    user = _watch_db.get_user_by_id(user_id)
    if not user or not user.stripe_customer_id:
        raise HTTPException(
            status_code=400, detail="No billing account found",
        )

    try:
        url = create_portal_session(user.stripe_customer_id)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    return {"url": url}


@app.post("/api/billing/webhook")
async def billing_webhook(request: Request):
    """Stripe webhook receiver — verifies HMAC signature, processes events."""
    from pnw_campsites.billing import handle_webhook_event, verify_webhook

    # Must read raw body for signature verification
    body = await request.body()
    sig = request.headers.get("stripe-signature", "")

    try:
        event = verify_webhook(body, sig)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    handle_webhook_event(event, _watch_db)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Trip planner
# ---------------------------------------------------------------------------

def _check_plan_limit(
    user_id: int | None, session_key: str,
) -> tuple[bool, bool, int, int]:
    """Check trip planner monthly limit.

    Returns (allowed, soft_gate, used, limit).
    - allowed=True, soft_gate=False: normal usage
    - allowed=True, soft_gate=True: at limit, show upgrade prompt
    - allowed=False: hard block
    """
    tier = _get_user_tier(user_id)
    limit = tier["plan_sessions_per_month"]
    month_start = date.today().replace(day=1).isoformat()
    if user_id and _watch_db:
        used = _watch_db.count_plan_sessions(user_id=user_id, since=month_start)
    elif _watch_db:
        used = _watch_db.count_plan_sessions(
            session_token=session_key, since=month_start,
        )
    else:
        return True, False, 0, limit
    if used < limit:
        return True, False, used, limit
    if used == limit:
        # Soft gate: show upgrade prompt but allow one more
        return True, True, used, limit
    return False, False, used, limit


class PlanChatRequest(BaseModel):
    messages: list[dict]


class PlanChatResponse(BaseModel):
    role: str
    content: str
    tool_calls: list[dict] = []


@app.post("/api/plan/chat", response_model=PlanChatResponse)
async def plan_chat(body: PlanChatRequest, request: Request, response: Response):
    from pnw_campsites.planner.agent import chat

    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise HTTPException(status_code=503, detail="Trip planner not configured")

    user_id = _get_current_user(request)
    session_key = request.cookies.get(SESSION_COOKIE) or request.client.host or "anon"
    allowed, soft_gate, used, limit = _check_plan_limit(user_id, session_key)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "plan_limit",
                "used": used,
                "limit": limit,
                "tier": _get_user_tier(user_id)["tier"],
            },
        )
    if _watch_db:
        _watch_db.record_plan_session(user_id=user_id, session_token=session_key)

    result = await chat(body.messages, _engine, _registry, api_key)
    resp = PlanChatResponse(**result)
    return resp


@app.post("/api/plan/chat/stream")
async def plan_chat_stream(body: PlanChatRequest, request: Request):
    from pnw_campsites.planner.agent import chat_stream

    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise HTTPException(status_code=503, detail="Trip planner not configured")

    user_id = _get_current_user(request)
    session_key = request.cookies.get(SESSION_COOKIE) or request.client.host or "anon"
    allowed, soft_gate, used, limit = _check_plan_limit(user_id, session_key)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "plan_limit",
                "used": used,
                "limit": limit,
                "tier": _get_user_tier(user_id)["tier"],
            },
        )
    if _watch_db:
        _watch_db.record_plan_session(user_id=user_id, session_token=session_key)

    async def event_generator():
        async for event_json in chat_stream(body.messages, _engine, _registry, api_key):
            yield f"data: {event_json}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# Static file serving (production — serves React build from /static)
# ---------------------------------------------------------------------------

# Serve React build in production. Check the Docker location (/app/static)
# first, then fall back to relative paths for local dev.
_static_candidates = [
    Path("/app/static"),
    Path(__file__).resolve().parents[3] / "static",
    Path(__file__).resolve().parents[2] / "static",
]
for _static_dir in _static_candidates:
    if _static_dir.is_dir():
        app.mount("/", StaticFiles(directory=str(_static_dir), html=True), name="static")
        break
