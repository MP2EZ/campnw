"""WA State Parks site/loop metadata, shipped as a JSON fixture.

GoingToCamp's WAF blocks Fly's egress IPs, so prod can't run the metadata
seeder (scripts/seed_wa_state_metadata.py). The seeder runs from a residential
IP and exports ``wa_state_sites`` + ``wa_state_loops`` to ``FIXTURE_PATH``;
``apply_wa_site_fixture`` imports it from ``CampgroundRegistry.__init__``, the
same idempotent-migration route as the curated tag overrides.

Rules:
- Upsert by ``map_id`` / ``resource_id``. Rows the fixture lacks are left alone.
- The fixture's sha256 is recorded in ``registry_meta``; an unchanged fixture
  costs one hash and one lookup per registry open.
- One row per line, sorted by park then id, so a re-seed diffs row by row.
  ``allowed_equipment`` is stored as ``[category, subcategory]`` pairs to keep
  the file small; the registry keeps GoingToCamp's dict form.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "wa_state_sites.json"
_META_KEY = "wa_site_fixture_sha256"

_LOOP_COLS = ("map_id", "park_facility_id", "title", "description")
_SITE_COLS = (
    "resource_id", "park_facility_id", "name", "loop_map_id",
    "max_capacity", "min_capacity", "allowed_equipment",
)


def export_wa_site_fixture(conn: sqlite3.Connection, path: Path | None = None) -> tuple[int, int]:
    """Write every WA loop and site row to the fixture. Returns (loops, sites)."""
    loops = _rows(conn, "wa_state_loops", _LOOP_COLS, "map_id")
    sites = _rows(conn, "wa_state_sites", _SITE_COLS, "resource_id")
    for site in sites:
        site["allowed_equipment"] = [
            [e["equipmentCategoryId"], e["subEquipmentCategoryId"]]
            for e in json.loads(site["allowed_equipment"] or "[]")
        ]
    body = ",\n".join(
        f'"{key}": [\n' + ",\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n]"
        for key, rows in (("loops", loops), ("sites", sites))
    )
    (path or FIXTURE_PATH).write_text("{\n" + body + "\n}\n")
    return len(loops), len(sites)


def _rows(conn: sqlite3.Connection, table: str, cols: tuple[str, ...], id_col: str) -> list[dict]:
    sql = f"SELECT {', '.join(cols)} FROM {table} ORDER BY park_facility_id, {id_col}"
    return [dict(zip(cols, row, strict=True)) for row in conn.execute(sql)]


def apply_wa_site_fixture(conn: sqlite3.Connection, path: Path | None = None) -> int:
    """Import the fixture if it changed since the last import. Returns sites upserted."""
    path = path or FIXTURE_PATH
    if not path.exists():
        return 0
    # Nothing to attach sites to yet (a fresh or test registry). Not recorded,
    # so the import runs on a later open once WA parks are seeded.
    if conn.execute(
        "SELECT 1 FROM campgrounds WHERE booking_system='wa_state' LIMIT 1"
    ).fetchone() is None:
        return 0
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    row = conn.execute("SELECT value FROM registry_meta WHERE key=?", (_META_KEY,)).fetchone()
    if row is not None and row[0] == digest:
        return 0

    data = json.loads(raw)
    now = datetime.now().isoformat()
    conn.executemany(
        """\
        INSERT INTO wa_state_loops (map_id, park_facility_id, title, description, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(map_id) DO UPDATE SET
            park_facility_id=excluded.park_facility_id, title=excluded.title,
            description=excluded.description, updated_at=excluded.updated_at
        """,
        [(*(loop[c] for c in _LOOP_COLS), now) for loop in data["loops"]],
    )
    conn.executemany(
        """\
        INSERT INTO wa_state_sites (resource_id, park_facility_id, name, loop_map_id,
            max_capacity, min_capacity, allowed_equipment, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(resource_id) DO UPDATE SET
            park_facility_id=excluded.park_facility_id, name=excluded.name,
            loop_map_id=excluded.loop_map_id, max_capacity=excluded.max_capacity,
            min_capacity=excluded.min_capacity,
            allowed_equipment=excluded.allowed_equipment, updated_at=excluded.updated_at
        """,
        [
            (
                *(site[c] for c in _SITE_COLS[:-1]),
                json.dumps([
                    {"equipmentCategoryId": cat, "subEquipmentCategoryId": sub}
                    for cat, sub in site["allowed_equipment"]
                ]),
                now,
            )
            for site in data["sites"]
        ],
    )
    conn.execute(
        "INSERT INTO registry_meta (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (_META_KEY, digest),
    )
    conn.commit()
    logger.info(
        "Imported WA site fixture: %d sites, %d loops", len(data["sites"]), len(data["loops"]),
    )
    return len(data["sites"])
