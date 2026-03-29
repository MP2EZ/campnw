"""SQLite-backed watch state for campground monitoring."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta
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
    user_id INTEGER,
    enabled INTEGER DEFAULT 1,
    created_at TEXT
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
    user_id: int | None = None
    notification_channel: str = ""  # ntfy, pushover, web_push, or ""
    enabled: bool = True
    created_at: str = ""
    trip_id: int | None = None
    watch_type: str = "single"  # "single" or "template"
    search_params: str = ""  # JSON search pattern for template watches


@dataclass
class User:
    """A registered user."""

    id: int | None = None
    email: str = ""
    password_hash: str = ""
    display_name: str = ""
    home_base: str = ""
    default_state: str = ""
    default_nights: int = 2
    default_from: str = ""
    recommendations_enabled: bool = False
    preferred_tags: list[str] | None = None
    onboarding_complete: bool = False
    created_at: str = ""
    last_login_at: str | None = None


@dataclass
class Snapshot:
    """A point-in-time availability snapshot for a watch."""

    watch_id: int
    polled_at: str
    available_sites: dict[str, list[str]] = field(
        default_factory=dict
    )  # site_id -> [available dates]


@dataclass
class Trip:
    """A trip grouping campgrounds together."""

    id: int | None = None
    user_id: int | None = None
    name: str = ""
    start_date: str = ""
    end_date: str = ""
    notes: str = ""
    created_at: str = ""
    updated_at: str = ""


@dataclass
class TripCampground:
    """A campground associated with a trip."""

    id: int | None = None
    trip_id: int | None = None
    facility_id: str = ""
    source: str = "recgov"
    name: str = ""
    sort_order: int = 0
    notes: str = ""
    added_at: str = ""


@dataclass
class SharedLink:
    """A shareable link for a watch or trip."""

    id: int | None = None
    uuid: str = ""
    watch_id: int | None = None
    trip_id: int | None = None
    created_by: int | None = None
    expires_at: str = ""
    revoked: bool = False
    created_at: str = ""


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
        self._migrate()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> WatchDB:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _migrate(self) -> None:
        """Run schema migrations for columns/tables added after initial release."""
        cols = [r[1] for r in self._conn.execute("PRAGMA table_info(watches)")]
        if "session_token" not in cols:
            self._conn.execute(
                'ALTER TABLE watches ADD COLUMN session_token TEXT DEFAULT ""'
            )
        if "user_id" not in cols:
            self._conn.execute(
                "ALTER TABLE watches"
                " ADD COLUMN user_id INTEGER"
            )
        # Drop UNIQUE(facility_id, start_date, end_date) — now per-user
        table_sql = self._conn.execute(
            "SELECT sql FROM sqlite_master"
            " WHERE type='table' AND name='watches'"
        ).fetchone()
        if table_sql and "UNIQUE" in table_sql[0]:
            self._conn.executescript("""\
                CREATE TABLE watches_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    facility_id TEXT NOT NULL,
                    name TEXT NOT NULL DEFAULT '',
                    start_date TEXT NOT NULL,
                    end_date TEXT NOT NULL,
                    min_nights INTEGER DEFAULT 1,
                    days_of_week TEXT,
                    notify_topic TEXT DEFAULT '',
                    session_token TEXT DEFAULT '',
                    user_id INTEGER,
                    enabled INTEGER DEFAULT 1,
                    created_at TEXT
                );
                INSERT INTO watches_new
                    SELECT id, facility_id, name, start_date,
                           end_date, min_nights, days_of_week,
                           notify_topic, session_token, user_id,
                           enabled, created_at
                    FROM watches;
                DROP TABLE watches;
                ALTER TABLE watches_new RENAME TO watches;
            """)
        # Users table
        self._conn.executescript("""\
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                display_name TEXT DEFAULT '',
                home_base TEXT DEFAULT '',
                default_state TEXT DEFAULT '',
                default_nights INTEGER DEFAULT 2,
                default_from TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                last_login_at TEXT
            );
            CREATE TABLE IF NOT EXISTS search_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                params TEXT NOT NULL,
                result_count INTEGER DEFAULT 0,
                searched_at TEXT NOT NULL
            );
        """)
        # v0.5 tables: cache, history, notification log
        self._conn.executescript("""\
            CREATE TABLE IF NOT EXISTS availability_cache (
                campground_id TEXT NOT NULL,
                month TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'recgov',
                payload TEXT NOT NULL,
                cached_at TEXT NOT NULL,
                PRIMARY KEY (campground_id, month, source)
            );
            CREATE TABLE IF NOT EXISTS availability_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                campground_id TEXT NOT NULL,
                site_id TEXT NOT NULL,
                date TEXT NOT NULL,
                status TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'recgov',
                observed_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_avail_hist_lookup
                ON availability_history(campground_id, date);
            CREATE TABLE IF NOT EXISTS notification_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                watch_id INTEGER REFERENCES watches(id)
                    ON DELETE CASCADE,
                channel TEXT NOT NULL,
                status TEXT NOT NULL,
                changes_count INTEGER DEFAULT 0,
                sent_at TEXT NOT NULL
            );
        """)
        # v0.5 watch column: notification_channel
        watch_cols = [
            r[1] for r in self._conn.execute(
                "PRAGMA table_info(watches)"
            )
        ]
        if "notification_channel" not in watch_cols:
            self._conn.execute(
                "ALTER TABLE watches ADD COLUMN"
                " notification_channel TEXT DEFAULT ''"
            )
        # v0.5 push subscriptions table
        self._conn.executescript("""\
            CREATE TABLE IF NOT EXISTS push_subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                session_token TEXT DEFAULT '',
                endpoint TEXT NOT NULL UNIQUE,
                p256dh TEXT NOT NULL,
                auth TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
        """)
        # v1.0: recommendations opt-in flag
        user_cols = [
            r[1] for r in self._conn.execute("PRAGMA table_info(users)")
        ]
        if "recommendations_enabled" not in user_cols:
            self._conn.execute(
                "ALTER TABLE users ADD COLUMN"
                " recommendations_enabled INTEGER DEFAULT 0"
            )
        if "preferred_tags" not in user_cols:
            self._conn.execute(
                "ALTER TABLE users ADD COLUMN"
                " preferred_tags TEXT DEFAULT '[]'"
            )
        if "onboarding_complete" not in user_cols:
            self._conn.execute(
                "ALTER TABLE users ADD COLUMN"
                " onboarding_complete INTEGER DEFAULT 0"
            )
        # v1.2: trips
        self._conn.executescript("""\
            CREATE TABLE IF NOT EXISTS trips (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                name TEXT NOT NULL DEFAULT '',
                start_date TEXT DEFAULT '',
                end_date TEXT DEFAULT '',
                notes TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_trips_user ON trips(user_id);
            CREATE TABLE IF NOT EXISTS trip_campgrounds (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trip_id INTEGER NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
                facility_id TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'recgov',
                name TEXT NOT NULL DEFAULT '',
                sort_order INTEGER DEFAULT 0,
                notes TEXT DEFAULT '',
                added_at TEXT NOT NULL,
                UNIQUE(trip_id, facility_id, source)
            );
        """)
        # v1.2: link watches to trips
        watch_cols2 = [
            r[1] for r in self._conn.execute("PRAGMA table_info(watches)")
        ]
        if "trip_id" not in watch_cols2:
            self._conn.execute(
                "ALTER TABLE watches ADD COLUMN trip_id INTEGER"
            )
        # v1.2: shared links
        self._conn.executescript("""\
            CREATE TABLE IF NOT EXISTS shared_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                uuid TEXT NOT NULL UNIQUE,
                watch_id INTEGER REFERENCES watches(id) ON DELETE CASCADE,
                trip_id INTEGER REFERENCES trips(id) ON DELETE CASCADE,
                created_by INTEGER NOT NULL REFERENCES users(id),
                expires_at TEXT NOT NULL,
                revoked INTEGER DEFAULT 0,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_shared_uuid ON shared_links(uuid);
        """)
        self._conn.commit()

        # v1.2: template watches
        watch_cols3 = [
            r[1] for r in self._conn.execute("PRAGMA table_info(watches)")
        ]
        if "watch_type" not in watch_cols3:
            self._conn.execute(
                "ALTER TABLE watches ADD COLUMN"
                " watch_type TEXT DEFAULT 'single'"
            )
        if "search_params" not in watch_cols3:
            self._conn.execute(
                "ALTER TABLE watches ADD COLUMN"
                " search_params TEXT DEFAULT ''"
            )
        self._conn.commit()

    # -------------------------------------------------------------------
    # Availability cache
    # -------------------------------------------------------------------

    _CACHE_TTL_SECONDS = 600  # 10 minutes

    def get_cached_availability(
        self, campground_id: str, month: str, source: str = "recgov",
    ) -> str | None:
        """Return cached JSON payload if fresh, None if expired."""
        row = self._conn.execute(
            "SELECT payload, cached_at FROM availability_cache"
            " WHERE campground_id=? AND month=? AND source=?",
            (campground_id, month, source),
        ).fetchone()
        if not row:
            return None
        cached_at = datetime.fromisoformat(row["cached_at"])
        age = (datetime.now() - cached_at).total_seconds()
        if age > self._CACHE_TTL_SECONDS:
            return None
        return row["payload"]

    def set_cached_availability(
        self, campground_id: str, month: str,
        payload: str, source: str = "recgov",
    ) -> None:
        now = datetime.now().isoformat()
        self._conn.execute(
            "INSERT OR REPLACE INTO availability_cache"
            " (campground_id, month, source, payload, cached_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (campground_id, month, source, payload, now),
        )
        self._conn.commit()

    def clear_expired_cache(self) -> int:
        """Remove stale cache entries. Returns count removed."""
        cutoff = datetime.now().isoformat()
        # SQLite datetime comparison works on ISO strings
        cursor = self._conn.execute(
            "DELETE FROM availability_cache"
            " WHERE datetime(cached_at, '+10 minutes') < datetime(?)",
            (cutoff,),
        )
        self._conn.commit()
        return cursor.rowcount

    # -------------------------------------------------------------------
    # Availability history
    # -------------------------------------------------------------------

    def record_availability_history(
        self,
        campground_id: str,
        records: list[tuple[str, str, str]],
        source: str = "recgov",
    ) -> None:
        """Batch-insert availability observations.

        records: list of (site_id, date, status) tuples.
        """
        now = datetime.now().isoformat()
        self._conn.executemany(
            "INSERT INTO availability_history"
            " (campground_id, site_id, date, status, source,"
            " observed_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            [
                (campground_id, sid, dt, st, source, now)
                for sid, dt, st in records
            ],
        )
        self._conn.commit()

    # -------------------------------------------------------------------
    # Notification log
    # -------------------------------------------------------------------

    def log_notification(
        self, watch_id: int, channel: str,
        status: str, changes_count: int = 0,
    ) -> None:
        now = datetime.now().isoformat()
        self._conn.execute(
            "INSERT INTO notification_log"
            " (watch_id, channel, status, changes_count, sent_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (watch_id, channel, status, changes_count, now),
        )
        self._conn.commit()

    def get_recent_notifications(
        self, limit: int = 10,
    ) -> list[dict]:
        rows = self._conn.execute(
            "SELECT n.*, w.name as watch_name"
            " FROM notification_log n"
            " LEFT JOIN watches w ON n.watch_id = w.id"
            " ORDER BY n.sent_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    # -------------------------------------------------------------------
    # Push subscriptions
    # -------------------------------------------------------------------

    def save_push_subscription(
        self,
        user_id: int | None,
        session_token: str,
        endpoint: str,
        p256dh: str,
        auth: str,
    ) -> None:
        """Upsert a web push subscription."""
        now = datetime.now().isoformat()
        self._conn.execute(
            "INSERT OR REPLACE INTO push_subscriptions"
            " (user_id, session_token, endpoint, p256dh, auth, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, session_token, endpoint, p256dh, auth, now),
        )
        self._conn.commit()

    def get_push_subscriptions_for_user(self, user_id: int) -> list[dict]:
        """Return all active push subscriptions for a user."""
        rows = self._conn.execute(
            "SELECT endpoint, p256dh, auth FROM push_subscriptions"
            " WHERE user_id=?",
            (user_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def delete_push_subscription(self, endpoint: str) -> None:
        """Remove a push subscription (e.g. after 404/410 from push service)."""
        self._conn.execute(
            "DELETE FROM push_subscriptions WHERE endpoint=?",
            (endpoint,),
        )
        self._conn.commit()

    def delete_push_subscription_scoped(
        self,
        endpoint: str,
        user_id: int | None = None,
        session_token: str = "",
    ) -> None:
        """Remove a push subscription only if owned by user/session."""
        if user_id:
            self._conn.execute(
                "DELETE FROM push_subscriptions"
                " WHERE endpoint=? AND user_id=?",
                (endpoint, user_id),
            )
        elif session_token:
            self._conn.execute(
                "DELETE FROM push_subscriptions"
                " WHERE endpoint=? AND session_token=?",
                (endpoint, session_token),
            )
        self._conn.commit()

    # -------------------------------------------------------------------
    # Users
    # -------------------------------------------------------------------

    def create_user(self, user: User) -> User:
        now = datetime.now().isoformat()
        self._conn.execute(
            """\
            INSERT INTO users
                (email, password_hash, display_name, home_base,
                 default_state, default_nights, default_from, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user.email,
                user.password_hash,
                user.display_name,
                user.home_base,
                user.default_state,
                user.default_nights,
                user.default_from,
                now,
            ),
        )
        self._conn.commit()
        user.id = self._conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        user.created_at = now
        return user

    def get_user_by_email(self, email: str) -> User | None:
        row = self._conn.execute(
            "SELECT * FROM users WHERE email=? COLLATE NOCASE", (email,)
        ).fetchone()
        return self._row_to_user(row) if row else None

    def get_user_by_id(self, user_id: int) -> User | None:
        row = self._conn.execute(
            "SELECT * FROM users WHERE id=?", (user_id,)
        ).fetchone()
        return self._row_to_user(row) if row else None

    def update_user(self, user_id: int, **fields: object) -> User | None:
        allowed = {
            "display_name", "home_base", "default_state",
            "default_nights", "default_from", "last_login_at",
            "recommendations_enabled", "preferred_tags",
            "onboarding_complete",
        }
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return self.get_user_by_id(user_id)
        # Serialize list fields to JSON
        if "preferred_tags" in updates and isinstance(updates["preferred_tags"], list):
            updates["preferred_tags"] = json.dumps(updates["preferred_tags"])
        set_clause = ", ".join(f"{k}=?" for k in updates)
        self._conn.execute(
            f"UPDATE users SET {set_clause} WHERE id=?",
            (*updates.values(), user_id),
        )
        self._conn.commit()
        return self.get_user_by_id(user_id)

    def delete_user(self, user_id: int) -> bool:
        # Delete watches and search history (cascade), then user
        self._conn.execute("DELETE FROM watches WHERE user_id=?", (user_id,))
        self._conn.execute("DELETE FROM search_history WHERE user_id=?", (user_id,))
        cursor = self._conn.execute("DELETE FROM users WHERE id=?", (user_id,))
        self._conn.commit()
        return cursor.rowcount > 0

    def _row_to_user(self, row: sqlite3.Row) -> User:
        d = dict(row)
        d["recommendations_enabled"] = bool(d.get("recommendations_enabled", 0))
        d["onboarding_complete"] = bool(d.get("onboarding_complete", 0))
        tags_raw = d.pop("preferred_tags", "[]") or "[]"
        d["preferred_tags"] = json.loads(tags_raw) if isinstance(tags_raw, str) else tags_raw
        return User(**d)

    # -------------------------------------------------------------------
    # Search history
    # -------------------------------------------------------------------

    def save_search(self, user_id: int, params: str, result_count: int = 0) -> None:
        now = datetime.now().isoformat()
        self._conn.execute(
            "INSERT INTO search_history (user_id, params, result_count, searched_at)"
            " VALUES (?, ?, ?, ?)",
            (user_id, params, result_count, now),
        )
        self._conn.commit()

    def get_search_history(self, user_id: int, limit: int = 10) -> list[dict]:
        rows = self._conn.execute(
            "SELECT params, result_count, searched_at"
            " FROM search_history WHERE user_id=?"
            " ORDER BY searched_at DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
        return [
            {
                "params": json.loads(r["params"]),
                "result_count": r["result_count"],
                "searched_at": r["searched_at"],
            }
            for r in rows
        ]

    def get_recommendation_affinities(
        self, user_id: int, history_limit: int = 20,
    ) -> dict:
        """Extract tag/state affinity from recent search history.

        Returns {"tags": {"lakeside": 3.2, ...}, "states": {"WA": 5.0, ...},
                 "watched_facility_ids": set[str]}.
        """
        import math

        history = self.get_search_history(user_id, limit=history_limit)
        tag_scores: dict[str, float] = {}
        state_scores: dict[str, float] = {}

        for i, entry in enumerate(history):
            # Exponential decay: most recent = 1.0, oldest ≈ 0.37
            weight = math.exp(-i * 0.05)
            params = entry["params"]

            # Tags
            if params.get("tags"):
                for tag in str(params["tags"]).split(","):
                    tag = tag.strip()
                    if tag:
                        tag_scores[tag] = tag_scores.get(tag, 0) + weight

            # State
            if params.get("state"):
                st = params["state"]
                state_scores[st] = state_scores.get(st, 0) + weight

        # Watched facility IDs — exclude from recommendations
        watched_rows = self._conn.execute(
            "SELECT DISTINCT facility_id FROM watches WHERE user_id=?",
            (user_id,),
        ).fetchall()
        watched = {r["facility_id"] for r in watched_rows}

        return {
            "tags": tag_scores,
            "states": state_scores,
            "watched_facility_ids": watched,
        }

    def get_user_export(self, user_id: int) -> dict:
        """Export all user data as a dict."""
        user = self.get_user_by_id(user_id)
        if not user:
            return {}
        watches = self.list_watches_by_user(user_id)
        history = self.get_search_history(user_id, limit=100)
        return {
            "user": {
                "email": user.email,
                "display_name": user.display_name,
                "home_base": user.home_base,
                "default_state": user.default_state,
                "default_nights": user.default_nights,
                "default_from": user.default_from,
                "created_at": user.created_at,
            },
            "watches": [
                {
                    "facility_id": w.facility_id,
                    "name": w.name,
                    "start_date": w.start_date,
                    "end_date": w.end_date,
                    "min_nights": w.min_nights,
                    "enabled": w.enabled,
                    "created_at": w.created_at,
                }
                for w in watches
            ],
            "search_history": history,
        }

    # -------------------------------------------------------------------
    # Watch migration helpers
    # -------------------------------------------------------------------

    def migrate_watches_to_user(self, session_token: str, user_id: int) -> int:
        """Migrate anonymous watches to a user account. Returns count migrated."""
        cursor = self._conn.execute(
            "UPDATE watches SET user_id=?, session_token='' WHERE session_token=?",
            (user_id, session_token),
        )
        self._conn.commit()
        return cursor.rowcount

    def list_watches_by_user(self, user_id: int) -> list[Watch]:
        rows = self._conn.execute(
            "SELECT * FROM watches WHERE user_id=? ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()
        return [self._row_to_watch(r) for r in rows]

    # -------------------------------------------------------------------
    # Watches
    # -------------------------------------------------------------------

    def has_duplicate_watch(self, watch: Watch) -> bool:
        """Check if an equivalent watch already exists for this owner."""
        if watch.user_id:
            row = self._conn.execute(
                "SELECT 1 FROM watches WHERE facility_id=?"
                " AND start_date=? AND end_date=? AND user_id=?",
                (watch.facility_id, watch.start_date,
                 watch.end_date, watch.user_id),
            ).fetchone()
        elif watch.session_token:
            row = self._conn.execute(
                "SELECT 1 FROM watches WHERE facility_id=?"
                " AND start_date=? AND end_date=?"
                " AND session_token=?",
                (watch.facility_id, watch.start_date,
                 watch.end_date, watch.session_token),
            ).fetchone()
        else:
            return False
        return row is not None

    def add_watch(self, watch: Watch) -> Watch:
        """Add a new watch. Returns it with its id."""
        now = datetime.now().isoformat()
        self._conn.execute(
            """\
            INSERT INTO watches
                (facility_id, name, start_date, end_date, min_nights,
                 days_of_week, notify_topic, notification_channel,
                 session_token, user_id, enabled, created_at,
                 watch_type, search_params)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                watch.facility_id,
                watch.name,
                watch.start_date,
                watch.end_date,
                watch.min_nights,
                json.dumps(watch.days_of_week) if watch.days_of_week else None,
                watch.notify_topic,
                watch.notification_channel,
                watch.session_token,
                watch.user_id,
                int(watch.enabled),
                now,
                watch.watch_type,
                watch.search_params,
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

    def toggle_enabled(self, watch_id: int, session_token: str = "") -> bool:
        """Toggle a watch's enabled state. Returns new state."""
        row = self._conn.execute(
            "SELECT enabled FROM watches WHERE id=?",
            (watch_id,),
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

    # -------------------------------------------------------------------
    # Trips
    # -------------------------------------------------------------------

    MAX_TRIPS_PER_USER = 10

    def create_trip(self, user_id: int, name: str, **fields: object) -> Trip:
        """Create a new trip. Raises ValueError if user has too many trips."""
        count = self._conn.execute(
            "SELECT COUNT(*) FROM trips WHERE user_id=?", (user_id,),
        ).fetchone()[0]
        if count >= self.MAX_TRIPS_PER_USER:
            raise ValueError(
                f"Maximum {self.MAX_TRIPS_PER_USER} trips per user"
            )
        now = datetime.now().isoformat()
        row = self._conn.execute(
            "INSERT INTO trips (user_id, name, start_date, end_date, notes,"
            " created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                user_id,
                name,
                fields.get("start_date", ""),
                fields.get("end_date", ""),
                fields.get("notes", ""),
                now,
                now,
            ),
        )
        self._conn.commit()
        return Trip(
            id=row.lastrowid,
            user_id=user_id,
            name=name,
            start_date=str(fields.get("start_date", "")),
            end_date=str(fields.get("end_date", "")),
            notes=str(fields.get("notes", "")),
            created_at=now,
            updated_at=now,
        )

    def get_trip(self, trip_id: int) -> Trip | None:
        row = self._conn.execute(
            "SELECT * FROM trips WHERE id=?", (trip_id,),
        ).fetchone()
        if not row:
            return None
        return self._row_to_trip(row)

    def list_trips_by_user(self, user_id: int) -> list[Trip]:
        rows = self._conn.execute(
            "SELECT * FROM trips WHERE user_id=? ORDER BY updated_at DESC",
            (user_id,),
        ).fetchall()
        return [self._row_to_trip(r) for r in rows]

    def update_trip(self, trip_id: int, **fields: object) -> Trip | None:
        allowed = {"name", "start_date", "end_date", "notes"}
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return self.get_trip(trip_id)
        updates["updated_at"] = datetime.now().isoformat()
        set_clause = ", ".join(f"{k}=?" for k in updates)
        self._conn.execute(
            f"UPDATE trips SET {set_clause} WHERE id=?",
            (*updates.values(), trip_id),
        )
        self._conn.commit()
        return self.get_trip(trip_id)

    def delete_trip(self, trip_id: int) -> bool:
        cursor = self._conn.execute(
            "DELETE FROM trips WHERE id=?", (trip_id,),
        )
        self._conn.commit()
        return cursor.rowcount > 0

    def _row_to_trip(self, row: sqlite3.Row) -> Trip:
        return Trip(
            id=row["id"],
            user_id=row["user_id"],
            name=row["name"],
            start_date=row["start_date"],
            end_date=row["end_date"],
            notes=row["notes"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    # -------------------------------------------------------------------
    # Trip campgrounds
    # -------------------------------------------------------------------

    def add_campground_to_trip(
        self, trip_id: int, facility_id: str, source: str = "recgov",
        name: str = "", notes: str = "",
    ) -> TripCampground:
        """Add a campground to a trip. Raises IntegrityError if duplicate."""
        now = datetime.now().isoformat()
        # Get next sort_order
        max_order = self._conn.execute(
            "SELECT COALESCE(MAX(sort_order), -1) FROM trip_campgrounds"
            " WHERE trip_id=?",
            (trip_id,),
        ).fetchone()[0]
        row = self._conn.execute(
            "INSERT INTO trip_campgrounds"
            " (trip_id, facility_id, source, name, sort_order, notes, added_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (trip_id, facility_id, source, name, max_order + 1, notes, now),
        )
        self._conn.commit()
        # Touch trip updated_at
        self._conn.execute(
            "UPDATE trips SET updated_at=? WHERE id=?",
            (now, trip_id),
        )
        self._conn.commit()
        return TripCampground(
            id=row.lastrowid,
            trip_id=trip_id,
            facility_id=facility_id,
            source=source,
            name=name,
            sort_order=max_order + 1,
            notes=notes,
            added_at=now,
        )

    def remove_campground_from_trip(
        self, trip_id: int, facility_id: str, source: str = "recgov",
    ) -> bool:
        cursor = self._conn.execute(
            "DELETE FROM trip_campgrounds"
            " WHERE trip_id=? AND facility_id=? AND source=?",
            (trip_id, facility_id, source),
        )
        self._conn.commit()
        if cursor.rowcount > 0:
            now = datetime.now().isoformat()
            self._conn.execute(
                "UPDATE trips SET updated_at=? WHERE id=?", (now, trip_id),
            )
            self._conn.commit()
        return cursor.rowcount > 0

    def get_trip_campgrounds(self, trip_id: int) -> list[TripCampground]:
        rows = self._conn.execute(
            "SELECT * FROM trip_campgrounds WHERE trip_id=?"
            " ORDER BY sort_order",
            (trip_id,),
        ).fetchall()
        return [
            TripCampground(
                id=r["id"],
                trip_id=r["trip_id"],
                facility_id=r["facility_id"],
                source=r["source"],
                name=r["name"],
                sort_order=r["sort_order"],
                notes=r["notes"],
                added_at=r["added_at"],
            )
            for r in rows
        ]

    # -------------------------------------------------------------------
    # Shared links
    # -------------------------------------------------------------------

    def create_shared_link(
        self, user_id: int,
        watch_id: int | None = None,
        trip_id: int | None = None,
        expires_days: int = 30,
    ) -> SharedLink:
        """Create a shareable link for a watch or trip."""
        import uuid as _uuid

        if not watch_id and not trip_id:
            raise ValueError("Must specify watch_id or trip_id")

        link_uuid = _uuid.uuid4().hex[:12]
        now = datetime.now()
        expires_at = (now + timedelta(days=expires_days)).isoformat()

        self._conn.execute(
            "INSERT INTO shared_links"
            " (uuid, watch_id, trip_id, created_by, expires_at, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (link_uuid, watch_id, trip_id, user_id, expires_at, now.isoformat()),
        )
        self._conn.commit()
        return SharedLink(
            uuid=link_uuid,
            watch_id=watch_id,
            trip_id=trip_id,
            created_by=user_id,
            expires_at=expires_at,
            created_at=now.isoformat(),
        )

    def get_shared_link(self, uuid: str) -> SharedLink | None:
        row = self._conn.execute(
            "SELECT * FROM shared_links WHERE uuid=?", (uuid,),
        ).fetchone()
        if not row:
            return None
        return SharedLink(
            id=row["id"],
            uuid=row["uuid"],
            watch_id=row["watch_id"],
            trip_id=row["trip_id"],
            created_by=row["created_by"],
            expires_at=row["expires_at"],
            revoked=bool(row["revoked"]),
            created_at=row["created_at"],
        )

    def revoke_shared_link(self, uuid: str, user_id: int) -> bool:
        cursor = self._conn.execute(
            "UPDATE shared_links SET revoked=1"
            " WHERE uuid=? AND created_by=?",
            (uuid, user_id),
        )
        self._conn.commit()
        return cursor.rowcount > 0

    def cleanup_expired_links(self) -> int:
        now = datetime.now().isoformat()
        cursor = self._conn.execute(
            "DELETE FROM shared_links WHERE expires_at < ?", (now,),
        )
        self._conn.commit()
        return cursor.rowcount
