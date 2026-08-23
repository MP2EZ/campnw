# Monitoring (v1.47)

How we know campable.co is up and its features work. Five layers, each
answering a different question — none replaces the others.

| Layer | Question | Cadence | Where |
|-------|----------|---------|-------|
| **UptimeRobot** | Is it down *right now*? | every 5 min | external service (you set up) |
| **Prod monitor** | Do the *features* work on prod? | daily | `.github/workflows/prod-monitor.yml` |
| **Dependency sweep** | *Which dependency* is broken? | on demand / daily | `python -m pnw_campsites doctor` |
| **Release gate** | Is the *next release* safe? | nightly / per-PR | `.github/workflows/playwright.yml` (staging) |
| **PostHog** | What broke for a *real user*? | passive | PostHog error tracking |

**Why not just PostHog?** PostHog is *passive* — it only captures an error once
a real user trips it. If the site dies at 3am, PostHog stays quiet until someone
shows up and gets hurt. The first two layers are *active / synthetic*: a robot
drives the live site on a schedule so we hear about breakage first.

**Why not just the existing nightly?** `playwright.yml` is a release *gate* — it
deploys `dev` HEAD to **staging** and tests that before promotion. It never
touches production, so a Fly outage, expired TLS cert, or Supabase incident on
the *live* site is invisible to it.

---

## Layer 1 — UptimeRobot (you set up, ~5 min)

Fast "is it down" detection on the real `/healthz` endpoint (added in v1.47 —
pings SQLite, returns `{"status":"ok","db":true,"version":"..."}`, or **503**
when the DB is unreachable).

1. Create a free account at <https://uptimerobot.com>.
2. **Add New Monitor**:
   - Type: **HTTP(s)**
   - URL: `https://campable.co/healthz`
   - Interval: **5 minutes**
   - **Keyword monitoring**: alert if the response does **not** contain
     `"status":"ok"`. This way a 503 (DB degraded) *or* a missing keyword both
     trigger — not just a hard connection failure.
3. **Alert contact**: add your Outlook address (`…@palouselabs.com`). UptimeRobot
   emails on down + recovery.

> Note: `/healthz` ships with v1.47. Until that release reaches prod, point the
> monitor at `https://campable.co/` (plain reachability) and switch to
> `/healthz` once deployed.

---

## Layer 2 — Daily prod monitor (built in, `.github/workflows/prod-monitor.yml`)

Runs daily at **15:00 UTC** (and on demand via *Actions → Prod Monitor → Run
workflow*). It checks, against live `https://campable.co`:

1. `/healthz` returns `"status":"ok"` (app + DB).
2. `/api/search` returns a well-shaped response (DB + provider pipeline).
3. `e2e/tests/prod-smoke.spec.ts` — a **read-only, anonymous** Playwright smoke:
   homepage renders, search API works, pricing page renders, SEO state index
   renders.

It is **strictly non-mutating** — no signup, no Stripe, no writes — so it is
safe to point at production. (The four flows in `e2e/tests/` *do* mutate state
and run only against staging.)

On failure it: uploads the Playwright report, **emails you via Resend**, and
**opens a GitHub issue** labelled `prod-down`.

### Required repo configuration

Set under *Settings → Secrets and variables → Actions*:

| Kind | Name | Value |
|------|------|-------|
| **Secret** | `RESEND_API_KEY` | your Resend API key |
| Variable | `ALERT_EMAIL_TO` | your Outlook address, e.g. `you@palouselabs.com` |
| Variable | `ALERT_EMAIL_FROM` | *(optional)* sender, default `Campable Monitor <alerts@campable.co>` — the domain must be verified in Resend |

