"""SQLite-backed watch state for campground monitoring."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

_docker_db = Path("/app/data/watches.db")
_local_db = Path(__file__).resolve().parents[3] / "data" / "watches.db"
DEFAULT_DB_PATH = _docker_db if _docker_db.parent.exists() else _local_db

SCHEMA = """\
CREATE TABLE IF NOT EXISTS watches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    facility_id TEXT NOT NULL,
    name TEXT NOT NULL DEFAULT '',
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    min_nights INTEGER DEFAULT 1,
    days_of_week TEXT,           -- JSON array of ints, null means all days
    notify_topic TEXT DEFAULT '', -- ntfy topic or Pushover key
    session_token TEXT DEFAULT '',  -- anonymous ownership token
    enabled INTEGER DEFAULT 1,
    created_at TEXT,
    UNIQUE(facility_id, start_date, end_date)
);

CREATE TABLE IF NOT EXISTS snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    watch_id INTEGER NOT NULL REFERENCES watches(id) ON DELETE CASCADE,
    polled_at TEXT NOT NULL,
    available_sites TEXT NOT NULL DEFAULT '{}',  -- JSON: {site_id: [dates]}
    UNIQUE(watch_id, polled_at)
);

CREATE INDEX IF NOT EXISTS idx_snapshots_watch ON snapshots(watch_id);
"""


@dataclass
class Watch:
    """A watched campground + date range."""

    id: int | None = None
    facility_id: str = ""
    name: str = ""
    start_date: str = ""  # YYYY-MM-DD
    end_date: str = ""  # YYYY-MM-DD
    min_nights: int = 1
    days_of_week: list[int] | None = None
    notify_topic: str = ""
    session_token: str = ""
    enabled: bool = True
    created_at: str = ""


@dataclass
class Snapshot:
    """A point-in-time availability snapshot for a watch."""

    watch_id: int
    polled_at: str
    available_sites: dict[str, list[str]] = field(
        default_factory=dict
    )  # site_id -> [available dates]


class WatchDB:
    """CRUD for watch state."""

    def __init__(self, db_path: Path | str = DEFAULT_DB_PATH) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(SCHEMA)

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> WatchDB:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -------------------------------------------------------------------
    # Watches
    # -------------------------------------------------------------------

    def add_watch(self, watch: Watch) -> Watch:
        """Add a new watch. Returns it with its id."""
        now = datetime.now().isoformat()
        self._conn.execute(
            """\
            INSERT INTO watches
                (facility_id, name, start_date, end_date, min_nights,
                 days_of_week, notify_topic, session_token, enabled, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                watch.facility_id,
                watch.name,
                watch.start_date,
                watch.end_date,
                watch.min_nights,
                json.dumps(watch.days_of_week) if watch.days_of_week else None,
                watch.notify_topic,
                watch.session_token,
                int(watch.enabled),
                now,
            ),
        )
        self._conn.commit()
        watch.id = self._conn.execute(
            "SELECT last_insert_rowid()"
        ).fetchone()[0]
        watch.created_at = now
        return watch

    def remove_watch(self, watch_id: int) -> bool:
        """Remove a watch and its snapshots. Returns True if it existed."""
        cursor = self._conn.execute(
            "DELETE FROM watches WHERE id=?", (watch_id,)
        )
        self._conn.commit()
        return cursor.rowcount > 0

    def list_watches(self, *, enabled_only: bool = True) -> list[Watch]:
        where = "enabled = 1" if enabled_only else "1=1"
        rows = self._conn.execute(
            f"SELECT * FROM watches WHERE {where} ORDER BY created_at"
        ).fetchall()
        return [self._row_to_watch(r) for r in rows]

    def get_watch(self, watch_id: int) -> Watch | None:
        row = self._conn.execute(
            "SELECT * FROM watches WHERE id=?", (watch_id,)
        ).fetchone()
        return self._row_to_watch(row) if row else None

    def _row_to_watch(self, row: sqlite3.Row) -> Watch:
        d = dict(row)
        d["enabled"] = bool(d["enabled"])
        d["days_of_week"] = (
            json.loads(d["days_of_week"]) if d["days_of_week"] else None
        )
        return Watch(**d)

    def list_watches_by_session(self, session_token: str) -> list[Watch]:
        """List watches owned by a session token."""
        rows = self._conn.execute(
            "SELECT * FROM watches WHERE session_token=? ORDER BY created_at DESC",
            (session_token,),
        ).fetchall()
        return [self._row_to_watch(r) for r in rows]

    def toggle_enabled(self, watch_id: int, session_token: str) -> bool:
        """Toggle a watch's enabled state. Returns new state, or None if not found."""
        row = self._conn.execute(
            "SELECT enabled FROM watches WHERE id=? AND session_token=?",
            (watch_id, session_token),
        ).fetchone()
        if not row:
            return False
        new_state = not bool(row[0])
        self._conn.execute(
            "UPDATE watches SET enabled=? WHERE id=?",
            (int(new_state), watch_id),
        )
        self._conn.commit()
        return new_state

    # -------------------------------------------------------------------
    # Snapshots
    # -------------------------------------------------------------------

    def save_snapshot(self, snapshot: Snapshot) -> None:
        """Save an availability snapshot for a watch."""
        self._conn.execute(
            """\
            INSERT OR REPLACE INTO snapshots (watch_id, polled_at, available_sites)
            VALUES (?, ?, ?)
            """,
            (
                snapshot.watch_id,
                snapshot.polled_at,
                json.dumps(snapshot.available_sites),
            ),
        )
        self._conn.commit()

    def get_latest_snapshot(self, watch_id: int) -> Snapshot | None:
        """Get the most recent snapshot for a watch."""
        row = self._conn.execute(
            """\
            SELECT * FROM snapshots
            WHERE watch_id=?
            ORDER BY polled_at DESC LIMIT 1
            """,
            (watch_id,),
        ).fetchone()
        if not row:
            return None
        return Snapshot(
            watch_id=row["watch_id"],
            polled_at=row["polled_at"],
            available_sites=json.loads(row["available_sites"]),
        )
