"""Server-rendered SEO pages: campground profiles, indexes, sitemap."""

from __future__ import annotations

import contextlib
import json
from datetime import datetime
from itertools import groupby
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from fastapi.templating import Jinja2Templates

from pnw_campsites.registry.models import BookingSystem
from pnw_campsites.routes.deps import get_registry
from pnw_campsites.urls import (
    or_state_availability_url,
    recgov_availability_url,
    wa_state_park_url,
)

router = APIRouter()

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

STATE_NAMES = {
    "WA": "Washington",
    "OR": "Oregon",
    "ID": "Idaho",
    "MT": "Montana",
    "WY": "Wyoming",
    "CA": "Northern California",
}

VALID_STATES = set(STATE_NAMES.keys())

SOURCE_LABELS = {
    "recgov": "Rec.gov",
    "wa_state": "WA State Parks",
    "or_state": "OR State Parks",
    "id_state": "ID State Parks",
}

BASE_URL = "https://campable.co"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _format_drive_time(minutes: int | None) -> str:
    if minutes is None:
        return ""
    h, m = divmod(minutes, 60)
    if h and m:
        return f"{h}h {m}m"
    if h:
        return f"{h}h"
    return f"{m}m"


def _booking_url(cg) -> str:
    """Build booking URL for a campground."""
    if cg.booking_system == BookingSystem.RECGOV:
        return recgov_availability_url(cg.facility_id)
    if cg.booking_system == BookingSystem.WA_STATE:
        return wa_state_park_url(str(abs(int(cg.facility_id))))
    if cg.booking_system == BookingSystem.OR_STATE:
        return or_state_availability_url(cg.facility_id, cg.booking_url_slug)
    return ""


def _common_ctx(request: Request) -> dict:
    """Context vars shared across all templates."""
    return {
        "request": request,
        "base_url": BASE_URL,
        "current_year": datetime.now().year,
        "format_drive_time": _format_drive_time,
        "source_labels": SOURCE_LABELS,
    }


def _cached_template(
    name: str, ctx: dict, *, max_age: int = 3600, stale: int = 86400,
):
    """Return a TemplateResponse with Cache-Control headers.

    max_age: seconds the edge/browser may serve from cache (default 1h).
    stale:   seconds the edge may serve stale while revalidating (default 24h).
    """
    resp = templates.TemplateResponse(ctx["request"], name, ctx)
    resp.headers["Cache-Control"] = (
        f"public, max-age={max_age}, stale-while-revalidate={stale}"
    )
    return resp


# ---------------------------------------------------------------------------
# Campground profile — /campgrounds/{state}/{slug}
# ---------------------------------------------------------------------------


@router.get("/campgrounds/{state}/{slug}")
async def campground_profile(request: Request, state: str, slug: str):
    state_upper = state.upper()
    if state_upper not in VALID_STATES:
        raise HTTPException(404)

    registry = get_registry()
    cg = registry.get_by_slug(state_upper, slug)
    if not cg:
        raise HTTPException(404)

    # Parse booking tips from JSON
    booking_tips = []
    if cg.booking_tips:
        with contextlib.suppress(json.JSONDecodeError, TypeError):
            booking_tips = json.loads(cg.booking_tips)

    # Nearby campgrounds
    nearby = []
    if cg.latitude and cg.longitude:
        nearby = registry.get_nearby(
            cg.latitude, cg.longitude,
            state=state_upper, limit=5, exclude_id=cg.id,
        )

    ctx = _common_ctx(request)
    ctx.update(
        cg=cg,
        state_name=STATE_NAMES[state_upper],
        source_label=SOURCE_LABELS.get(cg.booking_system.value, ""),
        drive_time=_format_drive_time(cg.drive_minutes_from_base),
        booking_url=_booking_url(cg),
        booking_tips=booking_tips,
        nearby=nearby,
        canonical_url=f"{BASE_URL}/campgrounds/{state.lower()}/{slug}",
    )
    return _cached_template("profile.html", ctx)


# ---------------------------------------------------------------------------
# State index — /campgrounds/{state}
# ---------------------------------------------------------------------------


@router.get("/campgrounds/{state}")
async def state_index(request: Request, state: str, tag: str | None = None):
    state_upper = state.upper()
    if state_upper not in VALID_STATES:
        raise HTTPException(404)

    registry = get_registry()
    if tag:
        campgrounds = registry.search(state=state_upper, tags=[tag])
    else:
        campgrounds = registry.search(state=state_upper)

    # Group by region
    campgrounds.sort(key=lambda c: (c.region or "zzz", c.name))
    groups = []
    for region, cgs in groupby(campgrounds, key=lambda c: c.region):
        groups.append((region, list(cgs)))

    # Collect tags available in this state for the filter bar
    tag_counts: dict[str, int] = {}
    all_in_state = campgrounds if not tag else registry.search(state=state_upper)
    for cg in all_in_state:
        for t in cg.tags:
            tag_counts[t] = tag_counts.get(t, 0) + 1
    all_tags = sorted(tag_counts.items(), key=lambda x: (-x[1], x[0]))

    ctx = _common_ctx(request)
    ctx.update(
        state=state_upper,
        state_name=STATE_NAMES[state_upper],
        total=len(campgrounds),
        groups=groups,
        all_tags=all_tags,
        active_tag=tag,
        canonical_url=f"{BASE_URL}/campgrounds/{state.lower()}",
    )
    return _cached_template("state_index.html", ctx)


