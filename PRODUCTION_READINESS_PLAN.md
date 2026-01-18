# 🎯 ZINC-FUSION-V15 Production Readiness Plan

**Document Version**: 1.0  
**Date**: 2026-01-18  
**Status**: PLANNING MODE - AWAITING APPROVAL

---

## Executive Summary

**Current State**: Mixed architectural patterns with legacy medallion schemas (`raw.*`, `gold.*`, `silver.*`), redundant MLflow infrastructure, and incomplete institutional schema migration.

**Target State**: Production-ready quantitative forecasting system with institutional schema architecture, Prisma-first data governance, and Grafana-based operational monitoring.

**Validation convention (repo rule)**: run Python via `.venv/bin/python` and tests via `.venv/bin/pytest`.

**Critical Path Timeline**: 8-13 days
1. Remove MLflow infrastructure (1-2 days)
2. Migrate to institutional schemas (3-5 days)
3. Validate training pipeline (2-3 days)
4. Production hardening (2-3 days)

---

## Part 1: MLflow Removal Plan

### 1.1 Why MLflow Must Be Removed

**Verdict**: MLflow is 100% redundant and violates architectural principles.

**Evidence**:
1. **Duplicate Tracking**: `grafana/grafana_registry.py` already writes to Prisma (`model.training_runs`, `model.model_registry`)
2. **Prisma is SoT**: Per AGENTS.md, Prisma Postgres is the single source of truth
3. **Grafana Configured**: Dashboards query Prisma directly - MLflow adds zero value
4. **Operational Overhead**: Requires separate PostgreSQL, MinIO, tracking server, sync scripts
5. **Not Used**: Active training scripts use `GrafanaRegistry`, not MLflow

**What MLflow Claims vs. Reality**:

| MLflow Feature | Prisma Equivalent | Status |
|----------------|-------------------|--------|
| Experiment Tracking | `model.training_runs` | ✅ Exists |
| Model Registry | `model.model_registry` | ✅ Exists |
| Metrics Logging | `model.training_runs.metrics_json` | ✅ Exists |
| Artifact Storage | `model.model_registry.artifact_path` | ✅ Exists |
| OOF Predictions | `training.oof_*_1d` | ✅ Exists |
| Grafana Dashboards | Direct Prisma queries | ✅ Configured |

### 1.2 Files to Remove/Modify

**DELETE (6 files)**:
```
docker/Dockerfile.mlflow
scripts/start-mlflow.sh
scripts/sync_prisma_to_mlflow.py
Docs/MLFLOW_SETUP.md
mlflow.db
mlruns/mlflow.db
```

**MODIFY (3 files)**:
```
docker/docker-compose.yml     → Remove MLflow services (mlflow, mlflow-postgres, minio)
README.md                     → Remove lines 760-779 (MLflow section)
requirements.txt              → Remove mlflow (if present)
```

### 1.3 Step-by-Step Removal Sequence

**Phase 1: Stop MLflow Services (5 minutes)**

```bash
# Stop and remove containers
cd /Volumes/Satechi\ Hub/ZINC-FUSION-V15
docker compose -f docker/docker-compose.yml down mlflow mlflow-postgres minio

# Remove volumes
docker volume rm zinc-fusion-v15_mlflow-postgres-data 2>/dev/null || true
docker volume rm zinc-fusion-v15_mlflow-minio-data 2>/dev/null || true
```

**Phase 2: Remove Files (10 minutes)**

```bash
# Delete MLflow infrastructure
rm docker/Dockerfile.mlflow
rm scripts/start-mlflow.sh
rm scripts/sync_prisma_to_mlflow.py
rm Docs/MLFLOW_SETUP.md
rm mlflow.db
rm -rf mlruns/

# Backup docker-compose.yml before editing
cp docker/docker-compose.yml docker/docker-compose.yml.backup
```

**Phase 3: Update docker-compose.yml (15 minutes)**

Remove these services from `docker/docker-compose.yml`:
- `mlflow-postgres` (lines ~20-40)
- `minio` (lines ~41-60)
- `minio-init` (lines ~61-68)
- `mlflow` (lines ~70-96)

Remove these volumes:
- `mlflow-postgres-data`
- `mlflow-minio-data`

**Phase 4: Update Documentation (10 minutes)**

Remove MLflow section from `README.md` (lines 760-779).

**Phase 5: Validation (10 minutes)**

```bash
# Verify no MLflow imports remain
grep -r "import mlflow" --include="*.py" src/ scripts/ grafana/
grep -r "from mlflow" --include="*.py" src/ scripts/ grafana/

# Expected: No results (sync script already deleted)

# Verify GrafanaRegistry is operational
.venv/bin/python -c "from grafana.grafana_registry import GrafanaRegistry; print('✅ GrafanaRegistry OK')"
```

**Success Criteria**:
- ✅ No MLflow containers running
- ✅ No MLflow imports in codebase
- ✅ GrafanaRegistry functional
- ✅ Grafana dashboards still query Prisma

---

## Part 2: Institutional Schema Migration

### 2.1 Schema Naming Principles

**CRITICAL**: Remove ALL version numbering (V1/V2/V3) and redundant naming.

**Institutional Naming Rules**:
1. **Pattern**: `{schema}.{entity}_{granularity}`
2. **No Redundancy**: `model.registry` NOT `model.model_registry`
3. **No Versions**: `features.elite_1d` NOT `features.elite_v2_1d`
4. **Mandatory Suffixes**: `_1d`, `_1h`, `_1w`, `_1m`, `_event`, `_static`

**Allowed Schemas (11 total)**:
```
mkt         → Market data (futures, options, fx)
econ        → Economic indicators (FRED)
pos         → Positioning (CFTC)
supply      → Supply/demand (USDA, EPA)
alt         → Alternative data (news, weather, events)
features    → Derived features
training    → Training artifacts
model       → Model outputs and registry
analytics   → Dashboard/presentation
metadata    → Symbol mappings, governance
ops         → Operational health
```

