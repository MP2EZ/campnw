# Monitoring (v1.47)

How we know campable.co is up and its features work. Four layers, each
answering a different question — none replaces the others.

| Layer | Question | Cadence | Where |
|-------|----------|---------|-------|
| **UptimeRobot** | Is it down *right now*? | every 5 min | external service (you set up) |
| **Prod monitor** | Do the *features* work on prod? | daily | `.github/workflows/prod-monitor.yml` |
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

## Layer 3 — Release gate (`.github/workflows/playwright.yml`)

Unchanged by v1.47. Per-PR smoke + nightly full E2E against **staging**
(`campnw-staging`), opening an issue on nightly failure. This is the
pre-promotion safety net, not a production monitor.

---

## Layer 4 — PostHog

Passive real-user product analytics + error tracking. Keeps the "what did a real
user experience" record that synthetic checks can't reproduce.
