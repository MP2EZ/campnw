# campnw v0.95 "Monetization" — Product Requirements

**Status:** Planning
**Target:** After v0.9 ships, before v1.0 public launch
**Authored:** March 2026

---

## Theme

campnw has real users, real infrastructure costs, and a feature set that justifies a paid tier. This milestone introduces a Free/Pro split, a Stripe-powered subscription flow, and the upgrade surfaces that make the paid tier discoverable without being coercive. The goal is not growth — it is sustainability. Break-even requires 2-4 Pro subscribers at $5/month. Everything here is scoped to that reality.

This is a lifestyle business milestone, not a venture-scale growth milestone. No enterprise tiers, no usage-based billing, no team accounts. Ship the minimum that makes campnw self-sustaining and gets out of the way.

---

## Positioning Context

campnw's two closest paid competitors:
- **Campnab:** ~$8/mo for single-campground monitoring on Recreation.gov only
- **Campflare:** $20+/mo, polished UI, rec.gov only, US-wide (not PNW-specific)

campnw's free tier already beats Campnab's paid tier on features (multi-provider, WA State Parks, AI notifications). The Pro tier at $5/mo is positioned as: *the best PNW campsite tool, supported by the people who use it most*.

The framing matters: this is not "pay to remove limits." It is "pay to support the tool and get more of what you already like."

---

## Free vs Pro Tier Definition

### Design Principles

1. **Core discovery is always free.** Search, calendar heat map, result cards, vibe descriptions, booking links — never gated. The tool's primary value must be accessible without payment.
2. **Watches are the natural gate.** Watches require background server load (polling, notifications, AI enrichment). This is where the cost lives, so this is where the gate goes.
3. **Limits create pressure without punishment.** A 3-watch limit is felt by engaged users but never by casual ones. A user with 3 active watches who finds a fourth campground they want to monitor is exactly the right upgrade moment.
4. **Pro features are more of the same, not a different product.** No feature is hidden behind a paywall that users can't see. They can see trip planner, see it's useful, and then be prompted — not blocked — on their 6th session.
5. **The free tier must be genuinely useful.** If a free user can't find and monitor a campsite, the free tier has failed.

### Tier Table

| Feature | Free | Pro ($5/mo) | Rationale |
|---|---|---|---|
| Search (all providers, all filters) | Unlimited | Unlimited | Core value; always free |
| Calendar heat map | Yes | Yes | Core value |
| Vibe descriptions | Yes | Yes | Delight, low cost, always on |
| Smart Search / zero-result diagnostics | Yes | Yes | Core value |
| Shareable search links | Yes | Yes | Core value + acquisition tool |
| Booking link passthrough | Yes | Yes | Core value |
| Watches (simultaneous active) | 3 | Unlimited | Natural limit on server cost |
| Watch polling interval | 15 min | 5 min | Meaningful upgrade for urgency |
| Contextual AI notifications (urgency scoring) | Yes | Yes | Already free in v0.7; don't regress |
| Anomaly alerts (proactive, from v0.9) | No | Yes | Pro-only; stateful, high signal |
| Availability predictions (from v0.9) | Preview only | Full | See note below |
| Trip planner sessions (from v0.8) | 3/month | 20/month | Rate-limited by Sonnet cost |
| Search history | 10 searches | 30 searches | Small, meaningful difference |
| Data export | Yes | Yes | Privacy right; never gate |
| Account deletion | Yes | Yes | Privacy right; never gate |

**Predictions preview note:** Free users see "Sites at this campground typically free up 2-3 weeks before the date" but without the per-date breakdown, confidence band, or "remind me when the booking window opens" CTA. The data is surfaced; the actionable layer is Pro. This avoids the perception that predictions are hidden — they're just richer for Pro.

**Watch polling interval:** 5-minute polling for Pro is a genuine capability upgrade for high-demand cancellations. The availability cache (v0.5) means 5-min polling does not 3x API calls — it reuses cached availability data and only re-fetches when TTL has expired. Implementation is feasible without straining provider rate limits.

### What is NOT Gated (ever)

These must remain ungated regardless of future pricing changes:

- Core search and availability checking
- Viewing any campground result, vibe description, or calendar heat map
- Booking link clicks (campnw never intermediates transactions)
- Account data export and deletion
- Basic notification delivery for existing watches

---

## User Stories

### Upgrade Flow

**US-1: Upgrade trigger — watch limit**
As a free user who tries to create a 4th watch, I see a clear explanation of the watch limit and a single CTA to upgrade. I can upgrade inline without leaving the watch creation flow. After upgrading, my 4th watch is immediately created.

