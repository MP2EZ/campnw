# Campable Roadmap: v0.2.1 to v2.0

**Last updated:** June 2026
**Current version:** v1.34 shipped (deployed at campable.co; weather cache fully warmed Apr–Oct 2026-06-12). v1.45 first milestone — internal iOS TestFlight — SHIPPED 2026-06-14.

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
v0.95   [BUILT*]   Monetization        — Free/Pro tiers, Stripe billing — built on feature/monetization (NOT merged, stale Mar 2026)
v0.96   [SHIPPED]  Registry + Infra    — Registry expansion, bundle audit, Lighthouse CI
v0.97   [SHIPPED]  Map + Power User    — Map view, keyboard shortcuts, lazy loading
v0.98   [SHIPPED]  Quality Hardening   — WCAG AA contrast, focus styles, ErrorBoundary, CI a11y
v0.99   [SHIPPED]  Pre-launch Audit    — Security headers, CSP, login rate limit, lazy loading, CVE CI
v1.0    [SHIPPED]  campnw 1.0          — OR State Parks, recs, collapsible form, hamburger, polish
v1.1    [SHIPPED]  Better Search       — NL search, registry expansion (MT/WY/NorCal), AI summaries
v1.15   [SHIPPED]  Brand + Identity    — Logo, palette, voice, og:image, notification copy
v1.2    [SHIPPED]  Trips + Watches     — Trip object, template watches, sharing, onboarding
v1.26   [SHIPPED]  Hardening           — History compaction, DB backup, SEC-10, re-enrichment
v1.27   [SHIPPED]  UX Polish           — Blue heatmap, teal WA, date picker, NL search, icons, filters
v1.28   [SHIPPED]  Watch Reliability   — Watch source persistence, N+1 fix, SSE batching, perf
v1.29   [SHIPPED]  Brand + Polish        — Madrona logo, og:image, LLM analytics, registry cleanup, itinerary cards
v1.3    [SHIPPED]  SEO + Discoverability — Campground profile pages, sitemap, structured data, Cloudflare
v1.31   [SHIPPED]  Audit Fixes          — Security hardening, perf optimizations, WCAG AA compliance
v1.32   [SHIPPED]  Accurate Drive Times — Mapbox routing, drive_times table, tiered search lookup
v1.33   ------->   Supabase Auth        — Replace custom auth with Supabase, Bearer tokens, auto-provisioning
v1.34   [SHIPPED]  Weather Context      — Typical temps + precipitation on search results via Visual Crossing
v1.35   [SHIPPED]  Source Photos        — Campground photos from RIDB/RA + SVG postcard placeholder for missing sources
v1.36   ------->   OAuth Login          — Google, Apple, + GitHub sign-in (Google/Apple blocked on LLC/developer accounts)
v1.4    [SHIPPED]  Monetization Launch  — Pro tier gate, Stripe Checkout/Portal, webhook handler, 1202 tests (test mode validated; live keys pending)
v1.41   [SHIPPED]  Playwright E2E       — Playwright E2E suite — smoke + watch/planner limits + cancel — 4/4 nightly green (2026-05-31)
v1.42   ------->   Site Polish + Legal  — About, Privacy, Terms, footer. Unblocks Stripe live-mode review + Apple App Store URL requirement.
v1.45   ~PARTIAL~  Native Apps          — Internal iOS TestFlight SHIPPED 2026-06-14 (Capacitor shell); App Store + Play + native push/GPS/offline registry in progress
v2.0    ------->   Predictions+        — Statistical model, anomaly alerts, post-mortems (~Q1 2027)
```

Each milestone is a shippable increment with clear user value. v1.33 establishes production auth (Supabase), v1.34 adds weather context to search results, v1.35 enriches result cards with source-site photos (engagement input to monetization), v1.36 adds OAuth sign-in, v1.4 transitions campable from personal tool to public product (code shipped + validated in Stripe test mode 2026-05-28; live keys + Stripe Customer Portal config still pending — see v1.4 Post-ship Status), v1.41 stands up Playwright E2E coverage (the 5 production bugs hit during v1.4 validation would have been caught by a single upgrade-flow smoke test — original plan was Maestro Web Beta, pivoted after Phase 0 spike found ~14min iframe lookups; see v1.41 entry), v1.42 adds the site pages v1.4 deferred (About + Privacy + Terms + footer — required for Stripe live-mode review and Apple App Store submission), v1.45 wraps the app for iOS + Android via Capacitor (sequenced after v1.4 so monetization is validated on the web before committing to App Store review cycles). v2.0 (Predictions+) deferred until Q1 2027 — data collection running since v0.5, quality improves with time.

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

## v0.95 "Monetization" [BUILT 2026-03-29, NOT MERGED — see status note]

### Theme
campnw has real users, real infrastructure costs, and a feature set that justifies a paid tier. This milestone introduces a Free/Pro split, subscription billing, and upgrade surfaces that make the paid tier discoverable without being coercive. The goal is sustainability, not growth. Break-even requires 2-4 Pro subscribers at $5/month. Everything here is scoped to that reality.

### Status (2026-05-25)
Implementation was completed on `feature/monetization` (6 commits, last touched 2026-03-29) and integrated against `main` through v1.0. The branch was never merged back to `dev`. Since March 2026, `dev` has moved 242 commits ahead — most critically v1.33 Supabase Auth, which replaced the custom-cookie user model that v0.95's billing code depends on. The branch is preserved as a reference implementation for v1.4 but will not be merged. See the v1.4 entry for the rebuild approach.

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

## v1.1 "Better Search + Coverage" — DONE

### Theme
Find campsites faster, across more of the northwest, with better data. Natural language search is the headline feature. Registry expansion and quality improvements make every search better. AI summarization and recommendation reasons add intelligence to results. Polling data continues accumulating toward v2.0 predictions.

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

## v1.15 "Brand + Identity" (~2-3 weeks, parallelizable with late v1.1)

### Theme
Campable rebranded from "campnw" but still has no formal visual identity — no logo, no brand palette spec, no og:image template. This milestone establishes the brand system: logo mark, color formalization, typography, voice guidelines, and the high-value touchpoints that drive word-of-mouth (notification copy, share cards). Can be worked alongside v1.1 since there are no code dependencies between them.

### Brand Positioning
**Discovery engine** — not monitoring (Campnab/Campflare), not listings (Dyrt/Hipcamp). Campable answers "where can I actually go camping this weekend?" across multiple booking systems. The key differentiating word is **available**: real availability, right now, across every system.

**Emotional territory:** Relief ("I can actually find something"), spontaneity ("let's just go"), local knowledge (a friend who knows all the spots).

**Tagline:** "Find your weekend." (primary) · "Real-time campsite availability across the Pacific Northwest." (explanatory/SEO)

### Features

| Feature | Size | Description |
|---------|------|-------------|
| Logo Mark | M | Prototype two directions: (A) Pin Drop — map pin with tent-shaped head, geometric; (B) Window/Ridgeline — rounded square with PNW treeline silhouette. Test both at 16px, 32px, 192px, 512px, and monochrome. The 16px favicon test decides the winner. Develop lowercase 'c' with pine-needle detail as compact variant. |
| Brand Palette Formalization | S | Name and spec the existing `tokens.css` colors as the brand palette. Define Brand Green (primary accent, exact HSL, AA-tested on both themes), Near-Black, Warm Cream, Campfire Orange (CTA accent, ~#D4722A). Resolve WA source green vs brand green collision — either shift WA to teal or use clearly distinct shade. |
| Typography System | S | Select and implement heading font (Plus Jakarta Sans or DM Sans). Two families max: heading/wordmark + system stack for body/data. No third accent font. Audit current system font usage and swap heading elements. |
| Dark Mode Heatmap Fix | XS | Widen dark mode heatmap color scale so levels 0-1 are distinguishable. Minimum 2:1 contrast between adjacent levels. CSS-only. (Carried from v1.1 — now a brand requirement, not just a bug.) |
| OG Image Template | S | Branded share card (1200×630) for link previews: logo mark + tagline + optional search context (source badge, campground name, dates, available count). Static SVG-to-PNG fallback. This is the acquisition touchpoint — shared in group chats and camping Facebook groups. |
| Notification Copy Audit | S | Apply brand voice to all watch alert copy. Title = campground name. Body = dates + site count + time-context. Never "Availability Alert" or "High urgency." Data-driven urgency, not manufactured. Test against 10 real notification scenarios. |
| PWA Assets | XS | Update manifest icons (192×192, 512×512), favicon (16×16, 32×32), apple-touch-icon, and splash screen with final logo mark. Monochrome variant for Android notification tray. |
| Brand Voice Guide | XS | Lightweight single-page reference (not a 40-page PDF): colors with hex values, logo usage, icon style (Lucide, outlined, 1.5px, rounded), voice examples, anti-patterns. Lives in `docs/BRAND.md`. |

### Scoping Consideration: Anthropic Batch API

The `enrich` CLI (`llm_tags.py`) currently calls Haiku sequentially in a `for` loop via `AsyncAnthropic` — 741 individual calls for a full registry run. The Anthropic Message Batches API (`client.messages.batches.create`) offers 50% input token savings and bulk submission for async workloads.

**Candidate jobs:** tag extraction, vibe generation, description rewrite — all offline, no latency requirement. These three passes have a data dependency chain (tags → vibes → descriptions), so they'd be 3 separate batch submissions, not 1.

**Scope in v1.15 if:** the enrichment code is already being modified for brand palette or description work, making it a natural time to refactor the call pattern.

**Defer to v1.2 if:** v1.15 stays purely design/CSS. v1.2's historical pattern extraction (741+ campgrounds × polling data) has higher volume and benefits more from batching. The `asyncio.gather()` with semaphore approach is a lighter-weight speed improvement that doesn't require changing the API pattern.

**Note:** At current scale (~$0.10/full run), batch savings are ~$0.02-0.03 per run. The primary benefit is speed (bulk submission vs sequential awaits), not cost. Savings become meaningful at v1.2 volumes.

### Voice Principles
- **Declarative, not interrogative.** "3 sites open at Ohanapecosh" not "Looking for campsites?"
- **Specific, not vague.** Always include the data point — campground name, dates, site count.
- **Honest about limitations.** "We check 794 campgrounds across 3 booking systems."
- **No outdoor-lifestyle marketing copy.** The user is already a camper. Don't sell camping — sell finding the campsite.
- **No "Oops!" or "Uh oh!"** in error states. State what happened, what to do, move on.
- **Discovery language** ("find", "search", "discover"), never monitoring language ("snag", "grab", "alert").

### Design Decisions

**Visual direction:** "AllTrails' clarity meets Hipcamp's warmth, printed in a National Park Service pamphlet." Information-dense and beautifully presented — like Dark Sky for campsite availability.

**What it should NOT feel like:** REI catalog (too corporate), camping emoji overload (too cute), hipster craft brand (too precious), government website (too sterile).

**Motion:** Snappy-functional (150-200ms, ease-out) for state changes. Slight overshoot (250-300ms) on feedback moments (watch confirmed). No celebration confetti, no bounce, no wiggle. The existing `--transition-fast` and `--transition-base` tokens are correct.

**Iconography:** Lucide icon set (MIT, rounded, 24px grid). Outlined at 1.5px stroke, filled for active states. No custom nature icon set initially — customize only where Lucide has gaps.

**Empty states:** Instructional, not decorative. No sad-tent illustrations. The SmartZeroState diagnostic data IS the content.

### Sequencing
Brand Palette (2) first — unblocks everything else. Typography (3) and Dark Mode Fix (4) can parallel. Logo (1) needs design iteration time. OG Image (5) and Notification Copy (6) depend on palette + logo. PWA Assets (7) and Brand Guide (8) ship last.

### Quality Bar
- Logo mark legible and recognizable at 16×16 favicon
- Brand Green passes WCAG AA (4.5:1) for text on both light and dark backgrounds
- WA source color visually distinct from brand green at all sizes
- OG image renders correctly in iMessage, Discord, Slack, and Facebook link previews
- All notification copy reviewed against 10 real-world watch alert scenarios
- No net increase in main bundle size from font loading (use `font-display: swap`, preload)

### Key Risks
- Logo design quality — geometric marks are hard to get right at small sizes without a skilled designer. Budget for 2-3 iteration rounds.
- Font loading performance — one custom font is fine, two will impact Lighthouse. System stack for body is non-negotiable.
- WA green collision — changing a source color affects 10+ tokens and every source badge in the UI. Audit all usages before changing.

### Cost
- $0 (no LLM costs — this is design + CSS work)
- Optional: $50-200 if commissioning logo from a designer

---

## v1.2 "Trips + Watches" — DONE

### Theme
Plan and track trips. The Trip object is the hub that search, watches, and the planner all connect to. Template watches make Pro worth paying for. Watch sharing drives organic growth. Historical patterns validate polling data quality while producing user-visible "Booking Tips." Identity improvements make accounts stickier.

### Features

| Feature | Size | Status | Description |
|---------|------|--------|-------------|
| Trip Object | L | DONE | trips + trip_campgrounds tables, CRUD API, SaveToTripButton dropdown, TripsPage + TripDetail pages, 10 trips/user max. |
| Template Watches | L | DONE | watch_type + search_params columns, expand.py resolves to facility_ids, poll_all integration, 20-campground cap. |
| Watch Sharing | S | DONE | shared_links table, UUID-based, POST /api/shares, GET /api/shared/{uuid} (no auth), 30-day expiry, revocable, 10/hr rate limit. |
| Trip Planner → Persistent Itinerary | M | DONE | POST /api/plan/save-trip extracts facility_ids from tool_use results, infers dates, creates Trip. |
| Onboarding + Profile | S | DONE | 2-step modal (home base + preferred tags), preferred_tags/onboarding_complete columns, toggle switch, home base → drive-from derivation. |
| Campground Comparison | S | DONE | POST /api/compare (2-3 facility_ids), Haiku narrative, graceful fallback to data-only. |
| Historical Pattern Extraction | M | DONE | analytics/patterns.py, availability_history aggregation, 30-day min, Haiku tips, booking_tips column, GET /api/campgrounds/{id}/tips. |
| Notification Quality Feedback Loop | S | DONE | analytics/notification_quality.py, analytics_digests table, monthly stats + Haiku analysis, 50-notification threshold. |

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

## v1.21 "Nav Redesign" — DONE

Simplified the top-level navigation from 5 tabs to a two-mode layout with inline map rendering.

| Feature | Status |
|---------|--------|
| "Find a Site" / "Plan a Trip" mode tabs on main page | DONE |
| Inline map (List/Map toggle in results toolbar) | DONE |
| Watchlist bell icon, Trips header button | DONE |
| AI search summary: bullet format, brand voice, moved below heatmap | DONE |
| Preferences: toggle switch, home base → drive-from derivation | DONE |
| Batch API for enrichment CLI (--batch, --batch-id, --force, --truncated) | DONE |
| Default state "All" (was WA) | DONE |

---

## v1.22 "Pre-Predictions Polish" — DONE

Frontend for v1.2 backend features + brand polish.

| Feature | Status |
|---------|--------|
| Dark mode heatmap fix (level 0-1 contrast) | DONE |
| Design principles in BRAND.md | DONE |
| Notification copy audit (brand voice) | DONE |
| Re-enrich registry (1,294/1,370 via batch API) | DONE |
| Comparison frontend (CompareBar + ComparePanel + checkbox) | DONE |
| Share buttons (WatchPanel + TripDetail) | DONE |
| Template watch UI ("Watch this search" + badge) | DONE |
| Batch --force/--truncated flags, sync-registry.sh | DONE |
| Dashboard hub for returning users | Deferred |

---

## v1.23 "Analytics" — DONE

PostHog integration replacing the custom `/api/track` endpoint.

| Feature | Status |
|---------|--------|
| PostHog JS SDK + `@posthog/react` PostHogProvider | DONE |
| `track()` → `posthog.capture()`, removed `/api/track` backend | DONE |
| User identification (posthog.identify on login/signup, reset on logout) | DONE |
| 17 custom events: search, card_expand, book_click, watch_created, trip_created, compare, share, mode_switched, map_toggled, onboarding, plan_message_sent, signup, login, save_to_trip | DONE |
| Automatic $pageview + session replay (masked inputs) | DONE |
| CI deploy: PostHog key as GitHub Actions secret → Vite build env | DONE |

---

## v1.24 "Hardening" — DONE

Security, a11y, and UX fixes from codebase audit.

| Feature | Status | Source |
|---------|--------|--------|
| CSP: add PostHog domains to script-src + connect-src | DONE | SEC-01 |
| OR State Parks watcher: add OR_STATE branch, thread ReserveAmericaClient | DONE | TEST-01 |
| OnboardingModal: focus trap + Escape key handler | DONE | UX-01 |
| Gate `/api/perf` and `/api/admin/digest` behind ADMIN_USER_IDS | DONE | SEC-02/03 |
| Scope `/api/poll-status` notifications to authenticated user | DONE | SEC-06 |
| Shared link UUIDs: full UUID4 32 hex chars (was 12) | DONE | SEC-04 |
| Share rate limit: IP-based (30/hr) + UUID-based (10/hr) | DONE | SEC-08 |
| Remove PII (email, home_base) from PostHog identify | DONE | SEC-05 |
| Dark mode accent-text overrides for v1.2+ components | DONE | UX-03 |
| SaveToTripButton: aria-expanded, aria-haspopup, role=menu | DONE | UX-02 |
| Use Fly-Client-IP instead of X-Forwarded-For | Deferred | SEC-10 |
| Auth modal max-width → var(--max-w-modal) | Deferred | UX-05 |
| Hardcoded spacing → tokens (1.25rem, 4px, 12px) | Deferred | UX-04/06/07 |

---

## v1.25 "Testing" — DONE

Close major test coverage gaps identified by audit.

| Feature | Priority | Source |
|---------|----------|--------|
| Planner agent: chat() + chat_stream() unit tests | Critical | TEST-02/03 |
| _poll_tranche() integration test | Warning | TEST-04 |
| batch process_results() test | Warning | TEST-08 |
| poll_all() with template watch integration | Warning | TEST-10 |
| useSearch hook tests (SSE, abort, source filter) | Warning | TEST-06 |
| useAuth hook tests (login/logout/identify) | Warning | TEST-07 |
| ResultCard, CompareBar, OnboardingModal component tests | Warning | TEST-05 |

---

## v1.26 "Hardening" [SHIPPED 2026-03-31]

### Theme
Operational stability. The availability_history table hit 9.37M rows in 2.5 days (377 MB/day), filling the 1GB Fly volume to 100%. Fixed the storage model, added backups, closed deferred security and enrichment gaps before the long data-collection runway to v2.0.

### What Shipped

| Feature | Description |
|---------|-------------|
| Fly volume 1GB → 3GB | Immediate relief, now at ~1% usage |
| Change-detection recording | `record_availability_history` rewrites to upsert `availability_daily` (one row per site/date) + `status_transitions` (only on change). Storage dropped from ~377 MB/day to negligible. |
| History compaction | 9.37M raw rows compacted into 57K daily rollups. DB rebuilt from 1.3GB to 34MB. Old `availability_history` table emptied. |
| patterns.py migration | Analytics reads from `availability_daily` instead of raw history. `refresh_all_tips` also updated. |
| SEC-10: Fly-Client-IP | `get_client_ip` prefers `Fly-Client-IP` header over spoofable `X-Forwarded-For` |
| Weekly DB backup | GitHub Actions workflow: `fly sftp get` both DBs, integrity check, upload as artifact (90-day retention) |
| Registry re-enrichment | 50 campgrounds enriched (remainder lacked sufficient description data for tag extraction) |

### Lessons Learned
- Compaction on a small Fly VM (256MB) can't handle bulk SQL over 9M+ rows — downloaded locally, compacted, re-uploaded.
- The prod DB had corruption (btreeInitPage errors, rowid out of order) likely from the volume filling to 100%. Rebuilt via table-by-table Python copy.
- `availability_cache` was lost during rebuild (ephemeral, repopulates on next poll cycle).

---

## v1.27 "UX Polish" [SHIPPED 2026-04-04]

### What Shipped

| Feature | Description |
|---------|-------------|
| Heatmap → blue ramp | Replaced green with blue (#eef1f5 → #1a5278). Moved tokens from App.css to tokens.css. |
| WA Parks → deep teal | Shifted from blue (#2a7a9a) to deep teal (#1a7068). CVD-safe under deuteranopia. |
| Badge contrast (WCAG AA) | Rec.gov #5a8a32 → #4f7d2c, OR Parks #b8860b → #9a7509. Both now pass 4.5:1. |
| Source filter isolate | Click from all-on isolates; click another adds; remove-last resets to all. |
| Heatmap day labels | All 7 rows labeled (Su–Sa). Day filter dimming with `filter: saturate(0.3) opacity(0.55)`. |
| NL search placement | Moved above form with search icon + "or search by filters" divider. |
| Watchlist text | Replaced bell emoji with "Watchlist" text button. |
| Font normalization | `font: inherit` on all form elements. |
| Date range picker | Unified popover calendar with mode-aware labels ("Search between" / "Check in – out"). |
| Icon library | 15 SVG components in `icons.tsx`, replaced all emoji/symbols. |
| Heatmap mobile | Sticky day labels on scroll, wrapping header. |
| Keyboard nav | Arrow keys in calendar grid, Home/End, `role="grid"`. |
| XSS fix | Replaced `dangerouslySetInnerHTML` with safe `renderMarkdown()` JSX. |
| MonthGrid perf | Extracted as memo child, pre-computed aria-labels. |
| PostHog events | 29 tracked events covering all user interactions. |
| Tests | 158 frontend tests (up from 141). |

### Design References
- `docs/v1.27-color-exploration.html`, `docs/v1.27-heatmap-labels.html`
- `docs/v1.27-nl-search-placement.html`, `docs/v1.27-date-range-picker.html`
- `docs/v1.27-date-labeling.html`

---

## v1.28 "Watch Reliability" [SHIPPED 2026-04-05]

### What Shipped

| Fix | Description |
|-----|-------------|
| `booking_system` column on watches | Added column + migration + self-heal on first poll. WA/OR state park watches now poll via correct provider. |
| Batched `record_availability_history` | Replaced N+1 (9K-18K queries per campground) with 3 queries (1 SELECT + 2 executemany). Primary OOM fix. |
| Persistent PostHog httpx client | Was creating new client per request; now initialized in lifespan. |
| Parallel watch polling | Sequential → `asyncio.gather` with semaphore(3). 5 watches: 75s → ~25s. |
| RAF-throttled SSE re-renders | 20 setState calls per search → ~2-3 batched via requestAnimationFrame. |
| Lazy-loaded CalendarHeatMap | Code-splits to 3.76KB chunk, loads on demand. Main bundle 289KB → 286KB. |
| Fly VM scaled to 512MB | Done 2026-04-04. Still under Fly's $5 waiver threshold ($0/mo). |

---

## v1.29 "Brand + Polish" [SHIPPED 2026-04-07]

### What Shipped

| Feature | Description |
|---------|-------------|
| Madrona pin logo | Custom madrona tree silhouette (S-curve trunk, 3 branches, scalloped canopy) inside a map pin. Generated all icon PNGs (16-512px), apple-touch-icon, og:image (1200x630). |
| PostHog LLM analytics | Wrapped all 12 Anthropic call sites with `posthog.ai.anthropic` wrapper. Captures `$ai_generation` events with model, tokens, latency, cost. Shared client in `posthog_client.py`. |
| PostHog session replay | Enabled with `maskAllInputs: true` for user privacy. |
| Registry cleanup | Removed 3 non-campground RIDB facilities (corridors, scenic areas). Updated seed script exclude patterns. |
| Itinerary card view | `ItineraryCard` component renders trip planner campground suggestions as visual cards with numbered badges, source badges, dates, drive time, booking links. Planner outputs structured JSON in ```itinerary fences. |

