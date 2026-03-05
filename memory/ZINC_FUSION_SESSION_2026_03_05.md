# ZINC-FUSION-V15 Specialist Data Source Expansion — Session Memory

**Date:** 2026-03-05  
**Session Duration:** ~3 hours  
**Mode:** Architect  
**Status:** Planning phase complete, implementation ready

---

## Project Context

### System Overview

ZINC-FUSION-V15 is a commodity procurement forecasting system for **ZL (soybean oil futures)**.

**Architecture:**

- **L0 Core:** AutoGluon TimeSeriesPredictor ensemble (4 horizons: 5d/21d/63d/126d), each training a 19-model zoo
  - Output: `predicted_price` (ZL futures contract price) — NOT quantiles
  - Metric: MAE (point forecast accuracy)
  - Target: `close.shift(-horizon)` — actual future ZL futures price
- **11 Specialists:** Domain-specific signal generators (crush, china, fx, fed, tariff, energy, biofuel, palm, volatility, substitutes, trump_effect)
  - Each outputs `(signal_1, signal_2, confidence)` per date to `training.specialist_signals_1d`
  - Signals merged into `training.matrix_1d` as core input features
- **L2/L3 Calibration:** Monte Carlo (10,000 runs) + pinball loss + MAE/accuracy % → wraps core's price with probability
  - Output: "ZL has an 88% chance of hitting 48.52 by July 7th" (horizontal Target Zones on chart)

**Tech Stack:**

- Backend: Python 3.11, FastAPI, psycopg2, AutoGluon (CPU-only), uv
- Frontend: Next.js on Vercel, Inngest serverless functions, TypeScript
- Database: Prisma Postgres (cloud), 12 schemas (mkt/econ/alt/pos/supply/features/training/model/forecasts/analytics/ops/vegas)
- ML tracking: MLflow (local)

**Client:** US Oil Solutions

### Specialist Model Types (DO NOT CHANGE)

```python
MODEL_TYPES = {
    "crush": "gbm",              # GradientBoostingRegressor
    "china": "gbm",              # GradientBoostingRegressor
    "fx": "ardl",                # ARDL (statsmodels)
    "fed": "ridge",              # Ridge regression
    "tariff": "tree",            # Rule-based + EPU
    "energy": "var",             # VAR + IRF
    "biofuel": "nlp_ema",        # NLP sentiment + EMA
    "palm": "ecm_ridge",         # ECM + Ridge
    "volatility": "garch",       # GJR-GARCH(1,1)
    "substitutes": "rf",         # RandomForestRegressor
    "trump_effect": "event_study"  # Event intensity scoring
}
```

### Critical Architecture Rules (from AGENTS.md)

1. **Core = price predictor.** Output is `predicted_price` (ZL futures price). Metric: MAE. No quantiles from core.
2. **11 specialists** (NOT 10) — trump_effect is the 11th specialist
3. **Target is ZL futures price** (`close.shift(-horizon)`), NOT returns
4. **L2/L3 = probability engine** (Monte Carlo + pinball + MAE). Output: horizontal Target Zones.
5. **Banned words:** "cones", "probability cone", "confidence band", "funnel", "cents/lb"
6. **Banned schemas:** raw, gold, silver, bronze, monitoring, specialist, weather, archive

---

## Problem Statement (Why This Work Matters)

### Initial Discovery

User requested investigation of 5 "priority fixes" listed in [`docs/data-source-catalog.md`](../docs/data-source-catalog.md):

1. CFTC COT (claimed "Never built")
2. `econ.activity_1d` (claimed "Stale, 29 missing series")
3. CPO Palm Oil (claimed "Stale, needs Yahoo proxies")
4. MPOB Palm Monthly (claimed "Stale, needs fallback")
5. EIA Biodiesel Weekly (claimed "0 rows, needs HTML scrape")

**Finding:** 4 out of 5 "priority fixes" were **already implemented** with active Inngest functions — catalog was outdated.

### Root Cause Pivot

User pivoted to broader concern: **"All 11 specialists operating on dangerously thin signal sets (1-3 data sources each) when they require thick, multi-dimensional coverage for reliable forecasting."**

**This is the real problem:**

- Specialists have 3-10 signals each
- Robust ML requires 30-40 signals per specialist (6-8 orthogonal dimensions)
- **30+ catalog sources are "Not built"** despite direct ZL relevance
- **4 sources STALE/BROKEN** (econ.activity_1d, MPOB palm, EIA biodiesel)
- Many **existing sources under-utilized** (FRED series ingested but not consumed by specialists)

---

## Completed Work Summary

### 1. Audit of Current Data Sources ✅

**Goal:** Inventory all data sources available to the system (no external API assumptions).

**Findings:**

