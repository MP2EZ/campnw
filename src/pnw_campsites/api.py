"""FastAPI backend exposing the campsite search library as a REST API."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from collections import deque
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response

from pnw_campsites.monitor.db import WatchDB
from pnw_campsites.providers.goingtocamp import GoingToCampClient
from pnw_campsites.providers.recgov import RecGovClient
from pnw_campsites.providers.reserveamerica import ReserveAmericaClient
from pnw_campsites.registry.db import CampgroundRegistry
from pnw_campsites.search.engine import SearchEngine

# ---------------------------------------------------------------------------
# App state — initialized in lifespan
# ---------------------------------------------------------------------------

_registry: CampgroundRegistry | None = None
_recgov: RecGovClient | None = None
_goingtocamp: GoingToCampClient | None = None
_reserveamerica: ReserveAmericaClient | None = None
_engine: SearchEngine | None = None
_watch_db: WatchDB | None = None
_posthog_client: httpx.AsyncClient | None = None
_poll_state: dict = {
    "last_poll": None,
    "next_poll": None,
    "active_watches": 0,
    "last_changes": 0,
    "last_errors": 0,
}

# Search timing
_search_timings: deque[float] = deque(maxlen=200)

_poll_logger = logging.getLogger("pnw_campsites.poller")


async def _poll_tranche(tranche: int | None = None) -> None:
    """Background job: poll a tranche of watches and dispatch notifications.

    When tranche is 0 or 1, only polls watches where id % 2 == tranche.
    This splits the API load into two cycles offset by ~7.5 minutes.
    """
    from pnw_campsites.monitor.notify import notify_ntfy, notify_web_push
    from pnw_campsites.monitor.watcher import poll_all

    if not _watch_db:
        return

    label = f"tranche {tranche}" if tranche is not None else "all"
    _poll_logger.info("Starting watch poll cycle (%s)", label)
    results = await poll_all(
        _recgov, _goingtocamp, _watch_db, _registry, tranche=tranche,
        reserveamerica=_reserveamerica,
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

    now = datetime.now(UTC)
    _poll_state["last_poll"] = now.isoformat()
    _poll_state["next_poll"] = (now + timedelta(minutes=15)).isoformat()
    _poll_state["last_changes"] = total_changes
    _poll_state["last_errors"] = total_errors
    _poll_state["active_watches"] = len(results)
    _poll_logger.info(
        "Poll cycle complete: %d watches, %d changes, %d errors",
        len(results), total_changes, total_errors,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _registry, _recgov, _goingtocamp, _reserveamerica, _engine, _watch_db, _posthog_client
    load_dotenv()

    _registry = CampgroundRegistry()
    api_key = os.getenv("RIDB_API_KEY")
    if api_key:
        _recgov = RecGovClient(ridb_api_key=api_key)
        await _recgov.__aenter__()

    _goingtocamp = GoingToCampClient()
    await _goingtocamp.__aenter__()

    _reserveamerica = ReserveAmericaClient()
    await _reserveamerica.__aenter__()

    _engine = SearchEngine(_registry, _recgov, _goingtocamp, _reserveamerica)
    _watch_db = WatchDB()

    # Start background watch poller — two tranches offset by 7.5 minutes
    # to halve the burst of rec.gov API calls per cycle
    scheduler = None
    if os.getenv("DISABLE_SCHEDULER") != "1":
        from functools import partial

        from apscheduler.schedulers.asyncio import AsyncIOScheduler

        scheduler = AsyncIOScheduler()
        scheduler.add_job(
            partial(_poll_tranche, tranche=0),
            "interval",
            minutes=15,
            id="watch_poller_t0",
            max_instances=1,
            coalesce=True,
            # Fire immediately on startup so watches don't wait 15 min
            next_run_time=datetime.now(),
        )
        scheduler.add_job(
            partial(_poll_tranche, tranche=1),
            "interval",
            minutes=15,
            id="watch_poller_t1",
            max_instances=1,
            coalesce=True,
            # Offset by 7.5 minutes from tranche 0
            next_run_time=datetime.now() + timedelta(minutes=7, seconds=30),
        )
        # Weekly analytics digest — Monday 8am Pacific
        async def _weekly_digest():
            import logging

            import httpx as _httpx

            from pnw_campsites.analytics.digest import generate_weekly_digest

            log = logging.getLogger(__name__)
            report = await generate_weekly_digest(_watch_db)
            log.info("Weekly digest:\n%s", report)
            # Send via ntfy if configured
            topic = os.getenv("DIGEST_NTFY_TOPIC")
            if topic and report:
                try:
                    async with _httpx.AsyncClient() as c:
                        await c.post(
                            f"https://ntfy.sh/{topic}",
                            content=report[:4000].encode(),
                            headers={"Title": "campable Weekly Digest"},
                        )
                except Exception as e:
                    log.warning("Digest ntfy send failed: %s", e)

        scheduler.add_job(
            _weekly_digest,
            "cron",
            day_of_week="mon",
            hour=8,
            id="weekly_digest",
            max_instances=1,
            coalesce=True,
        )

        scheduler.start()
        next_t0 = scheduler.get_job("watch_poller_t0").next_run_time
        _poll_state["next_poll"] = (
            next_t0.isoformat() if next_t0 else None
        )
        _poll_logger.info("Watch poller started (2 tranches, 15-min interval, 7.5-min offset)")

    _posthog_client = httpx.AsyncClient(timeout=10.0)

    yield

    if _posthog_client:
        await _posthog_client.aclose()

    if scheduler:
        scheduler.shutdown(wait=False)

    if _watch_db:
        _watch_db.close()

    if _recgov:
        await _recgov.__aexit__(None, None, None)
    if _goingtocamp:
        await _goingtocamp.__aexit__(None, None, None)
    if _reserveamerica:
        await _reserveamerica.__aexit__(None, None, None)
    if _registry:
        _registry.close()


logging.basicConfig(level=logging.INFO)

app = FastAPI(title="PNW Campsites", lifespan=lifespan)

_cors_origins = os.getenv(
    "ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:5177,http://localhost:3000"
).split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_methods=["GET", "POST", "DELETE", "PATCH"],
    allow_headers=["Content-Type"],
    allow_credentials=True,
)

# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

_search_logger = logging.getLogger("pnw_campsites.timing")


@app.middleware("http")
async def timing_middleware(request: Request, call_next):
    start = time.monotonic()
    response = await call_next(request)
    elapsed_ms = (time.monotonic() - start) * 1000
    response.headers["Server-Timing"] = f"total;dur={elapsed_ms:.0f}"
    if request.url.path.startswith("/api/search"):
        _search_timings.append(elapsed_ms)
        _search_logger.info("search_timing path=%s elapsed_ms=%.0f", request.url.path, elapsed_ms)
    # Security headers
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' https://*.tile.openstreetmap.org data:; "
        "connect-src 'self' https://*.tile.openstreetmap.org; "
        "frame-ancestors 'none'"
    )
    return response


# ---------------------------------------------------------------------------
# Route modules
# ---------------------------------------------------------------------------

from pnw_campsites.routes.auth import router as auth_router  # noqa: E402
from pnw_campsites.routes.compare import router as compare_router  # noqa: E402
from pnw_campsites.routes.planner import router as planner_router  # noqa: E402
from pnw_campsites.routes.poll import router as poll_router  # noqa: E402
from pnw_campsites.routes.push import router as push_router  # noqa: E402
from pnw_campsites.routes.recommendations import router as recs_router  # noqa: E402
from pnw_campsites.routes.search import router as search_router  # noqa: E402
from pnw_campsites.routes.sharing import router as sharing_router  # noqa: E402
from pnw_campsites.routes.tracking import router as tracking_router  # noqa: E402
from pnw_campsites.routes.trips import router as trips_router  # noqa: E402
from pnw_campsites.routes.watches import router as watches_router  # noqa: E402

app.include_router(search_router)
app.include_router(auth_router)
app.include_router(watches_router)
app.include_router(push_router)
app.include_router(planner_router)
app.include_router(tracking_router)
app.include_router(recs_router)
app.include_router(trips_router)
app.include_router(sharing_router)
app.include_router(compare_router)
app.include_router(poll_router)

# Re-export for test compatibility
from pnw_campsites.routes.auth import _auth_rate_limit  # noqa: E402, F401
from pnw_campsites.routes.deps import SESSION_COOKIE  # noqa: E402, F401

# ---------------------------------------------------------------------------
# PostHog reverse proxy — avoids ad blockers
# ---------------------------------------------------------------------------

_posthog_host = "https://eu.i.posthog.com"
_posthog_asset_host = "https://eu-assets.i.posthog.com"


@app.api_route("/ingest/{path:path}", methods=["GET", "POST", "OPTIONS"])
async def posthog_proxy(request: Request, path: str):
    """Proxy PostHog requests through our domain to bypass ad blockers."""
    # Static assets (array.full.js, recorder, etc.) come from the asset host
    if path.startswith("static/") or path.startswith("array/"):
        target = f"{_posthog_asset_host}/{path}"
    else:
        target = f"{_posthog_host}/{path}"

    headers = {
        k: v for k, v in request.headers.items()
        if k.lower() not in ("host", "connection", "content-length")
    }
    body = await request.body()

    if not _posthog_client:
        return Response(status_code=503)
    resp = await _posthog_client.request(
        method=request.method,
        url=target,
        headers=headers,
        content=body,
        params=dict(request.query_params),
    )

    return Response(
        content=resp.content,
        status_code=resp.status_code,
        headers={
            k: v for k, v in resp.headers.items()
            if k.lower() not in ("transfer-encoding", "content-encoding", "connection")
        },
    )


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
_static_dir: Path | None = None
for _candidate in _static_candidates:
    if _candidate.is_dir():
        _static_dir = _candidate
        break

if _static_dir is not None:

    @app.get("/{path:path}")
    async def spa_fallback(path: str) -> FileResponse:
        """Serve index.html for SPA client-side routes (e.g. /map, /plan)."""
        # Let API routes and actual static files pass through
        if path.startswith("api/"):
            raise HTTPException(404)
        # Serve actual file if it exists (JS, CSS, images, etc.)
        file_path = (_static_dir / path).resolve()
        if path and file_path.is_file() and str(file_path).startswith(str(_static_dir.resolve())):
            return FileResponse(file_path)
        # Everything else gets index.html for React Router
        index = _static_dir / "index.html"
        if index.exists():
            return FileResponse(index, media_type="text/html")
        raise HTTPException(404)
