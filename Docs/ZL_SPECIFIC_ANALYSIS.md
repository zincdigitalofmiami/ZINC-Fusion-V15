NOTE: Production is the dashboard/frontend, not the repo root.
# ZL Soybean Oil Futures - Specific Data Quality Analysis

**Generated:** 2026-01-02
**Purpose:** Deep dive into data sources most relevant to ZL futures price prediction

---

## Executive Summary

The ZINC-FUSION-V15 database contains **high-quality historical data** for ZL (Soybean Oil) futures forecasting with:
- ✅ **6,521 daily records** of ZL futures prices (2000-2025)
- ✅ **118 FRED economic series** with 100% coverage
- ✅ **1,020 weekly COT reports** for ZL positioning data
- ✅ **57 weather stations** across key growing regions (US, Argentina, Brazil)
- ⚠️ **Weather data is 13 days stale** - requires refresh

---

## 1. Core ZL Price Data

### Market Futures Coverage
- **Symbol:** ZL (Soybean Oil)
- **Records:** 6,521 daily observations
- **Date Range:** March 15, 2000 → December 29, 2025
- **Coverage:** 25+ years of continuous data
- **Data Quality:** 0% null values across all OHLCV fields
- **Freshness:** 4 days behind (last update: 2025-12-29)

### Related Commodity Coverage
Critical for cross-asset analysis and feature engineering:

| Symbol | Description | Records | Coverage | Relevance to ZL |
|--------|-------------|---------|----------|-----------------|
| **ZS** | Soybean Futures | 6,472 | 2000-2025 | **CRITICAL** - Primary input for soybean oil |
| **ZM** | Soybean Meal | 6,482 | 2000-2025 | **HIGH** - Crush spread dynamics |
| ZC | Corn | 6,482 | 2000-2025 | MEDIUM - Competing crop for acreage |
| ZW | Wheat | 6,492 | 2000-2025 | MEDIUM - Crop rotation effects |
| CPO | Palm Oil | 3,767 | 2010-2025 | **HIGH** - Substitute vegetable oil |
| CL | Crude Oil | 7,277 | 2000-2025 | MEDIUM - Diesel costs, biodiesel demand |
| HO | Heating Oil | 7,271 | 2000-2025 | MEDIUM - Biodiesel blending |
| NG | Natural Gas | 7,272 | 2000-2025 | LOW - Processing energy costs |

**Key Insight:** Excellent coverage of soy complex (ZS, ZL, ZM) enables sophisticated crush spread modeling.

---

## 2. FRED Economic Indicators

### Overall FRED Coverage
- **Total Series:** 118 unique economic indicators
- **Total Records:** 437,930 observations
- **Coverage Quality:** ALL series have 100% non-null coverage
- **Freshness:** 2 days behind (excellent)

### Critical FRED Series for ZL Forecasting

#### Agriculture & Commodities
| Series ID | Description | Frequency | Relevance |
|-----------|-------------|-----------|-----------|
| DCOILBRENTEU | Brent Crude Oil | Daily | Energy costs, biodiesel demand |
| DCOILWTICO | WTI Crude Oil | Daily | US diesel/biodiesel pricing |
| APU000074714 | CPI: Fats and Oils | Monthly | Direct soybean oil price inflation |

#### Currency & Trade
| Series ID | Description | Frequency | Relevance |
|-----------|-------------|-----------|-----------|
| DEXBZUS | Brazil Real / USD | Daily | **CRITICAL** - Brazil is largest soybean exporter |
| DEXMXUS | Mexican Peso / USD | Daily | Mexico biodiesel demand |
| DEXCHUS | Chinese Yuan / USD | Daily | **CRITICAL** - China is largest soybean importer |
| DEXINUS | Indian Rupee / USD | Daily | India edible oil demand |
| DEXCAUS | Canadian Dollar / USD | Daily | Canada biodiesel/canola oil |

#### Macro Indicators
| Series ID | Description | Frequency | Relevance |
|-----------|-------------|-----------|-----------|
| CPIAUCSL | Consumer Price Index | Monthly | General inflation |
| CPILFESL | Core CPI | Monthly | Underlying inflation trends |
| CHNCPIALLMINMEI | China CPI | Monthly | Chinese consumer demand |
| BOPGSTB | US Trade Balance | Quarterly | Export competitiveness |

#### Financial Conditions
| Series ID | Description | Frequency | Relevance |
|-----------|-------------|-----------|-----------|
| BAMLH0A0HYM2 | High Yield Credit Spread | Daily | Risk appetite, hedging activity |
| BAMLC0A0CM | Corporate Bond Yield | Daily | Financing costs for processors |

**Key Insight:** Currency pairs (especially DEXBZUS, DEXCHUS) are critical for modeling international supply/demand dynamics.

---

## 3. CFTC Commitment of Traders (COT)

