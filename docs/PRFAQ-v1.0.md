# campnw v1.0 — PRFAQ

---

## Press Release

**FOR IMMEDIATE RELEASE**

### campnw Launches the First AI-Powered Campsite Discovery Platform for the Pacific Northwest

**Searches Recreation.gov and Washington State Parks in a single query — with AI recommendations, real-time availability alerts, and calendar heat maps showing the best times to book**

**SEATTLE, WA — Spring 2026** — campnw today launched campnw v1.0, a campsite discovery and monitoring platform built specifically for campers in Washington, Oregon, and Idaho. For the first time, Pacific Northwest campers can search real availability across federal campgrounds (via Recreation.gov) and Washington State Parks in a single search — with AI-powered recommendations, predictive availability forecasts, and instant push notifications when cancellations appear at fully-booked campgrounds.

---

Every summer, millions of Pacific Northwest residents try to go camping. The process is the same for nearly all of them: open three or four booking websites, run separate searches on each, manually cross-reference results, and refresh pages hoping a cancellation opens up at the campground they actually want. Recreation.gov covers national parks and forests. GoingToCamp covers Washington State Parks. Neither talks to the other, and neither answers the question campers actually have: "Where can I go camping this weekend, and what's the best option for my trip?"

campnw answers that question. The platform searches 685+ campgrounds across Washington, Oregon, and Idaho simultaneously, returning availability filtered by drive time from home, amenity preferences, and date patterns — in under four seconds. A calendar heat map shows which weekends have the most availability across all matching campgrounds, making it easy to find the right window before committing to dates. When a target campground is fully booked, campnw watches it around the clock and sends a push notification the moment a site opens up — with a direct link to book before it disappears.

"I built campnw because I was spending 45 minutes searching every time I wanted to plan a camping trip, and I still wasn't getting a good answer," said Max Pengilly, founder of campnw. "The booking systems are actually fine — they have good data. The problem is discovery. campnw is a discovery layer on top of the systems that already exist. We're not trying to replace recreation.gov. We're trying to make it something people can actually use."

campnw works by maintaining a registry of 685+ PNW campgrounds enriched with drive time estimates from six major cities (Seattle, Bellevue, Portland, Spokane, Bellingham, and Moscow, ID) and searchable tags including lakeside, pet-friendly, old-growth, beach, RV-friendly, and more. When a user searches, campnw filters the registry first, then checks live availability in parallel across providers — returning only campgrounds with actual open sites for the specified dates. The result is the complete picture of what's available, not a list of campgrounds where availability might exist.

For v1.0, campnw introduces AI-powered natural language search, letting users describe what they want in plain English ("lakeside camping near Bellingham for a long weekend in July, dog-friendly") and automatically translating that into a structured search. A conversational trip planner helps users build multi-stop itineraries, checking availability at each proposed stop and providing drive time between sites.

"I've been using the beta for two months," said Sarah Chen, a nurse practitioner from Seattle who camps 6-8 times per year. "Last month I found a lakeside site at a state park I'd never heard of, 90 minutes from home, that was open the exact weekend I needed. I never would have found it searching normally. I booked it in five minutes."

campnw is available now at campable.co. Search and basic monitoring are free.

---

## Internal FAQ

### Why are we building this?

The personal tool phase validated the core thesis: the problem is real, the APIs are accessible, and the data is genuinely useful. The jump to consumer product is warranted because the working tool already has the hardest parts solved — multi-provider availability querying, the GoingToCamp WAF bypass, the registry with drive time enrichment, the watch/diff system. The surface area of what remains is mostly UX and distribution.

The camping market in the PNW is massive and underserved by discovery tools. Recreation.gov is authoritative but terrible at discovery. The Dyrt is great at community content but doesn't check real-time availability. Campnab monitors but doesn't discover. The gap between "I want to go camping" and "I have a booked site" is wide and filled with friction. campnw closes that gap.

### Who is the target customer?

Pacific Northwest residents who camp 2-8 times per year and book primarily through recreation.gov or Washington State Parks. They're not technical users (camply exists for them), but they're not first-time campers either — they know what they want, they're frustrated by the fragmentation of booking systems, and they'd pay for a tool that saves them 45 minutes of research every time they plan a trip.

