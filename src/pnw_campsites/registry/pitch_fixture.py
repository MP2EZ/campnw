"""LLM-written campground copy (pitch, description, best-for), shipped as a fixture.

Prod's registry.db lives on a Fly volume that is never re-seeded from the image,
so regenerating copy locally changes nothing in prod. ``enrich --only-pitch``
exports ``elevator_pitch``, ``description_rewrite`` and ``best_for`` to
``FIXTURE_PATH``; ``apply_pitch_fixture`` imports it from
``CampgroundRegistry.__init__``, the same route as the WA site fixture.

Rules:
- Keyed by ``(booking_system, facility_id)``. Rows the registry lacks are skipped;
  campgrounds the fixture lacks are left alone.
- The fixture's sha256 is recorded in ``registry_meta``; an unchanged fixture
  costs one hash and one lookup per registry open, and local edits made after
  an import survive until the fixture changes.
- One row per line, sorted by booking system then facility id, so a regen diffs
  row by row.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "campground_pitches.json"
_META_KEY = "pitch_fixture_sha256"
_COLS = ("booking_system", "facility_id", "elevator_pitch", "description_rewrite", "best_for")


def export_pitch_fixture(conn: sqlite3.Connection, path: Path | None = None) -> int:
    """Write every campground with a pitch to the fixture. Returns rows written."""
    rows = [
        dict(zip(_COLS, row, strict=True))
        for row in conn.execute(
            f"SELECT {', '.join(_COLS)} FROM campgrounds WHERE elevator_pitch != '' "
            "ORDER BY booking_system, facility_id"
        )
    ]
    body = ",\n".join(json.dumps(r, ensure_ascii=False) for r in rows)
    (path or FIXTURE_PATH).write_text('{"pitches": [\n' + body + "\n]}\n")
    return len(rows)


def apply_pitch_fixture(conn: sqlite3.Connection, path: Path | None = None) -> int:
    """Import the fixture if it changed since the last import. Returns rows updated."""
    path = path or FIXTURE_PATH
    if not path.exists():
        return 0
    # Nothing to attach copy to yet (a fresh or test registry). Not recorded,
    # so the import runs on a later open once campgrounds are seeded.
    if conn.execute("SELECT 1 FROM campgrounds LIMIT 1").fetchone() is None:
        return 0
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    row = conn.execute("SELECT value FROM registry_meta WHERE key=?", (_META_KEY,)).fetchone()
    if row is not None and row[0] == digest:
        return 0

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
    conn.execute(
        "INSERT INTO registry_meta (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (_META_KEY, digest),
    )
    conn.commit()
    logger.info("Imported pitch fixture: %d of %d campgrounds updated", updated, len(rows))
    return updated