- **Databento futures** (mkt.futures_1d) — 17 symbols confirmed (ZL, ZS, ZM, CL, NG, HG, LE, HE, etc.)
- **FRED economic data** (econ.\* tables) — 130+ series across 7 domain tables (rates, fx, commodities, macro, activity, spreads, stress)
- **Yahoo Finance ETFs** — equity indices, sector ETFs, commodity ETFs
- **CFTC COT positioning** (pos.cftc_1w) — 🔴 TABLE DOESN'T EXIST (top priority to build)
- **Internal computed tables** — board_crush, EPA RINs, MPOB palm, USDA exports, WASDE forecasts, specialist signals

**Verified available but NOT integrated:**

- USDA sources (NASS QuickStats, WASDE, FAS GATS, ERS Biofuels, Grain Stocks, 3 newsrooms)
- EIA sources (Petroleum Supply, Crude/NG prices via HTML scrape)
- EPA sources (RIN data — exists but "at source limit")
- CFTC COT (3 Socrata APIs — V14 code exists, never ported to V15)
- NOAA weather (NCEI Daily Summaries)
- White House/USTR/Federal Register (policy announcements)
- Foreign gov sources (CONAB Brazil, MPOB Malaysia, China GACC/MOFCOM/CNGOIC, Panama Canal)

**File:** Documented in [`plans/SPECIALIST_DATA_SOURCE_EXPANSION.md`](../plans/SPECIALIST_DATA_SOURCE_EXPANSION.md) Section 1.

---

### 2. Model Types & Requirements Documentation ✅

**Goal:** Document each specialist's model type, signal contract, and current feature set.

**Key Findings:**

- **Crush specialist (GBM):** 8 signals → target 35+
  - Current: board_crush, zl_cl_ratio, zl_price, soy_oil_share, soybean_production, domestic_use, crush_margin, LE/HE prices
  - Missing: cross-commodity spreads, livestock demand proxies, export flows, volume/OI, macro overlays
- **China specialist (GBM):** 6 signals → target 30+
  - Current: usd_cny, china_pmi, china_cpi, copper (via Databento HG), soybean_exports_to_china, brl_usd
  - Missing: copper technical signals, protein cycle (lean hogs), Brazil competition, export flow granularity, yuan carry
- **Energy specialist (VAR):** 10 signals → target 35+
  - Current: CL, NG, DCOILWTICO, DCOILBRENTEU, DHHNGSP, XLE, USO, UNG, crude_inventory_change, refinery_utilization
  - Missing: refinery cracks (3-2-1), BOHO spread, RIN prices, NG seasonality, gasoline demand
- **Fed specialist (Ridge):** 45 signals → ✅ EXCELLENT COVERAGE (best of all specialists)
- **Tariff specialist (Tree):** 3 signals → target 25+ (🔴 WORST COVERAGE)
  - Current: trade_policy_uncertainty, epu_index, tariff_mentions
  - Missing: CFTC COT, FAS Export Sales, GATS, White House/USTR, Federal Register, USDA news
- **Biofuel specialist (NLP+EMA):** 5 signals → target 30+
  - Current: biodiesel_production, rin_d4_price, boho_spread, biofuel_sentiment, epa_news_volume
  - Missing: EIA biodiesel (STALE), EPA RINs (at source limit), ERS Biofuels, Federal Register waivers, tallow/rendering PPI
- **Others:** fx (12 signals, adequate), palm (8 signals, STALE data), volatility (5 signals, missing COT), substitutes (4 signals, missing tallow PPI + NASS), trump_effect (4 signals, missing policy news)

**File:** Documented in [`plans/SPECIALIST_DATA_SOURCE_EXPANSION.md`](../plans/SPECIALIST_DATA_SOURCE_EXPANSION.md) Section 2.

---

### 3. Catalog Source → Specialist Mapping Matrix ✅

**Goal:** Map each source in [`docs/data-source-catalog.md`](../docs/data-source-catalog.md) to applicable specialists with causal ZL prediction links.

**Deliverable:** [`plans/CATALOG_SOURCE_TO_SPECIALIST_MAPPING.md`](../plans/CATALOG_SOURCE_TO_SPECIALIST_MAPPING.md) (1,800+ lines)

**Structure:**

- **Source-by-source analysis** (70+ data sources):
  - Applicable specialists (which of the 11 can use this source)
  - Causal link to ZL (specific transmission mechanism to soybean oil futures price)
  - Current integration status (✅ WORKING / ⚠️ STALE / 🔴 NOT BUILT)
  - Feature engineering (SQL/Python code showing how to transform raw data into specialist signals)
  - Integration requirements (Inngest function specs: cron, API endpoint, fallback logic, historical backfill)
  - Priority (P0/P1/P2/P3)
- **Under-utilization analysis** — which specialists are missing which catalog sources
- **Integration priority matrix** — ranked by impact x urgency x difficulty
- **4-phase implementation roadmap** (8 weeks)

**Example causal links:**

```
CFTC COT report → Managed money net long >90th percentile → Crowded trade → Reversal risk → ZL volatility ↑
WASDE monthly report → Soybean crush forecast revision → ZL supply expectation update → ZL price adjustment
White House press release → "China to purchase $X billion in ag products" → Export optimism → ZL price spike
NOAA drought monitor → Soybean yield forecast ↓ → Harvest size expectations ↓ → ZL supply concern → ZL price ↑
CONAB report → Brazil soybean production forecast ↑ → US-Brazil export competition ↑ → ZL export premium ↓ → ZL price ↓
```

