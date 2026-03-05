# Catalog Source → Specialist Mapping Analysis

**Created:** 2026-03-05  
**Purpose:** Map each [`docs/data-source-catalog.md`](../docs/data-source-catalog.md) source to relevant specialists with causal ZL prediction links, feature engineering recommendations, and integration requirements.

---

## Executive Summary

This document cross-references the 70+ data sources in the catalog against the 11 specialist models to identify:

1. **Under-utilized sources** — catalog sources not yet integrated into specialists that need them
2. **Causal links to ZL** — specific transmission mechanisms from each source to soybean oil futures price
3. **Feature engineering** — SQL/Python transformations to create specialist signals from raw catalog data
4. **Integration gaps** — which sources lack Inngest functions, need fallback scrapers, or have stale data

### Key Findings

| Finding                                                                                | Impact                                                                   |
| -------------------------------------------------------------------------------------- | ------------------------------------------------------------------------ |
| **30+ catalog sources are "Not built"** despite direct ZL relevance                    | Specialists operating with 20-60% of available signal coverage           |
| **CFTC COT positioning data** exists in catalog but NOT integrated into ANY specialist | Tariff, volatility, trump_effect specialists blind to positioning shifts |
| **WASDE Reports** not automated                                                        | China, crush, substitutes specialists lack USDA supply/demand forecasts  |
| **Foreign gov sources** (CONAB, MPOB, GACC) not built                                  | China, palm, substitutes specialists missing origin country data         |
| **NOAA weather** not integrated                                                        | Crush, china, biofuel specialists lack crop yield/drought signals        |
| **White House/USTR/Fed Register** not monitored                                        | Tariff, trump_effect specialists blind to policy announcements           |
| **EIA biodiesel data** stale/broken                                                    | Biofuel specialist running on Nov 2025 data (3+ months stale)            |

---

## Methodology

For each catalog source, this analysis documents:

1. **Applicable Specialists** — which of the 11 specialists can consume this source (and why)
2. **Causal Link to ZL** — specific transmission mechanism to soybean oil futures price
3. **Current Integration Status** — ✅ WORKING / ⚠️ STALE / 🔴 NOT BUILT / 🟡 PARTIAL
4. **Feature Engineering** — SQL/Python transformations to create specialist signals
5. **Integration Requirements** — Inngest function specs (cron, API endpoint, fallback logic)
6. **Priority** — P0 (critical) / P1 (high) / P2 (medium) / P3 (nice-to-have)

---

## Source-by-Source Mapping

### USDA Sources

#### 1. NASS QuickStats API

**URL:** https://quickstats.nass.usda.gov/api  
**Status:** 🔴 NOT BUILT  
**Priority:** P0 (CRITICAL)

**Applicable Specialists:**

- **crush** (GBM) — soybean production forecasts drive crush margin expectations
- **china** (GBM) — US soybean yield affects export availability to China
- **substitutes** (RF) — competing oilseed production (canola, sunflower, cotton) affects substitution pressure
- **biofuel** (NLP+EMA) — corn yield affects ethanol production economics and RIN prices

**Causal Link to ZL:**

```
QuickStats crop production → Soybean supply outlook → Crush availability → ZL supply/demand balance → ZL price
QuickStats yield/acre → Harvest timing → Export flow timing → China demand fulfillment → ZL export premium
QuickStats competing oilseeds → Substitution pressure → ZL relative value → ZL price
```

**Feature Engineering:**

```python
# Inngest function: usda-quickstats-monthly.ts
# Store in: supply.nass_crops_1m (new table)
# Schema: date, commodity, state, data_item, value, unit, freq

# SQL features for specialists:
SELECT
  date,
  -- Soybean production outlook
  AVG(CASE WHEN commodity = 'SOYBEANS' AND data_item = 'YIELD' THEN value END) as soybean_yield_bpa,
  AVG(CASE WHEN commodity = 'SOYBEANS' AND data_item = 'PRODUCTION' THEN value END) as soybean_production_bu,

  -- Competing oilseed supply
  AVG(CASE WHEN commodity = 'CANOLA' AND data_item = 'PRODUCTION' THEN value END) as canola_production_cwt,
  AVG(CASE WHEN commodity = 'SUNFLOWER' AND data_item = 'PRODUCTION' THEN value END) as sunflower_production_lbs,
  AVG(CASE WHEN commodity = 'COTTONSEED' AND data_item = 'PRODUCTION' THEN value END) as cottonseed_production_tons,

  -- Corn for ethanol (biofuel spillover)
  AVG(CASE WHEN commodity = 'CORN' AND data_item = 'YIELD' THEN value END) as corn_yield_bpa,

  -- Z-scores vs 5yr avg
  (value - AVG(value) OVER (PARTITION BY commodity, data_item ORDER BY date ROWS BETWEEN 60 PRECEDING AND 1 PRECEDING))
    / NULLIF(STDDEV(value) OVER (PARTITION BY commodity, data_item ORDER BY date ROWS BETWEEN 60 PRECEDING AND 1 PRECEDING), 0) as z_score
FROM supply.nass_crops_1m
WHERE commodity IN ('SOYBEANS', 'CANOLA', 'SUNFLOWER', 'COTTONSEED', 'CORN')
GROUP BY date, commodity, data_item, value;
```

**Integration Requirements:**

- **API Key:** Register at https://quickstats.nass.usda.gov/api (free, 500 req/min)
- **Inngest Function:** `usda-quickstats-monthly.ts`
- **Cron:** `0 5 10 * *` (monthly on 10th at 5am UTC — NASS releases mid-month)
- **Data Items:** YIELD, PRODUCTION, PLANTED, HARVESTED for SOYBEANS, CORN, CANOLA, SUNFLOWER, COTTONSEED
- **Historical Backfill:** 2010-present (annual data)
- **Fallback:** None (primary source, must succeed)

---

#### 2. WASDE Reports

**URL:** https://www.usda.gov/oce/commodity/wasde/  
**Status:** 🔴 NOT BUILT  
**Priority:** P0 (CRITICAL)

**Applicable Specialists:**

- **crush** (GBM) — WASDE soybean crush forecast directly impacts ZL supply
- **china** (GBM) — WASDE export forecasts signal China demand outlook
- **substitutes** (RF) — WASDE palm/canola/sunflower production affects global oils balance
- **tariff** (Tree) — WASDE Brazil/Argentina production forecasts signal competitive pressure during tariff disputes
- **palm** (ECM+Ridge) — WASDE palm oil global supply/demand balance

**Causal Link to ZL:**

```
WASDE monthly report → Soybean crush forecast revision → ZL supply expectation update → ZL price adjustment
WASDE export forecast → China import demand signal → ZL export premium → ZL price
WASDE palm oil production → Palm-soy spread → Substitution pressure → ZL demand → ZL price
WASDE Brazil production → US export competition → ZL export premium → ZL price
```

**Feature Engineering:**

```python
# Inngest function: usda-wasde-monthly.ts
# Store in: supply.wasde_1m (new table)
# Schema: report_date, commodity, country, metric, value, unit, forecast_year

# Key metrics to extract from PDF:
# - US Soybean Crush (million bushels)
# - US Soybean Exports (million bushels)
# - World Soybean Oil Production (million metric tons)
# - World Palm Oil Production (million metric tons)
# - Brazil Soybean Production (million metric tons)
# - Argentina Soybean Production (million metric tons)
# - China Soybean Imports (million metric tons)

# SQL features for specialists:
SELECT
  report_date,
  -- MoM revisions (shocks to expectations)
  value - LAG(value, 1) OVER (PARTITION BY commodity, country, metric ORDER BY report_date) as mom_revision,

  -- YoY growth
  (value / LAG(value, 12) OVER (PARTITION BY commodity, country, metric ORDER BY report_date) - 1) * 100 as yoy_growth_pct,

  -- Deviation from analyst consensus (if available)
  value - consensus_estimate as surprise,

  -- Crush-to-production ratio
  MAX(CASE WHEN metric = 'CRUSH' THEN value END) / NULLIF(MAX(CASE WHEN metric = 'PRODUCTION' THEN value END), 0) as crush_rate_pct
FROM supply.wasde_1m
WHERE commodity IN ('SOYBEANS', 'SOYBEAN_OIL', 'PALM_OIL')
  AND country IN ('US', 'WORLD', 'BRAZIL', 'ARGENTINA', 'CHINA')
GROUP BY report_date, commodity, country, metric, value, consensus_estimate;
```

**Integration Requirements:**

- **Source:** PDF reports published ~12th of each month at https://www.usda.gov/oce/commodity/wasde/latest.pdf
- **Inngest Function:** `usda-wasde-monthly.ts`
- **Cron:** `0 18 12 * *` (monthly on 12th at 6pm UTC — report usually drops 12pm ET)
- **Parsing:** Use tabula-py or pdfplumber to extract tables, normalize to long format
- **Historical Backfill:** 2010-present (120+ monthly reports)
- **Fallback:** Manual CSV upload if PDF parsing fails
- **Slack Alert:** Notify #data-pipeline if PDF structure changes (parsing failure)

---

#### 3. FAS Export Sales (CURRENT: WORKING ✅)

**URL:** https://apps.fas.usda.gov/export-sales/esrd1.html  
**Status:** ✅ WORKING  
**Priority:** P1 (maintain, enhance)

**Current Integration:**

- **Table:** `supply.usda_exports_1w`
- **Inngest:** Already exists (confirmed 2026-03-05)
- **Coverage:** Country-level data for soybeans, soybean oil, soybean meal

**Applicable Specialists:**

- **crush** (GBM) — soybean oil export sales signal domestic vs export demand split
- **china** (GBM) — China's share of soy complex purchases is DIRECT demand signal
- **tariff** (Tree) — bilateral trade flow disruptions (China drops, other countries surge) signal tariff impact
- **trump_effect** (Event Study) — country-level anomalies correlate with policy announcements

**Causal Link to ZL:**

