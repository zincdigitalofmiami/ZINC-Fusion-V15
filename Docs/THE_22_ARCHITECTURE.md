# ZINC-FUSION-V15: THE 22 ARCHITECTURE
## From Data to Discovery to Decision

---

## CURRENT STATE (January 12, 2026)

### DATA INVENTORY

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
| **TRAINING** | specialist_crush_1d | 23,487 | ✅ BUILT |
| | specialist_china_1d | 27,492 | ✅ BUILT |
| | specialist_fx_1d | 80,165 | ✅ BUILT |
| | specialist_fed_1d | 48,174 | ✅ BUILT |
| | specialist_tariff_1d | 42,414 | ✅ BUILT |
| | specialist_energy_1d | 45,380 | ✅ BUILT |
| | specialist_biofuel_1d | 42,055 | ✅ BUILT |
| | specialist_palm_1d | 24,037 | ✅ BUILT |
| | specialist_volatility_1d | 35,088 | ✅ BUILT |
| | specialist_substitutes_1d | 42,706 | ✅ BUILT |
| | specialist_trump_effect_1d | 2,273 | ⚠️ NEW |
| | core_features | 6,381 | ✅ BUILT |
| **MODEL** | oof_predictions | 0 | ❌ EMPTY |
| | model_registry | 18 | ⚠️ PARTIAL |
| **GOLD** | intel_drops | 0 | ❌ EMPTY |
| **ANALYTICS** | zl_live | 1 | ❌ EMPTY |

### TOTAL RAW DATA: ~6.3 MILLION ROWS
### STATUS: Data is DEEP. Models are NOT TRAINED. Intelligence is NOT FLOWING.

---

## THE 22 ARCHITECTURE

### The Difference

```
2+2=4 (What we have now):
────────────────────────
RAW DATA → FEATURES → MODEL → PREDICTION
"Here's the data" → "Here's the forecast"

2+2=22 (What we're building):
──────────────────────────────
RAW DATA → HUNTERS → DISCOVERIES → SYNTHESIS → FORECAST + STORY
"Here's the data" → "Here's what it MEANS that nobody else sees"
```

---

## SYSTEM ARCHITECTURE

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           INNGEST ORCHESTRATION                             │
│  Schedule: Daily 5AM CT (data), 6AM CT (features), 7AM CT (hunt)            │
└───────────────────────────────────┬─────────────────────────────────────────┘
                                    │
┌───────────────────────────────────▼─────────────────────────────────────────┐
│                              RAW LAYER                                      │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐          │
│  │ FRED     │ │ Yahoo    │ │ CFTC     │ │ USDA     │ │ Weather  │  ...     │
│  │ 506K     │ │ 442K     │ │ 18K      │ │ 22K      │ │ 215K     │          │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘          │
│                            6.3M+ ROWS TOTAL                                 │
└───────────────────────────────────┬─────────────────────────────────────────┘
                                    │
┌───────────────────────────────────▼─────────────────────────────────────────┐
│                           TRAINING LAYER                                    │
│  Feature Engineering: Domain-specific transformations                       │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐   │
│  │ CRUSH   │ │ CHINA   │ │ FX      │ │ FED     │ │ TARIFF  │ │ ENERGY  │   │
│  │ 23K     │ │ 27K     │ │ 80K     │ │ 48K     │ │ 42K     │ │ 45K     │   │
│  └─────────┘ └─────────┘ └─────────┘ └─────────┘ └─────────┘ └─────────┘   │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐               │
│  │ BIOFUEL │ │ PALM    │ │ VOL     │ │ SUBS    │ │ TRUMP   │               │
│  │ 42K     │ │ 24K     │ │ 35K     │ │ 43K     │ │ 2K      │               │
│  └─────────┘ └─────────┘ └─────────┘ └─────────┘ └─────────┘               │
└───────────────────────────────────┬─────────────────────────────────────────┘
                                    │
                    ┌───────────────┴───────────────┐
                    │                               │
                    ▼                               ▼
