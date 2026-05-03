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

## Tier A — Ship these, in order

### A1. Cache human site + loop names for WA parks (one-time enrichment per park)

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

## Don't / Killed

### Bookmarklet or browser extension

Distribution friction (drag-to-bookmarks or Chrome Web Store install) kills adoption pre-PMF. Power-user feature at best — revisit only if a paying-customer cohort asks for it.

### Server-side Playwright "click-through" service (runtime)

A backend that opens a browser per booking click, navigates the destination site, hands back a session URL. Maintenance treadmill (every WAF/UI tweak breaks it), latency cost on every click, and the discovery moat is more durable than a booking-automation moat would be.

**Note:** A1 was originally scoped to use Playwright as a periodic enrichment job (different risk profile than runtime). The 2026-05-03 diagnostic obviated even that — A1 is now plain HTTP via the existing `curl_cffi` session.

### Full middle-man booking (Campable takes payment, completes the reservation)

Hard no:

- **ToS.** Rec.gov explicitly prohibits automated reservation. Campnab/Campflare have lived in the gray zone for years by *only monitoring*. There's a reason.
- **CAPTCHA + 2FA** would force us to handle user credentials.
- **Payment liability and refund disputes.** Provider refunds go to the original card; we'd inherit chargeback handling.
- **Strategic risk.** The discovery moat (registry + filtering + watches) is defensible. A booking-automation moat is a regulatory cat-and-mouse game.

The right framing of "1-click booking" is "we get you to the booking page faster than anyone else," not "we book for you."

### Interstitial "how to book" page

Rejected on second pass — adds a click and a decision in flow. Same content lives better as inline UI on the result card (A2).

## Open questions / things to verify

1. ~~**A1 feasibility:** Does GoingToCamp expose human site names anywhere accessible without per-click automation?~~ **Answered 2026-05-03 (yes — see A1 above for endpoints).**
2. **B5 release-time data:** Is per-facility booking-window length anywhere in RIDB metadata? If yes, no manual overrides needed.
3. ~~**B6 RA params:** Does the new ReserveAmerica system honor a `siteId=` query param?~~ **Answered 2026-05-03 (yes — see B6 above; per-site URL pattern verified for Fort Stevens).**
4. **A3 push providers:** Confirm both ntfy and Pushover render long-press copy correctly on iOS and Android. Both should — but verify before relying on it.
5. **Conflict with existing watch v2:** The push and ICS work in A3/B4 should be reviewed against whatever notification format watches currently emit, to avoid double-sending.

## Recommended next step

If this becomes work: **A1 first.** Without it, A2 and A3 can't reach WA and the bulk of new value goes to OR/rec.gov only (where the UX is already best). A1 is also the one piece that's a prerequisite, not a polish — it changes what's achievable, not just how it looks.
