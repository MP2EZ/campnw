# Booking Enrichment Ideas

Exploratory notes on improving the booking handoff from Campable to provider sites. Not a roadmap commitment — input to one.

## Problem

Today, our booking deep links vary in quality:

| Provider | Quality | Behavior |
|---|---|---|
| Recreation.gov | Excellent | `recgov_campsite_booking_url()` lands on the booking page with site, dates, and facility pre-filled. One click to book. |
| OR / ReserveAmerica | Partial | Lands on the park's availability calendar with `arrivalDate` positioned. User still picks the site visually. |
| WA / GoingToCamp | Poor | Lands on a results page with `resourceLocationId` and `searchTime`. User must find the site on a map and click through. |

The asymmetry is structural: rec.gov uses URL-as-state. GoingToCamp and (legacy) ReserveAmerica are server-session apps where booking state lives behind POSTs.

## Critical constraint: WA has no human site names

Confirmed in the codebase:

- `src/pnw_campsites/providers/goingtocamp.py:226` — site labels are synthesized as `WA-{resource_id}` (e.g., `WA--2147482394`).
- `web/src/App.tsx:1129` — the UI displays a banner: "site data is limited — names, types, and capacity aren't available."
- CLAUDE.md confirms: "Site names not available via API — identified by resource ID."

The internal resource ID is meaningless to the user *and* GoingToCamp's UI doesn't accept it as input. So any "copy ID and paste on the provider site" pattern is broken for WA until we have human-readable site names (e.g., "Loop B, Site 142").

**This makes registry enrichment for WA the prerequisite for most other WA improvements.**

## Reframe: discovery friction vs checkout friction (2026-05-03)

After shipping A1 / B6 / OR deep-linking, the remaining friction in "search → reservation" isn't on Campable's side anymore — it's on the destination provider's checkout page. **The slow step is filling out the booking form** (equipment, party size, vehicle info, name/address/phone/email, payment) once the user lands there. That's the 2–3 minutes where bookings actually die.

Every Tier A–C item below addresses *Campable-side* friction (better signal, faster notifications, deeper deep links). They were the right work to ship first because Campable's side was the easier surface. But going forward, the highest-leverage moves are about **bypassing, pre-filling, or delegating the destination-side checkout form** — see new Tier D below.

The ceiling on Tier A–C is "user clicks Book and lands on the booking page in one click." That ceiling is now reached for rec.gov and OR; WA reaches it once A2 ships. Tier D is about everything *after* that landing.

## Tier A — Ship these, in order

### A1. Cache human site + loop names for WA parks (one-time enrichment per park)