```
Weekly export sales → China purchase volume → ZL export demand → ZL price
Export sales by country → Trade diversion patterns → Tariff impact → ZL premium/discount to global oils
Oil-to-meal export ratio → Crush demand signal → ZL supply expectations → ZL price
```

**Feature Engineering (EXPAND CURRENT USAGE):**

```sql
-- Current specialists under-utilize this table. Add these features:
WITH country_shares AS (
  SELECT
    report_date,
    country,
    commodity,
    outstanding_sales_current_week,
    accumulated_exports_current_week,

    -- China concentration risk
    SUM(CASE WHEN country = 'CHINA' THEN outstanding_sales_current_week END) /
      NULLIF(SUM(outstanding_sales_current_week), 0) as china_share_outstanding,

    -- Trade diversion index (Pakistan/Egypt surge when China drops)
    SUM(CASE WHEN country IN ('PAKISTAN', 'EGYPT', 'INDONESIA') THEN accumulated_exports_current_week END) /
      NULLIF(SUM(CASE WHEN country = 'CHINA' THEN accumulated_exports_current_week END), 0) as diversion_ratio
  FROM supply.usda_exports_1w
  WHERE commodity IN ('SOYBEANS', 'SOYBEAN_OIL')
    AND report_date >= CURRENT_DATE - INTERVAL '5 years'
  GROUP BY report_date, country, commodity, outstanding_sales_current_week, accumulated_exports_current_week
)
SELECT
  report_date,
  country,
  commodity,

  -- YoY comparison (tariff impact signal)
  (accumulated_exports_current_week /
    NULLIF(LAG(accumulated_exports_current_week, 52) OVER (PARTITION BY country, commodity ORDER BY report_date), 0) - 1) * 100
    as yoy_export_growth_pct,

  -- China share z-score (concentration risk)
  (china_share_outstanding - AVG(china_share_outstanding) OVER (PARTITION BY commodity ORDER BY report_date ROWS BETWEEN 52 PRECEDING AND 1 PRECEDING)) /
    NULLIF(STDDEV(china_share_outstanding) OVER (PARTITION BY commodity ORDER BY report_date ROWS BETWEEN 52 PRECEDING AND 1 PRECEDING), 0)
    as china_share_z,

  -- Diversion ratio spike (tariff signal)
  diversion_ratio,
  CASE WHEN diversion_ratio > 2 THEN 1 ELSE 0 END as diversion_spike_flag
FROM country_shares;
```

**Integration Requirements:**

- **ENHANCE existing Inngest function** — add country-level aggregations, z-scores, YoY comparisons
- **No new infrastructure needed** — table exists, function runs weekly
- **Add to specialists:** china (priority), tariff, trump_effect (currently NOT consuming this table)

---

#### 4. FAS GATS (Global Agricultural Trade System)

**URL:** https://apps.fas.usda.gov/gats/  
**Status:** 🔴 NOT BUILT  
**Priority:** P1 (HIGH — complements FAS Export Sales with full global trade matrix)

**Applicable Specialists:**

- **china** (GBM) — China's imports from Brazil vs US reveal competitive dynamics
- **palm** (ECM+Ridge) — Indonesia/Malaysia palm oil exports to all destinations
- **substitutes** (RF) — global vegetable oil trade flows (palm, soy, canola, sunflower)
- **tariff** (Tree) — bilateral trade disruptions visible in GATS matrix

**Causal Link to ZL:**

```
GATS China imports from Brazil → US-Brazil export competition → ZL export premium adjustment
GATS palm oil global flows → Palm-soy substitution pressure → ZL demand → ZL price
GATS canola/sunflower trade → Competing oils availability → ZL relative value → ZL price
GATS tariff-driven trade shifts → Policy impact quantification → ZL risk premium
```

**Feature Engineering:**

```python
# Inngest function: usda-gats-monthly.ts
# Store in: supply.gats_trade_1m (new table)
# Schema: date, exporter, importer, commodity, value_usd, quantity_mt, unit_price

# SQL features for specialists:
SELECT
  date,
  exporter,
  importer,
  commodity,

  -- Brazil-US competition for China market
  SUM(CASE WHEN exporter = 'BRAZIL' AND importer = 'CHINA' AND commodity = 'SOYBEANS' THEN quantity_mt END) /
    NULLIF(SUM(CASE WHEN exporter IN ('US', 'BRAZIL') AND importer = 'CHINA' AND commodity = 'SOYBEANS' THEN quantity_mt END), 0)
    as brazil_share_china_soy_imports,

  -- Palm oil global export concentration
  SUM(CASE WHEN exporter IN ('INDONESIA', 'MALAYSIA') AND commodity = 'PALM_OIL' THEN quantity_mt END) /
    NULLIF(SUM(CASE WHEN commodity = 'PALM_OIL' THEN quantity_mt END), 0)
    as palm_export_concentration,

  -- YoY trade flow changes (tariff impact)
  (quantity_mt / NULLIF(LAG(quantity_mt, 12) OVER (PARTITION BY exporter, importer, commodity ORDER BY date), 0) - 1) * 100
    as yoy_trade_growth_pct
FROM supply.gats_trade_1m
WHERE commodity IN ('SOYBEANS', 'SOYBEAN_OIL', 'PALM_OIL', 'CANOLA', 'SUNFLOWER_OIL')
  AND date >= '2010-01-01'
GROUP BY date, exporter, importer, commodity, quantity_mt;
```

**Integration Requirements:**

- **API:** GATS has a bulk download API (requires registration)
- **Inngest Function:** `usda-gats-monthly.ts`
- **Cron:** `0 10 5 * *` (monthly on 5th at 10am UTC — data lags by 2 months)
- **Commodities:** SOYBEANS, SOYBEAN_OIL, SOYBEAN_MEAL, PALM_OIL, CANOLA, SUNFLOWER_OIL, RAPESEED_OIL
- **Historical Backfill:** 2010-present (annual data available back to 1990)
- **Fallback:** CSV download from web interface if API fails

---

#### 5. ERS Exchange Rates

**URL:** https://www.ers.usda.gov/data-products/agricultural-exchange-rate-data-set  
**Status:** 🔴 NOT BUILT (using FRED proxies currently)  
**Priority:** P2 (MEDIUM — FRED already covers major currencies)

**Applicable Specialists:**

- **fx** (ARDL) — agricultural-weighted USD index complements FRED trade-weighted USD
- **china** (GBM) — CNY real effective exchange rate affects China import purchasing power
- **tariff** (Tree) — BRL devaluation affects Brazil-US export competition

**Causal Link to ZL:**

```
BRL devaluation → Brazil soy exports more competitive → US export pressure → ZL price decline
CNY appreciation → China import purchasing power ↑ → ZL demand ↑ → ZL price
Agricultural USD index → Export competitiveness → ZL international demand → ZL price
```

**Feature Engineering:**

```sql
-- Compare to FRED series (DEXBZUS, DEXCHUS) — if ERS provides REER or ag-weighted rates, add as features
-- Otherwise SKIP (FRED covers this adequately)
```

**Integration Requirements:**

- **SKIP FOR NOW** — FRED series (DEXBZUS, DEXCHUS, DTWEXBGS) already integrated
- **Revisit if ERS provides:** Real Effective Exchange Rates (REER) or agricultural export-weighted indices
- **Priority:** P2 (low urgency)

---

#### 6. ERS Biofuels

**URL:** https://www.ers.usda.gov/webdocs/  
**Status:** 🔴 NOT BUILT  
**Priority:** P1 (HIGH — biofuel specialist currently has only 5 signals)

**Applicable Specialists:**

- **biofuel** (NLP+EMA) — USDA biofuel production forecasts, RINs analysis, mandate compliance data
- **energy** (VAR) — biodiesel-petroleum substitution dynamics

**Causal Link to ZL:**

```
ERS biodiesel mandate forecast → B100 demand outlook → Soybean oil feedstock demand → ZL price
ERS RIN compliance cost analysis → Biodiesel profit margin → ZL feedstock willingness-to-pay → ZL price
ERS corn ethanol economics → RIN price spillover → Biodiesel RIN arbitrage → ZL demand
```

**Feature Engineering:**

```python
# Inngest function: usda-ers-biofuels-monthly.ts
# Store in: supply.ers_biofuels_1m (new table)
# Schema: date, metric, value, unit, forecast_flag

# Key metrics to extract from ERS reports:
# - Biodiesel production (million gallons)
# - Biodiesel RIN generation (D4, D6)
# - Soybean oil feedstock usage (million pounds)
# - Feedstock cost (cents/lb)
# - RFS mandate compliance rate (%)

# SQL features:
SELECT
  date,
  -- MoM production growth
  (value / NULLIF(LAG(value, 1) OVER (PARTITION BY metric ORDER BY date), 0) - 1) * 100 as mom_growth_pct,

  -- Feedstock intensity (lbs soy oil per gallon biodiesel)
  MAX(CASE WHEN metric = 'SOY_OIL_FEEDSTOCK_LBS' THEN value END) /
    NULLIF(MAX(CASE WHEN metric = 'BIODIESEL_PRODUCTION_GAL' THEN value END), 0) as feedstock_intensity,

  -- RIN compliance gap
  MAX(CASE WHEN metric = 'RIN_MANDATE' THEN value END) -
    MAX(CASE WHEN metric = 'RIN_GENERATED' THEN value END) as rin_deficit
FROM supply.ers_biofuels_1m
GROUP BY date, metric, value;
```

**Integration Requirements:**

- **Source:** ERS publishes monthly/quarterly reports as PDFs at https://www.ers.usda.gov/topics/farm-economy/bioenergy/
- **Inngest Function:** `usda-ers-biofuels-monthly.ts`
- **Cron:** `0 12 15 * *` (monthly on 15th at 12pm UTC)
- **Parsing:** PDF scraping via pdfplumber or manual CSV entry
- **Historical Backfill:** 2010-present
- **Fallback:** EIA biodiesel data (already partially integrated)

---

#### 7. AMS Grain Truck Tonnage

