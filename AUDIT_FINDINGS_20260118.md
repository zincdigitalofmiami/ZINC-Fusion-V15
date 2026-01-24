# Production Readiness Audit - Findings
**Date**: 2026-01-18  
**Scope**: Critical violations preventing production deployment

---

## Core Training Policy (CPU-only, Full Model Zoo)

Core runs **CPU-only** (no MPS, no CUDA). Set guards **before** importing torch/autogluon:

```
TOKENIZERS_PARALLELISM=false
OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES
AUTOGLUON_DISABLE_RAY=1
PYTORCH_ENABLE_MPS_FALLBACK=1
device = "cpu"
```

Core must try **ALL** AutoGluon-TimeSeries Model Zoo models via an explicit
`hyperparameters={...}` allowlist (model names may omit the “Model” suffix).
The full allowlist is maintained in `Docs/CORE_TRAINING_SPEC_LOCKED.md`.

AutoGluon trains the full allowlist, ranks models on validation/backtests, and
typically selects a **WeightedEnsemble** as best. No time limits are used.

Verification:
- `python -m fusion.core_training.run_pipeline --skip-matrix --horizons 5`
- `python -m fusion.core_training.run_pipeline --skip-matrix`
- Confirm logs show the full allowlist and a WeightedEnsemble selection

---

## ✅ COMPLETED

### 1. Barchart Runtime DDL Removal
**Status**: FIXED  
**Files Modified**:
- `scripts/ingest_barchart_etf_prices.py` - Line 123: Replaced `ensure_table_exists()` with `validate_table_exists()` (fail-fast validation)
- `scripts/ingest_barchart_options.py` - Line 194: Replaced `ensure_table_exists()` with `validate_table_exists()` (fail-fast validation)

**Impact**: Scripts now FAIL if Prisma-managed tables don't exist, enforcing migration-first workflow.

---

## 🔴 CRITICAL VIOLATIONS (Require Immediate Action)

### 2. anomaly_detection.py - Violates Append-Only Landing Architecture

**File**: `src/fusion/validators/anomaly_detection.py` (857 lines)

**Problem**: Script UPDATEs 7 raw.* tables, violating immutable landing zone contract.

**Tables Updated** (lines with UPDATE statements):
1. `raw.market_futures_1d` (line 540)
2. `raw.weather_noaa_1d` (line 577)  
3. `raw.fred_observations_1d` (line 615)
4. `raw.news_articles_1d` (line 652)
5. `raw.cftc_cot_1w` (line 690)
6. `raw.fx_spot_1d` (line 728)
7. `raw.epa_rin_prices_1d` (line 766)

**Current Behavior**:
- Computes `anomaly_flags` (array) and `quality_score` (int) for each row
- UPDATEs landing tables with these computed fields
- Uses 7 backfill functions (one per table)

**Existing Prisma ops Tables** (for output):
- `ops.data_quality_log` (line 1439) - Has: table_name, check_date, row_count, null_count, issues (JSON)
- `ops.data_quality_metrics` (line 1455) - Has: as_of_date, source, completeness_pct, is_stale

**Required Action**:
- [ ] Map reads to v2 schemas (raw.* → mkt.*, econ.*, alt.*, pos.*, supply.*)
- [ ] Write anomaly events to `ops.data_quality_log` (append-only)
- [ ] For FRED: Split by series_id routing (econ.rates_1d, econ.inflation_1d, etc.)
- [ ] STOP updating landing tables

**Schema Mapping**:
```
raw.market_futures_1d  → mkt.futures_1d
raw.weather_noaa_1d    → alt.weather_1d
raw.fred_observations_1d → econ.* (split by FRED_SERIES_BUCKETS routing)
raw.news_articles_1d   → alt.news_1d
raw.cftc_cot_1w        → pos.cftc_1w
raw.fx_spot_1d         → mkt.fx_1d
raw.epa_rin_prices_1d  → supply.epa_rin_1d
```

---

### 3. Massive Data Source - Requires Complete Removal

