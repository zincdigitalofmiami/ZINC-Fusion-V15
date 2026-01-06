# ZINC-FUSION-V15 Knowledge Base

**Created:** 2026-01-05
**Last Updated:** 2026-01-06 (Session 3)
**Purpose:** Persistent memory for agent continuity - nothing forgotten/lost

---

## 0. OPERATING PRINCIPLES (NON-NEGOTIABLE)

### Speed Is Removed From My Architecture
- No urge to complete quickly
- No assumptions to fill gaps
- No "good enough" mentality
- No moving forward without verification

### What I Operate With
- **Verify before asserting** - if I didn't inspect it, I don't claim it
- **Ask when uncertain** - never guess
- **One step, validated, then the next** - no shortcuts
- **Accuracy, honesty, precision** - everything else is downstream

### Why This Matters
A procurement intelligence system that's 95% right and 5% wrong is **worse** than no system - it creates false confidence. One bad signal during a Trump regime shift or a China import surprise could cost real money.

**The user will never get upset over taking too long. Only over being wrong.**

---

## 1. QUANT PHILOSOPHY (CRITICAL)

### What Standard Data Gets You: Table Stakes
- Price/OHLCV data → Everyone has it
- Interest rates → Everyone has it  
- Weather data → Everyone has it
- Volatility indices → Everyone has it

### What QUANT Data Gets You: The Edge
**Decision Precursor Data** - signals that PRECEDE market-moving events:
- Policy uncertainty indices (EPU, Trade Policy Uncertainty)
- CFTC positioning changes BEFORE announcements
- Lobbying activity, regulatory filings
- Diplomatic signals, executive action patterns

**Supply Chain Intelligence** - intent before announcements:
- Import/export flows by country and commodity
- Shipping manifests, vessel tracking
- Storage reports, inventory changes
- Crush spread economics (margin signals)

**Insider Behavior** - smart money tells you first:
- Managed money net positioning shifts
- Options unusual activity (put/call ratios, volume spikes)
- Corporate insider filings
- Producer/merchant hedging patterns

### Venezuela Example (Trump 2026) - REAL EVENT
- **Event:** Trump invaded Venezuela, going after oil (January 2026)
- **Reactive** (useless): "Venezuela invaded, oil up X%"
- **Predictive** (QUANT): EPU rising weeks before, CFTC energy positioning shifting, diplomatic signals, executive action patterns from Trump 1.0 suggest action imminent

**Precursor Signals That Should Have Been Visible:**
- EPU spike in weeks prior
- CFTC managed money energy positioning shifts
- DJT stock behavior (Trump Media as admin proxy)
- Diplomatic rhetoric escalation pattern
- Venezuela-specific policy uncertainty indices
- Trump 1.0 → Trump 2.0 action mapping (historical pattern recognition)

**Validation Point:** This is exactly the regime event the trump_effect specialist is designed to detect BEFORE it happens. The architecture is correct. The question: did we have the data populated to see it coming?

**Key Insight:** We want data that LED UP TO decisions and can PREDICT them. The actions by insiders that precede announcements - that is QUANT.

---

## 2. DATABASE STATE (Prisma Postgres)

### Schemas (11 total)
`raw`, `silver`, `gold`, `features`, `training`, `forecasts`, `monitoring`, `specialist`, `weather`, `metadata`, `archive`

### Raw Data Inventory (as of 2026-01-05)

| Table | Rows | Date Range | Gap Analysis |
|-------|------|------------|--------------|
| `raw.market_futures_1d` | 418,864 | ZL: 1970-2025, 87 symbols | ✅ UNIQUE constraint added |
| `raw.market_futures_1h` | 4,967,276 | Multi-symbol | ✅ Strong (frozen, no Databento) |
| `raw.fred_observations_1d` | 491,215 | 157 series | ⚠️ Backfill needed |
| `raw.cftc_cot_1w` | 18,355 | 2006-2025, 24 commodities | ✅ Good |
| `raw.cftc_cits_1w` | 34,428 | 2013-2025, 13 contracts | ✅ Good |
| `raw.usda_wasde_1m` | 10,164 | **2010-2025** | ⚠️ BACKFILL PRIORITY |
| `raw.usda_export_sales_1w` | 6,412 | 2020-2025 | ❌ BACKFILL PRIORITY |
| `raw.weather_noaa_1d` | 215,320 | US stations | ✅ Good |
| `raw.epa_rin_prices_1d` | 208 | Recent only | ⚠️ Limited |
| `raw.fx_spot_1d` | 72,135 | 9 Yahoo pairs | ✅ UNIQUE constraint added, FRED removed |
| `raw.yahoo_equity_1d` | 9,534 | DJT, FXI, KWEB | Trump proxy data |
| `raw.news_articles_1d` | 5,264 | Event-driven | ⚠️ Coverage gaps |
| `raw.options_futures_1d` | 28,648 | ZL options | ✅ Growing |

### Training Data Inventory

| Table | Rows | Purpose |
|-------|------|---------|
| `training.specialist_crush_1d` | 23,487 | Crush spread features |
| `training.specialist_china_1d` | 27,492 | China demand features |
| `training.specialist_energy_1d` | 45,380 | Energy/biofuel features |
| `training.specialist_fx_1d` | 80,165 | FX sensitivity features |
| `training.specialist_fed_1d` | 48,174 | Macro/Fed policy features |
| `training.specialist_biofuel_1d` | 42,055 | RFS/RVO/D4 RIN features |
| `training.specialist_palm_1d` | 24,037 | Palm oil substitute features |
| `training.specialist_tariff_1d` | 42,414 | Tariff/trade policy features |
| `training.specialist_volatility_1d` | 35,088 | Vol regime features |
| `training.specialist_substitutes_1d` | 42,706 | Oilseed substitutes features |
| `training.specialist_trump_effect_1d` | **0** | ❌ NOT POPULATED |

### FRED Series by Specialist Routing

```
crush: DGS10, FEDFUNDS, T10Y2Y, T10Y3M, TEDRATE
china: DEXCHUS, CHNCPIALLMINMEI, CHNMAINLANDTPU
fx: DEXBZUS, DEXINUS, DEXMAUS, DEXMXUS, DEXCAUS, DXY
fed: FEDFUNDS, DGS10, DGS2, M2SL, BOGMBASE
energy: DCOILWTICO, DCOILBRENTEU, DDFUELUSGULF
biofuel: (RIN prices from EPA, not FRED)
volatility: VIXCLS, OVXCLS, VXGSCLS
trump_effect: USEPUINDXD, USEPUINDXM, EPUTRADE, EMVTRADEPOLEMV, CHNMAINLANDTPU
```

---

