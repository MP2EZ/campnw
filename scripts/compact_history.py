#!/usr/bin/env python3
"""Compact availability_history into daily rollups.

Run on production: fly ssh console -C "python3 /app/scripts/compact_history.py"

Processes in batches of campground_ids to avoid OOM on small VMs.
Safe to run multiple times — uses ON CONFLICT upsert.
"""

import argparse
import sqlite3


def compact(db_path: str, *, drop_old: bool = False) -> None:
    conn = sqlite3.connect(db_path, timeout=120)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")

    total = conn.execute(
        "SELECT COUNT(*) FROM availability_history"
    ).fetchone()[0]
    print(f"Compacting {total:,} rows from availability_history...",
          flush=True)

    if total == 0:
        print("Nothing to compact.")
        conn.close()
        return

    # Get distinct campground_ids to process in batches
    cg_ids = [r[0] for r in conn.execute(
        "SELECT DISTINCT campground_id FROM availability_history"
    ).fetchall()]
    print(f"Processing {len(cg_ids)} campgrounds...", flush=True)

    for i, cg_id in enumerate(cg_ids):
        conn.execute("""
            INSERT INTO availability_daily
                (campground_id, site_id, date, status, source,
                 first_seen, last_seen, observation_count)
            SELECT
                campground_id, site_id, date,
                status, source,
                MIN(observed_at), MAX(observed_at), COUNT(*)
            FROM availability_history
            WHERE campground_id = ?
            GROUP BY campground_id, site_id, date
            ON CONFLICT(campground_id, site_id, date) DO UPDATE SET
                last_seen = MAX(availability_daily.last_seen, excluded.last_seen),
                observation_count = availability_daily.observation_count + excluded.observation_count
        """, (cg_id,))
        conn.commit()

        if (i + 1) % 10 == 0 or i + 1 == len(cg_ids):
            print(f"  {i + 1}/{len(cg_ids)} campgrounds", flush=True)

    daily_count = conn.execute(
        "SELECT COUNT(*) FROM availability_daily"
    ).fetchone()[0]
    print(f"Daily rollup rows: {daily_count:,}", flush=True)

    trans_count = conn.execute(
        "SELECT COUNT(*) FROM status_transitions"
    ).fetchone()[0]
    print(f"Transition rows (from live polling): {trans_count:,}", flush=True)

    if drop_old:
        print("Dropping old availability_history rows...", flush=True)
        conn.execute("DELETE FROM availability_history")
        conn.commit()
        print("VACUUMing...", flush=True)
        conn.execute("VACUUM")
        print("Done.", flush=True)
    else:
        print("\nRun with --drop-old to remove the raw history after"
              " verifying rollups look correct.", flush=True)

    conn.close()
    print("Complete.", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("db_path", default="/app/data/watches.db",
                        nargs="?")
    parser.add_argument("--drop-old", action="store_true",
                        help="Delete raw history after compaction")
    args = parser.parse_args()
    compact(args.db_path, drop_old=args.drop_old)
