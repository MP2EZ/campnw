"""Idempotent fixture seeder for Playwright E2E flows.

Creates the three pre-seeded users that Flows 2, 3, and 4 depend on:

  ${prefix}free-3watches@maestro.test  → 3 active watches (4th hits limit)
  ${prefix}free-3planner@maestro.test  → 3 planner sessions this month (4th hits limit)
  ${prefix}pro@maestro.test            → active Pro subscription (cancel/reactivate)

The @maestro.test domain is kept (not @playwright.test) because v1.41's
Phase 0 spike already created real auth users on this domain in prod
Supabase, and renaming would orphan them.

Designed to run inside the campable container against the live SQLite
volume — typically invoked from CI as:

    flyctl ssh console -a campnw-pr-${PR} \\
      -C "python scripts/seed_e2e_fixtures.py"

Required env:
  SUPABASE_URL                — https://<project>.supabase.co
  SUPABASE_SERVICE_ROLE_KEY   — admin JWT (NEVER ship to frontend)
  E2E_FIXTURE_PASSWORD        — shared password for all fixture users
  CAMPABLE_DB_PATH            — defaults to /app/data/registry.db

Optional:
  E2E_FIXTURE_PREFIX          — defaults to "e2e-fixture-"
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from urllib import request as urlrequest
from urllib.error import HTTPError

SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SERVICE_ROLE = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
PASSWORD = os.environ["E2E_FIXTURE_PASSWORD"]
DB_PATH = os.environ.get("CAMPABLE_DB_PATH", "/app/data/watches.db")
PREFIX = os.environ.get("E2E_FIXTURE_PREFIX", "e2e-fixture-")

NOW = datetime.now(timezone.utc)
NOW_ISO = NOW.isoformat()
PRO_EXPIRES = (NOW + timedelta(days=30)).isoformat()


def admin_create_user(email: str) -> str:
    """Create a confirmed Supabase auth user. Returns the user's uuid.

    Idempotent: if the email already exists, returns the existing uuid.
    """
    payload = json.dumps({
        "email": email,
        "password": PASSWORD,
        "email_confirm": True,
    }).encode()
    req = urlrequest.Request(
        f"{SUPABASE_URL}/auth/v1/admin/users",
        data=payload,
        headers={
            "apikey": SERVICE_ROLE,
            "Authorization": f"Bearer {SERVICE_ROLE}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlrequest.urlopen(req) as resp:
            return json.loads(resp.read())["id"]
    except HTTPError as e:
        if e.code != 422:
            raise
        # Supabase Admin GET /admin/users?email=... does NOT filter by
        # email — it returns the first page of users regardless of the
        # query param. Paginate and filter client-side instead.
        page = 1
        while True:
            lookup = urlrequest.Request(
                f"{SUPABASE_URL}/auth/v1/admin/users?page={page}&per_page=200",
                headers={
                    "apikey": SERVICE_ROLE,
                    "Authorization": f"Bearer {SERVICE_ROLE}",
                },
            )
            with urlrequest.urlopen(lookup) as resp:
                body = json.loads(resp.read())
            users = body.get("users", [])
            if not users:
                break
            for u in users:
                if (u.get("email") or "").lower() == email.lower():
                    return u["id"]
            if len(users) < 200:
                break
            page += 1
        raise RuntimeError(f"User {email} exists per 422 but not found across pages")


def upsert_user(
    conn: sqlite3.Connection,
    email: str,
    supabase_id: str,
    *,
    subscription_status: str = "free",
    stripe_customer_id: str = "",
    subscription_id: str = "",
    subscription_expires_at: str = "",
) -> int:
    row = conn.execute(
        "SELECT id FROM users WHERE email = ?", (email,)
    ).fetchone()
    if row is None:
        # Pre-set onboarding_complete=1 so fixture users skip the welcome
        # modal — eliminates a flaky race in fixture-based tests.
        cur = conn.execute(
            "INSERT INTO users (email, password_hash, supabase_id, "
            "subscription_status, stripe_customer_id, subscription_id, "
            "subscription_expires_at, created_at, onboarding_complete) "
            "VALUES (?, '', ?, ?, ?, ?, ?, ?, 1)",
            (email, supabase_id, subscription_status, stripe_customer_id,
             subscription_id, subscription_expires_at, NOW_ISO),
        )
        return cur.lastrowid
    user_id = row[0]
    conn.execute(
        "UPDATE users SET supabase_id = ?, subscription_status = ?, "
        "stripe_customer_id = ?, subscription_id = ?, "
        "subscription_expires_at = ? WHERE id = ?",
        (supabase_id, subscription_status, stripe_customer_id,
         subscription_id, subscription_expires_at, user_id),
    )
    return user_id


def ensure_watches(conn: sqlite3.Connection, user_id: int, count: int) -> None:
    existing = conn.execute(
        "SELECT COUNT(*) FROM watches WHERE user_id = ?", (user_id,)
    ).fetchone()[0]
    needed = count - existing
    if needed <= 0:
        return
    start = (NOW + timedelta(days=14)).date().isoformat()
    end = (NOW + timedelta(days=21)).date().isoformat()
    for i in range(needed):
        conn.execute(
            "INSERT INTO watches (facility_id, name, start_date, end_date, "
            "user_id, enabled, created_at, booking_system) "
            "VALUES (?, ?, ?, ?, ?, 1, ?, 'recgov')",
            (f"e2e-fixture-{user_id}-{i}",
             f"E2E Fixture Watch {i + 1}",
             start, end, user_id, NOW_ISO),
        )


def ensure_planner_sessions(
    conn: sqlite3.Connection, user_id: int, count: int
) -> None:
    month_start = NOW.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    existing = conn.execute(
        "SELECT COUNT(*) FROM planner_sessions "
        "WHERE user_id = ? AND started_at >= ?",
        (user_id, month_start.isoformat()),
    ).fetchone()[0]
    needed = count - existing
    if needed <= 0:
        return
    for i in range(needed):
        ts = (NOW - timedelta(hours=i + 1)).isoformat()
        conn.execute(
            "INSERT INTO planner_sessions (user_id, session_token, started_at) "
            "VALUES (?, ?, ?)",
            (user_id, f"e2e-fixture-session-{user_id}-{i}", ts),
        )


def main() -> int:
    # Bootstrap schema + run migrations by instantiating WatchDB once.
    # On a fresh staging volume the users/watches/planner_sessions tables
    # don't exist yet — FastAPI normally creates them at startup. The
    # seed script runs over flyctl ssh without going through FastAPI,
    # so we trigger the same bootstrap here.
    from pnw_campsites.monitor.db import WatchDB

    WatchDB(DB_PATH).close()

    fixtures = [
        ("free-3watches", "free", 3, 0),
        ("free-3planner", "free", 0, 3),
        ("pro", "pro", 0, 0),
    ]
    conn = sqlite3.connect(DB_PATH)

    # Clean up any pre-existing fixture rows. ON DELETE CASCADE clears
    # their watches and planner_sessions. Idempotent: no-op on a fresh
    # volume. Necessary on volumes that ran a buggy pre-2026-05-30
    # version of this script that wrote rows with wrong supabase_ids.
    conn.execute(f"DELETE FROM users WHERE email LIKE '{PREFIX}%'")
    conn.commit()
    try:
        for slug, status, watch_count, planner_count in fixtures:
            email = f"{PREFIX}{slug}@maestro.test"
            print(f"→ {email} ({status})")
            supabase_id = admin_create_user(email)
            user_id = upsert_user(
                conn,
                email,
                supabase_id,
                subscription_status=status,
                subscription_expires_at=PRO_EXPIRES if status == "pro" else "",
            )
            if watch_count:
                ensure_watches(conn, user_id, watch_count)
            if planner_count:
                ensure_planner_sessions(conn, user_id, planner_count)
            # DIAGNOSTIC: read back the row immediately to confirm INSERT
            # actually wrote the expected subscription_status.
            verify = conn.execute(
                "SELECT id, substr(supabase_id, 1, 8), subscription_status FROM users WHERE email = ?",
                (email,),
            ).fetchone()
            print(f"    verified: id={verify[0]} sup_id={verify[1]}... status={verify[2]}")
        conn.commit()
        # DIAGNOSTIC: verify rows still have expected status AFTER commit
        for slug, status, _, _ in fixtures:
            email = f"{PREFIX}{slug}@maestro.test"
            verify = conn.execute(
                "SELECT id, substr(supabase_id, 1, 8), subscription_status FROM users WHERE email = ?",
                (email,),
            ).fetchone()
            print(f"    post-commit {slug}: id={verify[0] if verify else None} sup_id={verify[1] + '...' if verify else None} status={verify[2] if verify else None}")
    finally:
        conn.close()
    print("✓ E2E fixtures seeded")
    return 0


if __name__ == "__main__":
    sys.exit(main())
