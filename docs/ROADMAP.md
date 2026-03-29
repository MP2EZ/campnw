# campnw Roadmap: v0.2.1 to v1.1

**Last updated:** March 2026
**Current version:** v1.0 (deployed at campable.co)

---

## Timeline Summary

```
v0.1    [SHIPPED]  Foundation          — Multi-provider search, CLI watches, dashboard
v0.2    [SHIPPED]  Watches on the Web  — Web-based watch management, dark mode
v0.2.1  [SHIPPED]  Hardening           — Security fixes, Level A a11y failures, perf wins
v0.3    [SHIPPED]  Calendar & Polish   — Calendar heat map, SSE streaming, shareable links
v0.4    [SHIPPED]  Accounts            — User accounts, saved preferences, persistent watches
v0.45   [SHIPPED]  Testing             — 346 tests, CI gating, 82% coverage
v0.5    [SHIPPED]  Background Engine   — Server-side polling, web push, registry auto-enrichment
v0.6    [SHIPPED]  Smart Search        — Zero-result recovery, date shifting, search diagnostics
v0.7    [SHIPPED]  Oregon + Delight    — Vibe descriptions, contextual notifications (OR provider deferred)
v0.8a   [SHIPPED]  Trip Planner MVP    — Conversational AI planner with tool calling
v0.8b   [SHIPPED]  Trip Planner Polish — Streaming, itinerary cards, shareable links
v0.95   [SHIPPED]  Monetization        — Free/Pro tiers, subscription billing, upgrade flows
v0.96   [SHIPPED]  Registry + Infra    — Registry expansion, bundle audit, Lighthouse CI
v0.97   [SHIPPED]  Map + Power User    — Map view, keyboard shortcuts, lazy loading
v0.98   [SHIPPED]  Quality Hardening   — WCAG AA contrast, focus styles, ErrorBoundary, CI a11y
v0.99   [SHIPPED]  Pre-launch Audit    — Security headers, CSP, login rate limit, lazy loading, CVE CI
v1.0    [SHIPPED]  campnw 1.0          — OR State Parks, recs, collapsible form, hamburger, polish
v1.1    ------->   Better Search       — NL search, registry expansion (MT/WY/NorCal), AI summaries
v1.2    ------->   Trips + Watches     — Trip object, template watches, sharing, onboarding
v1.3    ------->   Predictions+        — Statistical model, anomaly alerts, post-mortems (~Q1 2027)
```

Each milestone is a shippable increment with clear user value. Predictions+ deferred to v1.1 — data collection running since v0.5, quality improves with time.

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
| Registry auto-enrichment (LLM) | AI-1 | S | Batch LLM pass over RIDB/GoingToCamp description fields to extract structured tags, access notes, and campground attributes. Haiku extracts signals like "walk-in only," "bear box required," "pet-friendly" from prose into structured JSON. Validated with Pydantic before writing to registry. ~$0.10 for full registry run. Runs on campgrounds where `enriched_at IS NULL`. |

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
Fly.io always-on cost and polling volume. Background polling requires `min_machines_running = 1`. With 740+ campgrounds, batching watches aggressively is essential — aim for one availability check per campground per cycle regardless of how many watches target it. Cap free-tier watches at 3 per user. The availability cache at this milestone significantly reduces call volume.

---

## v0.6 "Smart Search"

### Theme
Zero-result and low-result states are the biggest drop-off point in any search tool. This milestone makes the search loop feel intelligent rather than broken — when a search fails, campnw explains why and suggests specific alternatives. This replaces the previously planned "AI Search" milestone (NL-to-form translation), which was assessed as low-impact relative to the integration cost. NL search is deferred to the backlog. The Anthropic SDK integration moves to v0.8 where it's load-bearing (trip planner with tool calling).

### Features

| Feature | PRD Ref | Effort | Description |
|---------|---------|--------|-------------|
| Smart date shifting | P0-1 | M | On zero/low results, analyze nearby date windows that satisfy the same constraint set (tags, radius, nights, day-of-week). Show a single inline suggestion: "Nothing for June 13-16. 3 campgrounds match June 20-22 — same tags, same radius." One tap replaces dates and re-runs the search. |
| "Why nothing?" diagnostic | P0-1 | M | Zero-result state shows a specific diagnosis instead of generic "adjust filters." Example: "Rainier campgrounds are fully booked all June weekends. Last cancellation appeared Wednesday at 11am." Three quick-action chips below: "Expand to July", "Try weekdays", "Set a watch." Each chip is a direct one-tap action. |
| Lightweight alternative suggestions | P0-1 | S | When a specific campground is fully booked, suggest 1-2 alternatives with similar attributes from the registry: "Colonial Creek is full. Newhalem Creek (4 mi away, also lakeside, old-growth) has 3 sites open." Uses tag similarity and geographic proximity — no behavioral data needed. |
| Search history | P1-1 | M | Last 20 searches saved per account. Quick re-run from history list. |

### Smart Date Shifting Design
The date shifting must respect the user's full constraint set, not just slide dates ±7 days blindly:
- Preserve tag filters, drive radius, night count, and day-of-week preferences
- Only suggest windows where results actually exist (run the secondary search server-side)
- Show the suggestion inline below the results header — not a modal, not a banner
- One tap updates the URL and re-renders results; the interaction is seamless

### "Why Nothing?" Diagnostic Design
The diagnostic combines availability state analysis with actionable next steps:
- Analyze which constraint is most restrictive (dates? tags? region?) and say so specifically
- If polling history exists, include timing context ("cancellations for this campground tend to appear mid-week mornings")
- Action chips are pre-configured: each one modifies a specific search parameter and re-runs immediately
- The watch chip pre-fills a watch for the current campground + date range with no additional form

### Technical Work
- Backend: secondary search with relaxed date windows for date-shifting suggestions
- Backend: constraint analysis endpoint that identifies the binding constraint on a zero-result search
- Frontend: inline suggestion component for zero/low-result states
- Frontend: action chip component with one-tap search modification
- Registry: tag similarity scoring for alternative suggestions (cosine similarity on tag vectors, or simpler overlap scoring)

### Quality Baseline
- Zero-result state designed (not just coded) before shipping — wireframes for all three features reviewed together
- Action chips must be keyboard-accessible (tab-focusable, enter/space to activate)
- Date-shifting suggestions must be accurate — never suggest a window that returns zero results
- `aria-live="polite"` region for suggestion announcements to screen readers

### Dependencies
- v0.4 (accounts for search history)
- v0.5 (polling history improves diagnostic quality, but diagnostics work without it using current availability data)

### Key Risk
Date-shifting requires running a secondary search server-side, which adds latency to the zero-result path. Keep the secondary search fast by limiting it to a small date window (±14 days) and capping the campground set. If it exceeds 2 seconds, show the diagnostic immediately and load the date suggestion asynchronously.

---

## v0.7 "Oregon + Delight"

### Theme
Oregon State Parks integration completes the PNW picture. This is the last major provider integration and meaningfully expands the campground registry. Pairs provider work with registry enrichment and two AI-driven delight features — contextual watch notifications and site character descriptions — that make existing surfaces feel alive. The delight features are low-effort additions that leverage the Haiku integration established in v0.5's registry enrichment.

### Features

