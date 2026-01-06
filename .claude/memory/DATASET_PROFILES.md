# ZINC-FUSION-V15 Dataset Profiles

**Created:** 2026-01-05
**Purpose:** Deep understanding of each dataset's "personality" before ingestion

---

## Dataset Inventory (data/downloads/)

| File | Rows | Date Range | Status | Priority |
|------|------|------------|--------|----------|
| `QDL_CITS_*.csv` | 34,428 | 2013-2025 | **RESEARCHED** | HIGH |
| `WASDE_DATA_*.csv` | 856,035 | 2010-2020 | ✅ INGESTED | - |
| `VIXCLS.csv` | 9,279 | 1990-2025 | ✅ SKIPPED (DB complete) | - |
| `chai_predictions.csv` | 249 | 2024-07 to 2025-07 | **RESEARCHED** | MEDIUM |
| `treasury_10y.csv` | 146 | ~2025 | **RESEARCHED** | LOW |
| `eia_biofuel.csv` | 134 | 2020-2026 | **RESEARCHED** | MEDIUM |
| `import_trade.csv` | 13,761 | 1960-2024 | **RESEARCHED** | LOW |
| `soybean_agricultural.csv` | 55,450 | N/A (agronomic) | **RESEARCHED** | LOW |
| `soybean_agricultural_v2.csv` | 55,450 | N/A (agronomic) | DUPLICATE | - |

---

## 1. CFTC CITS (Commitments of Index Traders Supplemental)

### What It Is
The **Index Traders Supplemental Report** is a CFTC publication that breaks out passive commodity index investors from the traditional COT categories. It exists because:

1. **Problem Identified (2006):** Institutional investors (pension funds, endowments) started buying commodity index exposure for portfolio diversification
2. **Distortion:** These "index traders" were being classified as either:
   - **Commercial** (when swap dealers hedge OTC index swaps)
   - **Noncommercial** (when managed funds hold index positions directly)
3. **Solution:** Create a supplemental report showing "Index Traders" separately

### Key Semantic Difference from COT
| Aspect | Traditional COT | CITS |
|--------|-----------------|------|
| Categories | Commercial / Noncommercial / Nonreportable | + Index Traders |
| Behavioral Model | Hedgers vs. Speculators | + Passive Index Capital |
| Price Responsiveness | High (directional views) | **LOW** (index rebalancing only) |
| Position Bias | Both long and short | **LONG-ONLY** |
| Relevant Markets | All 61+ markets | **12 AG markets ONLY** |

### Why AG Only?
The CFTC determined that for **energy and metals**, swap dealers' index business is too mixed with their other swap dealing to separate cleanly. For **agriculture**, the markets are more "pure" for index tracking.

### Covered Markets (12 Total)
1. CBOT Wheat
2. CBOT Corn
3. CBOT Soybeans
4. CBOT Soybean Oil ✅ **OUR TARGET**
5. CBOT Soybean Meal
6. CBOT Rice
7. KCBT Wheat
8. CME Feeder Cattle
9. CME Live Cattle
10. CME Lean Hogs
11. ICE Cotton No.2
12. ICE Sugar No.11

### Schema Details
```
contract_code     | VARCHAR(10)  | CFTC contract identifier (7601 = Soybean Oil)
type              | VARCHAR(20)  | Always "CITS_ALL"
date              | DATE         | Report date (weekly, Fridays)
market_participation | FLOAT     | Total open interest
non_commercial_longs | FLOAT     | Traditional spec longs
non_commercial_shorts | FLOAT    | Traditional spec shorts
non_commercial_spreads | FLOAT   | Spread positions
commercial_longs  | FLOAT        | Traditional hedger longs
commercial_shorts | FLOAT        | Traditional hedger shorts
total_reportable_longs | FLOAT   | Sum of reported longs
total_reportable_shorts | FLOAT  | Sum of reported shorts
non_reportable_longs | FLOAT     | Small traders (long)
non_reportable_shorts | FLOAT    | Small traders (short)
longs             | FLOAT        | **INDEX TRADER LONGS** ← KEY SIGNAL
shorts            | FLOAT        | **INDEX TRADER SHORTS** ← KEY SIGNAL
```

