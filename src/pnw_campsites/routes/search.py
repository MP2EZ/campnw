"""Search, check, and campground listing routes."""

from __future__ import annotations

import json
import logging
from datetime import date

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from pnw_campsites.registry.models import BookingSystem
from pnw_campsites.routes.deps import (
    _FACILITY_ID_RE,
    get_engine,
    get_registry,
)
from pnw_campsites.search.engine import SearchQuery, StreamDiagnosisEvent
from pnw_campsites.urls import (
    or_state_availability_url,
    recgov_availability_url,
    recgov_campsite_booking_url,
    wa_state_availability_url,
)

router = APIRouter(prefix="/api", tags=["search"])

_search_logger = logging.getLogger("pnw_campsites.api")

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
    elevator_pitch: str = ""
    description_rewrite: str = ""
    best_for: str = ""
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


async def _generate_search_summary(
    results_data: list[dict],
    query: SearchQuery,
) -> str | None:
    """Generate a brief AI summary of search results. Returns None on failure."""
    import asyncio
    import os

    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        return None

    import anthropic

    client = anthropic.AsyncAnthropic(api_key=api_key)

    compact = json.dumps(results_data[:20])  # cap at 20 for token budget
    state_str = query.state or "all states"
    date_str = f"{query.start_date} to {query.end_date}"

    prompt = (
        "Write 2 short sentences about these campsite search results.\n"
        "Sentence 1: Top pick — name it, say why (distance, feature, availability).\n"
        "Sentence 2: One useful pattern or standout detail from the rest.\n\n"
        f"Search: {state_str}, {date_str}, "
        f"{query.min_consecutive_nights} nights\n"
        f"Results ({len(results_data)} campgrounds):\n"
        f"{compact}\n\n"
        "Voice rules:\n"
        "- Declarative and specific. Lead with the campground name.\n"
        "- Bold **campground names** only.\n"
        "- No filler ('you won't regret', 'making it ideal', 'solid backup').\n"
        "- No inventory language ('offering X sites across Y').\n"
        "- State facts, not feelings. The data speaks.\n"
        "- No preamble, no sign-off."
    )

    try:
        response = await asyncio.wait_for(
            client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=150,
                messages=[{"role": "user", "content": prompt}],
            ),
            timeout=3.0,
        )
        return response.content[0].text.strip()
    except Exception:
        return None


def _build_availability_url(
    facility_id: str,
    booking_system: BookingSystem,
    start_date: date | None,
    end_date: date | None = None,
    slug: str = "",
) -> str:
    if booking_system == BookingSystem.WA_STATE:
        return wa_state_availability_url(facility_id, start_date, end_date)
    if booking_system == BookingSystem.OR_STATE:
        return or_state_availability_url(facility_id, slug, start_date, end_date)
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
        elevator_pitch=cg.elevator_pitch,
        description_rewrite=cg.description_rewrite,
        best_for=cg.best_for,
        estimated_drive_minutes=r.estimated_drive_minutes,
        availability_url=_build_availability_url(
            cg.facility_id, cg.booking_system, start, end,
            slug=cg.booking_url_slug,
        ) if start else None,
        windows=windows,
        error=r.error,
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/campgrounds/{facility_id}/tips")
async def get_booking_tips(facility_id: str):
    """Return cached booking tips for a campground."""
    import json as _json
    registry = get_registry()
    cg = registry.get_by_facility_id(facility_id)
    if not cg:
        return {"tips": [], "data_through": None}
    tips_raw = cg.booking_tips or "[]"
    try:
        tips = _json.loads(tips_raw) if isinstance(tips_raw, str) else tips_raw
    except (ValueError, TypeError):
        tips = []
    return {"tips": tips, "facility_id": facility_id}


@router.get("/search", response_model=SearchResponse)
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
    engine = get_engine()
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

    results = await engine.search(query)

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


