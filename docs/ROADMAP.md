# campnw Roadmap: v0.1 to v1.0

**Last updated:** March 2026
**Current version:** v0.1 (deployed at campnw.palouselabs.com)

---

## Timeline Summary

```
v0.1  [SHIPPED]  Foundation          — Multi-provider search, CLI watches, dashboard
v0.2  ------->   Watches on the Web  — Web-based watch management, dark mode
v0.3  ------->   Calendar & Polish   — Calendar heat map, shareable links, UX refinements
v0.4  ------->   Accounts            — User accounts, saved preferences, persistent watches
v0.5  ------->   Background Engine   — Server-side polling, web push notifications
v0.6  ------->   AI Search           — Natural language search, search history
v0.7  ------->   Oregon Expansion    — Oregon State Parks, registry growth to 900+
v0.8  ------->   Trip Planner        — AI-powered multi-stop itinerary builder
v0.9  ------->   Predictions         — Availability predictions, smart notifications
v1.0  ------->   campnw 1.0          — Map view, power user features, polish pass
```

Each milestone is a shippable increment with clear user value. P0 features complete by v0.5. P1 features complete by v0.8-v0.9. P2 features are stretch for v1.0 or deferred to post-v1.0.

---

## v0.2 "Watches on the Web"

### Theme
The watch system already works in CLI. This milestone brings it to the web, closing the highest-value gap between the CLI and the dashboard. Also ships dark mode, which the PRD calls out as a day-one design principle.

### Features

| Feature | PRD Ref | Effort | Description |
|---------|---------|--------|-------------|
| Web watch management UI | P0-5 | L | Create, list, pause, delete watches from the dashboard. Pre-fill from search results ("Watch this campground" CTA on zero-result searches). |
| Watch API endpoints | P0-5 | M | `POST /api/watches`, `GET /api/watches`, `DELETE /api/watches/{id}`, `PATCH /api/watches/{id}` (pause/resume). Anonymous watches stored server-side with a browser fingerprint or cookie token. |
| Dark mode | Design 6.1 | M | System-preference-aware dark mode with manual toggle. CSS custom properties for theming. Persist preference in localStorage. |
| Watch confirmation UX | Design 6.1 | S | Brief confirmation animation on watch creation. Inline watch status on result cards for watched campgrounds. |

### Technical Work
- Add watch CRUD endpoints to FastAPI (`api.py`)
- Extend `monitor/db.py` for server-side watch storage (SQLite, no auth yet -- anonymous watches tied to a session token cookie)
- CSS custom property system for light/dark theming across all components
- Cookie-based session token for anonymous watch ownership (no auth required yet)

### Dependencies
- None (builds on existing CLI watch system and monitor module)

### Key Risk
Anonymous watches without accounts create orphan data. Mitigation: TTL-based expiry (watches auto-delete after 90 days of inactivity). When accounts ship in v0.4, migrate anonymous watches via session token.

---

## v0.3 "Calendar & Polish"

### Theme
The calendar heat map is a P0 that transforms how users understand availability across time. Shareable links make campnw useful for group planning. This milestone also addresses UX polish that makes the product feel deliberate rather than functional.

### Features

| Feature | PRD Ref | Effort | Description |
|---------|---------|--------|-------------|
| Calendar heat map (search results) | P0-6 | L | Aggregate availability density visualization across months. Color scale: red (none) to yellow (some) to green (many). Clicking a date block filters results to that window. |
| Calendar heat map (single campground) | P0-6 | M | Per-campground availability calendar on the detail/check view. Same color scale, clickable dates. |
| Shareable search links | P1-5 | M | Encode search parameters in URL query string. Copy-link button on results page. No account required to view. |
| Progressive loading improvements | P0-1 | S | Show results from faster providers first (rec.gov typically returns before GoingToCamp). Skeleton loading states for pending results. |
| Micro-interactions | Design 6.1 | S | Availability chips animate in as data loads. Smooth transitions on filter changes. Expand/collapse animations on result cards. |