**URL:** https://www.ams.usda.gov/services/transportation/grain-truck-tonnage  
**Status:** 🔴 NOT BUILT  
**Priority:** P3 (LOW — indirect signal, low forecasting power)

**Applicable Specialists:**

- **crush** (GBM) — grain transportation constraints signal logistical bottlenecks affecting crush plant feedstock delivery

**Causal Link to ZL:**

```
Truck tonnage shortage → Soybean delivery delays to crush plants → Temporary crush slowdown → ZL supply tightness → ZL price spike
```

**Feature Engineering:**

```sql
-- Low priority — transportation data is noisy and lags crushing activity
-- Consider adding ONLY if crush specialist performance remains weak after other enhancements
```

**Integration Requirements:**

- **DEFER** — P3 priority, build only if other crush signals insufficient

---

#### 8. NASS Grain Stocks

**URL:** https://www.usda.gov/nass/  
**Status:** 🔴 NOT BUILT  
**Priority:** P1 (HIGH — quarterly grain stocks report is market-moving)

**Applicable Specialists:**

- **crush** (GBM) — soybean stocks-to-use ratio signals supply tightness for crush operations
- **substitutes** (RF) — corn stocks affect ethanol economics and RIN prices (spillover to biodiesel)

**Causal Link to ZL:**

```
NASS Grain Stocks report → Soybean stocks below expectations → Supply tightness → Crush margin compression → ZL supply concern → ZL price spike
NASS stocks-to-use ratio → Carryover availability → ZL seasonal pattern → ZL price
```

**Feature Engineering:**

```python
# Inngest function: usda-grain-stocks-quarterly.ts
# Store in: supply.grain_stocks_1q (new table)
# Schema: report_date, commodity, stocks_bu, previous_year_stocks_bu, pct_change_yoy

# SQL features:
SELECT
  report_date,
  commodity,
  stocks_bu,

  -- Stocks-to-use ratio (requires usage data from WASDE)
  stocks_bu / NULLIF((SELECT value FROM supply.wasde_1m WHERE metric = 'DOMESTIC_USAGE' AND commodity = 'SOYBEANS' AND report_date = grain_stocks_1q.report_date), 0)
    as stocks_to_use_ratio,

  -- YoY change
  (stocks_bu / NULLIF(previous_year_stocks_bu, 0) - 1) * 100 as yoy_stocks_change_pct,

  -- Surprise vs consensus (if available)
  stocks_bu - analyst_consensus as stocks_surprise_bu
FROM supply.grain_stocks_1q
WHERE commodity = 'SOYBEANS';
```

**Integration Requirements:**

- **Source:** Quarterly reports (Mar, Jun, Sep, Dec) at https://www.nass.usda.gov/Surveys/Guide_to_NASS_Surveys/Grain_Stocks/
- **Inngest Function:** `usda-grain-stocks-quarterly.ts`
- **Cron:** `0 15 30 3,6,9,12 *` (quarterly on 30th at 3pm UTC)
- **Historical Backfill:** 2010-present
- **Fallback:** Manual CSV entry from PDF

---

#### 9-11. USDA/NASS/FAS Newsrooms

**URLs:** https://www.usda.gov/media/press-releases, https://www.nass.usda.gov/Newsroom/, https://www.fas.usda.gov/newsroom/news-releases  
**Status:** 🔴 NOT BUILT  
**Priority:** P1 (HIGH — policy announcements are event-driven ZL movers)

**Applicable Specialists:**

- **tariff** (Tree) — USDA trade policy announcements (MFP payments, trade aid, export credits)
- **trump_effect** (Event Study) — executive ag policy, China trade deal mentions
- **biofuel** (NLP+EMA) — biofuel mandate waivers, RFS policy changes

**Causal Link to ZL:**

```
USDA press release → China Phase 1 trade deal update → Export expectation shift → ZL price
NASS surprise crop estimate → Supply shock → ZL volatility spike
FAS export subsidy announcement → US competitiveness boost → ZL export demand → ZL price
```

**Feature Engineering:**

```python
# Inngest function: usda-newsroom-scraper-daily.ts
# Store in: alt.usda_news_1d (new table)
# Schema: published_at, title, url, content, sentiment_score, entity_mentions, specialist_tags

# NLP pipeline:
# 1. Scrape RSS feeds daily
# 2. Extract entities (CHINA, BRAZIL, TARIFFS, BIOFUELS, SOYBEANS, etc.)
# 3. Sentiment scoring via FinBERT
# 4. Tag by specialist (tariff, trump_effect, biofuel, china)
# 5. Create event indicators for abnormal news volume/sentiment

# SQL features:
SELECT
  published_at::date as date,

  -- Daily news volume by specialist
  COUNT(*) FILTER (WHERE 'tariff' = ANY(specialist_tags)) as tariff_news_count,
  COUNT(*) FILTER (WHERE 'trump_effect' = ANY(specialist_tags)) as trump_news_count,
  COUNT(*) FILTER (WHERE 'biofuel' = ANY(specialist_tags)) as biofuel_news_count,

  -- Sentiment aggregation
  AVG(sentiment_score) FILTER (WHERE 'china' = ANY(specialist_tags)) as china_sentiment_avg,

  -- Spike detection (abnormal news volume)
  CASE WHEN COUNT(*) > AVG(COUNT(*)) OVER (ORDER BY published_at::date ROWS BETWEEN 30 PRECEDING AND 1 PRECEDING) * 2
    THEN 1 ELSE 0 END as news_spike_flag
FROM alt.usda_news_1d
WHERE published_at >= CURRENT_DATE - INTERVAL '5 years'
GROUP BY published_at::date;
```

**Integration Requirements:**

- **Inngest Function:** `usda-newsroom-scraper-daily.ts`
- **Cron:** `0 */6 * * *` (every 6 hours — check for new releases)
- **RSS Feeds:**
  - USDA: https://www.usda.gov/rss/oce-reports.xml
  - NASS: https://www.nass.usda.gov/rss/nass.xml
  - FAS: https://www.fas.usda.gov/rss.xml
- **NLP:** FinBERT via Hugging Face Inference API (transformers library)
- **Historical Backfill:** 2018-present (Trump admin onwards)
- **Fallback:** None (best-effort, missing days acceptable)

---

### FRED / Federal Reserve Sources

**Status:** ✅ WORKING (130+ series already integrated)  
**Current Tables:** `econ.rates_1d`, `econ.fx_1d`, `econ.commodities_1d`, `econ.macro_1d`, `econ.activity_1d` (STALE)

#### General FRED Integration Assessment

**WELL-UTILIZED FRED SERIES:**

- **fed** specialist — ✅ Excellent coverage (rates, spreads, Fed Funds, yield curve)
- **fx** specialist — ✅ Good coverage (DEXBZUS, DEXCHUS, DEXMXUS, DTWEXBGS)
- **energy** specialist — ✅ Good coverage (DCOILWTICO, DCOILBRENTEU, DHHNGSP)
- **volatility** specialist — ⚠️ Partial (VIXCLS, STLFSI4 ingested but under-utilized in model)

**UNDER-UTILIZED FRED SERIES:**

- **Tallow PPI (WPU06410132)** — 🔴 NOT consumed by substitutes specialist (competing animal fat feedstock for biodiesel)
- **Rendering PPI (PCU3116133116132)** — 🔴 NOT consumed by biofuel specialist (crushing by-product economics)
- **HY OAS (BAMLH0A0HYM2)** — 🔴 NOT consumed by fed specialist (credit risk signal)
- **Mortgage 30Y (MORTGAGE30US)** — 🔴 NOT consumed by fed specialist (rate transmission to real economy)

#### Priority FRED Enhancements

##### 1. Fix econ.activity_1d Staleness (P0 CRITICAL)

**Catalog Status:** ⚠️ STALE (data stopped Jan 12, 2026)  
**Issue:** 29 FRED series in this table stopped updating — Inngest function likely erroring silently

**Affected Specialists:**

- **fed** (Ridge) — missing recent PMI, unemployment, CPI, industrial production data
- **china** (GBM) — missing China PMI (if included), US activity signals for demand outlook

**Fix:**

```typescript
// frontend/src/inngest/fred-daily.ts — verify error handling for 29 series
// Check if series IDs changed or API key quota hit
// Add Slack alert if any series fails to update >3 days

const ACTIVITY_SERIES = [
  "PAYEMS", // Nonfarm Payroll
  "UNRATE", // Unemployment Rate
  "CPIAUCSL", // CPI
  "PCEPI", // PCE
  "INDPRO", // Industrial Production
  "TCU", // Capacity Utilization
  "RSXFS", // Retail Sales
  "HOUST", // Housing Starts
  "PERMIT", // Building Permits
  "DSPIC96", // Real Disposable Income
  // ... 19 more series
];

// Validate each series individually, quarantine failures
// Backfill missing dates (Jan 12 - present)
```

**Integration Requirements:**

- **Diagnose why 29 series stopped updating** — check FRED API logs in Inngest dashboard
- **Backfill:** Jan 12 - present (~7 weeks of missing data)
- **Add monitoring:** Alert if any series stale >3 days

##### 2. Add Tallow/Rendering PPI to Substitutes + Biofuel Specialists (P1 HIGH)

**Series:** WPU06410132 (Tallow PPI), PCU3116133116132 (Rendering PPI)  
**Status:** ✅ FRED series exist and ARE being ingested (confirmed in catalog), but NOT consumed by specialists

**Applicable Specialists:**

- **substitutes** (RF) — tallow is a competing animal fat feedstock for biodiesel (substitutes soy oil)
- **biofuel** (NLP+EMA) — rendering PPI signals by-product economics from livestock crush

**Causal Link to ZL:**

```
Tallow PPI spike → Tallow-based biodiesel less competitive → Soy oil biodiesel demand ↑ → ZL price ↑
Rendering PPI (distillers grains, DDGs) → Livestock feed economics → Protein meal demand → Soy meal demand → Crush margin → ZL price
```

**Feature Engineering:**