┌───────────────────────────────────┐ ┌────────────────────────────────────────┐
│         HUNTER LAYER (NEW)        │ │           MODEL LAYER                  │
│  ┌─────────────────────────────┐  │ │  ┌──────────────────────────────────┐  │
│  │     THE 22 DISCOVERY        │  │ │  │         L0 SPECIALISTS           │  │
│  │                             │  │ │  │  11 TabularPredictors             │  │
│  │  • Anomaly Detection        │  │ │  │  Quantile regression              │  │
│  │  • Pattern Matching         │  │ │  │  OOF predictions                  │  │
│  │  • Lead-Lag Correlation     │  │ │  └──────────────┬───────────────────┘  │
│  │  • Regime Detection         │  │ │                 │                      │
│  │  • Convergence Analysis     │  │ │  ┌──────────────▼───────────────────┐  │
│  │                             │  │ │  │         L0 CORE                  │  │
│  │  OUTPUT: Discoveries        │  │ │  │  TimeSeriesPredictor              │  │
│  │  "What others don't see"    │  │ │  │  Chronos-2 (strategic)            │  │
│  └──────────────┬──────────────┘  │ │  │  Chronos-Bolt (tactical)          │  │
│                 │                 │ │  └──────────────┬───────────────────┘  │
└─────────────────┼─────────────────┘ │                 │                      │
                  │                   │  ┌──────────────▼───────────────────┐  │
                  │                   │  │         L1 META-LEARNER          │  │
                  │                   │  │  Fuses OOF from all L0            │  │
                  │                   │  │  36 input columns                 │  │
                  │                   │  └──────────────┬───────────────────┘  │
                  │                   │                 │                      │
                  │                   │  ┌──────────────▼───────────────────┐  │
                  │                   │  │         L2 ENSEMBLE              │  │
                  │                   │  │  Final weighted combination       │  │
                  │                   │  └──────────────┬───────────────────┘  │
                  │                   │                 │                      │
                  │                   │  ┌──────────────▼───────────────────┐  │
                  │                   │  │         L3 MONTE CARLO           │  │
                  │                   │  │  10,000 simulations               │  │
                  │                   │  │  P10/P50/P90/P95 outputs          │  │
                  │                   │  └──────────────┬───────────────────┘  │
                  │                   └─────────────────┼──────────────────────┘
                  │                                     │
                  └──────────────────┬──────────────────┘
                                     │
┌────────────────────────────────────▼────────────────────────────────────────┐
│                           GOLD LAYER                                        │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                         INTEL DROPS                                   │  │
│  │                                                                       │  │
│  │  DISCOVERIES (from Hunters):                                          │  │
│  │  • "Crush margin at 3-year low - capacity cuts 73% likely in 4 weeks" │  │
│  │  • "COFCO accumulation pattern matches Q2 2021 - demand floor rising" │  │
│  │  • "Brazil pod-fill stress: 89% similar to 2019 pre-rally"            │  │
│  │                                                                       │  │
│  │  FORECASTS (from Models):                                             │  │
│  │  • 5d:  44.2 → 44.8 (+1.4%)  Confidence: 72%                          │  │
│  │  • 21d: 44.2 → 46.1 (+4.3%)  Confidence: 68%                          │  │
│  │  • 63d: 44.2 → 48.5 (+9.7%)  Confidence: 61%                          │  │
│  │                                                                       │  │
│  │  THE STORY (AI Synthesis):                                            │  │
│  │  "Three converging forces create a 3-week information advantage:      │  │
│  │   Supply squeeze from margin compression + China accumulation +       │  │
│  │   Brazil weather stress. Market hasn't priced this in yet."           │  │
│  │                                                                       │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          ANALYTICS / DASHBOARD                              │
│                                                                             │
│  Chris sees:                                                                │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  PRICE: 44.2 → 48.5 by March 15                                     │   │
│  │  CONFIDENCE: 88%                                                     │   │
│  │                                                                      │   │
│  │  THE STORY NOBODY ELSE HAS:                                          │   │
│  │  ─────────────────────────────────────────────────────               │   │
│  │  "Supply squeeze imminent. You have a 3-week window before           │   │
│  │   the market catches up. Crush margins hit breakeven last            │   │
│  │   Tuesday - historically this precedes capacity cuts by 4            │   │
│  │   weeks. Meanwhile, COFCO is quietly accumulating. Brazil            │   │
│  │   pod-fill stress matches 2019 pattern that preceded 12% rally."     │   │
│  │                                                                      │   │
│  │  ACTION WINDOW: Now through Feb 2                                    │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## INNGEST JOB STRUCTURE

