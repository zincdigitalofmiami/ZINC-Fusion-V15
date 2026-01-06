# ZINC-FUSION-V15: Data Schema Mapping

## Overview

This document defines the complete data architecture for ZINC-FUSION-V15, mapping all external data sources to:
1. **Raw Layer** - Immutable, append-only storage
2. **Specialist Buckets** - 10 economic drivers that vote on price direction
3. **Core Model** - Price history + minimal macro context (NO specialist features)
4. **Dashboard** - Chart-ready aggregated data

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           EXTERNAL DATA SOURCES                              │
├─────────────┬─────────────┬─────────────┬─────────────┬─────────────────────┤
│ CFTC COT    │ USDA WASDE  │ EIA         │ FRED        │ Market Futures      │
│ (1986+)     │ (1973+)     │ (1993+)     │ (1871+)     │ (1990+)             │
│             │ FAS Exports │ EPA RIN     │             │ Weather (2005+)     │
│             │ (1990+)     │ (2010+)     │             │ FX Spot (1981+)     │
└──────┬──────┴──────┬──────┴──────┬──────┴──────┬──────┴──────────┬──────────┘
       │             │             │             │                 │
       ▼             ▼             ▼             ▼                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              RAW LAYER (Prisma)                              │
│  Immutable, append-only, full history preserved                             │
├─────────────────────────────────────────────────────────────────────────────┤
│ raw.cftc_cot_1w         │ raw.market_futures_1d    │ raw.fred_observations_1d │
│ raw.usda_wasde_1m       │ raw.fx_spot_1d           │ raw.weather_observations │
│ raw.usda_exports_1w     │ raw.epa_rin_prices_1d    │ raw.eia_observations_1w  │
└──────────────────────────────────────────────────────────────────────────────┘
                                     │
                    ┌────────────────┼────────────────┐
                    │                │                │
                    ▼                ▼                ▼
┌──────────────────────┐  ┌──────────────────────┐  ┌──────────────────────────┐
│    CORE FEATURES     │  │  SPECIALIST BUCKETS  │  │     REFERENCE TABLES     │
│   (Limited scope)    │  │   (10 drivers)       │  │                          │
├──────────────────────┤  ├──────────────────────┤  ├──────────────────────────┤
│ - ZL price/returns   │  │ 1. Crush             │  │ - cv_folds               │
│ - ZL vol (21d, 63d)  │  │ 2. China             │  │ - bucket_config          │
│ - VIX                │  │ 3. FX                │  │ - drivers_static         │
│ - DXY (dollar index) │  │ 4. Fed               │  │ - weather_stations       │
│ - 10Y Treasury       │  │ 5. Tariff            │  │                          │
│ - Crude oil          │  │ 6. Energy            │  │                          │
│                      │  │ 7. Biofuel           │  │                          │
│ NO specialist-level  │  │ 8. Palm              │  │                          │
│ features allowed     │  │ 9. Volatility        │  │                          │
│                      │  │ 10. Substitutes      │  │                          │
└──────────┬───────────┘  └──────────┬───────────┘  └──────────────────────────┘
           │                         │
           ▼                         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           TRAINING LAYER                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│ training.core_matrix_full_1d      │ OOF predictions → oof_predictions       │
│ training.specialist_{bucket}_1d   │ LASSO coefficients → lasso_coefficients │
│ training.cv_folds                 │ Ensemble weights → meta_ensemble        │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           FORECAST LAYER                                     │
│  Chart-ready, append-only (never overwrite historical forecasts)            │
├─────────────────────────────────────────────────────────────────────────────┤
│ forecast_quantiles   │ driver_scores   │ chart_overlays   │ risk_metrics    │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              DASHBOARD                                       │
│  Pre-digested payloads, no raw model internals exposed                      │
├─────────────────────────────────────────────────────────────────────────────┤
│ /api/forecast/quantiles  │ /api/drivers/latest  │ /api/regime/current       │
│ /api/forecast/bands      │ /api/drivers/series  │ /api/dashboard/summary    │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Data Source → Specialist Mapping

### CFTC COT (Commitment of Traders)

| Field | Specialist | Feature Name | Description |
|-------|------------|--------------|-------------|
| Managed Money Long/Short | china | `cot_managed_money_net` | Spec positioning indicates demand expectations |
| Managed Money Net Change | china | `cot_mm_momentum_4w` | 4-week momentum in spec positioning |
| Commercial Long/Short | tariff | `cot_commercial_net` | Producer/merchant hedging activity |
| Commercial Net Change | tariff | `cot_commercial_hedge_ratio` | Change in hedge ratios |
| Open Interest | volatility | `cot_oi_change_1w` | Weekly OI change signals activity |
| Open Interest | volatility | `cot_oi_concentration` | Concentration of positions |

