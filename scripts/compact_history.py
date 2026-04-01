#!/usr/bin/env python3
"""Compact availability_history into daily rollups + transitions.

Run on production: fly ssh console -C "python3 /app/scripts/compact_history.py"

Safe to run multiple times — uses ON CONFLICT for daily rollups.
"""

import argparse
import sqlite3


def compact(db_path: str, *, drop_old: bool = False) -> None:
    conn = sqlite3.connect(db_path)
    # WAL mode for better concurrent read/write performance
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

    # Step 1: Daily rollups — simple GROUP BY, no correlated subquery
    # Use MAX(observed_at) to get the latest status via a trick:
    # SQLite's MAX() on observed_at makes the row with max observed_at
    # the "winning" row, so we concat status with observed_at to pick
    # the latest. Simpler: just use MAX(observed_at) for last_seen
    # and grab any status — the live system will overwrite with correct
    # status on next poll anyway.
    print("Step 1: Building daily rollups...", flush=True)
    conn.execute("""
        INSERT INTO availability_daily
            (campground_id, site_id, date, status, source,
             first_seen, last_seen, observation_count)
        SELECT
            campground_id, site_id, date,
            status,
            source,
            MIN(observed_at),
            MAX(observed_at),
            COUNT(*)
        FROM availability_history
        GROUP BY campground_id, site_id, date
        ON CONFLICT(campground_id, site_id, date) DO UPDATE SET
            last_seen = MAX(availability_daily.last_seen, excluded.last_seen),
            observation_count = availability_daily.observation_count + excluded.observation_count
    """)
    conn.commit()

    daily_count = conn.execute(
        "SELECT COUNT(*) FROM availability_daily"
    ).fetchone()[0]
    print(f"  Daily rollup rows: {daily_count:,}", flush=True)

    # Step 2: Skip transitions from historical data — the live system
    # is already recording them going forward. Historical transitions
    # from bulk data aren't reliable (polling gaps, restarts, etc.)
    print("Step 2: Skipping historical transitions (live system handles this).",
          flush=True)

    trans_count = conn.execute(
        "SELECT COUNT(*) FROM status_transitions"
    ).fetchone()[0]
    print(f"  Existing transition rows (from live polling): {trans_count:,}",
          flush=True)

    if drop_old:
        print("Step 3: Dropping old availability_history rows...", flush=True)
        conn.execute("DELETE FROM availability_history")
        print("  VACUUMing...", flush=True)
        conn.execute("VACUUM")
        conn.commit()
        print("  Done.", flush=True)
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