# ---------------------------------------------------------------------------
# Campgrounds index — /campgrounds
# ---------------------------------------------------------------------------


@router.get("/campgrounds")
async def campgrounds_index(request: Request):
    registry = get_registry()
    counts = registry.count_by_state()
    total = sum(counts.values())

    states = [
        (s, {"count": counts.get(s, 0), "name": STATE_NAMES[s]})
        for s in sorted(VALID_STATES)
        if counts.get(s, 0) > 0
    ]

    all_tags = registry.get_all_tags()

    ctx = _common_ctx(request)
    ctx.update(
        total=total,
        states=states,
        all_tags=all_tags,
        canonical_url=f"{BASE_URL}/campgrounds",
    )
    return _cached_template("campgrounds_index.html", ctx)


# ---------------------------------------------------------------------------
# Tag index — /tags/{tag}
# ---------------------------------------------------------------------------


@router.get("/tags/{tag}")
async def tag_index(request: Request, tag: str):
    registry = get_registry()
    campgrounds = registry.search(tags=[tag])
    if not campgrounds:
        raise HTTPException(404)

    # Group by state
    campgrounds.sort(key=lambda c: (c.state, c.name))
    groups = []
    for state_code, cgs in groupby(campgrounds, key=lambda c: c.state):
        groups.append((STATE_NAMES.get(state_code, state_code), list(cgs)))

    all_tags = registry.get_all_tags()
    other_tags = [(t, c) for t, c in all_tags if t != tag][:15]

    ctx = _common_ctx(request)
    ctx.update(
        tag=tag,
        total=len(campgrounds),
        groups=groups,
        other_tags=other_tags,
        canonical_url=f"{BASE_URL}/tags/{tag}",
    )
    return _cached_template("tag_index.html", ctx)


# ---------------------------------------------------------------------------
# This Weekend — /this-weekend
# ---------------------------------------------------------------------------

# In-memory cache populated by APScheduler job in api.py
_weekend_cache: dict = {
    "results": None,
    "refreshed_at": None,
    "date_range": "",
}


def get_weekend_cache() -> dict:
    """Accessor for the weekend cache (used by api.py scheduler)."""
    return _weekend_cache


@router.get("/this-weekend")
async def this_weekend(request: Request):
    cache = _weekend_cache

    ctx = _common_ctx(request)
    ctx.update(
        results=cache.get("results"),
        groups=cache.get("groups", []),
        date_range=cache.get("date_range", ""),
        refreshed_at=cache.get("refreshed_at"),
        loading=cache.get("results") is None,
        canonical_url=f"{BASE_URL}/this-weekend",
    )
    return _cached_template("this_weekend.html", ctx, max_age=900, stale=1800)


# ---------------------------------------------------------------------------
# Sitemap — /sitemap.xml
# ---------------------------------------------------------------------------


@router.get("/sitemap.xml")
async def sitemap_xml(request: Request):
    registry = get_registry()
    all_cgs = registry.list_all()

    lines = ['<?xml version="1.0" encoding="UTF-8"?>']
    lines.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')

    # Static pages
    for path in ["/campgrounds", "/this-weekend", "/", "/map"]:
        lines.append(f"  <url><loc>{BASE_URL}{path}</loc></url>")

    # State index pages
    for state in sorted(VALID_STATES):
        lines.append(
            f"  <url><loc>{BASE_URL}/campgrounds/{state.lower()}</loc></url>"
        )

    # Tag pages
    for tag, _ in registry.get_all_tags():
        lines.append(f"  <url><loc>{BASE_URL}/tags/{tag}</loc></url>")

    # Campground profiles
    for cg in all_cgs:
        if cg.slug and cg.state:
            lines.append(
                f"  <url><loc>{BASE_URL}/campgrounds/"
                f"{cg.state.lower()}/{cg.slug}</loc></url>"
            )

    lines.append("</urlset>")
    return Response(
        content="\n".join(lines),
        media_type="application/xml",
    )


# ---------------------------------------------------------------------------
# robots.txt — /robots.txt
# ---------------------------------------------------------------------------


@router.get("/robots.txt")
async def robots_txt():
    content = (
        "User-agent: *\n"
        "Allow: /\n"
        f"Sitemap: {BASE_URL}/sitemap.xml\n"
    )
    return Response(content=content, media_type="text/plain")