**BANNED Schemas**:
```
raw.*       → Migrate to domain schemas (mkt/econ/alt/pos/supply)
gold.*      → Migrate to features.*
silver.*    → Migrate to features.* or alt.*
archive.*   → Use external backups
bronze.*    → Never existed, but explicitly banned
```

### 2.2 Complete Legacy → Institutional Mapping

**Market Data (mkt schema)**:
```
raw.market_futures_1d      → mkt.futures_1d
raw.market_futures_1h      → mkt.futures_1h
raw.options_futures_1d     → mkt.options_1d
raw.fx_spot_1d             → mkt.fx_1d
```

**Economic Data (econ schema)**:
```
raw.fred_observations_1d   → econ.{domain}_1d (split by series category)
  - FRED rates series      → econ.rates_1d
  - FRED inflation series  → econ.inflation_1d
  - FRED labor series      → econ.labor_1d
  - FRED activity series   → econ.activity_1d
  - FRED vol indices       → econ.vol_indices_1d
  - FRED commodities       → econ.commodities_1d
  - FRED FX series         → econ.fx_1d
  - FRED money supply      → econ.money_1d
```

**Positioning Data (pos schema)**:
```
raw.cftc_cot_1w            → pos.cftc_1w
raw.cftc_cits_1w           → pos.cftc_cits_1w
```

**Supply/Demand Data (supply schema)**:
```
raw.usda_wasde_1m          → supply.usda_wasde_1m
raw.usda_export_sales_1w   → supply.usda_exports_1w
raw.epa_rin_prices_1d      → supply.epa_rin_1d
```

**Alternative Data (alt schema)**:
```
raw.news_articles_1d       → alt.news_1d
raw.news_articles_event    → alt.news_event
raw.weather_noaa_1d        → alt.weather_1d
raw.whitehouse_actions_event → alt.whitehouse_event
silver.news_scored_1d      → alt.news_scored_1d (requires Prisma schema approval; see 2.5)

```

**Features (features schema)**:
```
gold.elite_indicators_1d   → features.elite_1d
gold.options_features_1d   → features.options_1d
gold.weather_features_1d   → features.weather_1d
gold.intel_drops           → features.intel_drops
```

**Training (training schema)**:
```
training.core_matrix_curated_1d → training.matrix_1d
training.oof_core_zl_1d         → training.oof_core_1d
training.specialist_*_curated   → training.specialist_*_1d
```

### 2.3 Column Standardization

**Time Columns**:
```
Landing schemas (mkt/econ/alt/pos/supply):
  - Use: event_date (DATE)
  - Intraday: event_time (TIMESTAMPTZ)

Derived schemas (features/training):
  - Use: trade_date (DATE)
  - Reason: Aligns with trading calendar

Model outputs (model/analytics):
  - Use: as_of_date (DATE) for forecast reference
  - Use: target_date (DATE) for prediction target
```

**Metadata Columns (All Tables)**:
```
source          VARCHAR   → Data provider (e.g., 'YAHOO', 'FRED', 'USDA')
ingested_at     TIMESTAMPTZ → When row was inserted
knowledge_time  TIMESTAMPTZ → When data became known (optional)
row_hash        VARCHAR   → Deduplication key (optional)
```

### 2.4 File-by-File Migration Checklist

**PRIORITY 1: Production API (CRITICAL)**

**File**: `src/fusion/api/server.py`

Current violations:
```python
FROM raw.epa_rin_prices_1d
FROM raw.weather_noaa_1d
FROM raw.news_articles_1d
FROM gold.intel_drops
```

Required changes:
```python
raw.epa_rin_prices_1d  → supply.epa_rin_1d
raw.weather_noaa_1d    → alt.weather_1d (raw) OR features.weather_1d (aggregated)
raw.news_articles_1d   → alt.news_1d
gold.intel_drops       → features.intel_drops
```

Column mappings:
- `event_date` stays `event_date` for alt/supply tables
- `title` → `headline` in alt.news_1d
- All other columns match Prisma schema

**File**: `src/fusion/pulse/storage.py`

Current violations:
```python
INSERT INTO gold.intel_drops
SELECT FROM gold.intel_drops
```

Required changes:
```python
gold.intel_drops → features.intel_drops
```

No column changes needed (Prisma schema matches).

**File**: `scripts/generate_core_forecasts.py`

Current violations:
```python
INSERT INTO model.forecast_quantiles
```

Schema mismatch:
- Code writes to `model.forecast_quantiles`
- Prisma defines table under `@@schema("forecasts")`
- Actual table: `forecasts.forecast_quantiles`

Required changes:
```python
model.forecast_quantiles → forecasts.forecast_quantiles
```

**PRIORITY 2: Training Pipeline**

**File**: `scripts/preflight_52model.py`

Current violations (extensive):
```python
raw.market_futures_1d
raw.fx_spot_1d
raw.options_futures_1d
raw.fred_observations_1d
raw.weather_noaa_1d
raw.cftc_cot_1w
raw.usda_export_sales_1w
raw.usda_wasde_1m
raw.epa_rin_prices_1d
raw.whitehouse_actions_event
```

Required changes:
```python
raw.market_futures_1d      → mkt.futures_1d
raw.fx_spot_1d             → mkt.fx_1d
raw.options_futures_1d     → mkt.options_1d
raw.fred_observations_1d   → econ.* (domain-split)
raw.weather_noaa_1d        → alt.weather_1d
raw.cftc_cot_1w            → pos.cftc_1w
raw.usda_export_sales_1w   → supply.usda_exports_1w
raw.usda_wasde_1m          → supply.usda_wasde_1m
raw.epa_rin_prices_1d      → supply.epa_rin_1d
raw.whitehouse_actions_event → BLOCKED (see 2.5)
```

**File**: `scripts/audit_core_training_data.py`

Current violations:
```python
raw.market_futures_1d
gold.elite_indicators_1d
raw.fred_observations_1d
```

Required changes:
```python
raw.market_futures_1d    → mkt.futures_1d
gold.elite_indicators_1d → features.elite_1d (event_date → trade_date)
raw.fred_observations_1d → econ.*
```

**File**: `scripts/populate_core_matrix.py`

Status: **RETIRE OR REWRITE**

