# campable

Find available campsites across the western US.

**Live at [campable.co](https://campable.co)**

campable searches real-time availability across Recreation.gov, Washington State Parks, and Oregon State Parks in a single query. 1,370 campgrounds across WA, OR, ID, MT, WY, and Northern California — filter by drive time, trip type, tags, and toggle between sources instantly.

## Features

### Search + Discovery
- **Multi-provider search** — Rec.gov + WA State Parks (GoingToCamp) + OR State Parks (ReserveAmerica)
- **1,370 campgrounds** across 6 states with AI-generated tags, vibe descriptions, and elevator pitches
- **Natural language search** — "dog-friendly lakeside spot near Portland this weekend"
- **Distance filtering** — drive time from 12 known bases (Seattle, Portland, Bozeman, etc.)
- **Trip type presets** — Weekend, Long weekend, Weekdays, or custom day picker
- **Progressive results** — SSE streaming shows results as they arrive
- **Smart search** — zero-result diagnostics, date shifting suggestions, alternative campgrounds
- **Campground comparison** — select 2-3, get AI-narrated side-by-side analysis

### Planning + Trips
- **Trip planner** — conversational AI planner (Claude Sonnet) with search, drive time, and geocode tools
- **Trips** — save campgrounds to trips, manage from /trips, save directly from planner conversations
- **Availability heat map** — GitHub-style contribution graph showing site density
- **Direct booking links** — pre-filled links to Recreation.gov and GoingToCamp

### Monitoring + Notifications
- **Watchlist** — monitor campgrounds for cancellations with web push notifications
- **Template watches** — watch a search pattern, not just a single campground (expands dynamically)
- **Watch sharing** — shareable UUID links, read-only, no auth required to view
- **Background polling** — server-side 15-min poll cycles with availability history collection
- **Booking tips** — AI-generated tips from historical availability patterns

### Accounts + Personalization
- **Onboarding** — post-signup flow: set home base + preferred tags
- **Personalized recommendations** — search history affinity scoring
- **User accounts** — saved preferences, search history, data export, account deletion
- **Dark mode** — system-aware with manual toggle, warm forest palette
- **Mobile responsive** — hamburger menu, collapsible search form, touch-optimized
- **Keyboard shortcuts** — j/k navigation, w watchlist, m map toggle, ? help

## Tech Stack

- **Backend**: Python 3.12, FastAPI, SQLite, httpx, curl_cffi (WAF bypass)
- **Frontend**: React, Vite, TypeScript
- **AI**: Claude Sonnet (trip planner), Claude Haiku (tags, comparisons, tips, NL search)
- **Deployment**: Fly.io (Docker, persistent volume), GitHub Actions CI/CD, Cloudflare DNS
- **Testing**: 708 backend tests (86% coverage), 64 frontend tests

## Development

```bash
# Backend
python3 -m venv .venv
.venv/bin/pip install -e ".[api,dev]"
cp .env.example .env  # add RIDB_API_KEY
.venv/bin/uvicorn pnw_campsites.api:app --reload --port 8000

# Frontend
cd web && npm install && npm run dev
```

Open `http://localhost:5173`

## CLI

```bash
# Search for available campsites
.venv/bin/python3 -m pnw_campsites search --dates 2026-06-01:2026-06-30 --state WA --nights 2 --from seattle --days long-weekend

# Check a specific campground
.venv/bin/python3 -m pnw_campsites check 232465 --dates 2026-06-01:2026-06-30

# List registry campgrounds
.venv/bin/python3 -m pnw_campsites list --state WA --tags lakeside

# Watch for cancellations
.venv/bin/python3 -m pnw_campsites watch add 232465 --dates 2026-06-01:2026-06-30 --nights 2
.venv/bin/python3 -m pnw_campsites watch poll
```

## Project Status

**v1.2** — shipped. See [ROADMAP.md](docs/ROADMAP.md) for the full history from v0.1 through v1.2. Next up: v1.3 "Predictions+" (statistical availability predictions from 9-12 months of polling history, ~Q1 2027).

## License

Personal project by [Palouse Labs](https://palouselabs.com).
