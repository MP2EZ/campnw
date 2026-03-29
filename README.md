# campnw

Find available campsites across the Pacific Northwest.

**Live at [campable.co](https://campable.co)**

campnw searches real-time availability across Recreation.gov (federal campgrounds) and Washington State Parks in a single query. Filter by drive time, trip type, tags (lakeside, pet-friendly, old-growth...), and toggle between sources instantly.

## Features

- **Multi-provider search** — Recreation.gov + WA State Parks (GoingToCamp) in one search
- **740+ campgrounds** across WA, OR, and ID with auto-generated tags and vibe descriptions
- **Distance filtering** — drive time from Seattle, Bellevue, Portland, Spokane, Bellingham, or Moscow ID
- **Trip type presets** — Weekend, Long weekend, Weekdays, or custom day picker
- **Availability heat map** — GitHub-style contribution graph showing site density across your date range
- **Progressive results** — SSE streaming shows results as they arrive
- **Watchlist** — monitor campgrounds for cancellations with web push notifications
- **Background polling** — server-side 15-min poll cycles with split tranches and availability history
- **Map view** — Leaflet map with source-colored pins, clustering, and popups
- **AI trip planner** — conversational planner (Claude Sonnet) with search, drive time, and geocode tools
- **Personalized recommendations** — search history affinity scoring, opt-in
- **User accounts** — saved preferences, search history, data export, account deletion
- **Smart search** — zero-result diagnostics, date shifting suggestions, alternative campgrounds
- **Dark mode** — system-aware with manual toggle, warm forest palette
- **Mobile responsive** — hamburger menu, collapsible search form, touch-optimized
- **Direct booking links** — pre-filled links to recreation.gov and GoingToCamp

## Tech Stack

- **Backend**: Python 3.12, FastAPI, SQLite, httpx, curl_cffi (GoingToCamp WAF bypass)
- **Frontend**: React, Vite, TypeScript
- **Deployment**: Fly.io (Docker, persistent volume), GitHub Actions CI/CD, Cloudflare DNS

## Development

```bash
# Backend
python3 -m venv .venv
.venv/bin/pip install -e ".[api,dev]"
cp .env.example .env  # add RIDB_API_KEY
.venv/bin/uvicorn pnw_campsites.api:app --port 8000

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

**v1.0** — shipped. See [ROADMAP.md](docs/ROADMAP.md) for the full history from v0.1 through v1.0. Next up: v1.1 "Predictions+" (statistical availability predictions from polling history).

## License

Personal project by [Palouse Labs](https://palouselabs.com).
