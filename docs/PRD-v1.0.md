# campnw v1.0 — Product Requirements Document

**Version:** 1.0
**Date:** March 2026
**Status:** Draft

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

1. User lands on campnw.com. No account required for search.
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

#### P0-5: Watch/Alert System
- Watch a campground + date range + criteria (nights, day pattern)
- Polling every 15 minutes
- Notification channels: push (web push), email, ntfy, Pushover
- Diff detection: alert only on newly-available sites (cancellations), not baseline
- Watch management: list, pause, delete, edit criteria
- Account-gated for persistent watches; anonymous watches with email verification acceptable

#### P0-6: Calendar Heat Map
- Availability density visualization across months
- Color scale: red (none available) → yellow (some) → green (many sites open)
- Applies to both the search results aggregate view and individual campground view
- Clickable: selecting a date block filters to that window

#### P0-7: Mobile-Responsive Web
- Full functionality on mobile Chrome/Safari
- Notification tap-to-book flow optimized for mobile
- Touch-friendly date pickers, filter controls
- No native app in v1.0

### P1 — High Priority (target v1.0, can slip to v1.1)

#### P1-1: User Accounts
- Auth: email/password + Google OAuth
- Saved home base and preferences
- Persistent watch history
- Search history and saved searches
- Privacy-first: minimal data collection, clear data export/deletion

#### P1-2: AI Natural Language Search
**How it works:** User types a free-text query instead of filling form fields. Claude (Anthropic API) parses intent and extracts structured search parameters. Extracted parameters are shown to user for confirmation before search executes.

**Examples:**
- "Lakeside camping near Bellingham for 3 nights in July, dog-friendly" → state:WA, tags:[lakeside, pet-friendly], nights:3, date_range:July, base:Bellingham
- "Something not too far from Seattle this weekend with a beach" → state:WA, tags:[beach], dates:this-weekend, base:Seattle

**Data used:** Query text, registry metadata, user's home base preference.
**Value delivered:** Reduces search form friction to near-zero. Especially useful for first-time users who don't know the tag taxonomy.
**Guardrails:** Always show extracted parameters before search. User can correct misinterpretations. Never book on behalf of user.

#### P1-3: Predictive Availability ("When will it open?")

**How it works:** For fully-booked campgrounds, campnw analyzes historical availability patterns from its own polling data. The model identifies: typical cancellation windows (e.g., "sites at Sol Duc tend to open up 14-21 days before the date"), release patterns (6-month advance booking window for rec.gov), and high-demand periods.

**Data used:** campnw's own availability polling history (SQLite snapshots), booking window metadata from RIDB, known rec.gov release schedules.
**Value delivered:** Tells users whether to watch now or come back later. Reduces false hope on sold-out dates.
**Display:** Inline with unavailable results: "Sites here typically release 6 months in advance. Your target dates (Aug 12-14) should become bookable around Feb 12. We'll remind you."
**Limitation (be honest):** Pattern data is campnw's own. Early on, limited history means lower confidence. Show confidence level.

#### P1-4: Trip Planner (AI)
**How it works:** Conversational interface powered by Claude. User describes a trip in natural language. Assistant asks clarifying questions (group size, experience level, amenities needed), then generates a multi-stop itinerary with campground recommendations, drive times between stops, and availability checks for each stop.