@router.get("/search/stream")
async def search_stream(
    start_date: date | None = Query(None, description="Start date"),
    end_date: date | None = Query(None, description="End date"),
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
    q: str | None = Query(None, description="Natural language search query"),
):
    """SSE streaming search — yields results as each batch completes."""
    import os

    engine = get_engine()
    nl_parsed: dict | None = None

    # Natural language query -> structured params
    if q and not start_date:
        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        if api_key:
            from pnw_campsites.search.nl_parser import parse_natural_query

            nl_parsed = await parse_natural_query(q, api_key)
            # Apply NL-parsed values as defaults (explicit params override)
            if "start_date" in nl_parsed:
                start_date = date.fromisoformat(nl_parsed["start_date"])
            if "end_date" in nl_parsed:
                end_date = date.fromisoformat(nl_parsed["end_date"])
            if not state and "state" in nl_parsed:
                state = nl_parsed["state"]
            if not tags and "tags" in nl_parsed:
                tags = ",".join(nl_parsed["tags"])
            if not from_location and "from_location" in nl_parsed:
                from_location = nl_parsed["from_location"]
            if not max_drive and "max_drive_minutes" in nl_parsed:
                max_drive = nl_parsed["max_drive_minutes"]
            if not name and "name_like" in nl_parsed:
                name = nl_parsed["name_like"]
            if "min_consecutive_nights" in nl_parsed:
                nights = nl_parsed["min_consecutive_nights"]
            if not days_of_week and "days_of_week" in nl_parsed:
                days_of_week = nl_parsed["days_of_week"]

    # Require dates (either from query params or NL parse)
    if not start_date or not end_date:
        # Default: 2 weeks out, 30-day window
        from datetime import timedelta

        start_date = start_date or (date.today() + timedelta(days=14))
        end_date = end_date or (start_date + timedelta(days=30))

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
        # Emit parsed params so the frontend can show what was understood
        if nl_parsed:
            parsed_event = {
                "type": "parsed_params",
                "params": {
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                    "state": state,
                    "nights": nights,
                    "tags": tags,
                    "from_location": from_location,
                    "max_drive": max_drive,
                    "name": name,
                    "days_of_week": days_of_week,
                },
            }
            yield f"data: {json.dumps(parsed_event)}\n\n"

        available_count = 0
        summary_data: list[dict] = []
        async for item in engine.search_stream(query):
            # StreamDiagnosisEvent = zero results, emit diagnosis
            if isinstance(item, StreamDiagnosisEvent):
                if item.diagnosis or item.date_suggestions:
                    meta = {
                        "type": "diagnosis",
                        "diagnosis": (
                            {
                                "registry_matches": item.diagnosis.registry_matches,
                                "distance_filtered": item.diagnosis.distance_filtered,
                                "checked_for_availability": (
                                    item.diagnosis.checked_for_availability
                                ),
                                "binding_constraint": (
                                    item.diagnosis.binding_constraint
                                ),
                                "explanation": item.diagnosis.explanation,
                            }
                            if item.diagnosis
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
                            for s in item.date_suggestions
                        ],
                        "action_chips": [
                            {
                                "action": c.action,
                                "label": c.label,
                                "params": c.params,
                            }
                            for c in item.action_chips
                        ],
                    }
                    yield f"data: {json.dumps(meta)}\n\n"
                continue

            # CampgroundResult — normal result
            data = _format_result(
                item, booking_system or BookingSystem.RECGOV
            )
            yield f"data: {json.dumps(data.model_dump())}\n\n"
            if item.total_available_sites > 0:
                available_count += 1
                summary_data.append({
                    "name": item.campground.name,
                    "sites": item.total_available_sites,
                    "drive": item.estimated_drive_minutes,
                    "tags": item.campground.tags[:3],
                    "state": item.campground.state,
                })

        # AI summary when enough results to warrant it
        if available_count > 5:
            try:
                summary_text = await _generate_search_summary(
                    summary_data, query,
                )
                if summary_text:
                    yield f"data: {json.dumps({'type': 'summary', 'text': summary_text})}\n\n"
            except Exception:
                pass  # Silent skip — summary is optional

        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(), media_type="text/event-stream"
    )


@router.get("/check/{facility_id}", response_model=CampgroundResultResponse)
async def check(
    facility_id: str,
    start_date: date = Query(...),
    end_date: date = Query(...),
    nights: int = Query(1),
    source: str | None = Query(None, description="recgov or wa_state"),
):
    if not _FACILITY_ID_RE.match(facility_id):
        raise HTTPException(status_code=400, detail="Invalid facility_id")
    engine = get_engine()
    booking_system = BookingSystem(source) if source else None
    result = await engine.check_specific(
        facility_id=facility_id,
        start_date=start_date,
        end_date=end_date,
        min_nights=nights,
        booking_system=booking_system,
    )
    return _format_result(
        result, booking_system or BookingSystem.RECGOV
    )


@router.get("/campgrounds", response_model=list[CampgroundResponse])
async def list_campgrounds(
    state: str | None = Query(None),
    tags: str | None = Query(None),
    max_drive: int | None = Query(None),
    name: str | None = Query(None),
    source: str | None = Query(None),
):
    registry = get_registry()
    booking_system = BookingSystem(source) if source else None
    results = registry.search(
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
