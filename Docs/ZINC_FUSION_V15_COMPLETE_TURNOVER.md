# ZINC-FUSION-V15: COMPLETE TURNOVER DOCUMENT
## The 22 Architecture - From Data to Discovery to Decision
### January 12, 2026

---

# PART 1: PROJECT HISTORY & CONTEXT

## 1.1 The Mission

**Client:** U.S. Oil Solutions (Las Vegas, NV)
**Primary User:** Chris Stacy (Procurement)
**Project Codename:** Crystal Ball
**Architect:** Kirk (ZINC Digital)

**The Question Chris Needs Answered:**
> "Should I buy oil today or wait?"

**The Edge Chris Wants:**
> Information that others don't have. Before they have it.

**The Business Model:**
"Split The Difference" (STD) - Chris shares cost savings from strategic purchasing with customers. The AI's ability to generate cost avoidance directly drives customer loyalty and competitive advantage.

---

## 1.2 The 6-Month Journey

| PHASE | VERSION | FOCUS | OUTCOME |
|-------|---------|-------|---------|
| Sep 2024 | CBI-V13 | Initial forecasting | Foundation built |
| Oct 2024 | CBI-V14 | 11 Specialists | Domain taxonomy locked |
| Nov 2024 | CBI-V14.5 | Data ingestion | Pipeline architecture |
| Dec 2024 | V15 Start | Chronos-2 integration | Model stack defined |
| Jan 2026 | V15 Current | Pulse Engine attempt | Incomplete - paradigm wrong |

**Recurring Problems:**
- AI kept cutting corners, reducing data, simplifying models
- "Light" versions that gutted the system's power
- Hours/days of training wasted on broken pipelines
- Architecture drift - components not talking to each other
- Placeholder data passed off as real signals

**The ALL DATA Policy:**
Created to prevent AI from reducing feature sets. Rule: USE ALL DATASETS, ALL DATA, ALL THE TIME. AutoGluon figures out relevance. We provide EVERYTHING.

---

## 1.3 The Breakthrough (January 12, 2026)

**The Problem We Finally Named:**

```
2+2=4 (What we had):
─────────────────────
Data → Features → Model → Prediction
"Here's the forecast"

The model reports. It doesn't THINK.
```

**The Solution:**

```
2+2=22 (What we're building):
─────────────────────────────
Data → HUNTERS → Discoveries → Synthesis → Forecast + STORY
"Here's what it MEANS that nobody else sees"

The Hunter finds signal. It THINKS. It LEARNS.
```

**Key Insight:**
> "The edge isn't in the model. The edge is in KNOWING THINGS BEFORE OTHERS."

**The Specialists' True Purpose:**
They aren't just models. They're HUNTERS. Each one hunts for information asymmetry in their domain - signals that predict price movement before the market prices them in.

---

# PART 2: CURRENT STATE

## 2.1 Data Inventory

### RAW LAYER (Source Data)
| TABLE | ROWS | DATE RANGE | STATUS |
|-------|------|------------|--------|
| market_futures_1d | 432,152 | 1960s-present | ✅ DEEP |
| market_futures_1h | 4,967,276 | Multi-year | ✅ DEEP |
| fred_observations_1d | 505,800 | Decades | ✅ DEEP |
| weather_noaa_1d | 215,320 | Multi-year | ✅ DEEP |
| fx_spot_1d | 59,105 | Multi-year | ✅ DEEP |
| cftc_cot_1w | 18,372 | 20+ years | ✅ DEEP |
| usda_export_sales_1w | 9,712 | Multi-year | ✅ GOOD |
| usda_wasde_1m | 12,548 | Decades | ✅ GOOD |
| epa_rin_prices_1d | 208 | Recent | ⚠️ THIN |
| news_articles_1d | 2,878 | Recent | ⚠️ THIN |
| yahoo_equity_1d | 9,534 | Multi-year | ✅ GOOD |
| options_futures_1d | 28,648 | Multi-year | ✅ GOOD |

**TOTAL RAW: ~6.3 MILLION ROWS**