**Data used:** Registry metadata, real-time availability, drive time matrix, user preferences (if logged in).
**Value delivered:** Replaces 2 hours of research with a 5-minute conversation. Especially useful for first-time campers or trips to unfamiliar regions.
**Scope constraint:** Itinerary only, not activity planning or gear lists (that's scope creep). Clear handoff to booking links.

#### P1-5: Shareable Trip Links
- Shareable URL for a search result set or a saved itinerary
- Link encodes search parameters and snapshot of results at share time
- No account required to view a shared link
- Expiry: 30 days

#### P1-6: Oregon State Parks Integration
- ReserveAmerica platform via Playwright headless scraping
- 200+ OR state parks campgrounds added to registry
- Blocks with WA State Parks to complete the PNW picture

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

### AI-1: Natural Language Search Parser
**Model:** Claude (claude-3-5-haiku for latency, claude-opus for complex queries)
**Input:** Free-text query string
**Output:** Structured JSON matching search form schema: `{state, tags[], nights, date_range, base_city, nights_min, source, name_contains}`
**Prompt strategy:** System prompt defines the registry's tag taxonomy, available states, base cities, and date preset vocabulary. Few-shot examples cover common patterns.
**Fallback:** If confidence is low (missing required fields), ask one clarifying question rather than guessing.
**Latency budget:** 800ms P95. Show a loading state. Do not block search form — user can edit parsed params before submitting.
**Cost estimate:** ~$0.001 per query at haiku pricing. Acceptable at scale.

### AI-2: Predictive Availability Model
**Model:** Statistical (not LLM). Time-series analysis over campnw's availability polling data.
**Data schema:** `{campground_id, site_id, date, status, observed_at}` — every poll result stored.
**Analysis:** For each campground + date combination, compute: median days before date that at least one cancellation appears, standard deviation, confidence interval based on sample size.
**Output:** "Sites here typically free up X-Y days before the date" with a confidence band.
**Cold start problem:** New campgrounds have no history. Fallback to rec.gov's published booking window (6 months in advance) plus a "we're still learning this campground" notice.
**Improvement trajectory:** Every 90 days of polling data meaningfully improves prediction quality. After 1 year, predictions are genuinely useful.

### AI-3: Trip Planner Assistant
**Model:** Claude (claude-sonnet for quality, with function calling)
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

### AI-4: Smart Notification Scoring
**Model:** Logistic regression over campnw's diff history (not LLM).
**Features:** Time-to-date (how far out is the booking), day of week site opened, campground popularity score, prior availability duration for this site.
**Output:** P(site still available in 30 min), P(still available in 2 hours)
**Display in notification:** "Usually books within [timeframe]" or "Typically stays open for hours"
**Training:** Requires 6+ months of diff data. Ship as manual rule-based approximation first, transition to model when data exists.

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

---

## 7. Technical Architecture Considerations

### Current State (working)
- FastAPI backend + SQLite + React/Vite/TypeScript
- Deployed on Fly.io (Docker), Cloudflare DNS
- GitHub Actions CI/CD

### v1.0 Architecture Additions

**Accounts + Auth:** Add PostgreSQL (or keep SQLite with libsql/Turso for multi-instance compatibility) for user data. Use a managed auth provider (Clerk or Auth.js) to avoid rolling auth from scratch.

**Background Job Queue:** The polling system currently relies on external cron. v1.0 needs a proper job queue — APScheduler embedded in FastAPI, or a lightweight queue like Dramatiq + Redis. Required for: watch polling, AI pre-computation jobs, registry refresh.

**AI API Integration:** Anthropic Python SDK. Natural language search and trip planner call the API synchronously (acceptable latency). Predictive model is pre-computed and cached, not real-time.

**Push Notifications:** Web Push API via a service worker. Requires HTTPS (already satisfied via Cloudflare). User subscribes in-browser; subscription stored in user record.

**Registry Refresh:** Automated monthly re-seed from RIDB for rec.gov campgrounds. GoingToCamp parks refresh quarterly. Drift detection: if a campground 404s consistently, flag for manual review.

**Performance Targets:**
- Search P95: under 4 seconds (parallel provider queries, registry filter first)
- Availability check P95: under 2 seconds for single campground
- Watch poll cycle: complete all active watches within 10 minutes per cycle
- API P95: under 200ms for non-availability endpoints (registry queries, user data)

### What to Defer
- Oregon ReserveAmerica (Playwright scraping is fragile — phase it in carefully)
- Native mobile apps
- Own payments or booking intermediation (legal and operational complexity not worth it)

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
- NL search adoption rate (% of searches using NL input vs. form)
- NL parse accuracy (user edits extracted params < 20% of the time)
- Trip planner session completion rate
- Predictive availability feature engagement (impressions → hovers on prediction tooltip)

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
**Risk:** NL search parser misinterprets queries and surfaces wrong results.
**Mitigation:** Always show extracted parameters before search executes. Make it easy to correct. Log misparse rate; improve prompts. Never execute AI-suggested actions autonomously.

### R6: Cold Start — Thin Availability History (MEDIUM)
**Risk:** Predictive availability features need months of polling data to be meaningful.
**Mitigation:** Don't ship predictive availability in v1.0. Ship the data collection infrastructure now. Launch predictions in v1.1 when 90+ days of data exists.
