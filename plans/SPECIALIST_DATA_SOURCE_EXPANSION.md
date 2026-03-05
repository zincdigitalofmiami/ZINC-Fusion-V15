# SPECIALIST DATA SOURCE EXPANSION PLAN

**ZINC-FUSION-V15 — Comprehensive Signal Coverage Audit & Implementation Roadmap**

**Document Status:** Draft v1.0  
**Created:** 2026-03-05  
**Last Updated:** 2026-03-05  
**Target:** ZL (Soybean Oil) Forecast Accuracy Improvement

---

## Executive Summary

Current state: All 11 specialists are operating on **thin signal sets** (1-3 primary data sources each). This document provides a comprehensive expansion plan using **ONLY verified available data sources** to achieve thick, robust multi-dimensional signal coverage for each specialist.

**Key Constraint:** No external API assumptions. Work exclusively with:

1. Databento market data (mkt schema)
2. FRED economic series (econ schema, 130+ series confirmed)
3. Yahoo Finance equity/ETF data (via existing pollers)
4. CFTC COT positioning (pos schema)
5. Existing internal tables (supply, alt, analytics schemas)

---

## Verified Data Source Inventory

### 1. Databento Futures (mkt.futures_1d)

**Status:** ✅ ACTIVE  
**Symbols:** CL, HO, RB, NG, GC, SI, HG, ZC, ZS, ZW, ZM, ZL, LE, HE, CT, RS, CPO  
**Fields:** open, high, low, close, volume, vwap, open_interest  
**Cadence:** Daily, 1-day lag  
**Source:** [`frontend/src/inngest/databento-futures-daily.ts`](frontend/src/inngest/databento-futures-daily.ts)

### 2. FRED Economic Data (econ.\* tables)

**Status:** ✅ ACTIVE  
**Tables:**

- `econ.rates_1d` — 40 series (treasuries, yields, FX)
- `econ.activity_1d` — 22 series (GDP, industrial prod, trade, China data)
- `econ.inflation_1d` — 15 series (CPI, PCE, PPI, TIPS)
- `econ.labor_1d` — 5 series (unemployment, payrolls, claims)
- `econ.money_1d` — 6 series (M2, Fed balance sheet, reserves)
- `econ.vol_indices_1d` — 7 series (VIX, OVX, STLFSI4, EPU)
- `econ.commodities_1d` — 35+ series (ag commodities, metals, UCO/tallow proxies)

**Cadence:** Daily, variable lags (1-30 days depending on series)  
**Source:** [`frontend/src/inngest/fred-daily.ts`](frontend/src/inngest/fred-daily.ts)

### 3. Yahoo Finance (mkt schema via yahoofinance.com)

**Status:** ✅ ACTIVE  
**Equity Indices:** SPY, QQQ, DIA, IWM, VIX  
**Sector ETFs:** XLE, XLF, XLK, XLV, XLI, XLU, XLP, XLY, XLB, XLRE  
**Commodity ETFs:** USO, UNG, GLD, SLV, DBA, DBC, CORN, SOYB, WEAT  
**Source:** [`frontend/src/inngest/yahoo-indices-daily.ts`](frontend/src/inngest/yahoo-indices-daily.ts), [`frontend/src/inngest/databento-etf-daily.ts`](frontend/src/inngest/databento-etf-daily.ts)

### 4. CFTC COT Positioning (pos.cftc_1w)

**Status:** ✅ ACTIVE  
**Contracts:** ZL, ZS, ZM, CL  
**Fields:** managed_money_long/short/net, prod_merc_long/short/net, swap_long/short/net, open_interest, net_pct_oi  
**Cadence:** Weekly (Fridays)  
**Source:** [`frontend/src/inngest/cftc-weekly.ts`](frontend/src/inngest/cftc-weekly.ts)

### 5. Internal Computed Tables

**Status:** ✅ ACTIVE

- `analytics.board_crush_1d` — ZL/ZS/ZM crush spread economics
- `supply.epa_rin_1d` — D4/D5/D6 RIN prices
- `supply.eia_biodiesel_1m` — Biodiesel/renewable diesel production
- `supply.mpob_palm_1m` — Malaysia palm oil production/stocks/exports
- `supply.usda_exports_1w` — Weekly export sales by commodity & country
- `supply.usda_wasde_1m` — Monthly WASDE reports
- `alt.weather_1d` — Weather data aggregates (temp, precip, anomalies)
- `alt.econ_news` — Economic news feed (USDA, EIA, Fed, WhiteHouse, etc.)

---

## Current State: Specialist Signal Coverage Matrix

| Specialist       | Model Type  | Current Sources                     | Current Signal Count | Status      |
| ---------------- | ----------- | ----------------------------------- | -------------------- | ----------- |
| **crush**        | GBM         | ZL/ZS/ZM futures, board_crush       | ~8                   | ⚠️ THIN     |
| **china**        | GBM         | ZS futures, HG (copper), USD/CNY    | ~6                   | ⚠️ THIN     |
| **fx**           | ARDL        | FRED FX (10 pairs), DXY             | ~12                  | ⚠️ THIN     |
| **fed**          | Ridge       | FRED rates (40 series), yield curve | ~45                  | ✅ ADEQUATE |
| **tariff**       | Tree        | EPU index, news sentiment           | ~3                   | 🔴 CRITICAL |
| **energy**       | VAR         | CL/HO/RB/NG futures, crack spreads  | ~10                  | ⚠️ THIN     |
| **biofuel**      | NLP+EMA     | EPA RIN prices, EIA biodiesel       | ~5                   | ⚠️ THIN     |
| **palm**         | ECM+Ridge   | CPO futures, MPOB data, MYR/USD     | ~8                   | ⚠️ THIN     |
| **volatility**   | GARCH       | VIX, OVX, STLFSI4                   | ~5                   | 🔴 CRITICAL |
| **substitutes**  | RF          | RS (canola), sunflower FRED         | ~4                   | 🔴 CRITICAL |
| **trump_effect** | Event Study | EPU, WhiteHouse news                | ~4                   | 🔴 CRITICAL |

**Legend:**

- ✅ ADEQUATE: 40+ independent signals
- ⚠️ THIN: 5-15 signals (functional but brittle)
- 🔴 CRITICAL: <5 signals (dangerously thin)