If `RESEND_API_KEY` / `ALERT_EMAIL_TO` are unset, the email step is skipped with
a warning and the GitHub issue still fires (so you're never silently blind).

> The `ALERT_EMAIL_FROM` domain must be verified in Resend. If `campable.co`
> isn't verified there yet, either verify it or set `ALERT_EMAIL_FROM` to a
> domain that is.

---

## Layer 2b — Dependency sweep (`python -m pnw_campsites doctor`)

The other layers are **black-box**: they drive the real user path, which gives
the highest-fidelity signal and the lowest-resolution diagnosis. When the daily
monitor goes red it tells you *search broke*, not *ReserveAmerica is 403ing*.

`doctor` is the **white-box** counterpart: one cheap, read-only live call per
dependency, run concurrently, reported as a table.

```
$ .venv/bin/python3 -m pnw_campsites doctor

  DATA      registry.db           ok       243ms  1,368 campgrounds (CA:335, OR:302, ID:219)
  DATA      watch.db              ok       243ms  10 active watch(es)
  PROVIDER  rec.gov RIDB          ok     1,991ms  191 WA facilities indexed
  PROVIDER  rec.gov availability  ok       299ms  151 sites for Oct 2026
  PROVIDER  GoingToCamp (WA)      ok       960ms  75 WA parks with campsites
  PROVIDER  ReserveAmerica (OR)   FAIL     502ms  WAFBlockedError: WAF blocked the request
  ENRICH    Visual Crossing       ok       561ms  Jul 15 normals 69.7/43.3°F
  ENRICH    Mapbox                ok       240ms  Seattle→Paradise 153 min / 107.5 mi
  ENRICH    Nominatim             ok       576ms  geocoded to 47.597,-120.661
  PLATFORM  Supabase auth         ok       293ms  1 JWKS signing key(s)
  PLATFORM  Stripe                ok       377ms  live mode, $5.00/month price active
  PLATFORM  PostHog               ok       708ms  eu.i.posthog.com accepted project token
  NOTIFY    ntfy                  ok       360ms  ntfy.sh healthy
  NOTIFY    Pushover              skip            not configured (PUSHOVER_API_TOKEN, ...)
  LLM       Anthropic             ok       320ms  key valid, 1 model(s) listed

  13 ok · 1 fail · 1 skip
```

### Flags

| Flag | Effect |
|------|--------|
| `--json` | Machine-readable envelope, for CI |
| `--only data,provider,...` | Restrict to categories: `data`, `provider`, `enrich`, `platform`, `notify`, `llm` |
| `--timeout 20` | Per-check timeout in seconds |
| `--strict` | Exit non-zero on `slow` too, not just `fail` |

Exit code is `0` when healthy, `1` when anything failed — so it drops into any
shell or CI step directly.

### Status semantics

- **ok** — succeeded within the check's latency threshold.
- **slow** — succeeded, but slow enough to degrade a real search. Non-fatal by
  default; `--strict` promotes it to a failure.
- **fail** — errored, timed out, or returned something unusable.
- **skip** — the credentials aren't configured here. **Not** a failure: an
  unconfigured optional integration is not an outage, and rendering it red is
  how you train yourself to ignore red.

### Where to run it

| From | Command | Sees |
|------|---------|------|
| Laptop | `.venv/bin/python3 -m pnw_campsites doctor` | Your `.env`, your IP |
| Prod | `fly ssh console -a campnw -C "python -m pnw_campsites doctor"` | Fly secrets, prod's IP — **the authoritative view** |
| Browser | `GET /api/admin/health/deep` (admin session) | Same as prod, returns 503 when unhealthy |
| CI | daily, inside `prod-monitor.yml` | Providers only — see caveat below |

> **The IP matters.** Both state-park providers sit behind WAFs that block by
> address. A `FAIL` on your laptop can be your own IP being blocked while prod
> is fine — and vice versa. Confirm against prod before concluding anything.

That is exactly why the CI step is `continue-on-error: true`. It runs from a
GitHub runner, so it is a **diagnostic attached to the run, not a detector**;
the `/healthz` and `/api/search` steps remain the things that actually decide
whether the monitor fails. Its result is written to the run summary as a table
and uploaded as `dependency-sweep.json`.

### Design note: it uses the real client code

Every check calls the same client the app uses in production — `RecGovClient`,
`GoingToCampClient`, `billing.pro_price_id()`, `auth.jwks_url()`. This is
deliberate. Its predecessor, `scripts/validate_apis.py`, re-implemented the
provider requests with bare `requests` calls, so it could pass while
`providers/` was broken (and fail while it was fine). A health check that
doesn't share a code path with the thing it checks eventually lies.

The one exception is `ReserveAmericaClient.ping()`, added because
`get_availability()` parses a ~2MB Redux payload per 14-day window — far too
expensive for a probe. `ping()` reuses the same session, TLS impersonation and
WAF path in a single request.

---

## Layer 3 — Release gate (`.github/workflows/playwright.yml`)

Unchanged by v1.47. Per-PR smoke + nightly full E2E against **staging**
(`campnw-staging`), opening an issue on nightly failure. This is the
pre-promotion safety net, not a production monitor.

---

## Layer 4 — PostHog

Passive real-user product analytics + error tracking. Keeps the "what did a real
user experience" record that synthetic checks can't reproduce.
