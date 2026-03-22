# campnw Roadmap: v0.2.1 to v1.0

**Last updated:** March 2026
**Current version:** v0.2 (deployed at campnw.palouselabs.com)

---

## Timeline Summary

```
v0.1    [SHIPPED]  Foundation          — Multi-provider search, CLI watches, dashboard
v0.2    [SHIPPED]  Watches on the Web  — Web-based watch management, dark mode
v0.2.1  ------->   Hardening           — Security fixes, Level A a11y failures, perf wins
v0.3    ------->   Calendar & Polish   — Calendar heat map, SSE streaming, shareable links
v0.4    ------->   Accounts            — User accounts, saved preferences, persistent watches
v0.5    ------->   Background Engine   — Server-side polling, web push notifications
v0.6    ------->   AI Search           — Natural language as entry point, search history
v0.7    ------->   Oregon Expansion    — Oregon State Parks, registry enrichment
v0.8    ------->   Trip Planner        — AI-powered multi-stop itinerary builder
v0.9    ------->   Predictions         — Availability predictions, smart notifications
v1.0    ------->   campnw 1.0          — Map view, power user features, final polish
```

Each milestone is a shippable increment with clear user value. P0 features complete by v0.5. P1 features complete by v0.8–v0.9. P2 features are stretch for v1.0 or deferred.

---

## v0.2.1 "Hardening"

### Theme
v0.2 shipped the anonymous watch system. Before adding more features on top of it, fix the security issues and Level A accessibility failures uncovered during review. These are small, high-leverage changes — most are one-liners or targeted edits. Ship this as a patch release, not a feature milestone.

### Security Fixes (all HIGH or 1-line)

| Issue | Severity | Fix |
|-------|----------|-----|
| Cookie missing `Secure` flag | HIGH | Add `Secure` to session cookie on `Set-Cookie`. One-line fix. |
| CORS locked to `localhost` | HIGH | Move `allow_origins` to environment variable (`CORS_ORIGIN`). Defaults to `*` in dev, must be set in production. |
| `/api/track` unauthenticated log injection | HIGH | Add input validation, body size cap (1KB), and rate limit (10 req/min per IP) to the tracking endpoint. |
| Search `limit` param uncapped | MEDIUM | Cap at 50 via FastAPI validator. Add SlowAPI rate limiting on search endpoints (20 req/min per IP). |
| `facility_id` unvalidated in URL path | LOW | Add regex validator (`^\d+$`) on path param. Reject non-numeric values with 422. |
| GitHub Actions `flyctl` pinned to `@master` | MEDIUM | Pin to a specific SHA in `.github/workflows/deploy.yml`. |

### Accessibility Fixes (all Level A — must not ship broken)

The accessibility agent identified 8 Level A failures in the current codebase. These must be fixed before v0.3 adds the heat map.

