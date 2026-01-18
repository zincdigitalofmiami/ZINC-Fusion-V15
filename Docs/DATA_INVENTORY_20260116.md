# ZINC-FUSION Data Inventory

**Generated**: January 16, 2026  
**Purpose**: Complete inventory of all data sources, pending downloads, and database state

---

## 📊 Executive Summary

| Category | Status | Count |
|----------|--------|-------|
| **Futures Symbols in DB** | ✅ | 104 symbols |
| **Total Futures Rows** | ✅ | ~450K+ rows |
| **FRED Economic Series** | ✅ | 25+ series |
| **News Articles** | ✅ | 3,318 articles |
| **Barchart CSV Files** | 📦 Pending Ingest | 21 files (~12MB) |
| **Database Tables** | ✅ | 153 tables |

---

## 🗄️ DATABASE INVENTORY

### Futures Market Data (`raw.market_futures_1d`)

#### ✅ EXCELLENT COVERAGE (25+ years)
| Symbol | Rows | Earliest | Latest | Years | Description |
|--------|------|----------|--------|-------|-------------|
| **ZL** | 8,398 | 1970-01-01 | 2026-01-09 | 56 | Soybean Oil ⭐ PRIMARY TARGET |
| **ZS** | 14,573 | 1968-12-05 | 2026-01-09 | 58 | Soybeans |
| **VX** | 9,278 | 1990-01-02 | 2025-07-24 | 35 | VIX Futures |
| **DY** | 8,201 | 1990-01-01 | 2025-12-29 | 36 | Soybean Oil (alt) |

#### ✅ GOOD COVERAGE (20+ years)
| Symbol | Rows | Earliest | Latest | Years | Description |
|--------|------|----------|--------|-------|-------------|
| ZM | 6,490 | 2000-05-15 | 2026-01-09 | 26 | Soybean Meal |
| ZC | 6,493 | 2000-07-17 | 2026-01-09 | 26 | Corn |
| ZW | 6,907 | 1999-01-27 | 2026-01-09 | 27 | Wheat |
| ZO | 6,549 | 1999-09-14 | 2025-12-29 | 26 | Oats |
| ZR | 6,682 | 1999-09-14 | 2025-12-15 | 26 | Rice |
| KE | 5,466 | 2000-09-21 | 2025-12-29 | 25 | KC Wheat |
| CL | 7,290 | 2000-08-23 | 2026-01-09 | 26 | Crude Oil |
| NG | 7,285 | 2000-08-30 | 2026-01-09 | 26 | Natural Gas |
| HO | 7,278 | 2000-09-01 | 2026-01-08 | 26 | Heating Oil |
| RB | 7,239 | 2000-11-01 | 2026-01-08 | 26 | RBOB Gasoline |
| GC | 7,277 | 2000-08-30 | 2026-01-09 | 26 | Gold |
| SI | 7,279 | 2000-08-30 | 2026-01-09 | 26 | Silver |
| HG | 7,281 | 2000-08-30 | 2026-01-09 | 26 | Copper |
| PL | 7,290 | 1997-10-29 | 2025-12-29 | 28 | Platinum |
| PA | 7,299 | 1998-09-28 | 2025-12-29 | 27 | Palladium |
| ES | 7,298 | 2000-09-18 | 2026-01-08 | 26 | E-mini S&P 500 |
| NQ | 7,298 | 2000-09-18 | 2026-01-08 | 26 | E-mini Nasdaq |
| YM | 6,888 | 2002-04-05 | 2026-01-08 | 24 | E-mini Dow |
| ZB | 7,264 | 2000-09-21 | 2025-12-29 | 25 | 30Y Treasury |
| ZN | 7,259 | 2000-09-21 | 2025-12-29 | 25 | 10Y Treasury |
| ZF | 7,265 | 2000-09-21 | 2025-12-29 | 25 | 5Y Treasury |
| ZT | 7,316 | 2000-06-02 | 2025-12-29 | 26 | 2Y Treasury |
| LE | 6,226 | 2001-03-01 | 2025-12-29 | 25 | Live Cattle |
| HE | 6,293 | 2000-12-15 | 2025-12-29 | 25 | Lean Hogs |
| GF | 6,201 | 2001-04-03 | 2025-12-29 | 25 | Feeder Cattle |
| BZ | 5,332 | 2007-07-30 | 2025-12-29 | 18 | Brent Crude |
| DX | 6,795 | 1999-03-18 | 2025-07-18 | 26 | Dollar Index |

#### ✅ FX Futures (CME)
| Symbol | Rows | Years | Description |
|--------|------|-------|-------------|
| 6E | 7,294 | 25 | Euro |
| 6B | 7,208 | 25 | British Pound |
| 6J | 7,215 | 25 | Japanese Yen |
| 6C | 7,309 | 26 | Canadian Dollar |
| 6A | 7,190 | 25 | Australian Dollar |
| 6S | 7,188 | 25 | Swiss Franc |
| 6M | 7,014 | 25 | Mexican Peso |
| 6N | 7,174 | 25 | New Zealand Dollar |