---

## Expansion Plan by Specialist

### 1. CRUSH — Soybean Complex Fundamentals

**Model:** Gradient Boosting Machine (GBM)  
**Priority:** 🔥 P0 (Most important specialist for ZL)  
**Current:** 8 signals  
**Target:** 35+ signals

#### Current Sources

1. `mkt.futures_1d` WHERE symbol IN ('ZL', 'ZS', 'ZM')
2. `analytics.board_crush_1d` — Precomputed crush spread
3. `pos.cftc_1w` WHERE symbol IN ('ZL', 'ZS', 'ZM')

#### Gap Analysis

**Missing dimensions:**

- Cross-commodity substitution pressure (canola, palm, sunflower)
- Energy input costs (NG for processing plants)
- SA competition signals (Argentina, Brazil crush capacity)
- Meal demand proxies (livestock futures LE, HE)
- Export flow dynamics (China vs. ROW)
- Inventory pressure signals
- Weather-driven supply shocks

#### Expansion Plan (Using Available Sources)

**Phase 1: Cross-Commodity Pressure (5 new signals)**

```sql
-- 1. ZL vs Canola spread (RS futures from Databento)
SELECT
  f1.event_date,
  f1.close - f2.close AS zl_canola_spread,
  (f1.close - f2.close) / NULLIF(f2.close, 0) AS zl_canola_ratio
FROM mkt.futures_1d f1
JOIN mkt.futures_1d f2 ON f1.event_date = f2.event_date
WHERE f1.symbol = 'ZL' AND f2.symbol = 'RS'
ORDER BY f1.event_date;

-- 2. ZL vs Palm spread (CPO futures)
SELECT
  f1.event_date,
  f1.close - (f2.close / 22.046) AS zl_cpo_spread_cents_lb,  -- Convert CPO MT to lb
  f1.close / (f2.close / 22.046) AS zl_cpo_ratio
FROM mkt.futures_1d f1
JOIN mkt.futures_1d f2 ON f1.event_date = f2.event_date
WHERE f1.symbol = 'ZL' AND f2.symbol = 'CPO';

-- 3. ZL vs Sunflower (FRED PSUNOUSDM)
SELECT
  f.event_date,
  f.close AS zl_close,
  e.value AS sunflower_usd_mt,
  f.close - (e.value / 22.046 * 100) AS zl_sunflower_spread
FROM mkt.futures_1d f
LEFT JOIN econ.commodities_1d e ON f.event_date = e.event_date
WHERE f.symbol = 'ZL' AND e.series_id = 'PSUNOUSDM';

-- 4. Vegetable oil basket z-score (ZL position vs. substitutes)
WITH oil_prices AS (
  SELECT event_date,
    AVG(CASE WHEN symbol = 'ZL' THEN close END) AS zl,
    AVG(CASE WHEN symbol = 'RS' THEN close END) AS canola,
    AVG(CASE WHEN symbol = 'CPO' THEN close / 22.046 END) AS palm_cents_lb
  FROM mkt.futures_1d
  WHERE symbol IN ('ZL', 'RS', 'CPO')
  GROUP BY event_date
)
SELECT
  event_date,
  zl,
  (zl - AVG(zl) OVER (ORDER BY event_date ROWS BETWEEN 252 PRECEDING AND CURRENT ROW)) /
    NULLIF(STDDEV(zl) OVER (ORDER BY event_date ROWS BETWEEN 252 PRECEDING AND CURRENT ROW), 0) AS zl_zscore,
  (canola + palm_cents_lb) / 2 AS substitute_avg,
  zl - ((canola + palm_cents_lb) / 2) AS zl_vs_substitutes_spread
FROM oil_prices;

-- 5. Cotton (CT) as protein meal demand proxy
SELECT
  event_date,
  close AS cotton_close,
  close / LAG(close, 21) OVER (ORDER BY event_date) - 1 AS cotton_mom_21d
FROM mkt.futures_1d
WHERE symbol = 'CT';
```

**Phase 2: Energy Input Costs (3 new signals)**

```sql
-- 6. Natural gas (NG) for processing plant costs
SELECT
  f1.event_date,
  f1.close AS zl_close,
  f2.close AS ng_close,
  f1.close / NULLIF(f2.close, 0) AS zl_ng_ratio,
  (f1.close - LAG(f1.close, 21) OVER (ORDER BY f1.event_date)) /
    NULLIF(LAG(f1.close, 21) OVER (ORDER BY f1.event_date), 0) AS zl_mom_21d,
  (f2.close - LAG(f2.close, 21) OVER (ORDER BY f2.event_date)) /
    NULLIF(LAG(f2.close, 21) OVER (ORDER BY f2.event_date), 0) AS ng_mom_21d
FROM mkt.futures_1d f1
JOIN mkt.futures_1d f2 ON f1.event_date = f2.event_date
WHERE f1.symbol = 'ZL' AND f2.symbol = 'NG';

-- 7. Electricity proxy (XLU utilities ETF)
SELECT
  event_date,
  close AS xlu_close,
  close / LAG(close, 21) OVER (ORDER BY event_date) - 1 AS utilities_return_21d
FROM mkt.etf_1d
WHERE symbol = 'XLU';

-- 8. Crude oil (CL) for transportation costs
SELECT
  f1.event_date,
  f2.close AS cl_close,
  f2.close / LAG(f2.close, 63) OVER (ORDER BY f2.event_date) - 1 AS cl_return_63d
FROM mkt.futures_1d f1
JOIN mkt.futures_1d f2 ON f1.event_date = f2.event_date
WHERE f1.symbol = 'ZL' AND f2.symbol = 'CL';
```

**Phase 3: Livestock Demand Proxies (4 new signals)**