### Design Process
- Logo exploration: 60+ variations across evergreen, spruce, lodgepole, madrona tree types
- Final direction: madrona (Pacific madrone) — distinctive PNW tree with sinuous curved trunk
- Canopy styles explored: overlapping circles, scalloped edges, organic blobs, dappled negative space
- Final: LF9 — deep S-curve trunk, 3 forking branches, merged scalloped canopy, positioned +40px down / -5px left
- Design files: `docs/v1.29-logo-*.html`

---

## v1.3 "SEO & Discoverability" [SHIPPED 2026-04-08]

### What Shipped

| Feature | Description |
|---------|-------------|
| Campground profile pages | `/campgrounds/{state}/{slug}` — Jinja2 SSR with registry data, JSON-LD structured data (`schema.org/Campground`). |
| State index pages | `/campgrounds/{state}` — all campgrounds in a state, grouped/filterable. |
| Tag landing pages | `/tags/{tag}` — campgrounds filtered by enriched tags. |
| "This weekend" page | `/this-weekend` — auto-updated availability landing page. |
| Sitemap + robots.txt | Auto-generated `sitemap.xml` from registry. |
| Per-route meta tags | Unique `<title>`, `<meta description>`, og tags per SPA route via react-helmet-async. |
| Registry slug column | URL-safe slug generated from campground name. |

