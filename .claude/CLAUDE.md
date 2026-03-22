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

## Build Phases

### Phase 1: Core + CLI (DONE)
- [x] Validate APIs
- [x] Build recgov provider (availability + RIDB metadata clients)
- [x] Design and create SQLite campground registry schema
- [x] Seed registry with 610 PNW campgrounds from RIDB (WA/OR/ID)
- [x] Build search/discovery engine (with day-of-week filtering)
- [x] CLI entry point with search, check, list commands

### Phase 2a: Monitoring (rec.gov) — DONE (except cron setup)
- [x] Watch/diff layer — SQLite-backed snapshots with change detection
- [x] Notification dispatch (ntfy + Pushover + console)
- [x] CLI commands: watch add/remove/list/poll
- [ ] Cron/launchd timer setup for automated polling

### Phase 2b: WA State Parks (GoingToCamp) — DONE
- [x] Investigate WAF bypass — `curl_cffi` with Chrome TLS impersonation works
- [x] Research camply's GoingToCamp provider (plain requests, no WAF bypass)
- [x] Build `providers/goingtocamp.py` with map hierarchy traversal
- [x] Seed 75 WA State Parks into registry (`scripts/seed_wa_state.py`)
- [x] Integrate into search engine (multi-provider dispatch by booking_system)
- [x] CLI: `--source wa-state` flag on search/check/list commands
- [x] WA State Parks booking URLs in results
- **No overlap with 2a** — separate provider, different directory

**Parallel work note**: 2a and 2b can safely run in separate Claude Code sessions on the same branch. File overlap is minimal (different subdirectories). Separate git worktrees are an option but not necessary.

### Phase 3: Dashboard — DONE
- [x] FastAPI backend (`src/pnw_campsites/api.py`) — search, check, list endpoints with CORS
- [x] React + Vite + TypeScript frontend (`web/`) — search form, results cards, booking links
- [x] Multi-provider support (rec.gov + WA State Parks) in API
- **Run**: API: `.venv/bin/uvicorn pnw_campsites.api:app --port 8000` | Frontend: `cd web && npm run dev`

### Future: Dashboard enhancements
- [ ] Option C results view — date blocks across campgrounds ("what's available this weekend?" flat view)
- [ ] Cloudflare Workers deployment (Python Workers + D1 for registry, Pages for React frontend)

### Phase 4: Oregon/Idaho (stretch)
- [ ] ReserveAmerica scraping via Playwright
- [ ] Expand registry

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