**Prisma Tables:**
- `raw.cftc_cot_1w` (raw storage)
- `training.specialist_china_1d` (features)
- `training.specialist_tariff_1d` (features)
- `training.specialist_volatility_1d` (features)

---

### USDA WASDE (World Agricultural Supply and Demand Estimates)

| Field | Specialist | Feature Name | Description |
|-------|------------|--------------|-------------|
| Ending Stocks | crush | `usda_ending_stocks` | Tightness of supply |
| Stock-to-Use Ratio | crush | `usda_stock_to_use` | Supply adequacy metric |
| Crush Volume | crush | `usda_crush_volume` | Processing demand |
| Production Forecast | substitutes | `usda_global_production` | World veg oil production |
| China Imports | china | `usda_china_imports` | Chinese soybean demand |
| Argentina/Brazil Exports | substitutes | `usda_sa_exports` | South American competition |

**Prisma Tables:**
- `raw.usda_wasde_1m` (raw storage)
- `training.specialist_crush_1d` (features)
- `training.specialist_china_1d` (features)
- `training.specialist_substitutes_1d` (features)

---

### USDA FAS Export Sales (Weekly)

| Field | Specialist | Feature Name | Description |
|-------|------------|--------------|-------------|
| Weekly Export Inspections | china | `usda_export_pace_weekly` | Current export velocity |
| Cumulative Exports | china | `usda_exports_ytd` | Year-to-date exports |
| Destination: China | china | `usda_china_weekly_pct` | China's share of weekly exports |
| Export Cancellations | tariff | `usda_cancellations` | Trade friction indicator |
| Outstanding Sales | tariff | `usda_outstanding_sales` | Forward commitments |

**Prisma Tables:**
- `raw.usda_export_sales_1w` (raw storage)
- `training.specialist_china_1d` (features)
- `training.specialist_tariff_1d` (features)

---

### EIA Petroleum Data

| Field | Specialist | Feature Name | Description |
|-------|------------|--------------|-------------|
| Crude Oil Stocks | energy | `eia_crude_stocks` | Petroleum inventory levels |
| Refinery Utilization | energy | `eia_refinery_util` | Demand for crude processing |
| Distillate Stocks | energy | `eia_distillate_stocks` | Heating oil/diesel inventory |
| Biodiesel Production | biofuel | `eia_biodiesel_prod` | Renewable fuel output |
| Renewable Diesel | biofuel | `eia_renewable_diesel` | Next-gen biofuel growth |

**Prisma Tables:**
- `raw.eia_observations_1w` (raw storage)
- `training.specialist_energy_1d` (features)
- `training.specialist_biofuel_1d` (features)

---

### EPA RIN Prices

| Field | Specialist | Feature Name | Description |
|-------|------------|--------------|-------------|
| D4 RIN Price | biofuel | `rin_d4` | Biodiesel mandate compliance |
| D6 RIN Price | biofuel | `rin_d6` | Ethanol mandate compliance |
| D4-D6 Spread | biofuel | `rin_d4_d6_spread` | Biodiesel premium |
| RIN as % of Diesel | energy | `rin_compliance_cost` | Mandate cost burden |

**Prisma Tables:**
- `raw.epa_rin_prices_1d` (raw storage)
- `training.specialist_biofuel_1d` (features)
- `training.specialist_energy_1d` (features)

---

### FRED Economic Data

| Field | Specialist | Feature Name | Description |
|-------|------------|--------------|-------------|
| Fed Funds Rate | fed | `fed_funds` | Monetary policy stance |
| 2Y/10Y/30Y Treasury | fed | `treasury_2y/10y/30y` | Rate environment |
| 10Y-2Y Spread | fed | `yield_curve_10y2y` | Recession indicator |
| USD/CNY | fx, china | `usd_cny` | Chinese currency |
| USD/BRL | fx, substitutes | `usd_brl` | Brazilian currency |
| DXY Dollar Index | fx | `dxy` | Broad dollar strength |
| VIX | volatility | `vix` | Market fear gauge |
| Trade Balance | tariff | `trade_balance` | US trade deficit |

**Prisma Tables:**
- `raw.fred_observations_1d` (raw storage)
- `training.specialist_fed_1d` (features)
- `training.specialist_fx_1d` (features)
- `training.specialist_china_1d` (features)
- `training.specialist_tariff_1d` (features)
- `training.specialist_volatility_1d` (features)

---

### Weather (NOAA + NASA POWER)