### Technical Work
- New `CalendarHeatMap` React component with month grid layout
- Backend endpoint or response extension to return per-day availability density (counts, not full site lists) for the date range
- URL state synchronization: search form state serialized to/from URL query params
- CSS transitions and animation system

### Dependencies
- None (can ship independently of v0.2, but ideally follows it)

### Key Risk
Calendar heat map requires per-day aggregated data that the current search response doesn't provide. The backend may need a new endpoint (`/api/availability-density`) or the existing search response needs restructuring. Design the API contract carefully to avoid N+1 query patterns.

---

## v0.4 "Accounts"

### Theme
User accounts are infrastructure, not a feature -- so this milestone pairs accounts with the features they unlock: saved home base, persistent watches that survive browser clears, and search history. Users should feel immediate value from creating an account.

### Features

| Feature | PRD Ref | Effort | Description |
|---------|---------|--------|-------------|
| User accounts (email + Google OAuth) | P1-1 | L | Managed auth via Auth.js or Clerk. Minimal data collection: email, display name, home base. |
| Saved home base and preferences | P1-1 | M | Persist home base city, default search preferences (nights, tags, source). Pre-fill search form on return visits. |
| Persistent watch ownership | P1-1 | S | Migrate anonymous watches to account on sign-up. Watches tied to account survive device changes. |
| Search history | P1-1 | M | Last 20 searches saved per account. Quick re-run from history list. Accessible from a sidebar or dropdown. |
| Privacy controls | P1-1 | S | Data export (JSON) and account deletion. Clear explanation of what data is stored. |

### Technical Work
- Auth provider integration (Clerk recommended for speed; Auth.js if self-hosted preference)
- User table in SQLite (or migrate to libsql/Turso if multi-instance becomes necessary)
- Session middleware in FastAPI (JWT or session cookies)
- Watch ownership migration: link anonymous session-token watches to new account
- Search history table: `{user_id, query_params_json, result_count, searched_at}`
- Protected API endpoints: watches require auth or valid session token

### Dependencies
- v0.2 (anonymous watches exist and need migration path)

### Key Risk
Auth adds complexity to every API call (middleware, token validation, error states). Keep the unauthenticated experience fully functional -- accounts enhance but never gate core search. Risk of scope creep into profile features; resist adding anything beyond what's listed.

---

## v0.5 "Background Engine"

### Theme
Move watch polling from CLI cron to server-side background jobs. Add web push notifications so users get alerts in their browser without needing ntfy or Pushover. This completes the P0-5 watch system as a fully web-native feature.

### Features

| Feature | PRD Ref | Effort | Description |
|---------|---------|--------|-------------|
| Server-side watch polling | P0-5 | L | Background job queue (APScheduler embedded in FastAPI) polls all active watches every 15 minutes. Batches watches by campground to minimize API calls. |
| Web push notifications | P0-5 | L | Service worker + Web Push API. User subscribes in-browser. Notification includes campground name, site number, available dates, direct booking link. |
| Notification preferences | P0-5 | M | Per-watch notification channel selection: web push, ntfy, Pushover, or email (email via a simple SMTP integration). |
| Watch polling dashboard | P0-5 | S | Simple status view: last poll time, next poll time, total active watches, recent notifications. Accessible to logged-in users. |

### Technical Work
- APScheduler integration with FastAPI lifespan (or Dramatiq + Redis if APScheduler proves insufficient)
- Service worker for web push (`sw.js` in React build output)
- VAPID key generation and storage for web push
- Push subscription storage in user record
- Batch optimization: group watches by campground_id, run one availability check per campground per cycle
- Email notification channel (SMTP via environment variable config)
- Fly.io considerations: `min_machines_running = 1` required for background polling (currently 0, which means the app sleeps)

### Dependencies
- v0.4 (accounts required for persistent push subscriptions)
- v0.2 (web watch management)

