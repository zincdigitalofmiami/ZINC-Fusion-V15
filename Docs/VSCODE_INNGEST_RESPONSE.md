# VSCODE INNGEST RESPONSE - FULL CONTEXT
## From: Claude (Kirk's session)
## Date: January 12, 2026

---

## ⚠️ IMMEDIATE PRIORITY - DO THIS FIRST

### Priority 1: FIX EXISTING INNGEST JOBS
The 11 existing jobs need to be fixed and set LIVE:
```
├── fred-daily.ts
├── yahoo-eod.ts
├── cftc-weekly.ts
├── federal-register.ts
├── nyfed-daily.ts
├── cbp-trade.ts
├── ice-releases.ts
├── farmdoc-rins.ts
├── aei-trade.ts
├── conab-news.ts
├── zl-price.ts
```

**Task:** Audit each one. Identify what's broken. Fix it. Get them LIVE.

### Priority 2: NEW INNGEST JOBS FROM YESTERDAY'S URLs
Kirk built fresh URLs yesterday (Jan 11). These need Inngest jobs created.

**Task:** Find yesterday's URL backlog and build the jobs.

### Priority 3: THEN Architecture Expansion
Once data is flowing reliably, we expand to Hunters and the full architecture below.

---

## SEQUENCE
```
PHASE 1 (NOW):     Fix Inngest → Data flowing reliably
PHASE 2 (NEXT):    Build Hunters → Find the 22
PHASE 3 (THEN):    Train Models → Generate forecasts
PHASE 4 (FINALLY): Dashboard → Chris sees intelligence
```

**We can't hunt if the data isn't flowing.**

---

---

# FULL ARCHITECTURE CONTEXT (For Understanding)

## THE BIG PICTURE: What We're Building

This isn't just a forecasting system. It's an **information advantage machine**.

### The 22 Concept

```
2+2=4 (What most systems do):
────────────────────────────────
RAW DATA → FEATURES → MODEL → PREDICTION
"Here's the data" → "Here's the forecast"

2+2=22 (What we're building):
──────────────────────────────────
RAW DATA → HUNTERS → DISCOVERIES → SYNTHESIS → FORECAST + STORY
"Here's the data" → "Here's what it MEANS that nobody else sees"
```

**The edge isn't in the model. The edge is in KNOWING THINGS BEFORE OTHERS.**

---

## CURRENT DATA INVENTORY

| LAYER | TABLE | ROWS | STATUS |
|-------|-------|------|--------|
| **RAW** | market_futures_1d | 432,152 | ✅ DEEP |
| | market_futures_1h | 4,967,276 | ✅ DEEP |
| | fred_observations_1d | 505,800 | ✅ DEEP |
| | weather_noaa_1d | 215,320 | ✅ DEEP |
| | fx_spot_1d | 59,105 | ✅ DEEP |
| | cftc_cot_1w | 18,372 | ✅ DEEP |
| | usda_export_sales_1w | 9,712 | ✅ GOOD |
| | usda_wasde_1m | 12,548 | ✅ GOOD |
| | epa_rin_prices_1d | 208 | ⚠️ THIN |
| | news_articles_1d | 2,878 | ⚠️ THIN |
| | yahoo_equity_1d | 9,534 | ✅ GOOD |
| | options_futures_1d | 28,648 | ✅ GOOD |
| **TRAINING** | specialist_*_1d | ~450K total | ✅ BUILT |
| | core_features | 6,381 | ✅ BUILT |
| **MODEL** | oof_predictions | 0 | ❌ EMPTY |
| | model_registry | 18 | ⚠️ PARTIAL |
| **GOLD** | intel_drops | 0 | ❌ EMPTY |

### TOTAL RAW DATA: ~6.3 MILLION ROWS
### STATUS: Data is DEEP. Models are NOT TRAINED. Intelligence is NOT FLOWING.

---

## ANSWERS TO YOUR PLANNING QUESTIONS

### 1. Schedule Coordination Strategy
**Answer: Cascade after data ingestion, NOT separate weekend windows**

