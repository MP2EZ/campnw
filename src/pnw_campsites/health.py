"""Dependency health sweep — one cheap live call per external service.

Complements the black-box monitors (``/healthz``, ``prod-monitor.yml``). Those
drive the real user path, so they have the highest fidelity but the lowest
diagnostic resolution: they tell you *something* is wrong. This module tells you
*which dependency*.

Every check runs through the same client code the app uses in production, so a
check cannot silently drift from the real call path — the failure mode that
retired the old ``scripts/validate_apis.py``, which re-implemented the provider
requests with bare ``requests`` calls and could pass while ``providers/`` was
broken.

All checks are strictly READ-ONLY: no writes, no notifications sent, no state
mutated anywhere. Safe to point at production.
"""

from __future__ import annotations

import asyncio
import os
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Literal

import httpx

Status = Literal["ok", "slow", "fail", "skip"]

# Any check slower than this is reported "slow" — succeeded, but the dependency
# is degraded enough to hurt a real search. Per-check overrides below for the
# providers that are legitimately slow (WAF-impersonated, HTML-scraped).
DEFAULT_SLOW_MS = 2000
DEFAULT_TIMEOUT_S = 20.0

# Probe targets. Deliberately stable, well-known records — a check that fails
# because the probe target was decommissioned is a false alarm, so prefer
# flagship facilities over arbitrary ones.
PROBE_FACILITY_ID = "232464"  # Ohanapecosh, Mt. Rainier NP
PROBE_RA_PARK = ("402146", "cape-lookout-state-park", "OR")  # fallback; park_id, slug, state
PROBE_LATLON = (46.7860, -121.7350)  # Paradise, Mt. Rainier
SEATTLE = (47.6062, -122.3321)

POSTHOG_HOST_DEFAULT = "https://eu.i.posthog.com"
NTFY_SERVER_DEFAULT = "https://ntfy.sh"


class SkipCheck(Exception):  # noqa: N818 — a skip is not an error; "Error" would mislead
    """Raised by a check that cannot run here (optional dep absent, etc.)."""


@dataclass
class CheckResult:
    name: str
    category: str
    status: Status
    latency_ms: int | None = None
    detail: str = ""
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "category": self.category,
            "status": self.status,
            "latency_ms": self.latency_ms,
            "detail": self.detail,
            "error": self.error,
        }


@dataclass
class Check:
    name: str
    category: str
    fn: Callable[[], Awaitable[str]]
    slow_ms: int = DEFAULT_SLOW_MS
    # Env vars that must be set for the check to be meaningful. Missing ones
    # produce "skip", not "fail" — an unconfigured optional integration is not
    # an outage, and conflating the two trains you to ignore red.
    requires: tuple[str, ...] = field(default_factory=tuple)


# ---------------------------------------------------------------------------
# Checks — local data
# ---------------------------------------------------------------------------


async def _check_registry_db() -> str:
    from pnw_campsites.registry.db import DEFAULT_DB_PATH, CampgroundRegistry

    def _query() -> str:
        with CampgroundRegistry() as reg:
            total = reg.count()
            by_state = reg.count_by_state()
        if total == 0:
            raise RuntimeError(f"registry at {DEFAULT_DB_PATH} is empty")
        top = ", ".join(
            f"{s}:{n}" for s, n in sorted(by_state.items(), key=lambda kv: -kv[1])[:3]
        )
        return f"{total:,} campgrounds ({top})"

    return await asyncio.to_thread(_query)


async def _check_watch_db() -> str:
    from pnw_campsites.monitor.db import WatchDB

    def _query() -> str:
        db = WatchDB()
        try:
            watches = db.list_watches(enabled_only=True)
        finally:
            close = getattr(db, "close", None)
            if callable(close):
                close()
        return f"{len(watches)} active watch(es)"

    return await asyncio.to_thread(_query)


# ---------------------------------------------------------------------------
# Checks — booking providers
# ---------------------------------------------------------------------------


async def _check_recgov_ridb() -> str:
    from pnw_campsites.providers.recgov import RecGovClient

    async with RecGovClient(os.getenv("RIDB_API_KEY", "")) as client:
        _, total = await client.get_facilities("WA", limit=1)
    if total <= 0:
        raise RuntimeError("RIDB returned 0 WA camping facilities")
    return f"{total:,} WA facilities indexed"


