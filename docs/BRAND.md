# campable Brand Guide

## Name
**campable** — lowercase, one word. "camp" (the action) + "able" (available, capable, findable).

## Positioning
Discovery engine for campsite availability. Not monitoring (Campnab), not listings (Dyrt/Hipcamp). Campable answers "where can I actually go camping this weekend?" across multiple booking systems.

**Tagline:** "Find your weekend."
**Explanatory:** "Real-time campsite availability across the Pacific Northwest and beyond."

## Color Palette

| Name | Hex | HSL | Usage | Contrast on cream | Contrast on dark |
|------|-----|-----|-------|-------------------|------------------|
| Brand Green | `#2d5016` | `100, 55%, 20%` | Primary accent, buttons, links | 7.5:1 AA | — |
| Brand Green (dark) | `#3a6a28` | `100, 45%, 28%` | Accent on dark theme | — | 4.2:1 AA |
| Accent Text (dark) | `#7aad5a` | `100, 34%, 52%` | Text/links on dark bg | — | 4.8:1 AA |
| Near-Black | `#1a1a1a` | `0, 0%, 10%` | Body text (light), dark bg base | 13:1 AAA | — |
| Warm Cream | `#f5f5f0` | `60, 20%, 95%` | Light mode background | — | — |
| Campfire Orange | `#D4722A` | `24, 68%, 50%` | CTA accent, share cards | 3.5:1 AA-lg | — |
| Text on Accent | `#ffffff` | — | Text on green buttons | 6.5:1 AA | 6.5:1 AA |

### Source Colors (provider badges)
| Provider | Badge BG | Text | Border |
|----------|----------|------|--------|
| Rec.gov | `#e8f0e0` | Brand Green | `#5a8a32` |
| WA Parks | `#deeef5` | `#1a5276` | `#3498b0` |
| OR Parks | `#fef3e0` | `#7d5a1a` | `#d4920a` |
| ID Parks | `#eee5f5` | `#5b2d7a` | `#7d3cb5` |

### CSS Tokens
Brand colors are defined in `web/src/tokens.css` as `--brand-green`, `--brand-black`, `--brand-cream`, `--brand-orange`. Theme colors (--accent, --bg, --text) in `web/src/App.css` reference these values.

## Typography

| Role | Font | Weights | Usage |
|------|------|---------|-------|
| Headings | Plus Jakarta Sans | 500 (medium), 700 (bold) | Wordmark, h1-h3, result card names, nav |
| Body | System stack | 400, 500, 600, 700 | All body text, form controls, data |

**System stack:** `-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif`

**CSS tokens:** `--font-heading`, `--font-body` in `tokens.css`.

**Rules:**
- Never use more than 2 font families
- Headings: medium (500) for regular, bold (700) for emphasis
- Body: let the system font do the work — it's faster and matches the OS

## Logo

**Mark:** Pin drop with tree silhouette (Option A). Brand green fill, cream detail.

**Variants:**
- `favicon.svg` — 16px optimized pin drop
- `logo-option-a-pin.svg` — full 512px mark

**Wordmark:** "camp" (weight 500) + "able" (weight 700) in Plus Jakarta Sans. Single baseline, no gap. See `web/src/Wordmark.tsx`.

**Rules:**
- Minimum size: 16px (favicon)
- Clear space: equal to the height of the lowercase 'a' on all sides
- Never rotate, stretch, or add effects
- Monochrome variant: brand green on white, or white on brand green

## Icons
- Library: Lucide
- Style: outlined, 1.5px stroke, rounded caps
- Size: 16px default, 20px for primary actions
- Color: currentColor (inherits from text)

## Voice

### Principles
- **Declarative, not interrogative.** "3 sites open at Ohanapecosh" not "Looking for campsites?"
- **Specific, not vague.** Always include the data point — campground name, dates, site count.
- **Honest about limitations.** "We check 1,370 campgrounds across 3 booking systems."
- **No outdoor-lifestyle marketing copy.** The user is already a camper.
- **No "Oops!" or "Uh oh!"** in error states. State what happened, what to do.
- **Discovery language** ("find", "search", "discover"), never monitoring language ("snag", "grab", "alert").

### Notification Copy
- Title: campground name (never "Availability Alert")
- Body: site count + dates + timing context
- Urgency comes from data (weekend proximity, rarity), not exclamation marks
- No emoji prefixes — the data speaks

### Examples

**Good:**
- "3 sites open at Ohanapecosh, Fri Jul 3 – Sun Jul 5. Book soon — these typically fill within 2 hours."
- "Kalaloch has weekend availability for the first time in 3 weeks. 2 standard sites, Sat-Sun."
- "No results found for lakeside campgrounds in WA, June 15-17. Try expanding to OR or shifting dates."

**Bad:**
- "🔥 Great news! Availability alert for Ohanapecosh!" (manufactured urgency)
- "Uh oh, we couldn't find anything." (cutesy error)
- "Snag this site before it's gone!" (pressure language)

## Share Cards (OG Image)
- Size: 1200×630
- Background: Warm Cream (`#f5f5f0`)
- Elements: logo mark, wordmark, tagline, source badges, stats
- Template: `web/public/og-default.svg`
