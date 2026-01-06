# Complete Database Symbol Audit
**Generated:** 2026-01-05

## Executive Summary

| Table | Identifier Column | Unique Count | Date Range |
|-------|------------------|--------------|------------|
| `raw.market_futures_1d` | symbol | 87 | 1968-2025 |
| `raw.market_futures_1h` | symbol | 84 | 2010-2025 |
| `raw.fx_spot_1d` | pair | 30 | 1971-2025 |
| `raw.fred_observations_1d` | series_id | 157 | 1947-2026 |
| `raw.cftc_cot_1w` | symbol | 24 | 2006-2025 |
| `raw.cftc_cits_1w` | contract_code | 13 | 2013-2025 |
| `raw.yahoo_equity_1d` | symbol | 3 | 2004-2025 |
| `raw.weather_noaa_1d` | station_id | 57 | 2005-2025 |
| `raw.usda_wasde_1m` | commodity/country/metric | 71 | 2010-2025 |
| `raw.usda_export_sales_1w` | commodity/destination | 21 | 2020-2025 |
| `raw.epa_rin_prices_1d` | rin_type | 4 | 2024-2025 |
| `raw.news_articles_1d` | source | 112 | varies |
| `raw.options_futures_1d` | symbol | 14,611 | 2025 |

**Total Raw Tables:** 14
**Total Rows:** ~6.4 million

---

## 1. Futures (raw.market_futures_1d)

87 unique symbols, 418,864 rows

### Core Soybean Complex (Primary Target)
| Symbol | Description | Rows | Date Range |
|--------|-------------|------|------------|
| **ZL** | Soybean Oil | 8,390 | 1970-01-01 to 2025-12-29 |
| **ZS** | Soybeans | 14,565 | 1968-12-05 to 2025-12-29 |
| **ZM** | Soybean Meal | 6,482 | 2000-05-15 to 2025-12-29 |

### Energy Complex
| Symbol | Description | Rows | Date Range |
|--------|-------------|------|------------|
| CL | Crude Oil (WTI) | 7,282 | 2000-08-23 to 2025-12-29 |
| BZ | Brent Crude | 5,332 | 2007-07-30 to 2025-12-29 |
| NG | Natural Gas | 7,277 | 2000-08-30 to 2025-12-29 |
| HO | Heating Oil | 7,271 | 2000-09-01 to 2025-12-29 |
| RB | RBOB Gasoline | 7,232 | 2000-11-01 to 2025-12-29 |

### Grains
| Symbol | Description | Rows | Date Range |
|--------|-------------|------|------------|
| ZC | Corn | 6,485 | 2000-07-17 to 2025-12-29 |
| ZW | Wheat (SRW) | 6,899 | 1999-01-27 to 2025-12-29 |
| KE | KC Wheat (HRW) | 5,466 | 2000-09-21 to 2025-12-29 |
| ZO | Oats | 6,549 | 1999-09-14 to 2025-12-29 |
| ZR | Rice | 6,682 | 1999-09-14 to 2025-12-15 |

### Livestock
| Symbol | Description | Rows | Date Range |
|--------|-------------|------|------------|
| LE | Live Cattle | 6,226 | 2001-03-01 to 2025-12-29 |
| HE | Lean Hogs | 6,293 | 2000-12-15 to 2025-12-29 |
| GF | Feeder Cattle | 6,201 | 2001-04-03 to 2025-12-29 |
| DC | Milk (Class III) | 4,511 | 2010-06-07 to 2025-12-29 |
| DY | Dry Whey | 8,201 | 1990-01-01 to 2025-12-29 |

### Metals
| Symbol | Description | Rows | Date Range |
|--------|-------------|------|------------|
| GC | Gold | 7,269 | 2000-08-30 to 2025-12-29 |
| SI | Silver | 7,271 | 2000-08-30 to 2025-12-29 |
| HG | Copper | 7,273 | 2000-08-30 to 2025-12-29 |
| PL | Platinum | 7,290 | 1997-10-29 to 2025-12-29 |
| PA | Palladium | 7,299 | 1998-09-28 to 2025-12-29 |
| ALI | Aluminum | 1,872 | 2014-05-06 to 2025-12-29 |

