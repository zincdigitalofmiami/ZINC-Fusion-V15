# Core Model Refactor - Implementation Specification
## ZINC-Fusion-V15: P30/P50/P70 + Tail Calibration + Zone Probability

**Date:** 2026-02-13  
**Status:** Planning  
**Impact:** High - Changes entire ZL Core forecasting contract

---

## Executive Summary

This refactor changes the Core forecasting model from **p10/p50/p90 direct training** to a **three-layer architecture**:

1. **Layer 1 (Training):** Train P30/P50/P70 as primary quantile outputs ✅ ALREADY DONE
2. **Layer 2 (Calibration):** Compute P10/P90 as calibrated tail extensions 🔴 NEW
3. **Layer 3 (Probability):** Compute zone-entry probabilities via Monte Carlo paths 🔴 NEW

---

## Impact on Recent Code Review Audit

### ✅ Issues That This Refactor Helps Fix

**Issue #6 (Float vs Decimal for Prices)**
- **Current Problem:** `mkt.futures_1d` uses Float, `forecasts.core_cone_1d` uses Float for quantiles
- **Refactor Impact:** Provides perfect opportunity to standardize ALL quantile columns to Decimal(10,6)
- **Action:** Include Float→Decimal migration in schema changes

**Schema Consistency**
- **Current Problem:** Inconsistent naming across forecast tables
- **Refactor Impact:** New fields (p10_cal, p90_cal, prob_enter_p30_p70) enforce clearer naming contract
- **Action:** Standardize all forecast tables to use p10_cal/p30/p50/p70/p90_cal naming

### ⚠️ Issues That Are Orthogonal (Must Still Fix Separately)

These audit findings are UNRELATED to the model refactor and must be fixed independently:

- **Issue #1:** Connection leak in `zl-live.ts:160` - Inngest layer, not model
- **Issue #2:** No API authentication on 30+ endpoints - Security layer, not model
- **Issue #3:** N+1 specialist query in `server.py:351` - API layer, not model
- **Issue #4:** Missing DB error handling - API layer, not model
- **Issue #7:** N+1 backfill query in `board-crush-daily.ts:291` - Ingestion layer, not model

**CRITICAL:** Do NOT let the model refactor distract from fixing these security/performance issues.

### 🔄 Issues That Change Scope

**Issue #9 (Missing Indexes on training.matrix_1d)**
- **Current Scope:** Add indexes to training.matrix_1d
- **New Scope:** Add indexes to ALL forecast tables that get new columns (prob_enter_*, p10_cal, p90_cal)

**Issue #5 (Missing metadata schema)**
- **Current Scope:** Add metadata schema for instruments
- **New Scope:** Could add forecast_metadata for tracking calibration parameters per horizon

---

## Current Architecture Discovery

### Layer 1: Training Layer ✅ MOSTLY READY

**Files:**
- `src/fusion/core_training/train_models.py` (Lines 1-500)
- `src/fusion/core_training/config.py` (Line 31: QUANTILES = [0.3, 0.5, 0.7])

**Current State:**
```python
# config.py:31
QUANTILES = [0.3, 0.5, 0.7]  # ✅ CORRECT - Already trains P30/P50/P70

# train_models.py:270
predictor = TimeSeriesPredictor(
    quantile_levels=QUANTILES,  # ✅ Uses [0.3, 0.5, 0.7]
    ...
)

# train_models.py:346-348 - OOF extraction
"p30": row.get("0.3", row.get("mean", 0)),
"p50": row.get("0.5", row.get("mean", 0)),
"p70": row.get("0.7", row.get("mean", 0)),
```

**Database Schema:**
```prisma
// prisma/schema.prisma:3050-3071
model oof_core_1d {
  p30            Float  // ✅ CORRECT
  p50            Float  // ✅ CORRECT
  p70            Float  // ✅ CORRECT
  // Missing: No p10/p90 here (CORRECT - they should be calibrated, not trained)
}
```