### CURRENT JOBS (11 Functions)
```
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
```

### NEW JOBS NEEDED

```
PHASE 1: FEATURE ENGINEERING (Build the training data)
─────────────────────────────────────────────────────
├── specialist-features.ts    → training.specialist_*_1d
│   Schedule: Daily 6AM CT (after raw data)
│   Purpose: Transform raw → specialist features
│
├── core-features.ts          → training.core_features  
│   Schedule: Daily 6:30AM CT
│   Purpose: Build wide feature matrix for Core model

PHASE 2: HUNTING (Find the 22)
──────────────────────────────
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
│   Schedule: Daily 7AM CT (after features)
│   Purpose: Run anomaly detection, pattern matching, correlation discovery

PHASE 3: SYNTHESIS (Build the story)
────────────────────────────────────
├── intel-synthesis.ts        → gold.intel_drops
│   Schedule: Daily 7:30AM CT (after hunters)
│   Purpose: AI synthesizes discoveries into narrative

PHASE 4: MODEL TRAINING (Weekly)
────────────────────────────────
├── train-specialists.ts      → model.oof_predictions
│   Schedule: Saturday 6AM CT
│   Purpose: Retrain L0 specialists

├── train-core.ts             → model.oof_predictions
│   Schedule: Saturday 8AM CT  
│   Purpose: Retrain Core TimeSeriesPredictor

├── train-meta.ts             → model.meta_ensemble
│   Schedule: Saturday 10AM CT
│   Purpose: Retrain L1 meta-learner

PHASE 5: INFERENCE (Daily)
──────────────────────────
├── forecast-daily.ts         → analytics.*
│   Schedule: Daily 8AM CT (market open prep)
│   Purpose: Run inference on latest data
```

---

## PRIORITY SEQUENCE

### WEEK 1: Foundation
1. ✅ Verify raw data ingestion is working (11 Inngest jobs)
2. 🔲 Build specialist-features.ts job
3. 🔲 Build core-features.ts job
4. 🔲 Verify training.* tables are populating correctly

### WEEK 2: Hunting
5. 🔲 Build Hunter base class with discovery methods
6. 🔲 Build CrushHunter (first hunter)
7. 🔲 Test discovery output format
8. 🔲 Create gold.discoveries table

### WEEK 3: Scale
9. 🔲 Build remaining 10 hunters
10. 🔲 Build intel-synthesis.ts (AI narrative)
11. 🔲 Build forecast-daily.ts (inference)

### WEEK 4: Training
12. 🔲 Build train-specialists.ts
13. 🔲 Build train-core.ts  
14. 🔲 Build train-meta.ts
15. 🔲 End-to-end test

---

## THE 22 DISCOVERY TYPES

Each Hunter looks for these patterns:

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

## NEXT IMMEDIATE STEP

**VSCode needs now:** A working Inngest job template that can be duplicated for each Hunter.

Should I create:
1. The Hunter base class (Python) - for the actual discovery logic
2. The hunter-*.ts Inngest jobs (TypeScript) - for scheduling
3. The gold.discoveries schema addition (Prisma)

All three are needed. Which first?