### ZL-Specific COT Data
- **Records:** 1,020 weekly reports (2006-2025)
- **Date Range:** June 13, 2006 → December 23, 2025
- **Coverage:** 19+ years of positioning data
- **Freshness:** 10 days behind (acceptable for weekly data)
- **Data Quality:** 0% null values for key fields

### Available COT Metrics
- ✅ Open Interest
- ✅ Managed Money Long/Short positions
- ✅ Producer/Merchant Net positions
- ✅ Swap Dealer positions
- ✅ Non-Reportable positions

### Related COT Coverage
| Symbol | Description | Records | Use Case |
|--------|-------------|---------|----------|
| **ZS** | Soybean COT | 1,020 | Soy complex positioning |
| **ZM** | Meal COT | 1,020 | Crush spread positioning |
| CL | Crude Oil COT | 1,020 | Energy sector sentiment |
| GC | Gold COT | 1,020 | Safe-haven/inflation hedge flows |

**Key Insight:** COT data captures speculative vs commercial positioning, useful for regime detection and sentiment indicators.

---

## 4. Weather Data Coverage

### Overall Weather Metrics
- **Total Stations:** 57
- **Total Records:** 215,320 observations
- **Date Range:** 2005-2025
- **Freshness:** ⚠️ **13 days stale** - NEEDS REFRESH

### Geographic Coverage by Region

#### United States (Primary Producer)
| Region | Stations | Records | Coverage | Status |
|--------|----------|---------|----------|--------|
| US_IA (Iowa) | 3 | 22,977 | 2005-2025 | ✅ GOOD |
| US_IL (Illinois) | 3 | 22,977 | 2005-2025 | ✅ GOOD |
| US_IN (Indiana) | 2 | 15,318 | 2005-2025 | ✅ GOOD |
| US_MN (Minnesota) | 2 | 15,318 | 2005-2025 | ✅ GOOD |
| US_MO (Missouri) | 2 | 15,318 | 2005-2025 | ✅ GOOD |
| US_NE (Nebraska) | 2 | 15,318 | 2005-2025 | ✅ GOOD |

**US Corn Belt Coverage:** EXCELLENT - All major soybean producing states covered.

#### Brazil (Largest Exporter)
| Region | Stations | Records | Coverage | Status |
|--------|----------|---------|----------|--------|
| BR_MT (Mato Grosso) | 2 | 441 | 2024-2025 | ⚠️ LIMITED |
| BR_RS (Rio Grande do Sul) | 2 | 7,537 | 2005-2025 | ✅ GOOD |
| BR_PR (Paraná) | 4 | 7,868 | 2005-2025 | ✅ GOOD |
| BR_MG (Minas Gerais) | 2 | 7,537 | 2005-2025 | ✅ GOOD |
| BR_MS (Mato Grosso do Sul) | 1 | 230 | 2024-2025 | ⚠️ LIMITED |
| BR_SP (São Paulo) | 3 | 696 | 2024-2025 | ⚠️ LIMITED |
| BR_PA (Pará) | 2 | 7,537 | 2005-2025 | ✅ GOOD |
| BR_NE (Northeast) | 1 | 145 | 2024-2025 | ⚠️ LIMITED |

**Brazil Coverage:** MIXED - Good historical data for traditional regions (RS, PR), limited data for expanding frontier regions (MT, MS, SP).

#### Argentina (Third Largest Exporter)
| Region | Stations | Records | Coverage | Status |
|--------|----------|---------|----------|--------|
| AR_BA (Buenos Aires) | 5 | 8,234 | 2005-2025 | ✅ EXCELLENT |
| AR_SF (Santa Fe) | 2 | 7,482 | 2005-2024 | ✅ GOOD |
| AR_CO (Córdoba) | 3 | 7,628 | 2005-2025 | ✅ GOOD |
| AR_ER (Entre Ríos) | 2 | 7,715 | 2005-2025 | ✅ GOOD |
| AR_CH (Chaco) | 3 | 7,718 | 2005-2025 | ✅ GOOD |
| AR_SE (Santiago del Estero) | 2 | 7,447 | 2005-2025 | ✅ GOOD |
| AR_CR (Corrientes) | 2 | 7,538 | 2005-2025 | ✅ GOOD |

**Argentina Coverage:** EXCELLENT - Comprehensive coverage of Pampas region.

### Weather Variables Available
| Variable | Null % | Status | Use Case |
|----------|--------|--------|----------|
| tavg_c | 0.0% | ✅ EXCELLENT | Growing degree days, stress periods |
| tmax_c | 1.96% | ✅ EXCELLENT | Heat stress events |
| tmin_c | 1.47% | ✅ EXCELLENT | Frost risk |
| prcp_mm | 2.23% | ✅ EXCELLENT | Drought monitoring, planting delays |
| awnd_ms | 100.0% | ❌ MISSING | Wind damage (not critical) |
| rhav_pct | 100.0% | ❌ MISSING | Humidity for disease pressure |