**Status:** ✅ **COMPLETE** - Layer 1 already trains P30/P50/P70 correctly

**Action Required:** NONE (Layer 1 is already correct)

---

### Layer 2: Calibration Layer 🔴 MISSING

**Files:** NONE (needs to be created)

**What's Missing:**
- No dedicated calibration module exists
- No tail calibration algorithm
- No persistence of calibration offsets

**Required Files:**
1. `src/fusion/calibration/__init__.py`
2. `src/fusion/calibration/tail_calibration.py`
3. `scripts/calibrate_tails.py` (standalone calibration runner)

**Required Logic:**

```python
# tail_calibration.py - NEW FILE
def calibrate_tails(
    oof_df: pd.DataFrame,  # Contains p30/p50/p70
    actuals_df: pd.DataFrame,  # Contains realized returns
    target_coverage_p10: float = 0.10,  # 10% of actuals < p10
    target_coverage_p90: float = 0.90,  # 90% of actuals < p90
) -> Dict[str, float]:
    """
    Compute tail calibration offsets to achieve target coverage.
    
    Algorithm:
    1. For each OOF prediction, compute error: actual - p50
    2. Fit tail distribution to errors (e.g., Johnson SU or GPD)
    3. Compute p10_offset = quantile(errors, 0.10)
    4. Compute p90_offset = quantile(errors, 0.90)
    5. Validate: p10_cal = p30 + p10_offset, p90_cal = p70 + p90_offset
    6. Check monotonicity: p10_cal < p30 < p50 < p70 < p90_cal
    
    Returns:
        Dict with keys: p10_offset, p90_offset, coverage_p10, coverage_p90
    """
    pass
```

**Database Schema Changes:**

```prisma
// Add to forecasts.forecast_summary_1d (Lines 920-924)
// ✅ ALREADY EXISTS:
p30               Float?
p50               Float?
p70               Float?
p10_cal           Float?  // ✅ ALREADY EXISTS
p90_cal           Float?  // ✅ ALREADY EXISTS

// NEW: Add calibration metadata table
model tail_calibration_params {
  id                Int       @id @default(autoincrement())
  horizon_days      Int
  calibration_date  DateTime  @db.Date
  p10_offset        Decimal   @db.Decimal(10, 6)  // Offset from p30
  p90_offset        Decimal   @db.Decimal(10, 6)  // Offset from p70
  coverage_p10      Float     // Realized coverage at p10
  coverage_p90      Float     // Realized coverage at p90
  sample_size       Int       // Number of OOF predictions used
  created_at        DateTime  @default(now())
  
  @@unique([horizon_days, calibration_date])
  @@schema("model")
}
```

**Action Required:**
1. Create `src/fusion/calibration/tail_calibration.py` with calibration algorithm
2. Create `scripts/calibrate_tails.py` to run calibration and persist offsets
3. Add `model.tail_calibration_params` table to Prisma schema
4. Update `scripts/generate_production_forecasts.py` to apply calibration offsets

---

### Layer 3: Probability Layer 🔴 PARTIALLY EXISTS

**Files:**
- `scripts/run_monte_carlo.py` (EXISTS but needs zone-entry calculation)
- `forecasts.core_mc_1d` (EXISTS but missing prob_enter_p30_p70)

**Current State:**

```python
# run_monte_carlo.py:70-72
N_SIMULATIONS = 10000
PERCENTILES = [1, 5, 10, 25, 50, 75, 90, 95, 99]
RANDOM_SEED = 42

# run_monte_carlo.py:86-100 - RiskMetrics dataclass
@dataclass
class RiskMetrics:
    var_01: float
    var_05: float
    cvar_05: float
    prob_up: float  # ⚠️ Simple up/down, not zone-entry
    # Missing: prob_enter_p30_p70_within_h
    # Missing: prob_touch_p10, prob_touch_p90
```

**Database Schema:**

