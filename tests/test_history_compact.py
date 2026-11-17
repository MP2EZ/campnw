"""Tests for availability history compaction and change detection."""


from pnw_campsites.monitor.db import WatchDB


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
