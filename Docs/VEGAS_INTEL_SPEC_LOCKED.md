# VEGAS INTEL - COMPLETE SPECIFICATION

**Date:** January 14, 2026  
**Status:** LOCKED  
**Owner:** Kirk (Architect), Kevin (Sales Director)  
**Build Priority:** IMMEDIATE

---

## WHAT THIS IS

A sales intelligence weapon for Kevin. Not a dashboard. Not a CRM. A system that makes Kevin the smartest person in any room he walks into.

**Core Question Answered:**  
"Given this event, at this location, pulling this crowd—which restaurants win, and does Kevin have them or not?"

---

## THE VOICE

This is how the app talks. Direct. Urgent. Confident. No corporate dashboard bullshit.

| ❌ DON'T | ✅ DO |
|----------|-------|
| "Customer shows 14-day order gap" | "Bellagio hasn't ordered in 2 weeks. Something's wrong." |
| "Event projected +18% volume increase" | "F1 is 10 days out. Your Strip accounts are about to get slammed." |
| "Margin alert: upward price trend" | "Lock in now. Prices are climbing and they're not coming back down before CES." |
| "Churn risk score: 0.73" | "You're about to lose Aria. Call today or someone else will." |
| "Recommended action: contact" | "Pick up the phone." |

**The posture:** We're the smartest motherfuckers in the room. We built the model. We define how this is done.

---

## PAGE STRUCTURE

```
┌─────────────────────────────────────────────────────────────────────┐
│ VEGAS INTEL - Kevin's Sales Command Center                          │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│ SECTION 1: EVENT IMPACT DASHBOARD                                   │
│ ┌─────────────────────────────────────────────────────────────────┐ │
│ │ Upcoming events with crowd profiles and demand projections      │ │
│ │ "CES is in 3 weeks. 180,000 tech execs. Your corridor."         │ │
│ └─────────────────────────────────────────────────────────────────┘ │
│                                                                     │
│ SECTION 2: OPPORTUNITY RANKING                                      │
│ ┌───────────────────────────┐ ┌───────────────────────────────────┐ │
│ │ 🟢 EXISTING CUSTOMERS     │ │ 🔴 PROSPECTS (No Customer Yet)   │ │
│ │ Ranked by event impact    │ │ Ranked by missed opportunity     │ │
│ │ "Upsell these NOW"        │ │ "You're leaving money here"      │ │
│ └───────────────────────────┘ └───────────────────────────────────┘ │
│                                                                     │
│ SECTION 3: ALERTS                                                   │
│ ┌─────────────────────────────────────────────────────────────────┐ │
│ │ ⚠️ AT-RISK CUSTOMERS                                            │ │
│ │ "You're about to lose X. Call today or someone else will."      │ │
│ └─────────────────────────────────────────────────────────────────┘ │
│                                                                     │
│ SIDEBAR: INTEL SHEETS                                               │
│ ┌─────────────────────────────────────────────────────────────────┐ │
│ │ Generated sheets, pending, sent, tracking                       │ │
│ └─────────────────────────────────────────────────────────────────┘ │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## THE BEHAVIORAL DEMAND MODEL

This is the engine. Not a walk score. Not a distance formula. A matching model.

### The Flow

```
EVENT TYPE
    ↓
WHO is attending? (Demographics + Psychographics)
    ↓
CASINO CONTEXT (Pull factor, status, vibe)
    ↓
RESTAURANT FIT (Cuisine match, positioning)
    ↓
PROBABILITY: This crowd → This restaurant
    ↓
OUTPUT: Ranked opportunity list
```

### Event → Crowd Profile

| Event Type | Primary Demo | Psychographic | Cuisine Affinity |
|------------|--------------|---------------|------------------|
| CES | 35-55, male, high income | Time-poor, status-conscious | Steakhouse, sushi, fast-upscale |
| EDC | 21-35, mixed, medium income | Experience-seeking, social | Late night, shareable, Instagram-worthy |
| UFC Fight | 30-50, male, varied income | Tribal, celebratory | Sports bar, American, steakhouse |
| F1 | 35-55, high income, international | Luxury-seeking | Fine dining, international |
| Trade Convention | 40-60, mixed, business | Practical, networking | Casual groups, mid-tier |

### Casino Pull Factor

Each casino has a personality that attracts specific crowds:

| Casino | Vibe | Who It Pulls |
|--------|------|--------------|
| Wynn/Encore | Luxury, status | High rollers, execs |
| Cosmo | Trendy, young money | Tech bros, influencers |
| Venetian | Business, convention | Corp travelers, groups |
| Fremont | Gritty, authentic | Creatives, locals |
| MGM | Mass market | Everyone (diluted) |

### The Match

```
EVENT (CES)
    → CROWD (tech execs, high income, time-poor)
    → CASINO CONTEXT (Wynn = luxury match ✅)
    → RESTAURANT FIT (steakhouse = cuisine match ✅)
    → PROBABILITY: HIGH