```prisma
// prisma/schema.prisma:859-885
model core_mc_1d {
  p10           Float
  p50           Float
  p90           Float
  opp           Float?  // ⚠️ Not the same as prob_enter_p30_p70
  ruin          Float?  // ⚠️ Not the same as prob_touch_p10
  var_95        Float?
  cvar_95       Float?
  // Missing: prob_enter_p30_p70_within_h
  // Missing: prob_touch_p10, prob_touch_p90
}
```

**What's Missing:**

1. **Zone-Entry Probability Calculation:**
   ```python
   def compute_zone_entry_probability(
       paths: np.ndarray,  # Shape: (N_SIMS, horizon_days)
       p30: float,
       p70: float,
   ) -> float:
       """
       Compute probability that path enters [p30, p70] zone within horizon.
       
       Algorithm:
       1. For each path, check if ANY timestep t in [1, horizon] has:
          p30 <= path[t] <= p70
       2. Count paths that enter zone at least once
       3. Return: count / N_SIMS
       """
       enters_zone = np.zeros(len(paths), dtype=bool)
       for i, path in enumerate(paths):
           enters_zone[i] = np.any((path >= p30) & (path <= p70))
       return enters_zone.mean()
   ```

2. **Tail Touch Probability:**
   ```python
   def compute_tail_touch_probability(
       paths: np.ndarray,
       p10: float,
       p90: float,
   ) -> Tuple[float, float]:
       """
       Compute probability that path touches p10 or p90 tails.
       
       Returns:
           (prob_touch_p10, prob_touch_p90)
       """
       touch_p10 = np.any(paths <= p10, axis=1).mean()
       touch_p90 = np.any(paths >= p90, axis=1).mean()
       return touch_p10, touch_p90
   ```

**Database Schema Changes:**

```prisma
// Update forecasts.core_mc_1d (Lines 859-885)
model core_mc_1d {
  // ... existing fields ...
  
  // NEW: Zone-entry probabilities
  prob_enter_p30_p70_within_h  Float?  // Primary dashboard metric
  prob_touch_p10               Float?  // Downside tail risk
  prob_touch_p90               Float?  // Upside tail opportunity
  
  // RENAME for clarity:
  // opp → prob_up (generic upside)
  // ruin → prob_down_threshold (generic downside)
}

// Update forecasts.forecast_summary_1d (Lines 902-929)
model forecast_summary_1d {
  // ... existing fields ...
  
  // NEW: Add primary probability metric
  prob_enter_zone  Float?  // Alias for prob_enter_p30_p70_within_h
}
```

**Action Required:**
1. Add `compute_zone_entry_probability()` to `run_monte_carlo.py`
2. Add `compute_tail_touch_probability()` to `run_monte_carlo.py`
3. Update `core_mc_1d` schema with new probability columns
4. Persist probability metrics alongside existing MC outputs

---

### Layer 4: Serving/UI Contract 🔄 PARTIALLY READY

**Files:**
- `scripts/generate_production_forecasts.py` (Needs probability integration)
- `src/fusion/api/server.py` (Needs probability endpoints)
- Dashboard (frontend) - Needs "XX% probability" display

**Current State:**

```python
# generate_production_forecasts.py:67-94
def get_latest_oof_by_horizon(engine, horizon: int) -> pd.DataFrame:
    """Get the most recent OOF predictions for a given horizon."""
    query = """
        SELECT
            trade_date,
            AVG(p30) as p30,  # ✅ Already returns p30/p50/p70
            AVG(p50) as p50,
            AVG(p70) as p70,
            ...
        FROM training.oof_core_1d
        ...
    """
```

**Database Schema:**

```prisma
// forecasts.forecast_summary_1d (Lines 902-929)
model forecast_summary_1d {
  p30               Float?  // ✅ ALREADY EXISTS
  p50               Float?  // ✅ ALREADY EXISTS
  p70               Float?  // ✅ ALREADY EXISTS
  p10_cal           Float?  // ✅ ALREADY EXISTS
  p90_cal           Float?  // ✅ ALREADY EXISTS
  // Missing: prob_enter_zone (dashboard needs this)
}
```

