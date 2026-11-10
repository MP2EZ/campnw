# v1.48 "Answer-first Results": implementation plan

**Status:** planning (2026-11-07). **Design:** https://claude.ai/artifact/1nu7q5px7YSbTBeocHVPRv (private canvas, 5 artboards). **Roadmap:** `docs/ROADMAP.md` → v1.48.

## Goal

Replace the form-first results page with one that answers the search in a sentence, then shows places grouped by drive time. Each card shows the bookable windows (with counts that fit the user's party and rig), what happens on booking, and what can be watched. Every claim on the page must come from data the backend actually has. Where it doesn't, the page says so.

## Where the code is today (mapped 2026-11-07)

- **`web/src/App.tsx` (1,282 lines)** holds `SearchForm` (L165), `SearchSummaryBar` (L542), `FirstVisitState` (L599), the NL bar, the results skeleton, and the whole results block (≈L1111–1274), all inline and unexported.
- **`ResultCard.tsx` (481 lines)** renders a collapsed header (badges, weather, pitch). Its expandable body holds photo/postcard, `DateBlockView` / `SiteView`, booking links, `WatchButton` and `SaveToTripButton`.
- **`useSearch`** consumes the SSE stream: `parsed_params`, `progress`, `summary`, `warnings`, `coverage`, `not_released`, `diagnosis`, and per-campground results. Coverage (#169) and not-released (#171–#173) data are already in `results`. It's the right data layer to keep.
- **The API already sends per-window `site_name`, `loop`, `campsite_type`, `max_people`, `is_fcfs` and `booking_url`** (`WindowResponse`, `routes/search.py:46`). For WA these are placeholders: type is `STANDARD` and the site name is a resource id for unseeded parks.
- **Order.** The backend orders by `(boat_in, drive_minutes)` (#170), and the frontend doesn't re-sort or group.
- **Map.** `MapView` is lazy Leaflet + markercluster, prop-less, and reads `SearchContext`. There is no list↔map selection, only `?focus=`.
- **Watches** support facility + dates + `min_nights` + `days_of_week`, plus template watches. There are no site-type or party filters.
- **AI summary.** One Haiku call per search when more than 5 results; it arrives as an SSE `summary` frame.
- **Mobile is CSS only** (640px breakpoint, `hover: none`), with no JS viewport logic. CSP already allows Google Fonts.

## Decisions

Recommendations are marked ✅. Items marked ❓ need the product owner.

| # | Decision | Recommendation |
|---|----------|----------------|
| D1 | How to ship a rewrite safely | ✅ Build v2 in a new `web/src/results/` module behind a `results_v2` flag: a PostHog feature flag, plus a `?ui=v2` / `?ui=v1` override. v1 stays untouched until the flip. Funnel events carry `ui_version` so the two can be compared. |
| D2 | Data layer | ✅ Keep `useSearch` / `SearchContext`. Add derived selectors as pure functions, not new fetches. |
| D3 | Chip model | ✅ A pure `buildWindowChips(result, search)` returns `{start, end, label, open, fit, few, status: open\|full\|not_released}`. It groups windows by `(start, end)` like today's `groupByDateBlock`. Weekend searches give one chip per weekend; exact dates give one chip; long flexible ranges give the earliest N chips plus "+k more". |
| D4 | "Full" chips need the windows that *weren't* returned | ✅ Derive the candidate windows client-side from the search: dates, `days_of_week`, nights. A candidate with no available window and no NYR nights is **Full**. Pure function, TDD. |
| D5 | Fit-aware counts | ✅ Add a `who` search param (people, equipment: tent / van / trailer + length). The backend filters windows by `max_people` / `campsite_type`, and for WA by decoded equipment (P1a). Parks without type data say "Site types not listed yet" and are never silently dropped. |
| D6 | AI summary on the results page | **Decided 2026-11-07: dropped.** Gated behind `SEARCH_SUMMARY_ENABLED` (default off), which turns it off on the current site too and stops the Haiku call per search. Possible follow-up: an on-demand "Compare these for me" with structured inputs and no urgency language. |
| D7 | Site-list panel data | ✅ Render from the windows already in the search payload; no new endpoint. Verify payload size first: Dash Point alone returned 437 windows (see risk R2). |
| D8 | Watching a weekend | ✅ The "Full · Watch" chip creates a single watch with that weekend's dates; no backend change. The Watch sheet's site-type and party filters need new optional watch fields (P3c). |
| D9 | Release reminders | ✅ A new `watch_type="release"` storing `releases_on`. The scheduler sends a push at 6:55 am PT on release day, then converts it to a cancellation watch. Backend work (P3d). |
| D10 | Mobile bottom sheet | ✅ Custom CSS scroll-snap sheet with a 44px drag handle button, no new dependency. Respect `env(safe-area-inset-*)` for the Capacitor shell (roadmap v1.46 Theme A). |
| D11 | Heading font | ❓ ✅ Bricolage Grotesque for headings only (body stays the system font, per `docs/BRAND.md`), **self-hosted** woff2 rather than Google Fonts: no third-party request, and it works offline in the native app. Needs a BRAND.md update. |
| D12 | Tokens | ✅ New tokens in `tokens.css`: card surface, open/few/full chip, info notice, boat-in. Each gets a dark-mode value ("night camp"), and contrast is checked in `tokens.test.ts`. |
| D13 | Map | ✅ Keep Leaflet. Restyle the tiles (Mapbox style via the existing token), use pin *shapes* for drive band and full/boat-in (not colour alone), and sync list↔map selection through `SearchContext.selectedFacilityId`. |

## PR plan

Every PR goes to `dev`, stays under 400 changed lines, and keeps tests green. Phases can overlap where there are no dependencies.

### Phase 1: remaining data (backend)
- **P1a: decode WA site types.**
  - Store GoingToCamp's `/api/equipment` map (tent / van / RV ≤20′–>40′).
  - Derive `fits_tent`, `fits_van`, `max_rv_ft` from `wa_state_sites.allowed_equipment`, and `hookups` from parsed loop descriptions.
  - Put them on `WindowResponse` for all providers (Recreation.gov from `campsite_type`; OR from its site type).
- **P1b: seed all 75 WA parks.**
  - Prod can't reach GoingToCamp, so run the seeder locally, export to a JSON fixture in the repo, and import it with an idempotent startup migration (same pattern as #170).
  - Add a `doctor` line for parks with zero seeded sites.
- **P1c: `who` filter.** `people`, `equipment`, `rig_length` on `/api/search` and the stream; windows are filtered server-side. Consider a per-window summary to shrink the payload (R2). **First** fix the Oregon RV-length decode: prod shows "RV ≤96′" and "RV ≤81′" (found 2026-11-07).

### Phase 2: results v2 (behind the flag)
- **P2a: scaffolding.** Flag plumbing (D1), `web/src/results/` module, new tokens plus the self-hosted font (D11/D12), `AnswerHeader` (answer line plus coverage "Checked N of M"), and notices (not-released, provider warnings).
- **P2b: cards.** `CampgroundCard`, `WindowChips` (D3, TDD), drive-band grouping, the "Boat-in only" group, fit line, weather.
- **P2c: missing states.** "Full or not released yet" group (D4) with Watch / Remind-me stubs, `QuickPicks` (D6), and the zero-results page (release timeline, "camp sooner" options). Also from prod testing (2026-11-07): stay chips for flexible "Any day" searches (today's chips show runs of open dates and overlap), and the answer header must leave "Checking…" when the stream ends.
- **P2d: layout.** Desktop split layout with a sticky map, map restyle and pin shapes (D13), and list↔map selection.

### Phase 3: search and decisions
- **P3a: search bar.** Where / When / Who / Drive segments, popovers, and campground-name typeahead (from `/api/campgrounds`). Name matches ignore the drive cap.
- **P3b: site-list panel (dialog).**
  - Content: open sites by type, length, hookups, capacity.
  - Hand-off: "Book on <provider> ↗" with plain hand-off copy.
  - Analytics: `window_chip_opened`, `book_click{from:"site_panel"}`.
- **P3c: Watch sheet and per-weekend watches.** Backend: optional watch filters (`site_types`, `min_people`, `equipment`) honoured by the poller.
- **P3d: release reminders** (D9): backend watch type, scheduler, push, and UI.

### Phase 4: mobile and flip
- **P4a: mobile.** Bottom sheet (D10), date quick-chips (This weekend / Next weekend / month), safe areas. **Done** (#213–#216). **Decided 2026-11-08:** phones get a sticky "Map" button that opens the map in a modal sheet, not the Mobile artboard's map-always-on-top layout. Leaflet loads only when asked, and the list (the answer) stays first. A static map thumbnail is the fallback if a glance at locations is missed.
- **P4b: flip.**
  - Make v2 the default and delete the v1 results path from `App.tsx`.
  - Update `e2e/tests/prod-smoke.spec.ts` selectors **in the same PR**, because the prod monitor runs them daily.
  - Carry the new look over to Trips / Pricing / About.

## Testing
- **Pure functions** (chips, candidate windows, bands, quick picks, release dates) are TDD.
- **Each new component** gets a vitest file, and `a11y.test.tsx` is extended to v2 (44px targets, focus visible, no colour-only meaning).
- **E2E:** the v2 smoke flow uses `?ui=v2` until the flip; prod-smoke selectors change in P4b.

## Risks
- **R1 — WA State Parks are dark in prod** (GoingToCamp blocks prod's IPs; see the roadmap "Restoring WA State Parks"). The design's richest data is WA. Without the proxy, v2 in prod shows Recreation.gov and Oregon, with WA labelled "couldn't be checked".
- **R2 — Payload size.** Per-window arrays get large (Dash Point: 437 windows for one June search). With chips plus the panel rendering from this data, measure first. A server-side summary (chip counts, plus per-chip site lists fetched on open) may be needed in P1c.
- **R3 — Entanglement in `App.tsx`.** v2 must not grow `App.tsx`. Mount `ResultsPage` from one switch point.
- **R4 — Low traffic** (~65 pageviews/month): A/B results won't be statistically meaningful. Use the flag for safety and rollback, not for proof.
- **R5 — The native app** shares the web UI. The bottom sheet and safe areas need a TestFlight pass before the flip. **Passed 2026-11-09:** TestFlight build 4 on an iPhone 16e (iOS 27.2), with v2 turned on through the `results_v2` flag, was checked by the owner. Two native bugs were fixed along the way: #219 (adopt the UIScene lifecycle; builds 2–3 made with the iOS 27 SDK crashed at launch) and #220 (PostHog never loaded in the app, so there were no native analytics and flags always read as off). Re-test after P4b if the sheet or the search bar changes.