| Feature | PRD Ref | Effort | Description |
|---------|---------|--------|-------------|
| Oregon State Parks provider | P1-6 | XL | ReserveAmerica platform via Playwright headless browser. New provider module: `providers/reserveamerica.py`. |
| Oregon campground registry seed | P1-6 | M | Seed 200+ Oregon State Parks campgrounds. Auto-generate tags. Compute drive times from Portland and other bases. |
| OR State Parks source filter | P1-6 | S | `--source or-state` in CLI, `source=or_state` in API. Source badge in dashboard. |
| Registry enrichment pass | P0-2 | M | Improve auto-generated tags for all 900+ campgrounds. Fill gaps in drive time data. Manual curation for top 50 most-searched. Amenity data (site count, fire rings, bear boxes) added now — serves both this milestone and the trip planner in v0.8. |
| Booking link validation | P0-4 | S | Verify booking links resolve before surfacing. Flag stale links from provider changes. |
| Contextual watch notifications | AI-1 | S | When a watch fires, enrich the raw diff with LLM-generated context. Instead of "Site 004: Available," send "Ohanapecosh Site 004 just opened July 3-6 — that's a rare 4th of July weekend slot. This campground typically re-books within hours." Single Haiku call between diff detection and notification dispatch. Includes urgency scoring (1-3) based on date popularity and historical re-booking speed. |
| Site character / "vibe" descriptions | AI-1 | S | Pre-generated one-sentence campground personality rendered on expanded result cards. Examples: "Quiet forested loop — sites spread far apart, creek sounds" or "Popular trailhead camp — fills fast, noisy mornings as day hikers arrive." Generated at enrichment time from registry tags, RIDB descriptions, site counts, and proximity to trailheads. Stored as a registry field, zero query-time cost. |
| Registry gap detector (internal) | AI-1 | S | Internal script that clusters search misses by region — when users search for campgrounds in an area and get zero or sparse results, flag it as a registry gap. Generates specific seed recommendations with RIDB facility IDs. Run periodically, output to `data/registry_gaps.json`. Not user-facing. |

### Contextual Notification Design
The notification enrichment is a thin async call added to the existing `monitor/` pipeline:
- Input: campground name, available dates, current date, historical re-booking speed (if available from `availability_history`)
- Output: 1-2 sentence notification message + urgency score (1-3)
- Urgency 1 (low): Tuesday in January — suppress if user has set quiet mode
- Urgency 2 (medium): standard availability — always deliver
- Urgency 3 (high): rare opening on high-demand dates — deliver immediately with emphasis
- Fallback: if LLM call fails, send the raw diff notification (never block delivery on enrichment)

### Technical Work
- Playwright integration for ReserveAmerica (headless Chrome in Docker)
- New `BookingSystem.OR_STATE` enum value
- `providers/reserveamerica.py` with session management and availability parsing
- Dockerfile update: add Playwright + Chromium (significant image size — use multi-stage build)
- `scripts/seed_or_state.py` for registry seeding
- Rate limiting and retry logic for ReserveAmerica
- Notification enrichment: Haiku call in `monitor/` pipeline between diff and dispatch
- Registry `vibe` field: generated by batch enrichment script, rendered in result card component
- Gap detector: `scripts/detect_registry_gaps.py` querying search logs + RIDB cross-reference

### Quality Baseline
- OR State Parks results labeled "temporarily unavailable" when Playwright is blocked — graceful degradation from day one
- Registry enrichment quality gate: top 50 campgrounds manually reviewed before v0.8 trip planner ships
- No new axe-core failures from OR State Parks UI additions
- Notification enrichment must never block or delay notification delivery — LLM call is fire-and-forget with timeout
- Site vibe descriptions reviewed for accuracy on top 20 campgrounds before enabling for all

### Dependencies
- v0.5 (Haiku integration from registry enrichment, polling history for notification context)

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
- v0.5 (Anthropic SDK integrated via registry enrichment)
- v0.4 (accounts for rate limiting and itinerary saving)
- v0.7 (registry enrichment — trip planner needs good detail data to recommend well)

### Key Risk
Session cost at scale and conversation quality. A single session with 4 tool calls costs $0.03–0.10. Rate limiting is non-negotiable. Prompt engineering for the itinerary task is also genuinely hard — test with real trip scenarios before shipping.

---

## ~~v0.9~~ → v1.1 "Predictions+" (moved post-v1.0 — see v1.1 section below)

### Theme
The full intelligence layer — built on 9-12 months of polling data collected silently since v0.5 (originally scoped for 6 months, deferred to allow more data accumulation). Three capabilities, one statistical infrastructure: predictive availability ("when will it open?"), anomaly-based deal alerts ("this almost never happens"), and watch post-mortems ("why did I miss it?"). Data collection starts at v0.5; this milestone is where that investment pays off. All three features use the same `availability_history` table and the same cancellation pattern detection model.

### Features

| Feature | PRD Ref | Effort | Description |
|---------|---------|--------|-------------|
| Availability prediction display | P1-3 | L | For booked-out campgrounds: "Sites typically free up X–Y days before the date" with confidence band. Cold start fallback: "we're still learning." |
| Statistical prediction model | AI-2 | L | Time-series analysis: median days-before-date that cancellations appear, standard deviation, confidence interval. Per-campground. Pure statistical — not an LLM. Also infers booking window open dates from NYR→Available→Reserved transitions in polling data. |
| Smart notification scoring | P2-2 | M | When a watch fires, attach urgency context: "Usually books within 30 minutes" vs "Typically stays open for hours." Rule-based initially. |
| Prediction confidence display | P1-3 | S | Visual confidence indicator (low/medium/high) based on sample size. Transparent about data limitations. |
| Anomaly-based deal alerts | AI-2 | M | Detect statistically unusual availability against a per-campground seasonal baseline. When a campground that is historically always booked suddenly shows availability, proactively alert: "Unusual: 3 sites just opened at Sol Duc Hot Springs for July 4th weekend — this campground has been fully booked for that window every year we've tracked." System-initiated, not user-initiated — these are insights, not watch responses. |
| "Why did I miss it?" post-mortem | AI-2 | S | When a watched site opens and re-books before the user acts, show a brief analysis: "This site was available for 4 minutes at 11:23am Wednesday. Cancellations at this campground for July weekends average 7-minute windows. To catch this: enable 5-minute polling or add a mobile push channel." Turns a frustrating miss into actionable system tuning. |

### Anomaly Detection Design
- Build a per-campground seasonal baseline from `availability_history`: what does "normal" look like for this campground in this calendar window?
- Flag when current availability deviates by >2σ from the baseline for that period
- Context matters: an anomaly at a popular campground on a holiday weekend is noteworthy; the same pattern at an obscure forest road campground is not. Weight by campground popularity (search frequency, watch count).
- Deliver anomaly alerts through the existing notification channels (web push, ntfy, email). Users opt into anomaly alerts separately from watches.

### Post-Mortem Design
- Track availability window duration: time between "site opened" and "site re-booked" in `availability_history`
- On a missed window, compare the user's poll interval and notification latency against the window duration
- Generate a specific, natural-language recommendation (single Haiku call) that combines the timing data with actionable tuning steps
- Show in the watch detail view, not as a push notification — this is reflective, not urgent