**What's Missing:**

1. **Forecast Generation Must Include Probabilities:**
   ```python
   # generate_production_forecasts.py - ADD THIS
   def get_latest_probabilities(engine, horizon: int) -> pd.DataFrame:
       """Fetch latest MC probabilities for horizon."""
       query = """
           SELECT
               forecast_date,
               prob_enter_p30_p70_within_h,
               prob_touch_p10,
               prob_touch_p90
           FROM forecasts.core_mc_1d
           WHERE horizon_days = %s
           ORDER BY forecast_date DESC
           LIMIT 1
       """
       return pd.read_sql(query, engine, params=(horizon,))
   ```

2. **API Endpoint Must Serve Probabilities:**
   ```python
   # server.py - UPDATE /api/forecast/quantiles
   @app.get("/api/forecast/quantiles")
   def forecast_quantiles(horizon: int = Query(21)):
       # Current: Returns p30/p50/p70
       # NEW: Must also return prob_enter_zone
       
       rows = _fetch_rows("""
           SELECT 
               forecast_date,
               p10_cal, p30, p50, p70, p90_cal,
               prob_enter_zone  -- NEW
           FROM forecasts.forecast_summary_1d
           WHERE horizon_days = %s
           ORDER BY forecast_date DESC
           LIMIT 1
       """, [horizon])
       
       return {"quantiles": rows[0], "headline_probability": rows[0]["prob_enter_zone"]}
   ```

3. **Dashboard Display:**
   ```typescript
   // frontend/src/components/ForecastCard.tsx
   // BEFORE:
   // "ZL forecast for 21d: $42.30 - $45.80"
   
   // AFTER:
   // "75% probability ZL enters $42.30 - $45.80 within 21 days"
   //  ^^^ prob_enter_zone from API
   ```

**Action Required:**
1. Update `generate_production_forecasts.py` to fetch and persist probabilities
2. Update `forecast_summary_1d` upserts to include prob_enter_zone
3. Add API endpoint to serve probabilities
4. Update dashboard to display "XX% probability..." text

---

## Definition of Done (Validation Checklist)

The refactor is NOT complete unless ALL of these pass:

### 1. Schema Validation

```sql
-- All forecast tables have correct quantile columns
SELECT 
    table_name,
    column_name,
    data_type
FROM information_schema.columns
WHERE table_schema = 'forecasts'
  AND column_name IN ('p10_cal', 'p30', 'p50', 'p70', 'p90_cal', 'prob_enter_zone')
ORDER BY table_name, column_name;

-- Expected result: All columns use Decimal(10,6) or Float (to be migrated)
```

### 2. Monotonicity Validation

```python
# Add to generate_production_forecasts.py
def validate_monotonicity(row: dict) -> bool:
    """Validate quantile monotonicity."""
    assert row['p10_cal'] <= row['p30'], "p10_cal > p30"
    assert row['p30'] <= row['p50'], "p30 > p50"
    assert row['p50'] <= row['p70'], "p50 > p70"
    assert row['p70'] <= row['p90_cal'], "p70 > p90_cal"
    return True

# Add to run_monte_carlo.py
def validate_probabilities(probs: dict) -> bool:
    """Validate probability bounds."""
    assert 0 <= probs['prob_enter_zone'] <= 1, "prob_enter_zone out of bounds"
    assert 0 <= probs['prob_touch_p10'] <= 1, "prob_touch_p10 out of bounds"
    assert 0 <= probs['prob_touch_p90'] <= 1, "prob_touch_p90 out of bounds"
    return True
```

### 3. Integration Test