Reason: Legacy matrix builder using raw.* tables. Modern path is `src/fusion/core_training/phase3_build_core_matrix.py`.

Decision needed:
- Option A: Delete this script (recommended)
- Option B: Rewrite to use mkt.futures_1d + econ.* → training.matrix_1d

**PRIORITY 3: Ingestion Layer (Frontend Inngest Jobs)**

**File**: `frontend/src/inngest/yahoo-eod.ts`

Current violations:
```typescript
INSERT INTO raw.market_futures_1d
```

Required changes:
```typescript
raw.market_futures_1d → mkt.futures_1d
```

Column alignment:
- `event_date`, `symbol`, `open`, `high`, `low`, `close`, `volume` → All exist in Prisma
- Add: `source = 'YAHOO'`, `ingested_at = NOW()`

**Other Inngest Jobs to Migrate**:
```
frontend/src/inngest/fx-spot-daily.ts        → mkt.fx_1d
frontend/src/inngest/cftc-weekly.ts          → pos.cftc_1w
frontend/src/inngest/usda-export-sales-weekly.ts → supply.usda_exports_1w
frontend/src/inngest/usda-wasde-monthly.ts   → supply.usda_wasde_1m
frontend/src/inngest/epa-rin-prices-daily.ts → supply.epa_rin_1d
frontend/src/inngest/noaa-weather-daily.ts   → alt.weather_1d
frontend/src/inngest/fred-daily.ts           → econ.* (domain routing)
frontend/src/inngest/whitehouse-press.ts     → alt.news_1d OR alt.whitehouse_event
frontend/src/inngest/barchart-zl-news.ts     → alt.news_1d
```

**PRIORITY 4: Validators & Monitoring**

**File**: `src/fusion/validators/schema_contract.py`

Current state: Validates raw.* naming contract

Required changes:
- **REWRITE** to validate institutional schema contract
- Check: No raw/gold/silver references in runtime code
- Check: All tables follow `{schema}.{entity}_{granularity}` pattern
- Check: Required schemas exist (mkt/econ/features/training/model/analytics/metadata/ops)

**File**: `src/fusion/validators/freshness_monitor.py`

Current violations:
```python
Monitor raw.* tables for freshness
```

Required changes:
```python
Monitor: mkt.*, econ.*, alt.*, pos.*, supply.* (landing schemas)
Optional: features.* (derived schemas)
```

**File**: `src/fusion/validators/anomaly_detection.py`

Current violations:
```python
UPDATE raw.market_futures_1d SET anomaly_flag = ...
UPDATE raw.weather_noaa_1d SET anomaly_flag = ...
```

**CRITICAL ISSUE**: Violates append-only landing posture.

Required changes:
- **Option A (Recommended)**: Write anomaly events to `ops.anomaly_events` (append-only log)
- **Option B**: Add anomaly columns to V2 tables (requires schema approval)
- **Option C**: Retire this script

### 2.5 Blocked Items Requiring Governance Decisions

**1. raw.whitehouse_actions_event**

Issue: No corresponding table in Prisma under allowed schemas.

Options:
- **A**: Migrate to `alt.news_1d` with `source='WHITEHOUSE'`
- **B**: Create `alt.whitehouse_event` (requires schema approval)
- **C**: Create `alt.events_1d` (generalized event table)

Recommendation: **Option A** (simplest, reuses existing table)

**2. silver.news_scored_1d**

Issue: Multiple scripts read/write this table, but:
- `silver` schema is banned
- Target is `alt.news_scored_1d`, but Prisma does not currently define that table

Options:
- **A (TARGET / REQUIRES APPROVAL)**: Create `alt.news_scored_1d` and migrate `silver.news_scored_1d` into it
- **B (ONLY IF OVERRIDDEN)**: Merge sentiment columns into `alt.news_1d`

Recommendation: **Option A** (matches the stated migration target; blocked until Prisma schema + migration exists)

**3. Output Schema: forecasts.* vs model.***

Issue: Prisma places `forecast_quantiles` under `forecasts` schema, but V2 docs describe `model.*`.

Options:
- **A**: Align code to Prisma (use `forecasts.*`)
- **B**: Migrate Prisma tables to `model.*` schema (requires schema approval)

Recommendation: **Option A** (fastest, lowest risk)

### 2.6 Prisma Schema Validation

**Required Tables (Must Exist in Prisma)**:

**mkt schema**:
- ✅ `mkt.futures_1d` (MktFutures1d)
- ✅ `mkt.futures_1h` (MktFutures1h)
- ✅ `mkt.options_1d` (MktOptions1d)
- ✅ `mkt.fx_1d` (MktFx1d)

**econ schema**:
- ✅ `econ.rates_1d` (EconRates1d)
- ✅ `econ.inflation_1d` (EconInflation1d)
- ✅ `econ.labor_1d` (EconLabor1d)
- ✅ `econ.activity_1d` (EconActivity1d)
- ✅ `econ.vol_indices_1d` (EconVolIndices1d)
- ✅ `econ.commodities_1d` (EconCommodities1d)
- ✅ `econ.fx_1d` (EconFx1d)
- ✅ `econ.money_1d` (EconMoney1d)

**pos schema**:
- ✅ `pos.cftc_1w` (PosCftc1w)
- ✅ `pos.cftc_cits_1w` (PosCftcCits1w)

**supply schema**:
- ✅ `supply.usda_wasde_1m` (SupplyUsdaWasde1m)
- ✅ `supply.usda_exports_1w` (SupplyUsdaExports1w)
- ✅ `supply.epa_rin_1d` (SupplyEpaRin1d)

**alt schema**:
- ✅ `alt.news_1d` (AltNews1d)
- ✅ `alt.news_event` (AltNewsEvent)
- ✅ `alt.weather_1d` (AltWeather1d)
- ❓ `alt.news_scored_1d` (MISSING - requires schema approval)
- ❓ `alt.whitehouse_event` (MISSING - needs decision)

**features schema**:
- ✅ `features.elite_1d` (FeaturesElite1d)
- ✅ `features.options_1d` (FeaturesOptions1d)
- ✅ `features.weather_1d` (FeaturesWeather1d)
- ✅ `features.intel_drops` (IntelDrop)