### Architecture Decision
Jinja2 templates in FastAPI, not a Next.js migration. The React SPA continues to handle all interactive features unchanged.

---

## v1.31 "Audit Fixes" [SHIPPED 2026-04-09]

### What Shipped

| Fix | Description |
|-----|-------------|
| Rate limit hardening (SEC-04) | Planner rate limit keyed by IP only — removes cookie-based bypass. |
| Error sanitization (SEC-06) | Streamed planner errors return generic message; no raw exception details. |
| PostHog proxy allowlist (SEC-01) | Proxy forwards only safe headers. |
| Rate limiter cleanup (SEC-03/05) | Auth, planner, and share rate limiters evict stale entries. |
| CSP hash (SEC-02) | Reverted to `unsafe-inline` — sha256 hash broke PostHog session replay. |
| ReserveAmerica pagination (PERF-01) | Fetch all pages when park has >20 sites. |
| Watcher fetch dedup (PERF-02) | Pre-warm availability cache for multi-watch facilities. |
| SQL bounding box (PERF-03) | `get_nearby` uses lat/lon bounding box pre-filter. |
| SQL tag filter (PERF-04) | Tag filtering via SQLite `json_each()`. |
| Alt-date probe reuse (PERF-05) | Date suggestion probes reuse prepared search data. |
| LLM stream batching (PERF-06) | Text chunks batched via `requestAnimationFrame`. |
| Dark mode contrast (A11Y-01) | `--text-light` lightened to 4.7:1 ratio. |
| A11Y fixes (A11Y-02–12) | Auth alerts, landmarks, touch targets, nav structure, input labels. |

---

## v1.32 "Accurate Drive Times" [SHIPPED 2026-04-13]

### Theme
Replace haversine approximations with real road-network routing. The current haversine × 1.4 terrain multiplier can be off by 1.5-2x for PNW geography — Olympic Peninsula campgrounds show ~60 min but are actually 3+ hours due to water crossings and mountain passes. As Campable attracts real users, drive times must match what people see on Google Maps.

### Features

| Feature | Size | Description |
|---------|------|-------------|
| Mapbox client module | M | Async `mapbox.py` with Directions API (single route) and Matrix API (batch, auto-chunks at 25 destinations). |
| `drive_times` table | S | New SQLite table keyed by `(base_name, booking_system, facility_id)` storing Mapbox-computed minutes + miles. |
| Batch pre-compute script | M | `scripts/compute_drive_times.py` — Matrix API batch for all 12 known bases × 1,370 campgrounds (~660 API calls). |
| Tiered search engine lookup | M | Tier 1: DB lookup for known bases (instant). Tier 2: Mapbox Matrix for custom addresses (~10-50 results). Tier 3: haversine fallback. |
| Planner tool upgrade | S | `get_drive_time` uses Mapbox single route with haversine fallback. |
| Accurate `get_accurate_drive_minutes()` | S | New async function in `geo.py` — Mapbox with haversine fallback. |

### Architecture Decision
Mapbox free tier (100k requests/month) over self-hosted OSRM. Both use OpenStreetMap road data, but Mapbox requires zero infra — no Docker sidecar, no OSM data updates, no extra RAM on Fly.io. Pre-computed drive times from known bases mean most searches hit the DB with zero API calls. Custom address searches only route the filtered result set (~10-50 campgrounds), not all 1,370.

### Dependencies
- v1.31 shipped
- `MAPBOX_ACCESS_TOKEN` in `.env` and Fly secrets

### Quality Bar
- Spot-check known-bad routes: Kalaloch, Hurricane Ridge, Hoh Rainforest (Olympic Peninsula), Mt. Rainier east side
- Known base searches return DB-cached times (no API call)
- Custom address searches route via Mapbox Matrix
- App starts and searches work without `MAPBOX_ACCESS_TOKEN` (haversine fallback)
- All tests pass

### Key Risk
Mapbox Matrix API may return `null` for campgrounds on unmapped forest service roads. Fallback to haversine for those individual campgrounds, clearly labeled as "estimated."

---

## v1.33 "Supabase Auth"

### Theme
Replace custom email/password auth with Supabase Auth. No existing users — clean swap with no migration bridges. OAuth providers configured in Supabase dashboard but not connected yet (placeholders for v1.36). Auth data (email, password, OAuth identities) moves to Supabase; profile/preferences stay in SQLite keyed by Supabase user UUID.

### Features

| Feature | Size | Description |
|---------|------|-------------|
| Supabase project setup | S | Create project (us-west region for PNW latency), configure redirect URLs, note secrets. |
| Backend JWT swap | M | Replace custom HS256 validation with Supabase JWT validation via PyJWT. `SUPABASE_JWT_SECRET` env var. Local decode only (~0.5ms) — no network calls per request. |
| User auto-provisioning | S | `supabase_id TEXT UNIQUE` column on `users` table. On first authenticated API call, `get_current_user` creates local user record. Integer `id` stays as FK everywhere — zero schema migration on watches/trips. |
| Remove custom auth routes | M | Delete `/api/auth/signup`, `/api/auth/login`, `/api/auth/logout`. Keep `/api/auth/me` (GET, PATCH, DELETE) and `/api/auth/export`. Remove bcrypt dependency. |
| Frontend Supabase client | M | `@supabase/supabase-js` (~50KB gzipped). Replace `useAuth` internals — keep same `AuthContextValue` interface so all consumers unchanged. |
| Bearer token pattern | M | Replace `credentials: "include"` cookie approach with `Authorization: Bearer` header on all API calls. New `authFetch()` wrapper in `api.ts`. |
| Anonymous session migration | S | On first authenticated call for a new user, check for `campnw_session` cookie and migrate watches via existing `migrate_watches_to_user()`. |
| CSP update | S | Add `https://<project-ref>.supabase.co` to `connect-src`. Pin to exact project ref. |
| Account deletion update | S | `DELETE /api/auth/me` also calls Supabase admin API to delete user (prevents orphaned PII in Supabase). |

### Architecture Decisions

**Split data model.** Auth in Supabase, profile in SQLite. Lookup path: Supabase JWT `sub` (UUID) → query `users WHERE supabase_id = ?` → get local integer `id` → use as FK everywhere. One index, one join, zero FK migration.

**Auto-provisioning over webhooks.** `get_current_user()` creates the local user inline on first request. No webhook ordering issues, no race conditions.

**localStorage for tokens.** Supabase JS SDK default. A cookie proxy pattern would be more secure against XSS but adds significant complexity (backend refresh management, token rotation). Acceptable for a campsite tool with CSP protections. Revisit if handling sensitive data.

**Local JWT validation only.** Supabase uses HS256 with a static secret. PyJWT decodes in ~0.5ms — actually faster than the current bcrypt + JWT approach (~5ms). Never call Supabase's `/auth/v1/user` per-request.

### Security Requirements
- Pin JWT algorithm to `["HS256"]` — reject `none` and other algorithms
- Add `leeway=30` to `jwt.decode()` for clock skew between Supabase and Fly.io
- Validate `aud: "authenticated"` and `role: "authenticated"` claims
- `SUPABASE_SERVICE_ROLE_KEY` in Fly secrets only — never in frontend code or client responses
- `SUPABASE_ANON_KEY` is public by design — expose as `VITE_PUBLIC_SUPABASE_ANON_KEY`

### Secret Management

| Secret | Where | Notes |
|--------|-------|-------|
| `SUPABASE_JWT_SECRET` | Fly secrets | Replaces `JWT_SECRET` |
| `SUPABASE_URL` | Fly secrets + frontend env | Public project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | Fly secrets only | Bypasses RLS — backend-only |
| `VITE_PUBLIC_SUPABASE_URL` | Frontend build env | Public |
| `VITE_PUBLIC_SUPABASE_ANON_KEY` | Frontend build env | Public |

### Files Changed

**Backend (~150 lines changed):**
- `auth.py` — gut and replace with Supabase JWT decode (~20 lines)
- `routes/auth.py` — remove signup/login/logout, keep profile CRUD (~-80 lines)
- `routes/deps.py` — rewrite `get_current_user` for Bearer token + auto-provision
- `monitor/db.py` — add `supabase_id` column, `get_user_by_supabase_id()`, make `password_hash` optional
- `api.py` — CSP `connect-src` update

**Frontend (~110 lines changed):**
- `lib/supabase.ts` — new, ~5 lines
- `hooks/useAuth.ts` — rewrite internals, keep interface
- `api.ts` — replace cookie auth with Bearer token helper
- `components/AuthModal.tsx` — swap to use Supabase via hook

### Testing Strategy

**Delete:** Custom signup/login/bcrypt endpoint tests.

**New (15-20 tests):**
- 5 JWT validation (valid, expired, malformed, missing, wrong algorithm) — test JWTs signed with known secret in CI, no Docker or Supabase emulator
- 6 session migration (watches transfer, duplicates, idempotency, invalid token)
- 3-4 frontend `useAuth` hook tests — mock Supabase JS client
- 2 AuthModal tests

**Unchanged:** All watch/trip/planner/search tests — swap auth fixture in `conftest.py` from custom JWT to Supabase-shaped JWT.

### Dependencies
- v1.32 shipped
- Supabase project created (free tier, us-west region)

### Quality Bar
- Signup → create watch → logout → login → watch persists
- Anonymous watch → signup → watch migrates to account
- Expired/malformed token returns 401, not 500
- App functional in anonymous mode if Supabase is unreachable
- All existing tests pass with swapped auth fixture

### Key Risk
Supabase availability becomes a dependency for login (not for ongoing sessions — local JWT validation works offline). Existing valid tokens continue working until expiry (1 hour default). Anonymous mode is unaffected.

---

## v1.34 "Weather Context" [SHIPPED 2026-05-16]

### Post-ship Status [cache fully warmed 2026-06-12]
Code shipped 2026-05-16; the cache warmup ran as a long tail on the free tier and completed 2026-06-12. **Shipped reality differs from the plan below:**
- **Window: Apr–Oct (7 months), not 12.** Shoulder/winter months are mostly NYR or snowed-in at PNW elevations — weather badges there would decorate dates nobody can book. Source of truth: `SEASON_MONTHS` in `providers/weather.py`.
- **36,176 records, not ~16,400.** 1,300 unique rounded coordinates × 4 sample days/month (1, 8, 15, 22) × 7 months. The plan assumed one record per campground-month; the warmup samples 4 days/month for intra-month resolution.
- **Synced to the Fly volume** via `scripts/sync-registry.sh` (registry.db is reference data; user/watch state lives separately in `watches.db`, untouched by the sync).

### Theme
Show typical weather (high/low temps, precipitation probability) on search results so users can factor climate into campground selection. This is a **discovery-time** feature — "is it going to be freezing at night there in May?" — not a post-booking packing list (which was rejected as low-impact). Weather context turns campable from a pure availability tool into a trip-planning tool that helps you pick the *right* campground, not just an *available* one.

### Features

| Feature | Size | Description |
|---------|------|-------------|
| Visual Crossing provider | S | Thin async `httpx` client. Takes `(lat, lon, start_date, end_date)`, returns daily normals (high/low temp °F, precip probability %). Uses Visual Crossing Timeline API with `include=stats` for statistical normals. |
| SQLite weather cache | S | `weather_normals` table: `(lat_round, lon_round, month, day) → temp_high, temp_low, precip_pct`. Lat/lon rounded to 2 decimal places (~1km). Climate normals are static — cache never expires. |
| Cache warmup script | S | `scripts/warm_weather_cache.py` — iterate registry campgrounds, fetch normals for all 12 months, populate cache. ~1,370 campgrounds × 12 months = ~16,400 records. Run once over ~17 days on free tier, or faster on paid. |
| Search result enrichment | M | After availability check, look up cached normals for each result's lat/lon + searched date range. Average across the date range. Attach `weather` field to `CampgroundResultResponse`. |
| Weather display on ResultCard | S | Small weather summary on each result card: temp range + precip indicator. Follows existing design token system. No new dependencies. |
| Env var + fallback | S | `VISUAL_CROSSING_API_KEY` in `.env` and Fly secrets. Weather is best-effort — missing key or API errors skip weather silently, never block search results. |

### Architecture Decisions

**Visual Crossing over Open-Meteo.** Open-Meteo's free tier prohibits commercial use — campable.co is LLC-operated and heading toward monetization. Visual Crossing's free tier (1,000 records/day) explicitly allows commercial use. Upgrade path is pay-as-you-go at $0.0001/record if needed.

**Aggressive caching eliminates ongoing API cost.** Climate normals for a given location + calendar day are 30-year averages — they don't change. After the initial cache warmup (~16,400 records across the full registry), searches hit SQLite, not Visual Crossing. New campgrounds added to the registry are the only source of cache misses.