### Technical Work
- Statistical analysis module: `predictions/model.py` with cancellation pattern detection
- Seasonal baseline model: per-campground expected availability by calendar week
- Anomaly detection: z-score against seasonal baseline, weighted by popularity
- Pre-computation job: nightly predictions and baselines cached per campground
- Notification scoring: analyze diff history for time-to-rebook patterns
- Window duration tracking: timestamp pairs in `availability_history` for open→rebook transitions
- Post-mortem generation: Haiku call with window duration + user config context
- API response extension: predictions field on campground results when available
- Anomaly alert subscription: user preference for receiving proactive alerts

### Quality Baseline
- Prediction confidence is always displayed — never show a prediction without showing its certainty level
- "We're still learning" cold start state is a designed state, not an empty one
- Prediction display passes contrast on both light and dark themes
- Anomaly alerts must have a minimum confidence threshold — never alert on thin data (require ≥4 weeks of baseline)
- Post-mortem tone must be constructive, not critical — "here's how to catch it next time," never "you missed it because..."

### Dependencies
- v0.5 (background polling running for 6+ months — data collection started there)
- v0.7 (contextual notifications infrastructure reused for anomaly alerts)

### Key Risk
Data quality and sample size. Campgrounds polled infrequently will have unreliable predictions and noisy anomaly detection. Transparency is the mitigation — show confidence levels, never overstate certainty. Anomaly alert volume is the second risk: if too many alerts fire, users will ignore them. Start with a high threshold (>3σ, popular campgrounds only) and relax based on user engagement.

---

## v0.95 "Monetization"

### Theme
campnw has real users, real infrastructure costs, and a feature set that justifies a paid tier. This milestone introduces a Free/Pro split, subscription billing, and upgrade surfaces that make the paid tier discoverable without being coercive. The goal is sustainability, not growth. Break-even requires 2-4 Pro subscribers at $5/month. Everything here is scoped to that reality.

### Free vs Pro Tier

| Feature | Free | Pro ($5/mo) |
|---------|------|-------------|
| Search (all providers, all filters) | Unlimited | Unlimited |
| Calendar heat map, vibes, smart search | Yes | Yes |
| Booking links, shareable search links | Yes | Yes |
| Watches (simultaneous active) | 3 | Unlimited |
| Watch polling interval | 15 min | 5 min |
| Contextual AI notifications | Yes | Yes |
| Trip planner sessions | 3/month | 20/month |
| Availability predictions | Preview | Full (confidence bands, per-date) |
| Anomaly-based deal alerts | No | Yes |
| Data export + account deletion | Yes | Yes |

**Core principle:** Search and basic monitoring are always free. Watches are the natural gate — they drive server cost (polling, notifications, AI enrichment). The free tier must be genuinely useful.

### Features

| Feature | Effort | Description |
|---------|--------|-------------|
| Payment provider integration | M | Hosted checkout + customer portal + webhook handler. No custom payment forms (SAQ A). Stripe or Lemon Squeezy (MoR — handles sales tax). |
| Subscription schema + entitlements | S | `subscription_status` on users table, `subscription_events` audit table, webhook event dedup. Status written only by webhook handler. |
| Watch limit enforcement | S | Server-side check on `POST /api/watches`. HTTP 402 with upgrade URL. 5-min polling for Pro via per-watch scheduler config. |
| Trip planner gating | S | 3 sessions/month free, 20 Pro. Soft gate on 4th session (prompt, not block). |
| Pricing page (`/pricing`) | M | Two-column Free vs Pro. Minimal — not a marketing page. "Built by one person. Pro keeps the servers running." |
| Upgrade modal component | M | Reused across all trigger surfaces: watch limit, trip planner, anomaly alerts, settings. |
| Billing settings section | S | Current plan, usage summary, manage/upgrade CTA. Cancel flow via hosted customer portal. |
| Pro indicator | S | Subtle accent dot next to Account in header. No badge, no ribbon. |
| Downgrade + grandfather logic | M | Watches paused (never deleted) on downgrade. 30-day grandfather for existing users with >3 watches. |
| Webhook security + audit trail | S | Signature verification (HMAC-SHA256, raw bytes). Idempotency via event ID. `subscription_events` table with 12-month retention. |

### Upgrade Trigger Points

Four surfaces, no more:
1. **Watch creation** (4th watch) — hard gate, inline upgrade prompt showing existing watches
2. **Trip planner** (4th session/month) — soft gate, counter visible, prompt on attempt
3. **Anomaly alerts** (v0.9 Pro-only) — soft prompt with upgrade CTA
4. **Settings > Plan** — always visible, user-initiated

**Never a trigger:** page load, search results, notification delivery, account creation, data export.

### UX Design Decisions
- Hosted checkout redirect (not embedded) — simplest, no PCI surface
- Post-upgrade: return to product with brief success banner (4s auto-dismiss), not a celebration page
- Paywall moments use warning-banner styling (amber, not red) — helpful, not punishing
- Cancel confirmation: two-step inline confirm, "watches paused not deleted" language
- Pro dot uses existing `--accent` color, spring entrance animation (400ms)
- No new CSS tokens needed — reuses `--chip-bg`, `--warning-bg`, `--bg-card`

### Security Requirements (P0)
- Webhook signature verification with raw bytes — no exceptions
- Persistent `JWT_SECRET` in Fly secrets (not auto-generated on restart)
- Subscription status never in JWT — database is source of truth
- Server-side entitlement check on every gated endpoint
- Never log/store card data (hosted checkout eliminates PCI scope)
- Rate limit login endpoint before launching billing
- `past_due` retains Pro access during Stripe retry window (grace period)

### Communication Strategy
- 30-day grandfather period for existing users with >3 watches
- One honest email: "I'm adding Pro at $5/mo. Free tier stays fully featured for search and 3 watches."
- In-product banner during grandfather period showing watch count vs limit
- No countdown urgency, no repeated emails, no dark patterns

### Technical Work
- Payment provider account setup + product/price creation
- `billing.py` module: tier logic, API client (~100 lines)
- DB migration: subscription columns on users, `subscription_events` table, webhook dedup
- API endpoints: `POST /api/billing/checkout`, `POST /api/billing/portal`, `GET /api/billing/subscription`, `POST /api/billing/webhook`, `GET /api/entitlements`
- Frontend: pricing page, upgrade modal, billing settings, entitlements context, pro indicator
- Webhook handler: `checkout.session.completed`, `subscription.updated`, `subscription.deleted`, `invoice.payment_failed`
- Watch enforcement: limit check in `POST /api/watches`, poll interval tiering in APScheduler
- Tests: webhook handler, tier logic, gate enforcement, downgrade flow

### Quality Baseline
- Webhook endpoint validates signature on every request — never skip
- All billing state transitions covered by tests
- Upgrade modal keyboard-accessible (tab, enter/space, escape)
- Cancel flow accessible and honest — no dark patterns
- `subscription_events` audit table for dispute resolution

### Dependencies
- v0.8 Trip Planner (gated by Pro) — must be shipped
- v0.9 Predictions+ (anomaly alerts are Pro-only) — ideally shipped; billing can launch before v0.9 if needed
- v0.4 Accounts (billing is per-user) — shipped

### Key Risk
**R1: Nobody upgrades.** The free tier may be "good enough." Mitigation: start at $5/mo, monitor for 3 months. If MRR stays $0, revisit gate placement (lower free watch limit to 2, harder trip planner gate) or accept campnw as a free tool.

**R2: Stripe/billing complexity delays launch.** Mitigation: use hosted checkout + customer portal aggressively. Zero custom billing UI. Entire payment surface hosted by the provider.

