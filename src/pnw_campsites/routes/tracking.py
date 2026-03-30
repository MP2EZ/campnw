"""Performance and admin routes. Event tracking moved to PostHog (client-side)."""

from __future__ import annotations

import os
import statistics

from fastapi import APIRouter, HTTPException, Request

from pnw_campsites.routes.deps import (
    get_current_user,
    get_search_timings,
    get_watch_db,
)

router = APIRouter(prefix="/api", tags=["tracking"])

# Admin user IDs (comma-separated in env, e.g. "1,2")
_ADMIN_IDS: set[int] | None = None


def _is_admin(user_id: int | None) -> bool:
    global _ADMIN_IDS
    if _ADMIN_IDS is None:
        raw = os.getenv("ADMIN_USER_IDS", "1")
        _ADMIN_IDS = {int(x.strip()) for x in raw.split(",") if x.strip()}
    return user_id is not None and user_id in _ADMIN_IDS


@router.get("/perf")
async def perf_stats(request: Request):
    """Server timing stats. Admin only."""
    user_id = get_current_user(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if not _is_admin(user_id):
        raise HTTPException(status_code=403, detail="Admin access required")
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
    """On-demand analytics digest generation. Admin only."""
    user_id = get_current_user(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if not _is_admin(user_id):
        raise HTTPException(status_code=403, detail="Admin access required")
    from pnw_campsites.analytics.digest import generate_weekly_digest

    db = get_watch_db()
    report = await generate_weekly_digest(db)
    return {"report": report}