```python
# tests/test_core_refactor_integration.py
def test_full_forecast_pipeline():
    """Test complete forecast pipeline from OOF to dashboard."""
    
    # 1. Load latest OOF
    oof_df = get_latest_oof_by_horizon(engine, horizon=21)
    assert 'p30' in oof_df.columns
    assert 'p50' in oof_df.columns
    assert 'p70' in oof_df.columns
    
    # 2. Apply tail calibration
    calib_params = load_calibration_params(engine, horizon=21)
    p10_cal = oof_df['p30'] + calib_params['p10_offset']
    p90_cal = oof_df['p70'] + calib_params['p90_offset']
    
    # 3. Run Monte Carlo with zone-entry
    mc_results = run_monte_carlo_with_zone_entry(
        p30=oof_df['p30'],
        p50=oof_df['p50'],
        p70=oof_df['p70'],
        horizon=21
    )
    assert 'prob_enter_zone' in mc_results
    
    # 4. Validate monotonicity
    assert p10_cal < oof_df['p30'] < oof_df['p50'] < oof_df['p70'] < p90_cal
    
    # 5. Validate probabilities
    assert 0 <= mc_results['prob_enter_zone'] <= 1
```

### 4. Dashboard Display Test

```bash
# Manual verification:
# 1. Start API server
.venv/bin/python -m uvicorn fusion.api.server:app --port 8000

# 2. Check forecast endpoint
curl http://localhost:8000/api/forecast/quantiles?horizon=21

# Expected JSON:
{
  "quantiles": {
    "p10_cal": 40.25,
    "p30": 41.50,
    "p50": 43.00,
    "p70": 44.50,
    "p90_cal": 45.75,
    "prob_enter_zone": 0.72  # <-- NEW FIELD
  },
  "headline_probability": 0.72
}

# 3. Check dashboard displays:
# "72% probability ZL enters $41.50 - $44.50 within 21 days"
```

---

## Implementation Roadmap

### Phase 0: Pre-flight Checks (1 hour)

- [ ] Verify current OOF data has p30/p50/p70 ✅
- [ ] Confirm training pipeline uses QUANTILES = [0.3, 0.5, 0.7] ✅
- [ ] Check forecast_summary_1d already has p10_cal/p90_cal fields ✅
- [ ] Audit current Monte Carlo for probability calculation patterns

### Phase 1: Schema Migration (2-3 hours)

**1.1 Add Calibration Metadata Table**
```bash
# Create migration
scripts/prisma.sh migrate dev --name add-tail-calibration-params

# Edit prisma/schema.prisma
# Add model tail_calibration_params (see Layer 2 above)
```

**1.2 Add Probability Columns**
```bash
# Create migration
scripts/prisma.sh migrate dev --name add-zone-entry-probabilities

# Edit prisma/schema.prisma
# Add prob_enter_zone to forecast_summary_1d
# Add prob_enter_p30_p70_within_h, prob_touch_p10/p90 to core_mc_1d
```