```sql
-- 9-10. Livestock futures (meal demand)
SELECT
  event_date,
  symbol,
  close,
  close / LAG(close, 21) OVER (PARTITION BY symbol ORDER BY event_date) - 1 AS return_21d,
  (close - AVG(close) OVER (PARTITION BY symbol ORDER BY event_date ROWS BETWEEN 252 PRECEDING AND CURRENT ROW)) /
    NULLIF(STDDEV(close) OVER (PARTITION BY symbol ORDER BY event_date ROWS BETWEEN 252 PRECEDING AND CURRENT ROW), 0) AS zscore_252d
FROM mkt.futures_1d
WHERE symbol IN ('LE', 'HE');  -- Live Cattle, Lean Hogs

-- 11. Protein complex correlation
WITH protein AS (
  SELECT
    event_date,
    MAX(CASE WHEN symbol = 'LE' THEN close END) AS le,
    MAX(CASE WHEN symbol = 'HE' THEN close END) AS he,
    MAX(CASE WHEN symbol = 'ZM' THEN close END) AS zm
  FROM mkt.futures_1d
  WHERE symbol IN ('LE', 'HE', 'ZM')
  GROUP BY event_date
)
SELECT
  event_date,
  le,
  he,
  zm,
  (le + he) / 2 AS livestock_avg,
  CORR(zm, (le + he) / 2) OVER (ORDER BY event_date ROWS BETWEEN 63 PRECEDING AND CURRENT ROW) AS zm_livestock_corr_63d
FROM protein;

-- 12. Corn (ZC) as feed cost input to livestock
SELECT
  f1.event_date,
  f2.close AS zc_close,
  f1.close / NULLIF(f2.close, 0) AS zm_zc_ratio,
  (f2.close - AVG(f2.close) OVER (ORDER BY f2.event_date ROWS BETWEEN 126 PRECEDING AND CURRENT ROW)) /
    NULLIF(STDDEV(f2.close) OVER (ORDER BY f2.event_date ROWS BETWEEN 126 PRECEDING AND CURRENT ROW), 0) AS zc_zscore_126d
FROM mkt.futures_1d f1
JOIN mkt.futures_1d f2 ON f1.event_date = f2.event_date
WHERE f1.symbol = 'ZM' AND f2.symbol = 'ZC';
```

**Phase 4: Export Flow Dynamics (5 new signals)**

```sql
-- 13-15. China export sales from supply.usda_exports_1w
SELECT
  event_date,
  commodity,
  destination_country,
  outstanding_sales_mt,
  accumulated_exports_mt,
  outstanding_sales_mt / NULLIF(LAG(outstanding_sales_mt, 1) OVER (PARTITION BY commodity, destination_country ORDER BY event_date), 0) - 1 AS os_wow_change,
  accumulated_exports_mt - LAG(accumulated_exports_mt, 1) OVER (PARTITION BY commodity, destination_country ORDER BY event_date) AS weekly_shipments
FROM supply.usda_exports_1w
WHERE commodity IN ('SOYBEANS', 'SOYBEAN_OIL', 'SOYBEAN_MEAL')
  AND destination_country IN ('CHINA', 'TOTAL');

-- 16. Dollar strength (DXY) for export competitiveness
SELECT
  event_date,
  value AS dxy,
  (value - AVG(value) OVER (ORDER BY event_date ROWS BETWEEN 63 PRECEDING AND CURRENT ROW)) /
    NULLIF(STDDEV(value) OVER (ORDER BY event_date ROWS BETWEEN 63 PRECEDING AND CURRENT ROW), 0) AS dxy_zscore_63d
FROM econ.rates_1d
WHERE series_id = 'DTWEXBGS';  -- Trade-Weighted Dollar

-- 17. Brazil Real (BRL) for SA competition
SELECT
  event_date,
  value AS usd_brl,
  value / LAG(value, 21) OVER (ORDER BY event_date) - 1 AS brl_devalue_21d
FROM econ.rates_1d
WHERE series_id = 'DEXBZUS';
```

**Phase 5: Volume/OI Flow Signals (5 new signals)**

```sql
-- 18-22. Daily volume and open interest dynamics (NO forward-fill)
WITH oi_volume AS (
  SELECT
    event_date,
    symbol,
    close,
    volume,
    open_interest,
    volume / NULLIF(LAG(volume, 5) OVER (PARTITION BY symbol ORDER BY event_date), 0) AS volume_ratio_5d,
    open_interest - LAG(open_interest, 1) OVER (PARTITION BY symbol ORDER BY event_date) AS oi_delta_1d,
    open_interest - LAG(open_interest, 5) OVER (PARTITION BY symbol ORDER BY event_date) AS oi_delta_5d,
    (close - LAG(close, 1) OVER (PARTITION BY symbol ORDER BY event_date)) AS price_change_1d
  FROM mkt.futures_1d
  WHERE symbol IN ('ZL', 'ZS', 'ZM')
)
SELECT
  event_date,
  symbol,
  volume_ratio_5d,  -- Volume surge indicator
  oi_delta_1d,      -- Daily OI change
  oi_delta_5d,      -- Weekly OI change
  CASE
    WHEN price_change_1d > 0 AND oi_delta_1d > 0 THEN 1  -- Long accumulation
    WHEN price_change_1d > 0 AND oi_delta_1d < 0 THEN 2  -- Short covering
    WHEN price_change_1d < 0 AND oi_delta_1d > 0 THEN 3  -- Short building
    WHEN price_change_1d < 0 AND oi_delta_1d < 0 THEN 4  -- Long liquidation
    ELSE 0
  END AS oi_flow_regime
FROM oi_volume;
```

**Phase 6: Macro/Sentiment Overlays (5 new signals)**

