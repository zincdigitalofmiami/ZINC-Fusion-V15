# Core Model Refactor - Executive Brief
## Impact on Code Review Audit & Implementation Guidance

**Date:** 2026-02-13  
**Analysis:** How the proposed P30/P50/P70 + Calibration + Probability refactor affects the recent comprehensive code review

---

## TL;DR - 3 Key Points

1. **Training Layer Already Correct** ✅
   - Core already trains P30/P50/P70 (not p10/p50/p90)
   - No changes needed to `src/fusion/core_training/`
   - Layer 1 is done

2. **Refactor Adds 3 New Layers** 🔴
   - Layer 2: Tail calibration (NEW - compute p10_cal, p90_cal)
   - Layer 3: Zone-entry probability (NEW - Monte Carlo enhancement)
   - Layer 4: Probability serving (NEW - API + dashboard)

3. **Security Issues Are Orthogonal** ⚠️
   - 5 critical audit issues are UNRELATED to model refactor
   - Must fix security issues separately (don't delay for refactor)
   - Model refactor helps with 1 issue (Float→Decimal migration)

---

## Question: Does This Change the Audit Above?

**Answer:** Partially - here's the breakdown:

### ✅ Audit Issues That This Refactor HELPS Fix

**Issue #6: Float vs Decimal for Price Data**
- **Current Problem:** `mkt.futures_1d` uses Float, `forecasts.core_cone_1d` uses Float for quantiles
- **How Refactor Helps:** Schema changes for new columns (p10_cal, p90_cal, prob_enter_zone) provide perfect opportunity to standardize ALL quantile columns to Decimal(10,6)
- **Action:** Bundle Float→Decimal migration with probability column additions
- **Impact:** Fixes precision loss in price calculations, aligns with audit recommendation

### ⚠️ Audit Issues That Are UNRELATED (Must Fix Separately)

These 5 critical issues have NOTHING to do with the model refactor:

1. **Issue #1: Connection Leak** (`frontend/src/inngest/zl-live.ts:160`)
   - Problem: Missing try-finally on receiptClient
   - Impact: Pool exhaustion risk
   - Fix: 10 minutes, unrelated to model

2. **Issue #2: No API Authentication** (`src/fusion/api/server.py` - 30+ endpoints)
   - Problem: Business intelligence exposed without auth
   - Impact: Security vulnerability
   - Fix: 2-4 hours, unrelated to model

3. **Issue #3: N+1 Specialist Query** (`src/fusion/api/server.py:351-365`)
   - Problem: 20 queries instead of 1 batch
   - Impact: 2-3 second latency
   - Fix: 30 minutes, unrelated to model

4. **Issue #4: Missing DB Error Handling** (`src/fusion/api/server.py` - multiple)
   - Problem: Unhandled psycopg2.Error exceptions
   - Impact: Production failures with traceback exposure
   - Fix: 1-2 hours, unrelated to model

5. **Issue #7: N+1 Backfill Query** (`frontend/src/inngest/board-crush-daily.ts:291`)
   - Problem: 500 queries instead of batch fetch
   - Impact: Backfill performance
   - Fix: 30 minutes, unrelated to model

**CRITICAL RECOMMENDATION:** Do NOT delay fixing these security/performance issues while waiting for model refactor. Fix them NOW in parallel.

### 🔄 Audit Issues With CHANGED Scope

**Issue #9: Missing Indexes on training.matrix_1d**
- **Current Scope:** Add indexes to training.matrix_1d
- **New Scope:** Add indexes to ALL forecast tables that get new columns
- **Additional Indexes Needed:**
  - `forecasts.forecast_summary_1d.prob_enter_zone`
  - `forecasts.core_mc_1d.prob_enter_p30_p70_within_h`
- **Impact:** Slightly more work, but still straightforward

---

## Question: How Do We Fix Things?

**Answer:** Follow the implementation specifications provided:

### 📚 Documentation Provided

1. **CORE_MODEL_REFACTOR_SPEC.md** (24KB)
   - Comprehensive refactor specification
   - Layer-by-layer implementation guide
   - Database schema changes with exact SQL
   - Testing & validation checklist
   - 21-hour effort estimate
   - Rollout plan with rollback procedures

2. **CORE_MODEL_REFACTOR_QUICK_REF.md** (21KB)
   - File-by-file action checklist
   - Exact line numbers to modify
   - Copy-paste ready code snippets
   - Database migration commands
   - Validation commands

3. **This Document** (CORE_MODEL_REFACTOR_EXEC_BRIEF.md)
   - Executive summary
   - Impact analysis on audit
   - Prioritization guidance

### 🎯 Implementation Path

**Step 1: Pre-flight (1 hour)**
- Verify training layer is correct ✅ (already confirmed)
- Review both specification documents
- Set up development branch

**Step 2: Schema Migration (3 hours)**
- Add `model.tail_calibration_params` table
- Add probability columns to `forecasts.core_mc_1d`
- Add probability columns to `forecasts.forecast_summary_1d`
- Bonus: Migrate Float → Decimal (fixes audit issue #6)
- Add indexes for new columns

**Step 3: Calibration Layer - NEW (5 hours)**
- Create `src/fusion/calibration/tail_calibration.py`
- Implement tail calibration algorithm
- Create `scripts/calibrate_tails.py` runner
- Test calibration on historical data
- Validate coverage targets (p10: ~10%, p90: ~90%)

**Step 4: Probability Layer - ENHANCE (4 hours)**
- Add zone-entry calculation to `scripts/run_monte_carlo.py`
- Add tail touch probability calculation
- Update MC database persistence
- Test probability calculation
- Validate bounds (0 ≤ prob ≤ 1)

**Step 5: Serving Layer - INTEGRATE (3 hours)**
- Update `scripts/generate_production_forecasts.py`
- Apply tail calibration to forecasts
- Fetch and persist probabilities
- Update API endpoints to serve probabilities
- Add monotonicity validation

**Step 6: Dashboard - DISPLAY (2 hours - Frontend)**
- Update forecast display component
- Change from: "ZL forecast: $42.30 - $45.80"
- To: "72% probability ZL enters $42.30 - $45.80 within 21 days"

**Step 7: Validation (3 hours)**
- Add monotonicity checks
- Add probability validation
- Write integration tests
- End-to-end pipeline test

**Total:** 21 hours (~3 days for single developer)

---

## Critical Decisions Required

### Decision 1: Timing

**Option A: Do Security Fixes First, Then Refactor**
- Pros: Security vulnerabilities closed immediately
- Pros: Refactor can proceed without pressure
- Cons: Dashboard still shows generic forecasts
- **Recommended:** ✅ YES

**Option B: Do Refactor First, Then Security Fixes**
- Pros: New forecast features ship sooner
- Cons: Security vulnerabilities remain open longer
- Cons: High risk if refactor takes longer than expected
- **Recommended:** ❌ NO

**Option C: Do Both in Parallel**
- Pros: Everything ships together
- Cons: Requires 2 developers
- Cons: Higher merge conflict risk
- **Recommended:** ⚠️ MAYBE (if resources available)

### Decision 2: Float → Decimal Migration

**Option A: Bundle with Refactor**
- Pros: Single migration, single deployment
- Pros: All quantile columns consistent
- Cons: Larger change surface
- **Recommended:** ✅ YES (if refactor timing is acceptable)

**Option B: Separate Migration**
- Pros: Smaller, safer change
- Cons: Two migrations instead of one
- **Recommended:** ⚠️ ONLY if refactor delayed >4 weeks

### Decision 3: Backward Compatibility

**Option A: Keep Old Columns During Transition**
- Keep: `calibrated_p10`, `calibrated_p90`, `opp`, `ruin`
- Add: `p10_cal`, `p90_cal`, `prob_enter_zone`
- Deprecate old columns after 6 months
- **Recommended:** ✅ YES (safest)

**Option B: Clean Break**
- Remove old columns immediately
- Force all consumers to update
- **Recommended:** ❌ NO (too risky)

---

## Validation: How to Know It's Complete

The refactor is NOT done until ALL of these pass:

### 1. Schema Check
```sql
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_schema = 'forecasts'
  AND table_name = 'forecast_summary_1d'
  AND column_name IN ('p10_cal', 'p30', 'p50', 'p70', 'p90_cal', 'prob_enter_zone');

-- Expected: 6 rows returned, all with Decimal or Float type
```

### 2. Monotonicity Check
```python
# Must pass for 100% of forecast rows
assert p10_cal <= p30 <= p50 <= p70 <= p90_cal
```

### 3. Probability Bounds Check
```python
# Must pass for 100% of forecast rows
assert 0 <= prob_enter_zone <= 1
```

### 4. API Response Check
```bash
curl http://localhost:8000/api/forecast/quantiles?horizon=21 | jq

# Expected response includes:
{
  "quantiles": {
    "p10_cal": 40.25,
    "p30": 41.50,
    "p50": 43.00,
    "p70": 44.50,
    "p90_cal": 45.75,
    "prob_enter_zone": 0.72
  },
  "headline_probability": 0.72
}
```

### 5. Dashboard Display Check
```
Visit: http://localhost:3000

Expected text:
"72% probability ZL enters $41.50 - $44.50 within 21 days"

NOT:
"ZL forecast: $41.50 - $44.50"
```

---

## Risk Assessment

### Low Risk (Already Working)
- ✅ Training layer (no changes needed)
- ✅ OOF generation (already produces p30/p50/p70)
- ✅ Database schema (80% ready, just needs 3 new columns)

### Medium Risk (New Code)
- ⚠️ Tail calibration algorithm (new math, needs validation)
- ⚠️ Zone-entry probability (new MC logic, needs testing)
- ⚠️ Float → Decimal migration (data type change, needs backfill testing)

### High Risk (Integration Points)
- 🔴 API backward compatibility (multiple consumers)
- 🔴 Dashboard display (user-facing change)
- 🔴 Forecast generation pipeline (orchestration of 4 layers)

### Mitigation Strategies

1. **Feature Flags:** Deploy refactor behind flag, enable gradually
2. **Parallel Processing:** Keep old pipeline running during transition
3. **Rollback Plan:** Revert API/dashboard without touching database
4. **Monitoring:** Add alerts for monotonicity violations, probability out-of-bounds
5. **Staging:** Full end-to-end testing on staging before production

---

## Success Metrics (Post-Deployment)

### Technical Metrics
- ✅ Coverage accuracy: P10 = 10% ± 2%, P90 = 90% ± 2%
- ✅ Probability calibration: Observed zone-entry matches prediction ± 5%
- ✅ API latency: <100ms p95 for forecast endpoint
- ✅ Pipeline runtime: <5 minutes for all horizons
- ✅ Zero monotonicity violations
- ✅ Zero out-of-bounds probabilities

### Business Metrics
- ✅ Dashboard displays "XX% probability..." for ALL forecasts
- ✅ No NULL prob_enter_zone values (except legacy data)
- ✅ User feedback positive on new probability display
- ✅ No production incidents related to refactor

---

## Recommended Action Plan

### Immediate (This Week)
1. **Fix 4 critical security issues** (Issues #1, #2, #3, #4)
   - Connection leak (10 min)
   - API authentication (2-4 hours)
   - N+1 queries (1 hour total)
   - DB error handling (1-2 hours)
   - **Total:** 4-7 hours

2. **Review refactor specifications**
   - Team reads CORE_MODEL_REFACTOR_SPEC.md
   - Decides on timing (Option A vs C)
   - Assigns resources

### Next Week (If Proceeding with Refactor)
1. **Schema migration** (3 hours)
2. **Calibration layer** (5 hours)
3. **Probability layer** (4 hours)

### Week After (Refactor Completion)
1. **Serving layer** (3 hours)
2. **Dashboard integration** (2 hours)
3. **Validation & testing** (3 hours)

### Week 4 (Production Deployment)
1. Deploy to staging
2. Run validation suite
3. Deploy to production with monitoring
4. Collect user feedback

---

## Who to Contact

- **Refactor Spec Questions:** See CORE_MODEL_REFACTOR_SPEC.md
- **Implementation Details:** See CORE_MODEL_REFACTOR_QUICK_REF.md
- **Audit Issues:** See CODE_REVIEW_FINDINGS.md, CODE_REVIEW_ACTION_ITEMS.md
- **Architecture:** See AGENTS.md

---

## Final Recommendation

**Do the security fixes immediately.** They are critical and unrelated to the model refactor.

**Then do the refactor.** It's well-specified, has clear validation criteria, and provides an opportunity to fix the Float→Decimal issue from the audit.

**Timeline:** 
- Security fixes: This week (4-7 hours)
- Refactor: Next 2-3 weeks (21 hours)
- Total: 3-4 weeks to completion

**Risk Level:** Medium (manageable with proper staging and rollback plans)

**Business Value:** High (user-facing probability display is more intuitive than raw quantiles)

---

**Last Updated:** 2026-02-13  
**Status:** Ready for stakeholder decision on timing and resourcing
