# D4 Research: AI concierge with Claude computer use

Research conducted 2026-05-04 per the plan in `docs/BOOKING-ENRICHMENT-IDEAS.md` Tier D4.

## TL;DR

**Recommendation: do NOT build D4 as scoped.** The ToS landscape has hardened significantly since the original D4 framing was written, and a federal court ruling from March 2026 (Amazon v. Perplexity) directly addressed and rejected the "user-watched, user-approved automation falls outside platform ToS" theory that D4's strategy depended on.

Three findings drive the verdict:

1. **rec.gov + Aspira ToS broadly prohibit any automated access.** The exact language at both (rec.gov directly; Aspira covers RA + GTC) bans "any robot, bot, spider, offline reader, site search/retrieval application or other manual or automatic device or process" — sweeping enough to clearly cover an AI agent regardless of who initiates it.
2. **Amazon v. Perplexity (March 2026) established federal precedent that user consent doesn't matter.** Judge Chesney granted Amazon a preliminary injunction against Perplexity's Comet shopping agent, ruling that even when an AI agent acts with explicit user permission, accessing a platform whose ToS prohibits automation constitutes CFAA "unauthorized access." The ruling is on appeal to the 9th Circuit; until that resolves, it's the controlling precedent for buyer-side AI agents.
3. **rec.gov has an active enforcement program.** Campnab, Recbot, and others operate in this gray area only by *monitoring* (read-only); the moment they cross into automated reservation, accounts get banned. Not a theoretical risk.

The path forward isn't D4. **Recommended:**
- **Ship D5 (human concierge) first** as a paid wedge. Humans aren't bots; ToS doesn't apply. Validates willingness-to-pay before any technical work, and shapes what an automated version would need to do if the legal landscape shifts.
- **Park D4 until 9th Circuit rules on Perplexity appeal.** If the appeal narrows the precedent (e.g., distinguishes assistive vs. competitive automation), revisit. Otherwise, D4 stays parked.
- **Keep the per-trip-fields-only bookmarklet** as the smallest viable D-tier option — it's in the same legal gray zone as D4 but operates only on the user's own browser session for fields they could type themselves. Lowest risk profile because it doesn't *navigate* automatically.

## Phase 1: Computer Use API technical brief

**Status:** In public beta on Anthropic's Sonnet/Opus models. No special pricing tier — standard token billing applies.

**Models supporting computer use (May 2026):**
- Claude Sonnet 4.6 (`claude-sonnet-4-6`): $3/MTok input, $15/MTok output
- Claude Opus 4.6 (`claude-opus-4-6`): $5/MTok input, $25/MTok output
- Claude Opus 4.7 (`claude-opus-4-7`, latest): same pricing as 4.6
- Opus also offers a **Fast Mode** at 6× standard price ($30/$150 per MTok) for latency-sensitive workloads

**Sandbox model:** You provide the sandbox; Anthropic provides the API tool spec (the `computer` tool that emits screenshot/click/type/keyboard actions). Reference architecture is a Linux container with Xvfb (virtual X11), a window manager (Mutter), Firefox, and the Anthropic-provided action loop. You're responsible for hosting and securing this environment.

**Two product paths:**
- **Pure API route** — you build the orchestration around `client.messages.create(tools=[{"type": "computer_20250124", ...}])`. Maximum flexibility, you own the sandbox lifecycle.
- **Anthropic Cowork / Claude Code computer-use mode** — Anthropic-hosted desktop product, runs on the user's own machine (or a Cowork-managed VM). Less flexible, more secure-by-default.

**Cost estimate per booking (rec.gov-shaped flow):**
A typical agent loop is 30–50 turns (each screenshot + reasoning + action). Conservative tokens-per-turn estimate: 3K input (screenshot encoded + history) + 500 output. Total per booking:
- 30 turns × (3K + 0.5K) tokens = 105K tokens
- With Sonnet 4.6: 90K input × $3/MTok + 15K output × $15/MTok ≈ **$0.27 + $0.23 = ~$0.50/booking**
- With Opus 4.6: ~**$0.83/booking**
- With Opus 4.6 Fast Mode: ~**$5/booking** (only worth it if booking-window racing matters)

These numbers are consistent with the $0.50/booking estimate in the parent doc's Tier D4 entry — that estimate stands.

**Latency budget:**
Each turn round-trips through Claude (~5–10s) plus screenshot capture (~500ms) plus action execution (~500ms). 30 turns × ~7s = **~3.5 minutes per booking** end-to-end. Compare to manual baseline of ~135s per the D1 research → **agent is 1.5× SLOWER than manual.** This is the load-bearing economic check, and it fails. Even before legal concerns, the agent doesn't save time at the booking moment — it would only be valuable for asynchronous/scheduled booking attempts (e.g., "book this when it becomes available at 7am MT").

## Phase 2: ToS analysis — exact language

### Recreation.gov

**Source:** Help Center Terms of Service (and corroborated by widely-cited summary).

**Quoted prohibition:**