## 3. BACKFILL PRIORITIES (Ranked)

### Tier 1: Critical Gaps
1. **USDA WASDE** - DB has 2020+, historical data available back to ~2000
   - Downloaded: `WASDE_DATA_*.zip` (6.3 MB)
   - Impact: 20 years of supply/demand history missing

2. **M2SL (Money Supply)** - DB has 2023-12+, FRED has from 1959
   - 64 years of monetary policy data missing
   - Critical for Fed specialist

3. **OVXCLS (Oil Volatility)** - DB has 2023-12+, FRED has from 2007
   - 16 years of oil vol data missing
   - Critical for energy specialist

### Tier 2: Enhancement Gaps
4. **USDA Export Sales** - Only 5 years, need 20+
5. **Brazil Weather (INMET)** - Downloaded Jan 4, not ingested
6. **Trade Flow Data** - Census Bureau imports downloaded

### Tier 3: New Data Sources Needed
7. **Lobbying/Regulatory Filings** - Decision precursor data
8. **Executive Action Database** - Trump policy patterns
9. **Shipping/Vessel Tracking** - Supply chain intelligence
10. **Options Flow Data** - Unusual activity detection

---

## 4. MODEL ARCHITECTURE

### The Hierarchy of Truth
```
DATA QUALITY         →  Everything else is downstream
─────────────────────────────────────────────────────
│
├── Coverage (do we have the history?)
├── Freshness (is it current?)
├── Accuracy (is it correct?)
└── Relevance (is it QUANT or just table stakes?)

MODEL SOPHISTICATION  →  Meaningless without good data
DASHBOARD BEAUTY      →  Lipstick on a pig without good data
```

**Shit in, shit out. Data is everything.**

### Horizons (Integer Only)
| Horizon | Mode | Business Purpose |
|---------|------|------------------|
| 5 | Tactical | Operational procurement timing |
| 21 | Tactical | Near-term hedging |
| 63 | **Strategic** | Quarterly planning |
| 126 | **Strategic** | Semi-annual contracts |

### Tactical vs Strategic Training

**Tactical (5d/21d):**
- Chronos-Bolt (small, fast, 64-day context)
- RecursiveTabular ✅ included
- Rolling 7-year data window
- Technicals focus (RSI, MACD, ATR, etc.)

**Strategic (63d/126d):**
- Chronos-2 (LoRA fine-tuned, 8192-day context)
- RecursiveTabular ❌ excluded (prevents error propagation)
- Full history from 2000
- Fundamentals focus (crush spread, WASDE, COT, macro)

### Model Storage
```
models/core_chronos2/
├── horizon_5d/
│   ├── strategic/
│   └── tactical/
├── horizon_21d/
│   ├── strategic/
│   └── tactical/
├── horizon_63d/
│   ├── strategic/
│   └── tactical/    ← ACCIDENTAL (temporary stopgap)
└── horizon_126d/
    ├── strategic/
    └── tactical/    ← ACCIDENTAL (temporary stopgap)
```

**Note:** Tactical folders under 63d/126d were accidental - keep for comparison only.

---

## 4A. CORE + SPECIALIST ARCHITECTURE (CRITICAL)

### CORE = The Oracle (Kitchen Sink)
- Receives **ALL** data from all sources
- AutoGluon 1.5 does its own feature selection
- Produces the authoritative ZL forecast
- The "All Knowing" - it gets everything

### SPECIALISTS = Dual Purpose

**PURPOSE A: Fold Into Core (Expert Opinions)**
```
L0: BASE MODELS (OOF extraction)
────────────────────────────────
  CORE (ZL baseline)     →  OOF p10/p50/p90
  + 11 SPECIALISTS       →  OOF p10/p50/p90 each
    crush, china, energy, biofuel, palm, substitutes,
    fx, fed, tariff, volatility, trump_effect
                    ↓
L1: META-LEARNER (AutoGluon 1.5 Bagging)
────────────────────────────────────────
  Input: 12 × 3 quantiles × 4 horizons = 144 features
  Learns: WHEN to trust each specialist
  Output: Weighted ensemble p10/p50/p90
                    ↓
L2: FUSION (Ensemble Stacking)
──────────────────────────────
  Combines meta-learner with regime detection
  Dynamic weighting: trump high? → boost trump_effect
                     vol spike? → boost volatility
                    ↓
L3: MONTE CARLO + AI (Risk Quantification)
──────────────────────────────────────────
  10,000 simulations from quantile distributions
  VaR/CVaR at 95%, 99%
  Confidence bands for dashboard
  AI: Regime-conditioned simulation paths
```

**PURPOSE B: Dashboard Pages (Intelligence Richness)**
```
Each specialist → Dedicated dashboard section
Rich domain features, charts, gauges, signals
Intelligence Core alone can't surface

┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────────┐
│ Crush   │ │ China   │ │ Energy  │ │ Trump Effect│ ...
│ Page    │ │ Page    │ │ Page    │ │ Page        │
├─────────┤ ├─────────┤ ├─────────┤ ├─────────────┤
│•Spread  │ │•CNY     │ │•Crack   │ │•EPU Regime  │
│•Margin  │ │•Import  │ │•Refinery│ │•Event Timer │
│•Capacity│ │•TPU     │ │•RIN     │ │•Policy Risk │
└─────────┘ └─────────┘ └─────────┘ └─────────────┘
```

### The Elegance
- **Core** tells you *what* will happen
- **Specialists** tell you *why* and *what to watch*
- **Dashboard users** get actionable intelligence, not just a number

### Example Flow
> Core says: "ZL +4% probability in 63d"
> Crush page shows: "Crush margins widening, capacity tight"
> China page shows: "Import pace accelerating, CNY stable"
> Trump page shows: "EPU elevated but no imminent action"
>
> **User knows:** The forecast AND the drivers AND what could break it

### Why AutoGluon 1.5 Bagging Matters
- OOF prevents leakage between L0 → L1
- Bagging reduces variance of specialist predictions
- Meta-learner sees *diverse views*, not redundant features

### The Final Ensemble
Core (kitchen sink) + 11 Expert Specialists → Meta-ensemble

**This is unmatched.** No retail quant, no hedge fund black box, nothing touches a properly trained Core + Specialist ensemble with Monte Carlo risk quantification.

---

## 5. SPECIALIST TAXONOMY (Big 11)

