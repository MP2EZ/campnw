"""Performance and admin routes. Event tracking moved to PostHog (client-side)."""

from __future__ import annotations

import statistics

from fastapi import APIRouter, HTTPException, Request

from pnw_campsites.routes.deps import (
    get_current_user,
    get_search_timings,
    get_watch_db,
)

router = APIRouter(prefix="/api", tags=["tracking"])


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