EVENT (EDC)
    → CROWD (young, party, budget-conscious)  
    → CASINO CONTEXT (Wynn = mismatch ❌)
    → RESTAURANT FIT (steakhouse = mismatch ❌)
    → PROBABILITY: LOW
```

---

## OPPORTUNITY RANKING OUTPUT

The model produces TWO lists:

### 🟢 Existing Customers (Upsell)

> "You have the account. This event will spike their demand. Call now."

```
1. MGM Grand - Gallagher's Steakhouse     +25-45%    CALL NOW
   CES crowd is their demo. Prime positioning.
   
2. Venetian - Grand Lux Cafe              +20-35%    CALL NOW
   Convention overflow. They'll get slammed.
   
3. Caesars - Gordon Ramsay                +15-30%    THIS WEEK
   Secondary corridor. Still significant.
```

### 🔴 Prospects (Gap = Money on the Table)

> "You DON'T have this account. This event will spike THEIR demand. That's your money walking out the door."

```
1. Wynn - SW Steakhouse                   +30-50%    PROSPECT
   You don't have them. They're sitting in prime CES corridor.
   Their competitor next door is already your customer.
   
2. Encore - Sinatra                       +25-40%    PROSPECT  
   Same demo, same corridor. Missing opportunity.
   
3. Aria - Jean Georges                    +20-35%    PROSPECT
   High-end, matches the crowd. Go get it.
```

---

## PROJECTIONS: P30/P70 RANGE

We don't give point estimates. We give ranges.

**Not:** "You'll see +35%"  
**But:** "We're projecting 25-45% increased demand"

| Confidence | Range Width | When to Use |
|------------|-------------|-------------|
| HIGH | Narrow (±10%) | Strong historical match, known event |
| MEDIUM | Moderate (±15%) | Similar events, inferred match |
| LOW | Wide (±25%) | New event, limited data |

The range protects Kevin while still delivering value:
- Reality is +30%? Kevin nailed it.
- Reality is +22%? Kevin was close.
- Reality is +50%? Kevin was conservative.

---

## THE INTEL SHEET

Kevin's leave-behind. Not a quote. An intelligence product.

### Purpose

| For Prospects | For Existing Customers |
|---------------|------------------------|
| "Who is this guy and why should I care?" | "What's coming and why should I act?" |
| Shows Kevin knows their business | Reinforces Kevin as strategic partner |
| Opens conversation without asking | Justifies the upsell conversation |

### Content Structure

```
┌─────────────────────────────────────────────────────────────────────┐
│                                                                     │
│  US OIL SOLUTIONS                                                   │
│  VEGAS INTEL BRIEFING                                               │
│                                                                     │
│  Prepared for: [Restaurant Name, Casino]                            │
│  Event: [Event Name] | [Dates]                                      │
│  Generated: [Date]                                                  │
│                                                                     │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  THE SITUATION                                                      │
│                                                                     │
│  [Attendance] attendees. [Duration]. Your corridor.                 │
│  [Event] draws [demographic]—[why this matters to them].            │
│                                                                     │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  PROJECTED DEMAND IMPACT                                            │
│                                                                     │
│  Our platform is projecting [X-Y%] increased demand                 │
│  for [cuisine type] in your corridor during [event] week.           │
│                                                                     │
│       LOW ESTIMATE    ████████████░░░░░░    HIGH ESTIMATE           │
│           +X%                                    +Y%                │
│                                                                     │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  MARKET CONTEXT                                                     │
│                                                                     │
│  • [ZL price movement]                                              │
│  • [Supply/demand signal]                                           │
│  • [Actionable recommendation]                                      │
│                                                                     │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ABOUT US OIL SOLUTIONS                                             │
│                                                                     │
│  Las Vegas's premier cooking oil supplier.                          │
│  150+ restaurants. 31 casino properties. Same-day delivery.         │
│                                                                     │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  Kevin [Last Name]                                                  │
│  Sales Director                                                     │
│  kevin@usoilsolutions.com | (702) 555-1234                          │
│                                                                     │
│  "I'd rather you hear it from me now than feel it in your           │
│   kitchen during the rush."                                         │
│                                                                     │
├─────────────────────────────────────────────────────────────────────┤
│  Powered by quantitative event modeling and local market            │
│  intelligence. Projections for planning purposes.                   │
└─────────────────────────────────────────────────────────────────────┘
```

### Generation

- **Engine:** Gemini 2.0 Flash (visual generation)
- **Output:** Shareable link + downloadable PDF
- **Tracking:** View count, when opened

---

## AT-RISK ALERTS

Customers who are slipping away.

### Triggers

| Signal | Threshold | Alert |
|--------|-----------|-------|
| Days since last order | >14 days | "Hasn't ordered in 2 weeks. Something's wrong." |
| Volume decline | >20% vs 30-day avg | "Volume dropping. Find out why." |
| Missed delivery | Any | "They skipped a delivery. Red flag." |
| Pattern break | Deviation from norm | "This isn't normal for them. Call." |

### Alert Format

```
⚠️ WYNN BUFFET
   18 days since last order
   They used to order like clockwork.
   Either they found someone else or something's broken.
   
   [Call Now]  [View History]