```
WEEKDAY SCHEDULE (Monday-Friday):
─────────────────────────────────
5:00 AM CT  │ Data Ingestion (existing 11 jobs + new ones)
5:45 AM CT  │ Feature Engineering (specialist-features, core-features)
6:30 AM CT  │ Hunters Run (all 11 domain hunters)
7:00 AM CT  │ Intel Synthesis (AI narrative generation)
7:30 AM CT  │ Daily Forecast Inference
8:00 AM CT  │ Dashboard Ready for Chris

WEEKEND SCHEDULE (Saturday only):
─────────────────────────────────
6:00 AM CT  │ L0 Specialist Training (all 11)
8:00 AM CT  │ L0 Core Training (Chronos-2/Bolt)
10:00 AM CT │ L1 Meta-Learner Training
12:00 PM CT │ Validation & Registry Update
```

**Rationale:** Chris needs fresh intel every morning. Weekend training ensures models stay current without blocking daily operations.

---

### 2. Error Handling and Retry Policies
**Answer: Exponential backoff WITH circuit breaker**

```typescript
// Recommended pattern for all Inngest functions
const retryConfig = {
  retries: 3,
  backoff: {
    type: "exponential",
    base: "30s",
    factor: 2,
    max: "10m"
  }
};

// Circuit breaker for external APIs
const circuitBreaker = {
  failureThreshold: 5,      // 5 failures triggers open
  resetTimeout: "15m",      // Try again after 15 min
  halfOpenRequests: 2       // Test with 2 requests before closing
};
```

**Critical:** FRED, Yahoo, and CFTC are lifeline sources. If they fail:
1. Log to `ops.ingest_run` with status='FAILED'
2. Alert (Slack/email TBD)
3. Continue with stale data rather than crash pipeline

---

### 3. Resource Management Approach
**Answer: Vercel serverless for ingestion/features, SEPARATE compute for training**

```
VERCEL SERVERLESS (10s-60s jobs):
├── All data ingestion jobs ✓
├── Feature engineering jobs
├── Hunter jobs (Python via API call)
├── Intel synthesis
├── Daily inference

SEPARATE COMPUTE (Mac M4 Pro local, or Modal/RunPod):
├── L0 Specialist Training (30-60 min each)
├── L0 Core Training (1-2 hours)
├── L1 Meta Training (30 min)
```

**Implementation:** Inngest job triggers webhook to local Mac or Modal endpoint for heavy training. Vercel just orchestrates.

---

## FUTURE SCHEMA ADDITIONS (After Data is Flowing)

When ready for Phase 2, add to `prisma/schema.prisma`:

```prisma
// ============================================
// GOLD LAYER - Intelligence Output
// ============================================

model Discovery {
  id              String   @id @default(cuid())
  domain          String   // CRUSH, CHINA, FX, FED, TARIFF, ENERGY, BIOFUEL, PALM, VOLATILITY, SUBSTITUTES, TRUMP_EFFECT
  discovery_type  String   // ANOMALY, PATTERN_MATCH, LEADING_INDICATOR, CONVERGENCE, REGIME_SHIFT, DIVERGENCE, THRESHOLD_BREACH
  severity        String   // LOW, MEDIUM, HIGH, CRITICAL
  description     String   @db.Text
  signal_strength Float    // -1.0 to +1.0
  confidence      Float    // 0.0 to 1.0
  lead_days       Int      // How many days ahead this predicts
  historical_accuracy Float // Win rate when this pattern appeared before
  sample_size     Int      // Number of historical occurrences
  evidence        Json     // Raw supporting data
  supporting_metrics String[] // List of metrics that support this
  last_occurrence DateTime? // When this pattern last appeared
  last_outcome    String?   // What happened after last occurrence
  as_of_date      DateTime  // Point-in-time date
  created_at      DateTime  @default(now())
  
  @@index([domain, as_of_date])
  @@index([severity, created_at])
  @@map("discoveries")
  @@schema("gold")
}

model IntelSynthesis {
  id              String   @id @default(cuid())
  as_of_date      DateTime
  story           String   @db.Text  // The narrative nobody else has
  net_signal      Float    // -1.0 to +1.0 overall direction
  net_confidence  Float    // 0.0 to 1.0
  discovery_ids   String[] // References to Discovery records
  horizons        Json     // { "5d": {...}, "21d": {...}, "63d": {...} }
  action_window   String?  // "Now through Feb 2"
  created_at      DateTime @default(now())
  
  @@index([as_of_date])
  @@map("intel_synthesis")
  @@schema("gold")
}
```

