# PNW Campsite Tool

## What This Is
Personal tool for finding and monitoring campsite availability across the Pacific Northwest (WA, OR, ID). Not a product — built for a single user and friends. The core value: discovery ("what's available this weekend within 3 hours of Seattle?") across multiple booking systems, not just monitoring a single known campground.

## Tech Stack
- **Python 3.12+** — core library, API clients
- **SQLite** — campground registry, availability cache, watch state
- **FastAPI** — local API server for React UI (Phase 3)
- **React + Vite + TypeScript** — dashboard (Phase 3)
- **ntfy/Pushover** — push notifications (Phase 2)

## Project Structure
```
src/pnw_campsites/
  providers/          # Thin API clients per booking system
    recgov.py         # Recreation.gov (RIDB metadata + undocumented availability)
    goingtocamp.py    # WA State Parks (GoingToCamp, curl_cffi WAF bypass)
  registry/           # Campground registry (SQLite-backed)
    models.py         # Data models (campground, campsite, availability)
    db.py             # SQLite operations
  search/             # Discovery engine — translates flexible queries to API calls
  monitor/            # Watch/diff layer — polls, detects changes, dispatches notifications
scripts/              # Utility scripts (validation, seed data, etc.)
data/                 # SQLite databases, seed data files
tests/                # Tests
```

## Data Sources

### Recreation.gov — PRIMARY (Phase 1)
Two APIs, both critical:

**RIDB (official, documented)** — campground metadata
- `GET https://ridb.recreation.gov/api/v1/facilities?state=WA&activity=CAMPING`
- `GET https://ridb.recreation.gov/api/v1/facilities/{id}/campsites`
- Auth: API key in `apikey` header (stored in `.env` as `RIDB_API_KEY`)
- Rate limit: 50 req/min
- Use for: bulk-importing campground registry, facility details, GPS coords

**Availability (undocumented, no auth)** — real-time per-site availability
- `GET https://www.recreation.gov/api/camps/availability/campground/{facility_id}/month?start_date=YYYY-MM-01T00:00:00.000Z`
- Requires browser-like User-Agent header
- Returns per-campsite, per-day status for entire month
- Statuses: Available, Reserved, Not Available, Not Reservable, Not Reservable Management, NYR (not yet released), Open (FCFS), Closed (seasonal)
- Stable for years — used by camply, Campnab, Campflare, etc.
- THIS IS THE CRITICAL ENDPOINT for the whole project

**Search API**
- `GET https://www.recreation.gov/api/search?q=camping&fq=state:WA`
- Needs parameter tuning — returned 0 results in validation

### WA State Parks / GoingToCamp — DONE (Phase 2b)
- Base: `https://washington.goingtocamp.com`
- WAF bypass: `curl_cffi` with Chrome TLS fingerprint impersonation (`chrome131`)
- Key endpoints: `/api/maps` (hierarchy), `/api/resourceLocation` (parks), `/api/availability/map` (per-site avail)
- Map hierarchy: root → region → park → loop/area → individual site resources
- Availability values: 0=Available, 1=Reserved, 2=Closed, 3=Not Reservable, 5=NYR
- 75 WA State Parks with campsites seeded in registry (`scripts/seed_wa_state.py`)
- Site names not available via API — identified by resource ID (e.g., `WA--2147482394`)

### Oregon/Idaho State Parks — Phase 4 (Stretch)
- ReserveAmerica platform, blocked by bot protection
- Will need Playwright/headless browser

## CLI Usage (for Claude Code conversations)

Activate the venv first: `.venv/bin/python3 -m pnw_campsites <command>`

