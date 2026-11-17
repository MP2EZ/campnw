"""Hash gate shared by the registry's JSON fixture imports."""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path


def fixture_changed(
    conn: sqlite3.Connection, path: Path, meta_key: str, target_sql: str,
) -> tuple[bytes, str] | None:
    """The fixture's (bytes, sha256) if it needs importing, else None.

    None when the file is missing, when `target_sql` finds no row to attach the
    fixture to (a fresh or test registry; not recorded, so the import runs on a
    later open once rows are seeded), or when its hash matches the last import.
    """
    if not path.exists():
        return None
    if conn.execute(target_sql).fetchone() is None:
        return None
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    row = conn.execute("SELECT value FROM registry_meta WHERE key=?", (meta_key,)).fetchone()
    if row is not None and row[0] == digest:
        return None
    return raw, digest


def record_fixture(conn: sqlite3.Connection, meta_key: str, digest: str) -> None:
    conn.execute(
        "INSERT INTO registry_meta (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (meta_key, digest),
    )