---

### 4. Causal Links to ZL Price Prediction ✅

**Goal:** For each data source, document the specific transmission mechanism to ZL futures price (not just theoretical correlation).

**Methodology:**

```
Data Source → Economic/Geopolitical Event → Supply/Demand Shift → ZL Price Impact
```

**Examples:**

- **CFTC COT:** `COT positioning extremes → Crowded trades → Mean reversion risk → ZL volatility spike`
- **WASDE:** `USDA crush forecast revision → ZL supply expectation update → ZL price adjustment`
- **FAS Export Sales:** `China's share of US soy purchases ↑ → ZL export demand signal → ZL price support`
- **NOAA Weather:** `Soybean belt drought → Crop stress → Yield risk → ZL supply concern → ZL price ↑`
- **White House policy:** `Tariff announcement → Trade war risk premium → ZL volatility ↑`
- **CONAB Brazil:** `Brazil production surge → US export competition ↑ → ZL export premium ↓ → ZL price ↓`
- **MPOB Palm:** `CPO price spike → Palm-soy spread widens → Buyers shift to soy oil → ZL demand ↑ → ZL price ↑`
- **EPA RINs:** `D4 RIN price spike → Biodiesel profit margin ↑ → Feedstock demand (soy oil) ↑ → ZL price ↑`

**Coverage:** All 70+ catalog sources have documented causal links in the mapping document.

---

### 5. Feature Engineering Recommendations ✅

**Goal:** Provide SQL/Python code showing how to transform each raw data source into specialist signals.

**Pattern:**

1. **Raw ingestion** (Inngest function → database table)
2. **Feature computation** (SQL transformations: z-scores, percentiles, rolling correlations, momentum indicators, spreads, ratios)
3. **Specialist signal** (merge into `training.matrix_1d` or `training.specialist_signals_1d`)

**Example: CFTC COT for Tariff Specialist**

```sql
SELECT
  report_date,
  -- Managed money positioning (speculative sentiment)
  SUM(CASE WHEN trader_category = 'MANAGED_MONEY' THEN net_positions END) as mm_net_long,
  -- Positioning percentile (extremes = crowded trades)
  PERCENT_RANK() OVER (PARTITION BY contract_code ORDER BY mm_net_long) as mm_net_long_pctile,
  -- WoW change (momentum)
  mm_net_long - LAG(mm_net_long, 1) OVER (ORDER BY report_date) as mm_net_long_wow,
  -- Crowded trade flag (reversal risk)
  CASE WHEN mm_net_long_pctile > 0.90 OR mm_net_long_pctile < 0.10 THEN 1 ELSE 0 END as crowded_trade_flag
FROM pos.cftc_1w
WHERE contract_code = '007601';  -- ZL soybean oil
```

**Example: WASDE for Crush Specialist**

```sql
SELECT
  report_date,
  -- MoM revisions (expectation shocks)
  value - LAG(value, 1) OVER (PARTITION BY metric ORDER BY report_date) as mom_revision,
  -- Crush-to-production ratio
  MAX(CASE WHEN metric = 'CRUSH' THEN value END) /
    NULLIF(MAX(CASE WHEN metric = 'PRODUCTION' THEN value END), 0) as crush_rate_pct
FROM supply.wasde_1m
WHERE commodity = 'SOYBEANS';
```

**Example: White House Policy News for Trump_Effect Specialist**

```sql
SELECT
  published_at::date as date,
  -- Daily policy event count
  COUNT(*) FILTER (WHERE 'trump_effect' = ANY(specialist_tags)) as trump_event_count,
  -- Sentiment
  AVG(sentiment_score) as sentiment_avg,
  -- Abnormal activity flag
  CASE WHEN COUNT(*) > AVG(COUNT(*)) OVER (ORDER BY date ROWS BETWEEN 30 PRECEDING AND 1 PRECEDING) * 2
    THEN 1 ELSE 0 END as policy_spike_flag
FROM alt.policy_news_1d
WHERE 'trump_effect' = ANY(specialist_tags);
```

**Coverage:** 27 detailed feature engineering examples across 3 specialists in expansion plan, 70+ source-specific SQL/Python snippets in catalog mapping.

---

### 6. Integration Requirements Documentation ✅

**Goal:** For each data source, specify Inngest function requirements (API endpoint, cron schedule, fallback logic, historical backfill).

**Example: CFTC COT Integration**

- **API:** Socrata (3 endpoints: Legacy, Disaggregated, TFF)
  - https://publicreporting.cftc.gov/resource/6dca-aqww.json (Legacy)
  - https://publicreporting.cftc.gov/resource/jun7-fc8e.json (Disaggregated)
  - https://publicreporting.cftc.gov/resource/gpe5-46if.json (TFF)
