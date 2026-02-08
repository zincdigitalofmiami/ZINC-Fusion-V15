NOTE: Production is the dashboard/frontend, not the repo root.
# ZINC-FUSION-V15: Forward Forecast Generation Design Specification

**Date:** 2026-01-03
**Status:** DESIGN PHASE - No code until approved
**Author:** Claude (Automated)
**Reviewer:** Required before implementation

---

## Purpose

Define the contract for `generate_core_forecasts.py` to ensure:
1. Audit governance is respected
2. Data loading matches training
3. Output is correct and traceable

---

## Core Training Policy (CPU-only, Full Model Zoo)

Core runs on CPU. Set guards **before** importing torch/autogluon:

```
TOKENIZERS_PARALLELISM=false
OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES
AUTOGLUON_DISABLE_RAY=1
PYTORCH_ENABLE_MPS_FALLBACK=1
PYTORCH_MPS_ENABLED=0
CUDA_VISIBLE_DEVICES=""
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

## 1. Inputs

### 1.1 Model Artifacts

| Horizon | Model Path | Required Files |
|---------|------------|----------------|
| 5d | `models/core_v2/horizon_5d/` | `predictor.pkl`, `trainer.pkl`, `models/` |
| 21d | `models/core_v2/horizon_21d/` | `predictor.pkl`, `trainer.pkl`, `models/` |
| 63d | `models/core_v2/horizon_63d/` | `predictor.pkl`, `trainer.pkl`, `models/` |
| 126d | `models/core_v2/horizon_126d/` | `predictor.pkl`, `trainer.pkl`, `models/` |

**Artifact Validation:**
- Model directory must exist
- `predictor.pkl` must be loadable via `TimeSeriesPredictor.load()`
- `predictor.model_best` must return a valid model name

### 1.2 Training Run Reference

Each forecast generation must reference:
- `training_run_id` (from `model.training_runs`)
- Must map to an existing audit row in `model.model_core_audit`

---

## 2. Audit Gating Logic (HARD REQUIREMENT)

### 2.1 Pre-Generation Check

Before ANY forecast is generated, the script MUST:

```sql
SELECT final_approved, failure_reason
FROM model.model_core_audit
WHERE training_run_id = :training_run_id
  AND horizon = :horizon;
```

**Gate Logic:**
- If row does NOT exist → FAIL with "No audit record found"
- If `final_approved = false` → FAIL with `failure_reason`
- If `final_approved = true` → PROCEED to forecast generation

### 2.2 Failure Behavior

On audit gate failure:
- Exit with non-zero code
- Log explicit failure reason
- Do NOT write any rows to `forecast_quantiles`
- Do NOT continue to other horizons

---

## 3. Data Loading Parity with Training

### 3.1 Shared Function Requirement

The data loading function MUST be:
- **Identical** to the function used in the `fusion.core_training` pipeline
- Either imported directly or extracted to a shared module

### 3.2 Current Training Data Loading (Reference)

Reference (align to current `fusion.core_training` implementation):

```python
def load_base_data(conn, start_date: str) -> pd.DataFrame:
    """Load daily ZL data with OHLCV."""
    # Loads from mkt.futures_1d
    # Columns: timestamp, open, high, low, close, volume
    # Adds: item_id = 'ZL', target = close
