#!/usr/bin/env python3
"""Compact availability_history into daily rollups + transitions.

Run on production: fly ssh console -C "python3 /app/scripts/compact_history.py"

Safe to run multiple times — uses ON CONFLICT for daily rollups.
"""

import argparse
import sqlite3
import sys


def compact(db_path: str, *, batch_size: int = 500000,
            drop_old: bool = False) -> None:
    conn = sqlite3.connect(db_path)

    total = conn.execute(
        "SELECT COUNT(*) FROM availability_history"
    ).fetchone()[0]
    print(f"Compacting {total:,} rows from availability_history...",
          flush=True)

    if total == 0:
        print("Nothing to compact.")
        conn.close()
        return

    # Step 1: Bulk INSERT into availability_daily using SQL aggregation
    # This is orders of magnitude faster than row-by-row Python
    print("Step 1: Building daily rollups...", flush=True)
    conn.execute("""
        INSERT INTO availability_daily
            (campground_id, site_id, date, status, source,
             first_seen, last_seen, observation_count)
        SELECT
            campground_id, site_id, date,
            -- last status wins (max observed_at)
            (SELECT h2.status FROM availability_history h2
             WHERE h2.campground_id = h.campground_id
               AND h2.site_id = h.site_id
               AND h2.date = h.date
             ORDER BY h2.observed_at DESC LIMIT 1),
            source,
            MIN(observed_at),
            MAX(observed_at),
            COUNT(*)
        FROM availability_history h
        GROUP BY campground_id, site_id, date
        ON CONFLICT(campground_id, site_id, date) DO UPDATE SET
            status = excluded.status,
            last_seen = excluded.last_seen,
            observation_count = availability_daily.observation_count + excluded.observation_count
    """)
    conn.commit()

    daily_count = conn.execute(
        "SELECT COUNT(*) FROM availability_daily"
    ).fetchone()[0]
    print(f"  Daily rollup rows: {daily_count:,}", flush=True)

    # Step 2: Build transitions by finding status changes
    # Skip transitions if this is a re-run (idempotency)
    existing_transitions = conn.execute(
        "SELECT COUNT(*) FROM status_transitions"
    ).fetchone()[0]

    print(f"Step 2: Extracting transitions (existing: {existing_transitions:,})...",
          flush=True)

    # Use window function to detect changes — much faster than Python dict
    conn.execute("""
        INSERT INTO status_transitions
            (campground_id, site_id, date, old_status, new_status,
             source, observed_at)
        SELECT
            campground_id, site_id, date,
            COALESCE(prev_status, ''),
            status,
            source,
            observed_at
        FROM (
            SELECT
                campground_id, site_id, date, status, source, observed_at,
                LAG(status) OVER (
                    PARTITION BY campground_id, site_id, date
                    ORDER BY observed_at
                ) AS prev_status
            FROM availability_history
        )
        WHERE status != COALESCE(prev_status, '')
    """)
    conn.commit()

    trans_count = conn.execute(
        "SELECT COUNT(*) FROM status_transitions"
    ).fetchone()[0]
    print(f"  Transition rows: {trans_count:,}", flush=True)

    if drop_old:
        print("Step 3: Dropping old availability_history rows...", flush=True)
        conn.execute("DELETE FROM availability_history")
        print("  VACUUMing...", flush=True)
        conn.execute("VACUUM")
        conn.commit()
        print("  Done. DB size should be much smaller.", flush=True)
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
