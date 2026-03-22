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
    goingtocamp.py    # WA State Parks (GoingToCamp platform)
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

### WA State Parks / GoingToCamp — Phase 2
- Base: `https://washington.goingtocamp.com`
- Endpoints: `/api/maps`, `/api/resourcecategory`, `POST /api/availability/map`
- **STATUS: Blocked by Azure WAF (403)**. Needs session cookies, cloudscraper, or headless browser.
- camply has a working GoingToCamp provider — reference their implementation

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
```

### Check a specific campground
```bash
.venv/bin/python3 -m pnw_campsites check 232465 --dates 2026-06-01:2026-06-30
# Outputs per-site booking URLs
```

### List registry campgrounds
```bash
.venv/bin/python3 -m pnw_campsites list --state WA
.venv/bin/python3 -m pnw_campsites list --name "lake" --state OR
```

### Day-of-week presets
- `weekend` = Fri, Sat, Sun
- `long-weekend` = Thu, Fri, Sat, Sun
- `weekdays` = Mon-Fri
- Custom: `thu,fri,sat,sun` (any comma-separated day names)

### Booking URLs
Search results include recreation.gov availability links. The `check` command includes per-site booking links with dates pre-filled.

## Build Phases

### Phase 1: Core + CLI (DONE)
- [x] Validate APIs
- [x] Build recgov provider (availability + RIDB metadata clients)
- [x] Design and create SQLite campground registry schema
- [x] Seed registry with 610 PNW campgrounds from RIDB (WA/OR/ID)
- [x] Build search/discovery engine (with day-of-week filtering)
- [x] CLI entry point with search, check, list commands

### Phase 2: Monitoring + WA State Parks
- [ ] GoingToCamp provider (solve WAF issue)
- [ ] Watch/diff layer — store last-seen availability, detect changes
- [ ] Notification dispatch (ntfy or Pushover)
- [ ] Cron/systemd timer setup

### Phase 3: Dashboard
- [ ] FastAPI backend exposing core library
- [ ] React UI with calendar grid view
- [ ] Filter/sort by tags, drive time, dates

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
- GoingToCamp now has Azure WAF — simple requests get 403'd
- RIDB rate limit is 50 req/min — batch imports need throttling
- Availability statuses beyond the documented ones: "Not Reservable", "Not Reservable Management", "Open", "Closed" — all handled in AvailabilityStatus enum
- Many USFS campgrounds are first-come-first-served with no online system
- Some RIDB facilities return 404 on the availability endpoint (scenic byways, areas, corridors) — these aren't reservable campgrounds. Errors are caught and reported gracefully.
- Registry has 610 campgrounds across WA (146), OR (226), ID (238). Re-seed with `scripts/seed_registry.py`
