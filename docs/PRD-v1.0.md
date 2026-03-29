# campnw v1.0 — Product Requirements Document

**Version:** 1.0
**Date:** March 2026
**Status:** Active — v0.8 in progress, v0.95 Monetization planned

---

## 0. Current State (as of March 2026)

campnw is live at campable.co. Versions 0.1 through 0.7 have shipped. The core product — multi-provider discovery, monitoring, accounts, background polling, and AI-powered delight features — is fully operational.

**What's live:**
- Search across Recreation.gov + WA State Parks with tag, drive time, and date filtering
- Calendar heat map with keyboard accessibility
- SSE streaming for progressive search results
- Smart Search: zero-result diagnostics, ±7/14 day date shifting, alternative suggestions (v0.6)
- Watch/alert system with server-side APScheduler polling (15-min cycles), web push (VAPID + service worker), ntfy, Pushover
- PWA manifest for iOS web push support
- User accounts (PyJWT + bcrypt, httpOnly cookies), saved home base, search history, privacy controls
- Registry auto-enrichment via Claude Haiku (structured tag extraction from RIDB/GoingToCamp descriptions)
- Site vibe descriptions — Haiku-generated character summaries on expanded campground cards (v0.7)
- Contextual watch notifications — LLM-enriched alerts with urgency scoring 1-3 (v0.7)
- Availability cache (10-min TTL) and availability history collection (feeds future predictions)
- 346 tests (82% backend coverage), CI gating on deployment

**Deferred from original plan:**
- Oregon State Parks (ReserveAmerica has no availability API; Playwright required — tracked as stretch goal)
- AI natural language search (assessed as low-impact relative to effort; indefinitely deferred in favor of Smart Search)

**Next milestones:** v0.8 Trip Planner (conversational AI on `/plan`), v0.9 Predictions+, v0.95 Monetization (Free/Pro tiers, subscription billing).

---

## 1. Vision and Mission

**Vision:** Every PNW camper finds the trip they want, not just the trip that's available.

**Mission:** campnw removes the friction between wanting to go camping and actually going — by surfacing real availability across every major booking system, predicting when sites will open, and helping campers make confident decisions fast.

The current state of campsite discovery is broken in a specific way: it's fragmented. Recreation.gov, GoingToCamp, Reserve America, and park-specific systems each require separate logins, separate searches, and separate mental models. Campers who want to spend a weekend at a lake near Seattle have to run four different searches, manually cross-reference results, and refresh pages hoping a cancellation appears. Campnab and Campflare solve the monitoring problem for people who already know where they want to go. Camply is a powerful CLI for technical users. Nobody solves discovery with the quality of a consumer product.

campnw v1.0 is the answer to: "I want to go camping this summer — where should I go, when should I book, and will I actually get a site?"

---

## 2. Target Users and Personas

### Primary Persona: The Deliberate Weekend Planner

**Name:** Mara, 32, software engineer in Bellevue
**Behavior:** Plans 3-5 camping trips per year. Books 2-6 months out for popular spots (Rainier, Enchantments, Olympic). Knows recreation.gov but finds it frustrating. Has missed sites because she didn't refresh fast enough after a cancellation.
**Needs:** See what's actually available for her target dates. Know which sites are worth monitoring. Understand when to book without obsessing.
**Frustration:** "I spent 45 minutes searching three different websites and still don't know if there's anything available the weekend of the 4th."

### Secondary Persona: The Opportunistic Car Camper

**Name:** Jake, 28, teacher in Portland
**Behavior:** Prefers to plan loosely. Books 2-4 weeks out. Flexible on dates and location — cares more about the vibe (lakeside, old-growth, not too crowded) than the specific park.
**Needs:** "What's actually open this weekend within 2 hours of Portland?" Reliable drive time estimates. Quick booking.
**Frustration:** "I can never find anything last-minute because I don't know where to even look."

### Tertiary Persona: The Trip Organizer

**Name:** Priya, 36, product manager in Seattle
**Behavior:** Organizes group trips for 6-10 people 2-3 times per year. Coordinates date availability across multiple schedules. Needs sites that accommodate groups or multiple tent pads.
**Needs:** Shareable results. Group-size filtering. Side-by-side comparison of options. Confidence that she's picking the right dates before committing to the group.
**Frustration:** "I find a great site and then have to screenshot it and share it in a group chat and half the time by the time we agree it's gone."

### Out of Scope (v1.0)
- Backpackers (permit-based, different booking systems)
- International camping
- RV-only trips (supported but not primary focus)
- Commercial operators or outfitters

---

## 3. Core User Journeys

### Journey 1: Flexible Discovery ("I want to go camping, help me find something")