*Acceptance criteria:*
- Modal appears when watch creation would exceed the limit, not before
- Modal shows: current plan, what Pro includes, price, and a "Upgrade to Pro" button
- "Maybe later" dismisses without creating the watch
- Successful upgrade resumes and completes the watch creation
- No watch creation form data is lost during the upgrade flow

**US-2: Upgrade trigger — trip planner**
As a free user who has used 3 trip planner sessions this month, I see a soft prompt on the 4th session start (not on the 3rd). I can upgrade inline. If I dismiss, I can still use the planner until the new month resets my count.

*Acceptance criteria:*
- Counter visible in planner UI ("3 of 3 free sessions used this month")
- Prompt appears on session 4 attempt, not before
- Upgrade modal is the same component as the watch-limit modal (reuse)
- Monthly reset is calendar-month based (1st of month), shown in the counter

**US-3: Upgrade from settings**
As any user, I can navigate to Settings > Plan and see my current tier, usage (watches active, planner sessions remaining), and an upgrade/manage button.

*Acceptance criteria:*
- Settings page shows: current plan, billing period, next renewal date (Pro), usage summary
- "Upgrade to Pro" for free users, "Manage subscription" for Pro users
- Upgrade button opens Stripe Checkout in a new tab or embedded modal (TBD by implementation)

**US-4: Stripe checkout**
As a free user choosing to upgrade, I complete payment on Stripe Checkout. After success, I am immediately on Pro.