The total addressable base is PNW campers who use managed sites: millions of people. The immediately reachable segment — those frustrated enough to try a new tool — is tens of thousands. Growth comes primarily through word of mouth in camping communities (Reddit: r/CampingandHiking, r/Seattle, r/Portland, r/pnwhiking), and through SEO on campground-specific searches ("Ohanapecosh campground availability 2026").

### How is this different from camply, Campnab, and Campflare?

**camply:** Open source CLI. Powerful for technical users who want to script their own monitoring. No web UI, no discovery, no WA State Parks coverage. campnw is what camply would be if you built a consumer product on top of it.

**Campnab:** Single-campground monitoring only. No discovery, no WA State Parks, no AI features, no calendar heat map. You have to already know which campground you want. Campnab is good at what it does; campnw does that plus everything before it.

**Campflare:** Polished monitoring product for rec.gov. US-wide (not PNW-specific), more expensive, no WA State Parks, no discovery. The UI is better than campnw v1.0 today, but campnw has multi-provider coverage and a roadmap toward AI-differentiated features that Campflare doesn't appear to be pursuing.

The honest summary: no competitor offers PNW-specific, multi-provider, discovery-first availability search with monitoring. campnw owns that combination.

### What's the business model?

**Free tier:**
- Unlimited searches
- Up to 3 active watches
- 7-day notification history
- Basic AI search

**campnw Pro ($5/month or $40/year):**
- Unlimited watches
- 15-minute polling frequency (vs. 30-min free)
- AI trip planner
- Predictive availability forecasts
- Shareable trip links
- Priority notification delivery

The pricing is intentionally low. Campflare charges $20+/month. At $5/month, the question becomes "why wouldn't I" rather than a deliberate purchase decision. The goal in year one is not revenue — it's usage data and word of mouth.

Advertising is not a consideration. The audience is too small and the trust cost is too high.

### What are the biggest risks?

Three risks worth honest discussion:

**API fragility.** The entire product depends on unofficial API endpoints. Recreation.gov's availability API has been stable for years — camply, Campnab, and Campflare all depend on it too, which means any change would affect the whole ecosystem and would surface quickly. GoingToCamp is a real risk: the WAF bypass is a hack, and it could break without warning. Mitigation is monitoring, fast response, and graceful degradation.

**Network effects and distribution.** campnw has no distribution advantage today. The tool has to earn its users through search, community, and genuine usefulness. This is not a technical risk but a go-to-market risk. The plan is SEO (campground + availability searches), camping subreddit presence, and letting the product's usefulness drive sharing.

**Scope creep.** The feature surface area is enormous — trip planning, reviews, photos, map view, native apps, Oregon/Idaho state parks. The risk is building too many things to mediocre quality rather than a few things exceptionally well. The P0/P1/P2 framework in the PRD is the discipline mechanism.

### Why AI?

Three places where AI genuinely reduces friction (not gimmicks):

**Natural language search** eliminates the form-filling step. Users who know what they want can describe it in English and get structured results. The alternative is a 6-field form that requires knowing our tag taxonomy. NL search lowers the learning curve to zero.

**Trip planner** compresses multi-stop trip research from 2 hours to 5 minutes. The value isn't the AI per se — it's that the AI can call campnw's own search engine and availability API as tools, integrating data that would require a user to run 6 separate searches manually.

**Predictive availability** is the most defensible AI feature because it requires campnw's own data, not just a model. The predictions get better the longer campnw has been polling — a genuine moat as data accumulates.

What AI doesn't do in campnw: write campground descriptions, rate sites, answer general questions about camping, or anything that requires it to make up information. The product is grounded in real data or it says so clearly.

### What's the 3-year vision?

**Year 1:** Establish campnw as the default discovery tool for PNW campers. 10,000 MAU, 500 Pro subscribers, strong word of mouth in Pacific Northwest outdoor communities.

**Year 2:** Expand coverage (Oregon/Idaho state parks, British Columbia day trips), deepen AI features with meaningful history data, launch native mobile apps. Pro subscriber growth to 3,000-5,000.