```sql
-- 23. S&P 500 (SPY) risk appetite
SELECT
  event_date,
  close AS spy_close,
  close / LAG(close, 21) OVER (ORDER BY event_date) - 1 AS spy_return_21d,
  (close - AVG(close) OVER (ORDER BY event_date ROWS BETWEEN 63 PRECEDING AND CURRENT ROW)) /
    NULLIF(STDDEV(close) OVER (ORDER BY event_date ROWS BETWEEN 63 PRECEDING AND CURRENT ROW), 0) AS spy_zscore_63d
FROM mkt.etf_1d
WHERE symbol = 'SPY';

-- 24. DBA (agriculture ETF) for sector rotation
SELECT
  event_date,
  close AS dba_close,
  close / LAG(close, 21) OVER (ORDER BY event_date) - 1 AS dba_return_21d
FROM mkt.etf_1d
WHERE symbol = 'DBA';

-- 25. Industrial metals (HG copper) for global demand
SELECT
  event_date,
  close AS hg_close,
  (close - AVG(close) OVER (ORDER BY event_date ROWS BETWEEN 126 PRECEDING AND CURRENT ROW)) /
    NULLIF(STDDEV(close) OVER (ORDER BY event_date ROWS BETWEEN 126 PRECEDING AND CURRENT ROW), 0) AS hg_zscore_126d
FROM mkt.futures_1d
WHERE symbol = 'HG';

-- 26. VIX for risk-off episodes
SELECT
  event_date,
  value AS vix,
  CASE
    WHEN value > 30 THEN 1  -- Crisis
    WHEN value > 20 THEN 0.5  -- Elevated
    ELSE 0  -- Normal
  END AS vix_stress_flag
FROM econ.vol_indices_1d
WHERE series_id = 'VIXCLS';

-- 27. Ag sector ETF basket (XLP, DBA, CORN, SOYB)
WITH ag_basket AS (
  SELECT
    event_date,
    AVG(CASE WHEN symbol IN ('XLP', 'DBA', 'CORN', 'SOYB') THEN close END) AS ag_basket_close
  FROM mkt.etf_1d
  WHERE symbol IN ('XLP', 'DBA', 'CORN', 'SOYB')
  GROUP BY event_date
)
SELECT
  event_date,
  ag_basket_close,
  ag_basket_close / LAG(ag_basket_close, 21) OVER (ORDER BY event_date) - 1 AS ag_basket_return_21d
FROM ag_basket;
```

**Implementation Priority:**

1. Phase 1 (P0): Cross-commodity spreads — immediate ZL substitution pressure
2. Phase 3 (P0): Livestock demand — meal demand drives crush economics
3. Phase 4 (P1): Export flows — China trade is 60%+ of market
4. Phase 2 (P2): Energy costs — processing margin sensitivity
5. Phase 5 (P2): Volume/OI — flow signals for regime detection
6. Phase 6 (P3): Macro overlays — risk-on/risk-off context

**Expected Outcome:** 35+ independent signals, thick coverage across substitution/demand/supply/flow dimensions.

---

### 2. CHINA — Import Demand Dynamics

**Model:** Gradient Boosting Machine (GBM)  
**Priority:** 🔥 P0 (60%+ of global soybean trade)  
**Current:** 6 signals  
**Target:** 30+ signals

#### Current Sources

1. `mkt.futures_1d` WHERE symbol IN ('ZS', 'HG')
2. `econ.rates_1d` WHERE series_id = 'DEXCHUS' (USD/CNY)
3. `supply.usda_exports_1w` WHERE destination_country = 'CHINA'

#### Gap Analysis

**Missing dimensions:**

- Direct China economic indicators (PMI, GDP, industrial production)
- Pork/protein cycle (ASF impact on feed demand)
- China domestic crush margins
- Brazil premium/discount to US (origin competition)
- Port congestion/logistics signals
- State reserve auction activity proxies
- Yuan carry trade dynamics

#### Expansion Plan

**Phase 1: China Macro Indicators (5 new signals)**

```sql
-- 1-3. China FRED economic data
SELECT
  event_date,
  series_id,
  value,
  value / LAG(value, 1) OVER (PARTITION BY series_id ORDER BY event_date) - 1 AS mom_change,
  (value - AVG(value) OVER (PARTITION BY series_id ORDER BY event_date ROWS BETWEEN 252 PRECEDING AND CURRENT ROW)) /
    NULLIF(STDDEV(value) OVER (PARTITION BY series_id ORDER BY event_date ROWS BETWEEN 252 PRECEDING AND CURRENT ROW), 0) AS zscore_252d
FROM econ.activity_1d
WHERE series_id IN (
  'CHNCPIALLMINMEI',      -- China CPI
  'CHNRGDPEXP',           -- China GDP (quarterly)
  'CHNMAINLANDIPIM'       -- China Industrial Production (monthly)
);

-- 4. China PMI from activity_1d (if available)
SELECT
  event_date,
  value AS china_pmi,
  CASE
    WHEN value > 52 THEN 1  -- Expansion
    WHEN value > 50 THEN 0.5  -- Mild expansion
    WHEN value < 48 THEN -1  -- Contraction
    ELSE 0  -- Neutral
  END AS pmi_regime
FROM econ.activity_1d
WHERE series_id = 'china_pmi';  -- Verify this series exists

-- 5. China Trade Policy Uncertainty
SELECT
  event_date,
  value AS china_tpu,
  (value - AVG(value) OVER (ORDER BY event_date ROWS BETWEEN 126 PRECEDING AND CURRENT ROW)) /
    NULLIF(STDDEV(value) OVER (ORDER BY event_date ROWS BETWEEN 126 PRECEDING AND CURRENT ROW), 0) AS tpu_zscore_126d
FROM econ.activity_1d
WHERE series_id = 'CHNMAINLANDTPU';
```

**Phase 2: Copper (Dr. Copper) as China Demand Proxy (4 new signals)**

```sql
-- 6-9. HG copper technical + flow signals
WITH hg_signals AS (
  SELECT
    event_date,
    close AS hg_close,
    volume,
    open_interest,
    close / LAG(close, 5) OVER (ORDER BY event_date) - 1 AS hg_return_5d,
    close / LAG(close, 21) OVER (ORDER BY event_date) - 1 AS hg_return_21d,
    close / LAG(close, 63) OVER (ORDER BY event_date) - 1 AS hg_return_63d,
    (close - AVG(close) OVER (ORDER BY event_date ROWS BETWEEN 126 PRECEDING AND CURRENT ROW)) /
      NULLIF(STDDEV(close) OVER (ORDER BY event_date ROWS BETWEEN 126 PRECEDING AND CURRENT ROW), 0) AS hg_zscore_126d,
    volume / NULLIF(AVG(volume) OVER (ORDER BY event_date ROWS BETWEEN 21 PRECEDING AND CURRENT ROW), 0) AS hg_volume_ratio,
    open_interest - LAG(open_interest, 5) OVER (ORDER BY event_date) AS hg_oi_delta_5d
  FROM mkt.futures_1d
  WHERE symbol = 'HG'
),
zs_prices AS (
  SELECT
    event_date,
    close AS zs_close,
    close / LAG(close, 21) OVER (ORDER BY event_date) - 1 AS zs_return_21d
  FROM mkt.futures_1d
  WHERE symbol = 'ZS'
)
SELECT
  h.event_date,
  h.hg_close,
  h.hg_return_21d,
  h.hg_zscore_126d,
  h.hg_volume_ratio,
  h.hg_oi_delta_5d,
  z.zs_close,
  CORR(h.hg_return_5d, z.zs_return_21d) OVER (ORDER BY h.event_date ROWS BETWEEN 63 PRECEDING AND CURRENT ROW) AS hg_zs_corr_63d
FROM hg_signals h
LEFT JOIN zs_prices z ON h.event_date = z.event_date;
```