### FX Futures (CME)
| Symbol | Description | Rows |
|--------|-------------|------|
| 6E | Euro FX | 7,294 |
| 6J | Japanese Yen | 7,215 |
| 6B | British Pound | 7,208 |
| 6A | Australian Dollar | 7,190 |
| 6C | Canadian Dollar | 7,309 |
| 6S | Swiss Franc | 7,188 |
| 6M | Mexican Peso | 7,014 |
| 6N | New Zealand Dollar | 7,174 |
| 6L | Brazilian Real | 4,165 |
| 6R | Russian Ruble | 3,052 |
| 6Z | South African Rand | 3,987 |

### Equity Index Futures
| Symbol | Description | Rows |
|--------|-------------|------|
| ES | E-mini S&P 500 | 7,291 |
| NQ | E-mini Nasdaq 100 | 7,291 |
| YM | E-mini Dow | 6,881 |
| RTY | E-mini Russell 2000 | 2,631 |
| EMD | E-mini S&P MidCap 400 | 4,799 |

### Interest Rate Futures
| Symbol | Description | Rows |
|--------|-------------|------|
| ZB | 30-Year T-Bond | 7,264 |
| ZN | 10-Year T-Note | 7,259 |
| ZF | 5-Year T-Note | 7,265 |
| ZT | 2-Year T-Note | 7,316 |
| 10Y | 10-Year Micro | 1,346 |
| 30Y | 30-Year Ultra Micro | 776 |
| UB | Ultra T-Bond | 4,777 |
| SR1, SR3 | SOFR | 2,157, 2,127 |

### Crypto
| Symbol | Description | Rows |
|--------|-------------|------|
| BTC | Bitcoin | 2,493 |
| ETH | Ethereum | 1,516 |

### Palm Oil & Other Oils
| Symbol | Description | Rows |
|--------|-------------|------|
| CPO | Crude Palm Oil (BMD) | 3,767 |

---

## 2. FX Spot (raw.fx_spot_1d)

30 unique pairs, 211,752 rows

### Major Pairs (vs USD)
| Pair | Description | Rows | Date Range |
|------|-------------|------|------------|
| EURUSD | Euro/USD | 6,767 | 1999-2025 |
| USDJPY | USD/Yen | 6,515 | 2000-2025 |
| GBPUSD | Pound/USD | 6,515 | 2000-2025 |
| USDCHF | USD/Swiss | 6,515 | 2000-2025 |
| AUDUSD | Aussie/USD | 6,515 | 2000-2025 |
| USDCAD | USD/Canadian | 13,794 | 1971-2025 |
| NZDUSD | Kiwi/USD | 6,515 | 2000-2025 |

### EM & China (Critical for Soy Trade)
| Pair | Description | Rows | Date Range |
|------|-------------|------|------------|
| USDCNY | USD/Yuan | 11,228 | 1981-2025 |
| USDBRL | USD/Brazilian Real | 7,771 | 1995-2025 |

### FRED FX Series (Also in fx_spot_1d)
21 pairs overlap with FRED observations (e.g., DEXCHUS, DEXBZUS, DEXMXUS)

### Dollar Indices
| Pair | Description | Rows |
|------|-------------|------|
| DTWEXBGS | Broad Dollar Index | 5,001 |
| DTWEXAFEGS | AFE Dollar Index | 5,001 |
| DTWEXEMEGS | EME Dollar Index | 5,001 |

---

## 3. FRED Observations (raw.fred_observations_1d)

157 unique series, 491,215 rows

### Categories by Count

#### Interest Rates & Yields (23 series)
- DFF, FEDFUNDS, SOFR, DPRIME
- DGS1, DGS2, DGS5, DGS7, DGS10, DGS20, DGS30
- DGS1MO, DGS3MO, DGS6MO
- T10Y2Y, T10Y3M, T10YIE
- DFEDTARL, DFEDTARU
- MORTGAGE30US

