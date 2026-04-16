"""SQLite-backed campground registry."""

from __future__ import annotations

import json
import re
import sqlite3
import unicodedata
from datetime import datetime
from pathlib import Path

from pnw_campsites.geo import haversine_miles
from pnw_campsites.registry.models import BookingSystem, Campground


def slugify(name: str) -> str:
    """Convert a campground name to a URL-safe slug.

    >>> slugify("Deception Pass State Park")
    'deception-pass-state-park'
    >>> slugify("André's  Camp—Site #5")
    'andre-s-campsite-5'
    """
    # Normalize unicode → ASCII (e.g. é → e)
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    s = s.lower()
    # Replace non-alphanumeric with hyphens
    s = re.sub(r"[^a-z0-9]+", "-", s)
    # Collapse runs and trim
    return s.strip("-")

# Check Docker path first, then relative path for local dev
_docker_db = Path("/app/data/registry.db")
_local_db = Path(__file__).resolve().parents[3] / "data" / "registry.db"
DEFAULT_DB_PATH = _docker_db if _docker_db.exists() else _local_db

SCHEMA = """\
CREATE TABLE IF NOT EXISTS campgrounds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    facility_id TEXT NOT NULL,
    name TEXT NOT NULL,
    booking_system TEXT NOT NULL DEFAULT 'recgov',
    latitude REAL DEFAULT 0.0,
    longitude REAL DEFAULT 0.0,
    region TEXT DEFAULT '',
    state TEXT DEFAULT '',
    drive_minutes_from_base INTEGER,
    tags TEXT DEFAULT '[]',        -- JSON array
    notes TEXT DEFAULT '',
    rating INTEGER,
    total_sites INTEGER,
    enabled INTEGER DEFAULT 1,
    created_at TEXT,
    updated_at TEXT,
    UNIQUE(booking_system, facility_id)
);

CREATE INDEX IF NOT EXISTS idx_campgrounds_state ON campgrounds(state);
CREATE INDEX IF NOT EXISTS idx_campgrounds_booking_system ON campgrounds(booking_system);

CREATE TABLE IF NOT EXISTS drive_times (
    base_name TEXT NOT NULL,
    booking_system TEXT NOT NULL,
    facility_id TEXT NOT NULL,
    drive_minutes INTEGER NOT NULL,
    drive_miles REAL,
    source TEXT NOT NULL DEFAULT 'mapbox',
    computed_at TEXT NOT NULL,
    PRIMARY KEY (base_name, booking_system, facility_id)
);

CREATE INDEX IF NOT EXISTS idx_drive_times_base ON drive_times(base_name);

CREATE TABLE IF NOT EXISTS weather_normals (
    lat_2dp REAL NOT NULL,
    lon_2dp REAL NOT NULL,
    month INTEGER NOT NULL,
    day INTEGER NOT NULL,
    temp_high_f REAL NOT NULL,
    temp_low_f REAL NOT NULL,
    precip_pct REAL NOT NULL,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (lat_2dp, lon_2dp, month, day)
);
"""


