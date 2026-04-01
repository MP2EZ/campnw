#!/usr/bin/env python3
"""Compact availability_history into daily rollups + transitions.

Run on production: fly ssh console -C "python3 /app/scripts/compact_history.py"

Safe to run multiple times — uses INSERT OR IGNORE for daily rollups.
"""

import argparse
import sqlite3
import sys
from datetime import datetime


def compact(db_path: str, *, batch_size: int = 50000,
            drop_old: bool = False) -> None:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    total = conn.execute(
        "SELECT COUNT(*) FROM availability_history"
    ).fetchone()[0]
    print(f"Compacting {total:,} rows from availability_history...")

    # Process in batches by ROWID range
    processed = 0
    min_id = conn.execute(
        "SELECT MIN(id) FROM availability_history"
    ).fetchone()[0] or 0
    max_id = conn.execute(
        "SELECT MAX(id) FROM availability_history"
    ).fetchone()[0] or 0

    # Track last-seen status per (campground, site, date) for transitions
    last_status: dict[tuple[str, str, str], str] = {}

    cursor_id = min_id
    while cursor_id <= max_id:
        rows = conn.execute(
            "SELECT campground_id, site_id, date, status, source,"
            " observed_at FROM availability_history"
            " WHERE id >= ? AND id < ? ORDER BY id",
            (cursor_id, cursor_id + batch_size),
        ).fetchall()

        for r in rows:
            key = (r["campground_id"], r["site_id"], r["date"])
            old = last_status.get(key, "")

            # Upsert daily
            conn.execute(
                "INSERT INTO availability_daily"
                " (campground_id, site_id, date, status, source,"
                "  first_seen, last_seen, observation_count)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, 1)"
                " ON CONFLICT(campground_id, site_id, date) DO UPDATE"
                " SET status=excluded.status,"
                " last_seen=excluded.last_seen,"
                " observation_count=observation_count+1",
                (r["campground_id"], r["site_id"], r["date"],
                 r["status"], r["source"],
                 r["observed_at"], r["observed_at"]),
            )

            # Transition if changed
            if r["status"] != old:
                conn.execute(
                    "INSERT INTO status_transitions"
                    " (campground_id, site_id, date, old_status,"
                    "  new_status, source, observed_at)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (r["campground_id"], r["site_id"], r["date"],
                     old, r["status"], r["source"], r["observed_at"]),
                )

            last_status[key] = r["status"]

        conn.commit()
        processed += len(rows)
        cursor_id += batch_size
        pct = processed / total * 100 if total else 100
        print(f"  {processed:,} / {total:,} ({pct:.0f}%)")

    print(f"\nDone. Daily rollup rows: "
          f"{conn.execute('SELECT COUNT(*) FROM availability_daily').fetchone()[0]:,}")
    print(f"Transition rows: "
          f"{conn.execute('SELECT COUNT(*) FROM status_transitions').fetchone()[0]:,}")

    if drop_old:
        print("Dropping old availability_history rows...")
        conn.execute("DELETE FROM availability_history")
        conn.execute("VACUUM")
        conn.commit()
        print("VACUUMed. New DB size should be much smaller.")
    else:
        print("\nRun with --drop-old to remove the raw history after"
              " verifying rollups look correct.")

    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("db_path", default="/app/data/watches.db",
                        nargs="?")
    parser.add_argument("--drop-old", action="store_true",
                        help="Delete raw history after compaction")
    parser.add_argument("--batch-size", type=int, default=50000)
    args = parser.parse_args()
    compact(args.db_path, batch_size=args.batch_size,
            drop_old=args.drop_old)