#### FX Rates (21 series)
- DEXBZUS, DEXCHUS, DEXCAUS, DEXMXUS, etc.
- DTWEXBGS (Broad), DTWEXAFEGS (AFE), DTWEXEMEGS (EME)
- DXY

#### Energy & Oil (11 series)
- DCOILWTICO (WTI), DCOILBRENTEU (Brent)
- DHHNGSP (Henry Hub Nat Gas)
- DHOILNYH, DJFUELUSGULF, DDFUELUSGULF, DGASUSGULF
- GASDESW, GASREGW

#### Volatility (5 series)
- VIXCLS (VIX) - 9,092 rows from 1990
- OVXCLS (Oil VIX) - 501 rows from 2023
- VXGSCLS (Gold VIX) - 1,256 rows from 2020

#### Macro/Inflation (15+ series)
- CPIAUCSL, CPILFESL, PCEPI, PCEPILFE
- GDP, GDPC1, UNRATE, PAYEMS
- INDPRO, PCE, UMCSENT

#### Financial Conditions (5 series)
- NFCI, STLFSI, STLFSI4
- BAMLC0A0CM, BAMLH0A0HYM2

#### Commodities (12 series)
- PSOYBUSDM (Soybeans global price)
- PMAIZMTUSDM (Corn)
- PCOPPUSDM (Copper)
- PPOILUSDM, PROILUSDM, PSOILUSDM
- PBARLUSDM, PWHEAMTUSDM
- PRICENPQUSDM, PSUNOUSDM

#### Trump/Trade Policy (7 series)
- USEPUINDXD, USEPUINDXM (Policy Uncertainty)
- EPUTRADE (Trade Policy Uncertainty)
- EMVTRADEPOLEMV (Equity Vol: Trade Policy)
- CHNMAINLANDTPU (China Trade Policy)
- B235RC1Q027SBEA (Customs Duties)
- IMPCH (Imports from China)

#### China Macro (5 series)
- CHNCPIALLMINMEI (China CPI)
- CHNGDPNQDSMEI (China GDP)
- IR3TIB01CNM156N (China 3M Interbank)
- XTEXVA01CNM667S, XTIMVA01CNM667S (China Trade)

#### EIA Biofuel (8 series - limited data)
- EIA_BIODIESEL_PRODUCTION
- EIA_ETHANOL_*
- EIA_RENEWABLE_DIESEL_*

#### Historical Agriculture (8 series - NASS)
- CORN_*, SOYBEAN_* (pre-2018 only)

#### Crisis Indicators (9 series)
- CRISIS_* (synthetic/derived, 2017-2025)

---

## 4. CFTC COT (raw.cftc_cot_1w)

24 unique symbols, 18,355 rows

| Symbol | Name | Rows | Date Range |
|--------|------|------|------------|
| ZL | Soybean Oil | 1,020 | 2006-06-13 to 2025-12-23 |
| ZS | Soybeans | 1,020 | 2006-06-13 to 2025-12-23 |
| ZM | Soybean Meal | 1,020 | 2006-06-13 to 2025-12-23 |
| ZC | Corn | 1,020 | 2006-06-13 to 2025-12-23 |
| ZW | Wheat | 1,020 | 2006-06-13 to 2025-12-23 |
| KE | KC Wheat | 1,020 | 2006-06-13 to 2025-12-23 |
| CL | Crude Oil | 1,020 | 2006-06-13 to 2025-12-23 |
| NG | Natural Gas | 1,020 | 2006-06-13 to 2025-12-23 |
| HO | Heating Oil | 1,020 | 2006-06-13 to 2025-12-23 |
| GC | Gold | 1,020 | 2006-06-13 to 2025-12-23 |
| SI | Silver | 1,020 | 2006-06-13 to 2025-12-23 |
| HG | Copper | 1,020 | 2006-06-13 to 2025-12-23 |
| PA | Palladium | 1,020 | 2006-06-13 to 2025-12-23 |
| PL | Platinum | 308 | 2020-01-07 to 2025-11-25 |
| LE | Live Cattle | 1,020 | 2006-06-13 to 2025-12-23 |
| HE | Lean Hogs | 1,020 | 2006-06-13 to 2025-12-23 |
| GF | Feeder Cattle | 1,020 | 2006-06-13 to 2025-12-23 |
| MWE | Minneapolis Wheat | 1,020 | 2006-06-13 to 2025-12-23 |
| CC | Cocoa | 51 | 2025-01-07 to 2025-12-23 |
| CT | Cotton | 51 | 2025-01-07 to 2025-12-23 |
| KC | Coffee | 51 | 2025-01-07 to 2025-12-23 |
| SB | Sugar | 51 | 2025-01-07 to 2025-12-23 |
| ZO | Oats | 195 | 2020-01-07 to 2025-11-25 |
| ZR | Rice | 308 | 2020-01-07 to 2025-11-25 |