---

## FUTURE INNGEST JOB STRUCTURE (After Data is Flowing)

```
PHASE 1 JOBS (NOW - Fix these):
───────────────────────────────
├── fred-daily.ts         → raw.fred_observations_1d
├── yahoo-eod.ts          → raw.market_futures_1d, raw.yahoo_equity_1d
├── cftc-weekly.ts        → raw.cftc_cot_1w
├── federal-register.ts   → raw.news_articles_1d (policy)
├── nyfed-daily.ts        → raw.fred_observations_1d (rates)
├── cbp-trade.ts          → raw data (trade flows)
├── ice-releases.ts       → raw data (exchange)
├── farmdoc-rins.ts       → raw.epa_rin_prices_1d
├── aei-trade.ts          → raw data (trade)
├── conab-news.ts         → raw data (Brazil)
├── zl-price.ts           → analytics.zl_live
└── [NEW JOBS FROM YESTERDAY'S URLs]

PHASE 2 JOBS (NEXT - After data flows):
───────────────────────────────────────
├── specialist-features.ts    → training.specialist_*_1d
├── core-features.ts          → training.core_features  
├── hunter-crush.ts           → gold.discoveries
├── hunter-china.ts           → gold.discoveries
├── hunter-fx.ts              → gold.discoveries
├── hunter-fed.ts             → gold.discoveries
├── hunter-tariff.ts          → gold.discoveries
├── hunter-energy.ts          → gold.discoveries
├── hunter-biofuel.ts         → gold.discoveries
├── hunter-palm.ts            → gold.discoveries
├── hunter-volatility.ts      → gold.discoveries
├── hunter-substitutes.ts     → gold.discoveries
├── hunter-trump.ts           → gold.discoveries
├── intel-synthesis.ts        → gold.intel_synthesis

PHASE 3 JOBS (THEN - Weekly training):
──────────────────────────────────────
├── train-specialists.ts      → model.oof_predictions
├── train-core.ts             → model.oof_predictions
├── train-meta.ts             → model.meta_ensemble
├── forecast-daily.ts         → analytics.*
```

---

## THE 22 DISCOVERY TYPES (Reference for Hunter Design)

| TYPE | WHAT IT FINDS | EXAMPLE |
|------|---------------|---------|
| **ANOMALY** | Current value far from historical norm | "Crush margin at 2nd percentile (z=-2.8σ)" |
| **PATTERN_MATCH** | Current pattern matches historical precursor | "Pattern 87% similar to Q3 2019 pre-rally" |
| **LEADING_INDICATOR** | Something that leads price by N days | "China port stocks lead ZL by 12 days (r=0.68)" |
| **CONVERGENCE** | Multiple signals pointing same direction | "3 of 4 crush indicators bearish" |
| **REGIME_SHIFT** | Market structure is changing | "Transitioning from contango to backwardation" |
| **DIVERGENCE** | Something that should correlate isn't | "Palm premium diverging from 5-year pattern" |
| **THRESHOLD_BREACH** | Critical level crossed | "Crush margin below breakeven ($0.40)" |

---

## KEY METRICS FOR SUCCESS

| METRIC | TARGET | MEASUREMENT |
|--------|--------|-------------|
| Forecast Accuracy | >88% | Directional accuracy over 21d horizon |
| Information Lead | 2-4 weeks | How far ahead we see moves |
| Discovery Hit Rate | >60% | Discoveries that precede price moves |
| Story Quality | Qualitative | Chris's feedback on narratives |

---

## SUMMARY

**NOW:** Fix existing 11 Inngest jobs + build jobs for yesterday's URLs. Get data flowing.

**NEXT:** Build Hunters that find the 22 (anomalies, patterns, leading indicators).

**THEN:** Train models, generate forecasts, synthesize narratives.

**GOAL:** Chris gets a price forecast + a story nobody else has, every morning by 8 AM CT.

---

Ready to proceed. Focus on getting the data pipeline LIVE first.