### Search for available campsites
```bash
# Basic: WA campgrounds with 2+ night availability in a date range
.venv/bin/python3 -m pnw_campsites search --dates 2026-06-01:2026-06-30 --state WA --nights 2

# Day-of-week filter: only Thu-Sun windows
.venv/bin/python3 -m pnw_campsites search --dates 2026-06-01:2026-06-30 --state WA --days long-weekend

# Presets: this-weekend, next-weekend
.venv/bin/python3 -m pnw_campsites search --dates this-weekend --state WA

# Custom days: any combo
.venv/bin/python3 -m pnw_campsites search --dates 2026-07-01:2026-07-31 --days fri,sat,sun

# With filters
.venv/bin/python3 -m pnw_campsites search --dates 2026-06-01:2026-06-30 --state WA --tags lakeside --max-drive 180 --no-groups --people 4

# By name
.venv/bin/python3 -m pnw_campsites search --dates 2026-06-01:2026-06-30 --name "rainier"

# Increase limit (default checks 20 campgrounds)
.venv/bin/python3 -m pnw_campsites search --dates 2026-06-01:2026-06-30 --state WA --limit 50

# WA State Parks only (no RIDB key needed)
.venv/bin/python3 -m pnw_campsites search --dates 2026-07-01:2026-07-07 --source wa-state --nights 1

# WA State Parks by name
.venv/bin/python3 -m pnw_campsites search --dates 2026-07-01:2026-07-07 --source wa-state --name "deception"

# Rec.gov only
.venv/bin/python3 -m pnw_campsites search --dates 2026-06-01:2026-06-30 --source recgov --state WA
```

### Check a specific campground
```bash
# Rec.gov (default)
.venv/bin/python3 -m pnw_campsites check 232465 --dates 2026-06-01:2026-06-30

# WA State Park (use resourceLocationId from registry)
.venv/bin/python3 -m pnw_campsites check -2147483624 --dates 2026-07-01:2026-07-07 --source wa-state
```

### List registry campgrounds
```bash
.venv/bin/python3 -m pnw_campsites list --state WA
.venv/bin/python3 -m pnw_campsites list --name "lake" --state OR
.venv/bin/python3 -m pnw_campsites list --source wa-state
```

### Day-of-week presets
- `weekend` = Fri, Sat, Sun
- `long-weekend` = Thu, Fri, Sat, Sun
- `weekdays` = Mon-Fri
- Custom: `thu,fri,sat,sun` (any comma-separated day names)

### Booking URLs
Search results include recreation.gov availability links. The `check` command includes per-site booking links with dates pre-filled.

### Watch/monitor campgrounds for changes
```bash
# Add a watch — "alert me when Ohanapecosh opens up for June weekends"
.venv/bin/python3 -m pnw_campsites watch add 232465 --dates 2026-06-01:2026-06-30 --nights 2 --days long-weekend

# With ntfy push notifications
.venv/bin/python3 -m pnw_campsites watch add 232465 --dates 2026-06-01:2026-06-30 --ntfy-topic my-campsites

# List watches
.venv/bin/python3 -m pnw_campsites watch list

# Poll all watches (run via cron for automated monitoring)
.venv/bin/python3 -m pnw_campsites watch poll

# Remove a watch
.venv/bin/python3 -m pnw_campsites watch remove 1
```

The poll command diffs current availability against the last snapshot. First poll baselines; subsequent polls report only newly-available sites (cancellations, newly-released dates).

Note: In production (v0.5+), watch polling runs automatically via APScheduler every 15 minutes — the CLI `watch poll` command is for local/manual use only.

### Enrich registry tags (LLM — manual one-off)
```bash
# Preview what tags would be extracted (no changes saved)
ANTHROPIC_API_KEY=sk-... .venv/bin/python3 -m pnw_campsites enrich --dry-run --limit 10

# Enrich campgrounds lacking tags (calls Claude Haiku, ~$0.10 for full registry)
ANTHROPIC_API_KEY=sk-... .venv/bin/python3 -m pnw_campsites enrich --limit 50
```

This is a standalone CLI tool, not part of the server. It reads campground descriptions from the registry, sends them to Claude Haiku to extract structured tags (lakeside, pet-friendly, old-growth, etc.), and writes validated tags back. The `anthropic` package is in the optional `enrichment` dep group — not installed on the deployed server.

## Roadmap & Progress (v0.1 → v1.0)

Full roadmap details: `docs/ROADMAP.md` | PRD: `docs/PRD-v1.0.md` | PRFAQ: `docs/PRFAQ-v1.0.md`