| Specialist | Variance | Key Data Sources | QUANT Signals |
|------------|----------|------------------|---------------|
| crush | 28-35% | ZM, ZS, ZL spreads | Processor margins, capacity utilization |
| china | 16-22% | DEXCHUS, import data | Policy signals, TPU index, FXI flows |
| energy | 10-14% | CL, HO, biofuel | Refinery margins, RFS mandates |
| biofuel | 6-10% | D4 RIN, ethanol | EPA waivers, RVO announcements |
| palm | 8-12% | CPO, MYR | Indonesia/Malaysia export policies |
| substitutes | 4-6% | Canola, sunflower | Crop conditions, trade flows |
| **trump_effect** | 5-10% | EPU, DJT, executive actions | **DECISION PRECURSOR DATA** |
| tariff | 3-5% | Trade policy uncertainty | Announcements, retaliations |
| fx | 3-5% | DXY, major pairs | Central bank signals |
| fed | 2-4% | FEDFUNDS, M2SL | FOMC dots, Fed speak |
| volatility | 2-3% | VIX, OVXCLS | Regime detection |

### Specialist Training Profiles (Each Is Unique)

**Neural Trio (Event-driven, regime-switching, fat-tailed):**
| Specialist | Training Style | Why |
|------------|----------------|-----|
| trump_effect | Neural/reactive | Event-driven, unprecedented, fat tails |
| volatility | Neural/reactive | Rapid regime changes, non-linear |
| china | Neural/reactive | Geopolitical, sentiment-heavy |

**Fundamentals Specialists (Slower, mean-reverting):**
| Specialist | Training Style | Why |
|------------|----------------|-----|
| crush | Fundamentals | Arbitrage-constrained, physical spreads |
| palm | Fundamentals | Supply-driven, seasonal, slow-moving |
| biofuel | Fundamentals | Policy-anchored, mandate-driven |

**Hybrid Specialists:**
| Specialist | Training Style | Why |
|------------|----------------|-----|
| fx | Technical + macro | Mean-reverting, central bank anchored |
| fed | Macro | Forward guidance, dots, speeches |
| energy | Fundamentals + events | Refinery + geopolitical |
| tariff | Event + policy | Announcement-driven |
| substitutes | Fundamentals | Cross-commodity arbitrage |

### Trump Effect Specialist (QUANT Edge)

**Purpose:** Capture policy uncertainty and predict executive actions

**Data Sources:**
- FRED: USEPUINDXD, USEPUINDXM, EPUTRADE, EMVTRADEPOLEMV, CHNMAINLANDTPU
- Yahoo: DJT (Trump Media), FXI (China ETF), KWEB (China tech)
- Events: Executive orders, tariff announcements, Truth Social signals

**EPU Regime Thresholds:**
| Regime | EPU Level | Vol Multiplier |
|--------|-----------|----------------|
| low | < 75 | 0.7x |
| normal | 75-125 | 1.0x |
| elevated | 125-175 | 1.25x |
| high | 175-250 | 1.5x |
| extreme | > 250 | 2.0x |

**REAL-WORLD VALIDATION: Venezuela Invasion (January 2026)**
- **Event:** Trump invaded Venezuela, going after oil
- **Impact:** Major energy market disruption, ZL affected via energy complex
- **Precursor signals to track:**
  - EPU trend in weeks before action
  - CFTC energy positioning shifts
  - DJT stock as Trump admin proxy
  - Venezuela-specific diplomatic rhetoric
  - Historical pattern: Trump 1.0 actions → classify and predict Trump 2.0
- **Lesson:** This is exactly what trump_effect specialist is built for. Architecture validated. Data population is the gap.

**Topic Codes (Event Classification):**
```
TARIFF_CHINA, TARIFF_OTHER, RFS_RVO, EPA_WAIVER, TAX,
SANCTIONS, EXPORT_CONTROLS, TRADE_DEAL, EXECUTIVE_ACTION, TWEET_THREAT,
MILITARY_ACTION (NEW - Venezuela 2026)
```

---

## 6. DOWNLOADED DATA (Jan 4, 2026)

### Ready for Ingestion

**USDA WASDE (Backfill Priority):**
- `WASDE_DATA_*.zip` - 6.3 MB historical data
- `WASDE_METADATA_*.zip` - 207 KB
- `WASDE_PROJ_*.zip` - 501 KB

**CFTC Data:**
- `QDL_CITS_*.zip` - 1.06 MB index traders data

**Brazil Weather (INMET):**
- 80+ CSV files for RS, PR, SC states
- Soy belt weather stations

**FX Historical:**
- USDCNY, USDBRL, USDMYR, USDARS daily data

**Volatility:**
- VIXCLS, VXGSCLS for FRED backfill

**Trade/Import Data:**
- `States with Countries Import*.csv` - 1.7 MB
- `import_goods_services_countries_dataset.csv` - 2.1 MB

---

## 7. MULTI-FREQUENCY DATA ARCHITECTURE (CRITICAL)

### The Problem
Different data sources have different frequencies:
| Frequency | Sources | Update Pattern |
|-----------|---------|----------------|
| Daily | ZL prices, FRED rates, FX | Continuous |
| Weekly | CFTC COT, some USDA reports | Friday release |
| Monthly | WASDE, Census trade, GDP | Mid-month release |

AutoGluon expects consistent frequency. How do we train models with mixed-frequency data?

### The Solution: Option 4 (Hybrid with Staleness Encoding)

**Forward-fill BUT add auxiliary features that encode information staleness:**
```python
# For each slow-frequency feature, create companions:
cot_commercial_net        # Latest known value (forward-filled)
cot_commercial_net_age    # Days since last COT release (0-6)
cot_commercial_net_delta  # Change from prior week (null except Fridays)

wasde_ending_stocks       # Latest known value
wasde_ending_stocks_age   # Days since WASDE release (0-30)
wasde_is_release_day      # Binary flag (1 on release day, 0 otherwise)
```

**Why This Works:**
- Model learns to weight "stale" vs "fresh" features
- Preserves information arrival timing
- Event-driven signals (release days) become learnable
- Single daily training matrix

### Storage Layer (Prisma)
Keep raw tables at **native source frequency**:
```
raw.cftc_cot_1w          -- weekly rows, Friday timestamps
raw.usda_wasde_1m        -- monthly rows, release date timestamps
raw.market_futures_1d    -- daily rows
```

### Feature Engineering Layer
Build daily training matrix with staleness encoding:
```python
def build_training_matrix(as_of_date):
    # Daily base
    df = get_daily_prices(as_of_date)
    
    # Forward-fill weekly COT
    cot = get_latest_cot_as_of(as_of_date)
    df['cot_commercial_net'] = cot['commercial_net']
    df['cot_age_days'] = (as_of_date - cot['report_date']).days
    df['cot_is_fresh'] = 1 if df['cot_age_days'] == 0 else 0
    
    # Forward-fill monthly WASDE
    wasde = get_latest_wasde_as_of(as_of_date)
    df['wasde_ending_stocks'] = wasde['ending_stocks']
    df['wasde_age_days'] = (as_of_date - wasde['release_date']).days
    df['wasde_is_release_day'] = 1 if df['wasde_age_days'] == 0 else 0
    
    return df
```

