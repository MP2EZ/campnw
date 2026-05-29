"""Idempotent fixture seeder for Maestro E2E flows.

Creates the three pre-seeded users that Flows 2, 3, and 4 depend on:

  ${prefix}free-3watches@maestro.test  → 3 active watches (4th hits limit)
  ${prefix}free-3planner@maestro.test  → 3 planner sessions this month (4th hits limit)
  ${prefix}pro@maestro.test            → active Pro subscription (cancel/reactivate)

Designed to run inside the campable container against the live SQLite
volume — typically invoked from CI as:

    flyctl ssh console -a campnw-pr-${PR} \\
      -C "python scripts/seed_maestro_fixtures.py"

The plan called for a `.sql` file but Supabase auth user creation requires
HTTP calls to the Admin API (a service-role JWT against
`/auth/v1/admin/users`). Pure SQL can't do that. This script does both:
HTTP for the auth layer, SQLite for the app layer.

Required env:
  SUPABASE_URL                — https://<project>.supabase.co
  SUPABASE_SERVICE_ROLE_KEY   — admin JWT (NEVER ship to frontend)
  MAESTRO_FIXTURE_PASSWORD    — shared password for all fixture users
  CAMPABLE_DB_PATH            — defaults to /app/data/registry.db

Optional:
  MAESTRO_FIXTURE_PREFIX      — defaults to "maestro-fixture-"
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
PASSWORD = os.environ["MAESTRO_FIXTURE_PASSWORD"]
DB_PATH = os.environ.get("CAMPABLE_DB_PATH", "/app/data/registry.db")
PREFIX = os.environ.get("MAESTRO_FIXTURE_PREFIX", "maestro-fixture-")

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
        if e.code != 422:  # already exists
            raise
        # Look up existing user
        lookup = urlrequest.Request(
            f"{SUPABASE_URL}/auth/v1/admin/users?email={email}",
            headers={
                "apikey": SERVICE_ROLE,
                "Authorization": f"Bearer {SERVICE_ROLE}",
            },
        )
        with urlrequest.urlopen(lookup) as resp:
            body = json.loads(resp.read())
        users = body.get("users", [])
        if not users:
            raise RuntimeError(f"User {email} exists per 422 but not findable")
        return users[0]["id"]


def upsert_user(
    conn: sqlite3.Connection,
    email: str,
    supabase_id: str,
    *,
    subscription_status: str = "free",
    stripe_customer_id: str = "",
    subscription_id: str = "",
    subscription_expires_at: str | None = None,
) -> int:
    """Insert or update the local user row. Returns user_id."""
    row = conn.execute(
        "SELECT id FROM users WHERE email = ?", (email,)
    ).fetchone()
    if row is None:
        cur = conn.execute(
            "INSERT INTO users (email, password_hash, supabase_id, "
            "subscription_status, stripe_customer_id, subscription_id, "
            "subscription_expires_at, created_at) "
            "VALUES (?, '', ?, ?, ?, ?, ?, ?)",
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
    # Use unique-ish facility IDs so we don't collide with anything in
    # the production catalog and so a 4th create attempt by the flow
    # against a real recgov ID still triggers the 402 (not a dedupe).
    for i in range(needed):
        conn.execute(
            "INSERT INTO watches (facility_id, name, start_date, end_date, "
            "user_id, enabled, created_at, booking_system) "
            "VALUES (?, ?, ?, ?, ?, 1, ?, 'recgov')",
            (f"maestro-fixture-{user_id}-{i}",
             f"Maestro Fixture Watch {i + 1}",
             start, end, user_id, NOW_ISO),
        )


def ensure_planner_sessions(
    conn: sqlite3.Connection, user_id: int, count: int
) -> None:
    """Ensure user has `count` planner_sessions in the current calendar month."""
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
            (user_id, f"maestro-fixture-session-{user_id}-{i}", ts),
        )


def main() -> int:
    fixtures = [
        ("free-3watches", "free", 3, 0),
        ("free-3planner", "free", 0, 3),
        ("pro", "pro", 0, 0),
    ]
    conn = sqlite3.connect(DB_PATH)
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
                stripe_customer_id="cus_maestro_fixture_pro" if status == "pro" else "",
                subscription_id="sub_maestro_fixture_pro" if status == "pro" else "",
                subscription_expires_at=PRO_EXPIRES if status == "pro" else None,
            )
            if watch_count:
                ensure_watches(conn, user_id, watch_count)
            if planner_count:
                ensure_planner_sessions(conn, user_id, planner_count)
        conn.commit()
    finally:
        conn.close()
    print("✓ Maestro fixtures seeded")
    return 0


if __name__ == "__main__":
    sys.exit(main())