### TRAINING LAYER (Engineered Features)
| TABLE | ROWS | STATUS |
|-------|------|--------|
| specialist_crush_1d | 23,487 | ✅ BUILT |
| specialist_china_1d | 27,492 | ✅ BUILT |
| specialist_fx_1d | 80,165 | ✅ BUILT |
| specialist_fed_1d | 48,174 | ✅ BUILT |
| specialist_tariff_1d | 42,414 | ✅ BUILT |
| specialist_energy_1d | 45,380 | ✅ BUILT |
| specialist_biofuel_1d | 42,055 | ✅ BUILT |
| specialist_palm_1d | 24,037 | ✅ BUILT |
| specialist_volatility_1d | 35,088 | ✅ BUILT |
| specialist_substitutes_1d | 42,706 | ✅ BUILT |
| specialist_trump_effect_1d | 2,273 | ⚠️ NEW |
| core_features | 6,381 | ✅ BUILT |

**TOTAL TRAINING: ~450K ROWS**

### MODEL LAYER (Predictions)
| TABLE | ROWS | STATUS |
|-------|------|--------|
| oof_predictions | 0 | ❌ EMPTY |
| model_registry | 18 | ⚠️ PARTIAL |

### GOLD LAYER (Intelligence)
| TABLE | ROWS | STATUS |
|-------|------|--------|
| intel_drops | 0 | ❌ EMPTY |

### ANALYTICS LAYER (Dashboard)
| TABLE | ROWS | STATUS |
|-------|------|--------|
| zl_live | 1 | ❌ EMPTY |

---

## 2.2 Infrastructure

### Inngest Jobs (Data Ingestion)
```
EXISTING (11 functions - need fixes):
├── fred-daily.ts         → FRED economic data
├── yahoo-eod.ts          → Market futures, equities
├── cftc-weekly.ts        → COT positioning
├── federal-register.ts   → Policy/regulatory
├── nyfed-daily.ts        → Fed rates
├── cbp-trade.ts          → Trade flows
├── ice-releases.ts       → Exchange data
├── farmdoc-rins.ts       → RIN prices
├── aei-trade.ts          → Trade data
├── conab-news.ts         → Brazil agriculture
├── zl-price.ts           → Live ZL price

STATUS: Need to be fixed and set LIVE
BACKLOG: New URLs from Jan 11 need jobs built
```

### Database
- **Platform:** Prisma PostgreSQL (Neon)
- **Schemas:** raw, training, model, gold, analytics, ops, metadata, silver

### Compute
- **Serverless:** Vercel (ingestion, features, inference)
- **Training:** Mac M4 Pro (local) or Modal/RunPod (cloud)

### Frontend
- **Framework:** Next.js on Vercel
- **Charts:** TradingView Lightweight Charts

---

## 2.3 Model Architecture (Designed, Not Yet Trained)

```
L0 LAYER (Base Predictors):
├── CORE: TimeSeriesPredictor (Chronos-2/Bolt)
│   └── All features, all horizons
│   └── Tactical (5d/21d): Chronos-Bolt-Small
│   └── Strategic (63d/126d): Chronos-2 with LoRA
│
└── SPECIALISTS (×11): TabularPredictor
    └── Domain-specific features
    └── Quantile regression [P10, P50, P90, P95]
    └── 8-fold cross-validation
    └── Output: OOF predictions

L1 LAYER (Meta-Learner):
└── Fuses 36 OOF columns (11 specialists × 3 + 1 core × 3)
└── Quantile regression
└── Learns which specialists to trust when

L2 LAYER (Ensemble):
└── Final weighted combination
└── Regime-aware weighting

L3 LAYER (Monte Carlo):
└── 10,000 simulations
└── P10/P50/P90/P95 probability cones
└── Risk quantification
```

---

## 2.4 The 11 Specialists

| # | DOMAIN | WHAT IT HUNTS | KEY SIGNALS |
|---|--------|---------------|-------------|
| 1 | CRUSH | Supply-side squeeze from refiner economics | Margin compression, capacity utilization, basis |
| 2 | CHINA | Demand-side pressure from world's largest buyer | COFCO activity, port stocks, import pace, hog margins |
| 3 | FX | Currency impact on trade competitiveness | USD/BRL, DXY, carry trade flows |
| 4 | FED | Macro policy impact on commodity prices | Rates, yield curve, liquidity conditions |
| 5 | TARIFF | Trade policy disruption | Section 301, retaliatory measures, trade agreements |
| 6 | ENERGY | Cross-commodity correlation with crude/gas | WTI, diesel, refining margins |
| 7 | BIOFUEL | Renewable mandate impact on demand | RIN prices, RVO obligations, 45Z credits, LCFS |
| 8 | PALM | Substitute pricing and spread dynamics | CPO spread, Indonesia B40, production estimates |
| 9 | VOLATILITY | Risk regime and tail events | VIX, term structure, realized vs implied |
| 10 | SUBSTITUTES | Alternative oil competition | Canola, sunflower, corn oil spreads |
| 11 | TRUMP_EFFECT | Political/policy volatility | Executive orders, Truth Social, trade threats |