| Field | Specialist | Feature Name | Description |
|-------|------------|--------------|-------------|
| US Midwest Precip | crush | `weather_usmw_precip_30d` | Crop condition impact |
| US Midwest Temp | crush | `weather_usmw_gdd` | Growing degree days |
| Brazil Precip | substitutes | `weather_br_precip_30d` | SA crop conditions |
| Argentina Precip | substitutes | `weather_ar_precip_30d` | SA crop conditions |
| Palm Belt (SE Asia) | palm | `weather_palm_precip` | Palm production conditions |

**Prisma Tables:**
- `raw.weather_noaa_1d` (raw storage)
- `training.specialist_crush_1d` (features)
- `training.specialist_substitutes_1d` (features)
- `training.specialist_palm_1d` (features)

---

### Market Futures (Databento/Polygon)

| Field | Specialist | Feature Name | Description |
|-------|------------|--------------|-------------|
| ZL (Soybean Oil) | ALL | `zl_close`, `zl_return_*d` | Primary target |
| ZM (Soybean Meal) | crush | `zm_close`, `zm_zl_ratio` | Meal/oil value split |
| ZS (Soybeans) | crush | `zs_close`, `board_crush` | Crush margin |
| CL (Crude Oil) | energy | `cl_close`, `boho_spread` | Energy complex |
| HO (Heating Oil) | energy, biofuel | `ho_close` | Diesel/biodiesel linkage |
| Palm (proxy) | palm, substitutes | `palm_close` | Substitute oil |

**Prisma Tables:**
- `raw.market_futures_1d` (raw storage)
- `raw.market_futures_1h` (intraday)
- All specialist tables (derived features)

---

## Core Model Features (STRICT BOUNDARY)

The core model ONLY sees:

```python
CORE_FEATURES = [
    # Price history (ZL only)
    'zl_return_1d', 'zl_return_5d', 'zl_return_21d',
    'zl_volatility_21d', 'zl_volatility_63d',

    # Minimal macro context (≤5 covariates)
    'vix',                    # Market stress
    'dxy',                    # Dollar strength
    'treasury_10y',           # Rate environment
    'crude_oil',              # Energy linkage
    'sp500_return_21d',       # Risk appetite
]
```

**Core NEVER sees:**
- CFTC COT data (that's for China, Tariff, Volatility specialists)
- USDA fundamentals (that's for Crush, China, Substitutes specialists)
- Weather data (that's for Crush, Substitutes specialists)
- Individual specialist features

---

## Dashboard API Schema

### `/api/forecast/quantiles`
```json
{
  "symbol": "ZL",
  "asOfDate": "2025-12-29",
  "quantiles": [
    {"horizon": 5, "p10": 38.50, "p50": 39.25, "p90": 40.10, "probUp": 0.62},
    {"horizon": 21, "p10": 37.80, "p50": 39.50, "p90": 41.50, "probUp": 0.58},
    {"horizon": 63, "p10": 36.00, "p50": 40.00, "p90": 44.00, "probUp": 0.55}
  ]
}
```

### `/api/drivers/latest`
```json
{
  "asOfDate": "2025-12-29",
  "drivers": [
    {"bucket": "crush", "score": 0.35, "contribution": 0.18, "direction": "bullish"},
    {"bucket": "china", "score": -0.22, "contribution": 0.15, "direction": "bearish"},
    {"bucket": "energy", "score": 0.48, "contribution": 0.14, "direction": "bullish"}
  ]
}
```

### `/api/regime/current`
```json
{
  "regime": "sideways",
  "confidence": 0.72,
  "since": "2025-12-15",
  "characteristics": {
    "volatility": "elevated",
    "trend": "neutral",
    "correlation_regime": "normal"
  }
}
```

---

## Data Quality Requirements

| Source | Frequency | Lag | Validation |
|--------|-----------|-----|------------|
| CFTC COT | Weekly (Tue) | 3 days | Contract codes match |
| USDA WASDE | Monthly | 0 days | Report date valid |
| USDA Exports | Weekly (Thu) | 1 day | Volume > 0 |
| EIA Petroleum | Weekly (Wed) | 1 day | Values in range |
| EPA RIN | Daily | 1 day | Price > 0 |
| FRED | Varies | 0-30 days | Series ID valid |
| Weather | Daily | 1 day | Temp/precip in range |
| Market Futures | Daily | 0 days | OHLC valid |

---

## Non-Negotiable Constraints

1. **Core cannot see specialist features** - Prevents information leakage
2. **Meta layer only sees OOF predictions** - Never raw features
3. **Forecasts are append-only** - Historical reproducibility
4. **cv_folds is single source of truth** - All training uses same splits
5. **Dashboard serves pre-digested data** - No raw model internals exposed