**Phase 3: Protein Cycle (Pork Demand) (3 new signals)**

```sql
-- 10-12. Lean hogs (HE) as pork demand proxy
SELECT
  h.event_date,
  h.close AS he_close,
  h.close / LAG(h.close, 21) OVER (ORDER BY h.event_date) - 1 AS he_return_21d,
  (h.close - AVG(h.close) OVER (ORDER BY h.event_date ROWS BETWEEN 252 PRECEDING AND CURRENT ROW)) /
    NULLIF(STDDEV(h.close) OVER (ORDER BY h.event_date ROWS BETWEEN 252 PRECEDING AND CURRENT ROW), 0) AS he_zscore_252d,
  zm.close AS zm_close,
  zm.close / NULLIF(h.close, 0) AS zm_he_ratio  -- Meal/Hog ratio (feed cost to protein value)
FROM mkt.futures_1d h
JOIN mkt.futures_1d zm ON h.event_date = zm.event_date
WHERE h.symbol = 'HE' AND zm.symbol = 'ZM';
```

**Phase 4: Brazil Competition (4 new signals)**

```sql
-- 13-16. BRL devaluation = Brazil competitive advantage
SELECT
  e.event_date,
  e.value AS usd_brl,
  e.value / LAG(e.value, 21) OVER (ORDER BY e.event_date) - 1 AS brl_devalue_21d,
  e.value / LAG(e.value, 63) OVER (ORDER BY e.event_date) - 1 AS brl_devalue_63d,
  (e.value - AVG(e.value) OVER (ORDER BY e.event_date ROWS BETWEEN 252 PRECEDING AND CURRENT ROW)) /
    NULLIF(STDDEV(e.value) OVER (ORDER BY e.event_date ROWS BETWEEN 252 PRECEDING AND CURRENT ROW), 0) AS brl_zscore_252d,
  -- ZS price change vs. BRL devaluation correlation
  f.close AS zs_close,
  CORR(f.close / LAG(f.close, 1) OVER (ORDER BY f.event_date),
       e.value / LAG(e.value, 1) OVER (ORDER BY e.event_date))
    OVER (ORDER BY e.event_date ROWS BETWEEN 63 PRECEDING AND CURRENT ROW) AS zs_brl_corr_63d
FROM econ.rates_1d e
LEFT JOIN mkt.futures_1d f ON e.event_date = f.event_date AND f.symbol = 'ZS'
WHERE e.series_id = 'DEXBZUS';
```

**Phase 5: Export Flow Granularity (5 new signals)**

```sql
-- 17-21. Weekly export sales breakdown
WITH china_exports AS (
  SELECT
    event_date,
    commodity,
    destination_country,
    outstanding_sales_mt,
    accumulated_exports_mt,
    outstanding_sales_mt - LAG(outstanding_sales_mt, 1) OVER (PARTITION BY commodity ORDER BY event_date) AS os_wow_change,
    accumulated_exports_mt - LAG(accumulated_exports_mt, 52) OVER (PARTITION BY commodity ORDER BY event_date) AS exports_yoy_change
  FROM supply.usda_exports_1w
  WHERE destination_country = 'CHINA'
    AND commodity IN ('SOYBEANS', 'SOYBEAN_OIL', 'SOYBEAN_MEAL')
),
total_exports AS (
  SELECT
    event_date,
    commodity,
    outstanding_sales_mt AS total_os,
    accumulated_exports_mt AS total_exports
  FROM supply.usda_exports_1w
  WHERE destination_country = 'TOTAL'
    AND commodity IN ('SOYBEANS', 'SOYBEAN_OIL', 'SOYBEAN_MEAL')
)
SELECT
  c.event_date,
  c.commodity,
  c.outstanding_sales_mt AS china_os,
  c.accumulated_exports_mt AS china_exports,
  c.os_wow_change AS china_os_wow,
  c.exports_yoy_change AS china_exports_yoy,
  t.total_os,
  t.total_exports,
  c.outstanding_sales_mt / NULLIF(t.total_os, 0) AS china_share_of_os,
  c.accumulated_exports_mt / NULLIF(t.total_exports, 0) AS china_share_of_exports
FROM china_exports c
LEFT JOIN total_exports t ON c.event_date = t.event_date AND c.commodity = t.commodity;
```

**Phase 6: Yuan Carry Trade Dynamics (3 new signals)**

```sql
-- 22-24. CNY vs. other EM currencies (carry trade unwinding)
WITH fx_basket AS (
  SELECT
    event_date,
    series_id,
    value,
    value / LAG(value, 21) OVER (PARTITION BY series_id ORDER BY event_date) - 1 AS fx_return_21d
  FROM econ.rates_1d
  WHERE series_id IN ('DEXCHUS', 'DEXBZUS', 'DEXMXUS', 'DEXJPUS')
)
SELECT
  event_date,
  MAX(CASE WHEN series_id = 'DEXCHUS' THEN value END) AS usd_cny,
  MAX(CASE WHEN series_id = 'DEXCHUS' THEN fx_return_21d END) AS cny_return_21d,
  MAX(CASE WHEN series_id = 'DEXBZUS' THEN fx_return_21d END) AS brl_return_21d,
  MAX(CASE WHEN series_id = 'DEXMXUS' THEN fx_return_21d END) AS mxn_return_21d,
  MAX(CASE WHEN series_id = 'DEXJPUS' THEN fx_return_21d END) AS jpy_return_21d,
  -- EM currency stress (avg of BRL/MXN relative to CNY)
  ((MAX(CASE WHEN series_id = 'DEXBZUS' THEN fx_return_21d END) +
    MAX(CASE WHEN series_id = 'DEXMXUS' THEN fx_return_21d END)) / 2) -
   MAX(CASE WHEN series_id = 'DEXCHUS' THEN fx_return_21d END) AS em_vs_cny_stress
FROM fx_basket
GROUP BY event_date;
```