### Key Risk
Fly.io cost increase. Currently `min_machines_running = 0` allows the app to sleep between requests. Background polling requires at least one machine running 24/7. Estimate: ~$5-7/month for a shared-cpu-1x machine. Also: polling 685+ campgrounds every 15 minutes means ~2,700 API calls per hour. Need to batch watches aggressively and respect rate limits. Cap free-tier watches at 3 per user.

---

## v0.6 "AI Search"

### Theme
Natural language search -- the first AI feature. Users type what they want in plain English and campnw extracts structured search parameters. This is the highest-value AI feature because it directly reduces friction on the core action (searching).

### Features

| Feature | PRD Ref | Effort | Description |
|---------|---------|--------|-------------|
| Natural language search input | P1-2 | L | Text input that accepts free-form queries. Claude Haiku parses intent into structured search params. Extracted params shown in editable form before search executes. |
| NL search prompt engineering | P1-2 | M | System prompt with tag taxonomy, base cities, date presets, state codes. Few-shot examples for common query patterns. Confidence threshold for clarifying questions. |
| Search mode toggle: Form vs. NL | P1-2 | S | Users can switch between structured form and NL input. NL input is an enhancement, not a replacement. |
| NL parse accuracy tracking | AI-1 | S | Log extracted params vs. user edits. Track misparse rate. Feed into prompt improvements. |

### Technical Work
- Anthropic Python SDK integration (`anthropic` package)
- `ANTHROPIC_API_KEY` in Fly.io secrets
- New endpoint: `POST /api/search/parse` -- accepts text, returns structured `SearchQuery` JSON
- Prompt template with registry metadata context (tag list, base cities, state codes, date preset vocabulary)
- Model selection: Claude Haiku for latency (800ms P95 budget). Fallback to showing the form if API call fails.
- Client-side: NL input component with loading state, extracted-params preview, edit-before-search flow
- Cost controls: rate limit NL parse to 10/minute per user to prevent abuse

### Dependencies
- None technically (can use anonymous search), but better with v0.4 accounts for usage tracking

### Key Risk
Prompt reliability. NL parsing must handle ambiguous queries gracefully -- "near Seattle" could mean 1 hour or 3 hours. Strategy: when ambiguous, show extracted params with sensible defaults and let the user correct. Never auto-execute a search the user didn't confirm. Latency is the other risk: if Haiku P95 exceeds 1.5s, the feature feels sluggish. Measure early.

---

## v0.7 "Oregon Expansion"

### Theme
Oregon State Parks integration completes the PNW picture. This is the last major provider integration and meaningfully expands the campground registry. Combined with ongoing registry enrichment, this makes campnw the most comprehensive PNW campsite discovery tool.

### Features

| Feature | PRD Ref | Effort | Description |
|---------|---------|--------|-------------|
| Oregon State Parks provider | P1-6 | XL | ReserveAmerica platform scraping via Playwright headless browser. New provider module: `providers/reserveamerica.py`. |
| Oregon campground registry seed | P1-6 | M | Seed 200+ Oregon State Parks campgrounds into registry. Auto-generate tags. Compute drive times from Portland and other bases. |
| OR State Parks source filter | P1-6 | S | `--source or-state` in CLI, `source=or_state` in API. Source badge (new color) in dashboard. |
| Registry enrichment pass | P0-2 | M | Review and improve auto-generated tags for all 900+ campgrounds. Fill gaps in drive time data. Manual curation for top 50 most-searched campgrounds. |
| Booking link validation | P0-4 | S | Verify booking links resolve before surfacing. Flag stale links from provider changes. |

### Technical Work
- Playwright integration for ReserveAmerica scraping (headless Chrome in Docker)
- New `BookingSystem.OR_STATE` enum value
- `providers/reserveamerica.py` with session management, availability parsing
- Dockerfile update: add Playwright + Chromium to the container (significant image size increase -- consider a multi-stage build or sidecar)
- `scripts/seed_or_state.py` for registry seeding
- Rate limiting and retry logic for ReserveAmerica (likely more aggressive bot protection than GoingToCamp)