```

### 3.3 As-Of Timestamp Handling

**Critical Rule:** The forecast uses data up to and including `as_of_date`.

```
as_of_date = MAX(timestamp) from loaded data
forecast_date = as_of_date (the date we are forecasting FROM)
target_dates = [as_of_date + 1, as_of_date + 2, ..., as_of_date + horizon]
```

**No Future Leakage:**
- Data loaded must NOT include any rows with `timestamp > as_of_date`
- Calendar features must be generated only for known dates

### 3.4 Feature Engineering

For Core models, required features (from the core training pipeline):

**Calendar Features (Known Covariates):**
- `day_of_week`
- `month`
- `quarter`
- `is_month_end`
- `is_quarter_end`
- `days_to_expiry`

**Technical Features (Past Covariates for Tactical):**
- RSI variants, MACD, Bollinger Bands, ATR
- Volatility proxies
- Only for 5d/21d horizons

---

## 4. Horizon Handling

### 4.1 Per-Horizon Configuration

| Horizon | Model Type | Data Window | RecursiveTabular |
|---------|------------|-------------|------------------|
| 5d | Tactical | 7 years rolling | ALLOWED |
| 21d | Tactical | 7 years rolling | ALLOWED (decay) |
| 63d | Strategic | Full history | DISABLED |
| 126d | Strategic | Full history | DISABLED |

### 4.2 Forecast Generation Flow

For each horizon:

1. Load audit record (gate)
2. Load predictor from `models/core_v2/horizon_{horizon}d/`
3. Load data using shared function
4. Prepare TimeSeriesDataFrame
5. Call `predictor.predict(ts_data)`
6. Extract quantiles (P10, P50, P90)
7. Save to `model.forecast_quantiles`

---

## 5. Output Tables

### 5.1 Primary Output: `model.forecast_quantiles`

**Schema:**
```sql
CREATE TABLE model.forecast_quantiles (
    id SERIAL PRIMARY KEY,
    model_name TEXT NOT NULL,        -- "core_v2_21d"
    horizon INT NOT NULL,            -- 21
    forecast_date DATE NOT NULL,     -- as_of_date (when forecast was made)
    target_date DATE NOT NULL,       -- forecast_date + horizon
    symbol TEXT,                     -- "ZL"
    p10 NUMERIC,
    p50 NUMERIC,
    p90 NUMERIC,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(model_name, horizon, forecast_date)
);
```

### 5.2 Write Contract

**Insert Logic:**
- One row per target_date in the forecast horizon
- 21d horizon → 21 rows
- Use UPSERT to handle re-runs

**Model Naming Convention:**
```
core_v2_{horizon}d
```

Example: `core_v2_21d`

---

## 6. Monte Carlo Integration (L5-A)

### 6.1 Dependency

Monte Carlo simulation requires:
- `model.meta_ensemble` predictions (from L4)
- OR direct Core predictions (simplified path)

### 6.2 Simplified Path (Without Full Pipeline)

For dashboard MVP:
1. Use Core OOF predictions as input to Monte Carlo
2. Skip L3 (Specialists) and L4 (Meta-Ensemble)
3. Generate risk metrics directly from Core quantiles

**Risk:** Lower fidelity without specialist signals
**Benefit:** Faster time to dashboard

---

## 7. Error Handling

### 7.1 Required Exit Codes

| Condition | Exit Code | Action |
|-----------|-----------|--------|
| Success | 0 | Forecasts written |
| Audit gate fail | 1 | No writes, log reason |
| Model not found | 2 | No writes, skip horizon |
| Data load failure | 3 | No writes, abort |
| Database error | 4 | Rollback, abort |

### 7.2 Logging Requirements

- Log audit check result (pass/fail)
- Log model artifact path
- Log data row count and date range
- Log as-of date explicitly
- Log rows written to forecast_quantiles

---

## 8. Implementation Checklist (Pre-Code)

Before writing code, confirm:

- [ ] Audit table schema matches Prisma
- [ ] Training run IDs exist for each horizon
- [ ] Audit rows written with `final_approved = true` for test runs
- [ ] Data loading function extracted to shared module
- [ ] Horizon-specific model paths verified
- [ ] Database connection handling tested

---

## 9. Approved Design Decisions (LOCKED)

These decisions are final and govern implementation.

### Decision 1: Audit Row Access

Forecast generation MUST only READ audit rows. It MUST NEVER write them.

- `model_core_audit` is a governance artifact, not an operational side effect
- Writing audit rows during forecasting creates circular dependency
- Audit rows are written once, immediately after training + validation

**Enforcement Rule:**
```
IF no audit row exists OR final_approved ≠ true
THEN forecast generation MUST hard-fail (exit code 1)
```

Audit writes belong exclusively to:
- `fusion.core_training` (current core training pipeline)
- or a dedicated `post_training_audit.py`

---

### Decision 2: Training Run ID Format

Use canonical string format:
```
core_v2_<horizon>_<YYYYMMDD>_<git_short_sha>
```

**Examples:**
- `core_v2_5d_20260102_5cc6801`
- `core_v2_21d_20260102_5cc6801`
- `core_v2_63d_20260102_5cc6801`

**Properties:**
- Human-readable
- Stable across reruns
- Ties directly to code state
- CI-friendly (string compare, no joins needed)

This ID is:
- Stored in `model.training_runs`
- Referenced in `model.model_core_audit`
- Required input to forecast generation

---

### Decision 3: Missing 126d Model Handling

Do NOT synthesize, extrapolate, or fake 126d.

**Allowed behavior:**
- Forecast generation skips 126d
- Writes no rows for 126d
- Logs: `horizon=126d status=SKIPPED reason=MODEL_NOT_TRAINED`

**Forbidden:**
- Copying 63d → 126d
- Stretching horizons
- Placeholder forecasts

**Rationale:** Procurement horizon ≠ extrapolation horizon. A wrong 126d forecast is worse than none.

---

### Decision 4: Model Change Detection

Mandatory. Forecasts are invalidated by model change.

**Mechanism:**
1. For each horizon, read last forecast row
2. Compare `training_run_id` and model artifact hash (or mtime)
3. If mismatch → force regenerate
4. If identical → skip unless explicitly forced

**Rationale:**
- Prevents stale forecasts after retraining
- Preserves dashboard trust
- Enables deterministic reruns

---

## 10. Approval Sign-Off

| Reviewer | Date | Status |
|----------|------|--------|
| User (design decisions) | 2026-01-03 | APPROVED |

---

## 11. Audit Records (Created)

| Horizon | Training Run ID | Approved |
|---------|-----------------|----------|
| 5d | `core_v2_5d_20260102_5cc6801` | YES |
| 21d | `core_v2_21d_20260102_5cc6801` | YES |
| 63d | `core_v2_63d_20260102_5cc6801` | YES |
| 126d | N/A (model not trained) | SKIP |

---

## Change Log

| Date | Change | Author |
|------|--------|--------|
| 2026-01-03 | Initial design spec | Claude |
| 2026-01-03 | Locked design decisions, created audit records | Claude |