**Note:** 4 COT symbols not in futures table: CC, CT, KC, MWE

---

## 5. CFTC CITS (raw.cftc_cits_1w)

13 unique contract codes × 4 report types = 52 combos, 34,428 rows

| Contract Code | Name | Per Type Rows |
|---------------|------|---------------|
| 1602 | Soybeans | 663 |
| 1612 | Soybean Oil | 663 |
| 2602 | Soybean Meal | 663 |
| 5602 | Corn | 663 |
| 7601 | Wheat-SRW | 663 |
| 26603 | Wheat-HRW | 651 |
| 33661 | Cotton | 663 |
| 54642 | WTI Crude | 663 |
| 57642 | NG Natural Gas | 663 |
| 61641 | Sugar #11 | 663 |
| 73732 | RBOB Gasoline | 663 |
| 80732 | Heating Oil | 663 |
| 83731 | Coffee C | 663 |

**Date Range:** 2013-01-08 to 2025-09-16

---

## 6. Yahoo Equity (raw.yahoo_equity_1d)

3 symbols (Trump Effect proxies), 9,534 rows

| Symbol | Description | Rows | Date Range |
|--------|-------------|------|------------|
| DJT | Trump Media | 1,068 | 2021-09-30 to 2025-12-31 |
| FXI | iShares China Large Cap | 5,342 | 2004-10-08 to 2025-12-31 |
| KWEB | KraneShares China Internet | 3,124 | 2013-08-01 to 2025-12-31 |

---

## 7. Weather (raw.weather_noaa_1d)

57 unique stations, 215,320 rows

### Sources
- **GHCND:AR*** - Argentina stations (13)
- **GHCND:BR*** - Brazil stations (12)
- **OM_*** - OpenMeteo US Midwest (14) - soy belt coverage
- **OPENMETEO:*** - South America regions (14)

### US Soy Belt Coverage (OM_)
- IA: Cedar Rapids, Des Moines, Sioux City
- IL: Champaign, Peoria, Springfield
- IN: Fort Wayne, Indianapolis
- MN: Minneapolis, Rochester
- MO: Kansas City, St. Louis
- NE: Lincoln, Omaha

---

## 8. USDA WASDE (raw.usda_wasde_1m)

71 unique commodity/country/metric combos, 10,164 rows

### Commodities
- Soybeans
- Soybean Oil
- Soybean Meal

### Countries
- United States
- Brazil
- Argentina
- China
- World

### Metrics
- production, consumption, exports, imports, ending_stocks

**Date Range:** 2010-08 to 2025-12

---

## 9. USDA Export Sales (raw.usda_export_sales_1w)

21 unique commodity/destination combos, 6,412 rows

### Commodities
- Soybeans, Soybean Oil, Soybean Meal

### Destinations
- China, Mexico, Japan, Indonesia, European Union, TOTAL, Unknown

**Date Range:** 2020-01-02 to 2025-12-11

---

## 10. EPA RIN Prices (raw.epa_rin_prices_1d)

4 RIN types, 208 rows