**Rounded coordinates for cache efficiency.** Lat/lon rounded to 2 decimal places (~1.1km resolution). Campgrounds within ~1km share a cache entry. This is more than precise enough — weather doesn't vary meaningfully across 1km at the scale of PNW mountain/forest terrain.

**Per-source fan-out awareness.** Multi-source searches check up to `max_campgrounds` per source (e.g., 20 rec.gov + 20 WA State = 40 campgrounds). Weather lookups scale with total campgrounds checked, not the user-facing limit. Caching makes this a non-issue after warmup — all lookups are local SQLite reads.

**Best-effort, never blocking.** Weather enrichment happens after availability results are ready. If the cache is cold for a campground or Visual Crossing is down, the result ships without weather. No degradation to core search functionality.

### Data Model

```python
@dataclass
class WeatherNormals:
    temp_high_f: float    # average daily high (°F)
    temp_low_f: float     # average daily low (°F)
    precip_pct: float     # precipitation probability (0-100)
```

**API response addition:**
```json
{
  "facility_id": "232465",
  "name": "Ohanapecosh",
  "weather": {
    "temp_high_f": 72,
    "temp_low_f": 45,
    "precip_pct": 12
  },
  ...
}
```

### Files Changed

**Backend (~120 lines new):**
- `providers/weather.py` — new, Visual Crossing client + cache logic (~80 lines)
- `routes/search.py` — attach weather to response (~15 lines)
- `registry/db.py` — `weather_normals` table creation + lookup methods (~25 lines)

**Frontend (~40 lines new):**
- `api.ts` — add `weather` field to `CampgroundResult` interface
- `components/ResultCard.tsx` — weather summary display

**Scripts:**
- `scripts/warm_weather_cache.py` — new, one-time cache warmup

### Testing Strategy

**Automated (6-8 tests):**
- 3 provider: API response parsing, cache hit/miss, error fallback (mock `httpx`)
- 2 cache: round-trip write/read, coordinate rounding, deduplication
- 2 integration: search result includes weather when cached, omits when not cached
- 1 frontend: weather summary renders correctly, absent gracefully

**Manual checklist (~10 min at ship time):**
1. Search WA campgrounds for July dates → weather appears on result cards
2. Same search again → instant (cache hit, no API call)
3. Unset `VISUAL_CROSSING_API_KEY` → search works, no weather shown, no errors
4. Check a specific campground → weather shown
5. Search with dates spanning two months → averaged correctly

### Dependencies
- None. Weather is fully independent of auth — no shared models, no shared endpoints, no shared cache.
- Visual Crossing free account + API key
- Cache warmup script run at least once before deploy

### Quality Bar
- Weather never delays search results (best-effort enrichment)
- Cached lookups add <5ms to search response
- Missing API key logs a warning on startup, not per-request
- All existing search tests pass unchanged
- Temps displayed in °F (target audience is US Pacific Northwest)

### Key Risks

| Risk | Mitigation |
|------|------------|
| Visual Crossing free tier limit (1,000 records/day) | Cache warmup amortizes over ~17 days. Ongoing usage is near-zero (cache hits). Pay-as-you-go ($0.0001/record) if traffic spikes during warmup. |
| API accuracy for remote mountain locations | Visual Crossing blends station + radar + ERA5 reanalysis — better than pure station-based APIs for rural PNW. Verify accuracy for a few known mountain campgrounds before shipping. |
| Visual Crossing deprecation/pricing change | Provider is a thin ~80-line wrapper. Open-Meteo (with paid commercial license) is a drop-in backup. |
| Cache warmup takes 17 days on free tier | Acceptable for initial launch. Can accelerate with a temporary paid tier day ($0.0001 × 16,400 = $1.64 total). |

---

## v1.35 "Source Photos" [SHIPPED 2026-05-16]

### Theme
Surface campground photos from booking sources on result cards. Campable is a discovery tool — users compare 10-30 options before committing — and right now a result is a name + tags + availability. A photo answers "do I want to be there?" in the moment users would otherwise bounce to Google Images. Photos are facility-level (not site-level), shown only in the expanded card body so the collapsed scan path is unchanged.

Sources differ in photo accessibility: Rec.gov/RIDB has a documented `/facilities/{id}/media` endpoint (1,242 campgrounds, public domain); ReserveAmerica photos are already in the Redux JSON we scrape for OR State Parks (53 campgrounds, attribution required); WA State Parks/GoingToCamp has no JSON photo API, so its 75 campgrounds render an SVG postcard placeholder until/unless we add HTML scraping. ~91% real photo coverage at ship, the rest visibly designed as "we know this place, no photo yet" rather than "broken."

### Features

| Feature | Size | Description |
|---------|------|-------------|
| Registry schema migration | S | Add `image_urls TEXT DEFAULT '[]'`, `image_attribution TEXT DEFAULT ''`, `image_verified_at TEXT` to `campgrounds` table. Inline migration in `registry/db.py` `__init__` following existing pattern. |
| RIDB media fetch in seed | S | Extend `scripts/seed_registry.py` to call `GET /facilities/{id}/media`; store first 3 photo URLs as JSON array. Throttled to 50 req/min (existing RIDB limit). |
| RA Redux photo extract | S | Extend `scripts/seed_or_state.py` to pull photo URLs from the existing Redux scrape — no new HTTP. Attribution: "Oregon State Parks". |
| `<HeroPhoto>` component | M | Renders inside expanded `ResultCard.tsx` body, above date blocks. `aspect-ratio: 16/9` wrapper, `object-fit: cover`, `filter: saturate(0.85) contrast(1.03)` to flatten quality variance between sources. `<img loading="lazy" decoding="async">` with `alt={name}, {tags[0]}`. Dot pager for 2-3 photos. |
| `<PostcardPlaceholder>` component | S | Deterministic SVG: source-color stripe, Madrona pin watermark, campground name + region, 2-3 tag glyphs derived from `tags[]`. Zero network cost. Renders for campgrounds with empty `image_urls`. |
| Attribution overlay | XS | "Photo: Recreation.gov" / "Photo: Oregon State Parks" — hover/focus reveal, bottom-right of hero. Not shown on placeholder. |
| URL verification cron | S | Nightly job HEADs each cached `image_urls` entry; clears stale (4xx/5xx) URLs and bumps `image_verified_at`. Stale URLs gracefully fall back to placeholder. |
| Kill-switch flag | XS | `hero_photos` env flag (server-rendered into bootstrap). Ship 100%-on; flag exists for rollback only. |

### Architecture Decisions

**Hotlink, don't cache.** Store source-CDN URLs in registry; serve directly to clients. Saves Fly egress and storage. If Rec.gov/RA rotates CDN paths, `image_verified_at` plus the nightly probe catches breakage within 24h — broken cards fall back to placeholder cleanly. Caching layer (R2 / Fly volume) can be added later without schema change.

**Campground-level only.** No per-site photos. All three sources index media by facility, not by individual site. UX-wise, the hero answers "do I want to be at this campground?" — site-specific decisions happen on the booking site. Future v1.4+ enhancement could surface per-site media via RIDB `/campsites/{id}/media`, but coverage is sparse and the data shape pushes us toward a different UI (site-picker thumbnails), not an evolution of this hero pattern.

**Placeholder as design, not fallback.** The SVG postcard is rendered with the same chrome (16:9 box, source-color accent) as photo cards — it reads as a designed surface, not a defect. Critical for WA State Parks (~5.5% of registry) which will *never* have source photos until we add scraping.

**Uniform photo treatment.** `filter: saturate(0.85) contrast(1.03)` applied to all real photos. Rec.gov shots skew "1990s ranger snapshot"; RA shots are glossy marketing photos. Slight desaturation + micro contrast lift normalizes the visual register so the product reads as one design language. Applied via `.is-photo` modifier — placeholder keeps full brand vibrance.

### Measurement Plan

Two-week before/after window on PostHog (already wired):
- **Expansion rate** — do collapsed cards get expanded more once users learn photos exist?
- **Expand → outbound-click conversion** — do photos help users commit, or do they linger and bounce?
- **No-photo cohort delta** — does WA State Parks (placeholder-only) underperform on expand→click vs. photo cohorts? Tells us whether the 9% coverage gap is a real problem worth investing scraping effort into.

If photos clearly lift engagement, consider Option A (collapsed-card thumbs) as a v1.4+ follow-up. If they don't, photos aren't the missing UX piece and we redirect effort.

### Risks

- **Layout shift (CLS).** Mitigated by `aspect-ratio: 16/9` on the hero wrapper — reserves space before image loads. Smoke-test with Lighthouse on launch.
- **Hotlinking fragility.** Mitigated by nightly verification cron + graceful placeholder fallback. Not a launch blocker.
- **Photo licensing for non-federal sources.** RIDB is public domain (federal). RA may include user-submitted photos with murkier rights — attribution overlay covers the obligation. Audit a sample of 20 RA photos before ship to confirm none are obviously user-uploaded.
- **Image quality variance.** Mitigated by uniform desaturation treatment (above).
- **No alt text from sources.** Mitigated by generating from `${name}, ${tags[0]}`. Not as good as captions but better than empty.

### Files Changed

**Backend (~80 lines):**
- `src/pnw_campsites/registry/db.py` — schema constant + migration block + upsert/bulk_upsert column list + `_row_to_campground` parse + `update_image_urls()` helper
- `src/pnw_campsites/registry/models.py` — three fields on `Campground`
- `src/pnw_campsites/api.py` — `SearchResponse.results[]` includes `image_urls` + `image_attribution`
- `scripts/seed_registry.py` — RIDB `/facilities/{id}/media` fetch
- `scripts/seed_or_state.py` — extract photo URLs from existing Redux scrape
- New: `scripts/verify_image_urls.py` — nightly HEAD probe cron

**Frontend (~120 lines):**
- `web/src/components/ResultCard.tsx` — render `<HeroPhoto>` inside `card-body` when expanded
- New: `web/src/components/HeroPhoto.tsx` — img + lazy loading + dot pager + attribution overlay
- New: `web/src/components/PostcardPlaceholder.tsx` — deterministic SVG postcard
- `web/src/api.ts` — extend `SearchResponse` types
- `web/src/App.css` (or component-scoped CSS) — `.hero`, `.hero.is-photo`, `.hero-pager`, `.hero-attribution`

### Testing Strategy

**Automated (~8 tests):**
- 2 backend: registry migration adds columns; `update_image_urls()` round-trip
- 2 backend: RIDB media-endpoint adapter parses sample responses; OR Redux extractor handles missing-media case
- 3 frontend: `<HeroPhoto>` renders with lazy attribute and correct alt; pager increments on click; attribution shown on hover
- 1 frontend: `<PostcardPlaceholder>` renders for empty `image_urls`, includes tag glyphs

**Manual (~10 min):**
- Smoke test 5 Rec.gov campgrounds, 3 OR State Parks, 2 WA State Parks (placeholder)
- Lighthouse CLS check on results page
- Dark-mode visual check on placeholder

### Dependencies

None hard. Could ship in parallel with v1.33/v1.34 — no auth, no data-warehouse, no shared component changes. Reasonable shipping order: alongside or just after v1.34 (Weather Context), since both touch the expanded `ResultCard.tsx` body. Bundling the redesign passes is cheaper than two separate ones if scheduling allows.

### Out of Scope

- Per-site photos (deferred, may be v1.4+ if facility photos prove valuable)
- WA State Parks HTML scraping (deferred; placeholder is the launch experience for those 75 parks)
- Photo caching layer (R2 / Fly volume) — hotlink first, cache only if breakage justifies the storage cost
- Lightbox / fullscreen viewer — start with dot-paged hero only; revisit if usage data warrants
- User-uploaded photos (community feature, deferred indefinitely)
- Map view photo popovers (would land with the deferred dashboard hub item)

### Post-ship Status (2026-05-25)

- 7 of 8 spec features shipped in PR #21 (commit `2076040`). Frontend graceful fallback (`onError` → placeholder) and `photo_load_failed` PostHog event both wired and firing.
- **URL verification cron deferred.** The spec'd nightly HEAD probe (`scripts/verify_image_urls.py`) was not built. Rationale: the user-facing failure mode is already covered by the frontend `onError` fallback (broken image → placeholder), and bulk CDN rotation events are detectable in near-real-time via PostHog. A PostHog alert on `photo_load_failed` event rate replaces the cron as the detection mechanism — same coverage for ~80% of the risk at zero operational cost. Revisit the cron only if (a) v1.3 SEO traffic grows enough that broken OG-tag image URLs become a measurable issue, or (b) the PostHog alert misses a real rotation event.
- **Measurement window** closes 2026-05-30 (two weeks post-ship). Read `card_expand` rate, `expand → book_click` conversion, and the no-photo (WA State Parks) cohort delta to decide whether to invest in WA HTML scraping or pursue Option A collapsed-card thumbs as v1.4+ follow-up.