*Acceptance criteria:*
- Stripe Checkout handles the full payment form (no PCI scope on campnw's backend)
- On success: Stripe webhook updates user record; user sees confirmation within 5 seconds
- On failure: user sees a clear error and a retry path; never left in an ambiguous state
- Pro status is set by server-side webhook, not client-side redirect (no race conditions)

**US-5: Downgrade / cancel**
As a Pro user who wants to cancel, I can cancel from Settings > Plan. I retain Pro access through the end of the current billing period. After expiry, watches beyond the free limit are paused (not deleted) with a clear explanation.

*Acceptance criteria:*
- Cancel flow goes through Stripe Customer Portal (campnw does not build a custom cancel UI)
- Excess watches are paused, not deleted — user can reactivate them if they re-subscribe
- Paused watches show a clear "Paused — upgrade to reactivate" state in the watch list
- User receives an email (via Stripe) before the period ends
- No dark patterns: cancel link is visible, not buried in a nested menu

**US-6: Failed payment recovery**
As a Pro user whose payment fails (expired card), I receive a notification and a grace period before being downgraded.

*Acceptance criteria:*
- Stripe Billing retry logic handles the retry sequence (3 attempts over 7 days)
- campnw does not implement custom retry logic
- User is notified via Stripe email (no custom email plumbing required)
- Grace period: 7 days from first failure before Pro features are paused
- During grace period, user sees a persistent banner: "Payment failed — update your card to keep Pro access"
- After grace period expiry: same treatment as cancellation (watches paused, not deleted)

**US-7: Billing history**
As a Pro user, I can view my billing history and download receipts.

*Acceptance criteria:*
- "Billing history" link in Settings > Plan opens Stripe Customer Portal
- campnw does not build a custom billing history UI
- Receipts are provided by Stripe directly

---

## Pricing Structure

### Price

**$5/month, billed monthly.**

No annual plan at launch. The user base is small, annual billing adds complexity (prorated refunds, annual renewal churn), and the pricing advantage ($50/yr vs $60/yr) is not meaningful at this price point. Revisit after 6 months.

**No free trial.** The free tier is effectively a permanent trial — it is full-featured for casual users. A time-limited "Pro trial" adds complexity and trains users to expect free Pro access. The free tier does the work a trial would do.

### Pricing Page

The pricing page is a single, minimal page at `/pricing`. No separate marketing site required. Key copy principles:

- Lead with the value, not the limits: "campnw Pro gives you faster alerts, more watches, and the full trip planner."
- Don't feature-list the free tier as "limited." Present Free as a complete product and Pro as an extension.
- Honest about what you are: "Built and maintained by one person in Seattle. Pro subscriptions keep the servers running and the campgrounds coming."
- No countdown timers, no "limited time pricing" — this is not that kind of product.

Suggested headline:

> **campnw Pro**
> More watches. Faster alerts. The full trip planner.
> $5/month — cancel anytime.

Comparison table on the same page (mirroring the tier table above). No separate "Plans" vs "Features" pages.

---

## Upgrade Trigger Points

These are the surfaces where upgrade prompts appear. The rule: prompts appear at the moment of value, not before.

| Trigger | Location | Type | Behavior |
|---|---|---|---|
| 4th watch creation attempt | Watch creation modal | Hard gate | Watch not created until upgrade; inline upgrade prompt |
| 4th trip planner session (month) | Planner session start | Soft gate | Prompt shown; session still starts if dismissed |
| Viewing anomaly alerts list (Pro-only from v0.9) | Watch dashboard | Soft prompt | "You have 2 anomaly alerts — Pro feature" with upgrade CTA |
| Settings > Plan | Settings | Passive | Always visible; user-initiated upgrade |
| Pricing page | /pricing | Passive | Linked from footer + settings |

**Explicitly NOT a trigger:**
- Page load (never gate on first visit)
- Search results (core flow; never interrupt)
- Reading vibe descriptions or calendar heat maps
- Notification receipt (never gate delivery of an existing watch)
- Account creation
- Any privacy or data export flow

The trigger count is intentionally small. An upgrade prompt that appears in 5 places trains users to dismiss it. Prompts that appear exactly when the user hits a limit feel helpful, not manipulative.

---

## Communication Strategy

### The Problem

campnw has existing users who have been using the product for free with no expectation of limits. The watch limit (3 watches) may break some users' current setups if they have more than 3 active watches. This requires careful handling.

### Approach

**Grandfather existing watches. Announce well in advance. Be honest.**

1. **Grandfather period (30 days):** Users with more than 3 active watches at launch keep all of them active for 30 days post-launch. After 30 days, watches beyond 3 are paused for free users. This is non-negotiable — breaking existing setups without notice would be a trust violation.

2. **Announcement:** One email to registered users before the billing system goes live. Plain text, personal tone. No marketing language.

   Suggested copy direction:

   > "Hey — I'm adding a Pro tier to campnw at $5/month. The free tier stays fully featured for search and basic monitoring (3 watches). If you're already using more than 3 watches, I'm giving you 30 days to decide: downsize, or grab a Pro subscription before the limit kicks in. Thanks for using the thing I built."

3. **No dark pattern communication:** No countdown urgency. No "limited time pricing." No repeated emails. One announcement, one reminder before the grandfather period ends.

4. **In-product banner:** Logged-in users see a banner in the watch dashboard for the 30-day grandfather period: "campnw Pro is launching on [date]. You currently have [N] active watches — the free tier includes 3. [Learn more] [Upgrade to Pro]"

5. **What not to say:** Do not frame the free tier as "limited" or suggest users are losing something. The frame is: the free tier is complete for most people, and Pro exists for power users who want more.

---

## Technical Implementation Notes

### Stripe Integration

- **Stripe Checkout:** Hosted checkout page for payments. No custom card form — avoids PCI scope entirely.
- **Stripe Customer Portal:** Hosted portal for subscription management (cancel, update card, billing history). No custom cancel UI required.
- **Stripe Billing Webhooks:** `customer.subscription.updated`, `customer.subscription.deleted`, `invoice.payment_failed`, `invoice.payment_succeeded` — these four events cover all billing state transitions. Webhook handler updates `users` table in SQLite.
- **User schema additions:** `stripe_customer_id` (nullable), `subscription_status` (enum: free, pro, pro_grace, pro_cancelled), `subscription_expires_at` (nullable datetime), `pro_since` (nullable datetime for telemetry).
- **Idempotency:** Webhook handler must be idempotent — Stripe may deliver the same event more than once.
- **No financial data in SQLite:** campnw stores only `stripe_customer_id` and subscription status. All payment details live in Stripe.

### Watch Enforcement

- Watch limit check happens server-side in `POST /api/watches`, not just in the UI.
- Response: `HTTP 402 Payment Required` with body `{"error": "watch_limit_reached", "limit": 3, "upgrade_url": "/pricing"}` — this is machine-readable so the frontend can show the upgrade modal.
- Existing watches are never deleted by the system. Paused watches remain in the database with `status="paused"`.

### Polling Interval

- 5-minute polling for Pro is implemented as a per-user scheduler config. The APScheduler job checks user tier when batching watches for a cycle.
- Do not run two separate schedulers. One scheduler, per-watch polling metadata.

### Security

- Stripe webhook endpoint must validate the `Stripe-Signature` header using the webhook secret. Reject unvalidated requests with 400.
- `subscription_status` is set only by webhook, never by client-supplied parameters.
- Rate limit the Stripe Customer Portal redirect endpoint (max 10 requests/min/user) to prevent portal link abuse.

---

## Success Metrics

### Primary

| Metric | Target (6 months post-launch) | Notes |
|---|---|---|
| Monthly Recurring Revenue (MRR) | ≥$10/mo (2 Pro subscribers) | Break-even; $20 = comfortable |
| Pro conversion rate (active users) | 2–5% of MAU | Low bar given low free-tier friction |
| Upgrade-trigger-to-conversion rate | >15% | % of users who see upgrade modal and subscribe |

### Secondary

| Metric | Purpose |
|---|---|
| Churn rate (monthly) | Detect if Pro value is being delivered |
| Watch limit hit rate | How often do free users reach 3 watches? Validates the gate placement |
| Trip planner trigger rate | How often does the 4th-session prompt appear? Validates planner usage |
| Grandfather-period downsizes vs upgrades | How many users trimmed to 3 vs subscribed? Informs limit calibration |

### What NOT to measure (yet)

- LTV, CAC, payback period — premature at <10 subscribers
- NPS from paying users — requires infrastructure and a minimum sample size
- Churn cohort analysis — requires 3+ months of subscriber data

---

## What NOT to Build

These are explicitly out of scope for v0.95. Document them here so they don't get proposed.

| Idea | Why Deferred |
|---|---|
| Annual billing ($50/yr) | Adds proration complexity; minimal price advantage at this scale |
| Team/family plans | No use case evidence; adds seat management complexity |
| Usage-based billing (per API call, per watch) | Too complex to reason about; friction kills conversion |
| Referral / affiliate program | Premature; not worth building for <50 subscribers |
| Free trial (30-day Pro) | The free tier already functions as a permanent trial |
| Custom invoice / billing UI | Stripe Customer Portal covers this adequately |
| Pricing experiments (A/B) | Insufficient sample size for statistical significance |
| Enterprise / B2B tier | Out of scope for a personal tool indefinitely |
| Freemium "coins" or credits system | Wrong product category; camping ≠ gaming |
| In-app upsell notifications (non-trigger) | Dark pattern; not this product |

---

## Dependencies

- v0.8 Trip Planner (gated by Pro) must be shipped
- v0.9 Predictions+ (anomaly alerts are Pro-only) ideally shipped; acceptable to launch billing before v0.9 ships if revenue pressure exists
- Accounts (v0.4) — required; billing is per-user

---

## Key Risks

**R1: Grandfather period causes immediate churn.** Users with >3 watches who don't upgrade may disengage entirely. Mitigation: be transparent, make the grandfather period generous (30 days), and don't over-index on retention — a user with 5 watches who won't pay $5/month was unlikely to be a long-term user anyway.

**R2: Stripe integration complexity delays launch.** Webhooks + Customer Portal + idempotency + SQLite state sync is real backend work. Mitigation: use Stripe Checkout and Customer Portal aggressively — do not build any custom billing UI. The entire payment surface is hosted by Stripe.

**R3: Pricing feels wrong in retrospect.** $5/month may be too low (leaving money on the table) or too high (blocks conversion). Mitigation: start at $5. It is trivially easy to raise price later. It is hard to lower it without signaling weakness.

**R4: The free tier is "good enough" and nobody upgrades.** This is the lifestyle business version of product-market fit risk. Mitigation: if MRR is $0 after 3 months, revisit the gate. Options: lower the free watch limit to 2, add the trip planner to the gate earlier, or accept that campnw is a free personal tool and drop the billing system.

---

## Milestone Completion Criteria

- [ ] Stripe Checkout + Billing Webhooks integrated and tested in staging
- [ ] Stripe Customer Portal linked from Settings > Plan
- [ ] `subscription_status` field on user, enforced server-side
- [ ] Watch limit (3 free) enforced server-side with HTTP 402 response
- [ ] 5-minute poll interval functional for Pro users
- [ ] Upgrade modal component (reused across all trigger surfaces)
- [ ] Pricing page at `/pricing` (static, linked from footer)
- [ ] Settings > Plan page showing tier, usage, and upgrade/manage CTA
- [ ] Watch pausing logic on free tier downgrade (grandfather period + expiry)
- [ ] Grandfather period banner in watch dashboard
- [ ] Announcement email drafted and queued (single send, not a campaign)
- [ ] Webhook endpoint validates Stripe signature
- [ ] All billing state transitions covered by tests (upgrade, cancel, failed payment, grace expiry)