```sql
-- Add to substitutes specialist feature set:
SELECT
  date,
  -- Tallow spread to soy oil (substitution pressure)
  (SELECT close FROM mkt.futures_1d WHERE symbol = 'ZL' AND date = econ.commodities_1d.date) -
    (SELECT value FROM econ.commodities_1d WHERE series_id = 'WPU06410132' AND date = econ.commodities_1d.date)
    as tallow_soy_spread_cents,

  -- Tallow spread z-score
  (tallow_soy_spread_cents - AVG(tallow_soy_spread_cents) OVER (ORDER BY date ROWS BETWEEN 252 PRECEDING AND 1 PRECEDING)) /
    NULLIF(STDDEV(tallow_soy_spread_cents) OVER (ORDER BY date ROWS BETWEEN 252 PRECEDING AND 1 PRECEDING), 0)
    as tallow_spread_z,

  -- Rendering PPI (livestock by-product)
  (SELECT value FROM econ.commodities_1d WHERE series_id = 'PCU3116133116132' AND date = econ.commodities_1d.date) as rendering_ppi,

  -- YoY change
  (rendering_ppi / LAG(rendering_ppi, 252) OVER (ORDER BY date) - 1) * 100 as rendering_ppi_yoy_pct
FROM econ.commodities_1d
WHERE series_id IN ('WPU06410132', 'PCU3116133116132');
```

**Integration Requirements:**

- **NO new data ingestion needed** — series already in `econ.commodities_1d`
- **Update feature configs:** `scripts/generate_specialist_features.py` → add tallow/rendering features to substitutes + biofuel
- **Retrain specialists** after adding features

##### 3. Add HY OAS to Fed Specialist (P1 HIGH)

**Series:** BAMLH0A0HYM2 (High Yield Option-Adjusted Spread)  
**Status:** ✅ Ingested, 🔴 NOT used by fed specialist

**Applicable Specialists:**

- **fed** (Ridge) — credit risk signal complements Fed Funds and yield curve

**Causal Link to ZL:**

```
HY OAS widening → Credit stress → Risk-off sentiment → Commodities sell-off → ZL price decline
HY OAS compression → Risk-on → Commodity demand optimism → ZL price rise
```

-- Add to fed specialist:
SELECT
date,
value as hy_oas_bps,

-- Z-score (tail risk signal)
(value - AVG(value) OVER (ORDER BY date ROWS BETWEEN 252 PRECEDING AND 1 PRECEDING)) /
NULLIF(STDDEV(value) OVER (ORDER BY date ROWS BETWEEN 252 PRECEDING AND 1 PRECEDING), 0) as hy_oas_z,

-- MoM change (sudden stress)
value - LAG(value, 21) OVER (ORDER BY date) as hy_oas_mom_chg_bps
FROM econ.rates_1d
WHERE series_id = 'BAMLH0A0HYM2';

````

**Integration Requirements:**
- **Update fed specialist config** — add HY OAS as feature
- **Retrain fed specialist** after adding feature

---

### EIA (Energy Information Administration) Sources

#### 1. EIA API v2
**URL:** https://api.eia.gov/v2/
**Status:** 🔴 DOWN (upstream since ~Mar 1, 2026)
**Priority:** P1 (HIGH — energy specialist needs this)

**Issue:** EIA API has been unreliable/down since early March 2026. Biodiesel data stopped updating.

**Applicable Specialists:**
- **energy** (VAR) — crude oil inventory, refinery utilization, petroleum product stocks
- **biofuel** (NLP+EMA) — biodiesel production, feedstock usage, RIN generation

**Fallback Plan:**
```python
# IMMEDIATE: Implement CSV fallback for biodiesel data
# Inngest function: eia-biodiesel-weekly-csv-fallback.ts
# Source: https://www.eia.gov/petroleum/supply/weekly/archive/2026/csv/

# Long-term: Monitor EIA API status page (https://www.eia.gov/opendata/)
# Once API restored, resume API ingestion
````

**Integration Requirements:**

- **CSV scraper:** Parse weekly petroleum supply CSV files
- **Cron:** `0 18 * * 3` (weekly on Wednesday at 6pm UTC — EIA releases Wednesday afternoon)
- **Historical backfill:** Fill gaps from API downtime (Mar 1 - present)

---

#### 2. Weekly Petroleum Supply

**URL:** https://www.eia.gov/petroleum/supply/weekly/  
**Status:** 🔴 NOT BUILT (HTML scrape needed while API down)  
**Priority:** P1 (HIGH)

**Applicable Specialists:**

- **energy** (VAR) — crude inventory changes, refinery runs, product imports/exports

**Causal Link to ZL:**

```
EIA crude inventory surprise → Energy sector sentiment → Biodiesel economics → Soy oil demand → ZL price
Refinery utilization → Distillate demand (heating oil competes with biodiesel) → B100 blending demand → ZL price
```

**Feature Engineering:**

```sql
-- Store in: supply.eia_petroleum_1w
SELECT
  date,
  crude_inventory_mb,

  -- WoW change
  crude_inventory_mb - LAG(crude_inventory_mb, 1) OVER (ORDER BY date) as crude_inv_wow_mb,

  -- Surprise vs consensus
  crude_inv_wow_mb - analyst_consensus_wow as crude_surprise_mb,

  -- Refinery utilization
  refinery_utilization_pct,
  LAG(refinery_utilization_pct, 1) OVER (ORDER BY date) as refinery_util_prev_week
FROM supply.eia_petroleum_1w;
```

**Integration Requirements:**

- **HTML scraper:** Parse weekly tables from https://www.eia.gov/petroleum/supply/weekly/
- **Inngest Function:** `eia-petroleum-weekly-scraper.ts`
- **Cron:** `0 18 * * 3` (weekly on Wednesday)
- **Historical Backfill:** 2010-present

---

#### 3. Biodiesel Monthly/Weekly (CURRENT: STALE/BROKEN)

**Status:** 🔴 BROKEN (0 rows in weekly, stale data in monthly)  
**Priority:** P0 (CRITICAL — biofuel specialist has only 5 signals, needs this)

**Fix Plan:**

1. **Immediate:** Implement CSV fallback (weekly data available at https://www.eia.gov/biofuels/biodiesel/production/)
2. **Monitor EIA API:** Resume API once upstream fixed
3. **Backfill:** Nov 2025 - present

**Integration Requirements:**

- **CSV scraper active** — verify it's working and filling gaps
- **Alert if stale >7 days** — biodiesel data is critical for biofuel specialist

---

### EPA (Environmental Protection Agency) Sources

#### 1. EPA RIN Trades & Prices (CURRENT: WORKING but at source limit)

**URL:** wss://edap.epa.gov/public/app/{app_id}  
**Status:** ⚠️ WORKING (at source limit since Jan 19, 2026)  
**Priority:** P1 (maintain, optimize)

**Applicable Specialists:**

- **biofuel** (NLP+EMA) — D4/D6 RIN prices directly impact biodiesel profit margins
- **energy** (VAR) — RIN prices affect energy sector via petroleum refiners' compliance costs

**Causal Link to ZL:**

```
D4 RIN price spike → Biodiesel profit margin ↑ → Feedstock demand (soy oil) ↑ → ZL price ↑
D4-D6 spread → Advanced biofuel premium → Soy-based biodiesel incentive → ZL demand
```

**Current Issue:** "At source limit" suggests EPA Qlik WebSocket is hitting rate limits or connection quotas.

**Optimization Plan:**

```typescript
// frontend/src/inngest/epa-rins-daily.ts
// REDUCE polling frequency to avoid source limit
// Current: every 4 hours? → Reduce to: daily at 6pm ET (after market close)
// Cron: '0 23 * * *' (daily at 11pm UTC = 6pm ET)

// ALSO: Add caching layer to avoid redundant API calls
```

**Integration Requirements:**

- **Optimize Inngest function** — reduce call frequency
- **Monitor source limit status** — track if still hitting limits after optimization
- **Fallback:** If WebSocket unavailable, scrape https://www.epa.gov/fuels-registration-reporting-and-compliance-help/rin-trades-and-price-information

---

### CFTC (Commodity Futures Trading Commission) Sources

#### 1. CFTC COT Reports (Socrata Legacy, Disaggregated, TFF)

**URLs:**

- https://publicreporting.cftc.gov/resource/6dca-aqww.json (Legacy)
- https://publicreporting.cftc.gov/resource/jun7-fc8e.json (Disaggregated)
- https://publicreporting.cftc.gov/resource/gpe5-46if.json (TFF)

**Status:** 🔴 NOT BUILT (catalog says "V14 code exists" — need to port)  
**Priority:** P0 (CRITICAL — positioning data missing from ALL specialists)

**Applicable Specialists:**

- **tariff** (Tree) — managed money positioning signals speculative sentiment during tariff disputes
- **volatility** (GARCH) — net positioning extremes precede volatility regime shifts
- **trump_effect** (Event Study) — COT positioning spikes correlate with policy announcement reactions
- **crush** (GBM) — commercial hedger positioning signals industry supply/demand expectations
- **china** (GBM) — speculative long interest signals export demand optimism

**Causal Link to ZL:**

```
COT report → Managed money net long >90th percentile → Crowded trade → Reversal risk → ZL price volatility ↑
COT commercial shorts ↑ → Producer hedging (bearish outlook) → ZL price pressure
COT swap dealer positions → OTC market flow signal → Institutional ZL exposure → ZL price trend
```

**Feature Engineering:**

```python
# Inngest function: cftc-cot-weekly.ts (PORT from V14)
# Store in: pos.cftc_1w (NEW table — currently doesn't exist in schema)
# Schema: report_date, contract_code, trader_category, long_positions, short_positions, net_positions, oi_pct

# Contract codes needed:
# - 007601 (Soybean Oil)  # ZL
# - 005602 (Soybeans)     # ZS (for crush specialist)
# - 023651 (Soybean Meal) # ZM (for crush specialist)
# - 067651 (Crude Oil)    # CL (for energy specialist)
# - 023631 (Natural Gas)  # NG (for energy specialist)
# - 1170E1 (VIX)          # For volatility specialist