| Issue | Fix |
|-------|-----|
| `div`-as-button elements | Replace with `<button>` elements. Ensures keyboard access and correct role. |
| Missing landmark regions | Add `<main>`, `<nav>`, `<header>`, `<footer>` landmarks. Screen readers depend on these for orientation. |
| No focus trap on watch panel | Implement focus trap when the watch creation panel is open. Tab should cycle within the panel, not escape to background. |
| No `aria-pressed` on toggle buttons (dark mode, source filter) | Add `aria-pressed` attribute, updated dynamically to reflect state. |
| Dark mode accent color (#4a7a38) fails contrast (~2.7:1, needs 4.5:1) | Lighten to pass 4.5:1 against dark backgrounds when used for text. Keep the darker value for decorative use only. |
| Dark mode `--text-light` (#66665e) fails contrast (~2.2:1) | Brighten to at least #9a9990 or equivalent passing value. |

### Performance Quick Wins

| Issue | Fix |
|-------|-----|
| Search has 3.5s of artificial sleep | Increase `batch_size` from 1 to 5, reduce inter-batch `delay` to 0.3s. Measurable speedup with no risk. |
| No bundle visibility | Add `vite-bundle-visualizer` as a dev dependency. Run once before v0.3 to baseline bundle size. |

### Quality Baseline
- All Level A WCAG failures resolved
- axe-core added to CI — failing Level A violations block merges from this milestone forward
- Security: cookie, CORS, and `/api/track` issues resolved before any new users onboard

### Dependencies
- v0.2 shipped (done)

---

## v0.3 "Calendar & Polish"

### Theme
The calendar heat map transforms how users understand availability across time. SSE streaming makes search feel fast and progressive. Shareable links make campnw useful for group planning. This milestone also locks in design foundations (CSS variables, colorblind-safe palette, component directory structure) that would be expensive to retrofit later.

### Features

| Feature | PRD Ref | Effort | Description |
|---------|---------|--------|-------------|
| Calendar heat map (search results) | P0-6 | L | Aggregate availability density by day across months. Single-hue color scale (not red-to-green) with text density labels. Clicking a day filters results to that window. See design requirements below. |
| Calendar heat map (single campground) | P0-6 | M | Per-campground availability calendar on the detail/check view. Same scale, clickable dates. |
| SSE streaming for search results | P0-1 | M | Server-sent events stream results as each provider responds. Front-end renders cards as they arrive. Eliminates the "nothing for 6 seconds then everything" experience. |
| Shareable search links | P1-5 | M | Encode search parameters in URL query string. Copy-link button on results page. No account required to view. |
| Zero-result state with Watch CTA | UX | S | When a search returns no results, the primary action should be "Watch this search" — not just "try different dates." Pre-fill watch from current search params. |
| Micro-interactions | Design | S | Availability chips animate in as data loads. Smooth transitions on filter changes. Expand/collapse animations on result cards. |

### Calendar Heat Map Design Requirements
These must be specified and agreed before building the component:

- **Color scale:** Single-hue progression (e.g., light blue to dark blue). Never red-to-green — fails for ~8% of users with color vision deficiency.
- **Text labels:** Show density count inside or adjacent to each day cell (e.g., "3 sites"). Color should reinforce, not replace, the number.
- **Keyboard navigation:** `role="grid"` with arrow key navigation from day one. Each cell gets `aria-label="[day], [N] sites available"`.
- **Interaction model:** Clicking a day executes a filtered search for that date window (single-night or the user's requested night count starting that day). Make this behavior explicit in the UI.
- **Accessibility:** Cells also need a tooltip on hover and a summary row for screen readers.

### Technical Work
- New `CalendarHeatMap` React component with `role="grid"` keyboard navigation
- Backend endpoint `/api/availability-density` returning per-day counts (not full site lists) to avoid N+1 patterns
- SSE endpoint for streaming search results: `GET /api/search/stream` with `text/event-stream` response
- URL state synchronization: search form state serialized to/from URL query params
- CSS variable migration completed across all components (not just new ones)
- Component directory structure established: `web/src/components/{ui,search,calendar,watches}/`
- `CalendarHeatMap` story or fixture for visual regression testing

### Quality Baseline
- axe-core CI continues to block Level A failures
- Calendar heat map passes WCAG 1.4.1 (Use of Color) at build time — enforced in code review
- CSS `--text-light` and accent contrast fixes applied to any new dark mode components
- SSE error states designed alongside happy path (provider timeout, empty stream, connection drop)
- Zero-result state designed (not just coded) before shipping

### Dependencies
- v0.2.1 (Level A a11y fixes and CSS variable system must be in place before adding the heat map)

### Key Risk
The heat map API contract. The current search response doesn't return per-day density counts. Design `/api/availability-density` carefully — it's a new endpoint with different performance characteristics than search (aggregation-heavy, cache-friendly). Also: SSE requires the FastAPI response to stream without buffering; verify this works correctly on Fly.io's proxy layer.

---

## v0.4 "Accounts"

### Theme
Accounts are infrastructure, not a feature — so this milestone pairs them with the features they unlock: saved home base, persistent watches that survive browser clears, and search history. Users should feel immediate value from creating an account. Before shipping, fix the watch-existence information leak that anonymous session design introduced.

### Features

| Feature | PRD Ref | Effort | Description |
|---------|---------|--------|-------------|
| User accounts (email + Google OAuth) | P1-1 | L | Managed auth via Auth.js or Clerk. Minimal data collection: email, display name, home base. |
| Saved home base and preferences | P1-1 | M | Persist home base city, default search preferences (nights, tags, source). Pre-fill search form on return visits. |
| Persistent watch ownership | P1-1 | S | Migrate anonymous watches to account on sign-up. Watches tied to account survive device changes. |
| Anonymous watch email collection | P1-1 | S | For anonymous (pre-account) watches, collect email at watch creation time to enable notification delivery. Email stored ephemerally, not linked to identity. Clear disclosure about what it's used for. |
| Search history | P1-1 | M | Last 20 searches saved per account. Quick re-run from history list. |
| Privacy controls | P1-1 | S | Data export (JSON) and account deletion. Clear explanation of what data is stored. |

### Security Work (pre-ship requirements)
- **Fix cross-user watch uniqueness leak:** The current schema allows a `UNIQUE` constraint collision to reveal that another user is watching the same campground. Restructure so constraint failures return a generic error, not a distinguishable one.
- **Redact `from_location` from logs:** This field is currently logged in plaintext. Strip it before logs are written.
- **Auth provider selection:** Decide on Clerk vs Auth.js before starting v0.4 work. Document the decision.
- **Session migration plan:** Anonymous session-token watches must have a clear migration path to account ownership. Write this before touching the auth middleware.

### Technical Work
- Auth provider integration (Clerk recommended for speed; Auth.js if self-hosted preference)
- User table in SQLite (or migrate to libsql/Turso if multi-instance becomes necessary)
- Session middleware in FastAPI (JWT or session cookies)
- Watch ownership migration: link anonymous session-token watches to new account
- Search history table: `{user_id, query_params_json, result_count, searched_at}`
- Protected API endpoints: watches require auth or valid session token

### Quality Baseline
- Watch schema privacy fix ships with v0.4 — not after
- `from_location` log redaction ships with v0.4
- Error states for auth flows (bad credentials, expired session, OAuth failure) designed before coding
- axe-core CI continues; auth forms must pass Level AA contrast on both light and dark themes

### Dependencies
- v0.2 (anonymous watches need migration path)
- v0.2.1 (security fixes establish baseline before adding auth layer)

### Key Risk
Auth complexity touching every API call. Keep the unauthenticated experience fully functional — accounts enhance but never gate core search. Scope creep into profile features is the other risk; resist adding anything beyond what's listed. The anonymous email collection for watches is intentionally minimal — do not expand it into a marketing list.

---

## v0.5 "Background Engine"

### Theme
Move watch polling from CLI cron to server-side background jobs. Add web push notifications so users get alerts without needing ntfy or Pushover. This completes the P0-5 watch system as a fully web-native feature. Also ships the availability cache layer, which reduces redundant API calls across all polling.

### Features

| Feature | PRD Ref | Effort | Description |
|---------|---------|--------|-------------|
| Server-side watch polling | P0-5 | L | APScheduler embedded in FastAPI polls all active watches every 15 minutes. Batches watches by campground to minimize API calls. |
| Web push notifications | P0-5 | L | Service worker + Web Push API (with PWA manifest). Notification includes campground name, site number, available dates, direct booking link. |
| Notification preferences | P0-5 | M | Per-watch notification channel selection: web push, ntfy, Pushover, or email. |
| Watch polling dashboard | P0-5 | S | Simple status view: last poll time, next poll time, total active watches, recent notifications. |
| Availability cache | Perf | M | 10–15 minute TTL cache per campground keyed on `(campground_id, month)`. Prevents redundant calls when multiple watches target the same campground. Stored in SQLite with `cached_at` timestamp. |
| Historical data collection (silent) | AI-2 | S | Every poll result appended to `availability_history` table. No user-facing feature yet — just the data foundation for v0.9 predictions. |

### iOS Web Push Requirement
Web push on iOS requires a PWA manifest (`manifest.json`) with `display: standalone` and a registered service worker. This must be in place for the push subscription flow to work on Safari iOS 16.4+. Add the manifest at v0.5, not as an afterthought.

### Technical Work
- APScheduler integration with FastAPI lifespan
- Service worker (`sw.js`) in React build output for push + offline shell
- PWA manifest (`manifest.json`) with app name, icons, display mode
- VAPID key generation and storage for web push
- Push subscription storage in user record
- Availability cache table: `{campground_id, month, payload_json, cached_at}`
- Batch optimization: group watches by campground_id per cycle
- `availability_history` table: `(campground_id, site_id, date, status, observed_at)`
- Fly.io: `min_machines_running = 1` required for background polling (increases to ~$5–7/mo)

### Quality Baseline
- Push notification permission prompt follows best-practice UX: shown after user action (watching a campground), not on page load
- Error states for push permission denial designed (fallback to ntfy/email channel)
- Cache invalidation logic documented — what triggers a cache bust vs. TTL expiry
- Polling loop must handle provider failures gracefully (one provider down must not block others)

### Dependencies
- v0.4 (accounts required for persistent push subscriptions)
- v0.2 (web watch management)

### Key Risk
Fly.io always-on cost and polling volume. Background polling requires `min_machines_running = 1`. With 685+ campgrounds, batching watches aggressively is essential — aim for one availability check per campground per cycle regardless of how many watches target it. Cap free-tier watches at 3 per user. The availability cache at this milestone significantly reduces call volume.

---

## v0.6 "AI Search"

### Theme
Natural language as the primary entry point for search. Users type what they want in plain English and campnw auto-fills the structured search form — they review the extracted parameters and execute. NL is not a toggle or a separate mode; it's the first thing users see in the search interface. The form remains fully editable before search executes.

### Features

| Feature | PRD Ref | Effort | Description |
|---------|---------|--------|-------------|
| NL search as primary entry point | P1-2 | L | The search interface leads with a natural language input. Claude Haiku parses the query into structured params, which auto-populate the form fields. User reviews and edits before running. |
| NL parse feedback and correction | P1-2 | M | Extracted params are shown as editable chips or form fields. Any field the user edits after NL parse is tracked as a correction signal. |
| NL parse accuracy tracking | AI-1 | S | Log extracted params vs. user edits. Track misparse rate per param type. Feed into prompt improvements. |
| Search history | P1-1 | M | Last 20 searches saved per account. Quick re-run from history list. |

### NL Search UX Requirement
This is **not a form/NL toggle**. The UX agent identified that a toggle creates friction and dilutes the entry point. The intended behavior:

1. User sees a single text input: "Where do you want to camp?"
2. User types: "somewhere near Rainier, 2 nights in July, lakeside"
3. campnw calls `/api/search/parse`, shows a 400–800ms skeleton
4. Form fields animate in with extracted values pre-filled
5. User can edit any field, then runs the search

The structured form below the NL input acts as the edit layer — not a separate mode.

### Prompt Injection Defense (pre-ship requirement)
NL search introduces an LLM in the request path. Before shipping:
- System prompt must be hardened against jailbreak attempts that could exfiltrate context or produce unexpected structured output
- `/api/search/parse` response must be validated against the `SearchQuery` schema — never passed through raw
- Set Anthropic API spend limits in account settings before enabling the endpoint in production

### Technical Work
- Anthropic Python SDK integration
- `ANTHROPIC_API_KEY` in Fly.io secrets
- New endpoint: `POST /api/search/parse` — accepts text, returns structured `SearchQuery` JSON
- Prompt template with registry metadata context (tag list, base cities, state codes, date presets)
- Model: Claude Haiku (800ms P95 budget). Fallback: show the blank form with a toast if the API call fails.
- `aria-live="polite"` region for extracted params announcement to screen readers
- Rate limit NL parse: 10 req/min per user

### Quality Baseline
- `aria-live` region for NL extraction feedback — screen readers announce what was understood
- Loading state and error state designed before coding (skeleton during parse, graceful fallback on failure)
- Prompt injection hardening in place before any public-facing use
- Spend limit configured in Anthropic account

### Dependencies
- v0.4 (accounts for usage tracking and rate limiting), though technically usable with anonymous sessions

### Key Risk
Prompt reliability on ambiguous queries. "Near Seattle" spans 1–3 hours of drive time; "this summer" spans months. Strategy: when ambiguous, choose a sensible default and show it — never silently narrow the search. Latency is the second risk: if Haiku P95 exceeds 1.5s in production, the interaction model breaks. Measure on first deploy.

---

## v0.7 "Oregon Expansion"

### Theme
Oregon State Parks integration completes the PNW picture. This is the last major provider integration and meaningfully expands the campground registry. Pairs provider work with registry enrichment, which has been deferred long enough — campground detail data should reach a quality bar before the trip planner uses it in v0.8.

### Features

| Feature | PRD Ref | Effort | Description |
|---------|---------|--------|-------------|
| Oregon State Parks provider | P1-6 | XL | ReserveAmerica platform via Playwright headless browser. New provider module: `providers/reserveamerica.py`. |
| Oregon campground registry seed | P1-6 | M | Seed 200+ Oregon State Parks campgrounds. Auto-generate tags. Compute drive times from Portland and other bases. |
| OR State Parks source filter | P1-6 | S | `--source or-state` in CLI, `source=or_state` in API. Source badge in dashboard. |
| Registry enrichment pass | P0-2 | M | Improve auto-generated tags for all 900+ campgrounds. Fill gaps in drive time data. Manual curation for top 50 most-searched. Amenity data (site count, fire rings, bear boxes) added now — serves both this milestone and the trip planner in v0.8. |
| Booking link validation | P0-4 | S | Verify booking links resolve before surfacing. Flag stale links from provider changes. |

### Technical Work
- Playwright integration for ReserveAmerica (headless Chrome in Docker)
- New `BookingSystem.OR_STATE` enum value
- `providers/reserveamerica.py` with session management and availability parsing
- Dockerfile update: add Playwright + Chromium (significant image size — use multi-stage build)
- `scripts/seed_or_state.py` for registry seeding
- Rate limiting and retry logic for ReserveAmerica

### Quality Baseline
- OR State Parks results labeled "temporarily unavailable" when Playwright is blocked — graceful degradation from day one
- Registry enrichment quality gate: top 50 campgrounds manually reviewed before v0.8 trip planner ships
- No new axe-core failures from OR State Parks UI additions

### Dependencies
- None (provider work is independent)

### Key Risk
ReserveAmerica bot protection and Docker image size. Playwright adds ~400MB (Chromium). Consider whether this is acceptable at Fly.io scale or whether a browser API service (browserless.io, etc.) makes more sense. Registry enrichment is also a manual-curation effort — timebox it rather than chasing perfection.

---

## v0.8 "Trip Planner"

### Theme
The AI trip planner — the flagship P1 feature. A conversational interface where users describe a multi-day trip and get an itinerary with real-time availability checks, drive times, and booking links. The component architecture and detail data established in v0.7 make this possible. Quality bar: no hallucinated campgrounds.

### Features

| Feature | PRD Ref | Effort | Description |
|---------|---------|--------|-------------|
| Trip planner conversational UI | P1-4 | XL | Chat-style interface. User describes trip intent. Claude Sonnet asks clarifying questions, then generates a multi-stop itinerary. |
| Tool-calling integration | AI-3 | L | Claude function calling with campnw tools: `search_campgrounds`, `check_availability`, `get_drive_time`, `get_campground_detail`. Only recommend campgrounds returned by tool calls — never from training data. |
| Itinerary card view | P1-4 | L | Day-by-day cards with campground name, drive time from previous stop, availability status, booking link. Editable — user can ask to swap a leg. |
| Shareable itineraries | P1-5 | M | Save itinerary as a shareable link. Availability snapshot at share time with "as of [timestamp]" caveat. 30-day expiry. |

### Component Architecture Prerequisite
The chat UI is the most complex component in the app. Before building it:
- Establish `web/src/components/` directory structure (should be done by v0.3, confirmed here)
- Define shared design tokens in CSS variables for chat bubbles, transcript scroll, input area
- `role="log"` on the message transcript for screen reader live region
- Focus management on new message arrival (don't steal focus, do announce)

### Technical Work
- Anthropic SDK with function calling (Claude Sonnet)
- New endpoint: `POST /api/trip-planner` (streaming response)
- Tool definitions: search, check, drive time matrix, campground detail
- Conversation state management (server-side session or client-side context window)
- Itinerary data model: `{legs: [{campground_id, dates, drive_time_from_prev, availability_status, booking_url}]}`
- Itinerary storage for sharing (SQLite, UUID key, JSON payload, expiry timestamp)
- Rate limiting: cap at 5 trip planning sessions/day per user (Sonnet with function calls is ~$0.03–0.10/session)

### Quality Baseline
- `role="log"` on transcript, `aria-live` for loading states
- Focus management: new assistant messages announced, focus stays on input
- Hallucination guardrail: response validator checks all recommended campground IDs against registry before displaying
- Cost monitoring: log token counts per session; alert if average session cost exceeds $0.15

### Dependencies
- v0.6 (Anthropic SDK integrated)
- v0.4 (accounts for rate limiting and itinerary saving)
- v0.7 (registry enrichment — trip planner needs good detail data to recommend well)

### Key Risk
Session cost at scale and conversation quality. A single session with 4 tool calls costs $0.03–0.10. Rate limiting is non-negotiable. Prompt engineering for the itinerary task is also genuinely hard — test with real trip scenarios before shipping.

---

## v0.9 "Predictions"

### Theme
Predictive availability — "when will it open?" This requires 6+ months of polling data, sequenced late by design. Data collection starts silently at v0.5. Also includes smart notification scoring using the same diff history.

### Features

| Feature | PRD Ref | Effort | Description |
|---------|---------|--------|-------------|
| Availability prediction display | P1-3 | L | For booked-out campgrounds: "Sites typically free up X–Y days before the date" with confidence band. Cold start fallback: "we're still learning." |
| Statistical prediction model | AI-2 | L | Time-series analysis: median days-before-date that cancellations appear, standard deviation, confidence interval. Per-campground. Pure statistical — not an LLM. |
| Smart notification scoring | P2-2 | M | When a watch fires, attach urgency context: "Usually books within 30 minutes" vs "Typically stays open for hours." Rule-based initially. |
| Prediction confidence display | P1-3 | S | Visual confidence indicator (low/medium/high) based on sample size. Transparent about data limitations. |

### Technical Work
- Statistical analysis module: `predictions/model.py` with cancellation pattern detection
- Pre-computation job: nightly predictions cached per campground
- Notification scoring: analyze diff history for time-to-rebook patterns
- API response extension: predictions field on campground results when available

### Quality Baseline
- Prediction confidence is always displayed — never show a prediction without showing its certainty level
- "We're still learning" cold start state is a designed state, not an empty one
- Prediction display passes contrast on both light and dark themes

### Dependencies
- v0.5 (background polling running for 6+ months — data collection started there)

### Key Risk
Data quality and sample size. Campgrounds polled infrequently will have unreliable predictions. Transparency is the mitigation — show confidence levels, never overstate certainty.

---

## v1.0 "campnw 1.0"

### Theme
Polish, power features, and the map view. Every P0 and P1 feature is complete. Select P2 features ship based on time and appetite. The goal is a polished v1.0 over a feature-complete-but-rough one.

### Features

| Feature | PRD Ref | Effort | Description |
|---------|---------|--------|-------------|
| Map view | P2-1 | L | Interactive Leaflet/Mapbox map with campground pins. Pin color encodes availability density. Click for quick preview, click through to detail. Clustering at low zoom. Lazy-loaded — not in the initial bundle. |
| Keyboard shortcuts | P2-6 | M | `j/k` navigation, `b` bookmark, `w` watch, `?` help overlay. Discoverable via help modal. |
| Registry expansion | P2-5 | M | Re-seed RIDB for complete ID and OR federal coverage. Target: 1,000+ campgrounds. |
| Personalized recommendations | P2-3 | L | Based on search history and saved campgrounds, surface proactive suggestions. Opt-in, privacy-first. Requires accounts. |
| Bundle audit and optimization | P0-1 | M | Lighthouse audit. Map view lazy-loaded (current 200KB bundle is healthy — keep it that way). Image optimization. P95 search under 4 seconds. |

### Quality Baseline
- WCAG 2.1 AA compliance audit across all components — not just new ones
- Map view color encoding for availability density must use a colorblind-safe palette (consistent with heat map color strategy from v0.3)
- Map view is lazy-loaded at the route level — not in the initial JS bundle
- All error states across the app reviewed: every provider-down, empty-state, offline-handling path has a designed response
- Final axe-core run with zero Level A or Level AA failures before tagging v1.0

### Technical Work
- Leaflet.js integration (react-leaflet or custom wrapper)
- GeoJSON layer for campground pins with availability-density coloring
- Keyboard event system with shortcut registry and help modal
- Lighthouse CI in GitHub Actions PR pipeline
- RIDB re-seed script updates for comprehensive coverage
- Full axe-core audit in CI (currently blocking Level A; expand to Level AA for v1.0)

### Dependencies
- All previous milestones

### Key Risk
Scope management. Map view alone is a significant UI effort. Hard rule: any P2 feature that isn't 80% complete two weeks before the target ship date moves to v1.1.

---

## Cross-Cutting Concerns

### Accessibility Baseline (per milestone)

| Milestone | Requirement |
|-----------|-------------|
| v0.2.1 | Fix all 8 Level A failures. Add axe-core to CI blocking Level A. Fix dark mode contrast failures. |
| v0.3 | Heat map uses colorblind-safe single-hue scale + text labels + `role="grid"` from day one. |
| v0.4 | Auth forms pass Level AA contrast. Error states for auth flows designed before coding. |
| v0.5 | Push permission UX follows best practices (no on-load prompts). |
| v0.6 | `aria-live` for NL extraction. |
| v0.8 | `role="log"` on transcript. Focus management on new messages. |
| v1.0 | Full WCAG 2.1 AA audit. CI expanded to block Level AA failures. |

The principle: fix accessibility at build time, not in a batch audit. Color contrast and semantic HTML are cheapest when designed from the start.

### Security Baseline (per milestone)

| Milestone | Requirement |
|-----------|-------------|
| v0.2.1 | Cookie `Secure` flag, CORS env config, `/api/track` validation + rate limit, `limit` param cap. |
| v0.4 | Watch schema privacy fix, `from_location` log redaction, auth provider decision, session migration plan. |
| v0.6 | Prompt injection hardening, Anthropic spend limit configured. |
| v0.8 | Hallucination guardrail (tool-call-only recommendations), session cost monitoring. |

### Performance Baseline (per milestone)

| Milestone | Target |
|-----------|--------|
| v0.2.1 | Search time reduced by ~3.5s via batch_size/delay fix. Bundle baseline captured with vite-bundle-visualizer. |
| v0.3 | SSE streaming eliminates "nothing then everything" UX. |
| v0.5 | Availability cache (10–15min TTL) prevents redundant API calls across watch polling. |
| v1.0 | Map view lazy-loaded. P95 search under 4 seconds. Lighthouse audit passing. |

### Data Collection (start at v0.5, use at v0.9)
The `availability_history` table ships silently in v0.5 alongside background polling. Every poll cycle writes a row. By v0.9, there should be 4–6 months of data. Do not wait until v0.9 to start collecting.

### Registry Maintenance
The campground registry is a living dataset. Automated monthly re-seeding from RIDB and quarterly refresh from GoingToCamp should be set up in v0.5. Drift detection (campgrounds that consistently 404) should flag entries for manual review.

### Cost Model
| Component | v0.2–v0.4 | v0.5+ | v1.0 |
|-----------|-----------|-------|------|
| Fly.io | ~$0/mo (auto-sleep) | ~$5–7/mo (always-on for polling) | ~$7–15/mo |
| Anthropic API | $0 | $0 | ~$10–30/mo (NL search + trip planner) |
| Auth provider | $0 | $0 (free tier) | $0–25/mo (depends on MAU) |
| Total | ~$0/mo | ~$5–7/mo | ~$17–70/mo |

Rate limiting on AI features is non-negotiable. Spend limits in the Anthropic account are a pre-ship requirement for v0.6.

### Testing Strategy
- Unit tests for providers and search engine (existing, extend as needed)
- Integration tests for API endpoints (add starting v0.2)
- E2E tests for critical flows: search, watch creation, booking link click (add at v0.5)
- AI feature testing: golden-set evaluation for NL parsing accuracy (v0.6)
- axe-core in CI from v0.2.1 onward (Level A); expanded to Level AA at v1.0

### Deployment
Current GitHub Actions CI/CD deploys to Fly.io on push to main. Key additions:
- v0.2.1: Pin `flyctl` GitHub Action to SHA (not `@master`)
- v0.5: `min_machines_running = 1` in `fly.toml`
- v0.7: Docker image size increase (Playwright/Chromium) — likely needs multi-stage build or larger machine
- v1.0: Lighthouse CI check in PR pipeline

---

## What's Explicitly Post-v1.0

- **Idaho State Parks** (separate booking system, low demand)
- **Native mobile apps** (web-first is right for this scale)
- **Booking intermediation** (legal complexity, misaligned with the tool's positioning)
- **User reviews and photo uploads** (community features need critical mass)
- **Cell coverage overlay** (crowdsourced data is hard to bootstrap)
- **Full personalized recommendation engine** (basic version in v1.0, ML-powered post-v1.0)

---

## Decision Log

| Decision | Rationale | Alternatives Considered |
|----------|-----------|------------------------|
| Ship watches on web before accounts | Highest-value gap to close. Anonymous watches with session tokens avoid forcing account creation for core functionality. | Wait for accounts first — rejected because it delays the most requested feature. |
| Calendar heat map in v0.3, not v0.2 | Heat map needs backend API work (availability density endpoint). Watches are simpler and higher immediate value. | Ship together — rejected because it makes v0.2 too large. |
| Accounts in v0.4, not earlier | Accounts alone deliver no user value. v0.4 pairs them with features that require accounts (saved prefs, persistent watches, search history). | v0.2 — rejected because anonymous watches handle the immediate need. |
| NL as entry point, not a toggle (v0.6) | UX agent finding: a form/NL toggle splits the interaction model and trains users to ignore the NL input. Auto-filling the form from NL parse gives the best of both — fast entry and user review before execution. | Toggle mode — rejected based on UX recommendation. Separate NL-only mode — rejected because form editing should remain the confirmation step. |
| NL search before trip planner | NL search is simpler (single API call, Haiku pricing), reduces friction on the core action, and proves out Anthropic SDK integration. | Trip planner first — rejected because higher complexity and cost per session. |
| Registry enrichment moved to v0.7 | Trip planner in v0.8 needs good campground detail data. Doing enrichment the milestone before ensures the data quality bar is met when it matters. | v1.0 enrichment pass — rejected because the trip planner would recommend campgrounds with thin detail data. |
| Single-hue heat map color scale | Red-to-green fails for ~8% of users with color vision deficiency. A single-hue scale (e.g., light to dark blue) with text density labels is both accessible and visually clear. | Red-to-green — rejected on accessibility grounds. Multi-color categorical scale — rejected as unnecessarily complex for a density visualization. |
| axe-core in CI from v0.2.1 | Catching accessibility regressions at merge time costs near zero. Catching them in a late audit means rework. Level A failures in the current build confirm this risk is real. | Annual accessibility audit — rejected because it batches preventable regressions. |
| Oregon State Parks in v0.7 | Provider work is independent and high-effort (Playwright). Sequencing it mid-roadmap gives time to learn from GoingToCamp integration patterns. | Earlier — rejected because Playwright adds Docker complexity. Later — rejected because it's P1. |
| Predictions in v0.9 | Requires 6+ months of polling data. Starting data collection at v0.5 means 4+ months of history by v0.9. | v0.7 — rejected because insufficient data. v1.0 — acceptable fallback if data is thin. |
| SQLite over PostgreSQL | Single-instance Fly.io deployment. SQLite is simpler, faster for read-heavy workloads, and sufficient at personal-project scale. | PostgreSQL — overkill for current scale. Turso/libsql — good option if multi-instance needed later. |
| v0.2.1 hardening milestone | Security review found 3 HIGH issues and 8 Level A a11y failures in shipped code. Fixing these before adding more features prevents compounding the debt and is low-effort relative to impact. | Fold fixes into v0.3 — rejected because security issues (especially the cookie flag and CORS config) should not stay open while new users onboard. |