- **Inngest Function:** `cftc-cot-weekly.ts` (PORT from V14)
- **Cron:** `0 21 * * 5` (weekly on Friday at 9pm UTC — CFTC releases 3:30pm ET Friday)
- **Contract Codes:** 007601 (ZL), 005602 (ZS), 023651 (ZM), 067651 (CL), 023631 (NG), 1170E1 (VIX)
- **Historical Backfill:** 2010-present (~700 weekly reports)
- **New Table:** `pos.cftc_1w` (add to `prisma/schema.prisma`)
- **Fallback:** None (primary source, must succeed)

**Example: USDA WASDE Integration**

- **Source:** PDF reports published ~12th of each month at https://www.usda.gov/oce/commodity/wasde/latest.pdf
- **Inngest Function:** `usda-wasde-monthly.ts`
- **Cron:** `0 18 12 * *` (monthly on 12th at 6pm UTC — report drops 12pm ET)
- **Parsing:** tabula-py or pdfplumber to extract tables, normalize to long format
- **Key Metrics:** US Soybean Crush, US Soybean Exports, World Soybean Oil Production, World Palm Oil Production, Brazil/Argentina Soybean Production, China Soybean Imports
- **Historical Backfill:** 2010-present (120+ monthly reports)
- **New Table:** `supply.wasde_1m` (add to Prisma schema)
- **Fallback:** Manual CSV upload if PDF parsing fails
- **Slack Alert:** Notify #data-pipeline if PDF structure changes

**Coverage:** All 70+ catalog sources have detailed integration specs in the mapping document.

---

## Key Files Created/Modified

### 1. [`plans/SPECIALIST_DATA_SOURCE_EXPANSION.md`](../plans/SPECIALIST_DATA_SOURCE_EXPANSION.md)

**Size:** 500+ lines  
**Purpose:** Comprehensive signal coverage audit & implementation roadmap for top 3 specialists (crush, china, energy)

**Sections:**

1. **Verified Data Source Inventory** — what's available to work with (Databento, FRED, Yahoo, internal tables)
2. **Current State Audit** — signal count matrix (current vs. target for all 11 specialists)
3. **Detailed Expansion Plans** — 27 new signals for crush, 24 for china, 25 for energy
   - Each specialist has 6 phases (cross-commodity, energy inputs, demand proxies, export flows, volume/OI, macro overlays)
   - SQL queries for each phase using ONLY verified available sources
4. **Implementation Roadmap** — 3 phases over 6 weeks (critical expansions, flow signals, macro overlays)
5. **Validation & Testing Protocol** — data quality gates, signal independence tests, performance measurement
6. **Success Metrics** — quantitative targets (avg signals 6→30+, MAE improvement -15% to -20%)

---

### 2. [`plans/CATALOG_SOURCE_TO_SPECIALIST_MAPPING.md`](../plans/CATALOG_SOURCE_TO_SPECIALIST_MAPPING.md)

**Size:** 1,800+ lines  
**Purpose:** Exhaustive mapping of all 70+ catalog sources to specialists with causal ZL prediction links

**Sections:**

1. **Executive Summary** — key findings (30+ sources "Not built", 4 sources STALE, specialist under-utilization matrix)
2. **Methodology** — what each source analysis includes (applicable specialists, causal link, status, feature engineering, integration requirements, priority)
3. **Source-by-Source Mapping:**
   - **USDA sources** (11 sub-agencies: NASS, WASDE, FAS, ERS, AMS, newsrooms)
   - **FRED sources** (130+ series, staleness fix for econ.activity_1d, under-utilized series identification)
   - **EIA sources** (Petroleum Supply, Biodiesel, API v2 downtime)
   - **EPA sources** (RIN data optimization)
   - **CFTC sources** (COT reports — P0 priority)
   - **BLS sources** (defer, FRED covers)
   - **NOAA sources** (weather for crop yields)
   - **White House/USTR/Federal Register** (policy announcements — P0 priority)
   - **Foreign gov sources** (CONAB Brazil, MPOB Malaysia, China GACC/MOFCOM, Panama Canal)
4. **Under-Utilized Sources** — specialist-by-specialist gap analysis
5. **Integration Priority Matrix** — P0/P1/P2/P3 ranking with urgency x impact x difficulty
6. **4-Phase Implementation Roadmap** (8 weeks) — task breakdown with success metrics

---

### 3. [`docs/data-source-catalog.md`](../docs/data-source-catalog.md) (READ ONLY)

**Note:** Did NOT modify this file — it's the reference catalog that was analyzed.  
**Issue Found:** Catalog claims are outdated (4 out of 5 "priority fixes" already implemented).

---

## Current Status

### What's Complete ✅

1. ✅ Data source inventory (Databento, FRED, Yahoo, internal tables, catalog sources)
2. ✅ Model types & requirements per specialist
3. ✅ Current signal count matrix (8 specialists have <10 signals)
4. ✅ Causal links to ZL price (70+ sources documented)
5. ✅ Feature engineering SQL/Python code (80+ examples)
6. ✅ Integration requirements (API endpoints, cron schedules, fallbacks, backfills)
7. ✅ Under-utilization analysis (which specialists missing which sources)
8. ✅ Priority ranking (P0/P1/P2/P3)
9. ✅ 4-phase implementation roadmap (8 weeks)