**✅ Shipped 2026-05-03 (PR #5 / #7).** Followed by PR #9 / #10 which extended the cache to per-site `max_capacity`, `min_capacity`, and `allowed_equipment` (the latter stored, not yet consumed). Production cache holds 6,984 sites + 364 loops. WA search now shows real names like `Site 91 · Loop 3` instead of `WA--2147481xxx`.

**Diagnostic outcome (2026-05-03):** No Playwright needed. DevTools capture of the live GTC booking flow surfaced two undocumented endpoints the frontend hits on every search, both reachable via our existing `curl_cffi` chrome131 session with no auth:

- **`/api/resourcelocation/resources?resourceLocationId={parkId}`** — returns every site for the park as a dict keyed by resource ID. Each entry has `localizedValues[0].name` (the human site label, e.g., `"188"`, `"MT8"`, `"S7-Rosario Picnic Shelter"`) and `mapIds` linking the site to its loop. Also includes capacity, equipment, attributes, and photos. ~1.6 MB for Deception Pass (360 sites, 100% named).
- **`/api/maps?resourceLocationId={parkId}`** — returns the park's full map tree including all leaf loop maps. Each has `localizedValues[0].title` (e.g., `"Lower Loop A"`, `"Cabins"`) and `description` (e.g., `"Sites 79-145 (Serviced = 81-87, ...)"`).

These were missed in prior endpoint guessing because the param we tried (`mapId=`) is silently ignored — only `resourceLocationId=` works on `/api/maps`. The `/api/resourcelocation/resources` endpoint we never guessed at all. The lesson: drive the live UI with DevTools before guessing endpoint patterns.

**Implementation shape:**

- Add `get_resource_metadata(resource_location_id)` and `get_park_maps(resource_location_id)` methods to `GoingToCampClient`.
- New seed script: 167 parks × 2 calls = ~334 one-time HTTP requests (re-run quarterly, matches the deferred GoingToCamp registry-refresh cadence in the roadmap).
- Schema migration to store site names + loop names against resource/map IDs. Likely two new tables (`wa_state_sites`, `wa_state_loops`).
- Update `goingtocamp.py:226` to look up real names from the cache instead of synthesizing `WA-{res_id}`.
- Remove the "site data is limited" warning at `App.tsx:1129`.

Site labels are non-uniform strings (`"188"`, `"MT8"`, `"S7-Rosario Picnic Shelter"`) — store as `TEXT NOT NULL` rather than parsing prefixes.

**Generalization across diverse parks (2026-05-03):** Tested 7 parks spanning the size and type range — Deception Pass (360 sites), Steamboat Rock (275, desert), Lake Wenatchee (209, mountain), Moran (153, island), Bay View (94, coastal), Hope Island (12, marine), Posey Island (2, marine). Findings:

- **1,105/1,105 sites have human names** (100%) across the full sample.
- **23/23 leaf loop maps have titles** (100%) — descriptive names like "Banks Lake", "Mountain Lake", "Cabins, Group Site, Shelter".
- **Zero sites appear in multiple loops** → clean 1:N relationship, no many-to-many table needed.
- **2 orphan sites total** (0.18%, both at Deception Pass and Bay View) have no `mapIds`. Render with `loop = "(unassigned)"` — not worth special casing.

This locks the schema to `wa_state_loops(map_id PK, park_fid FK, title, description)` + `wa_state_sites(resource_id PK, park_fid FK, name, loop_map_id nullable FK)`.

**Effort:** ~4–6 hours. **Impact:** unlocks A2, A3, B5 for WA. Removes the `WA-{opaque-id}` UX everywhere.

### A2. Better booking-action UI on the result card itself

Replace the single "Book" link with a card-level action that acknowledges the friction visually per provider:

- **Rec.gov:** "Book Now" → opens deep link. No change.
- **OR / RA:** "Open RA & copy site #" → `navigator.clipboard.writeText(siteNumber)` + `window.open()`. Site number is shown as a copyable chip on the card.
- **WA (post-A1):** Same pattern as OR — copy human site name, open GTC park view with date pre-filled.

Inline acknowledgement of the gap ("the page that opens won't have this site pre-selected — paste the site number in the search box") instead of an interstitial page. **No extra navigation. No popover-blocker risk.**

**Effort:** half-day after A1 lands. **Impact:** removes the "I clicked book and now I'm lost" failure mode.

### A3. Site name + dates in push notification body

When a watch fires, the ntfy/Pushover body includes the site name, dates, and park (e.g., `Deception Pass · Loop B Site 142 · Jun 5–7`). Long-press to copy works natively on iOS/Android.

The watch firing is the *highest-stakes* booking moment (cancellations book in minutes). Putting actionable data in the notification body itself avoids the "open app, find result, copy info" path entirely.

**Effort:** ~1 hour. **Impact:** the most time-critical UX moment becomes ~10 seconds faster.

## Tier B — Worthwhile after A

### B4. Watch-fire `.ics` calendar invites (universal)

Every watch hit also generates a downloadable `.ics` event with the booking URL, site name, dates, and a "what to click" cheat-sheet in the description. Description fields support unlimited text — perfect home for provider-specific instructions.

Differs from a push because the calendar entry persists and is searchable later ("did I get notified about Ohanapecosh in May?").

**Effort:** half-day. **Impact:** moderate; complements pushes.

### B5. Rec.gov rolling-release window calendar invites

Rec.gov releases sites on a rolling 6-month window at 7am MT (with **per-facility variance** — Acadia is 2 months, lottery sites differ). For watches on far-future dates, generate `.ics` events for the exact release moment with the (already-perfect) deep link.

**Caveat I overstated last pass:** "deterministic" is wrong. The default is 6mo / 7am MT for most western US campgrounds, but per-facility overrides exist. Implementation needs:

- Sensible default (6mo / 7am MT)
- Per-facility override stored in registry
- Hand-curated overrides for known exceptions (manual, growable list)

**Effort:** 1 day for default behavior, ongoing for overrides. **Impact:** high for the "I want a popular site 6 months out" use case (rec.gov's hardest UX moment).

### B6. URL parameter sniff on RA and GTC

**✅ Shipped 2026-05-03 (PR #4).** OR provider's `_build_booking_url` now constructs the per-site RA deep link below; every OR search-result window ships with a fully deep-linked `booking_url`. GTC sniff intentionally not run — A1 was the right path for WA.

**RA outcome (2026-05-03):** ReserveAmerica supports rec.gov-quality per-site deep linking out of the box:

```
https://www.reserveamerica.com/explore/{slug}/OR/{park_id}/{site_id}/campsite-booking?arrivalDate=YYYY-MM-DD&departureDate=YYYY-MM-DD
```

Verified on Fort Stevens (site L03, RA site_id `3171`): page loads with H2 `"Site L03, Loop L"`, per-day calendar for that site, amenities, and a "Book Now" button. Same shape as `recgov_campsite_booking_url`.

**Crucially, the OR provider already extracts the site ID we need.** `src/pnw_campsites/providers/reserveamerica.py:246` pulls `record["id"]` into `site_id` — we just don't construct deep links from it. Implementation is a new helper `or_state_campsite_booking_url(slug, park_id, site_id, start_date, end_date)` plus wiring it into the search response per-site, in the same place `recgov_campsite_booking_url` is used. Probably 30–60 minutes including tests. The slug already lives in `campgrounds.booking_url_slug`.

This collapses OR's UX gap entirely with no enrichment work — different from WA's A1 path. Worth shipping ahead of A1 since it's small, isolated, and immediately improves the OR experience.

**GTC sniff:** Not run; A1 (which already exists in scope) is the right path for WA, not URL sniffing.

**Effort (RA only):** ~1 hour. **Impact:** OR per-site deep linking matches rec.gov.

## Tier C — Opportunistic, low cost

### C7. Claude-narrated push notifications

We already have Haiku infra from `pnw_campsites enrich`. Turn raw alerts into context-aware copy:

> "Three lakeside sites just opened at Deception Pass for Fri–Sun. These usually book in under an hour."

Cost: ~$0.0001 per notification. Latency: ~300ms before push fires. Sets up the v1.3 Predictions+ work later.

**Effort:** half-day. **Impact:** humanizes the alert; not a mechanism win.

### C8. Outreach to providers about official partnership

One email to rec.gov dev relations + WA State Parks IT asking about affiliate / per-site cart-link programs. Cost is one email per recipient. Likely no response, but the upside is a contractual blessing.

**Effort:** 30 min. **Impact:** lottery ticket.

## Tier D — Checkout friction reduction (2026-05-03)

The four classes of moves that compress the destination-side form-filling step. None of them have shipped or even been spiked yet; D1 and D4 are the immediate research priorities.

### D1. Bookmarklet that pre-fills the destination booking form

User saves a profile on Campable (equipment, party size, vehicle info, contact info). A bookmarklet they drag to their bookmarks bar recognizes when they're on a rec.gov / RA / GTC booking page and auto-fills the form fields with their saved values. User just clicks "Reserve" and enters payment.

- **Pros:** Actually compresses checkout from 2–3 min to ~30 sec. ~50 lines of JS, no extension store review. Pairs with the existing deep-link work.
- **Cons:** Distribution friction (drag-to-bookmarks is a >50% drop-off action). Modern Angular/React forms may reject programmatic `input.value =` writes; need to dispatch synthetic events. Maintenance treadmill on every form change.
- **Mitigations on distribution:** Camping power users (Campable's core demographic) are more motivated than average to install power-user tools. Onboarding with a 30-second video could lift install rate.

**Status:** Research scheduled — see "Recommended next step" below. Reverses the prior "Killed: bookmarklet" entry; rationale changed once we acknowledged that the WA side of the deep-link work has hit its ceiling and checkout is the next bottleneck.

**Effort to spike:** 2–3 hours (DevTools form-field map per provider + proof-of-concept bookmarklet against one provider). **Effort to ship for one provider:** ~half-day. **Effort to ship for all three:** ~2 days plus ongoing maintenance.

### D2. Browser extension (D1's polished form)

Same as D1 but as a Chrome/Firefox extension: auto-runs on every visit to a booking page, no manual click. Adds polish, removes the "drag a bookmarklet" friction.

- **Pros:** Lower per-use friction once installed.
- **Cons:** Higher install friction (Chrome Web Store review + permissions warning). Takes ~1 week to ship vs. ~1 day for bookmarklet. Worth it once the bookmarklet has proven user demand.

**Status:** Defer until D1 has telemetry showing "users want this" (e.g., bookmarklet adoption + repeat use). Don't build extension first.

### D3. Account linking via provider OAuth

User authorizes Campable to act against their rec.gov / GTC / RA account. Pre-favorite sites, pre-fill cart where the API allows, store equipment/contact info per-account.

- **Pros:** The cleanest theoretical path — uses providers' own systems, no DOM scraping, no maintenance treadmill.
- **Cons:** **Likely blocked.** Rec.gov and Aspira (RA + GTC) are government / B2B platforms; neither offers public OAuth for third-party integrations. The only paths are (a) undocumented APIs, (b) credential-proxy where Campable holds user passwords (security + ToS minefield), or (c) formal partnership we won't get pre-PMF.

**Status:** Research blocked unless one of those three paths opens. Worth one email per provider asking (folds into C8) but don't plan around it.

### D4. AI concierge with computer use (the differentiated bet)

User submits intent + payment authorization on Campable. A Claude-with-computer-use agent navigates the destination site, fills forms, gets to the payment step, surfaces a confirmation screen for the user to approve. **The closest thing to "book directly from Campable" that's actually buildable.**

- **Pros:** Genuinely seamless from the user's POV. Differentiates Campable from every other discovery tool. Degrades gracefully — if the agent fails, user falls back to manual booking. Compute cost (~$0.50/booking) is acceptable for a paid feature.
- **Cons:** **ToS risk is non-zero** — rec.gov "automated reservation" prohibition is the load-bearing concern; the gray area is whether "user-watched, user-approved automation" falls outside it. Maintenance treadmill on every UI change. Payment-handoff design needs careful thought (probably hand off the cart link with everything filled, user enters card themselves). Latency budget per booking could be 30–60 seconds.

**Status:** Research scheduled — see "Recommended next step." Distinct from the killed "full middle-man booking" because the user is in the loop (intent submitted explicitly, watching the agent, entering payment themselves) — different liability and ToS profile than headless mass automation.

**Effort to research:** ~3–4 hours (computer-use API status + ToS deep-read + architecture sketch + payment-handoff design + comparable products). **Effort to prototype on one provider:** ~1 week. **Effort to productize:** multi-week.

### D5. Human concierge (the wedge to test demand)

User submits booking intent + payment authorization. A human (initially: you) does the booking on their behalf within a few hours. **Charge for it ($5–10/booking?) to validate willingness-to-pay before any automation work.**

- **Pros:** Zero technical risk. Real travel agencies were built on exactly this. Validates the "users will pay to skip the form" hypothesis cheaply. Shapes what D4's automated version needs to do (you'll know exactly which fields matter, which providers fail, where things go wrong).
- **Cons:** Doesn't scale past a few bookings/day. Requires you to actually do bookings.

**Status:** Worth considering as a paid-tier wedge once Campable has any paying-customer cohort. Not urgent today.

**Effort:** Stripe checkout setup + a Notion form + you. ~1 day.

## Don't / Killed

### ~~Bookmarklet or browser extension~~ → moved to D1/D2

**Originally killed** for distribution friction. **Reinstated 2026-05-03** under Tier D after acknowledging that Campable-side deep-link work has hit its ceiling and the next bottleneck is destination-side checkout. The distribution friction is real but the value has grown: not "a slightly better booking link" (the original framing) but "compress 2–3 minutes of form-filling to 30 seconds" (the actual problem).

### Server-side Playwright "click-through" service (runtime)

A backend that opens a browser per booking click, navigates the destination site, hands back a session URL. Maintenance treadmill (every WAF/UI tweak breaks it), latency cost on every click, and the discovery moat is more durable than a booking-automation moat would be.

**Note:** A1 was originally scoped to use Playwright as a periodic enrichment job (different risk profile than runtime). The 2026-05-03 diagnostic obviated even that — A1 is now plain HTTP via the existing `curl_cffi` session.

### Full middle-man booking (Campable takes payment, completes the reservation headlessly)

Hard no — distinct from D4 (AI concierge) which keeps the user in the loop.

- **ToS.** Rec.gov explicitly prohibits automated reservation; the headless / unattended interpretation is the load-bearing one. Campnab/Campflare have lived in the gray zone for years by *only monitoring*. There's a reason.
- **CAPTCHA + 2FA** would force us to handle user credentials.
- **Payment liability and refund disputes.** Provider refunds go to the original card; we'd inherit chargeback handling.
- **Strategic risk.** The discovery moat (registry + filtering + watches) is defensible. A booking-automation moat is a regulatory cat-and-mouse game.

**What's different about D4:** the user explicitly submits intent, watches the agent navigate, and enters their own payment. That's closer to "power-user automation tool" than "Campable becomes a booking platform" — different ToS surface and different liability shape, though still non-zero.

The right framing of "1-click booking" is *not* "we book for you headlessly" — it's either "we get you to the booking page faster than anyone else" (Tier A–C) or "we fill out the form for you while you watch and confirm" (D4).

### Interstitial "how to book" page

Rejected on second pass — adds a click and a decision in flow. Same content lives better as inline UI on the result card (A2).

## Open questions / things to verify

1. ~~**A1 feasibility:** Does GoingToCamp expose human site names anywhere accessible without per-click automation?~~ **Answered 2026-05-03 (yes — see A1 above for endpoints).**
2. **B5 release-time data:** Is per-facility booking-window length anywhere in RIDB metadata? If yes, no manual overrides needed.
3. ~~**B6 RA params:** Does the new ReserveAmerica system honor a `siteId=` query param?~~ **Answered 2026-05-03 (yes — see B6 above; per-site URL pattern verified for Fort Stevens).**
4. **A3 push providers:** Confirm both ntfy and Pushover render long-press copy correctly on iOS and Android. Both should — but verify before relying on it.
5. **Conflict with existing watch v2:** The push and ICS work in A3/B4 should be reviewed against whatever notification format watches currently emit, to avoid double-sending.
6. **D1 feasibility:** Can a bookmarklet actually populate Angular/React form fields on rec.gov / RA / GTC, or do they reject programmatic writes? Need a DevTools form-field map per provider, then a proof-of-concept bookmarklet against one provider.
7. **D4 ToS analysis:** Does "user-watched, user-approved" automation fall outside the rec.gov / Aspira "automated reservation" prohibition? Read the exact terms language; lay out the gray areas (this is a strategic call, not a legal one).
8. **D4 architecture & cost:** What's the per-booking compute cost and latency budget for Claude computer-use agent navigating a multi-step booking flow? Sandboxed VM per session or browser pool? How does failure recovery work?

## Recommended next step

**Tier A–C is largely done; the new frontier is Tier D.** Concretely, the next session should be **research on D1 (bookmarklet) + D4 (AI concierge), in that order:**

1. **D1 research first** (~2–3 hours). Concrete deliverable: form-field map per provider + bookmarklet proof-of-concept against one provider. Outputs are reusable for D4 (the agent needs the same field knowledge). Decision gate at the end: "bookmarklet saves N seconds of X% of fields" → ship or don't.
2. **D4 research second** (~3–4 hours). Strategy doc covering computer-use API status, ToS analysis, architecture sketch, payment-handoff design. Decision gate: green-light a prototype or fall back to D1 only.

If D1 turns out to shave 80% of friction, the marginal value of D4 drops a lot and we may not need it. Worth knowing before committing to D4's complexity.

Optional in parallel: **D5 (human concierge) as a free wedge** to validate willingness-to-pay before any technical work. Stripe + Notion form + a few hours of your time per booking.

The Tier A–C residual work (A2 inline UI, A3 push body, B4 ICS invites, B5 rec.gov release calendars) is real polish but no longer the highest-leverage frontier. Slot it after Tier D research clarifies what's worth investing in.