**Year 3:** Evaluate whether the model extends to other regions (Southwest, Mountain West, Southeast). The registry + provider architecture is designed to be multi-region from the start — it's a data and provider question, not an architectural rebuild. Alternatively, go deep on the PNW and build the most complete, most trusted tool for this specific geography.

The 3-year ceiling scenario: campnw becomes the product that every PNW camper opens before they book, the way Hopper is what people open before they buy flights. Campsite booking is less frequent than flights, but the planning anxiety is equivalent, and the market for a tool that removes it is real.

---

## External FAQ

### How does campnw find availability?

campnw checks availability directly from Recreation.gov (for federal campgrounds — national parks, national forests) and Washington State Parks (GoingToCamp platform) in real time. When you search, campnw filters its registry of 685+ campgrounds to match your criteria, then queries those booking systems live. The results you see reflect actual current availability, not cached data from days ago.

### Which campgrounds are supported?

campnw covers 685+ campgrounds across Washington, Oregon, and Idaho, including:

- National parks and national forests via Recreation.gov (Mt. Rainier, Olympic, North Cascades, Okanogan-Wenatchee, Mt. Baker-Snoqualmie, and more)
- 75 Washington State Parks via GoingToCamp (Fort Worden, Deception Pass, Moran, Dosewallips, Kalaloch, and more)
- Oregon and Idaho federal campgrounds via Recreation.gov (Crater Lake, Hells Canyon, Deschutes, and more)

What's not yet supported: Oregon and Idaho state parks (those run on ReserveAmerica), first-come-first-served sites without any online booking system, and private campgrounds. We show FCFS sites in results and flag them clearly — but you can't book them online anywhere.

### Is it free?

Yes. Search, basic monitoring (up to 3 watches), and AI-assisted search are free with no account required. campnw Pro ($5/month) adds unlimited watches, faster alert polling, the AI trip planner, and predictive availability forecasts.

### Can I book directly through campnw?

No. campnw is a discovery and monitoring tool, not a booking intermediary. When you find an available site, campnw gives you a direct link to Recreation.gov or GoingToCamp with your dates and site pre-filled. The actual booking happens on the official platform. This is intentional — we have no interest in adding a layer between you and the park.

### How accurate are the drive time estimates?

Drive times are pre-computed estimates from six PNW cities (Seattle, Bellevue, Portland, Spokane, Bellingham, Moscow ID) based on typical driving conditions. They don't account for traffic, seasonal road closures, or time of day. The estimates are meant to help you filter out campgrounds that are obviously too far, not to replace a real map query. For trip planning, always verify with Google Maps or Apple Maps.

### Does it work for RVs?

Yes. campnw has an RV-friendly tag you can filter by — these are campgrounds with hookups or pull-through sites suitable for larger rigs. The search doesn't currently filter by site-level hookup type (water/electric/full hookup) — that level of detail is on the booking link destination.

### Can I set alerts for specific campgrounds?

Yes. If a campground is fully booked for your target dates, you can add it to your watch list. campnw polls for cancellations and sends you a push notification or email the moment a site opens up — with a direct link to book. Free accounts can watch up to 3 campgrounds simultaneously. Pro accounts have unlimited watches.

### How does the AI recommendation work?

The AI features in campnw are grounded in real data, not general knowledge. Natural language search translates your plain-English query into a structured search using campnw's actual registry tags and campground data — the AI's job is translation, not campground knowledge. The trip planner calls campnw's own search and availability APIs as tools, so every suggestion it makes is backed by live data. The AI doesn't invent campgrounds or availability — if it's not in the registry, it won't suggest it.

Predictive availability (coming in a future update) is a statistical model trained on campnw's own polling history — it learns from what it has actually observed about cancellation patterns at each campground.

### Is my data private?

campnw collects the minimum necessary to provide the service: your search preferences, saved watches, and notification settings. We don't sell data to third parties. We don't show ads. Search history is used only to improve your personalized recommendations (opt-in), and you can export or delete your data at any time. We don't store payment data — billing is handled by Stripe.

---

*campnw is built and operated by Palouse Labs. For press inquiries: hello@palouselabs.com*