**1.3 Migrate Float → Decimal (BONUS - Fixes Audit Issue #6)**
```bash
# Create migration
scripts/prisma.sh migrate dev --name float-to-decimal-quantiles

# Update ALL quantile columns to Decimal(10,6):
# - mkt.futures_1d: open/high/low/close
# - forecasts.core_cone_1d: p10/p50/p90
# - forecasts.core_mc_1d: all price fields
# - forecasts.forecast_summary_1d: p10_cal/p30/p50/p70/p90_cal
```

**1.4 Add Indexes**
```prisma
// Add to forecast_summary_1d
@@index([forecast_date, horizon_days])
@@index([prob_enter_zone])  // For dashboard queries

// Add to core_mc_1d
@@index([prob_enter_p30_p70_within_h])
```

### Phase 2: Calibration Layer (4-5 hours)

**2.1 Create Calibration Module**
```bash
mkdir -p src/fusion/calibration
touch src/fusion/calibration/__init__.py
touch src/fusion/calibration/tail_calibration.py
```

**2.2 Implement Tail Calibration Algorithm**
```python
# src/fusion/calibration/tail_calibration.py
# See Layer 2 section above for full implementation
```

**2.3 Create Calibration Runner Script**
```bash
touch scripts/calibrate_tails.py
```

```python
# scripts/calibrate_tails.py
"""
Run tail calibration for all horizons.

Usage:
    python scripts/calibrate_tails.py --horizon 21
    python scripts/calibrate_tails.py --all
"""
```

**2.4 Test Calibration**
```bash
# Run calibration on historical OOF data
python scripts/calibrate_tails.py --horizon 21 --dry-run

# Validate coverage targets are met (p10: ~10%, p90: ~90%)
```

### Phase 3: Probability Layer (3-4 hours)

**3.1 Add Zone-Entry Calculation**
```python
# Edit scripts/run_monte_carlo.py
# Add compute_zone_entry_probability() function (see Layer 3 above)
```

**3.2 Add Tail Touch Calculation**
```python
# Edit scripts/run_monte_carlo.py
# Add compute_tail_touch_probability() function (see Layer 3 above)
```

**3.3 Update Monte Carlo Pipeline**
```python
# Edit run_monte_carlo.py main() function
# After path simulation:
prob_enter_zone = compute_zone_entry_probability(paths, p30, p70)
prob_touch_p10, prob_touch_p90 = compute_tail_touch_probability(paths, p10_cal, p90_cal)

# Persist to core_mc_1d
```

**3.4 Test Probability Calculation**
```bash
# Run MC simulation
python scripts/run_monte_carlo.py --horizon 21 --dry-run

# Validate probabilities are in [0, 1]
# Validate prob_enter_zone + prob_touch_p10 + prob_touch_p90 makes sense
```

### Phase 4: Serving Layer (2-3 hours)

**4.1 Update Forecast Generation**
```python
# Edit scripts/generate_production_forecasts.py
# Add get_latest_probabilities() function
# Add apply_tail_calibration() function
# Update upsert_production_forecast() to include probabilities
```

**4.2 Update API Endpoints**
```python
# Edit src/fusion/api/server.py
# Update /api/forecast/quantiles to return prob_enter_zone
# Add /api/forecast/probabilities endpoint (if needed)
```

**4.3 Test API Contract**
```bash
# Start server
.venv/bin/python -m uvicorn fusion.api.server:app --port 8000

# Test endpoint
curl http://localhost:8000/api/forecast/quantiles?horizon=21 | jq

# Verify response includes prob_enter_zone
```

### Phase 5: Dashboard Integration (1-2 hours - Frontend)

**5.1 Update Forecast Display Component**
```typescript
// frontend/src/components/ForecastCard.tsx
// Change from: "ZL forecast: $42.30 - $45.80"
// To: "72% probability ZL enters $42.30 - $45.80 within 21 days"
```

**5.2 Update API Client**
```typescript
// frontend/src/lib/api.ts
// Add prob_enter_zone to ForecastResponse type
interface ForecastResponse {
  p10_cal: number;
  p30: number;
  p50: number;
  p70: number;
  p90_cal: number;
  prob_enter_zone: number;  // NEW
}
```

**5.3 Test Dashboard Display**
```bash
# Start dashboard
npm --prefix frontend run dev

# Visit http://localhost:3000
# Verify "XX% probability..." text displays correctly
```

### Phase 6: Validation & Testing (2-3 hours)

**6.1 Add Monotonicity Checks**
```python
# Add to scripts/generate_production_forecasts.py
# See Definition of Done section above
```

**6.2 Add Probability Validation**
```python
# Add to scripts/run_monte_carlo.py
# See Definition of Done section above
```

**6.3 Integration Tests**
```bash
# Create tests/test_core_refactor_integration.py
# See Definition of Done section above

# Run tests
.venv/bin/pytest tests/test_core_refactor_integration.py -v
```

**6.4 End-to-End Pipeline Test**
```bash
# Run full pipeline:
# 1. Training (if needed - already done)
# 2. Calibration
python scripts/calibrate_tails.py --all

# 3. Monte Carlo
python scripts/run_monte_carlo.py --horizon all

# 4. Forecast generation
python scripts/generate_production_forecasts.py

# 5. Verify database
psql $DATABASE_URL -c "SELECT * FROM forecasts.forecast_summary_1d ORDER BY forecast_date DESC LIMIT 5;"

# 6. Verify API
curl http://localhost:8000/api/forecast/quantiles?horizon=21 | jq

# 7. Verify dashboard
open http://localhost:3000
```

---

## Risk Mitigation

### 1. Backward Compatibility

**Problem:** Existing dashboards/APIs may expect old schema

**Mitigation:**
- Keep old columns (p10, p90) alongside new (p10_cal, p90_cal) during transition
- Use database views for backward compatibility
- Deprecate old endpoints with 6-month sunset period

### 2. Data Migration

**Problem:** Existing forecast data doesn't have probabilities

**Mitigation:**
- Run backfill script to compute probabilities for historical forecasts
- Mark pre-refactor forecasts with `refactor_version = 'v1'`
- Mark post-refactor forecasts with `refactor_version = 'v2'`

### 3. Calibration Drift

**Problem:** Tail calibration may drift over time as market regime changes

**Mitigation:**
- Re-run calibration monthly
- Store calibration history in `tail_calibration_params` table
- Add monitoring alert if coverage deviates >5% from target

### 4. Monte Carlo Performance

**Problem:** Adding zone-entry calculation may slow MC simulation

**Mitigation:**
- Profile path simulation code
- Use NumPy vectorization for zone checks
- Consider Numba JIT compilation if needed
- Target: <5 seconds per horizon (10k simulations)

---

## Success Metrics

### Quantitative

- **Coverage Accuracy:** P10 coverage = 10% ± 2%, P90 coverage = 90% ± 2%
- **Probability Calibration:** Observed zone-entry frequency matches predicted probability within ±5%
- **API Latency:** Forecast endpoint response time < 100ms (p95)
- **Pipeline Runtime:** Full forecast generation < 5 minutes for all horizons

### Qualitative

- Dashboard displays "XX% probability..." text for ALL forecasts
- No forecast rows with NULL prob_enter_zone (except legacy data)
- All quantile columns use Decimal (no Float precision loss)
- Monotonicity validation passes 100% of the time

---

## Effort Estimate

| Phase | Description | Hours | Dependencies |
|-------|-------------|-------|--------------|
| 0 | Pre-flight checks | 1 | None |
| 1 | Schema migration | 3 | Phase 0 |
| 2 | Calibration layer | 5 | Phase 1 |
| 3 | Probability layer | 4 | Phase 1 |
| 4 | Serving layer | 3 | Phase 2, 3 |
| 5 | Dashboard integration | 2 | Phase 4 |
| 6 | Validation & testing | 3 | Phase 2-5 |
| **Total** | **End-to-end refactor** | **21 hours** | **~3 days** |

---

## Rollout Plan

### Week 1: Development (Phases 0-3)
- Schema migration
- Calibration layer implementation
- Probability layer implementation
- Unit tests

### Week 2: Integration (Phases 4-5)
- Serving layer updates
- Dashboard integration
- Integration tests
- Staging deployment

### Week 3: Validation & Production (Phase 6)
- Production deployment
- Monitoring setup
- Performance validation
- User acceptance testing

---

## Rollback Plan

If issues arise post-deployment:

1. **Revert API changes** - Return to serving old schema (p10/p50/p90 only)
2. **Revert database writes** - Stop writing to new columns (prob_enter_zone, p10_cal, p90_cal)
3. **Revert dashboard** - Show generic "Forecast: $X - $Y" without probability
4. **Keep data** - Don't delete new columns or calibration params (for future retry)

**Time to rollback:** <30 minutes

---

## Contact & References

- **Primary Spec:** This document (CORE_MODEL_REFACTOR_SPEC.md)
- **Code Review Audit:** CODE_REVIEW_FINDINGS.md, CODE_REVIEW_ACTION_ITEMS.md
- **Training Spec:** Docs/CORE_TRAINING_SPEC_LOCKED.md
- **Architecture:** AGENTS.md (Schema boundaries, data flow)

---

**Last Updated:** 2026-02-13  
**Status:** Planning → Ready for Implementation