### Dependencies
- None (provider work is independent of other milestones)

### Key Risk
ReserveAmerica bot protection. This is flagged in the PRD as needing Playwright/headless browser, and in the CLAUDE.md as a known challenge. The scraping approach is inherently fragile -- any site redesign or WAF upgrade breaks the provider. Mitigation: build with graceful degradation from the start (OR State Parks results labeled "temporarily unavailable" when blocked). Consider whether the Docker image size increase (Chromium adds ~400MB) is acceptable for Fly.io deployment costs. May need to run Playwright in a separate service or use a browser API service.

---

## v0.8 "Trip Planner"

### Theme
The AI trip planner -- the flagship P1 feature. A conversational interface where users describe a multi-day trip and get an itinerary with real-time availability checks, drive times between stops, and booking links. This is the feature that makes campnw feel like "a knowledgeable friend."

### Features

| Feature | PRD Ref | Effort | Description |
|---------|---------|--------|-------------|
| Trip planner conversational UI | P1-4 | XL | Chat-style interface. User describes trip intent. Claude Sonnet asks clarifying questions, then generates a multi-stop itinerary. |
| Tool-calling integration | AI-3 | L | Claude function calling with campnw tools: `search_campgrounds`, `check_availability`, `get_drive_time`, `get_campground_detail`. |
| Itinerary card view | P1-4 | L | Structured output: day-by-day cards with campground name, drive time from previous stop, availability status, booking link. Editable -- user can ask to swap a leg. |
| Shareable itineraries | P1-5 | M | Save itinerary as a shareable link. Availability snapshot at share time with "as of [timestamp]" caveat. 30-day expiry. |

### Technical Work
- Anthropic SDK with function calling (Claude Sonnet)
- New endpoint: `POST /api/trip-planner` (streaming response for conversational UX)
- Tool definitions matching campnw's internal API: search, check, drive time matrix lookup, campground detail
- Conversation state management (server-side session or client-side context window)
- Itinerary data model: `{legs: [{campground_id, dates, drive_time_from_prev, availability_status, booking_url}]}`
- Itinerary storage for sharing (SQLite table with UUID key, JSON payload, expiry timestamp)
- Rate limiting: trip planner sessions are expensive (~$0.01-0.05 per session). Cap at 5/day for free users.

### Dependencies
- v0.6 (Anthropic SDK already integrated)
- v0.4 (accounts for rate limiting and itinerary saving)

### Key Risk
Cost per session. Claude Sonnet with function calling is meaningfully more expensive than Haiku NL parsing. A single trip planning session with 3-4 tool calls could cost $0.03-0.10. At scale, this needs a paid tier or aggressive rate limiting. Also: conversation quality requires careful prompt engineering and testing -- hallucinated campgrounds (recommending places not in the registry) would be a trust-breaking failure. Guardrail: only recommend campgrounds returned by the tool calls, never from the model's training data.

---

## v0.9 "Predictions"

### Theme
Predictive availability -- "when will it open?" This milestone requires 6+ months of polling data, so it's sequenced late by design. Also includes smart notification scoring (P2-2), which uses the same diff history data.

### Features

| Feature | PRD Ref | Effort | Description |
|---------|---------|--------|-------------|
| Availability prediction display | P1-3 | L | For fully-booked campgrounds, show: "Sites here typically free up X-Y days before the date" with confidence band. Cold start fallback: rec.gov booking window + "we're still learning" notice. |
| Historical data collection infra | AI-2 | M | Every poll result stored as a time-series record: `{campground_id, site_id, date, status, observed_at}`. This should ship earlier (v0.5) as a silent backend addition, with the user-facing predictions arriving here. |
| Statistical prediction model | AI-2 | L | Time-series analysis: median days-before-date that cancellations appear, standard deviation, confidence interval. Per-campground. Not an LLM -- pure statistical. |
| Smart notification scoring | P2-2 | M | When a watch fires, attach urgency context: "Usually books within 30 minutes" vs "Typically stays open for hours." Rule-based initially, logistic regression when data permits. |
| Prediction confidence display | P1-3 | S | Visual confidence indicator (low/medium/high) based on sample size. Transparent about data limitations. |