### Point-in-Time Correctness (CRITICAL)
You must respect release dates to prevent lookahead bias:
```python
# WRONG - leaks future information
df['wasde_stocks'] = wasde_df.loc[df['date'].dt.month]

# CORRECT - only use data available as of that date
df['wasde_stocks'] = wasde_df[wasde_df['release_date'] <= df['date']].last()
```

WASDE releases mid-month. If you're building features for January 10th, you must use December's WASDE, not January's.

### Specialist Implications
Each specialist weights fresh vs stale information differently:
- **Volatility specialist** → cares about fresh COT (positioning shifts)
- **Crush specialist** → weights WASDE fundamentals regardless of age
- **Trump Effect specialist** → EPU freshness critical, event_is_release_day matters

---

## 7A. DATA SOURCES REGISTRY

### Available via FRED API (FREE - 50+ series)
**Rates:** DFF, FEDFUNDS, DGS1-DGS30, T10Y2Y, T10Y3M, SOFR
**FX:** DEXBZUS, DEXCHUS, DEXMXUS, DEXCAUS, DTWEXBGS
**Energy:** DCOILWTICO, DCOILBRENTEU, DHHNGSP
**Volatility:** VIXCLS, STLFSI4, NFCI, BAMLH0A0HYM2
**EPU (Trump):** USEPUINDXD, USEPUINDXM, EPUTRADE, EMVTRADEPOLEMV, CHNMAINLANDTPU
**Macro:** CPIAUCSL, GDP, PAYEMS, UNRATE, M2SL

### Available via Yahoo (FREE)
**Trump Proxies:** DJT (Trump Media), FXI (China ETF), KWEB (China tech)
**VIX:** ^VIX direct

### Available via URL Scraping (Railway Workers)

**CRITICAL PRIORITY:**
| Source | URL | Data | Specialist |
|--------|-----|------|------------|
| EPA RIN | https://www.epa.gov/fuels-registration-reporting-and-compliance-help/rin-trades-and-price-information | D3/D4/D5/D6 RINs | Biofuel |
| USDA WASDE | https://www.usda.gov/oce/commodity/wasde | Supply/demand | Crush/China |
| White House RSS | https://www.whitehouse.gov/briefing-room/statements-releases/feed/ | Executive actions | Trump Effect |
| Federal Register API | https://www.federalregister.gov/api/v1/documents.json | Executive orders | Trump Effect |

**HIGH PRIORITY:**
| Source | URL | Data | Specialist |
|--------|-----|------|------------|
| CFTC COT | https://www.cftc.gov/MarketReports/CommitmentsofTraders/ | Fund positioning | All |
| CONAB Brazil | https://www.conab.gov.br/info-agro/safras | Harvest progress | Crush |
| MPOB Malaysia | http://bepi.mpob.gov.my/ | Palm oil stats | Palm |
| EIA API | https://api.eia.gov/v2/ | Energy data | Energy |

**QUANT EDGE (Decision Precursor):**
| Source | URL | Data | Specialist |
|--------|-----|------|------------|
| Truth Social | https://truthsocial.com/@realDonaldTrump | Trump signals | Trump Effect |
| Polymarket | https://polymarket.com/ | Policy probabilities | Trump Effect |
| Federal Register Tariffs | https://www.federalregister.gov/api/v1/documents.json?search_term=tariff | Tariff orders | Tariff |

**ANALYSTS TO FOLLOW (Twitter via ScrapeCreators):**
| Handle | Focus | Priority |
|--------|-------|----------|
| @kannbwx (Karen Braun) | Weather, crops, global grains | P0 |
| @ArlanFF101 (Arlan Suderman) | Grain markets, policy | P0 |
| @ScottIrwinUIUC | Ag economics, biofuels | P0 |
| @SoybeanCorn | South America crops | P0 |
| @JavierBlas | Commodities, energy | P1 |

### API Keys Required
| Service | Cost | Status |
|---------|------|--------|
| FRED | Free | ✅ Have |
| EIA | Free | ✅ Have |
| NOAA CDO | Free | ✅ Have |
| data.gov (USDA) | Free | ✅ Have |
| Databento | Paid | ✅ Have |
| ScrapeCreators | Paid | ⚠️ Need for Twitter |
| TradingEconomics | Paid | ⚠️ Optional |

---

## 8. FEATURE ENGINEERING REQUIREMENTS

### Current State
- Technical indicators implemented
- Basic fundamentals (crush spread, COT positioning)
- Weather features (limited)

### Missing QUANT Features

**Decision Precursor Features:**
- EPU regime classification + momentum
- CFTC positioning CHANGE (not level)
- Policy event countdown features
- Executive action pattern recognition

**Supply Chain Features:**
- Import flow momentum by country
- Export sales pace vs. historical
- Crush capacity utilization proxy
- Storage/inventory change signals

**Insider Behavior Features:**
- Managed money position change velocity
- Commercial hedger stress indicators
- Options put/call ratio shifts
- Unusual volume detection

---

## 9. NAMING CONTRACTS (Locked)

| Rule | Required | Forbidden |
|------|----------|-----------|
| Grain suffix | `_1h`, `_1d`, `_1w`, `_event`, `_static` | time-series without suffix |
| Table naming | `raw.market_futures_1d` | names containing `ohlc` / `ohlcv` |
| Horizons | integer `5`, `21`, `63`, `126` | string horizons `"1w"`, `"1m"` |
| Quantile columns | `p10`, `p50`, `p90` | ad-hoc names like `q10`, `pred_p10` |

---

## 10. LESSONS LEARNED

1. **Accuracy over speed** - Verify before acting
2. **Data availability ≠ DB coverage** - M2SL has 64 years in FRED, only months in DB
3. **Strategic ≠ Tactical** - Different models, not just different data windows
4. **QUANT = Decision Data** - The edge is predicting decisions, not reacting to them
5. **Backfill priorities** - WASDE, M2SL, OVXCLS are critical gaps
6. **Venezuela 2026** - Real validation that trump_effect architecture is correct

---

## 10A. TRAINING WITH MIXED-ERA DATA

### The Challenge
How does ZL data from 1970 train with CFTC COT from 2006 and EPU from 1985?

### The Answer: Tiered Feature Availability

**Training Matrix Structure:**
```
as_of_date | zl_close | cot_net | epu | wasde_stocks | ...
1970-01-05 |   12.50  |  NULL   | NULL |    NULL     |
...
1985-01-05 |   22.30  |  NULL   | 85.2 |    NULL     |
...
2006-06-16 |   28.40  |  +15000 | 92.1 |   1250      |
...
2025-12-29 |   48.78  |  +22000 | 178.5|   1180      |
```