**Implementation Priority:**

1. Phase 1 (P0): China macro — direct economic indicators
2. Phase 2 (P0): Copper signals — Dr. Copper as China demand barometer
3. Phase 4 (P0): Brazil competition — origin arbitrage is critical
4. Phase 5 (P1): Export flow — China purchase patterns
5. Phase 3 (P2): Protein cycle — feed demand linkage
6. Phase 6 (P2): CNY carry — advanced FX dynamics

**Expected Outcome:** 30+ independent signals, thick China demand coverage.

---

### 3. ENERGY — Petroleum Complex Dynamics

**Model:** Vector Autoregression (VAR)  
**Priority:** 🔥 P0 (Biodiesel economics drive 50%+ of ZL demand)  
**Current:** 10 signals  
**Target:** 35+ signals

#### Current Sources

1. `mkt.futures_1d` WHERE symbol IN ('CL', 'HO', 'RB', 'NG')
2. `econ.commodities_1d` WHERE series_id IN ('DCOILWTICO', 'DCOILBRENTEU')
3. `analytics.board_crush_1d` (BOHO spread computed)

#### Gap Analysis

**Missing dimensions:**

- Refinery crack spreads (3-2-1, 5-3-2)
- Heating oil (HO) vs. diesel premium (biodiesel substitution)
- RIN credit integration (D4 biodiesel RINs)
- Natural gas for power generation (renewable diesel electricity)
- Gasoline demand seasonality (summer driving → refinery runs)
- Energy sector rotation (XLE ETF)
- Crude inventory dynamics proxies

#### Expansion Plan

**Phase 1: Refinery Economics (5 new signals)**

```sql
-- 1-2. 3-2-1 Crack Spread (3 barrels crude → 2 RB + 1 HO)
WITH crack_321 AS (
  SELECT
    event_date,
    MAX(CASE WHEN symbol = 'CL' THEN close END) AS cl_close,
    MAX(CASE WHEN symbol = 'RB' THEN close END) AS rb_close,
    MAX(CASE WHEN symbol = 'HO' THEN close END) AS ho_close
  FROM mkt.futures_1d
  WHERE symbol IN ('CL', 'RB', 'HO')
  GROUP BY event_date
)
SELECT
  event_date,
  cl_close,
  rb_close,
  ho_close,
  ((2 * rb_close) + ho_close) / 3 - cl_close AS crack_321_spread,
  (((2 * rb_close) + ho_close) / 3 - cl_close) /
    NULLIF(AVG(((2 * rb_close) + ho_close) / 3 - cl_close) OVER (ORDER BY event_date ROWS BETWEEN 126 PRECEDING AND CURRENT ROW), 0) AS crack_321_ratio
FROM crack_321;

-- 3-4. HO-RB Spread (diesel vs. gasoline premium)
SELECT
  event_date,
  MAX(CASE WHEN symbol = 'HO' THEN close END) AS ho_close,
  MAX(CASE WHEN symbol = 'RB' THEN close END) AS rb_close,
  MAX(CASE WHEN symbol = 'HO' THEN close END) - MAX(CASE WHEN symbol = 'RB' THEN close END) AS ho_rb_spread,
  (MAX(CASE WHEN symbol = 'HO' THEN close END) - MAX(CASE WHEN symbol = 'RB' THEN close END)) /
    NULLIF(STDDEV(MAX(CASE WHEN symbol = 'HO' THEN close END) - MAX(CASE WHEN symbol = 'RB' THEN close END)) OVER (ORDER BY event_date ROWS BETWEEN 252 PRECEDING AND CURRENT ROW), 0) AS ho_rb_zscore
FROM mkt.futures_1d
WHERE symbol IN ('HO', 'RB')
GROUP BY event_date;

-- 5. Brent-WTI Spread (global vs. US crude arb)
SELECT
  event_date,
  MAX(CASE WHEN series_id = 'DCOILBRENTEU' THEN value END) AS brent,
  MAX(CASE WHEN series_id = 'DCOILWTICO' THEN value END) AS wti,
  MAX(CASE WHEN series_id = 'DCOILBRENTEU' THEN value END) - MAX(CASE WHEN series_id = 'DCOILWTICO' THEN value END) AS brent_wti_spread
FROM econ.commodities_1d
WHERE series_id IN ('DCOILBRENTEU', 'DCOILWTICO')
GROUP BY event_date;
```

**Phase 2: Biodiesel Substitution Economics (5 new signals)**

```sql
-- 6-8. BOHO Spread (Soybean Oil - Heating Oil = biodiesel premium)
WITH boho AS (
  SELECT
    f1.event_date,
    f1.close AS zl_close,
    f2.close AS ho_close,
    f1.close - f2.close AS boho_spread,
    (f1.close - f2.close) / NULLIF(f2.close, 0) AS boho_ratio
  FROM mkt.futures_1d f1
  JOIN mkt.futures_1d f2 ON f1.event_date = f2.event_date
  WHERE f1.symbol = 'ZL' AND f2.symbol = 'HO'
)
SELECT
  event_date,
  zl_close,
  ho_close,
  boho_spread,
  boho_ratio,
  (boho_spread - AVG(boho_spread) OVER (ORDER BY event_date ROWS BETWEEN 252 PRECEDING AND CURRENT ROW)) /
    NULLIF(STDDEV(boho_spread) OVER (ORDER BY event_date ROWS BETWEEN 252 PRECEDING AND CURRENT ROW), 0) AS boho_zscore_252d,
  boho_spread / LAG(boho_spread, 21) OVER (ORDER BY event_date) - 1 AS boho_mom_21d,
  PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY boho_spread) OVER (ORDER BY event_date ROWS BETWEEN 252 PRECEDING AND CURRENT ROW) AS boho_median_252d
FROM boho;

-- 9-10. D4 Biodiesel RIN prices (from supply.epa_rin_1d)
SELECT
  event_date,
  rin_type,
  price AS rin_price,
  price / LAG(price, 1) OVER (PARTITION BY rin_type ORDER BY event_date) - 1 AS rin_price_change_daily,
  price / LAG(price, 21) OVER (PARTITION BY rin_type ORDER BY event_date) - 1 AS rin_price_change_21d,
  (price - AVG(price) OVER (PARTITION BY rin_type ORDER BY event_date ROWS BETWEEN 126 PRECEDING AND CURRENT ROW)) /
    NULLIF(STDDEV(price) OVER (PARTITION BY rin_type ORDER BY event_date ROWS BETWEEN 126 PRECEDING AND CURRENT ROW), 0) AS rin_zscore_126d
FROM supply.epa_rin_1d
WHERE rin_type IN ('D4', 'D6');
```