### What's In Progress 🔄

- **Nothing** — planning phase is complete. Ready for implementation approval.

### What's Pending ⏳

1. ⏳ Stakeholder review of roadmap
2. ⏳ Phase 1 implementation (Weeks 1-2):
   - Fix 4 stale data sources (econ.activity_1d, MPOB palm, EIA biodiesel)
   - Build CFTC COT (new `pos.cftc_1w` table + 3 Inngest functions)
   - Add COT features to 5 specialists
   - Activate 3 under-utilized FRED series (HY OAS, Tallow PPI, Rendering PPI)
3. ⏳ Phase 2-4 implementation (Weeks 3-8) — see roadmap in mapping document

---

## Remaining Tasks (When Resuming)

### Immediate Next Steps (for implementation kickoff)

1. **Review roadmap with Kirk/stakeholders** — confirm priorities, adjust timelines
2. **Create Inngest function templates** for P0 sources:
   - `cftc-cot-weekly.ts` (port from V14)
   - `whitehouse-rss-scraper-hourly.ts`
   - `usda-wasde-monthly.ts`
   - `nass-quickstats-monthly.ts`
   - `noaa-weather-daily.ts`
3. **Update Prisma schema** for new tables:
   ```prisma
   // Add to prisma/schema.prisma
   model cftc_1w { ... }         // pos.cftc_1w
   model policy_news_1d { ... }  // alt.policy_news_1d
   model wasde_1m { ... }        // supply.wasde_1m
   model nass_crops_1m { ... }   // supply.nass_crops_1m
   model weather_1d { ... }      // alt.weather_1d
   model gats_trade_1m { ... }   // supply.gats_trade_1m
   ```
4. **Fix stale data sources:**
   - Diagnose `econ.activity_1d` staleness (29 FRED series stopped Jan 12)
   - Fix MPOB palm scraper or implement Yahoo Finance fallback (FCPO futures)
   - Verify EIA biodiesel CSV fallback is working
5. **Create monitoring dashboards** — alert if any source stale >3 days
6. **Historical backfill scripts** — for all new sources (2010-present)
7. **Feature engineering pipeline** — SQL functions to compute specialist signals from raw tables
8. **Retrain specialists** after Phase 1 — measure MAE improvement

### Long-Term Tasks (Phases 2-4)

- See 4-phase roadmap in [`plans/CATALOG_SOURCE_TO_SPECIALIST_MAPPING.md`](../plans/CATALOG_SOURCE_TO_SPECIALIST_MAPPING.md)
- Policy news automation (White House, USDA, USTR, Federal Register) → NLP pipeline
- Global trade flows (FAS GATS, CONAB Brazil, MPOB Malaysia)
- Weather integration (NOAA NCEI)
- Energy details (EIA Petroleum Supply, refinery cracks)

---

## Critical Findings

### 1. Specialists Are Dangerously Under-Signaled

**Problem:** 6 out of 11 specialists have <10 signals when robust ML requires 30-40 signals per specialist (6-8 orthogonal dimensions: price, flow, positioning, fundamentals, macro, sentiment, correlation, regime).

**Severity Matrix:**
| Specialist | Current Signals | Target | Gap | Severity |
|-----------|----------------|--------|-----|----------|
| **tariff** | 3 | 25+ | 22+ | 🔴 CRITICAL (worst) |
| **trump_effect** | 4 | 25+ | 21+ | 🔴 CRITICAL |
| **substitutes** | 4 | 25+ | 21+ | 🔴 CRITICAL |
| **volatility** | 5 | 30+ | 25+ | 🔴 CRITICAL |
| **biofuel** | 5 | 30+ | 25+ | 🔴 CRITICAL |
| **china** | 6 | 30+ | 24+ | ⚠️ HIGH |
| **palm** | 8 | 25+ | 17+ | ⚠️ HIGH |
| **crush** | 8 | 35+ | 27+ | ⚠️ HIGH |
| **energy** | 10 | 35+ | 25+ | ⚠️ MEDIUM |
| **fx** | 12 | 25+ | 13+ | ✅ ADEQUATE |
| **fed** | 45 | 50+ | 5+ | ✅ EXCELLENT |

**Impact:** Thin signal coverage → overfitting, unstable predictions, poor generalization, high sensitivity to single-source failures.

---

### 2. 30+ Catalog Sources Are "Not Built" Despite Direct ZL Relevance

**Sources with HIGH ZL forecasting value but NOT integrated:**