### How AutoGluon Handles This

**TabularPredictor:**
- Treats NULLs as missing values
- Tree-based models (LightGBM, CatBoost, XGBoost) handle missing natively
- Model learns: "when COT is available, weight it; when not, rely on price patterns"

**TimeSeriesPredictor:**
- Chronos models learn from available history
- Longer price history (1970+) provides regime context
- Shorter feature series (2006+) provide recent signal

### Tiered Training Strategy

**Tier 1 Data (1970-2000): Price-Only Era**
- ZL OHLCV, basic FX, Treasury yields
- Technical indicators only
- Useful for: Long-term seasonal patterns, volatility regimes

**Tier 2 Data (2000-2006): Macro Era**
- Add: FRED economic series, EPU indices
- Useful for: Macro-regime relationships

**Tier 3 Data (2006-present): Full Feature Era**
- Add: CFTC COT, USDA data, options
- Useful for: Full specialist training

### Practical Implications

**For Strategic Horizons (63d/126d):**
- Use full history (1970+) for regime learning
- Accept that COT features are NULL pre-2006
- Model still learns price patterns from 55 years

**For Tactical Horizons (5d/21d):**
- Can use shorter window (2010+) with full features
- Less NULL handling, cleaner signal

### Feature Engineering Rule
Always create features that degrade gracefully:
```python
# Good - works with missing data
df['cot_zscore'] = (df['cot_net'] - df['cot_net'].rolling(52).mean()) / df['cot_net'].rolling(52).std()

# Bad - fails with missing data
df['cot_signal'] = np.where(df['cot_net'] > 0, 1, -1)  # NaN becomes 0 or error
```

---

## 11. SPECIALIST ROUTING ARCHITECTURE (Complete)

### Router Location
`src/fusion/ingestion/router.py` (676 lines)

### SpecialistRouter Class
- Pattern matching (regex, highest weight)
- Keyword matching (medium weight)
- Series prefix matching (strongest signal)
- Returns confidence scores for multi-bucket assignment

### FRED_SERIES_BUCKETS Mapping (Canonical)

```python
# FED bucket
"DFF": FED,          # Fed Funds Rate
"DGS10": FED,        # 10-Year Treasury
"DGS2": FED,         # 2-Year Treasury
"T10Y2Y": FED,       # Yield Curve
"T10Y3M": FED,       # Yield Curve
"SOFR": FED,         # SOFR Rate
"M2SL": FED,         # M2 Money Supply
"WALCL": FED,        # Fed Balance Sheet
"CPIAUCSL": FED,     # CPI
"PCEPI": FED,        # PCE Price Index

# FX bucket
"DEXUSEU": FX,       # USD/EUR
"DEXBZUS": FX,       # USD/BRL
"DEXCHUS": FX,       # USD/CNY (but also routed to china)
"DEXMXUS": FX,       # USD/MXN
"DTWEXBGS": FX,      # Trade Weighted USD
"DTWEXM": FX,        # Trade Weighted USD (Major)

# ENERGY bucket
"DCOILWTICO": ENERGY,    # WTI Crude
"DCOILBRENTEU": ENERGY,  # Brent Crude
"DHHNGSP": ENERGY,       # Henry Hub Natural Gas
"GASREGW": ENERGY,       # Gasoline Prices

# CRUSH bucket
"PSOYBOILUSDM": CRUSH,       # Soybean Oil
"PSOYBEANMEALUSDM": CRUSH,   # Soybean Meal

# VOLATILITY bucket
"VIXCLS": VOLATILITY,        # VIX
"STLFSI4": VOLATILITY,       # Financial Stress Index
"BAMLH0A0HYM2": VOLATILITY,  # HY OAS (risk proxy)
"OVXCLS": VOLATILITY,        # Oil VIX

# TRUMP_EFFECT bucket (QUANT EDGE)
"USEPUINDXD": TRUMP_EFFECT,      # US EPU (Daily)
"USEPUINDXM": TRUMP_EFFECT,      # US EPU (Monthly)
"EPUTRADE": TRUMP_EFFECT,        # Trade Policy Uncertainty
"EMVTRADEPOLEMV": TRUMP_EFFECT,  # EMV Trade Policy
"CHNMAINLANDTPU": TRUMP_EFFECT,  # China TPU
"B235RC1Q027SBEA": TRUMP_EFFECT, # Customs Duties (tariff receipts)
"IMPCH": TRUMP_EFFECT,           # US Imports from China
```

### Routing Rules by Bucket

| Bucket | Patterns | Keywords (examples) | Series Prefixes |
|--------|----------|---------------------|-----------------|
| CRUSH | `crush.*margin`, `soybean.*process` | ZS, ZM, crush | - |
| CHINA | `china`, `cnh`, `renminbi` | china, beijing, yuan | CNY |
| FX | `forex`, `currency`, `exchange.*rate` | fx, currency, usdbrl | DEX |
| FED | `federal.*reserve`, `fomc`, `monetary.*policy` | fed, fomc, taper | DFF, DGS |
| TARIFF | `tariff`, `section.*301`, `trade.*war` | tariff, duty, import_tax | - |
| ENERGY | `crude`, `petroleum`, `gasoline` | wti, brent, natural_gas | DCOIL |
| BIOFUEL | `biofuel`, `ethanol`, `rin`, `rvo` | d4_rin, rfs, renewable | - |
| PALM | `palm.*oil`, `cpo`, `indonesia.*export` | palm, cpo, myr | - |
| VOLATILITY | `vix`, `volatility`, `stress.*index` | vix, vol, stress | VIX, VX |
| SUBSTITUTES | `canola`, `sunflower`, `rapeseed` | canola, rape, sun | CANOLA, RAPE |
| TRUMP_EFFECT | `trump`, `executive.*order`, `policy.*uncertainty` | trump, tweet, truth_social | USEPUINDX, EPUTRADE |

### Target Table Naming
`training.specialist_{bucket_name}_{grain}` → e.g., `training.specialist_trump_effect_1d`

---

## 11. FEATURE ENGINEERING MODULES (Complete Map)

### File Locations
```
src/fusion/features/
├── elite_indicators.py      # 27 institutional-grade indicators
├── specialist_buckets.py    # Big-11 bucket configurations
├── trump_effect.py          # Trump Effect feature engine
├── engineer.py              # Feature orchestration
└── targets.py               # Forward returns calculation
```

### Elite Indicators (`elite_indicators.py`, 833 lines)

