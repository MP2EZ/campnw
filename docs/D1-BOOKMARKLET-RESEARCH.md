# D1 Research: Bookmarklet feasibility for pre-filling booking forms

Research conducted 2026-05-04 per the plan in `docs/BOOKING-ENRICHMENT-IDEAS.md` Tier D1.

## TL;DR

**Recommendation: do NOT ship D1 as scoped. Fall back to D4 (AI concierge) as the next-priority research, with a small optional bookmarklet for per-trip fields only.**

Two unexpected findings from the DevTools sniff invalidated the original D1 framing:

1. **The actual booking form on all three providers is auth-walled.** Without signing in, you can't reach the form where equipment/occupants/vehicle/payment fields live. A bookmarklet can only act on pages the user can actually load.
2. **All three providers have account-based auto-fill that overlaps heavily with the bookmarklet's value proposition.** Logged-in users at rec.gov / RA / GTC already see contact info pre-populated from their saved profile. The bookmarklet's "save your profile on Campable, auto-fill on the destination" pitch duplicates work the providers' own systems already do server-side.

What's left for a bookmarklet to do is the ~30 seconds of per-trip fields (equipment type/length, vehicle license plate, occupants), not the 2–3 minutes of full form-filling we originally pitched. That falls below the 60% time-savings decision threshold from the parent doc.

**Provider priority context:** rec.gov is the priority provider; the state sites (RA, GTC) are P1. This *sharpens* the verdict rather than softening it — rec.gov happens to be the provider where the bookmarklet has the *least* value (most mature account auto-fill, deepest deep links, auth-walled checkout). A bookmarklet that only worked for the P1 state sites would be exactly the wrong investment shape: maximum maintenance burden (Angular Material widgets at GTC, vanilla JS surface area at RA) for the lowest-priority providers.

## Per-provider field maps

### Recreation.gov

**Framework:** React 18+ (hashed Vite-style bundle `index-VUqx_z7e.js`). React fibers detected on DOM elements via `__reactContainer*` keys.

**Pre-auth fields visible (sign-up modal):**

| Field | Selector | Type | Framework-controlled? | Plain `value=` works? | `autocomplete` hint |
|---|---|---|---|---|---|
| `firstName` | `#rec-acct-first` | text | No (uncontrolled) | ✅ Yes, persists | ❌ none |
| `lastName` | `#rec-acct-last` | text | No (uncontrolled) | ✅ Yes, persists | ❌ none |
| `email` | `#rec-acct-email` | email | No | ✅ Yes | ❌ none |
| `cellPhone` | `#rec-acct-cell-phone` | tel | No | ✅ Yes | ❌ none |
| `optIn` (newsletter) | `#rec-acct-newsletter-opt-in` | checkbox | No | trivial | n/a |

**Per-trip booking form (presumed, behind auth wall):**
- `/reservations/cart` and `/trips/new` both redirect unauthenticated users to home.
- Per-site page (`/camping/campsites/{id}`) shows site info but no booking form until signed in + dates available.
- Based on rec.gov's public help-center articles and the visible "Allowable Equipment" / "Allowable Vehicle / Driveway Details" buttons on site pages, the auth-walled booking form likely includes: equipment type, equipment length, number of vehicles, vehicle license plate(s), adults, children, pets, special needs.

**ReCAPTCHA v3** loaded site-wide (saw `enterprise.js?render=...` in script bundle). May fire on form submission — bookmarklet shouldn't trip it because the user submits manually.

**Fill-feasibility verdict:** ✅ **Easy where accessible.** React inputs use uncontrolled refs, plain `el.value = ... + dispatch input` works without the synthetic-setter hack. **But:** the high-value per-trip fields are auth-walled, AND rec.gov accounts auto-fill the contact fields server-side once you're logged in — so the bookmarklet's leverage shrinks to per-trip fields only.

### ReserveAmerica

**Framework:** Not React, not Angular. Likely vanilla JS / jQuery (no framework markers detected).

**Pre-auth fields visible at per-site booking page** (`/explore/{slug}/OR/{park_id}/{site_id}/campsite-booking`):

| Field | Selector | Type | `autocomplete` |
|---|---|---|---|
| Global search box | (no id) | text | none |
| Arrival date | `#arrivalDatelg-md` | text | none |

**That's it for visible inputs.** "Book Now" button is present but `disabled` — only enables when the date range has availability AND the user is signed in. Clicking through to the per-night occupants/equipment/vehicle form requires both gates.

**Fill-feasibility verdict:** ⚠️ **Unknown for the booking form.** The pre-booking page exposes essentially nothing useful for a bookmarklet to fill. The actual booking form is double-gated (availability + auth) — couldn't reach it for inspection. Best-case scenario: the form is plain HTML with stable IDs (consistent with RA's vanilla-JS profile) and would be easy to fill *if* we could test it.

### GoingToCamp (WA State Parks)

**Framework:** Angular 19.2.18 (latest). Angular Material widgets throughout.

**Search-form fields visible without auth:**

| Field | Selector | Type | Framework-controlled? | Plain `value=` works? | Notes |
|---|---|---|---|---|---|
| Park selector | `#park-autocomplete-input` | text | No (autocomplete) | ✅ Works (per earlier sessions) | `autocomplete="off"` |
| Arrival date | `#arrival-date-field` | text **`readonly`** | ✅ Reactive Forms (`formcontrolname="arrivalDate"`) | ❌ **No** — value sticks visually but `aria-invalid=true` persists | Material Date Picker — actual date selection is via calendar widget |
| Departure date | `#departure-date-field` | text **`readonly`** | ✅ Reactive Forms | ❌ Same as arrival | Same picker |
| Party size | `#party-size-field` | number | No (uncontrolled) | ✅ Yes | Plain numeric input |
| Equipment | `#mat-mdc-select-{n}` | mat-select | ✅ Material Select | ❌ Need to click options | Dropdown, not a typeable field |