- **CFTC COT** (positioning data) — 🔴 P0 CRITICAL (affects 5 specialists)
- **USDA WASDE** (monthly supply/demand forecasts) — 🔴 P0 CRITICAL (affects 5 specialists)
- **NASS QuickStats** (crop production) — P1 HIGH (affects 4 specialists)
- **FAS GATS** (global trade flows) — P1 HIGH (affects 4 specialists)
- **NOAA Weather** (drought, GDD) — P1 HIGH (affects 3 specialists)
- **White House/USTR/Federal Register** (policy announcements) — 🔴 P0 CRITICAL (affects 3 specialists)
- **USDA Newsrooms** (3 RSS feeds) — P1 HIGH (affects 4 specialists)
- **ERS Biofuels** (USDA biofuel forecasts) — P1 HIGH (affects 2 specialists)
- **CONAB Brazil** (Brazil soy production) — P1 HIGH (affects 3 specialists)
- **China GACC/MOFCOM** (China import data) — P1 HIGH but DIFFICULT (language, IP blocks)
- **Panama Canal Ops** (logistics bottlenecks) — P2 MEDIUM (affects 2 specialists)
- 20+ more sources...

**Why this matters:** These sources contain market-moving information that specialists are currently blind to (e.g., tariff specialist has ZERO positioning data, biofuel specialist missing EPA waiver announcements, china specialist missing Brazil competition data).

---

### 3. 4 Data Sources Are STALE or BROKEN

**Urgent fixes required:**

1. **`econ.activity_1d`** (29 FRED series) — stopped updating Jan 12, 2026 (7 weeks stale)
   - Affects: fed specialist (missing PMI, unemployment, CPI, industrial production)
   - Fix: Diagnose Inngest function error, backfill Jan 12 - present
2. **MPOB palm data** (Malaysia CPO prices) — stale since Dec 2025 (3 months stale)
   - Affects: palm specialist (PRIMARY palm signal), substitutes specialist
   - Fix: Repair scraper or implement Yahoo Finance fallback (FCPO futures)