**File**: `scripts/ingest_massive_options.py` (747 lines)

**References Found**:
- Creates `raw.options_equity_1d` table (line 289) - Runtime DDL
- Creates `gold.options_features_1d` table (line 326) - Runtime DDL
- Uses `MASSIVE_API_KEY` environment variable (line 75)
- Source attribution: `source VARCHAR(50) DEFAULT 'massive'` (line 312)

**Required Action**:
- [ ] DEPRECATE script entirely (add deprecation notice at top)
- [ ] Remove from any cron/scheduler (if exists)
- [ ] NO data deletion (keep existing data in DB)
- [ ] Remove API key references from docs
- [ ] Document replacement: Use Barchart options ingestion instead

---

## 🟡 MEDIUM PRIORITY VIOLATIONS

### 4. CREATE TABLE IF NOT EXISTS in 5 Additional Scripts

**Files with Runtime DDL**:

1. **scripts/build_options_silver_gold.py** (line 45, 68)
   - Creates `silver.options_agg_1d`
   - Creates `silver.etf_prices_1d`
   - **Schema**: `silver` (BANNED - not in v2 architecture)

2. **scripts/ingest_all_historical.py** (lines 155, 185, 211, 250, 279, 308, 338, 371)
   - Creates 8 tables without schema prefix (defaults to `public`)
   - **Status**: Historical backfill script (may be legacy-only)

3. **scripts/pull_fred_to_postgres.py** (line 114)
   - Creates `fred_observations_1d` (no schema prefix)
   - **Issue**: Should target `econ.*` tables, not raw

4. **src/fusion/core_training/phase3_build_core_matrix.py** (line 361)
   - Dynamic CREATE TABLE (parameterized schema/table)
   - **Context**: Needs review - may be Prisma-managed

5. **src/fusion/core_training/phase1_options_features.py** (line 406)
   - Creates `features.options_1d`
   - **Status**: Should be Prisma-managed

**Required Action**:
- [ ] Review each script's usage/status
- [ ] Deprecate or convert to validation pattern (like Barchart fix)
- [ ] Remove `silver` schema references entirely

---

## 📋 AUDIT SUMMARY

### Database Environment
**Issue**: `DATABASE_URL` not consistently available, causing connection failures.

**Solution**: Add validation helper at module import:
```python
# Add to all scripts that need DB
import os
import sys

DATABASE_URL = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL")
if not DATABASE_URL:
    sys.exit("FATAL: DATABASE_URL environment variable required")
```

### Prisma Schema State
- **Total Models**: 153 (as documented)
- **Schemas Defined**: 13 (alt, analytics, archive, econ, features, forecasts, metadata, mkt, model, ops, pos, supply, training)
- **multiSchema Preview**: Still enabled (line 4) - Deprecation warning expected

### Ops Tables Available for Anomaly Output
- `ops.data_quality_log` - Row-level data quality tracking
- `ops.data_quality_metrics` - Aggregate metrics by source/date
- Both tables support append-only logging (no UPDATE needed)

---

## 🎯 RECOMMENDED FIX ORDER

1. **STOP**: Do not create new scripts or files outside this list
2. **AUDIT**: Complete understanding of anomaly_detection.py dependencies
3. **FIX 1**: Remove Massive data source (deprecate script, keep data)
4. **FIX 2**: Map anomaly_detection.py reads to v2 schemas
5. **FIX 3**: Refactor anomaly_detection.py to write to ops tables (append-only)
6. **FIX 4**: Review and fix remaining CREATE TABLE scripts (5 files)
7. **FIX 5**: Add DATABASE_URL validation helper to all DB scripts
8. **VALIDATE**: Run pytest suite

---

## ❌ EXPLICITLY NOT DOING

- Creating new scripts
- Creating bridge tables/views without SQL definition
- Adding placeholder/mock data
- Making assumptions about data structure
- Modifying beyond the documented scope

---

**Next Step**: Await user confirmation on which fix to proceed with first.