### Contract Code Mapping
| Code | Market | Symbol |
|------|--------|--------|
| 001602 | Soybeans | ZS |
| 007601 | **Soybean Oil** | **ZL** |
| 001612 | Soybean Meal | ZM |
| 002602 | Corn | ZC |
| 005602 | Wheat | ZW |

### Recommended Table
**`raw.cftc_cits_1w`** (NEW TABLE - separate from COT)

### Feature Engineering Value
- **Passive Flow Proxy:** Index trader net position = demand from diversification mandates
- **Rebalancing Signal:** Changes in index positions often happen on roll dates
- **Non-Directional Capital:** Index positions don't predict price direction BUT they affect liquidity
- **Structural Change Detection:** Rising index allocation = more "long-only" bias in market

### Dashboard Features
- Index Trader Net Position (longs - shorts)
- Index Trader % of Open Interest
- Rolling Change in Index Exposure
- Comparison: Index vs. Commercial vs. Speculative

---

## 2. Treasury 10-Year Note Futures (ZN)

### What It Is
A futures contract on 10-year US Treasury Notes traded on CME/CBOT.

### File Structure
```
Time        | Timestamp of bar
Open        | Opening price (% of par, 32nds)
High        | High price
Low         | Low price  
Last        | Settlement/last price
Change      | Daily change
%Change     | Percent change
Volume      | Contracts traded
Open Int    | Open interest
```

### Key Points
- **Pricing:** Quoted in points and 32nds (113-10 = 113 and 10/32nds)
- **Contract Size:** $100,000 face value
- **Tick Size:** 1/32 of a point = $31.25
- **Delivery:** Physical delivery of Treasury notes
- **Primary Use:** Benchmark for long-term interest rates

### Data Coverage
- File has only 146 rows (~6 months of daily data)
- Date range: October 2025 (future data - projections?)

### Recommendation
**SKIP OR VERIFY** - This data appears to be:
1. Very limited coverage (only ~6 months)
2. Dates are in the future (Oct 2025)
3. We likely have better coverage via Databento already

**Action:** Check `raw.market_futures_1d` for existing ZN coverage before considering ingestion.

### Specialist Routing
If ingested: → **FED specialist** (interest rate sensitivity)

---

## 3. EIA Biofuel Supply/Consumption/Inventories

### What It Is
Data from EIA's **Short-Term Energy Outlook (STEO)** covering:
- U.S. biofuel production
- Consumption
- Inventories
- Forecasts

### File Structure (STEO Export)
This is a **pivot-style** export from EIA's STEO data browser:
```
Row 1: Title row ("4d. U.S. Biofuel Supply...")
Row 2: URL source
Row 3: Timestamp
Row 4: Source attribution
Row 5: Column headers (years 2020-2026)
Rows 6+: Data series (multiple metrics)
```

### Key Metrics Available (from EIA)
| Category | Metrics |
|----------|---------|
| **Ethanol** | Production, consumption, inventories, imports, exports |
| **Biodiesel** | Production, consumption, inventories, imports, exports |
| **Renewable Diesel** | Production, consumption (growing rapidly!) |
| **Other Biofuels** | SAF (Sustainable Aviation Fuel), renewable naphtha |

### Why This Matters for ZL
1. **Biodiesel/Renewable Diesel Use Soybean Oil:** ~35% of US soybean oil goes to biofuels
2. **RFS Mandates:** Renewable Fuel Standard drives demand
3. **Capacity Expansion:** New renewable diesel plants coming online 2024-2026

### Data Quality Issues
- File is **annual frequency** (not useful for daily features)
- Only 7 years (2020-2026)
- Includes forecasts (2025-2026)

### Recommendation
**LOW PRIORITY FOR DIRECT INGESTION**

Better approach:
1. Use **EIA API** for monthly/weekly data
2. Get D4 RIN prices from **EPA RIN trades** (daily)
3. Track **biodiesel plant capacity** announcements

### Specialist Routing
→ **BIOFUEL specialist**

---

## 4. World Bank Import Trade Data

### What It Is
World Bank's **World Development Indicators (WDI)** dataset for:
- Indicator: `NE.IMP.GNFS.ZS`
- Meaning: **Imports of goods and services (% of GDP)**

### File Structure
```
country_code      | ISO 3-letter code (AFG, USA, CHN, etc.)
country_name      | Full country name
region            | Geographic region
sub_region        | Sub-region
intermediate_region | Further subdivision
indicator_code    | NE.IMP.GNFS.ZS (always same)
indicator_name    | "IMPORTACIONES DE BIENES Y SERVICIOS (% DEL PIB)"
year              | Year (1960-2024)
imports_of_goods_and_services | % of GDP
```