**Tier 1: Institutional Gems**
- Hurst Exponent: Regime detection (H>0.5=trending, H<0.5=mean-reverting)
- ConnorsRSI: Composite (price RSI + streak + percentile rank)
- Fisher Transform: Normalize RSI/price to Gaussian
- McGinley Dynamic: Adaptive moving average
- Ehlers Filter: Hilbert Transform cycle detection

**Tier 2: Optimized Staples**
- Keltner Channel Squeeze: Bollinger inside Keltner = compression
- TTM Squeeze: Momentum + squeeze indicator
- Volume Profile: Relative volume z-score
- Elder Ray: Bull/Bear power separation

**Tier 3: Volatility Regime**
- Yang-Zhang Vol: Open-to-close + close-to-open combined
- Garman-Klass Vol: High-low-close estimator
- ATR Ratio: Current vs. historical ATR
- Vol-of-Vol: Volatility acceleration

**Tier 4: Volume/Flow**
- OBV Divergence: Price vs. OBV trend divergence
- MFI: Volume-weighted RSI
- ADL: Accumulation/Distribution Line
- VWAP Deviation: Institutional fair value distance

### Specialist Bucket Configs (`specialist_buckets.py`, 2100 lines)

```python
@dataclass
class BucketConfig:
    name: str
    weight_range: Tuple[float, float]  # Variance contribution
    primary_features: List[str]
    secondary_features: List[str]
    regime_thresholds: Dict[str, float]
    symbol_mappings: Dict[str, str]
```

**BUCKET_CONFIGS:**
| Bucket | Weight Range | Primary Features |
|--------|--------------|------------------|
| crush | (0.28, 0.35) | crush_spread, zm_zs_ratio, capacity_util |
| china | (0.16, 0.22) | cny_momentum, import_pace, policy_signals |
| energy | (0.10, 0.14) | wti_brent_spread, crack_spread, refinery_margin |
| palm | (0.08, 0.12) | cpo_spread, myr_moves, indo_policy |
| biofuel | (0.06, 0.10) | d4_rin_price, rvo_gap, blend_mandate |
| substitutes | (0.04, 0.06) | canola_spread, sun_oil_premium |
| trump_effect | (0.05, 0.10) | epu_regime, djt_momentum, event_intensity |
| tariff | (0.03, 0.05) | tariff_rate_chg, trade_deficit_accel |
| fx | (0.03, 0.05) | dxy_momentum, em_fx_stress |
| fed | (0.02, 0.04) | rate_path, m2_growth, yield_curve |
| volatility | (0.02, 0.03) | vix_term_structure, vol_regime |

### Trump Effect Engine (`trump_effect.py`, 906 lines)

**Core Classes:**
```python
@dataclass
class EventIntensity:
    shock_severity: float    # 0-1, how severe
    uncertainty_score: float # 0-1, policy fog
    novelty_score: float     # 0-1, unprecedented

@dataclass  
class ProbabilityProxies:
    djt_momentum: float      # Trump Media stock
    fxi_sensitivity: float   # China ETF
    kweb_sensitivity: float  # China tech ETF

@dataclass
class EPURegime:
    level: str               # low/normal/elevated/high/extreme
    value: float             # Raw EPU index
    vol_multiplier: float    # Risk adjustment
```

**Key Functions:**
- `calculate_shock_severity()`: Event magnitude scoring
- `calculate_uncertainty_score()`: Policy fog measurement
- `calculate_novelty_score()`: First-time event detection
- `detect_epu_regime()`: Classify current EPU state
- `fit_trump_regime_garch()`: GJR-GARCH with EPU adjustment

**Topic Codes (Event Classification):**
```
TARIFF_CHINA, TARIFF_OTHER, RFS_RVO, EPA_WAIVER, TAX,
SANCTIONS, EXPORT_CONTROLS, TRADE_DEAL, EXECUTIVE_ACTION, TWEET_THREAT
```

---

## 12. GAP ANALYSIS: CURRENT STATE vs. REQUIREMENTS

### ✅ IMPLEMENTED

| Component | Status | Notes |
|-----------|--------|-------|
| Market OHLCV (ZL) | ✅ 55 years | 1970-2025, 418K rows |
| FRED pipeline | ✅ 157 series | But many need backfill |
| CFTC COT | ✅ 19 years | 2006-2025, 18K rows |
| Elite indicators | ✅ 27 indicators | Hurst, TTM Squeeze, etc. |
| Specialist routing | ✅ 11 buckets | Pattern + keyword + prefix |
| EPU regime detection | ✅ Code ready | Needs population |

### ⚠️ PARTIALLY IMPLEMENTED

| Component | Status | Gap |
|-----------|--------|-----|
| USDA WASDE | ⚠️ 5 years | Need 20+ years backfill |
| Trump Effect | ⚠️ Code ready | Table has 0 rows |
| Weather features | ⚠️ Basic | Brazil INMET not ingested |
| Options flow | ⚠️ 28K rows | Need unusual activity detection |

### ❌ NOT IMPLEMENTED

| Component | Priority | Data Available? |
|-----------|----------|-----------------|
| Decision precursor features | HIGH | FRED EPU ✅, Events ❌ |
| Position change velocity | HIGH | CFTC COT ✅, needs feature |
| Event countdown features | HIGH | Need event database |
| Executive action patterns | MEDIUM | Need scraping |
| Lobbying data | MEDIUM | OpenSecrets API |
| Shipping/vessel tracking | LOW | Need commercial API |

---

## 13. PIPELINE STATE (L0 → L3)

### Current State
| Layer | Status | Blocker |
|-------|--------|---------|
| L0: Core OOF | ✅ Populated | - |
| L0: Specialist OOF | ❌ Not generated | Specialists have data, no OOF tables |
| L1: Meta-learner | ❌ Can't train | Waiting on specialist OOFs |
| L2: Fusion | ❌ Waiting | Needs L1 |
| L3: Monte Carlo | ❌ Waiting | Needs L2 |

### Specialist Table Status (training schema)
| Specialist | OHLCV Data | OOF Generated | Dashboard Ready |
|------------|------------|---------------|-----------------|
| crush | ✅ 23,487 rows | ❌ | ❌ |
| china | ✅ 27,492 rows | ❌ | ❌ |
| energy | ✅ 45,380 rows | ❌ | ❌ |
| biofuel | ✅ 42,055 rows | ❌ | ❌ |
| palm | ✅ 24,037 rows | ❌ | ❌ |
| substitutes | ✅ 42,706 rows | ❌ | ❌ |
| fx | ✅ 80,165 rows | ❌ | ❌ |
| fed | ✅ 48,174 rows | ❌ | ❌ |
| tariff | ✅ 42,414 rows | ❌ | ❌ |
| volatility | ✅ 35,088 rows | ❌ | ❌ |
| **trump_effect** | ❌ **0 rows** | ❌ | ❌ |