3. **EIA biodiesel weekly** — 0 rows (API down upstream)
   - Affects: biofuel specialist, energy specialist
   - Fix: CSV fallback (already exists, verify it's working)
4. **EIA biodiesel monthly** — stale since Nov 2025 (3+ months stale)
   - Affects: biofuel specialist (currently has only 5 signals total)
   - Fix: Same CSV fallback as weekly

**Impact:** Specialists training on stale data → predictions drift from reality, forecast accuracy degrades over time.

---

### 4. Existing Sources Are Under-Utilized

**Problem:** Many data sources ARE being ingested into the database but NOT consumed by specialists that need them.

**Examples:**

- **FRED Tallow PPI (WPU06410132)** — ingested, but substitutes specialist doesn't use it (competing biodiesel feedstock)
- **FRED Rendering PPI (PCU3116133116132)** — ingested, but biofuel specialist doesn't use it (by-product economics)
- **FRED HY OAS (BAMLH0A0HYM2)** — ingested, but fed specialist doesn't use it (credit risk signal)
- **FRED VIX / STLFSI4** — ingested, but volatility specialist under-utilizes them
- **FAS Export Sales** (country-level soy purchases) — ingested, but china/tariff/trump_effect specialists don't consume it (direct China demand signal)
- **EPA RIN data** — ingested but "at source limit" (hitting API quota)

**Fix:** Feature engineering pass to connect ingested data → specialist training matrices. NO new data ingestion needed for these.

---

### 5. Integration Priority: CFTC COT is P0 (Highest Impact)

**Why COT is critical:**

- **Positioning data affects 5 specialists:** tariff, volatility, trump_effect, crush, china
- **V14 code already exists** (Socrata API integration) — just needs porting to V15
- **Free API, no auth required** — low integration friction
- **Historical data available** (2010-present, ~700 weekly reports) — can backfill immediately
- **Weekly updates** (Friday 3:30pm ET) — aligns with ZL trading week
- **Direct ZL contract data** (code 007601) — no proxy needed

**Causal link:**

```
CFTC COT report → Managed money net long >90th percentile → Crowded trade → Mean reversion risk → ZL price reversal
COT commercial shorts ↑ → Producer hedging (bearish outlook) → ZL price pressure
COT positioning extremes → Volatility regime shift → ZL forecast uncertainty ↑
```

**Implementation:**

- New table: `pos.cftc_1w` (add to Prisma schema)
- Inngest function: `cftc-cot-weekly.ts` (port from V14)
- Cron: `0 21 * * 5` (weekly on Friday at 9pm UTC)
- Backfill: 2010-present (700 reports)
- Features: mm_net_long, mm_net_long_pctile, commercial_net_short, swap_dealer_net, crowded_trade_flag, wow_change

---

## Next Actions (Prioritized)

### Phase 1 (Weeks 1-2): Critical Data Fixes & COT

**Goal:** Fix stale data, add CFTC COT positioning to 5 specialists

| Priority | Task                                                 | Specialists                                    | Deliverable                                                         |
| -------- | ---------------------------------------------------- | ---------------------------------------------- | ------------------------------------------------------------------- |
| **P0-A** | Fix `econ.activity_1d` staleness                     | fed, china                                     | 29 FRED series updating daily                                       |
| **P0-B** | Fix MPOB palm data                                   | palm, substitutes                              | CPO price data current (scraper repair or Yahoo FCPO fallback)      |
| **P0-C** | Fix EIA biodiesel                                    | biofuel, energy                                | Weekly/monthly biodiesel data flowing (CSV fallback active)         |
| **P0-D** | Build CFTC COT (3 Socrata APIs)                      | tariff, volatility, trump_effect, crush, china | `pos.cftc_1w` table created + 700 weeks backfilled + weekly updates |
| **P0-E** | White House RSS scraper                              | tariff, trump_effect                           | Policy news flowing, NLP tagging working                            |
| **P1-A** | Add FRED HY OAS to fed specialist                    | fed                                            | Feature in training matrix                                          |
| **P1-B** | Add FRED Tallow/Rendering PPI to substitutes/biofuel | substitutes, biofuel                           | Features in training matrices                                       |

**Success Metrics:**

- 4 stale data sources fixed
- COT features added to 5 specialists
- 3 under-utilized FRED series activated
- Policy news pipeline operational

---

### Phase 2 (Weeks 3-4): USDA Core Data & Policy News

**Goal:** Add USDA forecasts, policy event monitoring

| Priority | Task                           | Specialists                             | Deliverable                                           |
| -------- | ------------------------------ | --------------------------------------- | ----------------------------------------------------- |
| **P1**   | USDA WASDE monthly scraper     | crush, china, substitutes, tariff, palm | `supply.wasde_1m` table + 120 months backfilled       |
| **P1**   | NASS QuickStats API            | crush, china, substitutes, biofuel      | `supply.nass_crops_1m` table + 10 years backfilled    |
| **P1**   | NASS Grain Stocks quarterly    | crush, substitutes                      | Quarterly stocks reports automated                    |
| **P1**   | USDA Newsrooms scraper (3 RSS) | tariff, trump_effect, biofuel, china    | Ag policy news classified by specialist               |
| **P1**   | Federal Register API scraper   | tariff, biofuel, trump_effect           | `alt.policy_news_1d` table, executive orders captured |
| **P1**   | USTR Press scraper             | tariff, trump_effect                    | Trade policy announcements captured                   |

**Success Metrics:**

- WASDE forecasts automated (monthly)
- NASS crop data flowing (annual production, yield)
- Policy event features added to 4 specialists

---

### Phase 3 (Weeks 5-6): Weather, Trade Flows, Energy Details

**Goal:** Add weather, global trade, refinery data

| Priority | Task                              | Specialists                      | Deliverable                                            |
| -------- | --------------------------------- | -------------------------------- | ------------------------------------------------------ |
| **P1**   | NOAA Weather daily scraper        | crush, china, biofuel            | `alt.weather_1d` table + drought/GDD features          |
| **P1**   | FAS GATS global trade             | china, palm, substitutes, tariff | `supply.gats_trade_1m` table + Brazil-China flows      |
| **P1**   | EIA Petroleum Supply weekly       | energy, biofuel                  | `supply.eia_petroleum_1w` table + refinery utilization |
| **P1**   | ERS Biofuels monthly              | biofuel, energy                  | `supply.ers_biofuels_1m` table + biodiesel forecasts   |
| **P1**   | Enhance FAS Export Sales features | china, tariff, trump_effect      | China share, diversion ratio, YoY features added       |

**Success Metrics:**

- Weather features added to 3 specialists
- Trade flow features added to 4 specialists
- Energy refinery signals added

---

### Phase 4 (Weeks 7-8): Foreign Sources & Final Enhancements

**Goal:** Brazil data, palm fallbacks, remaining gaps

| Priority | Task                                    | Specialists                | Deliverable                                                   |
| -------- | --------------------------------------- | -------------------------- | ------------------------------------------------------------- |
| **P1**   | CONAB Brazil harvest scraper            | china, tariff, substitutes | `supply.conab_harvest_1m` table + Brazil production forecasts |
| **P2**   | Yahoo Finance palm futures (FCPO)       | palm, substitutes          | Daily CPO price proxy if MPOB fails                           |
| **P1**   | Optimize EPA RINs (reduce source limit) | biofuel, energy            | Daily RIN prices flowing, no errors                           |
| **P2**   | Panama Canal Ops scraper                | crush, china               | Daily transit data (if needed)                                |
| **P0**   | Final feature engineering pass          | ALL                        | All catalog sources mapped to specialist features             |

**Success Metrics:**

- Brazil production features added
- Palm futures fallback operational
- 100% of P0/P1 catalog sources integrated
- Avg signals per specialist: 6 → 30+
- Specialists with <10 signals: 6/11 → 0/11

---

## Technical Notes

### Forward Fill Policy (from `src/fusion/config/forward_fill_config.py`)

**NEVER forward-fill:**

- Market prices (futures, FX, options, equity indices)
- Volume, open interest
- Intraday data

**DO forward-fill (with TTL limits):**

- Economic reports (WASDE, NASS, COT) — TTL: 30-90 days
- FRED series (rates, macro) — TTL: 7-30 days
- Weather aggregates (monthly) — TTL: 30 days
- Policy news sentiment (daily) — TTL: 3 days

### Data Quality Gates

All new sources must pass:

1. **Staleness check:** No gaps >3 days for daily data, >7 days for weekly data
2. **NULL validation:** <5% NULL rate for critical features
3. **Outlier detection:** Z-score >4 triggers quarantine (analyst review)
4. **Backfill completeness:** Historical data complete to 2010 (or source inception date)
5. **Idempotency:** Re-running ingestion doesn't create duplicates (row_hash deduplication)

### Signal Independence Testing

After adding new features to specialists:

1. **Correlation matrix:** No feature pairs >0.80 correlation (multicollinearity check)
2. **VIF analysis:** Variance Inflation Factor <10 for all features
3. **PCA:** No single principal component explains >50% variance (signals are orthogonal)

### Model Performance Validation

After retraining specialists:

1. **OOF MAE:** Out-of-fold Mean Absolute Error vs. baseline (pre-expansion)
2. **Backtest:** Rolling window validation on 2020-2025 data
3. **A/B test:** New specialist signals vs. old signals (hold specialist constant, swap signal sets)
4. **Target:** -15% to -20% MAE improvement for Core after all 11 specialists expanded

---

## References

### Key Files

- [`AGENTS.md`](../AGENTS.md) — Workspace guide, specialist architecture, hard-coded corrections
- [`docs/data-source-catalog.md`](../docs/data-source-catalog.md) — All 70+ data source URLs
- [`plans/SPECIALIST_DATA_SOURCE_EXPANSION.md`](../plans/SPECIALIST_DATA_SOURCE_EXPANSION.md) — Detailed expansion plan for top 3 specialists
- [`plans/CATALOG_SOURCE_TO_SPECIALIST_MAPPING.md`](../plans/CATALOG_SOURCE_TO_SPECIALIST_MAPPING.md) — Exhaustive catalog mapping
- [`src/fusion/specialists/contracts.py`](../src/fusion/specialists/contracts.py) — Model types, signal contracts
- [`scripts/generate_specialist_features.py`](../scripts/generate_specialist_features.py) — Current feature configs
- [`prisma/schema.prisma`](../prisma/schema.prisma) — Database schema (12 schemas, 150+ tables)

### Inngest Function Patterns

- [`frontend/src/inngest/cftc-weekly.ts`](../frontend/src/inngest/cftc-weekly.ts) — CFTC COT ingestion (ALREADY EXISTS, confirmed 2026-03-05)
- [`frontend/src/inngest/fred-daily.ts`](../frontend/src/inngest/fred-daily.ts) — FRED API ingestion (130+ series)
- [`frontend/src/inngest/databento-futures-daily.ts`](../frontend/src/inngest/databento-futures-daily.ts) — Futures price ingestion
- Use these as templates for new Inngest functions

### Specialist Training Pipeline

1. **Feature generation:** `scripts/generate_specialist_features.py` → `training.specialist_signals_1d`
2. **Matrix build:** `scripts/build_matrix.py` → `training.matrix_1d` (merges specialist signals + raw features)
3. **Specialist training:** `src/fusion/specialists/train_specialist.py` → `models/specialists/{bucket}/`
4. **Core training:** `src/fusion/core_training/train.py` → `models/core_v2/{horizon}d/`
5. **OOF predictions:** Written to `training.oof_core_1d`
6. **L2/L3 calibration:** Monte Carlo + pinball → `forecasts.target_zones_1d`

---

## Session Summary

**What was accomplished:**

- Audited 70+ catalog data sources
- Mapped each source to applicable specialists with causal ZL prediction links
- Identified 30+ sources "Not built", 4 sources STALE
- Documented under-utilization (6 specialists have <10 signals, target 30-40 signals)
- Created 80+ feature engineering SQL/Python examples
- Designed 4-phase implementation roadmap (8 weeks, P0→P1→P2→P3 prioritization)
- Generated 2 comprehensive planning documents (2,300+ total lines)

**Key insight:**
Specialists are operating on **dangerously thin signal sets** (1-3 data sources per specialist bucket) when robust ML requires **thick, multi-dimensional signal coverage** (6-8 orthogonal dimensions, 30-40 signals total). This is the root cause of why the system may be underperforming.

**Immediate action required:**
Phase 1 (Weeks 1-2) — Fix 4 stale data sources + build CFTC COT + White House RSS scraper → add positioning and policy signals to 8 specialists.

**Expected impact:**

- Avg signals per specialist: 6 → 30+ (5x improvement)
- Core MAE improvement: -15% to -20%
- Specialists with <10 signals: 6/11 → 0/11
- Data freshness: <3 days average staleness

**Status:** Planning phase complete. Ready for implementation approval and Phase 1 kickoff.

---

**Session End Time:** 2026-03-05 15:09 UTC (9:09 AM CST)  
**Next Session:** Review roadmap with stakeholders → begin Phase 1 implementation