**R3: Grandfather period churn.** Users with >3 watches who don't upgrade may disengage. Mitigation: transparent communication, 30-day window, watches paused not deleted.

---

## v0.96 "Registry + Infra" — DONE

### Theme
Expand the campground registry to 1,000+ and establish performance infrastructure. Unglamorous prerequisite work that prevents rework: the map view needs complete lat/lng data, and Leaflet needs lazy-loading infrastructure already in place.

### Features

| Feature | Effort | Description |
|---------|--------|-------------|
| Registry expansion (RIDB re-seed) | M | Re-seed RIDB for complete ID + OR federal campground coverage. Target: 1,000+ campgrounds with lat/lng, tags, drive times. Update `scripts/seed_registry.py`. Validate every entry has coordinates (required for v0.97 map). |
| Lighthouse CI in PR pipeline | S | Add Lighthouse CI check to GitHub Actions. Establish baseline scores. Block PRs that regress performance budget by >5%. |
| Bundle audit + code splitting prep | M | Run vite-bundle-visualizer. Identify split points for route-level lazy loading (`React.lazy` + `Suspense`). Implement lazy loading for `/plan` route as proof of pattern. |
| P95 search latency baseline | S | Add server-side timing to search endpoint. Log P95. Establish 4-second target as a measured metric. |

### Dependencies
- v0.95 shipped

### Quality Bar
- Every campground in the registry has valid lat/lng (null coordinates = not imported)
- Lighthouse CI passing in PR pipeline
- Trip planner route lazy-loaded, verified bundle size reduction
- No new axe-core failures

### Key Risk
RIDB data quality for ID and OR federal campgrounds. Some facilities may lack coordinates or return 404 on availability endpoints. Budget time for data cleaning, not just import.

---

## v0.97 "Map + Power User" — DONE

### Theme
The map view is the most visually transformative change since the calendar heat map. Ship alongside keyboard shortcuts (which need to account for map interactions) and the lazy-loading pattern established in v0.96.

### Features

| Feature | Effort | Description |
|---------|--------|-------------|
| Map view | L | ✅ Leaflet map on `/map` route with source-colored circleMarker pins, markerClusterGroup clustering, popups with name/source/sites/drive/link, dark mode tile inversion. |
| Map lazy loading | S | ✅ Leaflet loaded via `React.lazy` + manualChunks. Isolated 183KB chunk. Main bundle 270KB (under 350KB gate). |
| Keyboard shortcuts | M | ✅ `j/k` result nav, `w` watchlist, `m` map/list toggle, `?` help overlay. useKeyboardShortcuts hook with input/modifier skip. ShortcutHelpModal with focus trap. |
| Map accessibility | S | ✅ List alternative `<details>` table, `role="application"` + `aria-label`, `aria-live` view toggle announcements, `.sr-only` utility, `.card-focused` ring. |
| Search-map integration | S | ✅ SearchContext for cross-route state. Summary bar on map with search params + "Edit search" link. "See on map" in expanded cards with `zoomToShowLayer` + popup open. |

### Dependencies
- v0.96 (registry with complete lat/lng, lazy-loading infrastructure, Lighthouse CI baseline)

### Quality Bar
- Map route lazy-loaded; initial bundle size does not increase
- Lighthouse performance score does not regress from v0.96 baseline
- All keyboard shortcuts documented in `?` overlay
- Map has a non-map alternative (list view remains default)
- axe-core passes on map view

### Key Risk
Map UI scope creep. Hard boundary: pins with density coloring, clustering, click-to-preview. Nothing else in this release.

---

## v0.98 "Quality Hardening" — DONE

### Theme
Tactical UI and accessibility fixes that close the gap from WCAG Level A to Level AA. Error resilience, design token hygiene, and CI gating improvements. An intermediate ship point between v0.97 (map + shortcuts) and v1.0 (personalized recs).

### Features

| Feature | Effort | Description |
|---------|--------|-------------|
| WCAG AA contrast fixes | S | Fix `--text-light` (both modes) and `--accent` (dark mode) to pass 4.5:1 minimum contrast ratio. |
| Skip navigation link | S | Add skip-to-content link (WCAG 2.4.1), visible on keyboard focus, targets `<main>` landmark. |
| Focus-visible enhancement | S | Add transition to global `:focus-visible` for smooth outline appearance. |
| Missing hover transitions | S | Add `transition` to 6 interactive elements that snapped on hover (result-header, show-more-btn, watch-action-btn, user-menu-item, recent-chip, chat-new-btn). |
| Hardcoded color cleanup | S | Replace 15 `color: #fff` with `--text-on-accent` token. Tokenize hardcoded hover backgrounds and chip borders. |
| React ErrorBoundary | S | Wrap Routes with ErrorBoundary to prevent white-screen crashes. Styled recovery UI with reload button. |
| Loading indicator consistency | S | Replace WatchPanel text "Loading..." with animated thinking-dots pattern matching search/chat. |
| jest-axe a11y tests | S | axe-core tests for /, /map, /plan routes. Catches violations in CI before merge. |
| Lighthouse CI expansion | S | Add /map to Lighthouse URL list. Bump accessibility threshold from 0.9 to 0.95. |

### Dependencies
- v0.97 (map view, keyboard shortcuts)

### Quality Bar
- All `--text-light` and `--accent` usages pass WCAG AA 4.5:1 contrast
- Skip link visible on Tab, navigates to main content
- All interactive elements have smooth hover/focus transitions
- Zero hardcoded `color: #fff` in App.css (all via `--text-on-accent` token)
- ErrorBoundary catches render errors with styled recovery UI
- jest-axe passes on all routes
- Lighthouse a11y ≥ 0.95 on /, /plan, /map

### Key Risk
None — all items are small, well-scoped, and independently verifiable.

---

## v0.99 "Pre-launch Audit"

### Theme
The comprehensive quality gate before v1.0. v0.98 handles tactical UI/a11y fixes (contrast, focus styles, token cleanup, ErrorBoundary, CI gating). This release is the broad sweep: performance profiling, security hardening, cross-browser QA, and accessibility testing that goes beyond what automated tools catch.

### Features

| Feature | Effort | Description |
|---------|--------|-------------|
| Performance audit | M | Bundle size regression check against v0.96 baseline. P95 search latency validation (<4s). Lighthouse perf scores across all routes. React profiler for unnecessary re-renders. Verify lazy-load coverage (trip planner, map, pricing). |
| Security audit | M | Auth flow review (JWT lifecycle, cookie flags, session expiry). Input validation sweep across all API endpoints. OWASP top 10 checklist. `npm audit` + `pip-audit` for dependency CVEs. Stripe webhook signature verification confirmation. |
| Cross-browser/device QA | M | Manual testing on Safari, Firefox, Chrome. iOS Safari and Android Chrome for PWA flows. PWA install + web push notification flow on mobile. Dark mode rendering across browsers. |
| Accessibility completeness | S | Screen reader testing (VoiceOver) on all routes including trip planner and map. Keyboard navigation end-to-end (every interactive element reachable). ARIA pattern review beyond what axe-core catches (live regions, role usage, announcement timing). |
| Mobile responsive audit | S | All routes tested at 320px–768px breakpoints. Touch target sizing (48px minimum). Viewport-specific layout bugs. Trip planner and map usability on small screens. |

### Dependencies
- v0.98 (contrast fixes, focus styles, ErrorBoundary, CI a11y gating at 0.95)