# SQL features for specialists:
SELECT
  report_date,
  contract_code,

  -- Managed Money positioning
  SUM(CASE WHEN trader_category = 'MANAGED_MONEY' THEN net_positions END) as mm_net_long,
  SUM(CASE WHEN trader_category = 'MANAGED_MONEY' THEN long_positions END) as mm_long,
  SUM(CASE WHEN trader_category = 'MANAGED_MONEY' THEN short_positions END) as mm_short,

  -- Commercial hedgers (opposite signal)
  SUM(CASE WHEN trader_category = 'PRODUCER_MERCHANT' THEN net_positions END) as commercial_net_short,

  -- Swap dealers (institutional flow)
  SUM(CASE WHEN trader_category = 'SWAP_DEALER' THEN net_positions END) as swap_dealer_net,

  -- Positioning percentile (extremes matter)
  PERCENT_RANK() OVER (PARTITION BY contract_code ORDER BY mm_net_long) as mm_net_long_pctile,

  -- WoW change (momentum signal)
  mm_net_long - LAG(mm_net_long, 1) OVER (PARTITION BY contract_code ORDER BY report_date) as mm_net_long_wow,

  -- Crowded trade flag
  CASE WHEN mm_net_long_pctile > 0.90 OR mm_net_long_pctile < 0.10 THEN 1 ELSE 0 END as crowded_trade_flag
FROM pos.cftc_1w
WHERE contract_code IN ('007601', '005602', '023651', '067651', '023631', '1170E1')
GROUP BY report_date, contract_code;
```

**Integration Requirements:**

- **Port V14 code:** Review `/archive/v14/` or git history for CFTC ingestion code
- **Inngest Function:** `cftc-cot-weekly.ts`
- **Cron:** `0 21 * * 5` (weekly on Friday at 9pm UTC — CFTC releases 3:30pm ET Friday)
- **API:** Socrata API (free, no key required, 1000 req/day)
- **Historical Backfill:** 2010-present (~700 weekly reports)
- **New Table:** Add `pos.cftc_1w` to `prisma/schema.prisma`:
  ```prisma
  model cftc_1w {
    id               BigInt   @id @default(autoincrement())
    report_date      DateTime @db.Date
    contract_code    String   @db.VarChar(10)
    trader_category  String   @db.VarChar(50)
    long_positions   Int
    short_positions  Int
    net_positions    Int
    open_interest    Int
    oi_pct           Decimal  @db.Decimal(5,2)
    created_at       DateTime @default(now())

    @@unique([report_date, contract_code, trader_category])
    @@index([report_date])
    @@index([contract_code])
    @@map("cftc_1w")
    @@schema("pos")
  }
  ```

**CRITICAL:** This is the HIGHEST PRIORITY integration. COT data is essential for 5+ specialists and currently completely missing.

---

### BLS (Bureau of Labor Statistics) Sources

#### 1. BLS API v2

**URL:** https://api.bls.gov/publicapi/v2/timeseries  
**Status:** 🔴 NOT BUILT (using FRED proxies: WPU06410132, PCU3116133116132)  
**Priority:** P3 (LOW — FRED covers most needed PPI series)

**Applicable Specialists:**

- **substitutes** (RF) — additional PPI series for competing oils/fats
- **biofuel** (NLP+EMA) — diesel fuel PPI, energy input costs

**Assessment:** FRED already provides key PPI series (tallow, rendering). BLS API would add more granular commodity-level PPI data, but FRED coverage is adequate for current needs.

**Integration Requirements:**

- **DEFER** — P3 priority, only build if FRED proxies insufficient

---

### NOAA (Weather) Sources

#### 1. NCEI Daily Summaries

**URL:** https://www.ncei.noaa.gov/data/daily-summaries/  
**Status:** 🔴 NOT BUILT  
**Priority:** P1 (HIGH — weather affects crop yields, ZL supply expectations)

**Applicable Specialists:**

- **crush** (GBM) — drought in soybean belt signals crop stress → lower yield → tighter crush supply → ZL price
- **china** (GBM) — US crop weather affects export availability to China
- **biofuel** (NLP+EMA) — drought affects corn ethanol economics (RIN spillover)

**Causal Link to ZL:**

```
NOAA drought monitor → Soybean yield forecast ↓ → Harvest size expectations ↓ → ZL supply concern → ZL price ↑
Excessive rainfall → Planting delays → Late season supply → ZL seasonal curve shift
Growing Degree Days below normal → Crop stress → Yield risk → ZL volatility ↑
```

**Feature Engineering:**

```python
# Inngest function: noaa-weather-daily.ts
# Store in: alt.weather_1d (NEW table)
# Schema: date, station_id, region, temp_max, temp_min, precip_in, gdd_base50

# Key stations: Iowa, Illinois, Indiana, Ohio, Minnesota (top 5 soy states)
# Aggregate by region, compute anomalies

# SQL features:
SELECT
  date,
  region,

  -- Temperature anomaly (z-score)
  (AVG(temp_max) - AVG(AVG(temp_max)) OVER (PARTITION BY region, EXTRACT(DOY FROM date) ORDER BY EXTRACT(YEAR FROM date) ROWS BETWEEN 30 PRECEDING AND 1 PRECEDING)) /
    NULLIF(STDDEV(AVG(temp_max)) OVER (PARTITION BY region, EXTRACT(DOY FROM date) ORDER BY EXTRACT(YEAR FROM date) ROWS BETWEEN 30 PRECEDING AND 1 PRECEDING), 0)
    as temp_anomaly_z,

  -- Precipitation anomaly
  (SUM(precip_in) - AVG(SUM(precip_in)) OVER (PARTITION BY region, EXTRACT(MONTH FROM date) ORDER BY EXTRACT(YEAR FROM date) ROWS BETWEEN 5 PRECEDING AND 1 PRECEDING)) /
    NULLIF(STDDEV(SUM(precip_in)) OVER (PARTITION BY region, EXTRACT(MONTH FROM date) ORDER BY EXTRACT(YEAR FROM date) ROWS BETWEEN 5 PRECEDING AND 1 PRECEDING), 0)
    as precip_anomaly_z,

  -- Growing Degree Days (GDD) accumulation for growing season
  SUM(GREATEST(0, (temp_max + temp_min) / 2.0 - 50)) OVER (PARTITION BY region, EXTRACT(YEAR FROM date) ORDER BY date) as gdd_ytd,

  -- Drought flag
  CASE WHEN SUM(precip_in) OVER (PARTITION BY region ORDER BY date ROWS BETWEEN 30 PRECEDING AND CURRENT ROW) <
         AVG(SUM(precip_in)) OVER (PARTITION BY region, EXTRACT(MONTH FROM date) ORDER BY EXTRACT(YEAR FROM date) ROWS BETWEEN 10 PRECEDING AND 1 PRECEDING) * 0.5
    THEN 1 ELSE 0 END as drought_flag
FROM alt.weather_1d
WHERE region IN ('IA', 'IL', 'IN', 'OH', 'MN')  -- Top 5 soy states
GROUP BY date, region, temp_max, temp_min, precip_in;
```

**Integration Requirements:**

- **NOAA API:** Requires free API token from https://www.ncdc.noaa.gov/cdo-web/token
- **Inngest Function:** `noaa-weather-daily.ts`
- **Cron:** `0 10 * * *` (daily at 10am UTC — NOAA data lags by 1-2 days)
- **Stations:** Select 5-10 stations per top soy state (IA, IL, IN, OH, MN)
- **Historical Backfill:** 2010-present (daily data)
- **New Table:** Add `alt.weather_1d` to Prisma schema

---

### White House / USTR / Federal Register Sources

#### 1. White House Briefing Room / Trade Pages

**URLs:**

- https://www.whitehouse.gov/briefing-room/
- https://www.whitehouse.gov/trade/
- https://www.whitehouse.gov/briefing-room/statements-releases/feed/ (RSS)

**Status:** 🔴 NOT BUILT  
**Priority:** P0 (CRITICAL — tariff and trump_effect specialists blind to policy announcements)

**Applicable Specialists:**

- **tariff** (Tree) — tariff announcements, trade negotiations, exemptions
- **trump_effect** (Event Study) — executive ag policy, China mentions, trade tweets/statements
- **biofuel** (NLP+EMA) — biofuel mandate announcements, EPA waivers

**Causal Link to ZL:**

```
WH press release → "China to purchase $X billion in ag products" → Export optimism → ZL price spike
WH briefing → Tariff escalation threat → Trade war risk premium → ZL volatility ↑
WH trade page → Section 301 tariff list update → Soy complex included/excluded → ZL price adjustment
```

**Feature Engineering:**

```python
# Inngest function: whitehouse-rss-scraper-hourly.ts
# Store in: alt.policy_news_1d (NEW table)
# Schema: published_at, title, url, content, sentiment_score, entity_mentions, specialist_tags, event_type

# NLP pipeline (same as USDA newsrooms):
# 1. Scrape RSS hourly
# 2. Extract entities (CHINA, TARIFF, AGRICULTURE, SOYBEANS, BIOFUEL, etc.)
# 3. Sentiment scoring via FinBERT
# 4. Tag by specialist
# 5. Classify event type (TARIFF_ANNOUNCE, TRADE_DEAL, EXECUTIVE_ORDER, etc.)

# SQL features:
SELECT
  published_at::date as date,

  -- Daily policy event count by specialist
  COUNT(*) FILTER (WHERE 'tariff' = ANY(specialist_tags)) as tariff_event_count,
  COUNT(*) FILTER (WHERE 'trump_effect' = ANY(specialist_tags)) as trump_event_count,

  -- Sentiment aggregation
  AVG(sentiment_score) FILTER (WHERE 'tariff' = ANY(specialist_tags)) as tariff_sentiment_avg,

  -- Specific event types
  COUNT(*) FILTER (WHERE event_type = 'TARIFF_ANNOUNCE') as tariff_announce_count,
  COUNT(*) FILTER (WHERE event_type = 'TRADE_DEAL') as trade_deal_count,

  -- Abnormal activity flag
  CASE WHEN COUNT(*) > AVG(COUNT(*)) OVER (ORDER BY published_at::date ROWS BETWEEN 30 PRECEDING AND 1 PRECEDING) * 2
    THEN 1 ELSE 0 END as policy_spike_flag