**training schema**:
- ✅ `training.matrix_1d` (TrainingMatrix1d)
- ✅ `training.oof_core_1d` (TrainingOofCore1d)
- ✅ `training.oof_*_1d` (11 specialist tables)
- ✅ `training.specialist_*_1d` (11 specialist feature tables)

**model schema**:
- ✅ `model.model_registry` (ModelRegistry)
- ✅ `model.training_runs` (TrainingRuns)

**forecasts schema**:
- ✅ `forecasts.forecast_quantiles` (ForecastQuantiles)

**Validation Command**:
```bash
cd /Volumes/Satechi\ Hub/ZINC-FUSION-V15
npx prisma validate
```

---

## Part 3: Training Pipeline Readiness Assessment

### 3.1 Five-Phase Training Flow Validation

**PHASE 1: Data Ingestion (No ML)**

Status: **PARTIALLY READY** - Requires schema migration

Current state:
```
✅ Yahoo/Barchart → raw.market_futures_1d (needs migration to mkt.futures_1d)
✅ FRED → raw.fred_observations_1d (needs migration to econ.*)
✅ CFTC → raw.cftc_cot_1w (needs migration to pos.cftc_1w)
✅ USDA → raw.usda_* (needs migration to supply.*)
✅ Weather → raw.weather_noaa_1d (needs migration to alt.weather_1d)
✅ News → raw.news_articles_1d (needs migration to alt.news_1d)
```

Required actions:
1. Migrate all Inngest jobs to write to institutional schemas
2. Update FRED router (`src/fusion/ingestion/router.py`) to write to econ.* domain tables
3. Validate data freshness monitoring uses new schemas

**PHASE 2: Feature Engineering (No ML)**

Status: **READY** - Feature modules exist

Current state:
```
✅ features.elite_1d    ← 27 technical indicators (src/fusion/features/elite.py)
✅ features.options_1d  ← IV/Greeks aggregation (src/fusion/features/options.py)
✅ features.weather_1d  ← Regional weather (src/fusion/features/weather.py)
```

Validation needed:
- Confirm feature modules read from mkt.* (not raw.*)
- Verify output columns match Prisma schema
- Test feature generation end-to-end

**PHASE 3: Build Feature Matrix (No ML)**

Status: **READY** - Matrix builder exists

Current state:
```
✅ training.matrix_1d ← JOIN of elite + options + weather + econ + fx
   Script: src/fusion/core_training/phase3_build_core_matrix.py
   Features: ~130 columns
   Coverage: 1980-present for ZL
```

Validation needed:
- Confirm reads from features.* (not gold.*)
- Verify ~130 feature count
- Check date coverage (1980+ for strategic horizons, 2020+ for tactical)

**PHASE 4: Train L0 Specialists (11 models, parallel)**

Status: **ARCHITECTURE READY** - Needs execution

Specialist buckets:
```
1.  training.specialist_biofuel_1d      → training.oof_biofuel_1d
2.  training.specialist_china_1d        → training.oof_china_1d
3.  training.specialist_crush_1d        → training.oof_crush_1d
4.  training.specialist_energy_1d       → training.oof_energy_1d
5.  training.specialist_fed_1d          → training.oof_fed_1d
6.  training.specialist_fx_1d           → training.oof_fx_1d
7.  training.specialist_palm_1d         → training.oof_palm_1d
8.  training.specialist_substitutes_1d  → training.oof_substitutes_1d
9.  training.specialist_tariff_1d       → training.oof_tariff_1d
10. training.specialist_trump_effect_1d → training.oof_trump_effect_1d
11. training.specialist_volatility_1d   → training.oof_volatility_1d
```

Each specialist outputs:
- OOF predictions: p30, p50, p70 × 4 horizons (5d, 21d, 63d, 126d)
- Columns: `trade_date`, `symbol`, `horizon_days`, `p30`, `p50`, `p70`, `target_value`, `trained_at`, `run_hash`

Validation needed:
- Confirm specialist feature tables exist in Prisma
- Verify OOF table schemas match contract
- Test AutoGluon quantile regression configuration

**PHASE 5: Train L0 Core (1 model)**

Status: **READY** - Core training exists

Current state:
```
✅ training.matrix_1d → training.oof_core_1d
   Script: scripts/train_core_oof.py
   Tactical (5d, 21d): Chronos-Bolt + RecursiveTabular, 2020+ data
   Strategic (63d, 126d): GA-VMD-LSTM, 1980+ data
```

Validation needed:
- Confirm OOF output format (p30/p50/p70, not p10/p90)
- Verify horizon-specific data windows
- Test quantile monotonicity enforcement

**PHASE 6: Train L1 Meta-Ensemble (1 model)**

Status: **ARCHITECTURE READY** - Needs implementation

Meta-learner inputs:
```
training.meta_inputs_1d (144 columns):
  - Core: 12 columns (4 horizons × 3 quantiles)
  - Specialists: 132 columns (11 specialists × 4 horizons × 3 quantiles)

Naming convention: {model}_{horizon}_p{quantile}
  - core_5d_p30, core_5d_p50, core_5d_p70
  - biofuel_5d_p30, biofuel_5d_p50, biofuel_5d_p70
  - ... (all 11 specialists × 4 horizons × 3 quantiles)
```

Output:
- Final ensemble predictions: p30, p50, p70 per horizon
- Registered in model.model_registry
- Champion model selection logic

Validation needed:
- Build meta_inputs_1d table from all OOF tables
- Configure AutoGluon for ensemble learning
- Implement champion model promotion logic

### 3.2 Specialist Bucket Configuration

**Big 11 Specialist Taxonomy**:

| Specialist | Variance Contribution | Key Features | Data Sources |
|------------|----------------------|--------------|--------------|
| crush | 28-35% | Soybean-oil-meal spreads | USDA, Barchart |
| china | 16-22% | Import demand, trade flows | GACC, USITC |
| fx | 3-5% | USD/BRL, USD/CNY | FRED, Yahoo |
| fed | 2-4% | Fed funds, policy stance | FRED, FOMC |
| tariff | 3-5% | Trade policy uncertainty | USTR, Federal Register |
| energy | 10-14% | Crude oil, diesel | EIA, Yahoo |
| biofuel | 6-10% | RIN prices, RFS mandates | EPA, EIA |
| palm | 8-12% | Palm oil prices, production | MPOB, Barchart |
| volatility | 2-3% | VIX, OVX, VXGSCLS | CBOE, FRED |
| substitutes | 4-6% | Canola, sunflower, palm | Barchart, ICE |
| trump_effect | 5-10% | EPU, DJT, policy shocks | FRED, Truth Social |

**Feature Routing Validation**:

Each specialist must have:
1. **Feature table**: `training.specialist_{name}_1d` with domain-specific features
2. **OOF table**: `training.oof_{name}_1d` with p30/p50/p70 predictions
3. **Data sources**: Mapped in `src/fusion/ingestion/router.py`

**FRED Series Routing** (from `src/fusion/ingestion/router.py`):
```python
FRED_SERIES_BUCKETS = {
    'crush': ['ZS', 'ZM', 'ZL', 'USDA_CRUSH_MARGIN'],
    'china': ['CHNMAINLANDTPU', 'IMPCH'],
    'fx': ['DEXBZUS', 'DEXCHUS', 'DEXMXUS'],
    'fed': ['FEDFUNDS', 'DGS10', 'T10Y2Y'],
    'tariff': ['EPUTRADE', 'B235RC1Q027SBEA'],
    'energy': ['DCOILWTICO', 'DHOILNYH'],
    'biofuel': ['EPA_RIN_D4', 'EPA_RIN_D6'],
    'palm': ['MPOB_PALM_PRICE'],
    'volatility': ['VIXCLS', 'OVXCLS', 'VXGSCLS'],
    'substitutes': ['CANOLA_PRICE', 'SUNFLOWER_PRICE'],
    'trump_effect': ['USEPUINDXD', 'USEPUINDXM', 'EMVTRADEPOLEMV']
}
```

### 3.3 OOF Table Standardization

**Contract (LOCKED)**:

All OOF tables must follow this schema:
```sql
CREATE TABLE training.oof_{specialist}_1d (
    trade_date      DATE NOT NULL,
    symbol          VARCHAR NOT NULL,
    horizon_days    INTEGER NOT NULL,  -- 5, 21, 63, 126
    window_id       INTEGER,           -- CV fold identifier
    cutoff_date     DATE,              -- Training cutoff
    p30             DECIMAL(18, 6),    -- 30th percentile
    p50             DECIMAL(18, 6),    -- 50th percentile (median)
    p70             DECIMAL(18, 6),    -- 70th percentile
    target_value    DECIMAL(18, 6),    -- Actual realized return
    trained_at      TIMESTAMPTZ,
    run_hash        VARCHAR,
    matrix_version  VARCHAR,
    PRIMARY KEY (trade_date, symbol, horizon_days, window_id)
);
```

**Quantile Contract**:
- **OOF/Stacking**: p30, p50, p70 (procurement pace bands)
- **Risk/MC**: p10, p30, p50, p70, p90 (full tail risk)

**DO NOT MIX**: OOF tables must never contain p10/p90.

**Monotonicity Enforcement**:
```python
# After prediction, enforce p30 ≤ p50 ≤ p70
df['p30'] = df[['p30', 'p50']].min(axis=1)
df['p70'] = df[['p50', 'p70']].max(axis=1)
```

### 3.4 AutoGluon 1.5 Compatibility

**Current AutoGluon Version**: Check with `pip show autogluon.tabular`

**Required Configuration**:

```python
from autogluon.tabular import TabularPredictor

# Quantile regression for specialists
predictor = TabularPredictor(
    label='target_ret_5d',  # or 21d, 63d, 126d
    problem_type='quantile',
    quantile_levels=[0.3, 0.5, 0.7],  # p30, p50, p70
    eval_metric='pinball_loss',
    path='models/specialists/crush_5d/'
)

predictor.fit(
    train_data=df_train,
    presets='medium_quality',  # or 'best_quality' for production
    time_limit=3600,  # 1 hour per model
    num_bag_folds=8,
    num_stack_levels=0  # Disable stacking for speed
)
```

**Feature Matrix Compatibility**:

Verify `training.matrix_1d` contains:
- ✅ Target columns: `target_ret_5d`, `target_ret_21d`, `target_ret_63d`, `target_ret_126d`
- ✅ Feature columns: ~130 features from elite + options + weather + econ
- ✅ Index columns: `trade_date`, `symbol`
- ✅ No nulls in target columns (filter before training)

**Validation Script**:
```bash
python3 scripts/validate_training_tables.py
```

### 3.5 Four-Horizon Support Validation

**Horizon Configuration**:

| Horizon | Days | Type | Data Window | Model Architecture |
|---------|------|------|-------------|-------------------|
| 5d | 5 | Tactical | 2020+ | Chronos-Bolt + RecursiveTabular |
| 21d | 21 | Tactical | 2020+ | Chronos-Bolt + RecursiveTabular |
| 63d | 63 | Strategic | 1980+ | GA-VMD-LSTM |
| 126d | 126 | Strategic | 1980+ | GA-VMD-LSTM |

**Data Availability Tiers**:

| Tier | Data Window | Horizons | Series |
|------|-------------|----------|--------|
| Tier 1 | 2000+ | ALL (5d/21d/63d/126d) | ZL, VIXCLS, DGS10, FEDFUNDS, M2SL, OVXCLS |
| Tier 2 | Limited | Tactical only (5d/21d) | SOFR (2018+), VXGSCLS (2020+) |

**Validation Checks**:
1. Confirm all 4 target columns exist in `training.matrix_1d`
2. Verify sufficient data for strategic horizons (1980+ for ZL)
3. Test horizon-specific model configurations
4. Validate OOF tables contain all 4 horizons

---

## Part 4: Production Hardening Recommendations

### 4.1 Zero-Tolerance Failure Modes

**Principle**: System must FAIL HARD if institutional schemas are missing. No graceful degradation.

**Implementation**:

**Remove ALL fallback logic**:
```python
# ❌ BANNED PATTERN
if _table_exists("raw", "market_futures_1d"):
    df = pd.read_sql("SELECT * FROM raw.market_futures_1d", conn)
else:
    df = pd.read_sql("SELECT * FROM mkt.futures_1d", conn)

# ✅ REQUIRED PATTERN
df = pd.read_sql("SELECT * FROM mkt.futures_1d", conn)
# If table doesn't exist, let it fail with clear error
```

**Add schema validation at startup**:
```python
# src/fusion/validators/schema_guard.py
REQUIRED_SCHEMAS = ['mkt', 'econ', 'pos', 'supply', 'alt', 'features', 'training', 'model']
BANNED_SCHEMAS = ['raw', 'gold', 'silver', 'bronze', 'archive']

def validate_schema_compliance(conn):
    """Fail hard if legacy schemas are referenced."""

    # Check for banned schema usage
    for schema in BANNED_SCHEMAS:
        result = conn.execute(f"""
            SELECT COUNT(*) FROM information_schema.tables
            WHERE table_schema = '{schema}'
        """).fetchone()

        if result[0] > 0:
            raise SchemaViolationError(
                f"CRITICAL: Banned schema '{schema}' still contains {result[0]} tables. "
                f"Migration to institutional schemas is incomplete."
            )

    # Check required schemas exist
    for schema in REQUIRED_SCHEMAS:
        result = conn.execute(f"""
            SELECT COUNT(*) FROM information_schema.schemata
            WHERE schema_name = '{schema}'
        """).fetchone()

        if result[0] == 0:
            raise SchemaViolationError(
                f"CRITICAL: Required schema '{schema}' does not exist."
            )
```

**Call at API startup**:
```python
# src/fusion/api/server.py
from fusion.validators.schema_guard import validate_schema_compliance

@app.on_event("startup")
async def startup_validation():
    conn = get_db_connection()
    validate_schema_compliance(conn)
    conn.close()
```

### 4.2 Data Lineage Validation

**End-to-End Lineage**:

```
External APIs
    ↓
Landing Schemas (mkt/econ/alt/pos/supply)
    ↓
Feature Engineering (features.*)
    ↓
Training Matrices (training.matrix_1d, training.specialist_*_1d)
    ↓
Model Training (AutoGluon)
    ↓
OOF Predictions (training.oof_*_1d)
    ↓
Meta-Ensemble (training.meta_inputs_1d)
    ↓
Final Forecasts (forecasts.forecast_quantiles)
    ↓
Risk Metrics (analytics.risk_metrics)
    ↓
Dashboard (Grafana)
```

**Lineage Tracking Table**:
```sql
CREATE TABLE ops.data_lineage (
    id SERIAL PRIMARY KEY,
    source_table VARCHAR NOT NULL,
    target_table VARCHAR NOT NULL,
    transformation VARCHAR,
    row_count INTEGER,
    processed_at TIMESTAMPTZ DEFAULT NOW(),
    job_id VARCHAR
);
```

**Log lineage at each step**:
```python
def log_lineage(source, target, transformation, row_count, job_id):
    conn.execute("""
        INSERT INTO ops.data_lineage
        (source_table, target_table, transformation, row_count, job_id)
        VALUES (%s, %s, %s, %s, %s)
    """, (source, target, transformation, row_count, job_id))
```

### 4.3 Grafana Monitoring Configuration

**Dashboard Architecture**:

**Dashboard 1: Data Freshness**
- Query: `ops.data_quality_metrics`
- Panels:
  - Latest update timestamp per source
  - Hours since last update (alert if > 24h)
  - Row count trends
  - Completeness percentage

**Dashboard 2: Training Progress**
- Query: `model.training_runs`
- Panels:
  - Active training runs
  - Training time per model
  - Success/failure rates
  - MASE trends over time

**Dashboard 3: Model Performance**
- Query: `training.oof_*_1d` + `model.model_registry`
- Panels:
  - OOF accuracy (MAE, MAPE, coverage)
  - Quantile calibration (empirical vs. target)
  - Specialist contribution weights
  - Champion model metrics

**Dashboard 4: Forecast Quality**
- Query: `forecasts.forecast_quantiles` + `analytics.risk_metrics`
- Panels:
  - Latest forecasts (p30/p50/p70)
  - VaR/CVaR trends
  - Procurement signals
  - Forecast vs. actual (backtest)

**Example Grafana Query** (PostgreSQL data source):
```sql
-- Training run status
SELECT
    started_at,
    model_type,
    specialist_name,
    horizon,
    status,
    training_time_seconds,
    metrics_json->>'mase' AS mase
FROM model.training_runs
WHERE started_at > NOW() - INTERVAL '7 days'
ORDER BY started_at DESC;
```

**Alert Configuration**:
```yaml
# grafana/provisioning/alerting/alerts.yml
groups:
  - name: data_freshness
    interval: 5m
    rules:
      - alert: StaleData
        expr: hours_since_update > 24
        for: 10m
        labels:
          severity: critical
        annotations:
          summary: "Data source {{ $labels.source }} is stale"

  - name: training_failures
    interval: 1m
    rules:
      - alert: TrainingFailed
        expr: status = 'failed'
        labels:
          severity: warning
        annotations:
          summary: "Training run {{ $labels.run_id }} failed"
```

### 4.4 Risk Mitigation & Rollback Procedures

**Pre-Migration Backup**:
```bash
# Backup current database state
pg_dump $DATABASE_URL > backup_pre_migration_$(date +%Y%m%d).sql

# Backup critical tables
pg_dump $DATABASE_URL \
  -t raw.market_futures_1d \
  -t gold.elite_indicators_1d \
  -t training.matrix_1d \
  > backup_critical_tables_$(date +%Y%m%d).sql
```

**Rollback Strategy**:

**If migration fails at any phase**:
1. Stop all ingestion jobs (Inngest)
2. Stop all training jobs
3. Restore from backup:
   ```bash
   psql $DATABASE_URL < backup_pre_migration_YYYYMMDD.sql
   ```
4. Revert code changes (git reset)
5. Restart services