1. User lands on campable.co. No account required for search.
2. User selects "Find a date" mode.
3. User specifies: general region (e.g., "within 2 hours of Seattle"), date range (e.g., June), preferred weekend pattern (e.g., Friday–Sunday), and optional preferences (lakeside, pet-friendly).
4. campnw queries Recreation.gov availability and GoingToCamp in parallel across all matching campgrounds in the registry.
5. Results appear grouped by availability window. A calendar heat map shows which weekends have the most availability across all campgrounds.
6. AI layer surfaces a "Best picks this month" card: 3 campgrounds with the best combination of availability, drive time, and tag match.
7. User clicks a campground. Detail view shows: all available sites for their dates, site-level details (hookups, tent pads, photos where available), direct booking link.
8. User books directly on recreation.gov or GoingToCamp. campnw does not intermediate the transaction.

**Key design requirement:** First results should appear within 3 seconds. Progressive loading acceptable — show fast-responding providers first.

### Journey 2: Specific Monitoring ("I want Ohanapecosh in July — alert me when something opens")

1. User searches for a specific campground by name.
2. No availability found for target dates.
3. campnw shows a "Watch this campground" CTA with pre-filled dates.
4. User sets watch. If no account, prompts to create one (or accept a one-time email alert).
5. campnw polls every 15 minutes. When a cancellation appears, push notification fires within one poll cycle.
6. Notification includes: campground name, site number, available dates, direct booking link. Single tap to book.
7. AI layer adds: "Sites at Ohanapecosh typically release 6 months in advance. June/July weekends usually fill within 48 hours of release. We'll notify you the moment anything opens."

**Key design requirement:** Notification to booking action must be achievable in under 60 seconds on mobile.

### Journey 3: Trip Planning ("Help me plan a week-long camping road trip")

1. User selects "Plan a trip" mode (AI-powered, P1 feature).
2. User describes intent in natural language: "I want to spend 5 days camping in the Olympics in August, with a toddler, no hookups needed, prefer sites near water."
3. AI extracts parameters: dates, region, group composition, amenity preferences.
4. campnw generates an itinerary with: Day 1-2 at Hurricane Ridge, Day 3-4 at Kalaloch Beach, Day 5 at Sol Duc Hot Springs — each with availability check, drive time between sites, and direct booking links.
5. User can accept, modify, or regenerate individual segments.
6. Shareable link for the full itinerary.

**Key design requirement:** AI response must feel like a knowledgeable friend, not a search engine. Context should carry across the conversation.

### Journey 4: Last-Minute Booking ("What's open this weekend?")

1. User opens campnw on Thursday evening.
2. Selects "This weekend" preset.
3. Sets home base (remembered if account exists).
4. Results show only campgrounds with current availability — sorted by drive time by default.
5. AI surfaces: "3 sites just became available at Dosewallips in the last 2 hours" — cancellation recency signal.
6. User books within the app flow.

---

## 4. Feature Specifications

### P0 — Core (must ship for v1.0)

#### P0-1: Search Engine
- **Date modes:** "Find a date" (flexible range + day-of-week pattern) and "Exact dates" (specific arrival/departure)
- **Geographic filtering:** Distance from home base (user-selected or browser-detected city), drive time buckets (under 1hr, 1-2hr, 2-3hr, 3+hr)
- **Tag filtering:** Lakeside, riverside, beach, old-growth, pet-friendly, RV-friendly, tent-only, trails, swimming, shade — multi-select
- **Source filtering:** All sources, Recreation.gov only, WA State Parks only
- **Group size:** Min sites available for N people (drives site capacity filtering)
- **Results modes:** By date (availability windows) and By site (individual sites with date chips)
- **Performance target:** P95 search response under 4 seconds

#### P0-2: Campground Registry
- 685+ campgrounds across WA, OR, ID
- Auto-enriched tags from RIDB and GoingToCamp data
- Drive time estimates from 6 PNW base cities (pre-computed, not real-time)
- Manual curation layer for quality/notes/ratings

#### P0-3: Multi-Provider Availability
- Recreation.gov: real-time availability via undocumented availability endpoint
- WA State Parks (GoingToCamp): real-time availability with WAF bypass
- FCFS site awareness: show count but flag as non-bookable online
- Graceful degradation: if one provider fails, return results from the other with clear labeling

#### P0-4: Booking Link Passthrough
- Pre-filled booking links to recreation.gov with site + date parameters
- Pre-filled links to GoingToCamp reservation pages
- Link validation: verify links resolve before surfacing (avoid dead links from stale data)