> "any robot, bot, spider, offline reader, site search/retrieval application or other manual or automatic device or process to retrieve, index, data mine, scrape or in any way reproduce or circumvent the navigational structure or presentation of the Site or its contents without our prior written consent"

**Enforcement language:**

> "any account caught using bots or reselling reservations will be banned"

**Accommodation for assistive technology:** None found in the ToS or rules-and-policies pages. Accessibility statement linked in footer is about WCAG compliance, not third-party automation.

### Aspira (covers ReserveAmerica + GoingToCamp)

**Source:** `https://aspiraconnect.com/terms-of-use`.

**Quoted prohibition:**

> "use any robot, bot, spider, offline reader, Sites search/retrieval application or other manual or automatic device or process to retrieve, index, data mine, scrape or in any way reproduce or circumvent the navigational structure or presentation of the Sites or its contents without our prior written consent"

**Search engine carve-out:**

> "we grant the operators of public search engines permission to use spiders to copy materials from the Sites for the sole purpose of and solely to the extent necessary for creating publicly available searchable indices of the materials, but not caches or archives of such materials"

**CAPTCHA bypass explicitly prohibited:** Yes.

**Liquidated damages:** Users requesting "more than 1,000 pages of the Sites in any 24 hour period" face "$0.25 per page request each time that a page request is made after that first 1,000."

**Accommodation for assistive technology:** None.

### Risk-tier assessment

| Provider | ToS clarity | Enforcement evidence | Risk tier |
|---|---|---|---|
| rec.gov | Clear, broad prohibition | Active security team, ban policy explicit | **High** |
| Aspira (RA + GTC) | Even more sweeping, includes liquidated damages and CAPTCHA-bypass clause | Operates anti-scraping/CAPTCHA infrastructure | **High** |

The rec.gov and Aspira ToS clauses are nearly identical — they're industry-standard language that travels across reservation platforms. There is no carve-out for assistive technology, user-initiated automation, or AI-on-behalf-of-user.

## Phase 3: Architecture sketch