**Validation Checkpoints**:

After each migration phase, run:
```bash
# Phase 1: MLflow removal
python3 -c "from grafana.grafana_registry import GrafanaRegistry; print('✅ OK')"

# Phase 2: Schema migration
npx prisma validate
python3 scripts/validate_db_state.py

# Phase 3: Training pipeline
python3 scripts/validate_training_tables.py
python3 scripts/preflight_52model.py

# Phase 4: Production hardening
python3 src/fusion/validators/schema_guard.py
curl http://localhost:8000/health
```

**Canary Deployment**:

Test migration on subset of data first:
1. Create test database: `zinc_fusion_test`
2. Migrate schema
3. Ingest 1 week of data
4. Run training on single specialist
5. Validate outputs
6. If successful, proceed with production migration

---

## Part 5: Implementation Sequence

### 5.1 Prioritized Migration Steps

**PHASE 1: MLflow Removal (1-2 days)**

**Day 1 Morning**:
- [ ] Stop MLflow services
- [ ] Remove MLflow files
- [ ] Update docker-compose.yml
- [ ] Remove MLflow from documentation
- [ ] Validate GrafanaRegistry works

**Day 1 Afternoon**:
- [ ] Test training run tracking with GrafanaRegistry
- [ ] Verify Grafana dashboards still functional
- [ ] Document GrafanaRegistry usage for team

**Success Criteria**:
- ✅ No MLflow containers running
- ✅ No MLflow imports in codebase
- ✅ GrafanaRegistry operational
- ✅ Grafana dashboards query Prisma

---

**PHASE 2: Schema Migration - Production API (Day 2-3)**

**Day 2 Morning**:
- [ ] Backup database
- [ ] Update `src/fusion/api/server.py` (raw.* → mkt/alt/supply)
- [ ] Update `src/fusion/pulse/storage.py` (gold.* → features.*)
- [ ] Update `scripts/generate_core_forecasts.py` (model.* → forecasts.*)

**Day 2 Afternoon**:
- [ ] Test API endpoints locally
- [ ] Validate data returned matches expected schema
- [ ] Run integration tests

**Day 3 Morning**:
- [ ] Deploy API changes to staging
- [ ] Smoke test all endpoints
- [ ] Monitor error logs

**Success Criteria**:
- ✅ All API endpoints return data
- ✅ No raw/gold/silver references in API code
- ✅ Zero errors in production logs

---

**PHASE 3: Schema Migration - Ingestion Layer (Day 3-4)**

**Day 3 Afternoon**:
- [ ] Update Inngest jobs (yahoo-eod.ts, fx-spot-daily.ts, etc.)
- [ ] Update FRED router to write to econ.* tables
- [ ] Update Python ingestion scripts

**Day 4 Morning**:
- [ ] Test ingestion jobs in development
- [ ] Verify data lands in correct institutional schemas
- [ ] Check data quality metrics

**Day 4 Afternoon**:
- [ ] Deploy ingestion changes
- [ ] Monitor data freshness
- [ ] Validate row counts match expectations

**Success Criteria**:
- ✅ All ingestion jobs write to institutional schemas
- ✅ Data freshness < 24 hours
- ✅ Row counts stable

---

**PHASE 4: Schema Migration - Training Pipeline (Day 5-6)**

**Day 5 Morning**:
- [ ] Update `scripts/preflight_52model.py`
- [ ] Update `scripts/audit_core_training_data.py`
- [ ] Update feature engineering modules

**Day 5 Afternoon**:
- [ ] Test feature generation end-to-end
- [ ] Validate `training.matrix_1d` builds correctly
- [ ] Check feature count (~130 columns)

**Day 6 Morning**:
- [ ] Run preflight checks
- [ ] Validate all 11 specialist feature tables
- [ ] Test OOF table generation

**Success Criteria**:
- ✅ Preflight passes for all specialists
- ✅ training.matrix_1d contains ~130 features
- ✅ OOF tables follow standardized schema

---

**PHASE 5: Schema Migration - Validators (Day 7)**

**Day 7 Morning**:
- [ ] Rewrite `src/fusion/validators/schema_contract.py`
- [ ] Update `src/fusion/validators/freshness_monitor.py`
- [ ] Retire or rewrite `src/fusion/validators/anomaly_detection.py`

**Day 7 Afternoon**:
- [ ] Add schema guard to API startup
- [ ] Test zero-tolerance failure modes
- [ ] Validate monitoring dashboards

**Success Criteria**:
- ✅ Schema guard prevents legacy schema access
- ✅ Freshness monitor tracks institutional schemas
- ✅ Grafana dashboards operational

---

**PHASE 6: Production Hardening (Day 8)**

**Day 8 Morning**:
- [ ] Run full validation suite
- [ ] Test rollback procedure
- [ ] Document operational runbooks

**Day 8 Afternoon**:
- [ ] Final smoke tests
- [ ] Team training on new architecture
- [ ] Go/no-go decision

**Success Criteria**:
- ✅ All validation checks pass
- ✅ Rollback tested and documented
- ✅ Team trained on new system

---

### 5.2 Specific Commands for Execution

**MLflow Removal**:
```bash
# Stop services
docker compose -f docker/docker-compose.yml down mlflow mlflow-postgres minio

# Remove files
rm docker/Dockerfile.mlflow scripts/start-mlflow.sh scripts/sync_prisma_to_mlflow.py Docs/MLFLOW_SETUP.md mlflow.db
rm -rf mlruns/

# Validate
python3 -c "from grafana.grafana_registry import GrafanaRegistry; print('✅ OK')"
```

**Schema Migration - API**:
```bash
# Backup
pg_dump $DATABASE_URL > backup_$(date +%Y%m%d).sql

# Update code (manual edits to src/fusion/api/server.py)

# Test locally
cd /Volumes/Satechi\ Hub/ZINC-FUSION-V15
source .venv/bin/activate
python3 -m uvicorn fusion.api.server:app --reload

# Validate
curl http://localhost:8000/health
curl http://localhost:8000/api/zl/latest
```

