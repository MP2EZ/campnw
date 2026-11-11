"""A watches table with columns this code doesn't know (added by a newer
release, then rolled back, or a shared staging DB) must still load.

Found 2026-11-11: staging crashed at startup with `Watch.__init__() got an
unexpected keyword argument 'min_people'` after a newer branch migrated the
shared DB.
"""

from __future__ import annotations

from pnw_campsites.monitor.db import Watch, WatchDB


def test_watch_loads_when_the_table_has_unknown_columns(watch_db: WatchDB) -> None:
    added = watch_db.add_watch(
        Watch(facility_id="232465", name="Ohanapecosh",
              start_date="2027-06-04", end_date="2027-06-06")
    )
    watch_db._conn.execute("ALTER TABLE watches ADD COLUMN some_future_field TEXT")
    watch_db._conn.execute("UPDATE watches SET some_future_field = 'x'")
    watch_db._conn.commit()

    loaded = watch_db.get_watch(added.id)
    assert loaded is not None
    assert loaded.facility_id == "232465"
    assert [w.id for w in watch_db.list_watches(enabled_only=False)] == [added.id]