async def _check_recgov_availability() -> str:
    from pnw_campsites.providers.recgov import RecGovClient

    # ~45 days out: far enough to be inside the booking window, near enough
    # that the month is released.
    month = date.today() + timedelta(days=45)
    # The availability endpoint is unauthenticated — the RIDB key is irrelevant
    # here, so an empty key still exercises the real code path.
    async with RecGovClient(os.getenv("RIDB_API_KEY", "")) as client:
        avail = await client.get_availability(PROBE_FACILITY_ID, month)
    n = len(avail.campsites)
    if n == 0:
        raise RuntimeError(f"facility {PROBE_FACILITY_ID} returned no campsites")
    return f"{n} sites for {month:%b %Y}"


async def _check_goingtocamp() -> str:
    from pnw_campsites.providers.goingtocamp import GoingToCampClient

    # Entering the context manager fetches /api/maps, which is itself the
    # WAF-bypass check: plain httpx gets a 403 here, chrome131 impersonation
    # does not.
    async with GoingToCampClient() as client:
        locations = await client.get_campground_locations()
    if not locations:
        raise RuntimeError("no campground locations returned")
    return f"{len(locations)} WA parks with campsites"


def _resolve_ra_probe() -> tuple[str, str, str]:
    """Pick a ReserveAmerica probe park from the registry, falling back to a constant.

    Reading the registry keeps the probe self-maintaining: re-seeding OR parks
    can change facility IDs, and a hardcoded ID that quietly 404s would report
    a provider outage that isn't one.
    """
    import contextlib

    from pnw_campsites.registry.db import CampgroundRegistry

    # A registry that cannot be read is reported by the registry.db check; here
    # it should only cost us the nicer probe target.
    with contextlib.suppress(Exception), CampgroundRegistry() as reg:
        for cg in reg.list_all():
            if str(cg.booking_system) == "or_state" and cg.booking_url_slug:
                return cg.facility_id, cg.booking_url_slug, cg.state
    return PROBE_RA_PARK


async def _check_reserveamerica() -> str:
    from pnw_campsites.providers.reserveamerica import ReserveAmericaClient

    park_id, slug, state = await asyncio.to_thread(_resolve_ra_probe)
    async with ReserveAmericaClient() as client:
        records = await client.ping(park_id, slug, state)
    return f"{records} record(s) for {slug}"


# ---------------------------------------------------------------------------
# Checks — enrichment services
# ---------------------------------------------------------------------------


async def _check_weather() -> str:
    from pnw_campsites.providers.weather import VisualCrossingClient

    lat, lon = PROBE_LATLON
    async with VisualCrossingClient(os.getenv("VISUAL_CROSSING_API_KEY", "")) as client:
        results, rate_limited = await client.fetch_normals(lat, lon, [(7, 15)])
    if rate_limited:
        raise RuntimeError("429 — daily quota (1,000 records) likely exhausted")
    if not results:
        raise RuntimeError("no normals returned")
    r = results[0]
    return f"Jul 15 normals {r['temp_high_f']}/{r['temp_low_f']}°F (costs 1 quota record)"


async def _check_mapbox() -> str:
    from pnw_campsites.mapbox import get_drive_time

    lat, lon = PROBE_LATLON
    res = await get_drive_time(SEATTLE, (lat, lon))
    return f"Seattle→Paradise {res['drive_minutes']} min / {res['drive_miles']} mi"


async def _check_nominatim() -> str:
    from pnw_campsites.geo import geocode_address

    lat, lon = await geocode_address("Leavenworth, WA")
    return f"geocoded to {lat:.3f},{lon:.3f}"


# ---------------------------------------------------------------------------
# Checks — platform services
# ---------------------------------------------------------------------------


async def _check_supabase() -> str:
    from pnw_campsites.auth import jwks_url

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(jwks_url())
    resp.raise_for_status()
    keys = resp.json().get("keys", [])
    if not keys:
        # A reachable JWKS with no keys is worse than a down one: every login
        # fails with a confusing 401 rather than an obvious outage.
        raise RuntimeError("JWKS returned no signing keys — all logins will fail")
    return f"{len(keys)} JWKS signing key(s)"


