# Deferred Issues Status Report

**Date:** 2026-02-13  
**Review:** Comprehensive Code Review Follow-up  
**Branch:** copilot/full-code-review-inngest-schema-datasets-apis

---

## Summary

### Issues Completed ✅ (4 of 7)

| Issue | Description | Status | Effort |
|-------|-------------|--------|--------|
| #7 | N+1 backfill query (Inngest) | ✅ Fixed | 30 min |
| #8 | INTERVAL injection risk | ✅ Fixed | 30 min |
| #9 | Missing indexes (training.matrix_1d) | ✅ Fixed | 15 min |
| #10 | FRED duplication risk | ✅ Already Resolved | 0 min |

### Issues Remaining (3 of 7)

| Issue | Description | Priority | Estimated Effort |
|-------|-------------|----------|------------------|
| #5 | Missing metadata schema | High | 2 hours |
| #6 | Float vs Decimal | High | 3-4 hours |
| #11 | No rate limiting | Medium | 1 hour (requires new dependency) |
| #12 | Vegas schema | Low | Documentation only |

---

## Detailed Status

### ✅ Issue #7: N+1 Backfill Query (FIXED)

**File:** `frontend/src/inngest/board-crush-daily.ts:287-317`  
**Problem:** Loop executed individual SELECT for each date  
**Fix:** Batch fetch with `WHERE trade_date = ANY($1)`  
**Impact:** 100 queries → 1 query (99% reduction)

**Commit:** `6e7a269`

---

### ✅ Issue #8: INTERVAL Injection Risk (FIXED)

**Files:** `src/fusion/api/server.py` (3 locations)  
**Problem:** String interpolation in INTERVAL clause  
**Fix:** Parameterized queries with `INTERVAL '1 hour' * $1`  
**Impact:** Eliminated SQL injection risk

**Fixed Endpoints:**
1. `/api/zl/intraday` (Line 1297)
2. `/api/zl/intraday/ohlc` (Line 1348)
3. `/api/pulse/domain/{domain}/history` (Line 1595)

**Commit:** `4f5af1c`

---

### ✅ Issue #9: Missing Indexes (FIXED)

**File:** `prisma/schema.prisma:2925-2926`  
**Problem:** No indexes on training.matrix_1d for common queries  
**Fix:** Added 2 indexes:
- `@@index([symbol, trade_date])` - For symbol-based time-series queries
- `@@index([matrix_version])` - For version filtering

**Impact:** Faster training data loading

**Commit:** `6e7a269`

**Note:** Migration required to apply indexes to database

---

### ✅ Issue #10: FRED Duplication Risk (ALREADY RESOLVED)

**Files:** All 7 FRED tables in `econ` schema  
**Expected Problem:** No idempotency for parallel segment processing  
**Actual Status:** ✅ Already protected

**Database Protection:**
```prisma
model rates_1d {
  series_id      String
  event_date     DateTime
  row_hash       String?   // Idempotency support
  
  @@unique([series_id, event_date])  // Prevents duplicates ✅
  @@schema("econ")
}
```

**All 7 FRED tables verified:**
- `econ.rates_1d` ✅
- `econ.activity_1d` ✅
- `econ.commodities_1d` ✅
- `econ.vol_indices_1d` ✅
- `econ.inflation_1d` ✅
- `econ.labor_1d` ✅
- `econ.money_1d` ✅

**Conclusion:** Unique constraint prevents duplicates at database level. Parallel segment processing is safe.

---

## Remaining Issues

### ⚠️ Issue #5: Missing Metadata Schema (HIGH PRIORITY)

**Status:** NOT STARTED  
**Effort:** 2 hours  
**Impact:** Architecture compliance

**Required Actions:**
1. Add `metadata` to datasource schemas list
2. Create `metadata.instrument` table
3. Create `metadata.symbol_mapping` table
4. Create Prisma migration
5. Update documentation

**Purpose:** Canonical instrument registry and symbol deduplication control plane (per AGENTS.md architecture)

---

### ⚠️ Issue #6: Float vs Decimal (HIGH PRIORITY)

**Status:** NOT STARTED  
**Effort:** 3-4 hours  
**Impact:** Data precision in monetary calculations

**Affected Tables:**
- `mkt.futures_1d` (open, high, low, close)
- `model.core_cone_1d` (all quantile columns)
- Other price/monetary tables

**Required Actions:**
1. Identify all Float columns that should be Decimal
2. Create migration: Float → Decimal(10,6)
3. Test precision in calculations
4. Validate forecasts maintain accuracy

**Risk:** Large tables, requires careful migration testing

---

### ℹ️ Issue #11: No Rate Limiting (MEDIUM PRIORITY)

**Status:** DEFERRED (requires new dependency)  
**Effort:** 1 hour  
**Impact:** DoS prevention

**Options:**
1. Add `slowapi` package (external dependency)
2. Implement custom rate limiting
3. Use API gateway/reverse proxy for rate limiting

**Decision Needed:** Approve external dependency or defer to infrastructure layer

---

### ℹ️ Issue #12: Vegas Schema (LOW PRIORITY - DOCUMENTATION)

**Status:** DOCUMENTED  
**Effort:** 0 minutes (documentation only)  

**Finding:** Vegas schema is a separate project (casino analytics) in same database

**Current State:**
- 22 vegas tables exist in schema
- Glide ingestion pipeline active
- API endpoint `/api/vegas-intel/status` present
- AGENTS.md says: "Do not touch vegas schema: stay out"

**Resolution:** Per AGENTS.md policy, vegas schema is intentionally isolated. No action required beyond documentation.

**Recommendation:** If vegas should be removed, that's a separate architectural decision requiring stakeholder approval.

---

## Migration Plan

### Database Migrations Required

**1. Add Indexes to training.matrix_1d**
```bash
npx prisma migrate dev --name add-matrix-indexes
```

**2. Add Metadata Schema (If approved)**
```bash
npx prisma migrate dev --name add-metadata-schema
```

**3. Float to Decimal (If approved)**
```bash
npx prisma migrate dev --name float-to-decimal-precision
```

### Testing Plan

**After Migrations:**
1. Verify index performance improvement in training queries
2. Validate metadata schema structure
3. Test decimal precision in forecast calculations
4. Run full test suite

---

## Total Progress

**Completed:** 4 of 7 issues (57%)  
**Time Invested:** 1.25 hours  
**Remaining:** 6+ hours (depends on High Priority decisions)

**Overall Impact:**
- ✅ Performance optimized (N+1 eliminated, indexes added)
- ✅ Security hardened (INTERVAL injection fixed)
- ✅ Data integrity confirmed (FRED protection verified)

---

## Recommendations

**This Week:**
1. ✅ Deploy current fixes to production (already done via Vercel push)
2. Create database migrations for new indexes
3. Decide on metadata schema implementation
4. Plan Float→Decimal migration strategy

**Next Sprint:**
1. Implement metadata schema (Issue #5)
2. Execute Float→Decimal migration (Issue #6)
3. Evaluate rate limiting options (Issue #11)

**Long Term:**
- Consider separate database for vegas project
- Regular index performance monitoring
- Precision validation in risk calculations