### v0.1 "Foundation" — DONE
- [x] Rec.gov provider (RIDB metadata + availability)
- [x] GoingToCamp provider (WA State Parks, curl_cffi WAF bypass)
- [x] SQLite campground registry (685 campgrounds, 453 with tags)
- [x] Search engine with day-of-week, distance, tag filtering
- [x] CLI: search, check, list, watch add/remove/list/poll
- [x] FastAPI backend with multi-provider search/check/list endpoints
- [x] React dashboard: search modes, date-block results, source badges, drive time badges, tag badges
- [x] Mobile-responsive UI with progressive disclosure
- [x] Error handling: retry on 429/5xx, typed errors, warning banners
- [x] Event tracking (search params, card expand, booking clicks)
- [x] Fly.io deployment with GitHub Actions CI/CD
- [x] Custom domain (campnw.palouselabs.com)
- [x] Registry enrichment: auto-tags from RIDB + GoingToCamp descriptions

### v0.2 "Watches on the Web" — DONE
- [x] Watch CRUD API endpoints (POST/GET/DELETE/PATCH)
- [x] Web watch management UI (create, list, pause, delete)
- [x] "Watch this campground" CTA on result cards
- [x] Dark mode (system-preference-aware + manual toggle, warm forest palette)
- [x] Watch confirmation animation

### v0.2.1 "Hardening" — DONE
Security:
- [x] Cookie: add `secure=True` flag
- [x] CORS: env-based origin config (ALLOWED_ORIGINS)
- [x] /api/track: body size cap, schema validation, allowed events whitelist
- [x] Search limit param capped at 50
- [x] Pin GitHub Actions flyctl to SHA
- [x] Validate facility_id format in URL path

Accessibility (Level A):
- [x] Result card: button with aria-expanded
- [x] Add `<main>` landmark
- [x] Theme toggle: aria-label
- [x] Day/tag/mode/view pickers: aria-pressed on all toggles
- [x] Expand icon: aria-hidden="true"
- [x] Name filter: visible text label
- [x] Tag/day picker: role="group" with aria-label
- [ ] Watch panel: focus trap, aria-modal (deferred to v0.3)
- [ ] Add axe-core to CI (deferred to v0.3)

Performance:
- [x] Batch size 5, delay 0.3s (~40% faster)

### v0.3 "Calendar & Polish" — DONE
- [x] Calendar heat map — GitHub contribution graph layout, single-hue scale
- [x] Calendar heat map — aria-labels per cell, keyboard accessible
- [x] SSE streaming for progressive search results
- [x] Shareable search links (URL query string encoding)
- [x] Zero-result state with refinement suggestions
- [x] CSS variable migration (accent, error colors)
- [x] Component directory structure (src/components/)
- [x] Dark mode accent contrast fix (--accent-text for WCAG AA)
- [x] Focus-visible styles on all interactive elements
- [x] Watch panel focus trap + aria-modal + Escape to close
- [x] axe-core in dev mode for continuous a11y feedback
- [x] Search form restructure: trip type buttons, compact layout

### v0.4 "Accounts" — DONE
- [x] User auth (PyJWT + bcrypt, httpOnly cookie, no external service)
- [x] Saved home base and default preferences
- [x] Persistent watch ownership (migrate anonymous watches on signup/login)
- [x] Search history (recent searches as quick-fill chips)
- [x] Privacy controls (data export JSON, account deletion)
- [x] Fix watch UNIQUE constraint to scope per-user (app-level duplicate check)
- [x] Redact from_location from search logs

### v0.45 "Testing" — DONE
- [x] 346 tests (295 backend + 51 frontend)
- [x] 82% backend coverage, 70% CI threshold
- [x] Shared conftest.py with fixtures and factories
- [x] CI test job gates deployment in deploy.yml
- [x] Vitest + React Testing Library configured