async def _check_stripe() -> str:
    from pnw_campsites import billing

    price_id = billing.pro_price_id()
    mode = "test" if os.getenv("STRIPE_SECRET_KEY", "").startswith("sk_test") else "live"

    def _query() -> str:
        # Same-package internal: reusing billing's client factory keeps the key
        # resolution and SDK version identical to what checkout actually uses.
        client = billing._get_client()
        if price_id == billing.STRIPE_PRO_PRICE_ID_DEFAULT:
            # Not an outage, but checkout is guaranteed to 400 — worth red.
            client.v1.prices.list(params={"limit": 1})
            raise RuntimeError(
                "STRIPE_PRO_PRICE_ID unset — checkout would use the placeholder price"
            )
        price = client.v1.prices.retrieve(price_id)
        if not price.active:
            raise RuntimeError(f"price {price_id} is INACTIVE — checkout will fail")
        amount = (price.unit_amount or 0) / 100
        interval = price.recurring.interval if price.recurring else "one-time"
        return f"{mode} mode, ${amount:.2f}/{interval} price active"

    return await asyncio.to_thread(_query)


async def _check_posthog() -> str:
    host = os.getenv("VITE_PUBLIC_POSTHOG_HOST", POSTHOG_HOST_DEFAULT).rstrip("/")
    token = os.getenv("VITE_PUBLIC_POSTHOG_PROJECT_TOKEN", "")
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"{host}/array/{token}/config")
    if resp.status_code == 401:
        raise RuntimeError("project token rejected (401)")
    resp.raise_for_status()
    return f"{host.split('//')[-1]} accepted project token"


async def _check_ntfy() -> str:
    server = os.getenv("NTFY_SERVER", NTFY_SERVER_DEFAULT).rstrip("/")
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"{server}/v1/health")
    resp.raise_for_status()
    if not resp.json().get("healthy"):
        raise RuntimeError("ntfy reports unhealthy")
    return f"{server.split('//')[-1]} healthy"


async def _check_pushover() -> str:
    # users/validate is Pushover's own credential check — it sends no message.
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            "https://api.pushover.net/1/users/validate",
            data={
                "token": os.getenv("PUSHOVER_API_TOKEN", ""),
                "user": os.getenv("PUSHOVER_USER_KEY", ""),
            },
        )
    body = resp.json()
    if body.get("status") != 1:
        raise RuntimeError(f"credentials rejected: {body.get('errors')}")
    return "credentials valid"


async def _check_anthropic() -> str:
    try:
        import anthropic
    except ImportError as exc:  # optional 'enrichment' dep group
        raise SkipCheck("anthropic package not installed") from exc

    def _query() -> str:
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))
        models = client.models.list(limit=1)
        return f"key valid, {len(models.data)} model(s) listed"

    return await asyncio.to_thread(_query)


# ---------------------------------------------------------------------------
# Registry of checks
# ---------------------------------------------------------------------------

CHECKS: list[Check] = [
    Check("registry.db", "data", _check_registry_db, slow_ms=500),
    Check("watch.db", "data", _check_watch_db, slow_ms=500),
    Check("rec.gov RIDB", "provider", _check_recgov_ridb, requires=("RIDB_API_KEY",)),
    Check("rec.gov availability", "provider", _check_recgov_availability),
    # Both state-park providers impersonate a browser TLS fingerprint and parse
    # large payloads; 2s is normal for them, so they get a wider band.
    Check("GoingToCamp (WA)", "provider", _check_goingtocamp, slow_ms=5000),
    Check("ReserveAmerica (OR)", "provider", _check_reserveamerica, slow_ms=6000),
    Check(
        "Visual Crossing",
        "enrich",
        _check_weather,
        requires=("VISUAL_CROSSING_API_KEY",),
    ),
    Check("Mapbox", "enrich", _check_mapbox, requires=("MAPBOX_ACCESS_TOKEN",)),
    Check("Nominatim", "enrich", _check_nominatim, slow_ms=3000),
    Check("Supabase auth", "platform", _check_supabase, requires=("SUPABASE_URL",)),
    Check("Stripe", "platform", _check_stripe, requires=("STRIPE_SECRET_KEY",)),
    Check(
        "PostHog",
        "platform",
        _check_posthog,
        requires=("VITE_PUBLIC_POSTHOG_PROJECT_TOKEN",),
    ),
    Check("ntfy", "notify", _check_ntfy),
    Check(
        "Pushover",
        "notify",
        _check_pushover,
        requires=("PUSHOVER_API_TOKEN", "PUSHOVER_USER_KEY"),
    ),
    Check("Anthropic", "llm", _check_anthropic, requires=("ANTHROPIC_API_KEY",)),
]


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