```

---

---

## ACTION BUTTONS

| Action | Implementation | Status |
|--------|----------------|--------|
| Generate Intel Sheet | Gemini 2.0 Flash → shareable link | ✅ Build |
| Copy Outreach | AI-generated text → clipboard | ✅ Build |
| Add to Calendar | .ics file download | ✅ Build |
| Call | ❌ Removed | — |
| Quote | ⏳ Later phase | — |

---

## DATA ARCHITECTURE

### We READ (from Glide, never write)

```
ops.vegas_restaurants      ← Customer master data
ops.vegas_casinos          ← Casino relationships  
ops.vegas_fryers           ← Fryer counts
ops.vegas_export_list      ← Full customer list
```

### We OWN (our tables)

```
ops.vegas_events           ← Event calendar (scraped + manual)
ops.vegas_event_profiles   ← Demo/psycho profiles per event type
ops.vegas_casino_profiles  ← Casino pull factors, vibes
ops.vegas_cuisine_match    ← Event type → cuisine affinity scores
ops.vegas_intel_sheets     ← Generated sheets, tracking
ops.vegas_customer_scores  ← Computed at-risk, priority rankings
ops.vegas_activity_log     ← Engagement tracking
```



---

## EVENT DATA SOURCES

### Primary: Ticketmaster Discovery API

- Official, reliable
- Concerts, shows, sporting events
- Free tier: 5,000 calls/day
- Has attendance estimates

### Secondary: Manual CSV Upload

- Kevin maintains major conventions (CES, SEMA, etc.)
- Announced yearly, stable data
- Kevin controls what matters most

### Tertiary: LVCVA Scraper

- Convention calendar backup
- Weekly refresh
- Public data

---

## BUILD PHASES

### Phase 1: Foundation (Week 1)
- [ ] Install shadcn components (calendar, sheet, hover-card, collapsible)
- [ ] Create `/vegas-intel/_files/` component structure
- [ ] Build page layout (3 sections + sidebar)
- [ ] Migrate existing Glide data display

### Phase 2: Event Calendar (Week 1-2)
- [ ] Create `ops.vegas_events` table
- [ ] Build Ticketmaster API integration
- [ ] Build manual CSV upload for conventions
- [ ] Build EventCalendar + EventCard components

### Phase 3: Behavioral Model (Week 2)
- [ ] Create profile tables (event, casino, cuisine match)
- [ ] Build ranking algorithm
- [ ] Implement P30/P70 range calculations
- [ ] Build UpsellTargetCard + ProspectCard components

### Phase 4: Intel Sheet (Week 2-3)
- [ ] Integrate Gemini 2.0 Flash API
- [ ] Build sheet generation flow
- [ ] Create shareable link infrastructure
- [ ] Build sidebar tracking panel

### Phase 5: Alerts (Week 3)
- [ ] Build at-risk detection logic
- [ ] Connect margin signals to ZL forecasts
- [ ] Build AtRiskCard + MarginAlert components

### Phase 6: Polish (Week 4)
- [ ] The voice - audit all copy
- [ ] Mobile responsiveness
- [ ] Performance optimization
- [ ] Kevin UAT

---

## WHAT SUCCESS LOOKS LIKE

Kevin walks into SW Steakhouse at Wynn with a branded Intel Sheet:

> "180,000 people. 4 days. Your corridor. We're projecting 25-45% increased demand. Your neighbor already locked in. Here's my number."

That's not a sales call. That's a power move.

---

## LOCKED

This specification is locked. Changes require architect approval.

**Build starts now.**