**Phase 3: Natural Gas for Power/Heat (3 new signals)**

```sql
-- 11-13. Natural gas (NG) technical + seasonality
WITH ng_signals AS (
  SELECT
    event_date,
    close AS ng_close,
    volume,
    close / LAG(close, 21) OVER (ORDER BY event_date) - 1 AS ng_return_21d,
    (close - AVG(close) OVER (ORDER BY event_date ROWS BETWEEN 126 PRECEDING AND CURRENT ROW)) /
      NULLIF(STDDEV(close) OVER (ORDER BY event_date ROWS BETWEEN 126 PRECEDING AND CURRENT ROW), 0) AS ng_zscore_126d,
    EXTRACT(MONTH FROM event_date) AS month
  FROM mkt.futures_1d
  WHERE symbol = 'NG'
)
SELECT
  event_date,
  ng_close,
  ng_return_21d,
  ng_zscore_126d,
  month,
  CASE
    WHEN month IN (12, 1, 2) THEN 1  -- Winter demand
    WHEN month IN (6, 7, 8) THEN 0.5  -- Summer AC demand
    ELSE 0
  END AS ng_seasonal_demand,
  AVG(ng_close) OVER (PARTITION BY month ORDER BY event_date ROWS BETWEEN 1260 PRECEDING AND CURRENT ROW) AS ng_seasonal_avg_5y
FROM ng_signals;
```

**Phase 4: Energy Sector Rotation (4 new signals)**

```sql
-- 14-17. XLE Energy Sector ETF + USO/UNG
SELECT
  e.event_date,
  e.close AS xle_close,
  e.close / LAG(e.close, 21) OVER (ORDER BY e.event_date) - 1 AS xle_return_21d,
  (e.close - AVG(e.close) OVER (ORDER BY e.event_date ROWS BETWEEN 63 PRECEDING AND CURRENT ROW)) /
    NULLIF(STDDEV(e.close) OVER (ORDER BY e.event_date ROWS BETWEEN 63 PRECEDING AND CURRENT ROW), 0) AS xle_zscore_63d,
  u.close AS uso_close,
  u.close / LAG(u.close, 21) OVER (ORDER BY u.event_date) - 1 AS uso_return_21d,
  CORR(e.close / LAG(e.close, 1) OVER (ORDER BY e.event_date),
       cl.close / LAG(cl.close, 1) OVER (ORDER BY cl.event_date))
    OVER (ORDER BY e.event_date ROWS BETWEEN 63 PRECEDING AND CURRENT ROW) AS xle_cl_corr_63d
FROM mkt.etf_1d e
LEFT JOIN mkt.etf_1d u ON e.event_date = u.event_date AND u.symbol = 'USO'
LEFT JOIN mkt.futures_1d cl ON e.event_date = cl.event_date AND cl.symbol = 'CL'
WHERE e.symbol = 'XLE';
```

**Phase 5: Gasoline Demand Seasonality (3 new signals)**

```sql
-- 18-20. RB (gasoline) seasonal patterns
WITH rb_seasonal AS (
  SELECT
    event_date,
    close AS rb_close,
    volume,
    EXTRACT(MONTH FROM event_date) AS month,
    EXTRACT(WEEK FROM event_date) AS week_of_year,
    close / LAG(close, 21) OVER (ORDER BY event_date) - 1 AS rb_return_21d
  FROM mkt.futures_1d
  WHERE symbol = 'RB'
)
SELECT
  event_date,
  rb_close,
  rb_return_21d,
  month,
  CASE
    WHEN month IN (5, 6, 7, 8) THEN 1  -- Summer driving season
    ELSE 0
  END AS summer_driving_flag,
  AVG(rb_close) OVER (PARTITION BY week_of_year ORDER BY event_date ROWS BETWEEN 260 PRECEDING AND CURRENT ROW) AS rb_seasonal_avg_5y,
  rb_close / NULLIF(AVG(rb_close) OVER (PARTITION BY week_of_year ORDER BY event_date ROWS BETWEEN 260 PRECEDING AND CURRENT ROW), 0) - 1 AS rb_vs_seasonal_avg
FROM rb_seasonal;
```

**Phase 6: Crude Inventory Proxies (5 new signals)**

```sql
-- 21-25. CL volume/OI flow signals (inventory build/draw proxy)
WITH cl_flow AS (
  SELECT
    event_date,
    close AS cl_close,
    volume,
    open_interest,
    volume / NULLIF(AVG(volume) OVER (ORDER BY event_date ROWS BETWEEN 21 PRECEDING AND CURRENT ROW), 0) AS cl_volume_ratio_21d,
    open_interest - LAG(open_interest, 1) OVER (ORDER BY event_date) AS cl_oi_delta_1d,
    open_interest - LAG(open_interest, 5) OVER (ORDER BY event_date) AS cl_oi_delta_5d,
    (close - LAG(close, 1) OVER (ORDER BY event_date)) AS cl_price_change_1d,
    CASE
      WHEN (close - LAG(close, 1) OVER (ORDER BY event_date)) > 0
           AND (open_interest - LAG(open_interest, 1) OVER (ORDER BY event_date)) > 0 THEN 1  -- Bullish
      WHEN (close - LAG(close, 1) OVER (ORDER BY event_date)) < 0
           AND (open_interest - LAG(open_interest, 1) OVER (ORDER BY event_date)) < 0 THEN -1  -- Bearish
      ELSE 0
    END AS cl_flow_signal
  FROM mkt.futures_1d
  WHERE symbol = 'CL'
)
SELECT
  event_date,
  cl_close,
  cl_volume_ratio_21d,
  cl_oi_delta_1d,
  cl_oi_delta_5d,
  cl_flow_signal,
  SUM(cl_flow_signal) OVER (ORDER BY event_date ROWS BETWEEN 21 PRECEDING AND CURRENT ROW) AS cl_flow_score_21d
FROM cl_flow;
```