### Quality Bar
- Zero `npm audit` / `pip-audit` critical or high vulnerabilities
- P95 search latency under 4 seconds (measured via Server-Timing)
- Lighthouse scores: performance ≥0.9, accessibility ≥0.95, best practices ≥0.9 on all routes
- All routes usable via keyboard-only and screen reader
- No layout breakage at 320px viewport width

### Key Risk
Audit scope creep — this is a review milestone, not a rewrite. Fix issues found, but don't redesign. If a fix exceeds M effort, file it for v1.0 or v1.1.

---

## v1.0 "campnw 1.0"

### Theme
The capstone. Oregon State Parks via ReserveAmerica completes tri-state coverage. Personalized recommendations, collapsible search form, mobile hamburger menu, and UX polish across the board.

### Features — ALL SHIPPED

| Feature | Status | Description |
|---------|--------|-------------|
| Oregon State Parks provider | DONE | ReserveAmerica provider (53 parks), `curl_cffi` WAF bypass, seed script, dynamic source filter buttons, SSE abort-and-restart support. |
| Personalized recommendations | DONE | Search history affinity (tags, regions, date patterns). Opt-in toggle. Renders as recommendation row above search results. |
| Collapsible search form + scroll-to-results | DONE | Auto-scroll to results, form collapses to compact summary bar with Edit button. |
| Mobile hamburger menu | DONE | Watchlist, theme toggle, Sign in behind menu icon on mobile (≤640px). |
| Card expand/collapse animation | DONE | CSS grid-template-rows transition with opacity fade. |
| Jargon cleanup | DONE | "openings" terminology. FCFS expanded via `title` tooltip. Dynamic source filter counts. |
| Loading skeleton | DONE | `ResultsSkeleton` shimmer placeholder during SSE streaming. |
| First-visit empty state | DONE | `FirstVisitState` component with suggested searches for new users. |
| Dark mode warning banner | DONE | Dedicated `--warning-border` dark mode token. |
| A11y completions | DONE | Meta description tag. Sign-in modal close `aria-label`. Heat map legend with "0 sites" / "N+ sites" numeric labels. |
| Mobile result polish | DONE | Heat map larger cells at ≤640px. Date row flex-wrap at narrow widths. |

### Remaining Minor Polish (deferred to v1.0.1 or v1.1)