### v0.5 "Background Engine" — DONE
- [x] Server-side watch polling (APScheduler AsyncIOScheduler, 15-min cycles)
- [x] Web push notifications (service worker + Web Push API + VAPID)
- [x] PWA manifest + service worker (required for iOS Web Push)
- [x] In-product soft-ask for notification permission (after watch creation)
- [x] Notification channel preferences (per-watch: web_push, ntfy, pushover)
- [x] Availability cache in SQLite (10-min TTL, shared across watches)
- [x] Availability history data collection (silent — feeds v0.9 predictions)
- [x] Registry auto-enrichment (CLI: Claude Haiku tag extraction, ~$0.10/full run)
- [x] Watch polling dashboard (last/next poll, active watches, notification log)
- [x] Fly.io always-on (min_machines_running=1, ~$2/mo)
- [ ] Automated registry refresh (monthly RIDB, quarterly GoingToCamp) — deferred

### v0.6 "Smart Search" — DONE
- [x] Smart date shifting (±7/14 day probes, inline suggestions with result counts)
- [x] "Why nothing?" diagnostic (binding constraint analysis + action chips)
- [x] Lightweight alternative suggestions (Jaccard tag similarity + proximity)
- [x] Search history — shipped in v0.4 (recent chips in SearchForm)
- [x] SmartZeroState component (replaces generic no-results message)

### v0.7 "Oregon + Delight" — DONE
- [x] Site character / "vibe" descriptions (Haiku-generated, rendered in expanded cards)
- [x] Contextual watch notifications (LLM-enriched alerts with urgency 1-3 scoring)
- [ ] Oregon State Parks provider — deferred (ReserveAmerica has no availability API; Playwright required)
- [ ] Booking link validation — deferred
- [ ] Registry gap detector — deferred

### v0.8a "Trip Planner MVP" — DONE
- [x] Trip planner on `/plan` route (React Router)
- [x] Conversational UI (Claude Sonnet + function calling)
- [x] 5 tools: search, check, drive time, campground detail, geocode
- [x] Hallucination guardrail (only recommend tool-returned campgrounds)
- [x] Rate limiting (5 sessions/day per user)
- [x] role="log" on transcript, aria-live for loading states