**Key Insight:** Temperature and precipitation data are excellent. Missing humidity/wind data is not critical for yield modeling.

---

## 5. USDA Fundamental Data

### Export Sales (Weekly)
- **Records:** 9,544 weekly reports
- **Date Range:** 2000-2025
- **Freshness:** 22 days stale (⚠️ needs update)
- **Commodities Tracked:** Multiple (check includes soybeans, soybean oil)

### WASDE (Monthly)
- **Records:** 18,660 monthly reports
- **Date Range:** 2000-2025
- **Freshness:** 21 days acceptable (monthly frequency)
- **Content:** Supply/demand balance sheets, yield forecasts

**Key Insight:** USDA data provides fundamental supply/demand context. Export sales data is stale and should be refreshed.

---

## Data Quality Summary

### Strengths ✅
1. **Exceptional ZL price history** - 25+ years, no gaps, no nulls
2. **Complete soy complex** (ZS, ZL, ZM) enables crush spread analysis
3. **118 FRED series** with 100% coverage and daily updates
4. **Strong COT coverage** for positioning/sentiment
5. **Excellent US weather coverage** for domestic supply forecasting
6. **Good Argentina weather** for South American competition

### Weaknesses ⚠️
1. **Weather data 13 days stale** - impacts near-term forecasts
2. **Brazil weather gaps** - limited coverage in MT, MS (expanding regions)
3. **USDA Export Sales 22 days old** - stale fundamental data
4. **Missing humidity/wind data** - secondary importance
5. **No palm oil fundamentals** - CPO prices available but not USDA-style reports

### Data Gaps Identified
1. Date gaps in 30Y, 2YY, 5YY futures (not critical for ZL)
2. Historical gaps in FRED data pre-1920 (not relevant)
3. Limited recent coverage for some Brazil regions

---

## Recommendations for ZL Forecasting

### Immediate Actions
1. ✅ **Refresh weather data** - Priority #1 (13 days behind)
2. ✅ **Update USDA export sales** - Priority #2 (22 days behind)
3. ✅ **Verify market futures refresh** - Currently 4 days behind

### Data Enrichment Opportunities
1. **Add palm oil supply data** - Malaysia/Indonesia production reports
2. **Expand Brazil weather** - More stations in MT, MS (frontier regions)
3. **Add biodiesel mandate data** - US RFS, Brazil RenovaBio, EU RED II
4. **Enhance USDA data** - Crop progress reports, soil moisture
5. **Add shipping data** - Freight rates (BDRY available, leverage this)

### Feature Engineering Priorities
1. **Soy crush spread** = (ZL + ZM) - ZS - processing margin
2. **Export competitiveness** = (DEXBZUS × Brazil FOB) - (US Gulf)
3. **Weather stress indices** - GDD, drought severity scores
4. **COT positioning ratios** - Spec/Commercial net positioning
5. **Currency-adjusted basis** - Local currency pricing for export demand

### Model Architecture Considerations
Given data quality:
- ✅ **Daily frequency models** - Data supports it
- ✅ **Multi-horizon forecasting** - 1d, 7d, 30d, 90d all viable
- ✅ **Regime detection** - COT + volatility for market state classification
- ✅ **Cross-asset features** - Strong ZS/ZM/CPO coverage enables this
- ⚠️ **Weather ML models** - Good for US, limited for Brazil expansion zones

---

## Data Quality Score

| Data Source | Coverage | Freshness | Quality | ZL Relevance | Overall |
|-------------|----------|-----------|---------|--------------|---------|
| ZL Futures | ★★★★★ | ★★★★☆ | ★★★★★ | ★★★★★ | **4.8/5.0** |
| Soy Complex (ZS/ZM) | ★★★★★ | ★★★★☆ | ★★★★★ | ★★★★★ | **4.8/5.0** |
| FRED Economic | ★★★★★ | ★★★★★ | ★★★★★ | ★★★★☆ | **4.7/5.0** |
| CFTC COT | ★★★★★ | ★★★★☆ | ★★★★★ | ★★★★☆ | **4.5/5.0** |
| US Weather | ★★★★★ | ★★★☆☆ | ★★★★☆ | ★★★★★ | **4.2/5.0** |
| Brazil Weather | ★★★☆☆ | ★★★☆☆ | ★★★★☆ | ★★★★☆ | **3.5/5.0** |
| Argentina Weather | ★★★★★ | ★★★☆☆ | ★★★★☆ | ★★★☆☆ | **3.8/5.0** |
| USDA Reports | ★★★★☆ | ★★☆☆☆ | ★★★★☆ | ★★★★☆ | **3.5/5.0** |

**Overall Data Quality: 4.3/5.0** - EXCELLENT foundation for ZL forecasting

---

*Report generated 2026-01-02 for ZINC-FUSION-V15 ZL Procurement Forecasting*