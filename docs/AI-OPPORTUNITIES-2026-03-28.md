# campnw — Anthropic/Claude Integration Opportunities

**Date:** March 2026
**Context:** Analysis of where Anthropic models could add value beyond the 3 existing integrations.

---

## Current Integrations (Baseline)

| # | Integration | Model | Trigger | Cost |
|---|---|---|---|---|
| 1 | **Registry Tag Extraction** | Haiku 4.5 | Manual CLI (`enrich`) | ~$0.10/full run (741 campgrounds) |
| 2 | **Vibe Description Generation** | Haiku 4.5 | Manual CLI (`enrich`) | Included in above |
| 3 | **Notification Enrichment** | Haiku 4.5 | Auto — every watch poll with changes (3s timeout) | ~$0.001/notification |
| 4 | **Trip Planner** | Sonnet 4 | User-initiated on `/plan` route | ~$0.03-0.10/session |

**Total current spend:** Varies with usage. Trip planner dominates at scale.

---

## Opportunity Catalog

### Category A: User-Facing Features

---

#### A1. Natural Language Search

**What:** A freeform text input ("dog-friendly lakeside spot near Portland, July 4th weekend") that Haiku parses into structured search parameters (tags, state, dates, max_drive, from_location, source) and executes the existing search pipeline.

**Why it matters:** The search form has 8+ configurable fields. Most casual users think in sentences, not filter configurations. This bridges the gap without replacing the structured form — power users keep the form, NL input serves as the collapsed/quick-entry state.

**How it works:**
1. User types a natural language query
2. Haiku extracts structured params via tool_use (JSON schema matching existing search API params)
3. Show parsed interpretation ("Searching for: lakeside, dog-friendly near Portland, Jul 3-5") with edit link
4. Execute standard search pipeline with extracted params
5. Fall back to structured form if extraction confidence is low

**Model:** Haiku 4.5. This is structured extraction from short text — Haiku performs equivalently to Sonnet for this narrow task. Define a JSON tool schema matching the search API params.

**Prompt engineering challenges:**
- Date inference: "July 4th weekend" → 2026-07-03:2026-07-05, "next month" → relative to today
- Tag mapping: user says "waterfront" → tags: [lakeside, riverside, beach, oceanfront]
- Location normalization: "near Rainier" → from_location: "rainier" or tags: [volcanic, alpine]
- Ambiguity handling: show parsed interpretation for user correction

**Cost:** ~$0.001-0.003/query. At 50 searches/day = ~$3/month.

**Complexity:** M — prompt engineering for date inference and tag mapping is the hard part; backend already exists.

**Roadmap fit:** v1.0. Could serve as the collapsed search form state.

**Risk:** Ambiguous queries produce wrong filters. Mitigate with visible parsed interpretation + one-click edit.

---

#### A2. Post-Search Result Summarizer

**What:** After search results load, generate a 2-3 sentence summary that surfaces the signal across all results. Example: "12 sites across 4 campgrounds near Mt. Rainier. Most availability is mid-week — only Cape Disappointment has Friday-Saturday openings. Kalaloch has 3 waterfront sites if you can do Thursday-Friday."

**Why it matters:** When a search returns 10-20+ results, users must scan every card to understand the landscape. A summary surfaces clustering patterns (where availability concentrates), tradeoffs (weekend vs weekday), and standout options — enabling faster decision-making.

**How it works:**
1. After SSE search stream completes, aggregate results into a compact JSON summary
2. Send to Haiku with the user's original query params as context
3. Render as a trailing SSE event — summary card appears after all result cards
4. Only trigger when result count > 5 (small result sets are self-evident)

**Model:** Haiku 4.5. Input is structured data (search results JSON), output is a short templated summary.

**Cost:** ~$0.002-0.005/qualifying search. At 30 qualifying searches/day = ~$3/month.

**Complexity:** S — result data already exists in SSE stream; this adds one Haiku call and a new SSE event type.

**Roadmap fit:** v1.0. Complements the SmartZeroState (which handles the "no results" case — this handles the "many results" case).

**Risk:** Latency — mitigate by sending summary as trailing SSE event after results render. Progressive enhancement, not a gate.

---

#### A3. Campground Comparison

**What:** User selects 2-3 campgrounds from search results, gets a structured comparison synthesizing distance, available date overlap, vibe/character, amenity differences, and trade-offs specific to their search criteria.