#### P0-5: Watch/Alert System — SHIPPED (v0.2–v0.5)
- Watch a campground + date range + criteria (nights, day pattern)
- Server-side polling via APScheduler AsyncIOScheduler, 15-min cycles, embedded in FastAPI
- Notification channels: web push (VAPID + service worker), ntfy, Pushover — per-watch channel preferences
- PWA manifest for iOS web push support
- Diff detection: alert only on newly-available sites (cancellations), not baseline
- Contextual notification enrichment: LLM-generated alert copy with urgency scoring 1-3 (v0.7)
- Watch management: list, pause, delete, edit criteria
- Watch CRUD API (POST/GET/DELETE/PATCH); web management UI with creation animation
- Availability cache (10-min TTL, shared across all watches on the same campground)
- Account-gated; anonymous watch → account migration on signup
- Email channel: not yet implemented (tracked for post-v1.0)

#### P0-6: Calendar Heat Map — SHIPPED (v0.3)
- Availability density visualization across months
- Single-hue scale (GitHub contribution graph layout)
- Keyboard accessible; aria-labels per cell
- Applies to both the search results aggregate view and individual campground view
- Clickable: selecting a date block filters to that window

#### P0-7: Mobile-Responsive Web
- Full functionality on mobile Chrome/Safari
- Notification tap-to-book flow optimized for mobile
- Touch-friendly date pickers, filter controls
- No native app in v1.0

### P1 — High Priority (target v1.0, can slip to v1.1)

#### P1-1: User Accounts — SHIPPED (v0.4)
- Auth: email/password with PyJWT + bcrypt, httpOnly cookie sessions (no external auth provider)
- Google OAuth: not implemented (deferred; PyJWT is sufficient for current scale)
- Saved home base and default preferences
- Persistent watch ownership; anonymous watch migration on signup/login
- Search history as quick-fill chips in the search form
- Privacy controls: data export (JSON), account deletion
- Watch UNIQUE constraint scoped per-user (app-level duplicate check)

#### P1-2: Smart Search — SHIPPED (v0.6)
**What it is:** Intelligent zero-result handling and proactive date flexibility, replacing the form-friction problem that AI NL search was originally scoped to solve.

**Components shipped:**
- Smart date shifting: ±7/14 day probes when no results found; inline suggestions with result counts
- Zero-result diagnostics: binding constraint analysis identifies why nothing matched (source filter, date window, tag combination, distance)
- SmartZeroState component: replaces generic no-results with actionable refinement chips
- Lightweight alternative suggestions: Jaccard tag similarity + proximity scoring to surface nearby matches

**Value delivered:** Users who get zero results now understand why and have a one-tap path to refine. Reduces dead-end search sessions without requiring an LLM round-trip.

---

#### P2-backlog: AI Natural Language Search (DEFERRED)
*Originally P1-2. Demoted after roadmap assessment: low marginal impact relative to Smart Search, which solves the same form-friction problem more reliably and without LLM latency. The structured search form with tag chips and date presets (including "This wknd", "Next wknd", "Next 30 days", multi-select month buttons) covers the vast majority of query patterns. Revisit if user research surfaces strong demand for freeform input.*

#### P1-3: Registry Auto-Enrichment — SHIPPED (v0.5)
- Claude Haiku extracts structured tags from RIDB and GoingToCamp campground descriptions
- CLI command (`enrich`) for manual runs; ~$0.10 for a full registry pass
- Tags validated against defined taxonomy before writing to SQLite
- 453 of 685 campgrounds currently have enriched tags
- Automated scheduled refresh: not yet implemented (deferred to post-v1.0)

#### P1-4: Site Vibe Descriptions — SHIPPED (v0.7)
- Haiku-generated character summaries surfaced in expanded campground cards
- Describes the feel of a site (old-growth quiet, exposed ridge, family-busy, etc.)
- Generated at enrichment time, stored in registry; not a real-time API call

#### P1-5: Predictive Availability ("When will it open?") — IN PROGRESS (data collection)

**How it works:** For fully-booked campgrounds, campnw analyzes historical availability patterns from its own polling data. The model identifies: typical cancellation windows (e.g., "sites at Sol Duc tend to open up 14-21 days before the date"), release patterns (6-month advance booking window for rec.gov), and high-demand periods.

**Data used:** campnw's own availability polling history (SQLite snapshots, collecting since v0.5), booking window metadata from RIDB, known rec.gov release schedules.
**Value delivered:** Tells users whether to watch now or come back later. Reduces false hope on sold-out dates.
**Display:** Inline with unavailable results: "Sites here typically release 6 months in advance. Your target dates (Aug 12-14) should become bookable around Feb 12. We'll remind you."
**Data collection status:** Availability history has been collecting since v0.5 (launched ~late 2025). Sufficient data for early predictions expected by mid-2026. Cold start mitigation: fall back to rec.gov's published booking window until campground-specific history is sufficient.
**Limitation (be honest):** Pattern data is campnw's own. Early on, limited history means lower confidence. Show confidence level.

#### P1-6: Trip Planner (AI) — IN DEVELOPMENT (v0.8)
**How it works:** Conversational interface powered by Claude. User describes a trip in natural language. Assistant asks clarifying questions (group size, experience level, amenities needed), then generates a multi-stop itinerary with campground recommendations, drive times between stops, and availability checks for each stop.

