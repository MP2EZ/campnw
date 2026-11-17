"""The E2E seeder's cleanup must leave no orphaned fixture rows.

watches.user_id has no FOREIGN KEY, so ON DELETE CASCADE never reaches it;
planner_sessions does cascade, but only when foreign_keys=ON.
"""

import importlib.util
import sqlite3
from pathlib import Path

import pytest

from pnw_campsites.monitor.db import WatchDB

SCRIPT = Path(__file__).parent.parent / "scripts" / "seed_e2e_fixtures.py"


@pytest.fixture
def seed(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "http://supabase.invalid")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "x")
    monkeypatch.setenv("E2E_FIXTURE_PASSWORD", "x")
    spec = importlib.util.spec_from_file_location("seed_e2e_fixtures", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_cleanup_removes_fixture_watches_and_sessions(seed, tmp_path):
    db_path = str(tmp_path / "watches.db")
    WatchDB(db_path).close()
    conn = sqlite3.connect(db_path)  # plain connection: foreign_keys is OFF

    fixture_id = seed.insert_user(conn, f"{seed.PREFIX}a@maestro.test", "sb-1")
    real_id = seed.insert_user(conn, "real@example.com", "sb-2")
    for uid in (fixture_id, real_id):
        seed.add_watches(conn, uid, 2)
        seed.add_planner_sessions(conn, uid, 2)
    conn.commit()

    seed.cleanup_fixture_users(conn)
    conn.commit()

    for table in ("watches", "planner_sessions"):
        orphans = conn.execute(
            f"SELECT COUNT(*) FROM {table} WHERE user_id IS NOT NULL "
            "AND user_id NOT IN (SELECT id FROM users)"
        ).fetchone()[0]
        assert orphans == 0, table
        kept = conn.execute(
            f"SELECT COUNT(*) FROM {table} WHERE user_id = ?", (real_id,)
        ).fetchone()[0]
        assert kept == 2, table
    conn.close()