If we did build D4 (we shouldn't, per the verdict, but for completeness):

**Recommended topology:** Server-side sandbox per booking session.

- Each booking spins up a fresh Linux container (Xvfb + Firefox + the computer-use action handler)
- User credentials enter via OAuth where possible (rec.gov has none) or an encrypted at-rest credential vault
- Session lives for the duration of one booking (~3-5 min including agent loop), then the container is destroyed
- Failure modes (CAPTCHA, unexpected dialog, layout change) trigger an "agent stuck" state that surfaces a screenshot to the user with a "take over" handoff link

**Alternative: client-side via browser extension.** Agent runs in user's own Chrome session. Sidesteps credential transit and the "platform sees a different IP/fingerprint than the user" problem. Reintroduces the D1 distribution issue (extension install).

For D5 (human concierge), the architecture is `Stripe Checkout + Notion form + Slack alert + you doing the booking manually`. No sandbox, no agent, no ToS exposure.

## Phase 4: Payment-handoff design

If D4 were to be built:

**Recommended option (A): Agent stops at "Review and Pay."**

- Agent fills everything except payment fields
- Surfaces the cart-review page to user as a screenshot + "click here to enter payment yourself"
- User completes the payment step on the destination site directly with their own card
- Cleanest liability boundary: provider sees user's actual card transaction, no chargebacks Campable inherits

Options (B) "stored payment via Stripe + agent submits" and (C) "screenshot-confirm hybrid" both put Campable in the payment-flow, which carries Money Service Business considerations and chargeback exposure. Defer to (A) for any prototype.

This entire phase is moot given the verdict — included for record-keeping in case the legal landscape shifts and D4 is reconsidered.

## Phase 5: Comparable products survey

| Product | What they ship | ToS friction | Status (May 2026) |
|---|---|---|---|
| **MultiOn** | Autonomous web agent for general task automation including booking | Operates in gray zone; no public lawsuit found, but treads carefully on platforms with explicit anti-bot ToS | Active, growing |
| **Perplexity Comet** | AI shopping/browser agent, attempted Amazon shopping automation | **Lawsuit + preliminary injunction (March 2026)** — Amazon prevailed on CFAA and California CDAFA claims | **Blocked from Amazon** by court order; case on appeal |
| **Browser Use** | Open-source agent framework for browser automation | Framework itself ToS-neutral; the responsibility shifts to the operator | Most popular open-source agent framework (89.1% on WebVoyager) |
| **Adept ACT-1** | Demoed in 2022 as autonomous web agent | Pivoted away from consumer agent strategy | Largely abandoned consumer-direct; pivoted to enterprise |
| **Cowork (Anthropic)** | Anthropic's hosted desktop computer-use product | Designed for user-on-own-machine model — minimizes platform-side ToS exposure | Limited beta |

**Key comparable for D4: Amazon v. Perplexity.** The case directly addresses the architecture D4 would use (user-permitted, agent-driven shopping) and the ruling went against Perplexity. Until the 9th Circuit hears the appeal and either narrows or reverses, this is the controlling precedent for any buyer-side AI agent operating against a platform with anti-bot ToS.

**Quote from Cooley's analysis of the Amazon ruling:** Judge Chesney drew the critical distinction between "consent of the user" and "consent of the platform" — both are required, and a platform's ToS withholding consent for AI agents is enforceable even when the user explicitly authorized the agent.

This is dispositive for D4 against rec.gov/Aspira: both platforms explicitly withhold consent for any automated access in their ToS.

## Phase 6: rec.gov-specific feasibility map

Setting aside the legal verdict for a moment — was the agent even technically going to deliver value at rec.gov? Walking through the step sequence:

1. **Open browser session** — sandbox spin-up: ~10s
2. **Navigate to rec.gov + sign in** — credential transit + login form: ~15s + 1 turn
3. **Navigate to per-site deep link** (Campable already provides) — ~3s + 1 turn
4. **Click "Add to Cart"** — ~2s + 1 turn
5. **Fill per-trip fields** (equipment type, length, vehicle plate, occupants × N nights) — ~30s + 5–10 turns
6. **Navigate to review-and-pay** — ~5s + 1 turn
7. **Stop, surface to user** — ~2s + final summary turn

Total: ~70s of "real" page interactions + 10–15 Claude turns × ~7s/turn = **~85–105 seconds of agent overhead on top of the page interactions**, for a total of **~2.5–3 minutes per booking**.

**Manual baseline from D1 research:** ~135s (~2.25 min).

**Verdict: agent is roughly the same speed or slower than manual.** The agent isn't economically valuable for the booking-moment use case. It would only be useful for the *asynchronous booking* case — where the user submits intent ahead of time and the agent waits for inventory to open up (the rec.gov rolling-release moment, e.g., "book this site when it opens at 7am MT in 3 weeks"). That's a meaningfully different product than what D4 was scoped as.

## Phase 7: Decision

**Don't build D4 as scoped.** Three independent disqualifiers, each sufficient on its own:

1. **Legal/ToS risk is high and recently solidified.** Both rec.gov and Aspira have clear, sweeping anti-automation language. Amazon v. Perplexity (March 2026) established federal precedent that user consent doesn't override platform ToS for AI agents. Until the 9th Circuit rules on appeal, this is the controlling case.
2. **Latency washes out the economic value at the booking moment.** ~2.5–3 min agent vs ~2.25 min manual baseline. The agent doesn't save users time on synchronous booking. It would only deliver value for asynchronous "wait for inventory" scenarios — and that's a different product.
3. **Provider enforcement is real.** rec.gov has an active security team, behavioral detection, CAPTCHA, and an explicit account-ban policy. Even if Campable accepts the legal risk, individual users would face account bans — a much worse user-facing outcome than the friction we're trying to fix.

**Path forward:**

- **D5 (human concierge) is now the highest-leverage next move.** Humans aren't bots; ToS doesn't apply; no legal exposure. Test the willingness-to-pay hypothesis at $5–10/booking via Stripe + Notion form. Operationally limited to a few bookings/day, but that's enough to validate the wedge. Particularly compelling for the "rec.gov rolling release at 7am MT" moment where users *would* pay to skip the race.
- **Per-trip-fields-only bookmarklet remains as the smallest D-tier option.** Same legal gray area as D4 but operates only on fields the user could type themselves, only when they're already on the page. Lower risk profile because it doesn't navigate or submit. Probably 30 lines of JS, one weekend to build. Worth keeping as a paid-tier feature once D5 validates the pricing.
- **Park D4 until the 9th Circuit rules on Perplexity appeal.** If the ruling narrows (distinguishes assistive from competitive AI, or carves out user-watched flows), reconsider. Otherwise stays parked.
- **D3 (provider OAuth/partnership) is the only legitimate path** to a fully automated D4 — but as already documented, neither rec.gov nor Aspira offers public OAuth and partnership requires PMF that Campable doesn't have yet. Worth one outreach email to each (folds into C8) but not worth planning around.

## What this research did NOT cover

- **Asynchronous "scheduled booking" reframe.** The latency analysis surfaced this as the only D4-shaped use case where agent value could exceed cost. Worth a future research pass if D5 validates demand and the legal landscape shifts.
- **Detailed legal opinion.** This is reading ToS language and recent caselaw — not a substitute for actual legal counsel. If D4 ever gets serious consideration, a real attorney needs to weigh in (especially on California CDAFA exposure for Campable as a CA-relevant operator).
- **Building a prototype.** Per the verdict, no prototype work warranted at this time.

## Sources

- Anthropic computer use docs and pricing — surfaced via WebSearch + context7 query of `/anthropics/anthropic-sdk-python`
- rec.gov ToS language — confirmed via WebSearch (multiple corroborating summaries, original ToS page is JS-rendered)
- Aspira ToS — `https://aspiraconnect.com/terms-of-use` via WebFetch
- Amazon v. Perplexity ruling (Judge Maxine M. Chesney, N.D. Cal., March 2026) — multiple analyses including Cooley LLP, IAPP, CNBC, Search Engine Journal
- Browser Use 2026 status — Firecrawl blog, Bright Data, GitHub
- MultiOn current state — official site + AI agent directories