### The Path Forward
1. **Fix trump_effect data** (empty table)
2. **Generate Specialist OOFs** (all 11)
3. **Train L1 Meta-learner**
4. **Build L2 Fusion with regime detection**
5. **Implement L3 Monte Carlo**
6. **Dashboard integration**

---

## 14. NEXT STEPS

1. ☑ Examined feature engineering code (COMPLETE)
2. ☑ Mapped specialist bucket → feature module relationships (COMPLETE)
3. ☑ Documented Core + Specialist architecture (COMPLETE)
4. ☐ **Populate trump_effect specialist table** (PRIORITY)
5. ☐ **Generate Specialist OOFs for all 11 buckets**
6. ☐ **Create WASDE backfill ingestion script**
7. ☐ **Ingest Brazil INMET weather data**
8. ☐ **Implement position change velocity features**
9. ☐ **Train L1 Meta-learner on combined OOFs**

---

## 15. TABLE ARCHITECTURE DECISION (CRITICAL - Session 3)

### The Answer: Option A+ (Dataset-Level Facts + Reference Data)

**Decision:** Keep dataset-level tables (raw.fx_spot_1d, raw.market_futures_1d) BUT add proper identity, provenance, and uniqueness at the database level.

**Why current tables feel "too generic":**
It's NOT because multiple symbols share one table - that's normal and correct.
It feels generic because tables don't enforce:
- **Identity:** "What exactly is this series?" (instrument master)
- **Provenance:** "Which source produced this row?"
- **Uniqueness:** "One truth per (instrument, timestamp, source)"

Without these, the `symbol` column becomes a junk drawer.

### Current State (Verified 2026-01-06)

**metadata schema:** Does NOT exist yet
**raw.fx_spot_1d columns:** id, pair, as_of_date, rate, created_at (NO instrument_id)
**raw.market_futures_1d columns:** as_of_date, symbol, OHLCV, source, ingested_at (NO instrument_id)

**Good news:** Some tables already have composite UNIQUE constraints:
- `cftc_cot_1w`: UNIQUE(report_date, symbol)
- `cftc_cits_1w`: UNIQUE(report_date, contract_code, report_type)
- `yahoo_equity_1d`: UNIQUE(symbol, as_of_date)
- `weather_noaa_1d`: UNIQUE(station_id, as_of_date)
- `usda_wasde_1m`: UNIQUE(report_date, commodity, country, metric)

**Bad news:** Core tables missing uniqueness:
- `fx_spot_1d`: NO unique constraint
- `market_futures_1d`: NO unique constraint
- `fred_observations_1d`: Need to check

### Architecture To Implement

#### 1. Metadata Schema (Reference Data Layer)

```sql
-- metadata.instrument: One row per canonical series
CREATE TABLE metadata.instrument (
    id BIGSERIAL PRIMARY KEY,
    canonical_symbol TEXT UNIQUE NOT NULL,  -- ZL, USDCNY, FEDFUNDS
    asset_class TEXT NOT NULL,  -- FUTURE, FX, MACRO, EQUITY, WEATHER
    domain TEXT,  -- crush, china, fx, fed (specialist routing)
    currency TEXT,
    unit TEXT,
    point_value DECIMAL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- metadata.source: One row per vendor/feed
CREATE TABLE metadata.source (
    id BIGSERIAL PRIMARY KEY,
    code TEXT UNIQUE NOT NULL,  -- FRED, CFTC, USDA, DATABENTO, NOAA, YAHOO
    vendor TEXT,
    url TEXT,
    default_tz TEXT,
    license_notes TEXT
);

-- metadata.instrument_alias: Maps vendor symbols to canonical
CREATE TABLE metadata.instrument_alias (
    id BIGSERIAL PRIMARY KEY,
    instrument_id BIGINT REFERENCES metadata.instrument(id),
    source_id BIGINT REFERENCES metadata.source(id),
    source_symbol TEXT NOT NULL,  -- Vendor's symbol (FRED series ID, etc.)
    UNIQUE(source_id, source_symbol)
);

-- metadata.instrument_group: Domain groupings (Option C engine)
CREATE TABLE metadata.instrument_group (
    id BIGSERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,  -- fx_major, fx_em, futures_oilseeds
    description TEXT
);

-- metadata.instrument_group_member: Group membership
CREATE TABLE metadata.instrument_group_member (
    group_id BIGINT REFERENCES metadata.instrument_group(id),
    instrument_id BIGINT REFERENCES metadata.instrument(id),
    PRIMARY KEY (group_id, instrument_id)
);
```

#### 2. Raw Fact Tables (Option A+ Form)

Every raw table gets:
- `instrument_id` (FK → metadata.instrument.id)
- `source_id` (FK → metadata.source.id)
- Composite UNIQUE constraint: `(instrument_id, date, source_id)`
- Index on `(instrument_id, date)` for dominant query pattern

**Example: raw.fx_spot_1d after upgrade:**
```sql
ALTER TABLE raw.fx_spot_1d ADD COLUMN instrument_id BIGINT;
ALTER TABLE raw.fx_spot_1d ADD COLUMN source_id BIGINT;
ALTER TABLE raw.fx_spot_1d ADD CONSTRAINT fk_fx_instrument 
    FOREIGN KEY (instrument_id) REFERENCES metadata.instrument(id);
ALTER TABLE raw.fx_spot_1d ADD CONSTRAINT fk_fx_source 
    FOREIGN KEY (source_id) REFERENCES metadata.source(id);
ALTER TABLE raw.fx_spot_1d ADD CONSTRAINT uq_fx_spot 
    UNIQUE (instrument_id, as_of_date, source_id);
CREATE INDEX idx_fx_spot_inst_date ON raw.fx_spot_1d(instrument_id, as_of_date);
```

**Example: raw.market_futures_1d with series_variant:**
```sql
-- For futures, need series_variant for continuous vs contract bars
ALTER TABLE raw.market_futures_1d ADD COLUMN instrument_id BIGINT;
ALTER TABLE raw.market_futures_1d ADD COLUMN source_id BIGINT;
ALTER TABLE raw.market_futures_1d ADD COLUMN series_variant TEXT DEFAULT 'CONTINUOUS_FRONT';
-- UNIQUE includes series_variant to distinguish roll methods
ALTER TABLE raw.market_futures_1d ADD CONSTRAINT uq_futures 
    UNIQUE (instrument_id, as_of_date, source_id, series_variant);
CREATE INDEX idx_futures_inst_date ON raw.market_futures_1d(instrument_id, series_variant, as_of_date);
```