### Coverage
- 13,761 rows
- ~200+ countries × ~65 years
- Annual frequency

### Semantic Meaning
This measures **trade openness** - how much of a country's economy depends on imports. Higher % = more trade-dependent.

### Relevance to ZL
**MARGINAL** - This is macro-economic context, not commodity-specific:
- Useful for understanding China/Brazil trade dependency
- Not directly predictive of soybean oil prices

### Recommendation
**LOW PRIORITY** - Consider as supplemental macro context only.

### If Ingested
Table: `raw.worldbank_trade_1y` (annual)
Specialist: → **CHINA** (for China-specific data), **FX** (trade flows)

---

## 5. ChAI Predictions (Commodity Price Forecasts)

### What It Is
Daily **point-in-time forecasts** from a third-party commodity prediction service. Each row represents:
- A **prediction date** (when the forecast was made)
- **Historical prices** (trailing 12 months, labeled M-12 to M-1)
- **Forward predictions** (next 13 months, labeled M0 to M12)
- **Confidence intervals** (30% and 50% bands)

### File Structure (Complex Multi-Index)
```
Unnamed: 0                | Prediction date (YYYY-MM-DD)
M-12 to M-1               | Historical month labels (date strings)
M0 to M12                 | Prediction month labels (date strings)
M-12.1 to M-1.1           | Historical prices (actual values)
M0.1 to M12.1             | Mid predictions (mode)
M0.2 to M12.2             | Lower 50% CI
M0.3 to M12.3             | Upper 50% CI
M0.4 to M12.4             | Lower 30% CI
M0.5 to M12.5             | Upper 30% CI
```

### Coverage
- 249 rows (daily predictions)
- Date range: 2024-07-23 to 2025-07-21
- ~1 year of point-in-time forecasts

### Semantic Value
This is **external forecast benchmark data**:
- Can compare our predictions vs. ChAI
- Provides confidence interval methodology reference
- Shows what "competitors" are predicting

### Commodity Covered
Based on the price levels (43-68 range), this appears to be **soybean oil** (cents/lb) or similar vegetable oil.

### Recommendation
**MEDIUM PRIORITY** - Useful for:
1. Model benchmarking
2. Ensemble diversification
3. Understanding market consensus

### If Ingested
Table: `raw.external_forecasts_1d` or `metadata.chai_predictions`
Schema:
```sql
prediction_date     DATE        -- When forecast was made
target_month        DATE        -- Which month being predicted
price_mid           FLOAT       -- Central prediction
price_lower_50      FLOAT       -- 50% CI lower bound
price_upper_50      FLOAT       -- 50% CI upper bound
price_lower_30      FLOAT       -- 30% CI lower bound
price_upper_30      FLOAT       -- 30% CI upper bound
source              VARCHAR     -- 'chai'
```

---

## 6. Soybean Agronomic Data ⭐ QUANT EDGE

### What It Is
**Experimental agronomic data** from soybean field trials - this is **PHYSICAL REALITY DATA** that precedes market prices!

### Why This Is QUANT GOLD
This is exactly the kind of non-market data that creates edge:
- **Plant stress indicators** → Yield problems BEFORE harvest reports
- **Chlorophyll degradation** → Crop health signals
- **Protein variability** → Meal quality/demand implications
- **Seed weight changes** → Oil content proxy

**The C/S/G codes likely mean:** Cultivar/Stress/Genotype treatments
- Different cultivars under different stress conditions
- This reveals HOW soybeans respond to environmental pressure

### File Structure
```
Parameters         | Treatment code (C1S1G5 = Cultivar1_Stress1_Gene5)
Random             | Replicate (R1, R2, R3)
Plant Height (PH)  | cm - stunted growth = stress
Number of Pods (NP)| count - fewer pods = yield loss
Biological Weight  | grams - total biomass
Sugars (Su)        | g/100g - metabolic stress indicator
RWCL               | Relative water content (0-1) - drought stress!
ChlorophyllA663    | Absorbance - photosynthetic efficiency
Chlorophyllb649    | Absorbance - light harvesting capacity
Protein Percentage | % - meal quality driver
Weight of 300 Seeds| grams - oil content proxy (heavier = more oil)
Leaf Area Index    | m²/m² - canopy health
Seed Yield (SYUA)  | kg/ha - ultimate output
Seeds per Pod (NSP)| count - fill rate
Protein Content    | g/plant - absolute protein
```