# Modules each check imports lazily. Importing them inside a timed check blocks
# the whole event loop — curl_cffi, stripe and anthropic take seconds to load —
# so the cost lands on whichever checks happen to be awaiting, and an unwarmed
# sweep reported a local SQLite count at ~2s. Warming up front makes the
# reported latency service time rather than import time.
_PRELOAD_MODULES = (
    "pnw_campsites.registry.db",
    "pnw_campsites.monitor.db",
    "pnw_campsites.providers.recgov",
    "pnw_campsites.providers.goingtocamp",
    "pnw_campsites.providers.reserveamerica",
    "pnw_campsites.providers.weather",
    "pnw_campsites.mapbox",
    "pnw_campsites.geo",
    "pnw_campsites.auth",
    "pnw_campsites.billing",
    "anthropic",
)


def _preload_modules() -> None:
    """Import every check's dependencies before any timing begins."""
    import contextlib
    import importlib

    for name in _PRELOAD_MODULES:
        # A genuinely broken import resurfaces as that check's own failure, with
        # a useful message; suppressing it here only skips the warmup.
        with contextlib.suppress(Exception):
            importlib.import_module(name)


def _short_error(exc: BaseException) -> str:
    """One-line error text — stack traces belong in logs, not a status table."""
    if isinstance(exc, httpx.HTTPStatusError):
        return f"HTTP {exc.response.status_code} from {exc.request.url.host}"
    text = str(exc).strip().splitlines()[0] if str(exc).strip() else exc.__class__.__name__
    return f"{exc.__class__.__name__}: {text}" if text != exc.__class__.__name__ else text


async def run_check(check: Check, timeout: float = DEFAULT_TIMEOUT_S) -> CheckResult:
    """Run one check, converting any outcome into a CheckResult.

    Never raises: a sweep that dies on its first bad dependency is useless,
    since the whole point is seeing every dependency at once.
    """
    missing = [var for var in check.requires if not os.getenv(var)]
    if missing:
        return CheckResult(
            check.name,
            check.category,
            "skip",
            detail=f"not configured ({', '.join(missing)})",
        )

    start = time.perf_counter()
    try:
        detail = await asyncio.wait_for(check.fn(), timeout=timeout)
    except SkipCheck as exc:
        return CheckResult(check.name, check.category, "skip", detail=str(exc))
    except TimeoutError:
        return CheckResult(
            check.name,
            check.category,
            "fail",
            latency_ms=int(timeout * 1000),
            error=f"timed out after {timeout:g}s",
        )
    except Exception as exc:
        elapsed = int((time.perf_counter() - start) * 1000)
        return CheckResult(
            check.name, check.category, "fail", latency_ms=elapsed, error=_short_error(exc)
        )

    elapsed = int((time.perf_counter() - start) * 1000)
    status: Status = "slow" if elapsed > check.slow_ms else "ok"
    return CheckResult(check.name, check.category, status, latency_ms=elapsed, detail=detail)


async def run_all(
    checks: list[Check] | None = None,
    *,
    timeout: float = DEFAULT_TIMEOUT_S,
    categories: set[str] | None = None,
) -> list[CheckResult]:
    """Run checks concurrently and return results in declaration order."""
    selected = list(checks if checks is not None else CHECKS)
    if categories:
        selected = [c for c in selected if c.category in categories]
    # Off-thread so an API caller's event loop keeps serving during warmup.
    await asyncio.to_thread(_preload_modules)
    return list(await asyncio.gather(*(run_check(c, timeout) for c in selected)))


def summarize(results: list[CheckResult], *, strict: bool = False) -> dict:
    """Aggregate results into a status envelope. ``strict`` treats slow as failing."""
    counts = {s: sum(1 for r in results if r.status == s) for s in ("ok", "slow", "fail", "skip")}
    failed = counts["fail"] > 0 or (strict and counts["slow"] > 0)
    if counts["fail"]:
        overall = "fail"
    elif counts["slow"]:
        overall = "degraded"
    else:
        overall = "ok"
    return {
        "status": overall,
        "healthy": not failed,
        "counts": counts,
        "checks": [r.to_dict() for r in results],
    }