FROM alt.policy_news_1d
WHERE published_at >= CURRENT_DATE - INTERVAL '5 years'
GROUP BY published_at::date;
```

**Integration Requirements:**

- **Inngest Function:** `whitehouse-rss-scraper-hourly.ts`
- **Cron:** `0 */1 * * *` (hourly — policy announcements are time-sensitive)
- **RSS Feeds:**
  - WH Statements: https://www.whitehouse.gov/briefing-room/statements-releases/feed/
  - WH Presidential Actions: https://www.whitehouse.gov/briefing-room/presidential-actions/feed/
- **NLP:** FinBERT sentiment + named entity recognition (spaCy)
- **Historical Backfill:** 2017-present (Trump admin 1.0 + Biden + Trump 2.0)
- **New Table:** Add `alt.policy_news_1d` to Prisma schema

---

#### 2. USTR Press Office

**URL:** https://ustr.gov/about-us/policy-offices/press-office  
**Status:** 🔴 NOT BUILT  
**Priority:** P1 (HIGH — complements White House tariff coverage)

**Applicable Specialists:**

- **tariff** (Tree) — USTR is primary agency for trade policy implementation
- **trump_effect** (Event Study) — USTR announcements often precede White House statements

**Causal Link to ZL:**

```
USTR notice → Section 301 investigation opened → Tariff risk ↑ → ZL volatility ↑
USTR hearing schedule → Industry feedback on proposed tariffs → Exemption speculation → ZL price
USTR China trade deal text → Agricultural purchase commitments → ZL export demand outlook → ZL price
```

**Integration Requirements:**

- **Scraper:** No RSS available, need HTML scraping of press release list
- **Inngest Function:** `ustr-press-scraper-daily.ts`
- **Cron:** `0 */6 * * *` (every 6 hours)
- **Store in:** Same `alt.policy_news_1d` table as White House (unify policy news)
- **NLP:** Same pipeline as White House

---

#### 3. Federal Register API

**URL:** https://www.federalregister.gov/api/v1/documents.json  
**Status:** 🔴 NOT BUILT  
**Priority:** P1 (HIGH — executive orders and regulations are event-driven ZL movers)

**Applicable Specialists:**

- **tariff** (Tree) — tariff-related regulations, trade remedy investigations
- **biofuel** (NLP+EMA) — EPA biofuel mandate adjustments, RFS waivers
- **trump_effect** (Event Study) — executive orders affecting agriculture/trade

**Causal Link to ZL:**

```
Federal Register → EPA RFS waiver published → Biodiesel demand outlook ↓ → Soy oil demand ↓ → ZL price ↓
Federal Register → USDA export credit program expansion → US competitiveness ↑ → ZL export demand ↑ → ZL price ↑
Federal Register → Executive Order on China investment restrictions → Trade tension ↑ → ZL risk premium
```

**Feature Engineering:**

```python
# Inngest function: federal-register-api-daily.ts
# Store in: alt.policy_news_1d (same table as WH/USTR)
# API endpoint: https://www.federalregister.gov/api/v1/documents.json?conditions[term]=tariff+agriculture

# Query parameters:
# - conditions[term]: "tariff agriculture", "biofuel", "renewable fuel standard", "trade", "USDA", "EPA"
# - conditions[type]: RULE, PRORULE, NOTICE, PRESDOCU
# - per_page: 100
# - page: 1

# SQL features (same as WH/USTR):
SELECT
  publication_date::date as date,
  COUNT(*) FILTER (WHERE document_type = 'RULE' AND 'biofuel' = ANY(specialist_tags)) as biofuel_rule_count,
  COUNT(*) FILTER (WHERE document_type = 'PRESDOCU') as executive_order_count
FROM alt.policy_news_1d
WHERE source = 'FEDERAL_REGISTER'
GROUP BY publication_date::date;
```

**Integration Requirements:**

- **API:** Free, no auth required (https://www.federalregister.gov/developers/api/v1)
- **Inngest Function:** `federal-register-api-daily.ts`
- **Cron:** `0 12 * * *` (daily at 12pm UTC — Fed Register publishes each weekday)
- **Search Terms:** "tariff", "agriculture", "soybean", "biofuel", "renewable fuel standard", "trade", "China"
- **Historical Backfill:** 2017-present
- **Store in:** Existing `alt.policy_news_1d` table (unify all policy news)

---

### Foreign Government Sources

#### 1. CONAB (Brazil Harvests)

**URL:** https://www.conab.gov.br/info-agro/safras  
**Status:** 🔴 NOT BUILT  
**Priority:** P1 (HIGH — Brazil is #1 soybean exporter, competes directly with US)

**Applicable Specialists:**

- **china** (GBM) — Brazil soy exports to China compete with US
- **tariff** (Tree) — Brazil production outlook affects US export competitiveness during tariff disputes
- **substitutes** (RF) — Brazil soy oil production affects global oils balance

**Causal Link to ZL:**

```
CONAB report → Brazil soybean production forecast ↑ → US-Brazil export competition ↑ → ZL export premium ↓ → ZL price ↓
CONAB harvest delay (weather) → Brazil export timing shift → Temporary US export window → ZL price spike
CONAB soy oil crush forecast → Global oils supply outlook → ZL price adjustment
```

**Feature Engineering:**

```python
# Inngest function: conab-harvest-report-monthly.ts
# Store in: supply.conab_harvest_1m (NEW table)
# Schema: report_date, crop_year, commodity, production_mt, area_ha, yield_mt_ha, forecast_month

# Key metrics to extract from Portuguese PDF/HTML:
# - Soja (Soybean) Production (million metric tons)
# - Óleo de Soja (Soybean Oil) Production
# - Farelo de Soja (Soybean Meal) Production

# SQL features:
SELECT
  report_date,
  crop_year,
  commodity,

  -- MoM production forecast revision
  production_mt - LAG(production_mt, 1) OVER (PARTITION BY crop_year, commodity ORDER BY report_date) as mom_revision_mt,

  -- YoY growth
  (production_mt / LAG(production_mt, 12) OVER (PARTITION BY commodity ORDER BY report_date) - 1) * 100 as yoy_growth_pct,

  -- Brazil-US production ratio (requires joining with USDA WASDE)
  production_mt / (SELECT value FROM supply.wasde_1m WHERE country = 'US' AND commodity = 'SOYBEANS' AND metric = 'PRODUCTION' AND report_date = conab_harvest_1m.report_date)
    as brazil_us_production_ratio
FROM supply.conab_harvest_1m
WHERE commodity = 'SOJA';
```

**Integration Requirements:**

- **Source:** Monthly reports at https://www.conab.gov.br/info-agro/safras (Portuguese, PDF)
- **Inngest Function:** `conab-harvest-report-monthly.ts`
- **Cron:** `0 14 10 * *` (monthly on 10th at 2pm UTC — CONAB releases mid-month)
- **Parsing:** Portuguese PDF scraping via pdfplumber + Google Translate API for keywords
- **Historical Backfill:** 2015-present
- **Fallback:** USDA FAS PSD Online (has Brazil data as fallback)
- **New Table:** Add `supply.conab_harvest_1m` to Prisma schema

---

#### 2. MPOB (Malaysia Palm Oil Board) Statistics & Prices (CURRENT: STALE since Dec 2025)

**URLs:**

- http://bepi.mpob.gov.my/index.php/en/statistics/sectoral-status.html
- http://bepi.mpob.gov.my/index.php/en/price/monthly-prices

**Status:** ⚠️ STALE (last update Dec 2025)  
**Priority:** P0 (CRITICAL — palm specialist has NO palm price data for 3 months)

**Applicable Specialists:**

- **palm** (ECM+Ridge) — Malaysian CPO price is PRIMARY palm signal
- **substitutes** (RF) — palm-soy spread drives substitution pressure

**Causal Link to ZL:**

```
MPOB CPO price spike → Palm-soy spread widens → Buyers shift to soybean oil → ZL demand ↑ → ZL price ↑
MPOB production shortfall → Global oils tightness → ZL price support
MPOB export data → Malaysia-Indonesia competition → Palm supply outlook → ZL substitution pressure
```

**Current Issue:** Data stopped updating in Dec 2025. Likely scraper broke or MPOB website structure changed.

**Fix Plan:**

```python
# Diagnose failure:
# 1. Check frontend/src/inngest/mpob-palm-monthly.ts (if exists) — verify scraper still works
# 2. If MPOB site changed, update scraper logic
# 3. Add Slack alert if data stale >14 days