class CampgroundRegistry:
    """CRUD operations for the local campground registry."""

    def __init__(self, db_path: Path | str = DEFAULT_DB_PATH) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(SCHEMA)

        # Migrations — add columns that didn't exist in the original schema
        cols = {
            row[1]
            for row in self._conn.execute("PRAGMA table_info(campgrounds)").fetchall()
        }
        if "vibe" not in cols:
            self._conn.execute(
                "ALTER TABLE campgrounds ADD COLUMN vibe TEXT DEFAULT ''"
            )
            self._conn.commit()
        if "booking_url_slug" not in cols:
            self._conn.execute(
                "ALTER TABLE campgrounds ADD COLUMN booking_url_slug TEXT DEFAULT ''"
            )
            self._conn.commit()
        for col in ("elevator_pitch", "description_rewrite", "best_for", "booking_tips"):
            if col not in cols:
                self._conn.execute(
                    f"ALTER TABLE campgrounds ADD COLUMN {col} TEXT DEFAULT ''"
                )
                self._conn.commit()
        if "slug" not in cols:
            self._conn.execute(
                "ALTER TABLE campgrounds ADD COLUMN slug TEXT DEFAULT ''"
            )
            self._conn.commit()
            self._backfill_slugs()
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_campgrounds_slug"
                " ON campgrounds(state, slug)"
            )
            self._conn.commit()

        # Migration: weather_normals PK changed from (lat,lon,month) to (lat,lon,month,day)
        wn_cols = {
            row[1]
            for row in self._conn.execute("PRAGMA table_info(weather_normals)").fetchall()
        }
        if wn_cols and "day" not in wn_cols:
            self._conn.execute("DROP TABLE weather_normals")
            self._conn.executescript(SCHEMA)
            self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> CampgroundRegistry:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------

    def _backfill_slugs(self) -> None:
        """One-time backfill: generate slugs for all existing campgrounds."""
        rows = self._conn.execute(
            "SELECT id, name, state, facility_id FROM campgrounds"
        ).fetchall()
        # Detect duplicate names within state for disambiguation
        from collections import Counter
        state_name_counts = Counter((r["state"], slugify(r["name"])) for r in rows)
        dupes = {k for k, v in state_name_counts.items() if v > 1}

        for r in rows:
            base = slugify(r["name"])
            slug = f"{base}-{r['facility_id']}" if (r["state"], base) in dupes else base
            self._conn.execute(
                "UPDATE campgrounds SET slug=? WHERE id=?", (slug, r["id"])
            )
        self._conn.commit()

    def _row_to_campground(self, row: sqlite3.Row) -> Campground:
        d = dict(row)
        d["tags"] = json.loads(d["tags"]) if d["tags"] else []
        d["enabled"] = bool(d["enabled"])
        d["booking_system"] = BookingSystem(d["booking_system"])
        if d["created_at"]:
            d["created_at"] = datetime.fromisoformat(d["created_at"])
        if d["updated_at"]:
            d["updated_at"] = datetime.fromisoformat(d["updated_at"])
        return Campground(**d)

    # -------------------------------------------------------------------
    # Write
    # -------------------------------------------------------------------

    def upsert(self, cg: Campground) -> Campground:
        """Insert or update a campground. Returns the campground with its id."""
        now = datetime.now().isoformat()
        slug = cg.slug or slugify(cg.name)
        self._conn.execute(
            """\
            INSERT INTO campgrounds (
                facility_id, name, booking_system, latitude, longitude,
                region, state, drive_minutes_from_base, tags, notes,
                rating, total_sites, enabled, booking_url_slug, slug,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(booking_system, facility_id) DO UPDATE SET
                name=excluded.name,
                latitude=excluded.latitude,
                longitude=excluded.longitude,
                region=excluded.region,
                state=excluded.state,
                drive_minutes_from_base=COALESCE(
                    campgrounds.drive_minutes_from_base,
                    excluded.drive_minutes_from_base
                ),
                tags=CASE WHEN campgrounds.tags = '[]'
                    THEN excluded.tags ELSE campgrounds.tags END,
                notes=CASE WHEN campgrounds.notes = ''
                    THEN excluded.notes ELSE campgrounds.notes END,
                rating=COALESCE(campgrounds.rating, excluded.rating),
                total_sites=excluded.total_sites,
                enabled=campgrounds.enabled,
                booking_url_slug=CASE WHEN campgrounds.booking_url_slug = ''
                    THEN excluded.booking_url_slug
                    ELSE campgrounds.booking_url_slug END,
                slug=CASE WHEN campgrounds.slug = ''
                    THEN excluded.slug ELSE campgrounds.slug END,
                updated_at=?
            """,
            (
                cg.facility_id,
                cg.name,
                cg.booking_system.value,
                cg.latitude,
                cg.longitude,
                cg.region,
                cg.state,
                cg.drive_minutes_from_base,
                json.dumps(cg.tags),
                cg.notes,
                cg.rating,
                cg.total_sites,
                int(cg.enabled),
                cg.booking_url_slug,
                slug,
                now,
                now,
                now,  # for the ON CONFLICT updated_at
            ),
        )
        self._conn.commit()

        row = self._conn.execute(
            "SELECT * FROM campgrounds WHERE booking_system=? AND facility_id=?",
            (cg.booking_system.value, cg.facility_id),
        ).fetchone()
        return self._row_to_campground(row)

    def bulk_upsert(self, campgrounds: list[Campground]) -> int:
        """Upsert multiple campgrounds in a single transaction."""
        now = datetime.now().isoformat()
        sql = """\
            INSERT INTO campgrounds (
                facility_id, name, booking_system, latitude, longitude,
                region, state, drive_minutes_from_base, tags, notes,
                rating, total_sites, enabled, booking_url_slug, slug,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(booking_system, facility_id) DO UPDATE SET
                name=excluded.name,
                latitude=excluded.latitude,
                longitude=excluded.longitude,
                region=excluded.region,
                state=excluded.state,
                drive_minutes_from_base=COALESCE(
                    campgrounds.drive_minutes_from_base,
                    excluded.drive_minutes_from_base
                ),
                tags=CASE WHEN campgrounds.tags = '[]'
                    THEN excluded.tags ELSE campgrounds.tags END,
                notes=CASE WHEN campgrounds.notes = ''
                    THEN excluded.notes ELSE campgrounds.notes END,
                rating=COALESCE(campgrounds.rating, excluded.rating),
                total_sites=excluded.total_sites,
                enabled=campgrounds.enabled,
                booking_url_slug=CASE WHEN campgrounds.booking_url_slug = ''
                    THEN excluded.booking_url_slug
                    ELSE campgrounds.booking_url_slug END,
                slug=CASE WHEN campgrounds.slug = ''
                    THEN excluded.slug ELSE campgrounds.slug END,
                updated_at=?
        """
        rows = [
            (
                cg.facility_id, cg.name, cg.booking_system.value,
                cg.latitude, cg.longitude, cg.region, cg.state,
                cg.drive_minutes_from_base, json.dumps(cg.tags), cg.notes,
                cg.rating, cg.total_sites, int(cg.enabled), cg.booking_url_slug,
                cg.slug or slugify(cg.name),
                now, now, now,
            )
            for cg in campgrounds
        ]
        self._conn.executemany(sql, rows)
        self._conn.commit()
        return len(campgrounds)

    # -------------------------------------------------------------------
    # Read
    # -------------------------------------------------------------------

    def get_by_id(self, campground_id: int) -> Campground | None:
        row = self._conn.execute(
            "SELECT * FROM campgrounds WHERE id=?", (campground_id,)
        ).fetchone()
        return self._row_to_campground(row) if row else None

    def get_by_facility_id(
        self, facility_id: str, booking_system: BookingSystem = BookingSystem.RECGOV
    ) -> Campground | None:
        row = self._conn.execute(
            "SELECT * FROM campgrounds WHERE facility_id=? AND booking_system=?",
            (facility_id, booking_system.value),
        ).fetchone()
        return self._row_to_campground(row) if row else None

    def search(
        self,
        *,
        state: str | None = None,
        tags: list[str] | None = None,
        max_drive_minutes: int | None = None,
        booking_system: BookingSystem | None = None,
        name_like: str | None = None,
        enabled_only: bool = True,
    ) -> list[Campground]:
        """Flexible search across the registry."""
        clauses: list[str] = []
        params: list[object] = []

        if enabled_only:
            clauses.append("enabled = 1")
        if state:
            clauses.append("state = ?")
            params.append(state)
        if booking_system:
            clauses.append("booking_system = ?")
            params.append(booking_system.value)
        if max_drive_minutes is not None:
            clauses.append("drive_minutes_from_base IS NOT NULL AND drive_minutes_from_base <= ?")
            params.append(max_drive_minutes)
        if name_like:
            clauses.append("name LIKE ?")
            params.append(f"%{name_like}%")

        if tags:
            placeholders = ",".join("?" for _ in tags)
            clauses.append(
                f"EXISTS (SELECT 1 FROM json_each(tags) WHERE value IN ({placeholders}))"
            )
            params.extend(tags)

        where = " AND ".join(clauses) if clauses else "1=1"
        sql = f"SELECT * FROM campgrounds WHERE {where} ORDER BY name"

        rows = self._conn.execute(sql, params).fetchall()
        return [self._row_to_campground(r) for r in rows]

    def list_all(self, *, enabled_only: bool = True) -> list[Campground]:
        """Return all campgrounds."""
        return self.search(enabled_only=enabled_only)

    def count(self, *, enabled_only: bool = True) -> int:
        where = "enabled = 1" if enabled_only else "1=1"
        row = self._conn.execute(f"SELECT COUNT(*) FROM campgrounds WHERE {where}").fetchone()
        return row[0]

    def get_by_slug(self, state: str, slug: str) -> Campground | None:
        """Look up a campground by state + URL slug."""
        row = self._conn.execute(
            "SELECT * FROM campgrounds WHERE state=? AND slug=? AND enabled=1",
            (state.upper(), slug),
        ).fetchone()
        return self._row_to_campground(row) if row else None

    def get_nearby(
        self,
        lat: float,
        lon: float,
        *,
        state: str | None = None,
        limit: int = 5,
        exclude_id: int | None = None,
    ) -> list[Campground]:
        """Find nearest campgrounds by haversine distance."""
        # Bounding box pre-filter (~2 degrees ≈ 140 miles at PNW latitudes)
        bbox = 2.0
        clauses = [
            "enabled = 1",
            "latitude BETWEEN ? AND ?",
            "longitude BETWEEN ? AND ?",
        ]
        params: list[object] = [lat - bbox, lat + bbox, lon - bbox, lon + bbox]
        if state:
            clauses.append("state = ?")
            params.append(state)
        if exclude_id is not None:
            clauses.append("id != ?")
            params.append(exclude_id)
        where = " AND ".join(clauses)
        rows = self._conn.execute(
            f"SELECT * FROM campgrounds WHERE {where}", params
        ).fetchall()
        campgrounds = [self._row_to_campground(r) for r in rows]

        # Fallback to full scan if bbox returned fewer than requested
        if len(campgrounds) < limit:
            clauses_full = ["enabled = 1", "latitude != 0.0", "longitude != 0.0"]
            params_full: list[object] = []
            if state:
                clauses_full.append("state = ?")
                params_full.append(state)
            if exclude_id is not None:
                clauses_full.append("id != ?")
                params_full.append(exclude_id)
            rows = self._conn.execute(
                f"SELECT * FROM campgrounds WHERE {' AND '.join(clauses_full)}", params_full
            ).fetchall()
            campgrounds = [self._row_to_campground(r) for r in rows]

        campgrounds.sort(
            key=lambda cg: haversine_miles(lat, lon, cg.latitude, cg.longitude)
        )
        return campgrounds[:limit]

    def get_all_tags(self) -> list[tuple[str, int]]:
        """Return all distinct tags with their campground counts."""
        rows = self._conn.execute(
            "SELECT tags FROM campgrounds WHERE enabled = 1"
        ).fetchall()
        from collections import Counter
        tag_counts: Counter[str] = Counter()
        for r in rows:
            for tag in json.loads(r["tags"] or "[]"):
                tag_counts[tag] += 1
        return sorted(tag_counts.items(), key=lambda x: (-x[1], x[0]))

    def count_by_state(self) -> dict[str, int]:
        """Return campground counts grouped by state."""
        rows = self._conn.execute(
            "SELECT state, COUNT(*) as cnt FROM campgrounds"
            " WHERE enabled = 1 GROUP BY state ORDER BY state"
        ).fetchall()
        return {r["state"]: r["cnt"] for r in rows}

    # -------------------------------------------------------------------
    # Update / Delete
    # -------------------------------------------------------------------

    def update_tags(self, campground_id: int, tags: list[str]) -> None:
        self._conn.execute(
            "UPDATE campgrounds SET tags=?, updated_at=? WHERE id=?",
            (json.dumps(tags), datetime.now().isoformat(), campground_id),
        )
        self._conn.commit()

    def update_booking_tips(self, campground_id: int, tips_json: str) -> None:
        self._conn.execute(
            "UPDATE campgrounds SET booking_tips=?, updated_at=? WHERE id=?",
            (tips_json, datetime.now().isoformat(), campground_id),
        )
        self._conn.commit()

    def update_vibe(self, campground_id: int, vibe: str) -> None:
        self._conn.execute(
            "UPDATE campgrounds SET vibe=?, updated_at=? WHERE id=?",
            (vibe, datetime.now().isoformat(), campground_id),
        )
        self._conn.commit()

    def update_description(
        self,
        campground_id: int,
        elevator_pitch: str,
        description_rewrite: str,
        best_for: str,
    ) -> None:
        self._conn.execute(
            "UPDATE campgrounds SET elevator_pitch=?, description_rewrite=?,"
            " best_for=?, updated_at=? WHERE id=?",
            (
                elevator_pitch,
                description_rewrite,
                best_for,
                datetime.now().isoformat(),
                campground_id,
            ),
        )
        self._conn.commit()

    def update_notes(self, campground_id: int, notes: str, rating: int | None = None) -> None:
        if rating is not None:
            self._conn.execute(
                "UPDATE campgrounds SET notes=?, rating=?, updated_at=? WHERE id=?",
                (notes, rating, datetime.now().isoformat(), campground_id),
            )
        else:
            self._conn.execute(
                "UPDATE campgrounds SET notes=?, updated_at=? WHERE id=?",
                (notes, datetime.now().isoformat(), campground_id),
            )
        self._conn.commit()

    def set_enabled(self, campground_id: int, enabled: bool) -> None:
        self._conn.execute(
            "UPDATE campgrounds SET enabled=?, updated_at=? WHERE id=?",
            (int(enabled), datetime.now().isoformat(), campground_id),
        )
        self._conn.commit()

    def delete(self, campground_id: int) -> None:
        self._conn.execute("DELETE FROM campgrounds WHERE id=?", (campground_id,))
        self._conn.commit()

    # -------------------------------------------------------------------
    # Similarity search
    # -------------------------------------------------------------------

    def find_similar(
        self,
        campground: Campground,
        state: str | None = None,
        limit: int = 2,
    ) -> list[Campground]:
        """Find campgrounds with similar tags and nearby location.

        Scores candidates by Jaccard(tags) * 0.6 + proximity * 0.4.
        Proximity = max(0, 1.0 - haversine_miles / 100).
        """
        candidates = self.search(state=state, enabled_only=True)
        # Exclude the original campground
        candidates = [
            cg for cg in candidates
            if cg.facility_id != campground.facility_id
            or cg.booking_system != campground.booking_system
        ]

        source_tags = set(campground.tags)

        scored: list[tuple[float, Campground]] = []
        for cg in candidates:
            # Jaccard similarity on tags
            cg_tags = set(cg.tags)
            if source_tags or cg_tags:
                union = source_tags | cg_tags
                intersection = source_tags & cg_tags
                jaccard = len(intersection) / len(union)
            else:
                jaccard = 0.0

            # Proximity score
            if (
                campground.latitude
                and campground.longitude
                and cg.latitude
                and cg.longitude
            ):
                dist = haversine_miles(
                    campground.latitude, campground.longitude,
                    cg.latitude, cg.longitude,
                )
                proximity = max(0.0, 1.0 - dist / 100.0)
            else:
                proximity = 0.0

            # Require at least some tag overlap to be a suggestion
            if jaccard == 0.0 and source_tags:
                continue
            score = jaccard * 0.6 + proximity * 0.4
            if score > 0:
                scored.append((score, cg))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [cg for _, cg in scored[:limit]]

    # -------------------------------------------------------------------
    # Drive times (Mapbox pre-computed)
    # -------------------------------------------------------------------

    def get_drive_times_from_base(
        self, base_name: str
    ) -> dict[tuple[str, str], int]:
        """Load all pre-computed drive times for a known base.

        Returns {(booking_system, facility_id): drive_minutes}.
        """
        rows = self._conn.execute(
            "SELECT booking_system, facility_id, drive_minutes "
            "FROM drive_times WHERE base_name = ?",
            (base_name.lower(),),
        ).fetchall()
        return {(r["booking_system"], r["facility_id"]): r["drive_minutes"] for r in rows}

    def upsert_drive_times(self, rows: list[dict]) -> int:
        """Bulk upsert pre-computed drive times.

        Each dict: {base_name, booking_system, facility_id, drive_minutes,
                     drive_miles, source, computed_at}
        Returns number of rows upserted.
        """
        if not rows:
            return 0
        self._conn.executemany(
            """\
            INSERT INTO drive_times
                (base_name, booking_system, facility_id, drive_minutes,
                 drive_miles, source, computed_at)
            VALUES
                (:base_name, :booking_system, :facility_id, :drive_minutes,
                 :drive_miles, :source, :computed_at)
            ON CONFLICT (base_name, booking_system, facility_id)
            DO UPDATE SET
                drive_minutes = excluded.drive_minutes,
                drive_miles = excluded.drive_miles,
                source = excluded.source,
                computed_at = excluded.computed_at
            """,
            rows,
        )
        self._conn.commit()
        return len(rows)

    # ------------------------------------------------------------------
    # Weather normals cache
    # ------------------------------------------------------------------

    def get_weather_normals(
        self, lat: float, lon: float, month: int, day: int,
    ) -> tuple[float, float, float] | None:
        """Look up the closest cached weather normal for a location and date.

        Finds the entry in the given month with the closest day to the
        requested day.  Returns (temp_high_f, temp_low_f, precip_pct) or None.
        """
        lat_2dp = round(lat, 2)
        lon_2dp = round(lon, 2)
        row = self._conn.execute(
            "SELECT temp_high_f, temp_low_f, precip_pct "
            "FROM weather_normals "
            "WHERE lat_2dp = ? AND lon_2dp = ? AND month = ? "
            "ORDER BY ABS(day - ?) LIMIT 1",
            [lat_2dp, lon_2dp, month, day],
        ).fetchone()
        if row:
            return (row["temp_high_f"], row["temp_low_f"], row["precip_pct"])
        return None

    def get_weather_normals_batch(
        self, locations: list[tuple[float, float, int, int]],
    ) -> dict[tuple[float, float, int], tuple[float, float, float]]:
        """Batch lookup for multiple (lat, lon, month, day) tuples.

        For each location, finds the closest cached day within that month.
        Returns {(lat_2dp, lon_2dp, month): (temp_high_f, temp_low_f, precip_pct)}.
        """
        if not locations:
            return {}
        # Build unique (lat_2dp, lon_2dp, month) keys + track requested day
        key_to_day: dict[tuple[float, float, int], int] = {}
        for lat, lon, m, d in locations:
            key = (round(lat, 2), round(lon, 2), m)
            key_to_day[key] = d
        unique_keys = list(key_to_day.keys())

        # Fetch all rows for matching (lat, lon, month) combos
        clauses = " OR ".join(
            "(lat_2dp = ? AND lon_2dp = ? AND month = ?)" for _ in unique_keys
        )
        params = [v for k in unique_keys for v in k]
        rows = self._conn.execute(
            "SELECT lat_2dp, lon_2dp, month, day, "
            "temp_high_f, temp_low_f, precip_pct "
            f"FROM weather_normals WHERE {clauses}",
            params,
        ).fetchall()

        # Group by (lat, lon, month), pick closest day
        from collections import defaultdict
        grouped: dict[tuple[float, float, int], list] = defaultdict(list)
        for r in rows:
            grouped[(r["lat_2dp"], r["lon_2dp"], r["month"])].append(r)

        result = {}
        for key, candidates in grouped.items():
            target_day = key_to_day.get(key, 15)
            best = min(candidates, key=lambda r: abs(r["day"] - target_day))
            result[key] = (best["temp_high_f"], best["temp_low_f"], best["precip_pct"])
        return result

    def upsert_weather_normals(self, rows: list[dict]) -> int:
        """Bulk upsert weather normals.

        Each dict: {lat_2dp, lon_2dp, month, day, temp_high_f, temp_low_f,
                     precip_pct, fetched_at}
        Returns number of rows upserted.
        """
        if not rows:
            return 0
        self._conn.executemany(
            """\
            INSERT INTO weather_normals
                (lat_2dp, lon_2dp, month, day, temp_high_f, temp_low_f,
                 precip_pct, fetched_at)
            VALUES
                (:lat_2dp, :lon_2dp, :month, :day, :temp_high_f, :temp_low_f,
                 :precip_pct, :fetched_at)
            ON CONFLICT (lat_2dp, lon_2dp, month, day)
            DO UPDATE SET
                temp_high_f = excluded.temp_high_f,
                temp_low_f = excluded.temp_low_f,
                precip_pct = excluded.precip_pct,
                fetched_at = excluded.fetched_at
            """,
            rows,
        )
        self._conn.commit()
        return len(rows)

    def count_cached_normals(
        self, lat: float, lon: float, day: int,
    ) -> int:
        """Count how many months are cached for a specific (lat, lon, day).

        Used by warmup script to skip fully-cached campgrounds.
        """
        lat_2dp = round(lat, 2)
        lon_2dp = round(lon, 2)
        row = self._conn.execute(
            "SELECT COUNT(*) FROM weather_normals "
            "WHERE lat_2dp = ? AND lon_2dp = ? AND day = ? "
            "AND month BETWEEN 4 AND 10",
            [lat_2dp, lon_2dp, day],
        ).fetchone()
        return row[0]