---

## v1.36 "OAuth Login"

### Theme
Enable Google, Apple, and GitHub sign-in. Supabase infrastructure from v1.33 already supports OAuth — this milestone is provider configuration, frontend buttons, and account-linking UX. The backend doesn't change (a JWT from Google OAuth is identical to one from email/password). GitHub can ship immediately (no LLC/developer account needed); Google and Apple ship when accounts are ready.

### Features

| Feature | Size | Description |
|---------|------|-------------|
| GitHub OAuth provider | S | Configure in Supabase dashboard. Create OAuth App in GitHub Developer Settings — free, no paid account, ~5 min. Can ship immediately. |
| Google OAuth provider | S | Configure in Supabase dashboard. Google Cloud Console: OAuth consent screen, client ID + secret, redirect URL. Blocked on LLC. |
| Apple OAuth provider | S | Configure in Supabase dashboard. Apple Developer: Services ID, domain verification, private key for client secret signing. Blocked on LLC + $99/yr membership. |
| OAuth buttons in AuthModal | S | "Continue with GitHub/Google/Apple" buttons above email/password form. Calls `supabase.auth.signInWithOAuth({ provider })`. |
| Apple display name capture | S | Apple only sends name on first sign-in. Capture from `user_metadata` during auto-provisioning and store in local profile. |
| Email-linking UX | S | When OAuth email matches existing email/password account, Supabase auto-links. Surface clear message to user. |

### Architecture Decisions

**Supabase PKCE by default.** `@supabase/supabase-js` v2+ uses PKCE (Proof Key for Code Exchange) automatically for OAuth. No custom implementation. Do not set `flowType: 'implicit'`.

**Zero backend changes for OAuth.** `get_current_user` validates Supabase JWTs regardless of auth method. OAuth users hit the same auto-provisioning path as email/password users.

### Security Requirements
- Verify PKCE is active (default in SDK v2+)
- Pin redirect URLs in Supabase dashboard — exact URLs only, no wildcards
- Google: verify domain ownership in Cloud Console, submit OAuth consent screen for verification before launch (100-user limit in testing mode)
- Apple: domain verification via Developer portal
- Apple refresh tokens can be user-revoked in Apple ID settings — handle gracefully (prompt re-auth)

### Files Changed

**Frontend (~30 lines):**
- `components/AuthModal.tsx` — add GitHub/Google/Apple OAuth buttons
- `hooks/useAuth.ts` — capture Apple display name from `user_metadata`

**Backend (minimal):**
- `monitor/db.py` — handle display name from `user_metadata` in auto-provisioning

**External config (not code):**
- Supabase dashboard: enable GitHub, Google + Apple providers
- GitHub Developer Settings: OAuth App (free, immediate)
- Google Cloud Console: OAuth consent screen, credentials
- Apple Developer: Services ID, private key

### Testing Strategy

**Automated (3 tests):**
- 3 frontend: OAuth buttons render and call `signInWithOAuth` with correct provider string
- 1 backend: Apple display name captured from `user_metadata` during provisioning

**Manual checklist (~20 min at ship time):**
1. Sign out, clear cookies → "Continue with GitHub" → complete flow → name in header
2. Create watch → sign out → GitHub sign-in → watch persists
3. Anonymous watch → GitHub sign-in → watch migrates
4. Repeat 1-3 with Google (when available)
5. Repeat 1-3 with Apple (when available)
6. Existing email/password user → OAuth sign-in with same email → accounts linked
7. Cancel OAuth mid-flow → returns to app cleanly

### Dependencies
- v1.33 shipped (Supabase auth working with email/password)
- GitHub: none (free, can ship immediately with v1.33)
- Google: LLC registered, Google Cloud project with OAuth consent screen verified
- Apple: LLC registered, Apple Developer account with active membership ($99/yr)

### Quality Bar
- OAuth login completes in <4 seconds
- Failed/cancelled OAuth returns to app without error screen
- Apple first-sign-in captures display name
- Email/password login still works alongside OAuth
- All v1.33 tests pass (zero backend auth changes)

### Key Risks

| Risk | Mitigation |
|------|------------|
| Google/Apple accounts not ready | Ship GitHub OAuth first (no blockers), add Google/Apple as accounts are set up — each provider is independent |
| Google consent screen in "testing" mode | Submit for verification before launch; requires privacy policy on campable.co |
| Apple only sends name once | Capture in auto-provisioning; fallback: user sets name in profile settings |

---

## v1.4 "Monetization Launch" [SHIPPED 2026-05-28]

### Theme
Turn traffic into revenue. v1.3's SEO pages bring organic visitors. v1.4 gates the pro features (watches, alerts, trips) behind a subscription and builds the conversion flows that move free users to paid. The v0.95 billing prototype on `feature/monetization` is preserved as a reference but will not be merged — v1.4 rebuilds against post-v1.33 Supabase auth and the post-v1.27/v1.29 design system. See Implementation Approach below.

### Implementation Approach
v0.95's full monetization layer was built on `feature/monetization` (March 2026) but never merged. Since then, v1.33 Supabase Auth and v1.27/v1.29 design system work have made the branch's auth integration and UI patterns obsolete. v1.4 will rebuild against current architecture with the branch as a reference implementation. Specifically: lift `billing.py` (Stripe SDK wrapper) and adapt to current style; rewrite all routes against the `routes/` subdirectory pattern; reuse schema column names + grandfather migration logic; rebuild frontend components against current `tokens.css`; write tests first for entitlement logic + billing math. The branch will be deleted post-ship.

### Features

| Feature | Size | Description |
|---------|------|-------------|
| Freemium gate activation | M | Enable the free/pro tier split. Free: search, discovery, campground profiles. Pro: watches (>3), alerts, trip planner, sharing. |
| Landing page | M | SEO-optimized homepage explaining what campable does, why it's different (multi-source aggregation), and the free → pro value ladder. |
| Upgrade flows from SEO pages | S | "Check Live Availability" and "Set up Alerts" CTAs on campground profiles that lead into the app (and prompt upgrade if needed). |
| Conversion analytics | S | PostHog funnel: SEO page → search → watch creation → upgrade. Measure what's working. |
| Pricing page | S | Clear free vs. pro comparison. Accessible, both themes. |

### Dependencies
- v1.36 shipped (auth solid with OAuth before gating features behind it)
- v1.3 shipped (organic traffic flowing)
- v0.95 billing reference (`feature/monetization` branch — Stripe SDK wiring and webhook handler proven, but adapted/rebuilt against post-v1.33 Supabase auth and post-v1.27/v1.29 design system; see Implementation Approach above)

### Quality Bar
- Upgrade flows never block free tier functionality
- Payment flow works on mobile
- Pricing page passes WCAG 2.1 AA
- Conversion funnel instrumented in PostHog

### Key Risk
Premature monetization — if v1.3 hasn't generated meaningful organic traffic, gating features could hurt growth. Monitor Search Console data from v1.3 before activating gates. Auth must be stable (v1.33/v1.36) before tying subscription state to user accounts.

### Post-ship Status (2026-05-28)

**Code complete + validated in Stripe test mode.** Six commits on `feat/v1.4-billing-foundation` shipped through `dev → main` in the order: roadmap reconciliation (slice 0) → schema + billing module + 31 tests (slice 1) → self-review fixes (slice 2.0) → HTTP routes + watch cap (slice 2 main) → frontend (slice 3) → planner gating + 5-min Pro polling (slice 4). Plus 6 follow-up PRs for production bugs surfaced during end-to-end validation. **1202 tests passing** across backend (999) + frontend (203).

**End-to-end test mode flow validated** in production browser (via Chrome DevTools MCP, 2026-05-28): test account signup → /pricing renders Upgrade button → Stripe Checkout completes with `4242 4242 4242 4242` → PRO badge appears → `/api/billing/status` returns `is_pro:true` → cancel at period end via Customer Portal → `subscription_expires_at` populates with period end → reactivate → expires_at cleared → re-cancel → expires_at re-populates.

**Five real bugs surfaced during validation** (all fixed):
1. `VITE_PUBLIC_SUPABASE_*` not forwarded to the deploy workflow's build step → production bundle baked in `localhost:54321` fallback → "Failed to fetch" on signup. Fix: PR #25/#26.
2. `SUPABASE_URL` Fly secret set without `https://` prefix → CSP `connect-src` malformed → blocked. Defensive fix: PR #35 added `_supabase_csp_origin()` that prepends scheme.
3. Modal drawer width media query missing `max-width: none` override → narrow viewports kept the desktop cap. Fix: PR #27/#28 (initial), #29/#30 (cascade specificity follow-up).
4. `useAuth` INITIAL_SESSION race condition → returning users stuck on "Loading…" forever. Fix: PR #31/#32 calls `getSession()` on mount explicitly.
5. Stripe API version `2026-03-25.dahlia` moved `current_period_end` from subscription root to `items.data[0]` → `subscription_expires_at` empty after cancel. Fix: PR #33/#34 added `_current_period_end()` helper checking both locations.

**Live mode activation — still operational/pending.** Currently running on Stripe test-mode keys. To start accepting real money:
- Replace `STRIPE_SECRET_KEY` with `sk_live_...` from Stripe Dashboard (live mode → Developers → API keys)
- Create a NEW webhook endpoint in live mode (Dashboard → Webhooks → Add endpoint, URL = `https://campable.co/api/billing/webhook`, same 4 event types as test mode) and replace `STRIPE_WEBHOOK_SECRET` with its `whsec_...`
- Create a live-mode price for "Campable Pro" at $5/mo and replace `STRIPE_PRO_PRICE_ID` with the new `price_live_...` ID
- Activate Stripe account in Dashboard: business verification (LLC docs, EIN), bank account for payouts, decide on tax (Stripe Tax at $0.50/transaction OR self-managed)
- Configure Customer Portal for live mode (Dashboard → Settings → Billing → Customer Portal): allow cancel, allow payment-method update; same config that already worked in test mode
- Optional: brief Terms of Service link in footer (Stripe flags missing terms on live-mode review for some accounts)

**Deferred (not blocking ship)**:
- Grandfather migration script for users with >3 watches at activation time — irrelevant pre-launch with no real users; a small one-shot if any real users land in this state post-launch
- Announcement email (per v0.95 spec, "one honest email about Pro")
- v1.41 Playwright E2E suite would have caught 4 of the 5 production bugs above with a single upgrade-flow smoke test (see v1.41 entry)

---

## v1.41 "Playwright E2E" [SHIPPED 2026-05-31]

### Theme
Stand up end-to-end browser test coverage that mirrors real production failure patterns, using Playwright. A single upgrade-flow smoke test would have caught 4 of the 5 bugs hit during v1.4 validation in seconds rather than hours.

Original v1.41 plan chose Maestro Web Beta for cognitive consistency with the Being mobile app. Phase 0 spike against `campable.co` (2026-05-29) validated framework capability — all interaction patterns work — but **each cross-origin Stripe iframe element lookup took ~14 minutes** in Maestro Web Beta 2.6.0. Full upgrade smoke would have run 90+ min/run. Unusable for CI gating. Pivoted to Playwright. Full post-mortem under Architecture Decisions below.

### Features

| Feature | Size | Description |
|---------|------|-------------|
| Playwright setup (self-hosted, free) | XS | `e2e/` directory at repo root with `package.json`, `playwright.config.ts`, shared fixtures. Runs via `@playwright/test` in GitHub Actions (uses existing CI minutes, $0/mo). |
| Flow 1 — Upgrade smoke test | M | Anonymous → signup → /pricing → Upgrade to Pro → Stripe Checkout with `4242 4242 4242 4242` → assert PRO badge in header. Single flow that would have caught the missing VITE_PUBLIC_SUPABASE env vars, the CSP scheme bug, the modal width regression, and the useAuth race. |
| Flow 2 — Watch limit smoke test | S | Free user → create 4th watch (3 seeded) → assert UpgradeModal opens with reason=watch_limit. Validates the 402 → modal flow. |
| Flow 3 — Planner limit smoke test | S | Free user → submit 4th planner prompt (3 sessions seeded this month) → assert UpgradeModal opens with reason=planner_limit. |
| Flow 4 — Cancel + reactivate | M | Pro user → Manage billing → Stripe Customer Portal → Cancel → assert `subscription_expires_at` rendered in BillingSettings → Reactivate → assert "Pro until X" text removed. Webhook → DB → UI loop validation. |
| Staging URL strategy | S | Fly preview branches per PR (auto-deployed, real DB, isolated) plus a long-lived `campnw-staging` app for nightly runs. Tests never hit `campable.co` production. |
| Fixture seeding script | S | `scripts/seed_e2e_fixtures.py` creates 3 fixture users idempotently via Supabase Admin API + SQLite UPSERT. Runs in CI via `flyctl ssh console`. |
| Email confirmation off in prod Supabase | XS | Already configured (verified during Phase 0 spike). Saved to memory so future sessions don't propose email-verification waits. |
| CI integration | S | GitHub Actions job (`playwright.yml`) installs Playwright + Chromium and runs the smoke flow on every PR (~60s), nightly cron for all flows. Failures upload Playwright HTML report + trace as artifact. |