---

# PART 3: THE HUNTER ARCHITECTURE

## 3.1 What a Hunter Does

**A Hunter is NOT:**
- A calculator that reports data
- A static prompt that runs daily
- A feature generator that outputs the same thing every time

**A Hunter IS:**
- An AI agent that actively investigates
- A pattern detector trained on 25 years of history
- A learning system that improves every week
- A signal finder that discovers the 22

---

## 3.2 The Full Hunter Behavior Loop

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           HUNTER BEHAVIOR LOOP                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  1. TRIGGER                                                                 │
│     └── Anomaly detected in domain data                                     │
│     └── Example: "Crush margin at 1.8 percentile"                           │
│                                                                             │
│  2. DECIDE                                                                  │
│     └── What should I investigate?                                          │
│     └── Query pattern memory: "Have I seen this before?"                    │
│     └── Identify related domains to check                                   │
│                                                                             │
│  3. GATHER                                                                  │
│     └── Use tools: Database, Scraper, News, Cross-Domain APIs               │
│     └── Pull historical patterns from memory                                │
│     └── Check confirming/contradicting signals                              │
│                                                                             │
│  4. CORRELATE                                                               │
│     └── What does this mean together?                                       │
│     └── Cross-domain alignment check                                        │
│     └── Convergence/divergence analysis                                     │
│                                                                             │
│  5. DISCOVER                                                                │
│     └── Output: Story + Prediction + Confidence                             │
│     └── "Supply squeeze imminent - 4 week window, 87% confidence"           │
│     └── Evidence chain documented                                           │
│                                                                             │
│  6. LEARN                                                                   │
│     └── Store pattern in memory                                             │
│     └── Tag with regime context                                             │
│     └── Link to related patterns                                            │
│     └── Update base rates when outcome known                                │
│                                                                             │
│  7. GATHER MORE                                                             │
│     └── Find similar historical setups                                      │
│     └── Build pattern clusters                                              │
│     └── Strengthen cross-domain correlations                                │
│                                                                             │
│  8. SANITY CHECK                                                            │
│     └── Am I still grounded?                                                │
│     └── Does current regime match pattern regime?                           │
│     └── Is sample size sufficient for confidence?                           │
│     └── Am I ignoring contradicting signals?                                │
│     └── Am I straying from my domain?                                       │
│     └── IF DRIFT: Return to base, flag uncertainty                          │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3.3 The Pattern Memory Bank

Every Hunter maintains a memory of learned patterns:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         PATTERN MEMORY STRUCTURE                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  pattern_id:        crush_margin_squeeze_001                                │
│  domain:            CRUSH                                                   │
│  name:              "Margin Compression Squeeze"                            │
│                                                                             │
│  TRIGGER CONDITION:                                                         │
│  ├── metric:        crush_margin_board                                      │
│  ├── condition:     percentile < 5                                          │
│  └── threshold:     < $0.45/bushel                                          │
│                                                                             │
│  HISTORICAL PERFORMANCE:                                                    │
│  ├── occurrences:   47                                                      │
│  ├── hits:          38                                                      │
│  ├── accuracy:      80.9%                                                   │
│  ├── avg_return:    +6.2% over 21 days                                      │
│  ├── avg_lead_time: 18 trading days                                         │
│  └── last_updated:  2026-01-11                                              │
│                                                                             │
│  REGIME BREAKDOWN:                                                          │
│  ├── bull_trending:    89% (24/27)                                          │
│  ├── bear_trending:    71% (5/7)                                            │
│  ├── choppy_sideways:  75% (6/8)                                            │
│  └── crisis_volatile:  60% (3/5)                                            │
│                                                                             │
│  CROSS-DOMAIN CORRELATIONS:                                                 │
│  ├── CHINA (cofco_accumulation):     +18% accuracy when both fire           │
│  ├── WEATHER (brazil_stress):        +12% accuracy when both fire           │
│  └── ENERGY (diesel_margin_high):    +8% accuracy when both fire            │
│                                                                             │
│  ANTI-CORRELATIONS (Contradicting signals):                                 │
│  ├── FED (hawkish_pivot):            -15% accuracy when present             │
│  └── PALM (cpo_collapse):            -10% accuracy when present             │
│                                                                             │
│  NOTABLE INSTANCES:                                                         │
│  ├── 2019-07-15: +8.3% in 4 weeks (bull regime)                             │
│  ├── 2021-03-22: +12.1% in 6 weeks (with China signal)                      │
│  ├── 2023-09-01: -2.1% MISS (Fed pivot, flagged as regime exception)        │
│  └── 2024-11-18: +5.7% in 3 weeks (most recent)                             │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3.4 Regime Guardrails