| Type | Description | Rows | Date Range |
|------|-------------|------|------------|
| D3 | Cellulosic | 52 | 2024-12-23 to 2025-12-15 |
| D4 | Biomass-based Diesel | 52 | 2024-12-23 to 2025-12-15 |
| D5 | Advanced Biofuel | 52 | 2024-12-23 to 2025-12-15 |
| D6 | Renewable Fuel | 52 | 2024-12-23 to 2025-12-15 |

**Note:** Very limited history - only ~1 year

---

## 11. News Articles (raw.news_articles_1d)

112 unique sources, 5,264 rows

### Key Sources
- Twitter accounts: 81 sources (~3,500+ rows)
- farm_policy_news: 263 rows (2016-2025)
- scmp_china: 291 rows
- thehill_politics: 273 rows
- biofuels_digest: 32 rows
- Various USDA/government feeds

---

## 12. Options (raw.options_futures_1d)

14,611 unique option symbols, 28,648 rows
**Date Range:** 2025 only (recent)

Primarily ES (E-mini S&P 500) options with strikes/expirations

---

## 13. Hourly Futures (raw.market_futures_1h)

84 unique symbols, 4,967,276 rows
**Date Range:** 2010-06-07 to 2025-12-15

Key symbols same as daily but higher granularity.

---

## Cross-Table Analysis

### Symbol Collisions

**FX Duplicates:** 21 pairs appear in BOTH `fx_spot_1d` AND `fred_observations_1d`
- DEXBZUS, DEXCHUS, DEXCAUS, DEXMXUS, etc.
- These should be deduplicated in metadata layer

**Futures Daily vs Hourly:**
- In 1d only: BDRY, DX, DXY, GE, GVZ, RS, SB, SBLK
- In 1h only: CJ, CU, KT, SIL, YO

**COT vs Futures:**
- COT symbols missing from futures: CC, CT, KC, MWE
- These need backfill in futures table

---

## Recommended Canonical Instrument Taxonomy

### Asset Classes
1. **EQUITY_INDEX** - ES, NQ, YM, RTY
2. **COMMODITY_GRAIN** - ZC, ZW, KE, ZO, ZR
3. **COMMODITY_OILSEED** - ZS, ZL, ZM
4. **COMMODITY_ENERGY** - CL, BZ, NG, HO, RB
5. **COMMODITY_METAL** - GC, SI, HG, PA, PL, ALI
6. **COMMODITY_LIVESTOCK** - LE, HE, GF, DC, DY
7. **COMMODITY_SOFT** - CC, CT, KC, SB
8. **COMMODITY_VEGOIL** - CPO (palm)
9. **FX_MAJOR** - EURUSD, USDJPY, GBPUSD, etc.
10. **FX_EM** - USDCNY, USDBRL, USDMXN
11. **INTEREST_RATE** - ZB, ZN, ZF, ZT, SR1, SR3
12. **CRYPTO** - BTC, ETH
13. **VOLATILITY** - VIX, OVX, GVZ

### Sources Registry
1. **DATABENTO** - Futures OHLCV (primary)
2. **FRED** - Macro, rates, FX
3. **CFTC** - COT, CITS positioning
4. **YAHOO** - Equities
5. **USDA** - WASDE, Export Sales
6. **NOAA/OPENMETEO** - Weather
7. **EPA** - RIN prices
8. **QUANDL** - Historical backfill (if needed)

---

## Next Steps for Option A+ Migration

1. **Create metadata schema** with:
   - `metadata.instrument` (canonical ID, asset_class, description)
   - `metadata.source` (vendor registry)
   - `metadata.instrument_alias` (vendor→canonical mapping)

2. **Populate instrument master** from this audit (~350 unique instruments)

3. **Add columns** to all raw tables:
   - `instrument_id` (FK to metadata.instrument)
   - `source_id` (FK to metadata.source)

4. **Backfill FKs** from existing symbol/series_id columns

5. **Add UNIQUE constraints** where missing:
   - `raw.fx_spot_1d` - needs (pair, as_of_date)
   - `raw.market_futures_1d` - needs (symbol, as_of_date)
   - `raw.market_futures_1h` - needs (symbol, ts_event)

6. **Create domain views** for Option C grouping (e.g., `views.energy_prices`)
