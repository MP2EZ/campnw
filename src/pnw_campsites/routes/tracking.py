"""Event tracking and performance routes."""

from __future__ import annotations

import logging
import statistics

from fastapi import APIRouter, HTTPException, Request

from pnw_campsites.routes.deps import (
    get_current_user,
    get_search_timings,
    get_watch_db,
)

router = APIRouter(prefix="/api", tags=["tracking"])

_track_logger = logging.getLogger("pnw_campsites.track")

ALLOWED_TRACK_EVENTS = {"card_expand", "book_click", "search"}
ALLOWED_TRACK_FIELDS = {"event", "facility_id", "name", "source", "type", "site"}


@router.post("/track")
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


@router.get("/perf")
async def perf_stats():
    timings_deque = get_search_timings()
    if not timings_deque:
        return {"message": "No data yet"}
    timings = sorted(timings_deque)
    n = len(timings)
    return {
        "count": n,
        "p50_ms": round(statistics.median(timings)),
        "p95_ms": round(timings[int(n * 0.95)] if n >= 20 else timings[-1]),
        "p99_ms": round(timings[int(n * 0.99)] if n >= 100 else timings[-1]),
        "mean_ms": round(statistics.mean(timings)),
        "target_ms": 4000,
    }


@router.get("/admin/digest")
async def admin_digest(request: Request):
    """On-demand analytics digest generation. Requires authentication."""
    user_id = get_current_user(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    from pnw_campsites.analytics.digest import generate_weekly_digest

    db = get_watch_db()
    report = await generate_weekly_digest(db)
    return {"report": report}