**Implementation Priority:**

1. Phase 1 (P0): Refinery economics — crack spreads drive diesel/gasoline
2. Phase 2 (P0): BOHO spread + RINs — biodiesel substitution is core ZL driver
3. Phase 4 (P1): XLE sector rotation — energy sector strength = crude demand
4. Phase 3 (P2): Natural gas — power generation for renewable diesel
5. Phase 5 (P2): Gasoline seasonality — refinery run rates affect HO supply
6. Phase 6 (P3): CL flow signals — inventory dynamics

**Expected Outcome:** 35+ independent signals, thick petroleum complex coverage.

---

## Implementation Roadmap

### Phase 1: Critical Expansions (Weeks 1-2)

- **Crush:** Cross-commodity spreads, livestock demand
- **China:** Copper signals, Brazil competition
- **Energy:** BOHO spread + RINs, refinery cracks

**Target:** +30 signals across top 3 specialists  
**Priority:** P0  
**Impact:** High (60%+ of ZL forecast variance)

### Phase 2: Flow & Positioning (Weeks 3-4)

- **Crush:** Volume/OI flow signals
- **China:** Export flow granularity
- **Energy:** CL inventory proxies

**Target:** +15 signals  
**Priority:** P1  
**Impact:** Medium (regime detection, flow dynamics)

### Phase 3: Macro Overlays (Weeks 5-6)

- **All specialists:** SPY, DBA, VIX overlays
- **Cross-specialist correlation matrices**
- **ETF sector rotation signals**

**Target:** +20 signals  
**Priority:** P2  
**Impact:** Medium (risk-on/risk-off context)

---

## Validation & Testing Protocol

### 1. Data Quality Gates

```sql
-- Check for NULL values
SELECT
  'crush' AS specialist,
  COUNT(*) AS total_rows,
  COUNT(CASE WHEN signal_value IS NULL THEN 1 END) AS null_count,
  COUNT(CASE WHEN signal_value IS NULL THEN 1 END)::float / COUNT(*) AS null_pct
FROM specialist_features.crush_features
WHERE as_of_date >= CURRENT_DATE - INTERVAL '90 days';

-- Check for staleness
SELECT
  specialist,
  MAX(as_of_date) AS latest_date,
  CURRENT_DATE - MAX(as_of_date) AS days_stale
FROM specialist_features.all_specialists
GROUP BY specialist
HAVING CURRENT_DATE - MAX(as_of_date) > 7;

-- Check for forward-fill leakage
SELECT
  specialist,
  signal_name,
  COUNT(DISTINCT as_of_date) AS unique_dates,
  COUNT(*) AS total_rows,
  CASE
    WHEN COUNT(DISTINCT as_of_date) < COUNT(*) * 0.5 THEN 'SUSPECT_FFILL'
    ELSE 'OK'
  END AS ffill_check
FROM specialist_features.all_specialists
WHERE as_of_date >= CURRENT_DATE - INTERVAL '365 days'
GROUP BY specialist, signal_name
HAVING COUNT(DISTINCT as_of_date) < COUNT(*) * 0.5;
```

### 2. Signal Independence Check

```python
import pandas as pd
import numpy as np
from scipy.stats import pearsonr

def check_signal_independence(df: pd.DataFrame, threshold: float = 0.9) -> dict:
    """
    Check for highly correlated signals (potential duplication).

    Args:
        df: DataFrame with signals as columns
        threshold: Correlation threshold for flagging

    Returns:
        dict: Pairs of highly correlated signals
    """
    corr_matrix = df.corr()
    high_corr_pairs = []

    for i in range(len(corr_matrix.columns)):
        for j in range(i + 1, len(corr_matrix.columns)):
            if abs(corr_matrix.iloc[i, j]) > threshold:
                high_corr_pairs.append({
                    'signal_1': corr_matrix.columns[i],
                    'signal_2': corr_matrix.columns[j],
                    'correlation': corr_matrix.iloc[i, j]
                })

    return high_corr_pairs
```

### 3. Model Performance Impact

```python
# Before vs. After signal expansion
# Run ablation test: Core with old signals vs. Core with new signals

from autogluon.timeseries import TimeSeriesPredictor

# Baseline (thin signals)
predictor_baseline = TimeSeriesPredictor.load('models/core_baseline/')
mae_baseline = predictor_baseline.evaluate(test_data)

# Expanded (thick signals)
predictor_expanded = TimeSeriesPredictor.load('models/core_expanded/')
mae_expanded = predictor_expanded.evaluate(test_data)

improvement_pct = (mae_baseline - mae_expanded) / mae_baseline * 100
print(f"MAE improvement: {improvement_pct:.2f}%")
```

---

## Success Metrics

| Metric                       | Baseline | Target | Timeline |
| ---------------------------- | -------- | ------ | -------- |
| Avg signals per specialist   | 6        | 30+    | Week 6   |
| Specialists with <10 signals | 6/11     | 0/11   | Week 4   |
| Core MAE (5d horizon)        | TBD      | -15%   | Week 8   |
| Core MAE (21d horizon)       | TBD      | -20%   | Week 8   |
| Signal staleness (avg days)  | TBD      | <3     | Week 2   |
| Forward-fill contamination   | TBD      | 0%     | Week 1   |

---

## Next Steps

1. **Validate all SQL queries** against actual schema (databento, econ, mkt tables)
2. **Create Inngest functions** for new computed features (one per specialist)
3. **Run backfill** for historical signal generation (2010-present)
4. **Retrain specialists** with expanded signal sets
5. **Retrain Core** with new specialist outputs
6. **A/B test** baseline vs. expanded model performance

---

**Document Owner:** Architect Mode  
**Review Cadence:** Weekly  
**Status:** Draft — Awaiting validation of SQL queries against production schema