# Fallback options:
# A. Yahoo Finance: CPO futures on Bursa Malaysia (symbol: FCPO)
# B. USDA PSD Online: has Malaysia palm oil production/export data (but not prices)
# C. Palm oil company stock prices as proxy: Sime Darby, IOI Corp (Yahoo Finance)
```

**Integration Requirements:**

- **Immediate:** Diagnose why MPOB scraper stopped, fix or implement Yahoo Finance fallback
- **Backfill:** Dec 2025 - present (3 months missing data)
- **Add monitoring:** Alert if `supply.mpob_palm_1m` has no new rows for >14 days

---

#### 3. China GACC Customs / MOFCOM / CNGOIC

**URLs:**

- http://english.customs.gov.cn/Statics/ (GACC)
- http://43.248.49.97/ (GACC Data Portal)
- http://english.mofcom.gov.cn/ (MOFCOM)
- http://www.cngoic.com/ (China National Grain and Oils Info Center)

**Status:** 🔴 NOT BUILT  
**Priority:** P1 (HIGH — China is #1 soybean importer, direct demand signal)

**Applicable Specialists:**

- **china** (GBM) — China soybean import volumes, crush rates, soy oil stocks
- **tariff** (Tree) — China tariff retaliation announcements
- **trump_effect** (Event Study) — China trade policy responses

**Causal Link to ZL:**

```
GACC monthly import data → China soybean imports from US ↑ → ZL export demand ↑ → ZL price ↑
GACC China soy oil stocks ↓ → China buying pressure ↑ → ZL price support
CNGOIC crush rate forecast → China soy complex demand outlook → ZL export expectations → ZL price
MOFCOM retaliatory tariff announcement → US-China trade tension → ZL export risk → ZL price decline
```

**Integration Requirements:**

- **Challenge:** Chinese gov websites are unreliable for automated scraping, often block foreign IPs
- **Fallback:** USDA FAS China Oilseeds Report (weekly/monthly) has aggregated China import/crush/stocks data
- **Priority:** P1 but DIFFICULT — may need manual data entry or commercial data vendor (Bloomberg, Reuters)
- **Defer until:** Other higher-ROI sources built first

---

#### 4. Panama Canal Operations

**URL:** https://www.pancanal.com/en/daily-canal-operations/  
**Status:** 🔴 NOT BUILT  
**Priority:** P2 (MEDIUM — logistical bottleneck signal, but indirect)

**Applicable Specialists:**

- **crush** (GBM) — canal congestion delays soybean shipments to Asia, affects crush timing
- **china** (GBM) — canal delays disrupt US Gulf→China soybean exports

**Causal Link to ZL:**

```
Panama Canal drought → Ship queue ↑ → Soybean export delays → Temporary supply tightness → ZL price spike
Canal transit fees ↑ → US Gulf export competitiveness ↓ → ZL export premium ↓ → ZL price
```

**Feature Engineering:**

```sql
-- Track daily ship queue, transit times, toll fees
-- Correlate with ZL volatility during drought periods (2023-2024)
```

**Integration Requirements:**

- **Priority:** P2 — build ONLY if crush/china specialists underperform after other enhancements
- **Scraper:** Parse daily operations HTML table
- **Historical value:** 2023-2024 canal drought was market-moving, future relevance uncertain

---

## Under-Utilized Sources — Specialist-by-Specialist

### 1. Crush Specialist (GBM) — Currently 8 signals, target 35+

**MISSING CATALOG SOURCES:**

- ✅ FRED: Livestock futures (LE, HE) for protein demand → **ADD**
- ✅ FAS Export Sales: Soy oil export volumes → **ALREADY EXISTS, UNDER-UTILIZED**
- 🔴 NASS QuickStats: Competing oilseed production (canola, sunflower) → **BUILD**
- 🔴 WASDE: Soybean crush forecast → **BUILD**
- 🔴 EIA Petroleum: Distillate demand (competes with biodiesel) → **BUILD**
- 🔴 NOAA Weather: Soybean belt drought → **BUILD**
- 🔴 Panama Canal: Export logistics bottlenecks → **DEFER (P2)**

---

### 2. China Specialist (GBM) — Currently 6 signals, target 30+

**MISSING CATALOG SOURCES:**

- ✅ FRED: Copper (Dr. Copper proxy for China growth) → **FRED has DHHNGSP but not copper — use Databento HG futures instead**
- ✅ FAS Export Sales: China share of US soy exports → **ALREADY EXISTS, NOT CONSUMED**
- 🔴 FAS GATS: China imports from Brazil vs US → **BUILD**
- 🔴 WASDE: China soybean import forecast → **BUILD**
- 🔴 CONAB: Brazil production (competes for China market) → **BUILD**
- 🔴 China GACC: China soy import volumes → **BUILD (DIFFICULT)**
- 🔴 NOAA Weather: US crop weather (affects export availability) → **BUILD**

---

### 3. Energy Specialist (VAR) — Currently 10 signals, target 35+

**MISSING CATALOG SOURCES:**

- ✅ FRED: HY OAS (credit risk) → **ALREADY INGESTED, NOT USED**
- 🔴 EIA Petroleum: Refinery utilization, distillate stocks → **BUILD**
- 🔴 EPA RINs: D4 RIN prices → **ALREADY EXISTS (at source limit), ENHANCE**
- 🔴 CFTC COT: Crude oil positioning → **BUILD**

---

### 4. FX Specialist (ARDL) — Currently 12 signals, adequate

**WELL-COVERED** — FRED FX series (DEXBZUS, DEXCHUS, DEXMXUS, DTWEXBGS) are sufficient. No urgent catalog gaps.

---

### 5. Fed Specialist (Ridge) — Currently 45 signals, BEST COVERED

**WELL-COVERED** — FRED rates/macro data is excellent. Minor enhancements:

- ✅ FRED HY OAS → **ADD** (already ingested)
- 🔴 FOMC Statements NLP → **BUILD** (Federal Reserve website)

---

### 6. Tariff Specialist (Tree) — Currently 3 signals, target 25+ (🔴 MOST UNDER-COVERED)

**MISSING CATALOG SOURCES:**

- 🔴 CFTC COT: Positioning extremes signal tariff-driven sentiment → **BUILD (P0)**
- 🔴 FAS Export Sales: Country-level trade flow disruptions → **ALREADY EXISTS, NOT CONSUMED**
- 🔴 FAS GATS: Bilateral trade shifts → **BUILD**
- 🔴 White House/USTR: Tariff announcements → **BUILD (P0)**
- 🔴 Federal Register: Tariff regulations → **BUILD**
- 🔴 USDA Newsrooms: Trade policy mentions → **BUILD**
- 🔴 WASDE: Brazil/Argentina production (competitive pressure during tariffs) → **BUILD**

---

### 7. Biofuel Specialist (NLP+EMA) — Currently 5 signals, target 30+

**MISSING CATALOG SOURCES:**

- ⚠️ EIA Biodiesel: Weekly/monthly production → **FIX STALENESS (P0)**
- ⚠️ EPA RINs: D4/D6 prices → **OPTIMIZE (at source limit)**
- 🔴 ERS Biofuels: USDA biofuel forecasts → **BUILD**
- 🔴 Federal Register: EPA RFS waivers → **BUILD**
- 🔴 White House: Biofuel policy announcements → **BUILD**
- ✅ FRED Tallow/Rendering PPI → **ADD** (already ingested, not used)

---

### 8. Palm Specialist (ECM+Ridge) — Currently 8 signals, target 25+

**MISSING CATALOG SOURCES:**

- ⚠️ MPOB: Malaysia CPO prices/production → **FIX STALENESS (P0)**
- 🔴 WASDE: Global palm oil supply/demand → **BUILD**
- 🔴 FAS GATS: Malaysia/Indonesia palm export flows → **BUILD**
- 🔴 Yahoo Finance: Bursa Malaysia palm futures (FCPO) → **BUILD (fallback for MPOB)**

---

### 9. Volatility Specialist (GARCH) — Currently 5 signals, target 30+

**MISSING CATALOG SOURCES:**

- ✅ FRED VIX → **INGESTED but under-utilized in model**
- ✅ FRED STLFSI4 (Financial Stress) → **INGESTED but under-utilized**
- 🔴 CFTC COT: ZL positioning extremes signal reversal risk → **BUILD (P0)**
- 🔴 Federal Register: Policy surprise events → **BUILD**
- 🔴 White House: Event-driven volatility spikes → **BUILD**

---

### 10. Substitutes Specialist (RF) — Currently 4 signals, target 25+ (🔴 2ND MOST UNDER-COVERED)

**MISSING CATALOG SOURCES:**

- ✅ FRED Tallow PPI → **ADD** (already ingested, not used)
- ✅ FRED Rendering PPI → **ADD** (already ingested, not used)
- 🔴 NASS QuickStats: Canola, sunflower, cottonseed production → **BUILD**
- 🔴 WASDE: Competing oils supply/demand → **BUILD**
- 🔴 FAS GATS: Global vegetable oil trade flows → **BUILD**
- 🔴 MPOB: Palm oil (competes with soy oil) → **FIX STALENESS**

---

### 11. Trump_Effect Specialist (Event Study) — Currently 4 signals, target 25+

**MISSING CATALOG SOURCES:**

- 🔴 White House: Executive ag policy, China trade mentions → **BUILD (P0)**
- 🔴 USTR: Trade policy announcements → **BUILD**
- 🔴 Federal Register: Executive orders → **BUILD**
- 🔴 USDA Newsrooms: Policy-driven ag news → **BUILD**
- 🔴 CFTC COT: Positioning reactions to policy events → **BUILD**
- 🔴 FAS Export Sales: Country-level anomalies correlate with policy → **ALREADY EXISTS, NOT CONSUMED**

---

## Integration Priority Matrix

| Priority | Source                                       | Specialists Impacted                           | Urgency              | Difficulty                                  |
| -------- | -------------------------------------------- | ---------------------------------------------- | -------------------- | ------------------------------------------- |
| **P0**   | **CFTC COT** (3 APIs)                        | tariff, volatility, trump_effect, crush, china | 🔥 CRITICAL          | MEDIUM (port V14 code)                      |
| **P0**   | **Fix econ.activity_1d staleness**           | fed, china                                     | 🔥 CRITICAL          | LOW (diagnose Inngest error)                |
| **P0**   | **Fix MPOB palm data staleness**             | palm, substitutes                              | 🔥 CRITICAL          | MEDIUM (scraper repair or Yahoo fallback)   |
| **P0**   | **Fix EIA biodiesel staleness**              | biofuel, energy                                | 🔥 CRITICAL          | LOW (CSV fallback exists)                   |
| **P0**   | **White House RSS scraper**                  | tariff, trump_effect                           | 🔥 CRITICAL          | LOW (RSS is easy)                           |
| **P1**   | **USDA WASDE** (monthly PDF)                 | crush, china, substitutes, tariff, palm        | HIGH                 | MEDIUM (PDF parsing)                        |
| **P1**   | **NASS QuickStats API**                      | crush, china, substitutes, biofuel             | HIGH                 | MEDIUM (API integration)                    |
| **P1**   | **FAS GATS** (global trade)                  | china, palm, substitutes, tariff               | HIGH                 | MEDIUM (API + data volume)                  |
| **P1**   | **USDA Newsrooms** (3 RSS)                   | tariff, trump_effect, biofuel                  | HIGH                 | LOW (RSS scraping)                          |
| **P1**   | **NOAA Weather** (daily)                     | crush, china, biofuel                          | HIGH                 | MEDIUM (API + aggregation logic)            |
| **P1**   | **EIA Petroleum Supply** (weekly)            | energy, biofuel                                | HIGH                 | MEDIUM (HTML scraping)                      |
| **P1**   | **NASS Grain Stocks** (quarterly)            | crush, substitutes                             | HIGH                 | LOW (PDF parsing)                           |
| **P1**   | **Federal Register API**                     | tariff, biofuel, trump_effect                  | HIGH                 | LOW (free API)                              |
| **P1**   | **USTR Press scraper**                       | tariff, trump_effect                           | HIGH                 | MEDIUM (HTML scraping)                      |
| **P1**   | **ERS Biofuels**                             | biofuel, energy                                | HIGH                 | MEDIUM (PDF parsing)                        |
| **P1**   | **CONAB Brazil**                             | china, tariff, substitutes                     | HIGH                 | HARD (Portuguese, PDF)                      |
| **P1**   | **Enhance FAS Export Sales usage**           | china, tariff, trump_effect                    | HIGH                 | LOW (feature engineering only)              |
| **P2**   | **ERS Exchange Rates**                       | fx, china, tariff                              | MEDIUM               | LOW (but FRED covers this)                  |
| **P2**   | **Panama Canal Ops**                         | crush, china                                   | MEDIUM               | MEDIUM (HTML scraping)                      |
| **P3**   | **BLS API**                                  | substitutes, biofuel                           | LOW                  | LOW (but FRED covers this)                  |
| **P3**   | **AMS Grain Truck**                          | crush                                          | LOW                  | MEDIUM (API + noisy data)                   |
| **P3**   | **China Gov Sources** (GACC, MOFCOM, CNGOIC) | china, tariff, trump_effect                    | HIGH (if accessible) | VERY HARD (IP blocks, language, unreliable) |

---

## Implementation Roadmap

### Phase 1 (Weeks 1-2): Critical Data Fixes & COT Integration

**Goal:** Fix stale data, add CFTC COT positioning to 5 specialists

| Task                                                  | Specialists                                    | Success Metric                                 |
| ----------------------------------------------------- | ---------------------------------------------- | ---------------------------------------------- |
| Fix `econ.activity_1d` staleness (29 series)          | fed, china                                     | All 29 series updating daily                   |
| Fix MPOB palm data (scraper repair or Yahoo fallback) | palm, substitutes                              | CPO price data current                         |
| Fix EIA biodiesel (CSV fallback active)               | biofuel, energy                                | Weekly biodiesel data flowing                  |
| Build CFTC COT (3 Socrata APIs + new table)           | tariff, volatility, trump_effect, crush, china | 700+ weekly reports backfilled, weekly updates |
| Add FRED HY OAS to fed specialist                     | fed                                            | Feature in training matrix                     |
| Add FRED Tallow/Rendering PPI to substitutes/biofuel  | substitutes, biofuel                           | Features in training matrices                  |

**Deliverables:**

- 4 stale data sources fixed
- `pos.cftc_1w` table created + 700 weeks backfilled
- COT features added to 5 specialists
- 3 FRED series activated in specialists

---

### Phase 2 (Weeks 3-4): Policy News & USDA Core Data

**Goal:** Add policy event monitoring, WASDE automation, NASS data

| Task                                 | Specialists                             | Success Metric                                |
| ------------------------------------ | --------------------------------------- | --------------------------------------------- |
| White House RSS scraper (3 feeds)    | tariff, trump_effect, biofuel           | Policy news flowing, NLP tagging working      |
| USDA Newsrooms scraper (3 RSS feeds) | tariff, trump_effect, biofuel, china    | Ag policy news classified by specialist       |
| Federal Register API scraper         | tariff, biofuel, trump_effect           | Executive orders + regs captured              |
| USDA WASDE monthly scraper           | crush, china, substitutes, tariff, palm | 120+ monthly reports backfilled, auto-updated |
| NASS QuickStats API                  | crush, china, substitutes, biofuel      | Crop production/yield data flowing            |
| NASS Grain Stocks quarterly          | crush, substitutes                      | Quarterly stocks reports automated            |

**Deliverables:**

- `alt.policy_news_1d` table created
- Policy event features added to 4 specialists
- `supply.wasde_1m` table created + 120 months backfilled
- `supply.nass_crops_1m` table created + 10 years backfilled

---

### Phase 3 (Weeks 5-6): Weather, Trade Flows, Energy Details

**Goal:** Add weather, global trade, refinery data

| Task                              | Specialists                      | Success Metric                                   |
| --------------------------------- | -------------------------------- | ------------------------------------------------ |
| NOAA Weather daily scraper        | crush, china, biofuel            | Drought/GDD features added                       |
| FAS GATS global trade             | china, palm, substitutes, tariff | Brazil-China trade flows captured                |
| EIA Petroleum Supply weekly       | energy, biofuel                  | Refinery utilization, inventory data flowing     |
| ERS Biofuels monthly              | biofuel, energy                  | Biodiesel forecasts automated                    |
| USTR Press scraper                | tariff, trump_effect             | Trade policy announcements captured              |
| Enhance FAS Export Sales features | china, tariff, trump_effect      | China share, diversion ratio, YoY features added |

**Deliverables:**

- `alt.weather_1d` table created + 10 years backfilled
- `supply.gats_trade_1m` table created + 10 years backfilled
- `supply.eia_petroleum_1w` table created + 5 years backfilled
- Weather features added to 3 specialists
- Trade flow features added to 4 specialists

---

### Phase 4 (Weeks 7-8): Foreign Sources & Final Enhancements

**Goal:** Brazil data, palm fallbacks, remaining gaps

| Task                                         | Specialists                | Success Metric                                    |
| -------------------------------------------- | -------------------------- | ------------------------------------------------- |
| CONAB Brazil harvest scraper                 | china, tariff, substitutes | Brazil production forecasts automated             |
| Yahoo Finance palm futures (FCPO) fallback   | palm, substitutes          | Daily CPO price proxy if MPOB fails               |
| Optimize EPA RINs (reduce source limit hits) | biofuel, energy            | Daily RIN prices flowing, no source limit errors  |
| Panama Canal Ops scraper (if needed)         | crush, china               | Daily transit data captured                       |
| Final feature engineering pass               | ALL                        | All catalog sources mapped to specialist features |

**Deliverables:**

- `supply.conab_harvest_1m` table created
- Brazil production features added to 3 specialists
- Palm futures fallback operational
- 100% of P0/P1 catalog sources integrated

---

## Success Metrics

### Coverage Targets (by end of Phase 4)

| Specialist   | Current Signals | Target Signals | Catalog Sources Integrated                                                              |
| ------------ | --------------- | -------------- | --------------------------------------------------------------------------------------- |
| crush        | 8               | 35+            | +12 sources (WASDE, QuickStats, Export Sales, Weather, EIA, COT, Livestock)             |
| china        | 6               | 30+            | +10 sources (Export Sales, GATS, WASDE, CONAB, QuickStats, Weather, COT, Copper)        |
| energy       | 10              | 35+            | +8 sources (EIA Petroleum, EPA RINs, COT, HY OAS, WASDE)                                |
| fx           | 12              | 25+            | ✅ ADEQUATE (FRED covers)                                                               |
| fed          | 45              | 50+            | ✅ EXCELLENT (add HY OAS, FOMC NLP)                                                     |
| tariff       | 3               | 25+            | +9 sources (COT, WH/USTR, Fed Register, Export Sales, GATS, WASDE, USDA News)           |
| biofuel      | 5               | 30+            | +8 sources (EIA fix, EPA optimize, ERS Biofuels, WH/Fed Register, Tallow/Rendering PPI) |
| palm         | 8               | 25+            | +5 sources (MPOB fix, WASDE, GATS, Yahoo FCPO, COT)                                     |
| volatility   | 5               | 30+            | +6 sources (COT, VIX enhance, STLFSI4 enhance, Policy news, ZL OI flow)                 |
| substitutes  | 4               | 25+            | +8 sources (Tallow/Rendering PPI, QuickStats, WASDE, GATS, MPOB, COT)                   |
| trump_effect | 4               | 25+            | +7 sources (WH/USTR, Fed Register, USDA News, COT, Export Sales anomalies)              |

**Aggregate:**

- **Catalog sources integrated:** 20+ new sources (from 70+ available)
- **Specialist signal coverage:** 6 avg → 30+ avg (5x improvement)
- **Specialists with <10 signals:** 6/11 → 0/11
- **Stale data sources:** 4 → 0

### Model Performance Targets

- **Core MAE improvement:** -15% to -20% (from expanded specialist signals)
- **Specialist signal independence:** <0.70 correlation between new features
- **Data freshness:** <3 days average staleness across all sources
- **Integration success rate:** >95% of P0/P1 sources operational by Week 8

---

## Next Steps

1. **Review this analysis** with stakeholders (Kirk, data team)
2. **Prioritize Phase 1 tasks** — assign to engineers
3. **Create Inngest function templates** for each new source (see: [`frontend/src/inngest/`](../frontend/src/inngest/) for patterns)
4. **Update Prisma schema** for new tables (`pos.cftc_1w`, `alt.policy_news_1d`, `supply.wasde_1m`, etc.)
5. **Build monitoring** — alert on staleness, source limit errors, parsing failures
6. **Track progress** — update this doc weekly with integration status
7. **Retrain specialists** after each phase — measure MAE improvement incrementally

---

**Last Updated:** 2026-03-05  
**Next Review:** After Phase 1 completion (Week 2)