**Schema Migration - Ingestion**:
```bash
# Update Inngest jobs (manual edits to frontend/src/inngest/*.ts)

# Test locally
cd frontend
npm run dev

# Trigger test job
npx inngest-cli dev
```

**Schema Migration - Training**:
```bash
# Update scripts (manual edits)

# Test preflight
python3 scripts/preflight_52model.py

# Test feature generation
python3 -c "from fusion.features.elite import build_elite_features; build_elite_features()"

# Test matrix build
python3 src/fusion/core_training/phase3_build_core_matrix.py
```

**Production Validation**:
```bash
# Full validation suite
npx prisma validate
python3 scripts/validate_db_state.py
python3 scripts/validate_training_tables.py
python3 scripts/preflight_52model.py
python3 src/fusion/validators/schema_guard.py

# Check Grafana
open http://localhost:3000
```

---

## Part 6: Success Criteria & Validation

### 6.1 Phase-by-Phase Success Criteria

**Phase 1: MLflow Removal**
- ✅ No MLflow containers running (`docker ps | grep mlflow` returns empty)
- ✅ No MLflow imports (`grep -r "import mlflow" src/ scripts/` returns empty)
- ✅ GrafanaRegistry functional (test training run tracking)
- ✅ Grafana dashboards query Prisma (verify data displays)

**Phase 2: API Migration**
- ✅ Zero raw/gold/silver references in `src/fusion/api/`
- ✅ All endpoints return 200 status
- ✅ Data schema matches Prisma models
- ✅ No errors in production logs (24h monitoring)

**Phase 3: Ingestion Migration**
- ✅ All Inngest jobs write to institutional schemas
- ✅ Data freshness < 24 hours for all sources
- ✅ Row counts stable (±5% variance)
- ✅ No duplicate rows (check row_hash uniqueness)

**Phase 4: Training Migration**
- ✅ Preflight passes for all 11 specialists
- ✅ `training.matrix_1d` contains ~130 features
- ✅ OOF tables follow p30/p50/p70 contract
- ✅ Feature generation completes without errors

**Phase 5: Validator Migration**
- ✅ Schema guard prevents legacy access (test with intentional violation)
- ✅ Freshness monitor tracks institutional schemas
- ✅ Anomaly detection retired or rewritten to ops.* tables

**Phase 6: Production Hardening**
- ✅ All validation scripts pass
- ✅ Rollback procedure tested
- ✅ Grafana dashboards operational
- ✅ Team trained on new architecture

### 6.2 Final Validation Checklist

**Database State**:
```bash
# No legacy schemas contain data
psql $DATABASE_URL -c "SELECT table_schema, COUNT(*) FROM information_schema.tables WHERE table_schema IN ('raw', 'gold', 'silver') GROUP BY table_schema;"
# Expected: 0 rows

# All institutional schemas exist
psql $DATABASE_URL -c "SELECT schema_name FROM information_schema.schemata WHERE schema_name IN ('mkt', 'econ', 'pos', 'supply', 'alt', 'features', 'training', 'model', 'analytics', 'metadata', 'ops');"
# Expected: 11 rows
```

**Code State**:
```bash
# No legacy schema references
grep -r "raw\." --include="*.py" --include="*.ts" src/ scripts/ frontend/src/ | grep -v ".pyc" | wc -l
# Expected: 0

grep -r "gold\." --include="*.py" --include="*.ts" src/ scripts/ frontend/src/ | grep -v ".pyc" | wc -l
# Expected: 0

grep -r "silver\." --include="*.py" --include="*.ts" src/ scripts/ frontend/src/ | grep -v ".pyc" | wc -l
# Expected: 0
```

**Training Readiness**:
```bash
# All specialist tables exist
.venv/bin/python - <<'PY'
import os
import psycopg2

specialists = ['biofuel','china','crush','energy','fed','fx','palm','substitutes','tariff','trump_effect','volatility']
conn = psycopg2.connect(os.environ['DATABASE_URL'])
cur = conn.cursor()
for s in specialists:
    cur.execute(f"SELECT COUNT(*) FROM training.specialist_{s}_1d")
    n = cur.fetchone()[0]
    print(f"training.specialist_{s}_1d: {n} rows")
cur.close(); conn.close()
PY
```

**Monitoring**:
```bash
# Grafana dashboards accessible
curl -s http://localhost:3000/api/health | jq .
# Expected: {"status": "ok"}

# Data quality metrics populated
psql $DATABASE_URL -c "SELECT source, last_update, hours_since_update FROM ops.data_quality_metrics ORDER BY hours_since_update DESC LIMIT 10;"
# Expected: Recent timestamps, hours_since_update < 24
```

---

## Appendix A: Risk Assessment Matrix

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Data loss during migration | Low | Critical | Pre-migration backup, canary deployment |
| API downtime | Medium | High | Staged rollout, rollback procedure |
| Training pipeline breaks | Medium | High | Preflight validation, test on subset |
| Grafana dashboards fail | Low | Medium | Test queries before deployment |
| Team confusion | High | Low | Documentation, training session |

---

## Appendix B: Rollback Decision Tree

```
Migration fails?
├─ Yes → Which phase?
│   ├─ Phase 1 (MLflow) → Restore docker-compose.yml, restart services
│   ├─ Phase 2 (API) → Revert code, redeploy
│   ├─ Phase 3 (Ingestion) → Pause jobs, restore backup, resume
│   ├─ Phase 4 (Training) → Revert scripts, clear OOF tables
│   └─ Phase 5+ → Full rollback from backup
└─ No → Proceed to next phase
```

---

## Appendix C: Team Communication Plan

**Pre-Migration (Day 0)**:
- Email: Migration timeline, expected downtime
- Slack: Pin migration plan document
- Meeting: Walkthrough of changes

**During Migration (Day 1-8)**:
- Daily standup: Progress update
- Slack: Real-time status updates
- Incident channel: For issues

**Post-Migration (Day 9+)**:
- Retrospective: Lessons learned
- Documentation: Update runbooks
- Training: New architecture walkthrough

---

**END OF PRODUCTION READINESS PLAN**

**Next Steps**: Review this plan, approve phases, and begin execution starting with Phase 1 (MLflow Removal).