#### ⚠️ NEEDS ATTENTION (Stale/Short)
| Symbol | Rows | Issue | Action Needed |
|--------|------|-------|---------------|
| DX | 6,795 | Ends 2025-07-18 | 🔴 6 months stale - INGESTING |
| VX | 9,278 | Ends 2025-07-24 | 🔴 6 months stale - INGESTING |
| GVZ | 2,590 | Ends 2025-07-18 | ⚠️ Gold VIX stale |
| CC | 7 | Only 1 week | 🔴 INGESTING from Barchart |
| CT | 7 | Only 1 week | 🔴 INGESTING from Barchart |
| KC | 7 | Only 1 week | 🔴 INGESTING from Barchart |

#### 📈 Mini/Micro Contracts
| Symbol | Rows | Years | Description |
|--------|------|-------|-------------|
| MES | 2,065 | 7 | Micro E-mini S&P |
| MNQ | 2,065 | 7 | Micro E-mini Nasdaq |
| MYM | 2,064 | 7 | Micro E-mini Dow |
| M2K | 2,065 | 7 | Micro E-mini Russell |
| QM | 4,813 | 16 | E-mini Crude |
| QG | 4,813 | 16 | E-mini Nat Gas |
| MGC | 4,700 | 15 | Micro Gold |

---

### FRED Economic Data (`raw.fred_observations_1d`)

| Series ID | Observations | Description |
|-----------|--------------|-------------|
| DFF | 26,132 | Fed Funds Rate |
| DGS10 | 15,997 | 10Y Treasury Yield |
| USEPUINDXD | 14,993 | Economic Policy Uncertainty |
| DEXMAUS | 13,995 | USD/MYR Exchange |
| DEXCAUS | 13,803 | USD/CAD Exchange |
| DEXJPUS | 13,795 | USD/JPY Exchange |
| DEXINUS | 13,289 | USD/INR Exchange |
| DGS2 | 12,405 | 2Y Treasury Yield |
| T10Y2Y | 12,405 | 10Y-2Y Spread |
| DEXCHUS | 11,421 | USD/CNY Exchange |
| T10Y3M | 11,014 | 10Y-3M Spread |
| DCOILWTICO | 10,076 | WTI Crude Price |
| DCOILBRENTEU | 9,806 | Brent Crude Price |
| VIXCLS | 9,105 | VIX Close |
| DEXMXUS | 8,065 | USD/MXN Exchange |
| DEXBZUS | 8,005 | USD/BRL Exchange |
| DHHNGSP | 7,285 | Henry Hub Nat Gas |
| BAMLH0A0HYM2 | 6,800 | High Yield Spread |
| BAMLC0A0CM | 6,799 | Corporate Bond Spread |
| DEXUSEU | 6,780 | USD/EUR Exchange |
| DXY | 6,609 | Dollar Index |
| DPRIME | 6,568 | Prime Rate |
| NASDAQCOM | 6,536 | Nasdaq Composite |

---

### News & Sentiment (`raw.news_articles_event`)

| Metric | Value |
|--------|-------|
| **Total Articles** | 3,318 |
| **Date Range** | 2017-05-08 → 2026-01-16 |
| **Sources** | Barchart RSS (with FinBERT sentiment) |
| **Sentiment Scoring** | FinBERT (-1 to +1) |
| **Specialist Tags** | Big 11 keyword matching |

---

## 📦 BARCHART DOWNLOADS (Pending Ingestion)

### Files in `data/Barchart/` (21 files, ~12MB total)

| File | Size | Symbols | Status |
|------|------|---------|--------|
| `1980+ CC, KC, CT, SB, OJ, LBR...` | 537KB | Softs | 📦 Ready |
| `1980+ CL, HO, RB, NG...` | 1.1MB | Energy | 📦 Ready |
| `1980+ CL, NG, HO, RB, GC, SI, ZC, ZM, ZW...` | 1.1MB | Mixed backfill | 📦 Ready |
| `1980+ CPO, RS, GC...` | 462KB | Palm/Canola/Gold | 📦 Ready |
| `1980+ DX, CT, CC, KC, SB, CPO, RS...` | 1.4MB | FX + Softs | 📦 Ready |
| `1980+ ES, NQ, YM, MES...` | 627KB | Indices | 📦 Ready |
| `1980+ HG, GC, SI, PL, PA...` | 103KB | Metals | 📦 Ready |
| `1980+ LE, HE, GF...` | 1.3MB | Livestock | 📦 Ready |
| `1980+ ZB, ZN, ZF, ZT...` | 634KB | Rates | 📦 Ready |
| `1980+ ZC, ZW, ZO, ZR, KE...` | 157KB | Grains | 📦 Ready |
| `1980+ ZL, ZM, ZC, ZW, CT...` | 101KB | Soy complex | 📦 Ready |
| `1980+ vx, dx...` | 574KB | VIX + Dollar | 📦 Ready |
| `FXI, DJT, KWEB...` | 577KB | Trump/China ETFs | 📦 Ready |
| Plus 8 more files... | ~4MB | Various | 📦 Ready |