### Architecture Decisions

**Playwright after Maestro Web Beta failed Phase 0 perf bar.** Phase 0 spike (2026-05-29) against `campable.co` confirmed Maestro Web 2.6.0 _can_ drive the full flow (signup, tap-then-inputText for React-controlled inputs, onboarding modal skip via `runFlow: when:`, cross-origin Stripe iframe pierce). The fatal finding from `~/.maestro/tests/2026-05-29_130340/maestro.log`: every iframe element lookup took **~14 minutes** (visible in the gap between RUNNING and "Refreshed element" log lines). A complete upgrade flow would have run 90+ min/run — unusable for CI smoke gates. Playwright's `frameLocator` handles cross-origin iframes in <5s. Cognitive-consistency-with-Being argument loses when web tests need a separate tool anyway. **Follow-up:** file upstream perf issue at github.com/mobile-dev-inc/maestro with the log timestamps.

**Self-hosted (GitHub Actions), not a paid runner.** $0/mo until revenue justifies otherwise. GitHub Actions already runs Campable's other CI (test, security, lighthouse, bundle-size); adding a Playwright job uses the same already-paid-for minutes.

**Staging environment, not production.** Tests like "cancel subscription" pollute metrics and burn test users when run against prod. Fly preview deployments per PR (ephemeral URL, isolated DB, isolated Stripe test keys). Auto-suspend on idle = $0/mo standing cost.

**Test mode Stripe keys only.** E2E never touches live-mode Stripe. The `4242 4242 4242 4242` test card is fast, deterministic, and free.

**`data-testid` selectively, not blanket.** Only on form inputs where the visible-text/label selectors are unreliable for automation (`email-input`, `password-input`, `display-name-input` in AuthModal). Everything else uses visible text + role + CSS class. Keeps production code clean.

**Fixture seeding via Python, not SQL.** Supabase auth user creation requires HTTP Admin API calls — pure SQL can't do that. `scripts/seed_e2e_fixtures.py` does both layers (HTTP for auth, SQLite for app).

### Files Changed

**New:**
- `e2e/package.json` — Playwright deps only (separate from `web/`)
- `e2e/playwright.config.ts` — base URL via `E2E_BASE_URL` env, retries, traces, reporter
- `e2e/tsconfig.json` — standalone TS config
- `e2e/fixtures/auth.ts` — `signupFresh()`, `loginAsFixture()`, `skipOnboarding()`
- `e2e/fixtures/stripe.ts` — `payWithCard()`, `waitForProBadge()`
- `e2e/tests/upgrade.spec.ts` — Flow 1
- `e2e/tests/watch-limit.spec.ts` — Flow 2
- `e2e/tests/planner-limit.spec.ts` — Flow 3
- `e2e/tests/cancel-reactivate.spec.ts` — Flow 4
- `e2e/.gitignore` — ignore reports + trace artifacts
- `.github/workflows/playwright.yml` — CI integration
- `scripts/seed_e2e_fixtures.py` — fixture user seeding (Supabase Admin API + SQLite)

**Modified:**
- `web/src/components/AuthModal.tsx` — `data-testid` on email/password/display-name inputs

**External config:**
- Long-lived `campnw-staging` Fly app for nightly runs (TODO: create)
- Stripe test-mode keys reused from v1.4
- Repo secrets: `E2E_FIXTURE_PASSWORD`, `SUPABASE_SERVICE_ROLE_KEY`

### Quality Bar

- Smoke test (Flow 1) runs in **< 60s** end-to-end (realistic with Playwright; was <90s with Maestro)
- All four flows pass on `dev` HEAD
- CI failure uploads the Playwright HTML report + trace as a GitHub Actions artifact (interactive trace viewer makes failures self-diagnosable)
- Flow 1 generates a fresh randomly-emailed user per run; Flows 2-4 use idempotent fixtures
- **Monthly infrastructure cost: $0** (GitHub Actions free minutes + Fly preview branches auto-suspend)

### Dependencies

- v1.4 shipped (we're testing v1.4's flows)
- Fly preview deployments enabled (configuration on the Fly side)
- Email confirmation off in prod Supabase (already verified during Phase 0)

### Key Risks

| Risk | Mitigation |
|------|------------|
| Stripe Checkout UI changes | Stripe's Checkout UI is stable across years but does occasionally rev (modern variant now wraps the card form inside a "Card" radio under payment-method tabs — discovered during Phase 0 spike and handled in `fixtures/stripe.ts`). If a flow breaks, fix that single fixture — don't add wrapper layers that "future-proof" against hypothetical changes. |
| Fixture user drift if schema changes | `scripts/seed_e2e_fixtures.py` is idempotent and re-runnable. Schema changes invalidate fixtures; rerun seed = fixed. |
| Test account email collision | Flow 1 uses `e2e-fresh-{timestamp}-{random}@maestro.test` per run. Flows 2-4 use stable fixtures named by purpose. |
| Live-mode bugs missed by test-mode tests | Test mode covers ~95% of real flows. Risks not covered: real fraud detection, real bank decline codes, real refund processing. Need a manual smoke when first live transaction goes through. |
| Maestro Web perf regression doesn't affect Playwright | Playwright's iframe handling is mature and used by thousands of projects — not at risk of the same beta perf trap. |

### What v1.41 catches that v1.4's 1202 tests don't

The unit tests we added in v1.4 lock in code behavior. They CAN'T catch:
- Build-time env var omissions (VITE_PUBLIC_* bug)
- CSP construction at the middleware layer with real Supabase domain
- React effect timing bugs in production (useAuth race surfaced from live network behavior)
- CSS specificity bugs across responsive breakpoints
- Cross-tab Supabase session sync
- Real Stripe Checkout iframe behavior
- Webhook delivery from real Stripe in real network conditions

That's the gap v1.41 fills. Five real bugs from v1.4 validation map directly to flows here.

---

## v1.42 "Site Polish + Legal Footing" [SHIPPED 2026-05-31]

### Theme
Add the site pages v1.4 deferred and that v1.45 (Apple App Store) will require regardless. Privacy Policy + Terms unblock Stripe live-mode review. About + Contact give trust signals that convert fence-sitters on /pricing. Footer ties everything together. ~1-2 days of focused work; the legal text comes from a generator (Termly or similar) and the user customizes the specifics, so most of the effort is page structure + content writing, not legal drafting.

### Post-ship Status (2026-05-31)

**Shipped and deployed.** Three PRs through `feat/chore` → `dev` → `main` release: PR #54 (legal pages + footer + routes + tests), PR #55 (copy pass removing em-dashes and AI-pattern tells from About, Privacy, Terms), PR #56 (support email swap to `hello@campable.co`). Release PR #57 merged into `main` at `4a6352e` triggering Fly deploy. Verified post-deploy: `/privacy`, `/terms`, `/about` all return 200; bundle hash flipped (`index-DMMAvE1u.js` → `index-BpX3omL_.js`); `hello@campable.co` and `site-footer` class present in the served bundle.

**Decisions that diverged from the original entry:**
- Hand-written legal text instead of Termly. Voice consistency with About/Pricing wins; honest disclosure of actual services (Supabase, Stripe, PostHog, Mapbox, Visual Crossing, Cloudflare, Fly) is more legally defensible than boilerplate "service providers" language.
- No version string in the footer. `package.json` is `0.0.0` and the site is continuously deployed; the number would be noise.
- Cloudflare RUM disabled in CF dashboard during this ship since PostHog already captures Core Web Vitals. Removes a beacon the operator wasn't reading and keeps the Privacy disclosure clean (Cloudflare's only listed role is now DNS + TLS).
- About page was already shipped early (commit `1cd555a`); v1.42 added its missing contact mailto during the copy pass.

**One real bug surfaced and fixed during self-review:** original Privacy draft claimed Google/Apple OAuth, but `useAuth.ts:107` only wires `signInWithPassword` (v1.36 OAuth not yet shipped). Removed the false claim before merge.

**Out-of-code follow-ups (operator-side):**
- Stripe Dashboard → Settings → Business → Public details: paste `https://campable.co/privacy` + `/terms`, set support email to `hello@campable.co`, support URL `https://campable.co/about`
- Stripe Dashboard → Settings → Billing → Customer Portal: add Privacy + Terms URLs
- Test that `hello@campable.co` actually delivers (send from outside, confirm receipt)
- Stripe live-mode activation (still test-mode keys per v1.4 post-ship notes) when ready to accept real money

Sequencing: realistically wants to happen before live Stripe mode activates (Stripe flags missing Privacy/ToS on subscription products) and before v1.45 (Apple requires a Privacy Policy URL at submission). Can be done in parallel with v1.41 since they touch different surfaces.

### Features

