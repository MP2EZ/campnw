"""Tests for availability history compaction and change detection."""

import sqlite3
from pnw_campsites.monitor.db import WatchDB


def test_status_transitions_table_exists(tmp_path):
    db = WatchDB(str(tmp_path / "test.db"))
    tables = [
        r[0] for r in db._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    ]
    assert "status_transitions" in tables


def test_availability_daily_table_exists(tmp_path):
    db = WatchDB(str(tmp_path / "test.db"))
    tables = [
        r[0] for r in db._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    ]
    assert "availability_daily" in tables


def test_record_availability_only_stores_changes(tmp_path):
    """Second call with same data should not add to status_transitions."""
    db = WatchDB(str(tmp_path / "test.db"))

    records = [("site1", "2026-06-01", "Available")]
    db.record_availability_history("CG1", records, "recgov")

    # Same data again — no transition
    db.record_availability_history("CG1", records, "recgov")

    transitions = db._conn.execute(
        "SELECT * FROM status_transitions"
    ).fetchall()
    # First observation creates a transition from '' -> Available
    assert len(transitions) == 1

    # availability_daily should have 1 row with count=2
    daily = db._conn.execute(
        "SELECT observation_count FROM availability_daily"
        " WHERE campground_id='CG1' AND site_id='site1'"
    ).fetchone()
    assert daily[0] == 2


def test_record_availability_detects_status_change(tmp_path):
    db = WatchDB(str(tmp_path / "test.db"))

    db.record_availability_history(
        "CG1", [("site1", "2026-06-01", "Available")], "recgov",
    )
    db.record_availability_history(
        "CG1", [("site1", "2026-06-01", "Reserved")], "recgov",
    )

    transitions = db._conn.execute(
        "SELECT old_status, new_status FROM status_transitions"
        " ORDER BY id"
    ).fetchall()
    # '' -> Available, then Available -> Reserved
    assert len(transitions) == 2
    assert (transitions[0]["old_status"], transitions[0]["new_status"]) == ("", "Available")
    assert (transitions[1]["old_status"], transitions[1]["new_status"]) == ("Available", "Reserved")


from pnw_campsites.analytics.patterns import get_availability_summary


def test_patterns_reads_from_daily_table(tmp_path):
    """patterns.py should work with availability_daily, not raw history."""
    db = WatchDB(str(tmp_path / "test.db"))

    from datetime import date, timedelta
    base = date(2026, 6, 1)
    for i in range(31):
        d = base + timedelta(days=i)
        status = "Available" if d.weekday() < 5 else "Reserved"
        db._conn.execute(
            "INSERT INTO availability_daily"
            " (campground_id, site_id, date, status, source,"
            "  first_seen, last_seen, observation_count)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("CG1", "site1", d.isoformat(), status, "recgov",
             "2026-06-01", d.isoformat(), 10),
        )
    db._conn.commit()

    result = get_availability_summary(db, "CG1")
    assert result is not None
    assert result["day_of_week_availability"]["Monday"] > result["day_of_week_availability"]["Saturday"]