### v0.8b "Trip Planner Polish" — DONE
- [x] Streaming chat responses (SSE — progressive text + tool events)
- [x] Chat UI design pass (tighter bubbles, pill badges, sticky input)
- [x] Prompt engineering (act-don't-ask, date inference, dense output)
- [x] Conversation persistence (localStorage, survives nav + refresh)
- [x] Clickable example prompts + "New conversation" button
- [ ] Itinerary card view (structured day-by-day cards) — deferred
- [ ] Shareable itineraries (UUID link, 30-day expiry) — deferred
- [ ] Cost monitoring dashboard — deferred

### v0.9 "Predictions+"
- [ ] Predictive availability display ("typically frees up X days before")
- [ ] Statistical prediction model (time-series on polling history + booking window detection)
- [ ] Smart notification scoring ("usually books within 30 min")
- [ ] Prediction confidence display with "still learning" cold start
- [ ] Anomaly-based deal alerts (proactive alerts for statistically unusual availability)
- [ ] "Why did I miss it?" post-mortem (explains missed cancellations, suggests tuning)

### v0.95 "Monetization" — DONE (feature/monetization branch)
- [x] Free/Pro tier ($5/mo): 3 free watches @ 15-min, unlimited Pro @ 5-min
- [x] Payment provider integration (Stripe hosted checkout + customer portal + webhooks)
- [x] Subscription schema (status on users table, webhook-driven, never in JWT)
- [x] Watch limit enforcement (server-side, HTTP 402) + poll interval tiering (5-min pro scheduler)
- [x] Trip planner gating (3 sessions/month free, 20 Pro, DB-backed monthly counter)
- [x] Pricing page (`/pricing`), upgrade modal (focus trap, ARIA), billing settings, ProBadge
- [x] 30-day grandfather migration for existing users with >3 watches
- [x] Webhook security (HMAC signature verification, idempotency via stripe_events table)

### v1.0 "campnw 1.0"
- [ ] Map view (Leaflet, lazy-loaded, with list alternative for a11y)
- [ ] Keyboard shortcuts (j/k nav, b bookmark, w watch, ? help)
- [ ] Registry expansion to 1,000+ campgrounds
- [ ] Personalized recommendations (opt-in, based on search history)
- [ ] Performance audit (P95 search < 4s, Lighthouse CI)
- [ ] Accessibility audit (WCAG 2.1 AA final sweep, axe-core in CI)

## Key Design Decisions

- **Registry is the differentiator.** Enriched with drive time from Bellevue, user tags (lakeside, river, old-growth, kid-friendly), personal notes/ratings. Discovery queries filter the registry first, then check availability only for matching campgrounds.
- **Thin provider clients.** Each provider is just a clean async wrapper around the booking system's API. No business logic in providers.
- **Extract patterns from camply, don't depend on it.** The value is in ~200 lines of endpoint logic. Reference: https://github.com/juftin/camply
- **SQLite for everything local.** Registry, availability cache, watch state. No external DB.

## Environment
- API keys in `.env` (never commit)
- `RIDB_API_KEY` — Recreation.gov RIDB metadata API

## Code Style
- Python: type hints, dataclasses/pydantic for models, async where beneficial
- Keep providers stateless and testable
- Prefer `httpx` over `requests` for async support
- Use `python-dotenv` for env loading

### CSS / Design System
All frontend styling uses design tokens defined in `web/src/tokens.css`. **Never use hardcoded values** for properties that have tokens — always use `var(--token-name)`.

**Token reference** (see `web/src/tokens.css` for full list):
- **Spacing:** `--space-1` (0.25rem) through `--space-7` (3rem). Use for padding, margin, gap.
- **Type scale:** `--text-xs` (0.7rem) through `--text-xl` (1.5rem). Use for font-size.
- **Font weight:** `--weight-normal` (400), `--weight-medium` (500), `--weight-semi` (600), `--weight-bold` (700).
- **Border radius:** `--radius-xs` (3px) through `--radius-pill` (999px). `--radius-sm` (6px) is the default.
- **Shadows:** `--shadow-sm`, `--shadow-card`, `--shadow-overlay`. Dark mode overrides `--shadow-sm` automatically.
- **Transitions:** `--transition-fast` (0.12s), `--transition-base` (0.15s). All interactive elements must have transitions.
- **Z-index:** `--z-sticky` (5), `--z-overlay` (100), `--z-modal` (101).
- **Layout:** `--max-w-app` (960px), `--max-w-modal` (400px).
- **Source colors:** `--src-{recgov,wa,or,id}-badge-bg`, `--src-{...}-badge-text`, `--src-{...}-border`. Dark mode variants defined in tokens.css.
- **Theme colors:** Defined in `App.css` `:root` — `--bg`, `--text`, `--accent`, `--border`, `--chip-*`, `--warning-*`, `--error-*`, `--heatmap-*`.

**Intentional exclusions** (stay hardcoded):
- Spacing: 0.3rem, 0.35rem (tight interactive elements), sub-0.25rem (micro)
- Font size: 0.5rem/0.55rem (heatmap), 0.95rem (edge cases)
- Radius: 50% (circles), 20px (decorative)
- Line-height: 1.4, 1.45 (between named tokens)
- Breakpoint: 640px (CSS vars don't work in @media)

## Known Gotchas
- Rec.gov availability endpoint needs browser-like User-Agent or you may get blocked
- GoingToCamp has Azure WAF — bypassed with `curl_cffi` Chrome TLS impersonation. Plain `requests`/`httpx` get 403'd.
- RIDB rate limit is 50 req/min — batch imports need throttling
- Availability statuses beyond the documented ones: "Not Reservable", "Not Reservable Management", "Open", "Closed" — all handled in AvailabilityStatus enum
- Many USFS campgrounds are first-come-first-served with no online system
- Some RIDB facilities return 404 on the availability endpoint (scenic byways, areas, corridors) — these aren't reservable campgrounds. Errors are caught and reported gracefully.
- GoingToCamp resource/site details endpoint returns 404 — site names not available via API. Sites identified by resource ID (e.g., `WA--2147482394`).
- GoingToCamp map hierarchy must be traversed park-by-park via the `resourceLocationId → childMapId` mapping from `/api/maps` links. Starting from region maps returns ALL parks' sites.
- Registry has 685 campgrounds: 610 rec.gov (WA 146, OR 226, ID 238) + 75 WA State Parks. Re-seed with `scripts/seed_registry.py` and `scripts/seed_wa_state.py`