| Feature | Size | Description |
|---------|------|-------------|
| About page (/about) | M | _Shipped early, ahead of v1.42._ Honest first-person voice matching the Pricing page. Covers: what Campable does, why it exists, who's behind it, how it's funded, where data comes from, what's coming. Trust signal for fence-sitters on /pricing. |
| Privacy Policy (/privacy) | S | Hand-written in Campable voice. See Architecture Decisions for why Termly was rejected. Honest disclosure of every third party that touches user data (Supabase, Stripe, PostHog, Mapbox, Visual Crossing, Cloudflare, Fly), retention policy, and GDPR/CCPA rights. |
| Terms of Service (/terms) | S | Hand-written. $5/mo subscription terms, explicit 30-day refund policy (per Stripe's preference), liability limit, governing law (Washington), right to terminate abusive accounts. Linked from /pricing. |
| Footer component | S | New `<Footer>` rendered site-wide outside `<Routes>`. Links: About, Pricing, Privacy, Terms, Contact (mailto). © year only. Version dropped because package.json is 0.0.0 and the site is continuously deployed. |
| Contact email | XS | `hello@campable.co` mailto in footer and on About/Privacy/Terms contact sections. |
| Stripe Business profile config | XS | Paste Privacy + ToS URLs into Stripe Dashboard → Settings → Public details. Required for live-mode review. |
| Stripe Customer Portal links | XS | Customer Portal config page → add Terms + Privacy URLs so the cancel/manage flow shows them. |
| Apple App Store URL prep | XS | Confirm /privacy URL renders in Helmet meta + is reachable for Apple's submission crawler. (v1.45 will actually submit; v1.42 just has the URL ready.) |

### Architecture Decisions

**Generator over hand-rolled legal text.** Termly (or similar) generates compliant baselines that update as regulations change. For a $5/mo solo SaaS, this is the right cost/risk balance — pay a lawyer when you have 100 paying customers, not 1. Customize the generator output for the parts specific to Campable (third-party services list, retention windows, jurisdiction), don't write from scratch.

**Footer as a global component.** Rendered in `main.tsx` or App.tsx outside `<Routes>` so it appears on every page including /pricing, /trips, /plan, and the legal pages themselves. No per-route opt-out.

**Voice continues from Pricing page.** Honest, direct, no marketing puffery. "Built by one person" angle works because it's true. Conversion lift comes from credibility, not slickness.

**Defer cookie banner.** EU PostHog tracking technically needs a banner for GDPR consent, but enforcement against small US SaaS is near-zero and the UX cost is real. Document the deferral here so we revisit when EU traffic > 5% of total (measured via PostHog).

### Files Changed

**New frontend:**
- `web/src/pages/About.tsx` — written from scratch matching Pricing voice
- `web/src/pages/Privacy.tsx` — Termly-generated text in React component shell
- `web/src/pages/Terms.tsx` — same pattern
- `web/src/components/Footer.tsx` — global footer
- `web/src/App.css` — `.about-page`, `.legal-page`, `.site-footer` styles

**Modified frontend:**
- `web/src/App.tsx` — register /about, /privacy, /terms routes; render <Footer/> outside Routes
- `web/src/main.tsx` — possibly footer mount if not in App.tsx

**Non-code:**
- Stripe Dashboard → Settings → Public details (paste URLs)
- Stripe Dashboard → Settings → Billing → Customer Portal (paste URLs)
- Optional: support@campable.co email forwarding setup (Fastmail / Google Workspace / Cloudflare Email Routing)

### Testing Strategy

**Automated (Vitest):**
- About / Privacy / Terms components render with correct headings
- Footer renders all expected links and the year matches current
- Routes resolve and lazy-load

**Manual (~10 min):**
- Smoke test all 4 pages in both themes (dark + light)
- Lighthouse a11y pass on each
- Confirm WCAG 2.1 AA contrast on legal text (often a sneaky regression)
- Confirm Privacy URL is reachable from a fresh browser session (no auth wall)

### Dependencies

- v1.4 shipped (we have a real product and billing flow to legally cover)
- Termly account (free tier sufficient) OR equivalent generator
- Decision on support email address

### Quality Bar

- All pages WCAG 2.1 AA
- Mobile-responsive at 375px viewport
- Privacy Policy URL added to Stripe Business profile
- Privacy Policy URL added to Customer Portal links
- Privacy Policy honestly discloses each third-party service that handles user data
- No marketing copy lifted from generic templates ("we are committed to your privacy" etc.) — keep the Campable voice

### Key Risks

| Risk | Mitigation |
|------|------------|
| Templates miss state-specific nuance | Templates are deliberately generic. For higher-revenue future state (>$10K/mo) consider a brief lawyer review specific to WA LLC operations |
| Cookie banner deferral risk if EU traffic grows | Measure EU traffic in PostHog quarterly; banner becomes priority if EU > 5% |
| About-page voice drifts into marketing | Have the user read it back as if they were a skeptical Hacker News commenter before merging |
| Privacy Policy gets stale as third parties change | Re-audit annually OR when adding any new third-party service; Termly handles regulatory drift but not service-list updates |
| Stripe Business profile review timing | Live mode activation may stall if the profile review is slow. Submit Privacy + ToS URLs ASAP after v1.42 deploys, even if not yet ready to flip live keys |

---

## v1.45 "Native Apps" [PARTIAL — internal iOS TestFlight SHIPPED 2026-06-14]

### Theme
Wrap the existing React app in a Capacitor shell and ship to the iOS App Store and Google Play Store. Capacitor lets us keep the entire web codebase as the UI layer while adding native capabilities (APNs/FCM push, GPS, offline registry) that satisfy Apple's "Minimum Functionality" guideline (4.2) and make the app actually useful at the campground — where users frequently have no cell signal. This is not a port; it's a thin native shell + native plugins + a re-architected data layer that respects three different freshness models (registry = local, watches = local-with-sync, availability = online-only). Slotted after v1.4 so the monetization model is validated on the web (cheap iteration) before committing to App Store review cycles.

The Features table below is the **eventual full target** (App Store + Play Store, push, offline, IAP-free monetization). The first executable slice is much smaller and is scoped under "First Milestone" immediately below.

---

### First Milestone — Internal TestFlight (iOS only, Option A) [SHIPPED 2026-06-14]

**Goal:** Get a bundled iOS build of Campable onto a real iPhone via **internal** TestFlight (≤100 of our own testers, **no App Review**). Validates the toolchain and the web-in-WebView port without solving monetization, push, or offline.

**Achieved 2026-06-14.** Build 1.0 (1), bundle id `co.campable.app`, uploaded and installed on a real iPhone via TestFlight internal testing. Gauntlet along the way: Capacitor 8 SPM scaffold, CORS for `capacitor://localhost`, the `API_BASE`/Supabase-storage/SW/billing native gates, two CI fixes (api.ts chunk split + PyJWT/npm CVE cleanup), the iOS safe-area top inset (`ios.contentInset: "always"`; scroll-bleed parked as a documented follow-up), recurring SPM-artifact resolution, device registration for signing, and cross-Apple-ID tester setup (developer account signs; personal Apple ID installs via TestFlight after being added under Users and Access). `DEVELOPMENT_TEAM` (KN6FDLG98K) committed to the Xcode project so future builds auto-sign.

**Decisions (locked 2026-06-07):**
- **Option A — no In-App Purchase.** Apple requires StoreKit IAP for digital subs sold *inside* the app and takes 15–30%. The app sells nothing; Pro features show "manage your subscription at campable.co" (opens system browser via `@capacitor/browser`). Sidesteps IAP integration + the biggest review-rejection risk. Internal TestFlight has no review, so anti-steering rules don't bite at this stage.
- **Internal TestFlight only.** External testers require Beta App Review (≈ full review); deferred. App Store submission deferred.
- **Bundled assets, not `server.url`.** Load the Vite build from the local bundle (`capacitor://localhost`). A one-time `server.url=https://campable.co` boot is allowed only as a 5-minute simulator sanity check, never shipped.

**Why the port is small (grounded in current code, 2026-06-07):**
- **CSP is HTTP-header-only** (no `<meta>` CSP in `web/index.html`) → the bundled app loads `index.html` as a local file with no server headers → **no CSP origin allowlist work needed** in the native context. Web header-based CSP is untouched.
- **`API_BASE` seam already exists** (`web/src/api.ts:3`: `import.meta.env.DEV ? "http://localhost:8000" : ""`). Every call routes through `${API_BASE}/api/...`, so making native calls absolute is a one-line branch → `https://campable.co`.
- **Apple's hard gates are already done:** `DELETE /api/auth/me` exists (`routes/auth.py:106`) and is surfaced in `UserMenu` (5.1.1(v) account deletion ✅); Privacy Policy URL shipped v1.42 (`campable.co/privacy` ✅); `Authorization: Bearer` already sent (`api.ts:26`, v1.33 groundwork ✅).

**Change-list:**

| Area | Change | File |
|------|--------|------|
| Backend | Add `capacitor://localhost` to CORS allowlist (explicit list required — `allow_credentials=True` forbids `*`). Small PR → dev → main. | `src/pnw_campsites/api.py` (`_cors_origins`) |
| Frontend | `API_BASE` gains a native branch → `https://campable.co` (via `Capacitor.isNativePlatform()` / `VITE_NATIVE` flag) | `web/src/api.ts:3` |
| Frontend | Supabase client `storage` adapter → `@capacitor/preferences` (web falls back to localStorage). Prevents WKWebView storage-pressure logout. | `web/src/lib/supabase.ts:8` |
| Frontend | Gate `serviceWorker.register` behind `!isNativePlatform()` | `web/src/main.tsx:35` |
| Frontend | Native upgrade CTA → "Manage at campable.co", opens system browser. This *is* Option A. | Pricing / upgrade UI |
| Native | Capacitor scaffold (`@capacitor/core`, `cli`, `ios`), `cap add ios`, config, `@capacitor/assets` icons/splash from 1024² Madrona source, `Info.plist` `ITSAppUsesNonExemptEncryption=false` | new `ios/`, `capacitor.config.ts` |

All frontend changes are **additive and native-gated** — the web bundle is byte-identical on web, so they can ship to dev/main safely before the app exists.

**Execution sequence (isolates the one scary unknown — Apple signing):**
1. **Simulator** (no signing, free): scaffold + bundle → run in iOS Simulator. Catches all web-in-WebView issues (CORS, API base, auth, Leaflet/Mapbox) with zero Apple variables. Optional 5-min `server.url` control boot first.
2. **Tethered device** (first signing): run on a real iPhone via Xcode automatic signing. Adds only the dev-cert/provisioning variable.
3. **Archive → upload → internal TestFlight** (full pipeline): distribution signing, App Store Connect record, upload, processing, install. Highest first-timer variance — budget a full day for Xcode/provisioning friction.

**Bundle ID:** `co.campable.app` (reverse-DNS of `campable.co`, matching the sibling Being app's `fyi.being.app` convention — domain-namespaced per product, not entity-namespaced). **Permanent once the App Store Connect record is created.**

**Risks:**
1. Apple toolchain (signing/provisioning/upload) — not code, pure first-timer friction. Mitigated by the simulator→device→TestFlight progression.
2. Anonymous watch-migration cookie (`credentials:"include"` + `campnw_session`) won't cross from `capacitor://localhost` to campable.co (WKWebView blocks third-party cookies). Non-issue for an internal, signed-in tester; revisit for public.
3. JWT localStorage purge — mitigated by the `@capacitor/preferences` swap.

**Deferred (NOT needed for internal TestFlight):** push notifications (APNs / `device_push_tokens` — biggest deferred chunk), universal/deep links, bundled offline registry, native geolocation, Android, IAP (Option A = none), external TestFlight + Beta App Review, full App Privacy nutrition labels (minimal section filled to upload; comprehensive labels wait for public).

**Known issue (follow-up, non-blocking):** `ios.contentInset: "always"` fixes the at-rest top inset (header clears the status bar / Dynamic Island), but on scroll, content still bleeds slightly behind the status bar strip. `env(safe-area-inset-*)` only reports non-zero with `contentInset` set, and a CSS mask / sticky-header attempt collided with the header's z-index. Cosmetic only — does not block internal TestFlight. Revisit with the `@capacitor/status-bar` overlay API (or Capacitor's newer core `SystemBars.setOverlay`, not yet in 8.4.0) for a clean non-overlapping status bar.

**Prereqs:** Xcode installed, a physical iPhone, Apple Developer account (✅ approved 2026-06-07). **Estimate:** 2–3 focused days, variance entirely in step 3.

---

### Features

| Feature | Size | Description |
|---------|------|-------------|
| Capacitor scaffolding | M | `npx cap init` + `cap add ios` + `cap add android`. Vite production build bundled into `ios/App/App/public/` and `android/app/src/main/assets/public/` on each release. Web build pipeline unchanged. |
| Native push notifications | L | Swap VAPID/Service Worker push (web) for `@capacitor/push-notifications`. APNs (iOS) + FCM (Android). New `device_push_tokens` table (`user_id`, `platform`, `token`, `created_at`). Server-side router picks transport per token type. Keep existing web push pipeline for browser users. |
| Native geolocation | S | `@capacitor/geolocation` for true GPS-based "campgrounds near me" search. Falls back to existing IP geolocation if permission denied. Permission prompt copy reviewed for App Store. |
| Bundled registry snapshot | M | `assets/registry.db` shipped in the IPA/APK (~2-5MB). Capacitor SQLite plugin for read-only access. Refresh on app launch when online via existing registry export endpoint. Enables offline search by name, region, distance from current location. |
| Local watch state | M | Mirror user's watches to local SQLite via Capacitor SQLite. Sync to backend on app foreground. Conflict resolution: last-write-wins for v1, server is source of truth. Availability data still fetched live. |
| Auth Bearer migration completion | S | Verify all `/api/*` callsites use `Authorization: Bearer` (groundwork from v1.33). Store JWT in `@capacitor/preferences`, not `localStorage` (WKWebView purges localStorage under storage pressure). |
| Service worker gating | S | Wrap `/sw.js` registration in `!Capacitor.isNativePlatform()`. SWs are flaky in WKWebView and redundant once native push is wired. |
| Universal Links / App Links | S | Serve `apple-app-site-association` and `assetlinks.json` from Fly. Map existing share URLs (`/trip/:id`, `/campground/:slug`) to native deep links. |
| In-app account deletion | S | Apple Guideline 5.1.1(v) requirement. Wire Supabase user deletion to `UserMenu` settings. Check if `DELETE /api/auth/me` already exists from v1.33; surface in UI if not. |
| Native share sheet | S | `@capacitor/share` for trip/campground sharing. Replaces web `navigator.share` fallback. |
| App icons + splash screens | S | Generate all iOS sizes (App Store, Spotlight, Settings) + Android adaptive icon + splash screens from Madrona brand assets. Tool: `@capacitor/assets`. |
| App Store / Play Store metadata | M | Screenshots (6.7", 6.9", iPad, Android phone, Android tablet), descriptions, keywords, privacy policy URLs, age rating, privacy nutrition labels (PostHog, Sentry, Mapbox, Visual Crossing declared). |
| Sentry crash reporting | S | `@sentry/capacitor` for native + WebView crash traces. PostHog alone misses WKWebView crashes and Capacitor plugin failures. |
| CI/CD via Xcode Cloud + Play Console | M | Xcode Cloud workflow building from `main` on push (25 free build-hrs/mo, native TestFlight delivery). Play Console internal testing track for Android. No Fastlane unless we outgrow it. |

### Architecture Decisions

**Capacitor over React Native rewrite.** RN would mean rewriting the entire React 19 + Vite + Leaflet + Supabase + PostHog frontend. Capacitor keeps the existing codebase as a WKWebView (iOS) / WebView (Android) bundle, with native plugins for the 5-10% of functionality that needs native APIs. Loss: ~5% UX polish vs RN. Gain: weeks vs months, single codebase, web and native ship from the same React PRs forever.

**Offline-aware per data layer, not offline-first uniformly.** Three data types, three policies: (1) Registry metadata bundled in the IPA, refreshed on launch — works offline because the snapshot is local. (2) Watches in local SQLite, synced to backend on foreground — works offline because reads/writes are local. (3) Availability online-only with "last checked Xm ago" timestamps — caching real-time data would lie to users. This is the right shape for "used at the campground with no signal" without overengineering.

**Dual push transport, not migration.** Keep web push (VAPID + SW) for browser users; add native push (APNs/FCM) for app users. `device_push_tokens` table sits alongside `push_subscriptions`. Server-side dispatcher picks per token. Web users don't lose anything; native users get native UX.

**Xcode Cloud over Fastlane.** Solo dev, new Apple account, no need for Ruby toolchain or `match` certificate management. Xcode Cloud's automatic signing + native TestFlight delivery is the simpler path. Revisit if we need cross-CI parity or non-Apple infrastructure access during builds.

**Ship Android two weeks before iOS.** Play Store review is hours (not days); $25 one-time vs $99/year; Capacitor's Android story is more forgiving. Finding bugs on Android first means we don't burn App Store review cycles on issues we could've caught for free.

### Security Requirements

- APNs `.p8` key + FCM service account JSON in Fly secrets only — never in repo
- App Transport Security: no exceptions needed (Fly serves valid TLS 1.2+)
- Pin `apple-app-site-association` paths to known routes only — no wildcards
- JWT in `@capacitor/preferences` (encrypted on device) — not `localStorage`
- Universal Link payloads validated server-side — never trust deep link query params for state mutations
- Privacy nutrition labels honest about PostHog (analytics), Sentry (diagnostics), Mapbox (location), Visual Crossing (none — server-side only)
- Account deletion path (Apple 5.1.1(v)) tested end-to-end before submission

### Files Changed

**Backend (~120 lines added):**
- `monitor/db.py` — new `device_push_tokens` table + indexes; migration script
- `routes/push.py` — new `POST /api/push/device-token` for native token registration; dispatcher logic to route per transport type
- `routes/auth.py` — verify `DELETE /api/auth/me` exists and surface in spec; add Supabase admin client call if missing
- `routes/registry.py` (new or extended) — `GET /api/registry/snapshot` returning the full 1,370-row registry as a downloadable SQLite blob for native sync
- `api.py` — serve `apple-app-site-association` (Content-Type: application/json, no extension) and `assetlinks.json`
- Push sender modules — add APNs HTTP/2 + FCM HTTP v1 senders alongside existing web push

**Frontend (~200 lines added/changed):**
- `main.tsx` — gate SW registration on `!Capacitor.isNativePlatform()`
- `hooks/usePushNotifications.ts` — branch on platform: web push (existing) or `@capacitor/push-notifications` (new)
- `hooks/useGeolocation.ts` (new) — native GPS with web fallback
- `hooks/useLocalRegistry.ts` (new) — read from bundled SQLite on native, from API on web
- `lib/storage.ts` (new) — abstract `localStorage` ↔ `@capacitor/preferences` per platform
- `lib/api.ts` — read JWT from new storage abstraction
- `App.tsx` — handle deep link routes from `@capacitor/app` URL open events
- `components/ShareButton.tsx` — prefer `@capacitor/share` when native
- `components/UserMenu.tsx` — wire account deletion if not already present

**Native (new directories):**
- `ios/` — Xcode workspace, generated by Capacitor, committed to repo
- `android/` — Gradle project, generated by Capacitor, committed to repo
- `ios/App/App/public/.well-known/` — AASA delivery as a build artifact (alternatively served from Fly)
- `capacitor.config.ts` — app ID (`co.campable.app`), bundle settings, plugin config

**Ops / external (not code):**
- Apple Developer account ($99/yr)
- Google Play Developer account ($25 one-time)
- APNs `.p8` auth key generated in Apple Developer portal
- Firebase project + FCM service account
- App Store Connect listing (screenshots, description, keywords, privacy)
- Google Play Console listing (same)
- Xcode Cloud workflow connected to repo
- Sentry project with iOS + Android DSNs in Fly secrets

### Testing Strategy

**Automated (~25 tests):**
- 8 backend: `device_push_tokens` CRUD, dispatcher routing (APNs vs FCM vs web push), token deduplication, account deletion cascade
- 5 frontend: storage abstraction (native vs web branch), geolocation hook fallback, deep link routing
- 5 frontend: registry snapshot loader (cache hit, cache miss, stale data, refresh on foreground)
- 4 frontend: watch sync (online write, offline write, foreground sync, conflict resolution)
- 3 integration: Capacitor plugin mocks render correctly in Vitest

**Manual checklist (~2 hrs at ship time):**
1. Install on physical iPhone via TestFlight → grant push + location permissions → receive test notification
2. Same for Android via Play Store internal track
3. Airplane mode → open app → registry browsable, watches visible, availability shows "offline" state
4. Universal link: tap shared trip URL in iMessage → opens directly in app, not Safari
5. Account creation → delete account from in-app settings → verify Supabase user gone
6. Cold launch in <2s on iPhone 12 / Pixel 6 baseline
7. Push notification tapped → app opens to the correct campground
8. Sign out → sign in with email → watches persist
9. App Store screenshots accurately reflect current UI
10. Crash test: force a JS error → verify Sentry receives it with native context

### Dependencies

- v1.33 shipped (Supabase auth with Bearer token foundation)
- v1.36 shipped (stable OAuth for native sign-in flows)
- v1.4 shipped (monetization model validated on web before committing to App Store review cycles)
- Apple Developer account approved + active
- Google Play Developer account active
- LLC registered (required for Apple business listing)
- APNs `.p8` key generated
- Firebase / FCM project set up
- Decision on map tile strategy (online-only with messaging vs MapLibre + MBTiles bundled) — see Risks

### Quality Bar

- App launches cold in <2s on baseline devices (iPhone 12, Pixel 6)
- Search results render from local registry in <100ms when offline
- Native push notifications deliver within 30s of trigger (matches web push SLA)
- Universal Links open the correct screen 100% of the time
- App passes WCAG 2.1 AA (inherited from web — verify in WebView context)
- No JavaScript errors in Sentry across a 7-day TestFlight cohort before App Store submission
- iOS + Android version numbers stay in lockstep with web `package.json`
- Account deletion verifiable in Supabase dashboard
- Zero P0/P1 bugs in TestFlight internal testing before external review

### Key Risks

| Risk | Mitigation |
|------|------------|
| Web Push (VAPID/SW) doesn't work in WKWebView — existing push pipeline is dead on native | Plan APNs/FCM swap as v1.0 critical path, not a follow-on. Build server-side dispatcher to route per transport, keep web push working for browser users. |
| First TestFlight review takes 2-7 days; rejections add another cycle | Front-load Apple's known scrutiny areas: privacy nutrition labels, account deletion, push permission copy, location justification string. Ship Android first to find non-Apple bugs cheaply. |
| Map tiles unusable offline — Leaflet renders grey squares at the trailhead | Decide v1: ship online-only maps with explicit "connect to load map" empty state, OR migrate Leaflet → MapLibre with MBTiles bundle (~30-50MB for PNW region). Don't silently defer — users will tap and be confused. |
| iOS WKWebView purges localStorage under storage pressure | Migrate all critical state (JWT, watch cache, user prefs) to `@capacitor/preferences` before TestFlight. UI-only state can stay in localStorage. |
| Apple 4.2 rejection ("repackaged website") | The bundled registry + native push + native geolocation + native share sheet + in-app account deletion is comfortably over the 4.2 bar in 2026. Risk is low IF we ship all four; high if we cut any to save time. |
| Capacitor + Vite build pipeline drift over time | Lock Capacitor major version. Run `npx cap sync` in CI on every PR touching `web/`. Document in CLAUDE.md. |
| In-app purchases not part of v1.45 scope | Subscription billing stays web-only at v1.45. Native IAP is a v1.5+ decision — Apple takes 15-30% revenue share and adds complex receipt validation. Defer until web monetization metrics justify it. |
| Realistic timeline: 4-6 weeks calendar for solo dev new to Capacitor | Don't promise dates externally until first TestFlight build is in Apple's hands. Screenshots/metadata always take longer than estimated. |

---

## v2.0 "Predictions+" (~Q1 2027, needs 9-12 months of polling data)

### Theme
The intelligence layer. By Q1 2027, there will be 9-12 months of polling data. v1.2's historical pattern extraction has validated data quality. The statistical model, anomaly detection, and post-mortems all ship together because they share the same data pipeline. This is the premium differentiator that justifies ongoing Pro subscriptions.

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
- v1.26 shipped (history compaction fixes storage model that feeds predictions)
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
| v1.3 | SEO templates meet Level AA. Campground profiles have proper heading hierarchy and landmarks. |
| v1.4 | Pricing page and upgrade flows pass Level AA. Payment flow accessible on mobile. |
| v2.0 | Prediction displays pass contrast on both themes. Confidence indicators accessible. |

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
| v1.3 | SEO pages load under 500ms. Cloudflare cache hit ratio >80% for profile pages. |
| v1.4 | Upgrade flows add no latency to free tier. Landing page Lighthouse performance green. |
| v2.0 | Prediction queries add <200ms to page load. |

### Data Collection (start at v0.5, use at v2.0)
The `availability_history` table ships silently in v0.5 alongside background polling. Every poll cycle writes a row. v1.2's Historical Pattern Extraction (C2) validates data quality at ~6 months. By v2.0 (~Q1 2027), there should be 9–12 months of data — strictly better for prediction quality than the original v0.9 target.

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

## What's Explicitly Post-v2.0

- **Idaho State Parks** (Brandt/Idaho Time at getoutside.idaho.gov — behind AWS WAF with mandatory visual CAPTCHA, would need paid CAPTCHA-solving service; ~20 state parks, low demand. Probed March 2026.)
- **BC Parks (Canada)** (revisit based on demand signals from B1 analytics digest)
- **Native mobile apps** (web-first is right for this scale)
- **Booking intermediation** (legal complexity, misaligned with the tool's positioning)
- **User reviews and photo uploads** (community features need critical mass)
- **Cell coverage overlay** (crowdsourced data is hard to bootstrap)

---

## AI Feature Backlog (Evaluated)

Features brainstormed and scored during the March 2026 AI feature review. Re-evaluated post-v1.0 and slotted into v1.1-v2.0 where appropriate. See also: `docs/AI-OPPORTUNITIES-2026-03-28.md` for the full analysis and `docs/REQUIREMENTS-v1.1-v1.2.md` for detailed acceptance criteria.

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
| Anomaly Narrator | v2.0 | B3 |
| "Why Did I Miss It?" Post-Mortem | v2.0 | A4 |

### Deferred (revisit when conditions change)

| Feature | Description | Why Not Now |
|---------|-------------|-------------|
| **Shoulder season finder** | Identify "best value" booking windows per campground from multi-season availability data. | Needs 12+ months of polling data. Revisit after v2.0 prediction model ships. |
| **Trip compatibility scorer** | Score campgrounds on fit for a specific trip. | Largely redundant with trip planner conversational reasoning. |
| **Availability narrative digest** | Weekly "campsite weather report" email. | Engagement pattern doesn't match episodic tool usage. Anomaly alerts (v2.0) fire at the right moment instead. |
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
| Restructure post-v1.0 into v1.1/v1.2/v2.0 | Predictions+ needs 9-12 months of polling data (collection started March 2026). Jumping straight to predictions leaves a ~9-month gap. v1.1 (AI search + registry quality) and v1.2 (trips + watches) fill the gap with user value while data matures. v1.3/v1.4 added April 2026 to transition from personal tool to public product (SEO + monetization). | Ship nothing, wait for data — rejected because momentum matters for personal projects and registry quality improvements have immediate payoff. |
| NL search in v1.1, reversing v0.6 deferral | Originally scored "low innovation/low impact" in March 2026 AI review. Re-evaluated: trip planner proves the Haiku tool_use pattern works, structured form has grown to 8+ fields, and NL input is the highest-impact single UX feature. Product review confirmed: if you only ship one thing post-v1.0, it should be this. | Keep deferred — rejected because the pattern is proven and the form complexity has increased. |
| Registry expansion to MT/WY/NorCal | All use existing RIDB provider — it's a seed script update, not new infrastructure. Broadens discovery for road trips beyond the PNW triangle. Low effort, high coverage payoff. | BC Parks — considered but different country, different booking system, lower demand. Idaho state parks — CAPTCHA-blocked. |
| Trip Object as v1.2 headline | Trips are the connective tissue between search, watches, and the planner. Without them, these features are independent tools. With them, there's a workflow: search → save to trip → watch → get alerted → book. Template watches and watch sharing both build on the trip concept. | Trips in v1.1 — rejected because NL search + registry quality is the right first move. Trips in v2.0 — rejected because watches are the Pro feature and need strengthening before predictions. |
