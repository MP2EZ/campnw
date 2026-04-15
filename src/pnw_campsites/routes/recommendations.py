"""Recommendation and search history routes."""

from __future__ import annotations

import json

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from pnw_campsites.routes.deps import (
    get_current_user,
    get_registry,
    get_watch_db,
)

router = APIRouter(prefix="/api", tags=["recommendations"])

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class SaveSearchRequest(BaseModel):
    params: dict
    result_count: int = Field(default=0, ge=0)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _enhance_rec_reasons(
    results: list[dict],
    affinities: dict,
    posthog_distinct_id: str | None = None,
) -> list[str] | None:
    """Generate personalized recommendation reasons via Haiku batch call."""
    import asyncio
    import os

    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        return None

    from pnw_campsites.posthog_client import get_posthog_client

    try:
        from posthog.ai.anthropic import AsyncAnthropic
        client = AsyncAnthropic(api_key=api_key, posthog_client=get_posthog_client())
    except (ImportError, ValueError):
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=api_key)

    top_tags = sorted(
        affinities["tags"].items(), key=lambda x: -x[1],
    )[:5]
    top_states = sorted(
        affinities["states"].items(), key=lambda x: -x[1],
    )[:3]

    recs_summary = json.dumps([
        {"name": r["name"], "state": r["state"], "tags": r["tags"][:3],
         "vibe": r.get("vibe", "")[:60]}
        for r in results
    ])

    prompt = (
        "Generate a brief personalized recommendation reason (1 sentence, "
        "max 80 chars) for each campground. The user tends to search for "
        f"{', '.join(t for t, _ in top_tags)} in "
        f"{', '.join(s for s, _ in top_states)}.\n\n"
        f"Campgrounds:\n{recs_summary}\n\n"
        "Return a JSON array of strings, one reason per campground, same "
        "order. Reference specific campground attributes. No preamble."
    )

    try:
        response = await asyncio.wait_for(
            client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=400,
                messages=[{"role": "user", "content": prompt}],
                posthog_distinct_id=posthog_distinct_id,
                posthog_privacy_mode=True,
            ),
            timeout=2.0,
        )
        text = response.content[0].text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        reasons = json.loads(text)
        if isinstance(reasons, list) and len(reasons) == len(results):
            return [r[:80] for r in reasons]
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/recommendations")
async def recommendations(request: Request):
    """Personalized campground recommendations based on search history."""
    db = get_watch_db()
    registry = get_registry()
    user_id = get_current_user(request)
    if not user_id:
        return []

    user = db.get_user_by_id(user_id)
    if not user or not user.recommendations_enabled:
        return []

    affinities = db.get_recommendation_affinities(user_id)
    if not affinities["tags"] and not affinities["states"]:
        return []

    # Score registry campgrounds against user affinities
    top_states = sorted(
        affinities["states"].items(), key=lambda x: x[1], reverse=True,
    )
    target_states = [s for s, _ in top_states[:2]] if top_states else None

    candidates = registry.search(
        state=target_states[0] if target_states and len(target_states) == 1 else None,
    )

    watched = affinities["watched_facility_ids"]
    tag_scores = affinities["tags"]
    state_scores = affinities["states"]

    scored = []
    for cg in candidates:
        if cg.facility_id in watched:
            continue

        # Tag overlap score
        tag_overlap = sum(
            tag_scores.get(t, 0) for t in (cg.tags or [])
        )
        # State match score
        state_match = state_scores.get(cg.state, 0)

        score = tag_overlap * 2 + state_match
        if score <= 0:
            continue

        # Build reason string from strongest signal
        top_tag = max(
            ((t, tag_scores.get(t, 0)) for t in (cg.tags or []) if t in tag_scores),
            key=lambda x: x[1],
            default=None,
        )
        if top_tag:
            reason = f"Based on your {top_tag[0]} searches"
            if cg.state in state_scores:
                reason += f" in {cg.state}"
        elif cg.state in state_scores:
            reason = f"Popular in {cg.state}, near your usual searches"
        else:
            reason = "You might like this"

        scored.append({
            "facility_id": cg.facility_id,
            "name": cg.name,
            "booking_system": (
                cg.booking_system.value
                if hasattr(cg.booking_system, "value")
                else str(cg.booking_system)
            ),
            "state": cg.state,
            "tags": cg.tags or [],
            "vibe": cg.vibe or "",
            "reason": reason,
            "score": score,
        })

    scored.sort(key=lambda x: x["score"], reverse=True)
    results = scored[:5]
    # Strip internal score from response
    for r in results:
        del r["score"]

    # Enhance reasons with LLM if user has enough search history
    if results and len(affinities["tags"]) >= 3:
        try:
            enhanced = await _enhance_rec_reasons(
                results, affinities, posthog_distinct_id=str(user_id),
            )
            if enhanced:
                for r, reason in zip(results, enhanced, strict=False):
                    if reason:
                        r["reason"] = reason
        except Exception:
            pass  # Keep template reasons on failure

    return results


@router.get("/search-history")
async def search_history(request: Request):
    db = get_watch_db()
    user_id = get_current_user(request)
    if not user_id:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Not authenticated")
    return db.get_search_history(user_id)


@router.post("/search-history")
async def save_search(body: SaveSearchRequest, request: Request):
    db = get_watch_db()
    user_id = get_current_user(request)
    if not user_id:
        return {"ok": False}
    db.save_search(user_id, json.dumps(body.params), body.result_count)
    return {"ok": True}
