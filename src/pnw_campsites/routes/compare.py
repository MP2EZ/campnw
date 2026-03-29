"""Campground comparison route."""

from __future__ import annotations

import asyncio
import json
import os

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from pnw_campsites.routes.deps import get_registry

router = APIRouter(prefix="/api", tags=["compare"])


class CompareRequest(BaseModel):
    facility_ids: list[str] = Field(..., min_length=2, max_length=3)
    start_date: str = Field(default="", max_length=10)
    end_date: str = Field(default="", max_length=10)


@router.post("/compare")
async def compare_campgrounds(body: CompareRequest):
    registry = get_registry()

    campgrounds = []
    for fid in body.facility_ids:
        cg = registry.get_by_facility_id(fid)
        if not cg:
            raise HTTPException(status_code=404, detail=f"Campground {fid} not found")
        campgrounds.append({
            "facility_id": cg.facility_id,
            "name": cg.name,
            "state": cg.state,
            "booking_system": (
                cg.booking_system.value
                if hasattr(cg.booking_system, "value")
                else str(cg.booking_system)
            ),
            "tags": cg.tags or [],
            "vibe": cg.vibe or "",
            "elevator_pitch": cg.elevator_pitch or "",
            "drive_minutes": cg.drive_minutes_from_base,
            "total_sites": cg.total_sites,
            "latitude": cg.latitude,
            "longitude": cg.longitude,
        })

    # Generate narrative comparison via Haiku (optional)
    narrative = await _generate_narrative(campgrounds, body.start_date)

    return {
        "campgrounds": campgrounds,
        "narrative": narrative,
    }


async def _generate_narrative(
    campgrounds: list[dict], date_context: str,
) -> str | None:
    """Generate a Haiku comparison narrative. Returns None on failure."""
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        return None

    import anthropic

    client = anthropic.AsyncAnthropic(api_key=api_key)

    compact = json.dumps([
        {
            "name": c["name"], "state": c["state"],
            "tags": c["tags"][:5], "vibe": c["vibe"][:80],
            "drive": c["drive_minutes"], "sites": c["total_sites"],
        }
        for c in campgrounds
    ])

    prompt = (
        "Compare these campgrounds in 2-3 sentences. "
        "Highlight key tradeoffs (drive time, setting, amenities). "
        "Be specific and opinionated.\n\n"
        f"Campgrounds:\n{compact}\n"
        f"{'Dates: ' + date_context if date_context else ''}\n\n"
        "No preamble. Just the comparison."
    )

    try:
        response = await asyncio.wait_for(
            client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=200,
                messages=[{"role": "user", "content": prompt}],
            ),
            timeout=3.0,
        )
        return response.content[0].text.strip()
    except Exception:
        return None