**Example output:** "Both are lakeside, but Kalaloch is 30 min closer and has oceanfront sites. Moran State Park has more weekend availability but requires a ferry. If distance matters most, go Kalaloch; if you want Saturday night, Moran is your best bet."

**How it works:**
1. UI: "Compare" checkbox on result cards, "Compare selected" button when 2-3 checked
2. Collect full result data for selected campgrounds (already in client state)
3. Send to Haiku with user's search params as context
4. Render as a comparison card/modal

**Model:** Haiku 4.5. All inputs are structured (registry data + availability). Comparison is formulaic.

**Cost:** ~$0.003/comparison. Low volume — maybe 5-10/day. Under $1/month.

**Complexity:** S — prompt template with campground data slots, simple UI surface.

**Roadmap fit:** v1.0 or v1.1. Nice-to-have, not critical path.

**Risk:** Low. Informational only, no system state changes.

---

#### A4. "Why Did I Miss It?" Post-Mortem

**What:** When a watched site goes Available → Reserved between poll cycles (user missed the window), generate an explanation with actionable tuning advice.

**Example output:** "Site 47 at Ohanapecosh was available for ~2.5 hours on Tuesday at 3pm. Historically, cancellations at this campground rebook within 90 minutes on weekdays. To catch this next time: enable push notifications (you're currently ntfy-only) and consider upgrading to 5-minute polling."