### QUANT Features Extractable
1. **Stress Response Profiles:** How do yields drop under water stress? Under heat?
2. **Cultivar Performance:** Which varieties are more resilient?
3. **Quality-Yield Tradeoffs:** High protein often means lower oil content
4. **Chlorophyll Health Index:** Early warning of crop problems

### Coverage
- 55,450 rows
- 35 treatment combinations (cultivar × stress × gene)
- 3 replicates each
- Statistically robust experimental design

### Specialist Routing
→ **CRUSH specialist** (yield/quality affects crush margins)
→ **SUBSTITUTES specialist** (quality variations affect competition)
→ Could create new **AGRONOMY specialist**

### Recommended Table
`raw.agronomic_soybean_trials` or `research.soybean_phenotypes`

### Feature Engineering Ideas
```python
# Stress sensitivity score per cultivar
stress_sensitivity = (yield_under_stress / yield_control) 

# Quality index
quality_score = (protein_pct * 0.4) + (seed_weight * 0.3) + (chlorophyll * 0.3)

# Drought resilience
drought_resilience = rwcl_stressed / rwcl_control
```

### Why Neural Networks Will Love This
- High dimensionality (15 measurements per observation)
- Latent patterns humans won't see
- Cross-correlations between physiological metrics
- Non-linear relationships between stress and yield

---

## Summary: Ingestion Priority Matrix

| Dataset | Priority | Action | Target Table |
|---------|----------|--------|--------------|
| **CFTC CITS** | 🔴 HIGH | CREATE NEW TABLE | `raw.cftc_cits_1w` |
| **Soybean Agronomic** | 🔴 HIGH | QUANT EDGE! | `raw.agronomic_soybean_trials` |
| **WASDE** | ✅ DONE | Already ingested | `raw.usda_wasde_1m` |
| **VIXCLS** | ✅ SKIP | DB already complete | - |
| **ChAI Predictions** | 🟡 MEDIUM | Ingest as benchmark | `metadata.external_forecasts` |
| **EIA Biofuel** | 🟡 MEDIUM | Use API instead | - |
| **Treasury 10Y** | 🟢 LOW | Verify DB coverage | Check `raw.market_futures_1d` |
| **World Bank Trade** | 🟢 LOW | Supplemental only | `raw.worldbank_trade_1y` |

---

## Data Gaps Identified (Need to Source)

### Treasury Yield Curve (CRITICAL for FED Specialist)
Need full yield curve data:
- **DGS2** - 2-Year Treasury Constant Maturity
- **DGS3** - 3-Year Treasury Constant Maturity  
- **DGS5** - 5-Year Treasury Constant Maturity
- **DGS10** - 10-Year Treasury Constant Maturity

**Source:** FRED API (free)
**Table:** Already in `raw.fred_observations_1d` - verify coverage/backfill

### GDP by Major Soybean Countries (CRITICAL for Macro Context)
Need quarterly GDP for:
- **China** - #1 soy importer
- **Brazil** - #1 soy exporter  
- **Argentina** - #3 soy exporter
- **United States** - #2 soy exporter

**FRED Series:**
- `GDP` - US GDP
- `CHNNGDP` - China GDP (or use World Bank)
- Brazil/Argentina - World Bank WDI

**Feature Value:**
- GDP growth → demand trajectory
- Recession signals → crush margin pressure
- Currency-GDP relationships

---

## Next Steps

1. **CITS Ingestion** (Priority 1)
   - Create `raw.cftc_cits_1w` table
   - Build contract_code → symbol mapping
   - Ingest 34,428 rows

2. **ChAI Benchmark Import** (Priority 2)
   - Reshape wide → long format
   - Store point-in-time predictions
   - Enable forecast comparison

3. **EIA Biofuel Enhancement** (Priority 3)
   - Use EIA API for monthly data
   - Focus on biodiesel/renewable diesel production
   - Track capacity utilization

---

*Document created during meticulous dataset research session.*
*Philosophy: "Datasets are like kids - learn their personality before parenting them."*