Hunters stay sane through explicit boundaries:

| GUARDRAIL | IMPLEMENTATION |
|-----------|----------------|
| **Regime Tagging** | Every pattern tagged with regime(s) it occurred in |
| **Regime Matching** | Only apply patterns that match current regime (±1 category) |
| **Sample Size Floor** | Confidence capped if occurrences < 10 |
| **Contradiction Flagging** | Must acknowledge opposing signals in output |
| **Domain Boundary** | Hunter cannot make claims outside its domain |
| **Drift Detection** | If reasoning chain strays, return to fundamentals |
| **Confidence Calibration** | Stated confidence must match historical accuracy |
| **Human Escalation** | Unusual patterns (< 3 occurrences) flagged for review |

---

## 3.5 The Weekly Intelligence Cycle

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         WEEKLY INTELLIGENCE CYCLE                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  MONDAY - FRIDAY (Daily Operations):                                        │
│  ═══════════════════════════════════                                        │
│                                                                             │
│  5:00 AM CT │ DATA INGESTION                                                │
│             │ └── 11+ Inngest jobs pull fresh data                          │
│             │ └── Raw tables updated                                        │
│                                                                             │
│  5:45 AM CT │ FEATURE ENGINEERING                                           │
│             │ └── Specialist feature tables refreshed                       │
│             │ └── Core features computed                                    │
│                                                                             │
│  6:30 AM CT │ HUNTERS RUN                                                   │
│             │ └── All 11 Hunters execute                                    │
│             │ └── Anomaly detection                                         │
│             │ └── Pattern matching against memory                           │
│             │ └── Cross-domain correlation                                  │
│             │ └── Discoveries generated                                     │
│                                                                             │
│  7:00 AM CT │ SYNTHESIS                                                     │
│             │ └── AI synthesizes discoveries into narrative                 │
│             │ └── The Story Nobody Else Has                                 │
│                                                                             │
│  7:30 AM CT │ INFERENCE                                                     │
│             │ └── Models generate forecasts                                 │
│             │ └── P10/P50/P90/P95 probabilities                             │
│                                                                             │
│  8:00 AM CT │ DASHBOARD READY                                               │
│             │ └── Chris sees: Price + Confidence + Story                    │
│                                                                             │
│  SATURDAY (Weekly Learning):                                                │
│  ═══════════════════════════                                                │
│                                                                             │
│  6:00 AM CT │ VALIDATION                                                    │
│             │ └── Pull predictions from 3+ weeks ago                        │
│             │ └── Compare to actual outcomes                                │
│             │ └── Score each prediction: HIT or MISS                        │
│             │ └── Score each pattern: Update accuracy                       │
│                                                                             │
│  8:00 AM CT │ LEARNING                                                      │
│             │ └── Update pattern accuracy rates                             │
│             │ └── Adjust confidence calibration                             │
│             │ └── Strengthen correlations that worked                       │
│             │ └── Deprecate patterns that stopped working                   │
│             │ └── Tag regime exceptions                                     │
│                                                                             │
│  10:00 AM CT│ MODEL RETRAINING                                              │
│             │ └── L0 Specialists retrain on validated signals               │
│             │ └── L0 Core retrains                                          │
│             │ └── L1 Meta-learner retrains                                  │
│             │ └── Only PROVEN patterns become features                      │
│                                                                             │
│  12:00 PM CT│ REGISTRY UPDATE                                               │
│             │ └── New model versions registered                             │
│             │ └── Performance metrics logged                                │
│             │ └── Ready for next week                                       │
│                                                                             │
│  RESULT: Hunters are MEASURABLY SMARTER every Monday                        │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3.6 Hunter Output → Training Features

The Hunter's discoveries replace Pulse Drops as training features:

```sql
-- gold.hunter_signals_1d (replaces intel_drops)

as_of_date          DATE          -- Point-in-time date
domain              TEXT          -- CRUSH, CHINA, etc.
signal_name         TEXT          -- Pattern identifier
signal_strength     FLOAT         -- How strong is signal today (0-1)
pattern_accuracy    FLOAT         -- Historical hit rate (LEARNED, updated weekly)
regime              TEXT          -- Current market regime
regime_match        FLOAT         -- How well current regime matches pattern (0-1)
confidence          FLOAT         -- signal_strength × pattern_accuracy × regime_match
direction           INT           -- -1 (bearish), 0 (neutral), 1 (bullish)
pressure_5d         FLOAT         -- Expected % move, 5 days
pressure_21d        FLOAT         -- Expected % move, 21 days
pressure_63d        FLOAT         -- Expected % move, 63 days
cross_domain_signals JSONB        -- Supporting signals from other domains
contradicting_signals JSONB       -- Opposing signals (for transparency)
evidence            JSONB         -- Raw data supporting discovery
story               TEXT          -- Human-readable narrative
last_validated      TIMESTAMP     -- When pattern accuracy was last updated
created_at          TIMESTAMP     -- When this signal was generated
```

---

## 3.7 Bootstrap Sequence (Day 1 Intelligence)

The Hunter doesn't start dumb. It inherits 25 years of knowledge:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         BOOTSTRAP SEQUENCE                                  │
│                         (One-Time, Before Go-Live)                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  STEP 1: HISTORICAL PATTERN SCAN                                            │
│  ════════════════════════════════                                           │
│  For each domain (CRUSH, CHINA, etc.):                                      │
│  └── Scan full history (2000-2026)                                          │
│  └── Identify all anomaly occurrences (z-score > 2)                         │
│  └── Identify all threshold breaches                                        │
│  └── Log each occurrence with timestamp                                     │
│                                                                             │
│  STEP 2: OUTCOME VALIDATION                                                 │
│  ══════════════════════════                                                 │
│  For each identified pattern occurrence:                                    │
│  └── What happened to ZL price in next 5/21/63 days?                        │
│  └── Direction correct? (HIT/MISS)                                          │
│  └── Magnitude captured? (within 50% of actual)                             │
│  └── Log outcome                                                            │
│                                                                             │
│  STEP 3: ACCURACY CALCULATION                                               │
│  ═════════════════════════════                                              │
│  For each pattern type:                                                     │
│  └── Calculate overall accuracy (hits/total)                                │
│  └── Calculate regime-specific accuracy                                     │
│  └── Calculate average return when pattern fires                            │
│  └── Calculate average lead time                                            │
│                                                                             │
│  STEP 4: CROSS-DOMAIN CORRELATION                                           │
│  ═════════════════════════════════                                          │
│  For each pattern:                                                          │
│  └── When this fires, what else fires within ±5 days?                       │
│  └── Does combined signal improve accuracy?                                 │
│  └── Build correlation matrix                                               │
│                                                                             │
│  STEP 5: POPULATE MEMORY BANK                                               │
│  ═════════════════════════════                                              │
│  Create pattern records with:                                               │
│  └── Full historical statistics                                             │
│  └── Regime breakdowns                                                      │
│  └── Cross-domain correlations                                              │
│  └── Notable instances                                                      │
│                                                                             │
│  RESULT:                                                                    │
│  ════════                                                                   │
│  Hunter boots with:                                                         │
│  ├── 200+ validated patterns across 11 domains                              │
│  ├── Historical accuracy rates (not guesses)                                │
│  ├── Regime-specific adjustments                                            │
│  ├── Cross-domain correlation matrix                                        │
│  └── Ready to hunt with PhD-level market knowledge                          │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# PART 4: TECHNICAL IMPLEMENTATION

## 4.1 Vercel AI SDK 6 Integration

The Hunters run on Vercel's AI infrastructure:

