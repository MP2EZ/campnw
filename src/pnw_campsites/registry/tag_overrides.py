"""Reviewed tag corrections, applied to the registry every time it opens.

Prod's registry.db lives on a Fly volume that is never re-seeded from the image,
so editing data/registry.db changes nothing in prod. Data fixes ship as code:
``apply_tag_overrides`` is an idempotent migration run from
``CampgroundRegistry.__init__``.

Rules:
- Keyed by ``(booking_system, facility_id)``. Only the listed tags move; every
  other tag (including ones enrichment adds later) is left alone.
- Add tags append; remove tags drop. Nothing is written when tags already match.
- Every entry needs evidence from the campground's own description (or, where the
  registry text is silent, the managing agency's page). Don't add a row on a hunch.
"""

from __future__ import annotations

import json
import logging
import sqlite3

logger = logging.getLogger(__name__)

TagChange = dict[str, list[str]]

# Reachable only by private boat or kayak: no road, no ferry. ``boat-launch`` means
# a ramp and ``walk-in`` means a hike from a car; neither fits these.
_BOAT_IN: dict[tuple[str, str], TagChange] = {
    # Registry: "reachable only [by] boat", "accessible only by boat".
    ("wa_state", "-2147483640"): {"add": ["boat-in"]},  # Blake Island
    # Registry: 1-acre marine park, "part of the Cascadia Marine Trail" (kayak camp).
    ("wa_state", "-2147483476"): {"add": ["boat-in"]},  # Posey Island
    # Registry text is silent; parks.wa.gov: "boat-in only", no road access.
    ("wa_state", "-2147483518"): {"add": ["boat-in"]},  # Hope Island (Mason)
    # Registry text is silent; BLM/WA State Parks: no ferry, "Boat-in Only".
    ("recgov", "255186"): {"add": ["boat-in"]},  # Patos Island
    # Registry text is silent; WA State Parks/BLM: 3-acre island, reachable only by boat.
    ("recgov", "255185"): {"add": ["boat-in"]},  # Blind Island
    # Registry: "accessible only by boat".
    ("recgov", "233263"): {"add": ["boat-in"]},  # Bartoo Island Boat-In (ID)
    ("recgov", "233264"): {"add": ["boat-in"]},  # Kalispell Island Boat-In (ID)
    ("recgov", "233431"): {"add": ["boat-in"]},  # Boat-In Sites, Lake Sonoma (CA)
    # Name says boat-in; USACE: New Hogan Lake's only boat-access camp, "only way in is
    # by boat".
    ("recgov", "270421"): {"add": ["boat-in"]},  # Deer Flat Boat In (CA)
}

# ``beach`` reads as saltwater sand. These parks sit on a river and their
# descriptions mention no beach, only "freshwater shoreline on the <X> River".
# Lake parks are deliberately not listed: a lake beach is a real beach.
_RIVER_NOT_BEACH: dict[tuple[str, str], TagChange] = {
    key: {"remove": ["beach"], "add": ["riverside"]}
    for key in (
        ("wa_state", "-2147483644"),  # Beacon Rock: Columbia River
        ("wa_state", "-2147483626"),  # Daroga: Columbia River
        ("wa_state", "-2147483601"),  # Kanaskat-Palmer: Green River
        ("wa_state", "-2147483591"),  # Lewis and Clark Trail (SE WA): Touchet River
        ("wa_state", "-2147483576"),  # Paradise Point: Lewis River
        ("wa_state", "-2147483568"),  # Rainbow Falls: Chehalis River
        ("wa_state", "-2147483567"),  # Rasar: Skagit River
        ("wa_state", "-2147483559"),  # Schafer: Satsop River
        ("wa_state", "-2147483545"),  # Wallace Falls: Wallace River, no beach named
    )
}

TAG_OVERRIDES: dict[tuple[str, str], TagChange] = {**_BOAT_IN, **_RIVER_NOT_BEACH}


def apply_tag_overrides(conn: sqlite3.Connection) -> int:
    """Apply ``TAG_OVERRIDES`` to ``conn``. Returns the number of rows changed."""
    changed = 0
    for (booking_system, facility_id), change in TAG_OVERRIDES.items():
        row = conn.execute(
            "SELECT id, tags FROM campgrounds WHERE booking_system=? AND facility_id=?",
            (booking_system, facility_id),
        ).fetchone()
        if row is None:
            continue
        current = json.loads(row[1]) if row[1] else []
        remove = set(change.get("remove", []))
        wanted = [t for t in current if t not in remove]
        wanted += [
            t for t in change.get("add", []) if t not in wanted
        ]
        if wanted == current:
            continue
        conn.execute(
            "UPDATE campgrounds SET tags=? WHERE id=?", (json.dumps(wanted), row[0]),
        )
        changed += 1
    if changed:
        conn.commit()
        logger.info("Applied curated tag overrides to %d campgrounds", changed)
    return changed
