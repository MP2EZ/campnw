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

### v0.4 "Accounts"
- [ ] User auth (email + Google OAuth via Clerk or Auth.js)
- [ ] Saved home base and default preferences
- [ ] Watch email collection (anonymous watches need notification channel)
- [ ] Persistent watch ownership (migrate anonymous watches)
- [ ] Search history (recent 5-10 as quick-fill, not full log)
- [ ] Privacy controls (data export, account deletion)
- [ ] Fix watch UNIQUE constraint to scope per-user (not cross-user)
- [ ] Redact from_location from search logs

### v0.5 "Background Engine"
- [ ] Server-side watch polling (APScheduler, 15-min cycles)
- [ ] Web push notifications (service worker + Web Push API)
- [ ] PWA manifest + service worker (required for iOS Web Push)
- [ ] In-product soft-ask for notification permission (not raw browser prompt)
- [ ] Notification channel preferences (web push, ntfy, Pushover, email)
- [ ] Availability cache in SQLite (10-15 min TTL)
- [ ] Availability history data collection (silent — feeds v0.9 predictions)
- [ ] Automated registry refresh (monthly RIDB, quarterly GoingToCamp)

### v0.6 "AI Search"
- [ ] NL search as entry point → auto-fills form → user confirms (NOT a toggle)
- [ ] NL prompt engineering (tag taxonomy, few-shot examples)
- [ ] Loading shimmer state while NL parses
- [ ] aria-live on extracted parameter preview
- [ ] NL parse accuracy tracking
- [ ] Prompt injection defense (strict Pydantic validation on model output)
- [ ] Anthropic API spend limits in console

### v0.7 "Oregon Expansion"
- [ ] Oregon State Parks provider (ReserveAmerica via Playwright)
- [ ] Seed 200+ OR state parks into registry
- [ ] OR State Parks source filter + color-coded badge (amber)
- [ ] Campground detail enrichment (amenities, photos, site counts)
- [ ] Registry enrichment pass (manual curation top 50)
- [ ] Booking link validation

### v0.8 "Trip Planner"
- [ ] Trip planner on dedicated route (/plan), not embedded in search
- [ ] Conversational UI (Claude Sonnet + function calling)
- [ ] Tool-calling integration (search, check, drive time, detail)
- [ ] Itinerary card view (day-by-day with booking links, ol semantics)
- [ ] Shareable itineraries (UUID link, 30-day expiry)
- [ ] role="log" on transcript, aria-live for tool-call states
- [ ] Rate limit communication UX (5/day free tier)

### v0.9 "Predictions"
- [ ] Predictive availability display ("typically frees up X days before")
- [ ] Statistical prediction model (time-series on polling history)
- [ ] Smart notification scoring ("usually books within 30 min")
- [ ] Prediction confidence display with "still learning" cold start

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