**How it works:**
1. Detect missed windows: availability_history shows Available → Reserved transition between two poll snapshots
2. Calculate window duration estimate (bounded by poll interval)
3. Query historical rebook speed for this campground from availability_history
4. Feed structured data (window timing, historical stats, user's current notification config) to Haiku
5. Generate constructive, actionable recommendation
6. Show in watch detail view (reflective context, not push notification)

**Model:** Haiku 4.5. Input is structured timestamps and stats. Output is a short paragraph.

**Cost:** ~$0.001/post-mortem. Rare events — maybe 5-20/week across all users. <$0.10/month.

**Complexity:** M — the Claude call is S, but depends on availability_history analysis infrastructure (v1.1 statistical model). The data pipeline is the real work.

**Roadmap fit:** v1.1 (already planned). Claude narrates the statistical model's output.

**Risk:** Low. Read-only informational feature. Worst case is an unhelpful summary.

---

#### A5. Personalized Recommendation Reasons

**What:** Enhance the existing recommendation engine (`get_recommendation_affinities()`) with LLM-generated explanation strings instead of template-based reasons.

**Current:** "Similar tags to your recent searches"
**Enhanced:** "You've been searching for lakeside spots near Rainier — Ohanapecosh has river access, old-growth trails, and is only 15 minutes farther than your usual picks."

**How it works:**
1. Existing affinity engine scores and selects top 5 recommendations
2. For each batch of 5, send to Haiku with: user's recent search patterns (tags, states, dates), recommendation campground data (tags, vibe, drive time), and the affinity scores
3. Generate a personalized 1-2 sentence reason per recommendation
4. Cache reasons for 24 hours (recommendations don't change rapidly)

**Model:** Haiku 4.5. Structured input, short output.

**Cost:** ~$0.002/page load. With 24h caching, maybe 5-10 uncached loads/day. <$1/month.

**Complexity:** S — prompt template, 24h cache, swap out template string for LLM string.

**Roadmap fit:** v1.0 (pairs with the planned personalized recommendations feature).

**Risk:** Low. Degraded gracefully to current template strings if Haiku unavailable.

---

### Category B: Internal-Facing Ongoing (Automated)

---

#### B1. Search Query Analytics Digest

**What:** Weekly automated job that aggregates search_history data and feeds it to Claude for product intelligence analysis. Outputs: (1) most-requested regions/dates with zero availability, (2) tag combinations users search for that the registry doesn't serve well, (3) emerging pattern detection (e.g., "3x increase in Idaho campground searches"), (4) registry gap identification.

**Why it matters:** As a solo developer, you don't have time to manually analyze search logs. This is your automated product analyst — it turns raw event data into actionable insights for registry expansion, tag taxonomy improvements, and feature prioritization.

**How it works:**
1. APScheduler job or cron runs weekly (Sunday night)
2. Aggregate search_history: group by state, tags, date_range, result_count, source
3. Identify zero-result searches, most popular filter combinations, week-over-week trends
4. Send aggregated summary (not raw rows) to Haiku
5. Store structured JSON report in SQLite (new `analytics_digests` table)
6. Optionally push summary via ntfy to your phone

**Model:** Haiku 4.5. Input is tabular search data aggregated into a summary. Output is structured analysis.

**Cost:** One call/week with ~2-5K tokens of aggregated data. ~$0.01/week, effectively free.

**Complexity:** S — aggregate query, prompt, store. Could reuse the APScheduler infrastructure already running for watch polling.

**Roadmap fit:** Standalone, implement anytime. Informs v1.0 personalization and registry expansion decisions.

**Risk:** None. Internal-only, no user impact if output is unhelpful.

---

#### B2. Notification Quality Feedback Loop

**What:** Monthly batch job that correlates notification messages with user actions to identify what notification patterns drive engagement.

**How it works:**
1. Join notification_log with event tracking (book_click events within 1 hour of notification)
2. Build dataset: (notification_text, urgency_score, campground_popularity, time_of_day, clicked_yes_no)
3. Feed batch to Haiku: "Which notification patterns correlate with booking clicks? What phrasings or urgency levels drive action?"
4. Output: suggested prompt adjustments for the notification enrichment system
5. Store analysis; apply suggestions after manual review

**Why it matters:** The v0.7 notification enrichment generates contextual messages, but there's no feedback loop. This closes it — over time, notification quality improves based on actual user behavior rather than prompt intuition.

**Model:** Haiku 4.5. Pattern recognition on structured data.

**Cost:** ~$0.005/batch, run monthly. Effectively free.

**Complexity:** S — requires joining notification_log with event tracking data. The analysis prompt is straightforward.

**Roadmap fit:** Standalone. Improves v0.7's notification enrichment incrementally.

**Risk:** Small sample sizes may produce unreliable patterns at low user volume. Only apply suggestions after manual review. More valuable as user base grows.

---

#### B3. Availability Anomaly Narrator

**What:** When the v1.1 statistical model detects an anomaly (unusual availability at a historically-full campground), Claude generates the user-facing alert text with rich historical context.

**Example:** "Ohanapecosh just released 8 sites for July 12-14 — this hasn't happened since last March. These typically book within 2 hours at this time of year."

**How it works:**
1. v1.1 anomaly detector flags the event with structured data (campground, dates, z-score, historical baseline)
2. Haiku generates a contextual alert message combining: the anomaly data, historical booking speed for this campground, day-of-week/holiday context
3. Dispatch via existing notification channels

**Model:** Haiku 4.5. Structured input (anomaly data + historical stats), short output.

**Cost:** Anomalies are rare — maybe 10-30/month across all watched campgrounds. ~$0.01/month.

**Complexity:** S (the Claude integration). Depends entirely on v1.1 anomaly detection being built first.

**Roadmap fit:** v1.1 (already planned as part of anomaly-based deal alerts).

**Risk:** Low. Extension of existing notification enrichment pattern.

---

### Category C: Internal-Facing One-Time (Batch)

---

#### C1. Registry Description Rewrite

**What:** Transform bureaucratic RIDB descriptions into user-friendly campground summaries. For all 741 campgrounds, generate: (1) a 1-sentence elevator pitch for search result cards, (2) a 2-3 sentence "what makes this place special" description, (3) a "best for" label (families, backpackers, RVs, solitude-seekers).

**Why it matters:** RIDB descriptions are institutional ("This facility offers camping opportunities in a forested setting adjacent to recreational waterways..."). Users scanning 15 results need to quickly distinguish options. Better descriptions improve discovery quality for every single search.

**How it works:**
1. Clone the existing `enrich` CLI pattern
2. For each campground: send name + RIDB description + existing tags to Haiku
3. Return structured JSON: `{elevator_pitch, description, best_for}`
4. Add new columns to registry schema
5. Render elevator_pitch in result cards (before expand), full description in expanded view

**Model:** Haiku 4.5. Same pattern as existing tag extraction — proven at scale.

**Cost:** 741 campgrounds x ~500 tokens each = ~350K tokens. Under $0.15 total.

**Complexity:** S — clone existing `enrich` CLI pattern, add new registry columns, update result card rendering.

**Roadmap fit:** Pre-v1.0. Improves every search result immediately with minimal effort.

**Risk:** Low. Review a sample of 20-30 before bulk-writing. Descriptions are supplementary, not authoritative. Can always regenerate.

---

#### C2. Historical Availability Pattern Extraction

**What:** Analyze accumulated availability_history data to extract qualitative booking patterns per campground, producing "Booking Tips" for campground detail views.

**Example output:** "Ohanapecosh fills weekends 6 months in advance. Weekday cancellations appear 2-3 weeks before the date, mostly Tuesday-Wednesday. Peak season is June-September. FCFS overflow sites sometimes open in shoulder season."

**How it works:**
1. Aggregate availability_history into per-campground time-series summaries (availability rates by day-of-week, days-before-date cancellation distribution, seasonal patterns)
2. Per-campground: send aggregated stats to Haiku for pattern narration
3. Cross-campground: send all summaries to Sonnet for regional trend synthesis
4. Store as structured JSON + human-readable text per campground
5. Render as "Booking Tips" section in expanded campground cards

**Model:** Haiku for per-campground (structured time-series → narrative). Sonnet for cross-campground synthesis (finding regional trends across 741 campgrounds).

**Cost:** Per-campground: ~$0.001 x 741 = ~$0.75. Cross-campground synthesis: ~$0.05. Under $1 total.

**Complexity:** M — the Claude calls are simple; the data aggregation pipeline (availability_history → per-campground summaries) is the real work.

**Roadmap fit:** Between v1.0 and v1.1. Produces user-visible booking tips immediately. Also validates whether availability_history data is rich enough for v1.1's statistical model.

**Risk:** Data may be too sparse if polling history is < 6 months. Mitigate by only generating patterns for campgrounds with >30 days of observation, and flagging confidence levels. Re-run periodically as data accumulates.

---

#### C3. Tag Taxonomy Audit

**What:** Feed Claude the full tag list, frequency distribution, and sample campgrounds per tag. Identify: (1) tags that should be merged (e.g., overlapping semantics), (2) tags too broad to be useful for filtering, (3) missing tags suggested by descriptions but not in the 29-tag vocabulary.

**Why it matters:** The tag vocabulary was designed once during initial enrichment. Tag quality directly affects search filtering accuracy and v1.0 personalization (tag affinity scoring). A cleaner taxonomy = better recommendations.

**How it works:**
1. Export full tag data: tag → count, tag → sample campground names+descriptions
2. Single Sonnet call with full taxonomy context
3. Output: proposed merges, additions, removals with rationale
4. Manual review and implementation
5. Re-run tag extraction for affected campgrounds

**Model:** Sonnet 4. Requires reasoning about semantic relationships and making taxonomy design judgment calls. Haiku would produce a flatter, less useful analysis.

**Cost:** One call, ~$0.05.

**Complexity:** S — data export, one prompt, manual review. If taxonomy changes, re-run existing `enrich` CLI for affected entries.

**Roadmap fit:** Pre-v1.0. Directly improves personalization quality.

**Risk:** None. Output is a recommendation for manual review, not an automated change.

---

## Cost Summary

### One-Time Batch Costs
| Opportunity | Cost |
|---|---|
| C1. Registry Description Rewrite | ~$0.15 |
| C2. Historical Pattern Extraction | ~$1.00 |
| C3. Tag Taxonomy Audit | ~$0.05 |
| **Total one-time** | **~$1.20** |

### Ongoing Monthly Costs (all opportunities deployed)
| Opportunity | Monthly Cost |
|---|---|
| A1. Natural Language Search | ~$3.00 |
| A2. Post-Search Summarizer | ~$3.00 |
| A3. Campground Comparison | ~$1.00 |
| A4. Post-Mortem (v1.1) | ~$0.10 |
| A5. Recommendation Reasons | ~$1.00 |
| B1. Search Analytics Digest | ~$0.05 |
| B2. Notification Quality Loop | ~$0.01 |
| B3. Anomaly Narrator (v1.1) | ~$0.01 |
| **Total ongoing** | **~$8.17/month** |

**Context:** Break-even is 2-4 Pro subscribers at $5/month. Current Anthropic spend is dominated by the trip planner (~$0.03-0.10/session). All new opportunities combined add ~$8/month — roughly 2 additional Pro subscribers to cover.

---

## Priority Ranking

### Assessment Matrix

| # | Opportunity | User Impact | Strategic Value | Effort | Dependencies | Timing |
|---|---|---|---|---|---|---|
| C3 | Tag Taxonomy Audit | M | H | S | None | Pre-v1.0 |
| C1 | Registry Description Rewrite | H | H | S | None (clone enrich pattern) | Pre-v1.0 |
| B1 | Search Query Analytics Digest | L (internal) | H | S | APScheduler (exists) | Pre-v1.0 |
| A2 | Post-Search Result Summarizer | H | M | S | SSE stream (exists) | v1.0 |
| A5 | Personalized Recommendation Reasons | M | M | S | Recommendation engine (v1.0 planned) | v1.0 |
| A1 | Natural Language Search | H | H | M | Search API (exists) | v1.0 |
| A3 | Campground Comparison | M | L | S | Search results (exists) | v1.0 / v1.1 |
| C2 | Historical Availability Pattern Extraction | M | H | M | Sufficient polling history (months of data) | v1.0-v1.1 bridge |
| A4 | "Why Did I Miss It?" Post-Mortem | M | H | M | v1.1 statistical model, availability_history pipeline | v1.1 |
| B3 | Availability Anomaly Narrator | M | H | S | v1.1 anomaly detector | v1.1 |
| B2 | Notification Quality Feedback Loop | L (internal) | M | S | Meaningful user base for sample size | Opportunistic |

### Ordered Priority List

**Tier 1: Do Now (pre-v1.0) — low effort, immediate payoff**

1. **C3 - Tag Taxonomy Audit** — One Sonnet call, $0.05, no code changes; directly improves the quality of every search filter and the v1.0 personalization engine that depends on tag affinity.
2. **C1 - Registry Description Rewrite** — Clones the proven `enrich` pattern for $0.15; replaces bureaucratic RIDB descriptions in every result card, improving discovery quality across the board with minimal dev time.
3. **B1 - Search Query Analytics Digest** — Gives you a free automated product analyst that identifies registry gaps and informs what to build next; trivial to wire into existing APScheduler.

**Tier 2: Ship with v1.0 — user-facing features that raise the bar**

4. **A2 - Post-Search Result Summarizer** — Small effort (one trailing SSE event), high user impact; surfaces the signal when search returns 10+ cards and complements the existing SmartZeroState for the "too many results" case.
5. **A1 - Natural Language Search** — The highest-impact single feature on this list, ranked 5th only because the prompt engineering for date inference and tag mapping is medium effort; the collapsed NL input + visible parsed interpretation is the ideal v1.0 search UX.
6. **A5 - Personalized Recommendation Reasons** — Cheap upgrade from template strings to contextual explanations; pairs naturally with the v1.0 recommendation feature already on the roadmap.
7. **A3 - Campground Comparison** — Nice-to-have that rounds out the search experience; small effort, low cost, but lower strategic value since it doesn't drive Pro conversion or enable future features.

**Tier 3: Ship with v1.1 — depend on the statistical model**

8. **C2 - Historical Availability Pattern Extraction** — The bridge between v1.0 and v1.1; validates whether your polling history is rich enough for statistical modeling while producing user-visible "Booking Tips" immediately.
9. **A4 - "Why Did I Miss It?" Post-Mortem** — Compelling Pro-tier feature that turns missed cancellations into upgrade motivation; blocked on the v1.1 availability_history analysis pipeline.
10. **B3 - Availability Anomaly Narrator** — Natural extension of the existing notification enrichment pattern; trivial Claude integration but fully blocked on the v1.1 anomaly detector.

**Tier 4: Opportunistic — build when conditions are right**

11. **B2 - Notification Quality Feedback Loop** — Sound idea but premature; with a small user base the sample sizes will produce unreliable patterns. Revisit when you have 20+ active watch users generating meaningful notification-to-action data.

### Summary

The first three items (C3, C1, B1) cost under $1.25 total and require roughly 1-2 days of work. They improve every search result and give you product intelligence — do them before v1.0 ships. The v1.0 tier adds ~$7/month in ongoing Anthropic costs (covered by ~2 additional Pro subscribers). The v1.1 tier is blocked on the statistical model but the Claude integration cost is negligible once the data pipeline exists.
