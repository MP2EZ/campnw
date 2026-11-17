"""Dry run of the booking-tips pipeline: summary stats next to generated tips.

Read-only. Both databases open with sqlite `mode=ro`, so nothing can be written,
and `update_booking_tips` is never called. Haiku is called once per campground
that has enough history (ANTHROPIC_API_KEY must be set).

    python scripts/booking_tips_dry_run.py --limit 10
    python scripts/booking_tips_dry_run.py 232466 233136
    python scripts/booking_tips_dry_run.py --as-of 2026-08-01

On prod, run it over `fly ssh console -a campnw` against the installed package.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sqlite3
import time
from datetime import date

from pnw_campsites import posthog_client
from pnw_campsites.analytics import patterns
from pnw_campsites.monitor.db import DEFAULT_DB_PATH as WATCH_DB_PATH
from pnw_campsites.registry.db import DEFAULT_DB_PATH as REGISTRY_DB_PATH

# Haiku 4.5, USD per million tokens.
_PRICE_IN = 1.0
_PRICE_OUT = 5.0


def _connect_ro(path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


class _ReadOnlyWatchDB:
    """Stands in for WatchDB, whose constructor runs migrations (writes)."""

    def __init__(self, path) -> None:
        self._conn = _connect_ro(path)


class _UsageMeter:
    """Wraps the Anthropic client to record tokens, latency and errors."""

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self._real = posthog_client.get_anthropic_client

    def install(self) -> None:
        posthog_client.get_anthropic_client = self._client

    def _client(self, api_key: str):
        client = self._real(api_key)
        create = client.messages.create
        meter = self

        async def metered(**kwargs):
            start = time.monotonic()
            call: dict = {}
            meter.calls.append(call)
            try:
                resp = await create(**kwargs)
            except BaseException as exc:
                call["error"] = repr(exc)
                raise
            finally:
                call["seconds"] = round(time.monotonic() - start, 2)
            call["in"] = resp.usage.input_tokens
            call["out"] = resp.usage.output_tokens
            call["raw"] = resp.content[0].text
            return resp

        client.messages.create = metered
        return client

    def cost(self) -> float:
        tokens_in = sum(c.get("in", 0) for c in self.calls)
        tokens_out = sum(c.get("out", 0) for c in self.calls)
        return (tokens_in * _PRICE_IN + tokens_out * _PRICE_OUT) / 1e6


def _status_mix(db: _ReadOnlyWatchDB, cg_id: str) -> dict[str, int]:
    rows = db._conn.execute(
        "SELECT status, COUNT(*) FROM availability_daily"
        " WHERE campground_id=? GROUP BY status ORDER BY 2 DESC",
        (cg_id,),
    ).fetchall()
    return {r[0]: r[1] for r in rows}


def _default_ids(db: _ReadOnlyWatchDB, limit: int) -> list[str]:
    rows = db._conn.execute(
        "SELECT campground_id, COUNT(DISTINCT substr(last_seen, 1, 10)) AS days"
        " FROM availability_daily GROUP BY campground_id"
        " ORDER BY days DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [r[0] for r in rows]


async def run(args: argparse.Namespace) -> None:
    db = _ReadOnlyWatchDB(args.watch_db)
    registry = _connect_ro(args.registry_db)
    today = args.as_of
    meter = _UsageMeter()
    meter.install()

    for cg_id in args.ids or _default_ids(db, args.limit):
        row = registry.execute(
            "SELECT name, booking_system FROM campgrounds WHERE facility_id=?",
            (cg_id,),
        ).fetchone()
        name = row["name"] if row else ""
        summary = patterns.get_availability_summary(db, cg_id, today)
        before = len(meter.calls)
        tips = (
            await patterns.extract_booking_tips(db, cg_id, name, today)
            if summary else []
        )
        print(json.dumps({
            "campground_id": cg_id,
            "name": name,
            "booking_system": row["booking_system"] if row else None,
            "status_mix": _status_mix(db, cg_id),
            "summary": summary,
            "tips": tips,
            "llm_calls": meter.calls[before:],
        }, indent=1))

    print(json.dumps({
        "haiku_calls": len(meter.calls),
        "cost_usd": round(meter.cost(), 5),
    }))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("ids", nargs="*", help="campground facility ids")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument(
        "--as-of", type=date.fromisoformat, default=None,
        help="pretend today is this date (the staleness gate uses it)",
    )
    parser.add_argument("--watch-db", default=WATCH_DB_PATH)
    parser.add_argument("--registry-db", default=REGISTRY_DB_PATH)
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