### Technical Work
- Time-series storage table: `availability_history` with `(campground_id, site_id, date, status, observed_at)` -- indexed for efficient window queries
- Statistical analysis module: `predictions/model.py` with cancellation pattern detection
- Pre-computation job: run predictions nightly, cache results per campground
- Notification scoring: analyze diff history for time-to-rebook patterns
- API response extension: predictions field on campground results when available

### Dependencies
- v0.5 (background polling must be running for 6+ months to accumulate meaningful data)
- Data collection should start at v0.5 even though user-facing predictions ship here

### Key Risk
Data quality and sample size. Predictions are only as good as the polling history. Campgrounds polled infrequently or recently added will have low-confidence predictions. Must be transparent about this -- show confidence levels, never overstate certainty. The cold start problem is real: "we're still learning" is an honest answer for the first season.

---

## v1.0 "campnw 1.0"

### Theme
Polish, power user features, and the map view. This milestone is about crossing the finish line with quality. Every P0 and P1 feature is complete. Select P2 features (map view, keyboard shortcuts) ship based on time and appetite.

### Features

| Feature | PRD Ref | Effort | Description |
|---------|---------|--------|-------------|
| Map view | P2-1 | L | Interactive Leaflet/Mapbox map with campground pins. Pin color encodes availability density. Click for quick preview, click through to detail. Clustering at low zoom. |
| Keyboard shortcuts | P2-6 | M | `j/k` navigation, `b` bookmark, `w` watch, `?` help overlay. Discoverable via help modal. |
| Campground detail enrichment | P2-4 | M | Amenity data beyond tags: site count, fire rings, bear boxes. Link to recreation.gov photos. No user reviews in v1.0. |
| Registry expansion | P2-5 | M | Re-seed RIDB for complete ID and OR federal coverage. Target: 1,000+ campgrounds. |
| Personalized recommendations | P2-3 | L | Based on search history and saved campgrounds, surface proactive suggestions. Opt-in, privacy-first. Requires accounts. |
| Performance audit and optimization | P0-1 | M | P95 search under 4 seconds. Lighthouse audit. Bundle size review. Image optimization. |
| Comprehensive error states | -- | S | Empty states, offline handling, provider-down messaging. Every error path has a designed response. |
| Accessibility audit | P0-7 | M | WCAG 2.1 AA compliance. Screen reader testing. Focus management. Color contrast verification (especially heat map and dark mode). |

### Technical Work
- Leaflet.js integration with React (react-leaflet or custom wrapper)
- GeoJSON layer for campground pins with availability-density coloring
- Keyboard event system with shortcut registry and help modal
- RIDB re-seed script updates for comprehensive coverage
- Lighthouse CI integration in GitHub Actions
- Accessibility testing tooling (axe-core)

### Dependencies
- All previous milestones (this is the final release)

### Key Risk
Scope management. v1.0 has the most P2 features and the greatest temptation to keep adding "one more thing." The map view alone is a significant UI effort. Define a hard cut-off: if a P2 feature isn't 80% complete two weeks before the target ship date, it moves to v1.1. Ship a polished v1.0 over a feature-complete but rough one.

---

## Cross-Cutting Concerns

### Data Collection (start at v0.5, use at v0.9)
The availability prediction system needs months of polling data. The `availability_history` table and collection logic should ship silently in v0.5 when background polling goes live, even though the user-facing prediction features don't arrive until v0.9. Every poll cycle writes to this table. By v0.9, there should be 4-6 months of data.

