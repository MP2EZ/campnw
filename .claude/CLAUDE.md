# PNW Campsite Tool

## What This Is
Personal tool for finding and monitoring campsite availability across the western US (WA, OR, ID, MT, WY, NorCal). Not a product — built for a single user and friends. The core value: discovery ("what's available this weekend within 3 hours of Seattle?") across multiple booking systems, not just monitoring a single known campground.

## Tech Stack
- **Python 3.12+** — core library, API clients
- **SQLite** — campground registry, availability cache, watch state
- **FastAPI** — API server
- **React + Vite + TypeScript** — dashboard
- **ntfy/Pushover** — push notifications

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

### Oregon State Parks / ReserveAmerica — DONE
- Base: `www.reserveamerica.com` (unified site, NOT state subdomain)
- WAF bypass: `curl_cffi` with Chrome131 TLS fingerprint impersonation
- Data: Redux state JSON embedded in HTML `<script>` tags (~2MB per page)
- Path: `backend.productSearch.searchResults.records[].availabilityGrid[]`
- Statuses: AVAILABLE, RESERVED, NOT_AVAILABLE, WALK_UP
- 14-day availability window per request, 20 records per page, 1 req/sec rate limit
- 53 Oregon State Parks seeded in registry (`scripts/seed_or_state.py`)
- `booking_url_slug` column in registry for RA URL construction

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

## Roadmap & Progress

Full roadmap: `docs/ROADMAP.md` | PRD: `docs/PRD-v1.0.md` | PRFAQ: `docs/PRFAQ-v1.0.md` | Brand: `docs/BRAND.md`

**Completed:** v0.1 through v1.25 — see `docs/ROADMAP.md` for full history.

**Deferred items** (carried forward):
- Automated registry refresh (monthly RIDB, quarterly GoingToCamp)
- Booking link validation
- Itinerary card view + shareable itineraries
- Dashboard hub
- Use Fly-Client-IP instead of X-Forwarded-For (SEC-10)
- Auth modal max-width → var(--max-w-modal) (UX-05)
- Hardcoded spacing → tokens (UX-04/06/07)
- Idaho State Parks (CAPTCHA-blocked, ~20 parks, not worth it)

### v1.3 "Predictions+" (~Q1 2027, needs 9-12 months polling data)
- [ ] Statistical prediction model (time-series on polling history + booking window detection)
- [ ] Predictive availability display ("typically frees up X days before" with confidence bands)
- [ ] Prediction confidence display with "still learning" cold start
- [ ] Smart notification scoring ("usually books within 30 min")
- [ ] Anomaly-based deal alerts (Pro-only, Haiku-narrated with historical context)
- [ ] "Why did I miss it?" post-mortem (Haiku-narrated timing analysis + tuning suggestions)

Full requirements: `docs/REQUIREMENTS-v1.1-v1.2.md` | Full roadmap: `docs/ROADMAP.md` | Brand details: v1.15 in ROADMAP.md

## Key Design Decisions

- **Registry is the differentiator.** Enriched with drive time from Seattle, user tags (lakeside, river, old-growth, kid-friendly), personal notes/ratings. Discovery queries filter the registry first, then check availability only for matching campgrounds.
- **Thin provider clients.** Each provider is just a clean async wrapper around the booking system's API. No business logic in providers.
- **Extract patterns from camply, don't depend on it.** The value is in ~200 lines of endpoint logic. Reference: https://github.com/juftin/camply
- **SQLite for everything local.** Registry, availability cache, watch state. No external DB.

## Environment
- API keys in `.env` (never commit)
- `RIDB_API_KEY` — Recreation.gov RIDB metadata API
- `VITE_PUBLIC_POSTHOG_PROJECT_TOKEN` — PostHog project API key (public, baked into frontend build)
- `VITE_PUBLIC_POSTHOG_HOST` — PostHog API host (default: https://us.i.posthog.com)

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
- Registry has 1,370 campgrounds: 1,242 rec.gov (WA/OR/ID/MT/WY/NorCal) + 75 WA State Parks + 53 OR State Parks. Re-seed with `scripts/seed_registry.py`, `scripts/seed_wa_state.py`, and `scripts/seed_or_state.py`