**No `window.ng` debug API** in production builds (it's stripped) — so we can't grab Angular form controls programmatically and call `.setValue()`. Only path is **simulating clicks through the Material widgets**, which is fragile and version-dependent.

**Booking form** (post-Reserve-click): auth-walled, can't inspect.

**Fill-feasibility verdict:** ❌ **Hard to impossible for the search form.** Angular Material widgets are the nightmare case for bookmarklets. **But:** the search form is mostly bypassable via URL params (`searchTime`, `equipmentId`, `peopleCapacityCategoryCounts`) — Campable already passes some of these. So the bookmarklet wouldn't target the search form anyway. The booking form is auth-walled and unreachable for testing.

## Existing-tool overlap

**Browser autofill / 1Password:** ⚠️ Minimally helpful.
- All three providers' forms have **either no `autocomplete=` attribute or `autocomplete="off"` explicitly disabled.** Browser autofill only fires when the field's `autocomplete` hint matches a known type (`email`, `name`, `street-address`, etc.).
- Password managers like 1Password use heuristics (field labels, surrounding text) and *can* fill these forms, but with low reliability.

**Provider account auto-fill:** ✅ This is the big one we missed.
- Once signed in, rec.gov / RA / GTC each pre-populate contact fields (name, email, phone, address) from the user's saved account profile. **This is exactly the value a bookmarklet would deliver, but the providers do it server-side already.**
- The remaining unfilled fields are per-trip (equipment, occupants, vehicle license, special needs) — these aren't account-stored.

This is the load-bearing finding for the recommendation. The original D1 pitch ("save your profile on Campable, auto-fill destination forms") is largely solved by the providers themselves once the user invests one-time in setting up a provider account.

## Time-savings estimate

Originally we framed D1 as "compress 2–3 min of form-filling to 30 sec." Revised estimate based on findings:

| Field category | Baseline time | Bookmarklet savings | Why |
|---|---|---|---|
| Contact info (name, email, phone, address) | ~60s | ~5s | Provider account auto-fill already covers this for logged-in users |
| Per-trip fields (equipment, occupants, vehicle, plate) | ~45s | ~30s | The real bookmarklet target |
| Payment | ~30s | 0s | Always manual |
| Date/site/park selection | already URL-driven (Campable's deep links) | 0s | No bookmarklet needed |

**Realistic time savings per booking: ~30s out of ~135s = ~22%.** Below the 60% decision threshold from the parent doc. And that 22% requires the bookmarklet to reliably reach the auth-walled per-trip form, which depends on per-provider availability and login state.

## Maintenance burden

| Provider | Selector stability | Risk |
|---|---|---|
| rec.gov | Stable React component IDs (`#rec-acct-*` pattern) | Low |
| RA | Vanilla JS, presumed stable IDs (limited test data) | Low to medium |
| GTC | Angular Material widgets — DOM structure tied to specific Material version | **High** — Material updates regularly change generated class names and widget internals |

Plus: every provider can add ReCAPTCHA, mandatory new fields, or A/B test new flows that break the bookmarklet silently.

## Decision

**Fall back to D4 (AI concierge research) as the next-priority work.** Reasons:

1. **D1's expected savings are below threshold.** ~22% time savings vs the 60% decision gate. The original framing assumed the bookmarklet would attack the full form-filling cost; reality is most of that cost is either server-side auto-fill or doesn't exist on Campable's deep-link path.
2. **D1 doesn't address the auth wall**, which is where the form actually lives. A bookmarklet only helps users who've already logged in and reached the booking form — at which point the provider's own auto-fill covers most of what the bookmarklet would do.
3. **The provider priority makes it worse, not better.** rec.gov (the priority provider) is exactly where the bookmarklet has the least marginal value, because rec.gov already solved the saved-profile problem with their account system. A bookmarklet that disproportionately benefits P1 state sites isn't an efficient use of effort.
4. **D4 doesn't have any of these limitations.** An agent navigating with the user's session can: cross the auth wall, handle Material Date Pickers via visual interaction, fill per-trip fields the same as any other field, and apply equally well to rec.gov (where the value is highest).
5. **The maintenance treadmill is similar between D1 and D4** (both break on UI changes), but D4 delivers more value per breakage event and concentrates that value at the priority provider.

**Optional small consolation prize:** A "per-trip field bookmarklet" focused only on the auth-walled-form fields a bookmarklet *could* fill if the user got there manually (equipment type/length, vehicle license plate, occupants). Probably ~30 lines of JS. Saves the ~30 seconds of per-trip typing but ignores all other fields. Low engineering cost, low maintenance burden (these fields are simpler than the picker widgets), low user value but non-zero. Worth keeping in the back pocket if D4 turns out to be too expensive — but per the priority context above, build it for rec.gov *first* (where stable IDs and React uncontrolled inputs make it the easiest target), not for the state sites.

## What this research did NOT cover

- **D1 against logged-in flows** — would need a real test account on each provider. Worth revisiting if D4 falls through, but unlikely to change the verdict because account auto-fill is the primary blocker, not per-field fillability.
- **Time-on-task user research** — I estimated savings from form complexity, not from real users. PostHog `book_click` data (PR #1) will give us actual click-through-and-bounce rates over the next few weeks; that's a better signal for "is this even a problem."
- **D4's actual feasibility** — separate research session per the plan.