### Registry Maintenance
The campground registry is a living dataset. Automated monthly re-seeding from RIDB (rec.gov) and quarterly refresh from GoingToCamp should be set up in v0.5 alongside the background job queue. Drift detection (campgrounds that consistently 404) should flag entries for manual review.

### Cost Model
| Component | v0.2-v0.4 | v0.5+ | v1.0 |
|-----------|-----------|-------|------|
| Fly.io | ~$0/mo (auto-sleep) | ~$5-7/mo (always-on for polling) | ~$7-15/mo |
| Anthropic API | $0 | $0 | ~$10-30/mo (NL search + trip planner) |
| Auth provider | $0 | $0 (free tier) | $0-25/mo (depends on MAU) |
| Total | ~$0/mo | ~$5-7/mo | ~$17-70/mo |

These are personal-project scale costs. If usage grows beyond single-user, the Anthropic API costs are the primary scaling concern. Rate limiting on AI features is essential.

### Testing Strategy
- Unit tests for providers and search engine (existing, extend as needed)
- Integration tests for API endpoints (add starting v0.2)
- E2E tests for critical web flows: search, watch creation, booking link click (add at v0.5)
- AI feature testing: golden-set evaluation for NL parsing accuracy (v0.6)

### Deployment
The current GitHub Actions CI/CD pipeline deploys to Fly.io on push to main. This workflow is sufficient through v1.0. Key additions:
- v0.5: Fly.io machine config change (`min_machines_running = 1`)
- v0.7: Docker image size increase (Playwright/Chromium) -- may need larger machine or multi-stage build
- v1.0: Lighthouse CI check in PR pipeline

---

## What's Explicitly Post-v1.0

These items from the PRD are out of scope for v1.0:

- **Idaho State Parks** (separate booking system, low user demand)
- **Native mobile apps** (web-first is the right call for this scale)
- **Booking intermediation** (legal complexity, not aligned with the tool's positioning)
- **User reviews and photo uploads** (community features need critical mass)
- **Cell coverage overlay** (crowdsourced data is hard to bootstrap)
- **Full personalized recommendation engine** (basic version in v1.0, ML-powered version post-v1.0)

---

## Decision Log

| Decision | Rationale | Alternatives Considered |
|----------|-----------|------------------------|
| Ship watches on web before accounts | Highest-value gap to close. Anonymous watches with session tokens avoid forcing account creation for core functionality. | Wait for accounts first -- rejected because it delays the most requested feature. |
| Calendar heat map in v0.3, not v0.2 | Heat map needs backend API work (availability density endpoint). Watches are simpler and higher immediate value. | Ship together -- rejected because it makes v0.2 too large. |
| Accounts in v0.4, not earlier | Accounts alone deliver no user value. v0.4 pairs them with features that require accounts (saved prefs, persistent watches, search history). | v0.2 -- rejected because anonymous watches handle the immediate need. |
| NL search before trip planner | NL search is simpler (single API call, Haiku pricing), directly reduces friction on the core action, and proves out the Anthropic SDK integration. | Trip planner first -- rejected because it's higher complexity and cost per session. |
| Oregon State Parks in v0.7 | Provider work is independent and high-effort (Playwright). Sequencing it mid-roadmap gives time to learn from GoingToCamp integration patterns. | Earlier -- rejected because Playwright adds Docker complexity. Later -- rejected because it's P1. |
| Predictions in v0.9 | Requires 6+ months of polling data. Starting data collection at v0.5 means 4+ months of history by v0.9. | v0.7 -- rejected because insufficient data. v1.0 -- acceptable fallback if data is thin. |
| SQLite over PostgreSQL | Single-instance Fly.io deployment. SQLite is simpler, faster for read-heavy workloads, and sufficient at personal-project scale. Revisit if multi-instance becomes necessary. | PostgreSQL -- overkill for current scale. Turso/libsql -- good option if multi-instance needed later. |