```typescript
// Hunter Agent Definition (Vercel AI SDK 6)

import { ToolLoopAgent } from 'ai';
import { anthropic } from '@ai-sdk/anthropic';

const CrushHunter = new ToolLoopAgent({
  model: anthropic('claude-sonnet-4-5-20250929'),
  
  system: CRUSH_HUNTER_SYSTEM_PROMPT, // Domain-specific, not generic
  
  tools: {
    queryDatabase: /* Prisma query tool */,
    queryPatternMemory: /* Pattern bank lookup */,
    checkCrossDomain: /* Query other Hunters */,
    scrapeSource: /* Web scraper for news */,
    analyzeAnomaly: /* Statistical analysis */,
    validateRegime: /* Regime matching */,
  },
  
  stopWhen: (result) => 
    result.confidence > 0.75 ||  // High enough confidence
    result.steps > 12 ||         // Max investigation depth
    result.driftDetected         // Sanity check failed
});

// Execution
const discovery = await CrushHunter.run({
  trigger: {
    type: 'ANOMALY',
    metric: 'crush_margin_board',
    value: 0.38,
    percentile: 1.8,
    zscore: -2.4
  },
  as_of_date: '2026-01-12',
  current_regime: 'bull_trending'
});
```

---

## 4.2 Database Schema Strategy

### PRINCIPLE: USE EXISTING SCHEMA FIRST

Creating new schema is expensive - migration risks, testing overhead, potential for errors. Before adding ANY new table:

1. **Check if existing table can be extended** - Can we add columns to existing tables?
2. **Check if existing table can be repurposed** - Is there an empty or underused table?
3. **Only create new if absolutely necessary** - And even then, keep it minimal

**Existing tables we should USE:**
- `gold.intel_drops` (0 rows) → Can become Hunter signal output
- `model.oof_predictions` (0 rows) → Already exists for predictions
- `ops.data_source_registry` → Can track pattern metadata
- `training.specialist_*_1d` → Already built, extend if needed

**New tables only if required:**
- `gold.pattern_memory` → Needed for learned patterns (no existing equivalent)
- `gold.hunter_predictions` → Could potentially use `model.oof_predictions` instead

### PROPOSED SCHEMA ADDITIONS (Minimal)

```prisma
// Add to prisma/schema.prisma

// ============================================
// GOLD LAYER - Hunter Intelligence Output
// ============================================

model HunterSignal {
  id                    String   @id @default(cuid())
  as_of_date            DateTime
  domain                String   // CRUSH, CHINA, etc.
  signal_name           String   // Pattern identifier
  signal_strength       Float    // 0-1
  pattern_accuracy      Float    // Historical hit rate
  regime                String   // Current regime
  regime_match          Float    // 0-1
  confidence            Float    // Combined confidence
  direction             Int      // -1, 0, 1
  pressure_5d           Float?
  pressure_21d          Float?
  pressure_63d          Float?
  cross_domain_signals  Json?
  contradicting_signals Json?
  evidence              Json
  story                 String   @db.Text
  last_validated        DateTime?
  created_at            DateTime @default(now())
  
  @@index([as_of_date, domain])
  @@index([domain, signal_name])
  @@map("hunter_signals_1d")
  @@schema("gold")
}

model PatternMemory {
  id                    String   @id @default(cuid())
  domain                String
  pattern_name          String
  trigger_metric        String
  trigger_condition     String
  trigger_threshold     Float?
  
  // Performance stats
  occurrences           Int
  hits                  Int
  accuracy              Float
  avg_return_5d         Float?
  avg_return_21d        Float?
  avg_return_63d        Float?
  avg_lead_days         Int?
  
  // Regime breakdown
  regime_stats          Json     // { "bull": { "occ": 27, "hits": 24, "acc": 0.89 }, ... }
  
  // Cross-domain
  correlations          Json     // { "CHINA": { "pattern": "cofco_accum", "lift": 0.18 }, ... }
  anti_correlations     Json     // Signals that reduce accuracy
  
  // Notable instances
  notable_instances     Json     // Array of significant historical occurrences
  
  last_updated          DateTime
  created_at            DateTime @default(now())
  
  @@unique([domain, pattern_name])
  @@index([domain])
  @@map("pattern_memory")
  @@schema("gold")
}

model HunterPrediction {
  id                    String   @id @default(cuid())
  as_of_date            DateTime // When prediction was made
  target_date           DateTime // When outcome should be measured
  domain                String
  pattern_name          String
  predicted_direction   Int      // -1, 0, 1
  predicted_magnitude   Float    // Expected % move
  confidence            Float
  
  // Outcome (filled in later during validation)
  actual_direction      Int?
  actual_magnitude      Float?
  outcome               String?  // HIT, MISS, PARTIAL
  validated_at          DateTime?
  
  created_at            DateTime @default(now())
  
  @@index([as_of_date])
  @@index([target_date, outcome])
  @@index([domain, pattern_name])
  @@map("hunter_predictions")
  @@schema("gold")
}

model IntelSynthesis {
  id                    String   @id @default(cuid())
  as_of_date            DateTime
  
  // The Story
  headline              String   // One-liner
  story                 String   @db.Text // Full narrative
  
  // Aggregated signal
  net_direction         Int      // -1, 0, 1
  net_confidence        Float
  
  // Components
  discovery_ids         String[] // References to HunterSignal records
  domain_signals        Json     // { "CRUSH": { "signal": 0.73, "conf": 0.87 }, ... }
  
  // Forecast
  forecast_5d           Json     // { "p10": 43.2, "p50": 44.1, "p90": 45.3 }
  forecast_21d          Json
  forecast_63d          Json
  
  // Action
  action_window         String?  // "Now through Feb 2"
  key_risks             String[] // What could invalidate this
  
  created_at            DateTime @default(now())
  
  @@index([as_of_date])
  @@map("intel_synthesis")
  @@schema("gold")
}
```