| Item | Effort | Description |
|------|--------|-------------|
| Dark mode heat map levels 0-1 | XS | `--heatmap-0` (#1e1e1a) and `--heatmap-1` (#2e4a1e) too similar in dark mode. Widen low-end color scale. |
| FCFS inline expansion | XS | Currently tooltip-only. Could expand "First-come, first-served" inline on first occurrence per session. |

---

## v1.1 "Better Search + Coverage" (~3-4 weeks)

### Theme
Find campsites faster, across more of the northwest, with better data. Natural language search is the headline feature. Registry expansion and quality improvements make every search better. AI summarization and recommendation reasons add intelligence to results. Polling data continues accumulating toward v1.3 predictions.

### Features

| Feature | Size | Description |
|---------|------|-------------|
| Natural Language Search | M | Freeform text input parsed by Haiku into structured search params via tool_use. Shows parsed interpretation with "Edit filters" link. Date inference, tag mapping, 1.5s latency budget. |
| Registry Expansion (MT, WY, NorCal) | S | Add campgrounds via existing RIDB seed pipeline. NorCal filtered to ≥38.5°N. Drive times calculated, enrichment run on new entries. |
| Tag Taxonomy Audit | XS | Single Sonnet call to analyze 29-tag vocabulary — merges, gaps, removals. Manual review, re-run enrichment for affected entries. |
| Registry Description Rewrite | S | Haiku generates elevator_pitch, description_rewrite, best_for per campground. New registry columns with graceful fallback to RIDB originals. |
| Post-Search Result Summarizer | S | Trailing SSE event after results stream. Haiku summarizes patterns across 5+ results. 3s timeout, silent failure. |
| Personalized Rec Reasons | S | LLM-generated contextual reasons replace template strings. 24h cache. Min 3 searches before enabling. Graceful fallback. |
| Search Analytics Digest | S | Weekly APScheduler job aggregates search_history, Haiku produces product intelligence report. Stored in analytics_digests table, optional ntfy push. |
| Dark Mode Heatmap Fix | XS | Widen dark mode heatmap color scale so levels 0-1 are distinguishable. CSS-only, 2:1 min contrast between adjacent levels. |

### Sequencing
Batch/infra first: Tag Audit (3) → Description Rewrite (4) → Registry Expansion (2). Then headline: NL Search (1). Then AI features (5, 6, 7) in any order. Heatmap fix (8) whenever.

### Quality Bar
- NL search: test suite of 20-30 natural language queries with expected structured output
- Registry descriptions: spot-check 20-30 before bulk write; reject hallucinated amenities
- Summarizer: P95 under 2s; never blocks result display
- All new features pass Lighthouse a11y ≥0.95

### Key Risks
- NL date inference edge cases ("July 4th weekend" must resolve to future, not past)
- Description hallucination (Haiku may infer amenities not in source data — prompt constrains to stated facts)
- NorCal latitude cutoff — verify RIDB returns coords for CA facilities

### Cost
- One-time: ~$0.20 (tag audit + description rewrite)
- Ongoing: ~$7-8/month (NL search ~$3, summarizer ~$3, rec reasons ~$1, digest ~$0.05)

---

## v1.2 "Trips + Watches" (~5-7 weeks)

### Theme
Plan and track trips. The Trip object is the hub that search, watches, and the planner all connect to. Template watches make Pro worth paying for. Watch sharing drives organic growth. Historical patterns validate polling data quality while producing user-visible "Booking Tips." Identity improvements make accounts stickier.

### Features

| Feature | Size | Description |
|---------|------|-------------|
| Trip Object | L | First-class entity: trips table + trip_campgrounds junction. CRUD API, "Save to trip" on result cards, aggregated availability view, trip-linked watches. 10 trips free, 25 Pro. |
| Template Watches | L | Watch a search pattern, not a single campground. Expands to matching registry entries at poll time. 20-campground/cycle cap. "Watch this search" button on results page. |
| Watch Sharing | S | UUID-based shareable link. Read-only view of watch/trip availability. 30-day expiry, no auth required to view, 10 req/hr rate limit per UUID. |
| Trip Planner → Persistent Itinerary | M | "Save as Trip" button in chat when AI has recommended campgrounds. Extracts from tool_use calls. User can prune after saving. |
| Onboarding + Profile | S | Post-signup 2-step modal: set home base + select preferred tags. Feeds into search defaults and recommendation scoring. Profile page with editable preferences. |
| Campground Comparison | S | Select 2-3 campgrounds, get inline comparison panel: data table + Haiku narrative. Falls back to data-only if Haiku unavailable. |
| Historical Pattern Extraction | M | Aggregate availability_history into per-campground booking tips via Haiku. 30-day observation minimum. Monthly batch refresh. "Booking Tips" in expanded cards with data freshness indicator. |
| Notification Quality Feedback Loop | S | Monthly batch correlating notifications with booking clicks. 50-notification minimum. Outputs prompt suggestions for manual review. |

### Sequencing
Trip Object (1) is critical path — blocks Watch Sharing (3) and Planner-to-Itinerary (4). Template Watches (2) can parallel with 4. Onboarding (5) and Comparison (6) are independent. Historical Patterns (7) depends on data maturity — start pipeline early. Notification Feedback (8) last.

### Quality Bar
- Trip CRUD: full API test coverage, cross-source campground support (recgov + wa-state + or-state in same trip)
- Template watches: validated against Pro 5-min polling budget (20 campgrounds × 12 polls/hr = 240 calls/hr max)
- Shared links: no PII exposed, rate limited, graceful expiry
- Historical patterns: "Still learning..." for campgrounds with <30 days data
- Onboarding: skippable, no degradation if skipped

### Key Risks
- Template watch rate limiting: 20-campground cap needs validation against API budgets
- Trip-campground composite key: (facility_id + source) to handle cross-source trips correctly
- Historical pattern sparsity: only watched/searched campgrounds have data; unwatched ones show nothing

### Cost
- One-time: ~$1.00 (historical pattern extraction)
- Ongoing: ~$1-2/month (comparison ~$1, notification loop ~$0.01)

---

## v1.3 "Predictions+" (~Q1 2027, needs 9-12 months of polling data)

### Theme
The intelligence layer. By Q1 2027, there will be 9-12 months of polling data. v1.2's historical pattern extraction has validated data quality. The statistical model, anomaly detection, and post-mortems all ship together because they share the same data pipeline.

### Features

| Feature | Size | Description |
|---------|------|-------------|
| Statistical prediction model | L | Time-series analysis on `availability_history`: median days-before-date cancellations appear, confidence intervals, booking window detection. Per-campground. |
| Availability prediction display | L | "Sites typically free up X-Y days before the date" with confidence band. Cold start: "still learning." Integrates into result cards and check view. |
| Prediction confidence display | S | Visual confidence indicator (low/medium/high) based on sample size. Transparent about data limitations. |
| Smart notification scoring | M | When a watch fires, attach urgency: "Usually books within 30 minutes" vs "Typically stays open for hours." |
| Anomaly-based deal alerts | M | Detect statistically unusual availability against seasonal baseline. Proactive alerts for popular campgrounds with rare openings. Pro-only. Haiku narrates the alert with historical context. |
| "Why did I miss it?" post-mortem | M | Timing analysis + Haiku-narrated actionable tuning suggestions when watched sites open and re-book before user acts. |

### Dependencies
- v1.2 shipped (historical pattern extraction validates data quality)
- 9-12 months of polling data (accumulating since March 2026)

### Quality Bar
- Predictions never shown without confidence level
- Anomaly alerts require minimum 4 weeks of baseline data
- Post-mortem tone is constructive
- All prediction displays pass contrast on both themes

### Key Risk
Data quality and sample size for less-popular campgrounds. v1.2's pattern extraction serves as early validation.

---

## Cross-Cutting Concerns

### Accessibility Baseline (per milestone)

| Milestone | Requirement |
|-----------|-------------|
| v0.2.1 | Fix all 8 Level A failures. Add axe-core to CI blocking Level A. Fix dark mode contrast failures. |
| v0.3 | Heat map uses colorblind-safe single-hue scale + text labels + `role="grid"` from day one. |
| v0.4 | Auth forms pass Level AA contrast. Error states for auth flows designed before coding. |
| v0.5 | Push permission UX follows best practices (no on-load prompts). |
| v0.6 | `aria-live` for date-shifting suggestions and zero-result diagnostics. Action chips keyboard-accessible. |
| v0.8 | `role="log"` on transcript. Focus management on new messages. |
| v0.95 | Upgrade modal keyboard-accessible. Pricing page passes Level AA contrast on both themes. Cancel flow accessible. |
| v0.97 | Map view has list-based alternative. Pin interactions keyboard-reachable. Colorblind-safe density palette. |
| v1.0 | Full WCAG 2.1 AA audit. CI expanded to block Level AA failures. |
| v1.1 | NL search input accessible (label, aria-live for parsed interpretation). Summarizer card keyboard-dismissible. |
| v1.2 | Trip views meet Level AA. Shared link views accessible without auth. Comparison panel keyboard-navigable. |
| v1.3 | Prediction displays pass contrast on both themes. Confidence indicators accessible. |

The principle: fix accessibility at build time, not in a batch audit. Color contrast and semantic HTML are cheapest when designed from the start.

### Security Baseline (per milestone)

| Milestone | Requirement |
|-----------|-------------|
| v0.2.1 | Cookie `Secure` flag, CORS env config, `/api/track` validation + rate limit, `limit` param cap. |
| v0.4 | Watch schema privacy fix, `from_location` log redaction, auth provider decision, session migration plan. |
| v0.5 | Anthropic spend limit configured (registry enrichment introduces SDK). |
| v0.8 | Prompt injection hardening, hallucination guardrail (tool-call-only recommendations), session cost monitoring. |
| v0.95 | Webhook HMAC signature verification (raw bytes). Persistent `JWT_SECRET` in Fly secrets. Subscription status server-side only (never in JWT). Rate limit login endpoint. Never log/store card data. Idempotent webhook processing. |

### Performance Baseline (per milestone)

| Milestone | Target |
|-----------|--------|
| v0.2.1 | Search time reduced by ~3.5s via batch_size/delay fix. Bundle baseline captured with vite-bundle-visualizer. |
| v0.3 | SSE streaming eliminates "nothing then everything" UX. |
| v0.5 | Availability cache (10–15min TTL) prevents redundant API calls across watch polling. |
| v0.96 | Lighthouse CI baseline established. P95 search latency measured. `/plan` route lazy-loaded. |
| v0.97 | Map view lazy-loaded. Initial bundle size does not increase. Lighthouse does not regress. |
| v1.0 | P95 search under 4 seconds. Lighthouse performance, accessibility, best practices all green. |
| v1.1 | NL search parsing under 1.5s P95. Summarizer under 2s P95. No regression on main bundle size. |
| v1.2 | Trip views load under 1s. Template watch polling stays within API rate budgets. |
| v1.3 | Prediction queries add <200ms to page load. |

### Data Collection (start at v0.5, use at v1.3)
The `availability_history` table ships silently in v0.5 alongside background polling. Every poll cycle writes a row. v1.2's Historical Pattern Extraction (C2) validates data quality at ~6 months. By v1.3 (~Q1 2027), there should be 9–12 months of data — strictly better for prediction quality than the original v0.9 target.

### Registry Maintenance
The campground registry is a living dataset. Automated monthly re-seeding from RIDB and quarterly refresh from GoingToCamp should be set up in v0.5. Drift detection (campgrounds that consistently 404) should flag entries for manual review.

### Cost Model
| Component | v0.2–v0.4 | v0.5–v1.0 | v1.1+ (with AI features) |
|-----------|-----------|-----------|--------------------------|
| Fly.io | ~$0/mo (auto-sleep) | ~$5–7/mo (always-on for polling) | ~$7–15/mo |
| Anthropic API | $0 | ~$1/mo (enrichment, notifications) | ~$18–40/mo (trip planner + NL search + summarizer + rec reasons) |
| Payment provider fees | $0 | $0 | ~2.9–5% per txn ($0.45–0.75 per $5 sub) |
| Auth provider | $0 (self-rolled PyJWT) | $0 | $0 |
| Total cost | ~$0/mo | ~$6–8/mo | ~$26–60/mo |
| Pro revenue (target) | $0 | $0 | $75–750/mo (15–150 subscribers) |
| **Net** | ~$0/mo | -$6–8/mo | **+$15–690/mo** |

Break-even requires ~6 Pro subscribers at $5/mo with all v1.1 AI features enabled. Watch cost creep — the ~$8/mo in new AI features (NL search, summarizer, rec reasons) is the largest single cost increase since v0.5.

Rate limiting on AI features is non-negotiable. Spend limits in the Anthropic account are a pre-ship requirement for v0.5 (when the SDK is first introduced).

### Testing Strategy
- Unit tests for providers and search engine (existing, extend as needed)
- Integration tests for API endpoints (add starting v0.2)
- E2E tests for critical flows: search, watch creation, booking link click (add at v0.5)
- AI feature testing: golden-set evaluation for trip planner prompt accuracy (v0.8)
- axe-core in CI from v0.2.1 onward (Level A); expanded to Level AA at v1.0

### Deployment
Current GitHub Actions CI/CD deploys to Fly.io on push to main. Key additions:
- v0.2.1: Pin `flyctl` GitHub Action to SHA (not `@master`)
- v0.5: `min_machines_running = 1` in `fly.toml`
- v0.7: Docker image size increase (Playwright/Chromium) — likely needs multi-stage build or larger machine
- v1.0: Lighthouse CI check in PR pipeline

---

## What's Explicitly Post-v1.3

- **Idaho State Parks** (Brandt/Idaho Time at getoutside.idaho.gov — behind AWS WAF with mandatory visual CAPTCHA, would need paid CAPTCHA-solving service; ~20 state parks, low demand. Probed March 2026.)
- **BC Parks (Canada)** (revisit based on demand signals from B1 analytics digest)
- **Native mobile apps** (web-first is right for this scale)
- **Booking intermediation** (legal complexity, misaligned with the tool's positioning)
- **User reviews and photo uploads** (community features need critical mass)
- **Cell coverage overlay** (crowdsourced data is hard to bootstrap)

---

## AI Feature Backlog (Evaluated)

Features brainstormed and scored during the March 2026 AI feature review. Re-evaluated post-v1.0 and slotted into v1.1-v1.3 where appropriate. See also: `docs/AI-OPPORTUNITIES-2026-03-28.md` for the full analysis and `docs/REQUIREMENTS-v1.1-v1.2.md` for detailed acceptance criteria.

### Scheduled

| Feature | Version | Source |
|---------|---------|--------|
| Natural Language Search | v1.1 | A1 — re-evaluated: highest-impact UX feature, trip planner proves the pattern |
| Post-Search Result Summarizer | v1.1 | A2 |
| Personalized Rec Reasons | v1.1 | A5 |
| Tag Taxonomy Audit | v1.1 | C3 |
| Registry Description Rewrite | v1.1 | C1 |
| Search Analytics Digest | v1.1 | B1 |
| Campground Comparison | v1.2 | A3 |
| Historical Pattern Extraction | v1.2 | C2 |
| Notification Quality Feedback Loop | v1.2 | B2 |
| Anomaly Narrator | v1.3 | B3 |
| "Why Did I Miss It?" Post-Mortem | v1.3 | A4 |

### Deferred (revisit when conditions change)

| Feature | Description | Why Not Now |
|---------|-------------|-------------|
| **Shoulder season finder** | Identify "best value" booking windows per campground from multi-season availability data. | Needs 12+ months of polling data. Revisit after v1.3 prediction model ships. |
| **Trip compatibility scorer** | Score campgrounds on fit for a specific trip. | Largely redundant with trip planner conversational reasoning. |
| **Availability narrative digest** | Weekly "campsite weather report" email. | Engagement pattern doesn't match episodic tool usage. Anomaly alerts (v1.3) fire at the right moment instead. |
| **Watch drift detection** | Detect when search behavior has drifted from watch parameters. | Needs meaningful search volume. Revisit if user base grows. |

### Skipped (not worth building)

| Feature | Description | Why Skip |
|---------|-------------|----------|
| **Entity resolution across providers** | LLM-assisted fuzzy matching to deduplicate campgrounds across rec.gov and GoingToCamp (e.g., "Ohanapecosh Campground" vs "Ohanapecosh"). | Not a real problem at 741 campgrounds. The registry is manually curated — duplicates are caught during seeding. The complexity of maintaining an ongoing dedup system isn't justified until the registry is 2,000+ campgrounds across 4+ providers. |
| **Schema change detection** | Store API response shape snapshots, LLM diffs when provider API structure changes, alerts developer. | Valid engineering concern for a solo operator, but a simple health-check test in CI (assert expected fields present in a sample response) accomplishes 80% of this without LLM complexity. Over-engineered for the actual failure mode. |
| **Drive time access correction** | Extract "unpaved road," "ferry required," "high clearance" from descriptions to apply multipliers to drive time estimates. | Low innovation, marginal impact. The current haversine-based drive times are directionally correct. Free-text extraction of road conditions would be noisy — "unpaved" could mean a smooth gravel road or a 4WD-only track. Better solved by manual curation of the top 50 campgrounds during v0.7 enrichment. |
| **Smart poll scheduling** | Dynamically allocate polling budget based on predicted cancellation probability windows — poll more when history says cancellations are likely. | Invisible to users, moderate implementation complexity, and the polling budget is not a real constraint at personal-tool scale with the existing 15-minute cycle. Engineering effort that doesn't move any user-facing metric. Could matter if polling costs become significant, but they won't at this scale. |
| **Packing weather brief** | Post-booking ephemeral card: "Olympic Hot Springs in late June: highs upper 50s, wool layer recommended." | Low impact. Most campers already have their own packing system. Weather apps do this better. The ephemeral-card interaction pattern is deceptively complex to build well (timing, dismissal, mobile responsiveness) for a feature that provides minor convenience. |
| **Smoke/wildfire risk scorer** | Integrate historical fire data and prevailing wind patterns to score campground-level smoke risk by month. | Interesting idea but the data pipeline is complex (USFS fire perimeters, AirNow, NASA FIRMS, wind modeling) and the problem is inherently unpredictable — smoke risk varies dramatically year to year. Real-time AQI at trip time is more useful than historical averages, and that's just a link to AirNow, not an AI feature. |

---

## Decision Log

| Decision | Rationale | Alternatives Considered |
|----------|-----------|------------------------|
| Ship watches on web before accounts | Highest-value gap to close. Anonymous watches with session tokens avoid forcing account creation for core functionality. | Wait for accounts first — rejected because it delays the most requested feature. |
| Calendar heat map in v0.3, not v0.2 | Heat map needs backend API work (availability density endpoint). Watches are simpler and higher immediate value. | Ship together — rejected because it makes v0.2 too large. |
| Accounts in v0.4, not earlier | Accounts alone deliver no user value. v0.4 pairs them with features that require accounts (saved prefs, persistent watches, search history). | v0.2 — rejected because anonymous watches handle the immediate need. |
| v0.6 restructured: AI Search → Smart Search | AI feature review scored NL search as low innovation/low impact — the structured form already works well, and NL-to-form is the most commoditized LLM use case. Zero-result recovery (smart date shifting, diagnostics) solves a higher-friction problem without requiring LLM integration. SDK integration moves to v0.5 (registry enrichment) and v0.8 (trip planner) where it's load-bearing. | Keep NL search as v0.6 — rejected because it occupies a full milestone for marginal UX improvement. Fold NL into v0.8 — considered but trip planner scope is already XL. |
| Registry auto-enrichment added to v0.5 | LLM tag extraction from RIDB/GoingToCamp descriptions feeds every downstream feature (search filtering, site vibe, trip planner recommendations). ~$0.10 for the full registry, no user-facing complexity. Natural pairing with v0.5's background engine since it introduces the Anthropic SDK. | Wait for v0.7 enrichment pass — rejected because earlier enrichment improves search quality sooner. |
| Contextual notifications + site vibe added to v0.7 | Both are low-effort, high-delight features that leverage Haiku (already integrated at v0.5). Contextual notifications transform raw watch alerts into actionable intelligence. Site vibe adds texture to result cards at zero query-time cost. Natural pairing with v0.7's registry enrichment. | Separate milestone — rejected because neither justifies its own release. Earlier — rejected because contextual notifications benefit from polling history accumulation. |
| v0.9 expanded to Predictions+ | Anomaly deal alerts and watch post-mortems use the same statistical infrastructure and polling data as predictions. All three are outputs of one system: cancellation pattern detection, seasonal baselines, and window duration tracking. Shipping them together avoids duplicating the data pipeline work. | Anomaly alerts as separate milestone — rejected because it's the same model with a different output direction. Post-mortems earlier — rejected because they need sufficient watch history. |
| Registry enrichment moved to v0.7 | Trip planner in v0.8 needs good campground detail data. Doing enrichment the milestone before ensures the data quality bar is met when it matters. | v1.0 enrichment pass — rejected because the trip planner would recommend campgrounds with thin detail data. |
| Single-hue heat map color scale | Red-to-green fails for ~8% of users with color vision deficiency. A single-hue scale (e.g., light to dark blue) with text density labels is both accessible and visually clear. | Red-to-green — rejected on accessibility grounds. Multi-color categorical scale — rejected as unnecessarily complex for a density visualization. |
| axe-core in CI from v0.2.1 | Catching accessibility regressions at merge time costs near zero. Catching them in a late audit means rework. Level A failures in the current build confirm this risk is real. | Annual accessibility audit — rejected because it batches preventable regressions. |
| Oregon State Parks in v0.7 | Provider work is independent and high-effort (Playwright). Sequencing it mid-roadmap gives time to learn from GoingToCamp integration patterns. | Earlier — rejected because Playwright adds Docker complexity. Later — rejected because it's P1. |
| Predictions in v0.9 | Requires 6+ months of polling data. Starting data collection at v0.5 means 4+ months of history by v0.9. | v0.7 — rejected because insufficient data. v1.0 — acceptable fallback if data is thin. |
| SQLite over PostgreSQL | Single-instance Fly.io deployment. SQLite is simpler, faster for read-heavy workloads, and sufficient at personal-project scale. | PostgreSQL — overkill for current scale. Turso/libsql — good option if multi-instance needed later. |
| v0.2.1 hardening milestone | Security review found 3 HIGH issues and 8 Level A a11y failures in shipped code. Fixing these before adding more features prevents compounding the debt and is low-effort relative to impact. | Fold fixes into v0.3 — rejected because security issues (especially the cookie flag and CORS config) should not stay open while new users onboard. |
| Monetization at v0.95, not v1.0 | Billing infrastructure needs trip planner (v0.8) and ideally predictions (v0.9) to exist before gating them. Shipping billing before v1.0 polish avoids coupling monetization with map view and keyboard shortcuts, which are independent. | v0.8 — rejected because trip planner should ship and stabilize before gating it. v1.0 — rejected because it delays revenue and couples with unrelated work. |
| Watches as the primary gate | Watches drive the only meaningful per-user server cost (polling, notifications, AI enrichment). Search is free to serve. Gating watches at 3 free creates natural upgrade pressure at the exact moment a user is most engaged. | Gate search — rejected because it destroys the free tier's value and word-of-mouth growth. Gate trip planner only — rejected because it's a soft limit (3/month free is sufficient for most users). |
| Hosted checkout + customer portal | Zero custom billing UI. Eliminates PCI scope (SAQ A), avoids building cancel flow, billing history, payment method management. At lifestyle-business scale, the ~2-5% fee premium is worth the engineering time saved. | Custom checkout form — rejected on PCI and complexity grounds. Custom cancel/billing UI — rejected because Stripe/LS customer portal is better than anything campnw would build. |
| 30-day grandfather period | Existing users with >3 watches must not be surprised or punished. Trust is the product's most valuable asset at small scale. Pausing (not deleting) watches preserves data and makes reactivation seamless on upgrade. | No grandfather — rejected as trust violation. Grandfather indefinitely — rejected because it eliminates upgrade pressure for the most engaged users. |
| Split v1.0 into v0.96/v0.97/v1.0 | Three focused releases of 2-4 weeks each beat one 10-week monolith. Each is independently shippable. Single developer context means serial focus is faster than context-switching. Registry first (map needs lat/lng), map+shortcuts together (shared keyboard model), recommendations last (capstone on top of both). | Ship as one v1.0 — rejected because 10+ weeks of mixed work with no intermediate ship points. |
| Defer Predictions+ to v1.1 | Data collection running since v0.5. Every month of deferral improves prediction quality. No v1.0 feature depends on predictions. Avoids interleaving statistical modeling with geographic visualization. | Ship v0.9 before v1.0 — rejected because it delays v1.0 by 4-6 weeks and predictions improve with more data. Interleave between v0.96/v0.97 — rejected because it splits focus across unrelated domains. |
| Personalized recommendations in v1.0, not deferred | Recommendations make v1.0 feel like a product milestone rather than "map + shortcuts." Without it, v1.0 is indistinguishable from v0.97. Scope must be tight: query over search history with tag/region affinity, not a recommendation engine. | Defer to v1.1 — considered but v1.0 needs a capstone beyond polish. |
| Restructure post-v1.0 into v1.1/v1.2/v1.3 | Predictions+ needs 9-12 months of polling data (collection started March 2026). Jumping straight to predictions leaves a ~9-month gap. v1.1 (AI search + registry quality) and v1.2 (trips + watches) fill the gap with user value while data matures. | Ship nothing, wait for data — rejected because momentum matters for personal projects and registry quality improvements have immediate payoff. |
| NL search in v1.1, reversing v0.6 deferral | Originally scored "low innovation/low impact" in March 2026 AI review. Re-evaluated: trip planner proves the Haiku tool_use pattern works, structured form has grown to 8+ fields, and NL input is the highest-impact single UX feature. Product review confirmed: if you only ship one thing post-v1.0, it should be this. | Keep deferred — rejected because the pattern is proven and the form complexity has increased. |
| Registry expansion to MT/WY/NorCal | All use existing RIDB provider — it's a seed script update, not new infrastructure. Broadens discovery for road trips beyond the PNW triangle. Low effort, high coverage payoff. | BC Parks — considered but different country, different booking system, lower demand. Idaho state parks — CAPTCHA-blocked. |
| Trip Object as v1.2 headline | Trips are the connective tissue between search, watches, and the planner. Without them, these features are independent tools. With them, there's a workflow: search → save to trip → watch → get alerted → book. Template watches and watch sharing both build on the trip concept. | Trips in v1.1 — rejected because NL search + registry quality is the right first move. Trips in v1.3 — rejected because watches are the Pro feature and need strengthening before predictions. |
