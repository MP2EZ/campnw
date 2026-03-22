# campnw

Find available campsites across the Pacific Northwest.

**Live at [campnw.palouselabs.com](https://campnw.palouselabs.com)**

campnw searches real-time availability across Recreation.gov (federal campgrounds) and Washington State Parks in a single query. Filter by drive time, trip type, tags (lakeside, pet-friendly, old-growth...), and toggle between sources instantly.

## Features

- **Multi-provider search** — Recreation.gov + WA State Parks (GoingToCamp) in one search
- **685+ campgrounds** across WA, OR, and ID with auto-generated tags
- **Distance filtering** — approximate drive time from Seattle, Bellevue, Portland, Spokane, Bellingham, or Moscow ID
- **Trip type presets** — Weekend (F–Su), Long weekend (Th–Su), Weekdays, or custom day picker
- **Two search modes** — "Find a date" (flexible range) and "Exact dates"
- **Availability heat map** — GitHub-style contribution graph showing site density across your date range
- **Progressive results** — SSE streaming shows results as they arrive (~1-2s for first results)
- **Watchlist** — monitor campgrounds for cancellations, get notified when sites open up
- **Dark mode** — system-aware with manual toggle
- **Direct booking links** — pre-filled links to recreation.gov and GoingToCamp

## Tech Stack

- **Backend**: Python 3.12, FastAPI, SQLite, httpx, curl_cffi (GoingToCamp WAF bypass)
- **Frontend**: React, Vite, TypeScript
- **Deployment**: Fly.io (Docker), GitHub Actions CI/CD, Cloudflare DNS

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

See [ROADMAP.md](docs/ROADMAP.md) for the full v0.1 → v1.0 plan.

Currently at **v0.3** — search, monitoring, dashboard, dark mode, calendar heat map, streaming results, and distance/tag filtering are all working and deployed.

## License

Personal project by [Palouse Labs](https://palouselabs.com).