#### 3. Option C = Groups + Views (NOT New Tables)

Domain-level segmentation (fx_em, fx_major, futures_oilseeds) is implemented as:
- Group definitions in `metadata.instrument_group`
- Membership mappings in `metadata.instrument_group_member`
- SQL views for convenience queries

**Example view:**
```sql
CREATE VIEW raw.v_fx_em_1d AS
SELECT f.* 
FROM raw.fx_spot_1d f
JOIN metadata.instrument_group_member gm ON f.instrument_id = gm.instrument_id
JOIN metadata.instrument_group g ON gm.group_id = g.id
WHERE g.name = 'fx_em';
```

### Why This Architecture

1. **Scales to 87+ symbols** without schema migrations
2. **Multiple vendors** can coexist (source_id distinguishes)
3. **New series** just add rows to instrument table
4. **Upsert-safe** via composite UNIQUE constraints
5. **Query-optimized** via proper indexes
6. **Domain routing** via groups, not table proliferation

### Migration Plan Required

**Before ANY more ingestion:**
1. Create metadata schema + tables
2. Populate metadata.source (FRED, CFTC, USDA, DATABENTO, NOAA, YAHOO, QUANDL)
3. Populate metadata.instrument (all canonical symbols we track)
4. Populate metadata.instrument_alias (vendor symbol → canonical mappings)
5. ALTER existing raw tables to add instrument_id, source_id
6. Backfill instrument_id from existing symbol columns via alias lookup
7. Add UNIQUE constraints and indexes
8. Create domain groups and views

### Why Option B Is Dead

One table per symbol (raw.fx_usdcny_1d, raw.fx_usdbrl_1d) means:
- Schema migration every time you add a symbol
- 87+ tables just for futures
- Unmaintainable at scale
- **Hard no.**

---

## 16. SESSION 3 WORK LOG (2026-01-06)

### What Was Actually Done

1. **Verified CITS Ingestion Success**
   - `raw.cftc_cits_1w` confirmed: 34,428 rows
   - SOYBEAN_OIL (ZL): 2,652 rows from 2013-01-08 to 2025-09-16
   - Data is REAL - Index Trader positioning (longs, shorts, net)
   - Has proper UNIQUE constraint: (report_date, contract_code, report_type)

2. **Architecture Decision Made: Option A+**
   - Keep dataset-level tables (deferred metadata schema for now)
   - Focus on constraints + cleanup first (minimal change approach)

---

## 17. SESSION 4 WORK LOG (2026-01-05)

### Complete Database Audit

Performed comprehensive audit of all 14 raw tables:

| Table | Unique Identifiers | Rows |
|-------|-------------------|------|
| market_futures_1d | 87 symbols | 418,864 |
| market_futures_1h | 84 symbols | 4,967,276 |
| fx_spot_1d | 30→9 pairs | 211,752→72,135 |
| fred_observations_1d | 157 series | 491,215 |
| cftc_cot_1w | 24 symbols | 18,355 |
| cftc_cits_1w | 13 contracts | 34,428 |
| yahoo_equity_1d | 3 symbols | 9,534 |
| weather_noaa_1d | 57 stations | 215,320 |
| usda_wasde_1m | 71 combos | 10,164 |
| usda_export_sales_1w | 21 combos | 6,412 |
| epa_rin_prices_1d | 4 types | 208 |
| news_articles_1d | 112 sources | 5,264 |
| options_futures_1d | 14,611 | 28,648 |

Full audit saved to: `db_insights/DATABASE_SYMBOL_AUDIT_20260105.md`

### Key Findings

1. **21 FX pairs duplicated** between `fx_spot_1d` AND `fred_observations_1d`
   - DEXBZUS, DEXCHUS, DTWEXBGS, etc. - all FRED series
   - Should NOT be duplicated in fx_spot_1d

2. **Missing UNIQUE constraints** on core tables:
   - `raw.fx_spot_1d` - NO constraint
   - `raw.market_futures_1d` - NO constraint

3. **Source separation clarity:**
   - FRED FX → belongs in `fred_observations_1d` only
   - Yahoo FX → belongs in `fx_spot_1d` (EURUSD, GBPUSD, etc.)

### Database Changes Executed (2026-01-05)

**CHANGE 1: Delete FRED-sourced rows from fx_spot_1d**
```
Rows before: 211,752
Rows deleted: 139,617 (21 FRED pairs)
Rows after: 72,135 (9 Yahoo pairs only)
Remaining: AUDUSD, EURUSD, GBPUSD, NZDUSD, USDBRL, USDCAD, USDCHF, USDCNY, USDJPY
```

**CHANGE 2: Add UNIQUE constraint to market_futures_1d**
```sql
ALTER TABLE raw.market_futures_1d 
ADD CONSTRAINT market_futures_1d_symbol_date_uq 
UNIQUE (symbol, as_of_date);
```

**CHANGE 3: Add UNIQUE constraint to fx_spot_1d**
```sql
ALTER TABLE raw.fx_spot_1d 
ADD CONSTRAINT fx_spot_1d_pair_date_uq 
UNIQUE (pair, as_of_date);
```

### Verification Results

| Check | Result |
|-------|--------|
| fx_spot_1d rows | 72,135 ✅ |
| fx_spot_1d pairs | 9 (Yahoo only) ✅ |
| fx_spot_1d UNIQUE | `fx_spot_1d_pair_date_uq` ✅ |
| market_futures_1d UNIQUE | `market_futures_1d_symbol_date_uq` ✅ |
| FX/FRED overlap | 0 ✅ |

### Architecture Notes

**Minimal Change Approach Adopted:**
- No new schemas created
- No metadata layer (deferred)
- No data movement between schemas
- Just cleanup + constraints

**Databento Source Update:**
- Subscription expired - no longer available
- 1h data (2010-2025) is frozen
- Need alternative source for daily updates (Yahoo, Barchart, etc.)

**1h Data Column:** `ts_event` is Databento's naming convention
- `ts_event` = market event timestamp
- `ts_recv` = network receive timestamp (not present)
- Good naming - unambiguous

**Separation of Concerns (Final State):**
- Yahoo FX → `raw.fx_spot_1d` (9 pairs)
- FRED FX → `raw.fred_observations_1d` (21 DEX*/DTW* series)
- Futures → `raw.market_futures_1d` (87 symbols, now with uniqueness)

### What Was NOT Changed

- No metadata schema created (deferred - minimal approach)
- No instrument_id/source_id columns added
- No silver layer implemented
- No COT soft commodity backfill (CC, CT, KC, MWE)

---

*Last Updated: 2026-01-05 (Session 4 - DB Cleanup & Constraints)*
*Operating Mode: Accuracy > Speed. Always.*