---

## 4.3 Inngest Job Structure

```
PHASE 1: DATA (Fix existing, add new)
═════════════════════════════════════
├── fred-daily.ts           [FIX]
├── yahoo-eod.ts            [FIX]
├── cftc-weekly.ts          [FIX]
├── federal-register.ts     [FIX]
├── nyfed-daily.ts          [FIX]
├── cbp-trade.ts            [FIX]
├── ice-releases.ts         [FIX]
├── farmdoc-rins.ts         [FIX]
├── aei-trade.ts            [FIX]
├── conab-news.ts           [FIX]
├── zl-price.ts             [FIX]
└── [NEW JOBS FROM BACKLOG] [BUILD]

PHASE 2: FEATURES
═════════════════
├── specialist-features.ts  → training.specialist_*_1d
└── core-features.ts        → training.core_features

PHASE 3: HUNTERS
════════════════
├── hunter-crush.ts         → gold.hunter_signals_1d
├── hunter-china.ts         → gold.hunter_signals_1d
├── hunter-fx.ts            → gold.hunter_signals_1d
├── hunter-fed.ts           → gold.hunter_signals_1d
├── hunter-tariff.ts        → gold.hunter_signals_1d
├── hunter-energy.ts        → gold.hunter_signals_1d
├── hunter-biofuel.ts       → gold.hunter_signals_1d
├── hunter-palm.ts          → gold.hunter_signals_1d
├── hunter-volatility.ts    → gold.hunter_signals_1d
├── hunter-substitutes.ts   → gold.hunter_signals_1d
└── hunter-trump.ts         → gold.hunter_signals_1d

PHASE 4: SYNTHESIS
══════════════════
└── intel-synthesis.ts      → gold.intel_synthesis

PHASE 5: TRAINING (Weekly)
══════════════════════════
├── validate-predictions.ts → gold.hunter_predictions (outcome fill)
├── learn-patterns.ts       → gold.pattern_memory (accuracy update)
├── train-specialists.ts    → model.oof_predictions
├── train-core.ts           → model.oof_predictions
└── train-meta.ts           → model.meta_ensemble

PHASE 6: INFERENCE (Daily)
══════════════════════════
└── forecast-daily.ts       → analytics.*
```

---

# PART 5: SUCCESS CRITERIA

## 5.1 Quantitative Targets

| METRIC | TARGET | MEASUREMENT |
|--------|--------|-------------|
| **Forecast Accuracy** | >88% | Directional accuracy on 21d horizon |
| **Information Lead** | 2-4 weeks | Days ahead of market pricing |
| **Pattern Hit Rate** | >70% | Validated predictions that were correct |
| **Confidence Calibration** | <5% error | Stated confidence vs actual accuracy |
| **Weekly Improvement** | Measurable | Accuracy should trend up over time |

## 5.2 Qualitative Targets

| METRIC | TARGET |
|--------|--------|
| **Story Quality** | Chris finds narratives valuable and unique |
| **Edge Perception** | Chris feels he knows things others don't |
| **Decision Support** | Forecasts actually influence procurement timing |
| **Trust** | Chris relies on the system for major decisions |

---

# PART 6: IMPLEMENTATION ROADMAP

## Phase 1: Foundation (Week 1-2)
- [ ] Fix existing 11 Inngest jobs
- [ ] Build jobs for backlog URLs
- [ ] Verify data flowing to all raw tables
- [ ] Add gold schema tables (hunter_signals, pattern_memory, etc.)

