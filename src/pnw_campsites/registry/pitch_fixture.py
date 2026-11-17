"""LLM-written campground copy (pitch, description, best-for), shipped as a fixture.

Prod's registry.db lives on a Fly volume that is never re-seeded from the image,
so regenerating copy locally changes nothing in prod. ``enrich --only-pitch``
exports ``elevator_pitch``, ``description_rewrite`` and ``best_for`` to
``FIXTURE_PATH``; ``apply_pitch_fixture`` imports it from
``CampgroundRegistry.__init__``, the same route as the WA site fixture.

Rules:
- Keyed by ``(booking_system, facility_id)``. Rows the registry lacks are skipped;
  campgrounds the fixture lacks are left alone. An empty field clears the copy.
- The fixture's sha256 is recorded in ``registry_meta``; an unchanged fixture
  costs one hash and one lookup per registry open, and local edits made after
  an import survive until the fixture changes.
- One row per line, sorted by booking system then facility id, so a regen diffs
  row by row.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path

from pnw_campsites.registry.fixture_meta import fixture_changed, record_fixture

logger = logging.getLogger(__name__)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "campground_pitches.json"
_META_KEY = "pitch_fixture_sha256"
_COLS = ("booking_system", "facility_id", "elevator_pitch", "description_rewrite", "best_for")


def export_pitch_fixture(conn: sqlite3.Connection, path: Path | None = None) -> int:
    """Write every campground's copy to the fixture, empty copy included, so
    an import clears copy the regen dropped. Returns rows written."""
    rows = [
        dict(zip(_COLS, row, strict=True))
        for row in conn.execute(
            f"SELECT {', '.join(_COLS)} FROM campgrounds "
            "ORDER BY booking_system, facility_id"
        )
    ]
    body = ",\n".join(json.dumps(r, ensure_ascii=False) for r in rows)
    (path or FIXTURE_PATH).write_text('{"pitches": [\n' + body + "\n]}\n")
    return len(rows)


def apply_pitch_fixture(conn: sqlite3.Connection, path: Path | None = None) -> int:
    """Import the fixture if it changed since the last import. Returns rows updated."""
    changed = fixture_changed(
        conn, path or FIXTURE_PATH, _META_KEY, "SELECT 1 FROM campgrounds LIMIT 1",
    )
    if changed is None:
        return 0
    raw, digest = changed

    rows = json.loads(raw)["pitches"]
    now = datetime.now().isoformat()
    updated = 0
    for r in rows:
        cur = conn.execute(
            """\
            UPDATE campgrounds SET elevator_pitch=?, description_rewrite=?, best_for=?,
                updated_at=?
            WHERE booking_system=? AND facility_id=?
              AND (elevator_pitch IS NOT ? OR description_rewrite IS NOT ?
                   OR best_for IS NOT ?)
            """,
            (
                r["elevator_pitch"], r["description_rewrite"], r["best_for"], now,
                r["booking_system"], r["facility_id"],
                r["elevator_pitch"], r["description_rewrite"], r["best_for"],
            ),
        )
        updated += cur.rowcount
    record_fixture(conn, _META_KEY, digest)
    conn.commit()
    logger.info("Imported pitch fixture: %d of %d campgrounds updated", updated, len(rows))
    return updated