**Total Pending**: ~180,000+ rows of historical data

---

## 🔥 OPTIONS FLOW & ANALYTICS (Future Integration)

### Barchart Options Screens (API Access Tomorrow)

| Screen | URL | Data Available |
|--------|-----|----------------|
| **Unusual Options Activity** | `/options/unusual-activity/indices` | Volume spikes, V/OI ratio |
| **IV Rank & Percentile** | `/options/iv-rank-percentile/high` | IV vs 52-week range |
| **Highest IV** | `/options/highest-implied-volatility` | Current IV levels |
| **Options Flow** | `/options/options-flow/etfs` | Large blocks, sweeps |
| **Options News** | `/news/options-news` | Activity alerts |

### Key ETFs for Options Flow Monitoring

| Category | Symbols | Specialist |
|----------|---------|------------|
| **Ag/Soy** | SOYB, CORN, WEAT, DBA, MOO, JJG | crush, substitutes |
| **Energy** | USO, XLE, XOP, OIH, UNG | energy, biofuel |
| **China/EM** | FXI, KWEB, EEM, MCHI, YINN | china, tariff |
| **Volatility** | VXX, UVXY, SVXY, VIXY | volatility |
| **Rates/FX** | UUP, TLT, TBT, IEF, HYG | fx, fed |

### Options Data Tables (Existing)
- `raw.options_futures_1d` - Futures options
- `raw.options_equity_1d` - ETF/equity options
- `training.options_features` - Derived features (24 columns)
- `training.options_greeks` - Greeks calculations (25 columns)
- `training.volatility_surface` - IV surface data

---

## 🎯 SPECIALIST DATA COVERAGE

### Big 11 Specialists - Data Readiness

| Specialist | Primary Data | Status | Gaps |
|------------|--------------|--------|------|
| **crush** | ZL, ZS, ZM | ✅ Excellent (50+ years) | None |
| **china** | FXI, KWEB, 6L, DEXCHUS | ⚠️ ETFs short | Need more CNH depth |
| **fx** | DX, 6E, 6B, 6J, 6C, 6A | ✅ Good (25+ years) | DX stale - fixing |
| **fed** | ZB, ZN, ZF, ZT, DFF, DGS10 | ✅ Excellent | None |
| **tariff** | DJT, EPU (FRED) | ⚠️ DJT short | FRED EPU good |
| **energy** | CL, NG, HO, RB, BZ | ✅ Excellent (25+ years) | None |
| **biofuel** | HO, RB, ZC, SB | ✅ Good | SB shorter |
| **palm** | CPO, RS | ⚠️ Starts 2010 | Backfill coming |
| **volatility** | VX, VIXCLS, GVZ | ⚠️ VX/GVZ stale | Fixing today |
| **substitutes** | CC, KC, CT, SB, OJ | 🔴 Mostly broken | Ingesting today |
| **trump_effect** | DJT, FXI, KWEB, EPU | ⚠️ Mixed | ETFs downloading |

---

## 📋 PENDING ACTIONS

### Immediate (Today)
- [ ] Ingest all Barchart CSV files to `raw.market_futures_1d`
- [ ] Fix DX (6 months stale)
- [ ] Fix VX (6 months stale)
- [ ] Backfill CC, KC, CT, SB, OJ, LBR (softs - broken)
- [ ] Backfill CPO, RS (palm/canola depth)

### Tomorrow (API Key)
- [ ] Set up Barchart API ingestion pipeline
- [ ] Configure options flow data ingestion
- [ ] Set up IV rank/percentile tracking
- [ ] Build unusual activity monitoring

### Training Ready After Ingestion
- [ ] Core model (ZL focus) - ready after ingest
- [ ] Specialist models (Big 11) - mostly ready

---

## 📊 DATABASE SCHEMA SUMMARY

| Schema | Tables | Purpose |
|--------|--------|---------|
| `raw` | 23 | Raw ingested data |
| `training` | 55 | Feature matrices, OOF predictions |
| `model` | 10 | Model registry, metrics |
| `forecasts` | 12 | Forecast outputs |
| `analytics` | 33 | Dashboard tables |
| **Total** | **153** | |

---

## 🔗 Data Sources

| Source | Type | Status | Cadence |
|--------|------|--------|---------|
| **Yahoo Finance** | Futures prices | ✅ Active | Daily |
| **FRED API** | Economic indicators | ✅ Active | Daily/Weekly |
| **Barchart RSS** | News (free) | ✅ Active | Real-time |
| **Barchart Premier** | Historical + API | 📦 Trial active | Daily |
| **USDA** | Ag fundamentals | ✅ Active | Weekly/Monthly |
| **CFTC** | COT positioning | ✅ Active | Weekly |

---

*Last Updated: January 16, 2026 05:58 AM*