## Phase 2: Bootstrap (Week 3-4)
- [ ] Run historical pattern scan (2000-2026)
- [ ] Calculate pattern accuracies from history
- [ ] Build cross-domain correlation matrix
- [ ] Populate pattern_memory with 25 years of knowledge

## Phase 3: Hunters (Week 5-6)
- [ ] Build Hunter base class with Vercel AI SDK 6
- [ ] Implement CrushHunter as template
- [ ] Build remaining 10 Hunters
- [ ] Test discovery output quality

## Phase 4: Learning Loop (Week 7-8)
- [ ] Implement prediction storage
- [ ] Build validation job (compare predictions to outcomes)
- [ ] Build learning job (update pattern accuracies)
- [ ] Test weekly improvement cycle

## Phase 5: Synthesis & Training (Week 9-10)
- [ ] Build intel synthesis (AI narrative generation)
- [ ] Integrate Hunter signals into model training
- [ ] Retrain L0/L1 models on validated signals
- [ ] End-to-end test

## Phase 6: Dashboard & Delivery (Week 11-12)
- [ ] Build dashboard views for Chris
- [ ] Price + Confidence + Story display
- [ ] Alert system for critical discoveries
- [ ] Go-live

---

# PART 7: PRINCIPLES (NON-NEGOTIABLE)

## 7.1 Data Principles
1. **ALL DATA, ALL THE TIME** - Never reduce feature sets
2. **NO PLACEHOLDERS** - Every signal must be real, validated data
3. **POINT-IN-TIME** - No look-ahead bias, ever

## 7.2 Model Principles
1. **PROVEN PATTERNS ONLY** - Only validated signals become features
2. **CONFIDENCE = ACCURACY** - Stated confidence must match historical hit rate
3. **REGIME AWARENESS** - All patterns tagged and filtered by regime

## 7.3 Hunter Principles
1. **HUNT, DON'T REPORT** - Find the 22, not the 4
2. **LEARN EVERY WEEK** - Accuracy updates from real outcomes
3. **STAY SANE** - Guardrails prevent drift and overconfidence
4. **TRANSPARENCY** - Show evidence, acknowledge contradictions

## 7.4 System Principles
1. **NO HALF-ASSING** - If it's not done right, it's not done
2. **NO LYING** - Don't fake signals or inflate confidence
3. **NO CUTTING CORNERS** - The edge requires the full effort
4. **MEASURABLE IMPROVEMENT** - If we can't measure it, we can't trust it

---

# APPENDIX A: Key File Locations

```
/Volumes/Satechi Hub/ZINC-FUSION-V15/
├── docs/
│   ├── THE_22_ARCHITECTURE.md          # This document
│   └── VSCODE_INNGEST_RESPONSE.md      # VSCode direction
├── frontend/
│   └── src/inngest/                    # Inngest job functions
├── prisma/
│   └── schema.prisma                   # Database schema
├── src/fusion/
│   ├── pulse/                          # Old Pulse Engine (to be replaced)
│   ├── hunters/                        # New Hunter agents (to be built)
│   └── validation/
│       └── all_data_policy.py          # Data guardrails
├── scripts/
│   └── train_core_v15.py               # Model training script
└── models/
    ├── core_v15/                       # Core model artifacts
    ├── core_chronos2/                  # Experimental core
    └── specialists/                    # Specialist model artifacts
```

---

# APPENDIX B: Glossary

| TERM | DEFINITION |
|------|------------|
| **The 22** | Information advantage - knowing what others don't |
| **Hunter** | AI agent that finds the 22 through active investigation |
| **Discovery** | A pattern or signal that predicts price movement |
| **Pattern Memory** | Database of historical patterns with validated accuracy |
| **Regime** | Market state (bull, bear, choppy, crisis) |
| **Hit** | Prediction where direction was correct |
| **Confidence** | Probability estimate calibrated to historical accuracy |
| **Bootstrap** | One-time process to seed Hunter with 25 years of knowledge |
| **Sanity Check** | Guardrails that prevent Hunter drift |
| **Synthesis** | AI-generated narrative combining multiple discoveries |

---

**Document Version:** 1.0
**Created:** January 12, 2026
**Author:** Claude (with Kirk)
**Status:** LOCKED - Reference Architecture

---

*"The edge isn't in the model. The edge is in KNOWING THINGS BEFORE OTHERS."*