**Data used:** Registry metadata, real-time availability, drive time matrix, user preferences (if logged in).
**Value delivered:** Replaces 2 hours of research with a 5-minute conversation. Especially useful for first-time campers or trips to unfamiliar regions.
**Scope constraint:** Itinerary only, not activity planning or gear lists (that's scope creep). Clear handoff to booking links.

#### P1-7: Shareable Trip Links — PARTIAL (search links shipped v0.3)
- Shareable search links via URL query string encoding: SHIPPED (v0.3)
- Shareable saved itineraries (trip planner output): planned for v0.8
- No account required to view a shared link
- Expiry: 30 days

#### P1-8: Oregon State Parks Integration — DEFERRED
- ReserveAmerica has no public availability API; Playwright headless scraping is the only path
- Deferred indefinitely due to fragility of scraping-based approaches and maintenance burden
- Will be revisited if ReserveAmerica exposes an API or a reliable community solution emerges
- OR federal campgrounds (rec.gov) are covered; the gap is OR State Parks specifically

#### P1-9: Subscription Billing & Pro Tier — PLANNED (v0.95)

**Goal:** Make campnw self-sustaining. Break-even requires 2-4 Pro subscribers at $5/month. This is a sustainability milestone, not a growth milestone.

**Tier structure:**

| Feature | Free | Pro ($5/mo) |
|---|---|---|
| Search, heat map, vibe descriptions, Smart Search | Unlimited | Unlimited |
| Shareable links, booking link passthrough | Yes | Yes |
| Simultaneous active watches | 3 | Unlimited |
| Watch polling interval | 15 min | 5 min |
| Contextual AI notifications (urgency scoring) | Yes | Yes |
| Anomaly alerts (v0.9) | No | Yes |
| Availability predictions (v0.9) | Preview only | Full |
| Trip planner sessions (v0.8) | 3/month | 20/month |
| Search history | 10 searches | 30 searches |
| Data export, account deletion | Yes | Yes |

**Core design constraints:**
- Search and availability checking are always free — core discovery is never gated
- Watches are the natural billing gate: background polling and AI enrichment are where the server cost lives
- Watches beyond the free limit are paused on downgrade, never deleted
- Existing users get a 30-day grandfather period at launch before the limit kicks in

**Billing infrastructure:**
- Stripe Checkout for payments (hosted — no PCI scope on campnw)
- Stripe Customer Portal for subscription management (cancel, update card, billing history)
- Four webhook events cover all state transitions: `customer.subscription.updated`, `.deleted`, `invoice.payment_failed`, `invoice.payment_succeeded`
- `subscription_status` is always set by server-side webhook, never by client redirect
- Webhook endpoint validates `Stripe-Signature` header; rejects unverified requests with 400

**Upgrade trigger surfaces:** 4th watch creation attempt (hard gate, inline upgrade modal), 4th trip planner session of the month (soft gate), anomaly alerts panel (soft prompt), Settings > Plan (passive, always visible). Never on page load or during search.

**Pricing page:** `/pricing` — static, linked from footer and settings. No separate marketing site required.

**Completion criteria:** Stripe Checkout + webhooks integrated and tested; watch limit enforced server-side (HTTP 402 with `watch_limit_reached` body); 5-min polling active for Pro; upgrade modal reused across all trigger surfaces; Settings > Plan page; grandfather period banner; all billing state transitions covered by tests.

### P2 — Nice to Have (post-v1.0)

#### P2-1: Map View
- Interactive map (Mapbox or Leaflet) with campground pins
- Pin color encodes availability density
- Click pin to see quick preview; click through to full detail
- Cluster at low zoom levels

#### P2-2: Smart Notifications — "Confidence Score"
**How it works:** When a watch fires, attach a confidence score to the notification: "This site has opened before but typically re-books within 30 minutes. Act fast." vs "This site opened and was available for 4+ hours when we last saw this pattern."

**Data used:** campnw's own diff history — how long sites stay available after a cancellation appears.
**Value delivered:** Helps users prioritize which alerts to act on immediately vs. which can wait.

#### P2-3: Personalized Recommendations
**How it works:** Based on search history and saved campgrounds, surface proactive suggestions: "Sites at your saved campgrounds are opening up for a weekend you haven't booked yet" or "You tend to camp lakeside in August — here are 3 options with current availability."

**Data used:** User's search history, saved campgrounds, watch history, past bookings (self-reported).
**Value delivered:** Shifts campnw from reactive (search when you think of it) to proactive (campnw surfaces trips you'd want before you ask).
**Privacy:** Opt-in. Clear explanation of what data is used. No third-party sharing.

#### P2-4: Campground Detail Enrichment
- Amenity data beyond tags: number of sites, fire rings, bear boxes, cell coverage (crowdsourced)
- User reviews (simple: 1-5 stars + 280-char note, tied to account)
- Photos (link to recreation.gov photos; no upload in v1.0)
- Cell coverage overlay (crowdsourced from OpenSignal or user reports)

#### P2-5: Idaho and Oregon Federal Campgrounds Expansion
- Expand RIDB seed to cover all ID and OR federal campgrounds (currently partial)
- Re-seed registry with complete coverage
- Target: 1,000+ campgrounds total

#### P2-6: Keyboard Shortcuts and Power User Mode
- `/search` slash command in any text field to jump to search
- `k/j` navigation through results
- `b` to add to bookmarks, `w` to add watch from results list
- Notion-inspired: discoverable via `?` help overlay

---

## 5. AI Feature Specifications (Detailed)

### AI-1: Shipped AI Features

#### AI-1a: Registry Auto-Enrichment — SHIPPED (v0.5)
**Model:** Claude Haiku (claude-haiku — fast, cheap, sufficient for structured extraction)
**Input:** Campground name + description text from RIDB or GoingToCamp
**Output:** Structured tag array validated against the registry taxonomy (lakeside, riverside, beach, old-growth, pet-friendly, etc.)
**Usage pattern:** CLI-triggered (`enrich` command), not real-time. Operator runs as needed (~$0.10/full registry pass). Results written to SQLite.
**Cost:** ~$0.10 per full registry run. Not on the hot path; cost is not a concern.

#### AI-1b: Site Vibe Descriptions — SHIPPED (v0.7)
**Model:** Claude Haiku
**Input:** Registry metadata (tags, name, description, park context)
**Output:** 1-2 sentence character summary surfaced in expanded campground cards ("Exposed ridge site with panoramic Cascades views — stunning but windswept; bring extra stakes")
**Usage pattern:** Generated at enrichment time, stored in registry. Not a real-time call.
**Guardrail:** Descriptions are clearly AI-generated impressions, not authoritative campground facts.

#### AI-1c: Contextual Watch Notifications — SHIPPED (v0.7)
**Model:** Claude Haiku
**Input:** Watch criteria (campground, dates, nights), availability diff (what just opened), campground vibe/tags
**Output:** LLM-enriched notification copy with urgency score (1=low, 2=medium, 3=high)
**Usage pattern:** Called during watch poll diff when new availability is detected. Enriches the notification before dispatch.
**Urgency scoring drives:** notification priority, "act fast" vs. "take your time" framing in push body

---

### AI-1-deferred: Natural Language Search Parser — DEFERRED
*Originally the primary AI feature. Assessed as low-impact after v0.6 Smart Search shipped. The structured form with tag chips, date presets (including "This wknd", "Next wknd", "Next 30 days"), and Smart Zero State covers the form-friction problem more reliably without LLM latency. Revisit if user research resurfaces clear demand.*

### AI-2: Predictive Availability Model — PLANNED (v0.9)
**Model:** Statistical (not LLM). Time-series analysis over campnw's availability polling data.
**Data schema:** `{campground_id, site_id, date, status, observed_at}` — collected since v0.5.
**Analysis:** For each campground + date combination, compute: median days before date that at least one cancellation appears, standard deviation, confidence interval based on sample size.
**Output:** "Sites here typically free up X-Y days before the date" with a confidence band.
**Cold start problem:** New campgrounds have no history. Fallback to rec.gov's published booking window (6 months in advance) plus a "we're still learning this campground" notice. Data has been collecting since v0.5 — early predictions feasible by mid-2026.
**Improvement trajectory:** Every 90 days of polling data meaningfully improves prediction quality. After 1 year, predictions are genuinely useful.

### AI-3: Trip Planner Assistant — IN DEVELOPMENT (v0.8)
**Model:** Claude Sonnet (claude-sonnet-4-5 or later, with function calling)
**Tools available to the model:**
- `search_campgrounds(params)` — calls campnw's own search engine
- `check_availability(campground_id, dates)` — real-time check
- `get_drive_time(from, to)` — pre-computed matrix lookup
- `get_campground_detail(id)` — registry metadata

**Conversation pattern:**
1. User describes trip intent
2. Assistant asks 1-2 clarifying questions if needed (group size, accessibility needs)
3. Assistant calls tools, generates itinerary
4. User can say "swap day 3, I want something more remote" — assistant replaces that leg
5. Final output: structured itinerary card with booking links per stop

**Guardrails:**
- Never commit to availability that isn't real-time verified
- Always show the "as of [timestamp]" caveat on availability data
- Do not recommend sites outside the registry (no hallucinated campgrounds)

### AI-4: Smart Notification Scoring — PARTIAL (lightweight version shipped v0.7)
**Current state (v0.7):** Contextual notifications use Claude Haiku to generate urgency scores (1-3) and enriched copy per alert. This is the LLM-based precursor to a statistical model.
**Future state (v0.9):** Logistic regression over campnw's diff history.
**Features:** Time-to-date (how far out is the booking), day of week site opened, campground popularity score, prior availability duration for this site.
**Output:** P(site still available in 30 min), P(still available in 2 hours)
**Display in notification:** "Usually books within [timeframe]" or "Typically stays open for hours"
**Training:** Requires 6+ months of diff data. Currently using LLM heuristics; transition to statistical model when data volume supports it.

---

## 6. Design Principles

### 6.1 Notion-Inspired Aesthetic

**Content density over decoration.** Every pixel should carry information. Avoid hero images, splash screens, and marketing fluff within the product. Results load into structured, scannable cards — not a wall of whitespace with a single fact.

**Typography as hierarchy.** Use a single typeface (Inter or equivalent) at 4-5 sizes maximum. Let weight and size communicate importance. No color-as-decoration — color means something (availability status, urgency, category).

**Minimal chrome.** The interface recedes to let campground data be the hero. Navigation is functional, not prominent. Filters are collapsible. The search bar is always present and always focused on mobile.

**Keyboard-first, touch-friendly.** Power users navigate with keyboard shortcuts. Casual users never need them. Both experiences are first-class.

**Tasteful micro-interactions.** Availability chips animate in as data loads. Heat map cells transition colors smoothly. Watch confirmation has a brief, satisfying animation. Never gratuitous.

**Dark mode from day one.** campnw is used on phones in tents. Dark mode is not an afterthought.

### 6.2 Information Hierarchy for Results

Each result card presents (in order): campground name + park system icon, drive time from home base, tag chips, availability summary (X sites open for your dates), and one CTA (Book Now or Watch). Expandable to show individual site breakdown. Never show information that requires explanation inline — use tooltips.

### 6.3 Honest Communication

The product should never overstate confidence. "Usually books within 30 minutes" is better than "BOOK NOW!" Availability data has a timestamp. Drive times are approximate and labeled as such. AI predictions show confidence levels. FCFS sites are clearly marked as non-bookable online.

### 6.4 Honest Monetization

Upgrade prompts appear at the moment of genuine value, not on page load, not during search, and not on notification receipt. The free tier is a complete product — it should be presented as such, not framed as "limited." Watches beyond the free limit are paused on downgrade, never silently deleted. No countdown timers, no dark-pattern cancellation flows, no repeated upsell emails. The pricing page says what the product costs and why.

---

## 7. Technical Architecture Considerations

### Current State (deployed at campable.co)
- FastAPI backend + SQLite + React/Vite/TypeScript
- Deployed on Fly.io (Docker, min_machines_running=1, ~$2/mo always-on)
- GitHub Actions CI/CD with test gating (346 tests, 82% backend coverage, 70% CI threshold)
- Cloudflare DNS, HTTPS everywhere

**Auth:** PyJWT + bcrypt, httpOnly cookie sessions. Self-rolled — no external auth provider. Sufficient for current scale and avoids vendor dependency. Google OAuth not implemented; deferred.

**Database:** SQLite for everything — registry, availability cache (10-min TTL), watch state, user accounts, availability history. No PostgreSQL. SQLite handles current single-instance Fly.io deployment cleanly. Revisit if multi-instance scaling becomes necessary.

**Background Jobs:** APScheduler AsyncIOScheduler embedded in FastAPI. Handles watch polling (15-min cycles) and AI enrichment jobs. Running in production since v0.5. No external queue dependency (no Redis, no Dramatiq).

**Push Notifications:** Web Push API (VAPID) + service worker. Deployed and working on desktop Chrome/Firefox, Android. PWA manifest enables iOS Safari web push. VAPID keys stored in environment. Subscription objects stored in user record in SQLite.

**Availability History:** Silent data collection since v0.5. Schema: `{campground_id, site_id, date, status, observed_at}`. Powers future predictive availability (v0.9).

**AI Integration:** Anthropic Python SDK. Haiku for enrichment, vibe generation, and contextual notifications. Sonnet planned for Trip Planner (v0.8) with function calling.

**SSE Streaming:** Progressive search results via Server-Sent Events (v0.3). Campgrounds stream in as providers respond; first results appear quickly, slow providers fill in after.

### v0.95 Billing Infrastructure

**Payment provider:** Stripe (Checkout + Billing Webhooks + Customer Portal). Lemon Squeezy is an acceptable alternative if Stripe's MoR model creates tax complexity — decision deferred to implementation.

**Schema additions:**
- `users` table: `stripe_customer_id` (nullable text), `subscription_status` (enum: free | pro | pro_grace | pro_cancelled), `subscription_expires_at` (nullable datetime), `pro_since` (nullable datetime)
- New `subscription_events` table: append-only audit log of all webhook-driven state transitions (event type, stripe event id, timestamp, resulting status). Provides a complete audit trail without storing payment data.

**Webhook endpoint:** `POST /api/billing/webhook` — validates `Stripe-Signature` HMAC before processing. Handles `customer.subscription.updated`, `customer.subscription.deleted`, `invoice.payment_failed`, `invoice.payment_succeeded`. Idempotent: safe to replay. All subscription state changes flow through this endpoint only; client-side redirects do not set subscription status.

**Entitlement checking:** Always server-side. The `subscription_status` from the database is the source of truth. Never encoded in JWT or derived from client-supplied parameters. Watch creation (`POST /api/watches`) checks entitlement and returns `HTTP 402 Payment Required` with a machine-readable body when the limit is reached.

**No financial data in SQLite:** campnw stores only `stripe_customer_id` and subscription status enum. All payment details, card data, and billing history live in Stripe.

### v1.0 Remaining Architecture Work

**Trip Planner (v0.8):** Conversational interface on `/plan` route. Claude Sonnet + function calling tools: `search_campgrounds`, `check_availability`, `get_drive_time`, `get_campground_detail`. Shareable itinerary links (UUID, 30-day expiry). Rate limiting on free tier (3 planner sessions/month, enforced server-side).

**Predictive Availability (v0.9):** Statistical model over collected availability history. Pre-computed, cached, not real-time. Cold start handled by rec.gov booking window fallback.

**Registry Refresh:** Automated monthly RIDB re-seed and quarterly GoingToCamp refresh not yet implemented. Currently manual. Drift detection (404 on campground) is handled gracefully in providers.

**Performance Targets:**
- Search P95: under 4 seconds (parallel provider queries, registry filter first)
- Availability check P95: under 2 seconds for single campground
- Watch poll cycle: complete all active watches within 10 minutes per cycle
- API P95: under 200ms for non-availability endpoints (registry queries, user data)

### Confirmed Deferrals
- Oregon ReserveAmerica: no API, Playwright scraping too fragile
- Native mobile apps: PWA covers mobile use case adequately
- PostgreSQL: SQLite is the confirmed long-term choice at current scale
- External auth providers (Clerk, Auth.js): self-rolled JWT is sufficient
- Own payments or booking intermediation: legal and operational complexity not worth it

---

## 8. Success Metrics and KPIs

### North Star Metric
**Trips facilitated per month** — a user finds available campgrounds, clicks a booking link, and (self-reported or inferred via return visit) books a trip. This is the only metric that actually measures whether campnw is delivering value.

### Acquisition
- Monthly active users (MAU)
- Search sessions per week
- Organic search traffic (SEO on campground names + availability)

### Engagement
- Searches per session (target: >2, indicating refinement and exploration)
- Watch creation rate (% of no-results sessions that create a watch)
- Notification open rate (target: >60% — high intent audience)
- Notification-to-booking link click rate (target: >40%)

### Retention
- 30-day retention of registered users
- Repeat sessions within same camping season
- Watch-to-rewatch rate (users who successfully book and come back for the next trip)

### AI Features
- Smart Search refinement rate (% of zero-result sessions that use a suggested chip to find results)
- Trip planner session completion rate (target: v0.8)
- Predictive availability feature engagement (impressions → hovers on prediction tooltip) (target: v0.9)
- Watch notification urgency score distribution (% high/medium/low urgency alerts)
- Notification-to-booking click rate segmented by urgency score (validates LLM scoring quality)

### Monetization (v0.95)
- **MRR target:** $10/month (2 Pro subscribers) = break-even; $20/month = comfortable. These are low bars — sustainable, not ambitious.
- **Pro conversion rate:** 2–5% of monthly active users. Low bar given free-tier friction is intentionally minimal.
- **Churn rate:** Track monthly. Sustained >20% monthly churn indicates Pro value is not landing.
- **Watch limit hit rate:** % of active free users who reach 3 watches. Validates that the gate is placed correctly — too high means the limit is too loose, too low means it never creates upgrade pressure.
- **Upgrade-trigger-to-conversion rate:** Target >15% of users who see the upgrade modal and subscribe.
- **Grandfather-period behavior:** % of affected users (>3 watches) who upgrade vs. trim to 3 vs. disengage. Informs whether the limit is calibrated correctly.

### Quality
- Provider uptime (rec.gov availability endpoint, GoingToCamp endpoint) — alert if either drops below 95%
- False notification rate (watch fires but site already gone by the time user clicks) — target: < 15%
- Stale booking link rate — target: < 1%

---

## 9. Competitive Landscape

| Product | Strength | Weakness | campnw Advantage |
|---|---|---|---|
| **Campnab** | Reliable rec.gov monitoring, established trust | Single-campground watches only, no discovery, no WA State Parks | Multi-provider discovery + monitoring in one tool |
| **Campflare** | Polished UI, group booking features | Rec.gov only, US-wide (not PNW-specific), expensive ($20+/mo) | Free tier, PNW-specific registry depth, WA State Parks |
| **camply** | Powerful CLI, multi-provider, open source | Requires technical setup, no web UI, no discovery | Zero setup, web-first, non-technical users |
| **Recreation.gov** | Authoritative source, direct booking | No discovery, terrible search, no multi-park view | Discovery layer on top of the same data |
| **GoingToCamp** | WA State Parks coverage | Per-park only, no aggregation | Aggregated into unified search |
| **The Dyrt** | Large community, reviews, photos | No real-time availability, no monitoring, paid Pro for offline | Availability-first, free |
| **Hipcamp** | Private land campsites, unique experiences | Different inventory, no public land | Complements campnw (different supply) |

**Key insight:** No competitor does PNW-specific multi-provider discovery + monitoring + AI with a consumer-quality interface.

---

## 10. Risks and Mitigations

### R1: Provider API Instability (HIGH)
**Risk:** Recreation.gov's undocumented availability endpoint changes without notice, breaking the core product.
**Mitigation:** Monitor endpoint response shape on every poll. Alert on schema changes before users notice. Maintain a cached "last known good" snapshot for graceful degradation. Watch camply and other tools in the ecosystem — they'll notice breaks too.

### R2: GoingToCamp WAF Escalation (MEDIUM)
**Risk:** WA State Parks upgrades WAF, blocking the curl_cffi TLS impersonation bypass.
**Mitigation:** Monitor 403 rate in production. Keep curl_cffi updated. Have Playwright-based fallback ready. If blocked, disable WA State Parks and communicate to users.

### R3: User Growth Strains Fly.io Costs (LOW-MEDIUM)
**Risk:** Polling 685+ campgrounds every 15 minutes for active watches becomes expensive at scale.
**Mitigation:** Batch watches by campground (one poll serves all watchers on the same campground). Rate limit anonymous watches. Paid tier unlocks higher polling frequency. Cap free tier at 3 simultaneous watches.

### R4: Legal/ToS Issues (LOW)
**Risk:** Recreation.gov or WA State Parks objects to automated querying.
**Mitigation:** campnw is a discovery and monitoring tool, not a booking intermediary. All transactions happen on official platforms. Respect rate limits. Not materially different from what camply, Campnab, and Campflare do.

### R5: AI Accuracy and Trust (MEDIUM)
**Risk:** AI-powered features (trip planner, contextual notifications, vibe descriptions) generate inaccurate or misleading output that damages user trust.
**Mitigation:** Trip planner never commits to availability that isn't real-time verified; always shows "as of [timestamp]" caveat. Vibe descriptions are labeled as AI-generated impressions. Notification enrichment affects copy only — the underlying availability diff is always ground truth. Never execute AI-suggested actions autonomously. Log cases where users click "watch" after a notification to detect false urgency patterns.

### R6: Cold Start — Thin Availability History (LOW-MEDIUM, actively mitigated)
**Risk:** Predictive availability features need months of polling data to be meaningful.
**Mitigation:** Availability history collection has been running since v0.5 (late 2025). By mid-2026, sufficient data exists for early predictions on high-watch campgrounds. Cold start fallback: rec.gov's published 6-month booking window + "we're still learning this campground" notice. Predictions ship in v0.9, not v1.0, giving additional runway for data accumulation.

### R7: Free Tier Is Too Good — Nobody Upgrades (MEDIUM)
**Risk:** The free tier covers most users' real needs well enough that Pro offers insufficient pull. MRR stays at $0.
**Mitigation:** Watch the watch-limit hit rate. If free users rarely reach 3 watches, the gate is too loose — lower to 2, or move the trip planner gate earlier. If MRR is $0 after 3 months, revisit the tier definition before investing further in billing infrastructure. Accepting that campnw remains a free personal tool is a valid outcome.

### R8: Grandfather Period Causes Churn (LOW)
**Risk:** Users with more than 3 active watches who don't want to pay may disengage entirely rather than trim or upgrade.
**Mitigation:** 30-day grandfather period is non-negotiable — breaking existing setups without notice is a trust violation. Honest, plain-text communication. Don't over-index on retaining users who won't pay $5/month for a tool they're actively using.

### R9: Stripe Integration Complexity Delays Launch (LOW-MEDIUM)
**Risk:** Webhooks + Customer Portal + idempotency + SQLite state sync is real backend work that can slip.
**Mitigation:** Use Stripe Checkout and Customer Portal aggressively — build no custom billing UI. The entire payment surface is hosted by Stripe. The campnw backend only handles webhook state sync and entitlement checking. Scope is bounded.
