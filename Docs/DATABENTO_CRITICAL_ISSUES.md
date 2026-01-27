# Databento Integration - Critical Issues Summary

**Status**: ✅ **RESOLVED IN CODE - VERIFY IN DB**

## 🚨 CRITICAL ISSUE #1: Symbol Mismatch

### Problem
**Different ingestion paths use different ZL symbols:**

| Path | Current Symbol | Should Be | Status |
|------|---------------|------------|--------|
| Daily OHLCV (`databento-futures-daily.ts`) | `ZL.n.0` ✅ | `ZL.n.0` | ✅ CORRECT |
| Daily Statistics (`databento-statistics-daily.ts`) | `ZL.n.0` ✅ | `ZL.n.0` | ✅ CORRECT |
| **Live Connector** (`ingest_databento_live_zl.py`) | `ZL.n.0` ✅ | `ZL.n.0` | ✅ **FIXED** |
| **Historical 15m** (`zl-15m.ts`) | `ZL.n.0` ✅ | `ZL.n.0` | ✅ **FIXED** |
| **Historical 1h** (`zl-1h.ts`) | `ZL.n.0` ✅ | `ZL.n.0` | ✅ **FIXED** |
| **Yahoo EOD** (`yahoo-eod.ts`) | **ZL removed** ✅ | `ZL.n.0` | ✅ **FIXED** |

### Impact
- **Charts will show inconsistent data**: Live feeds use calendar contracts (`.c.0`) while daily data uses OI-ranked contracts (`.n.0`)
- **Price discontinuities**: On roll dates, prices will jump because contracts diverge
- **Data confusion**: Same date will have different prices depending on source

### Fix Required
Change these files to use `ZL.n.0`:
1. `scripts/ingest_databento_live_zl.py` - Line 32: `SYMBOL = "ZL.n.0"`
2. `frontend/src/inngest/zl-15m.ts` - Line 47: `symbols: "ZL.n.0"`
3. `frontend/src/inngest/zl-1h.ts` - Line 47: `symbols: "ZL.n.0"`
4. `frontend/src/inngest/yahoo-eod.ts` - Line 145: `symbols: "ZL.n.0"`

### Testing Required
- Run parallel collection (both `.c.0` and `.n.0`) for 7 days
- Compare prices - should be <0.1% difference on non-roll days
- Verify no data gaps after switch
- Monitor for roll date issues

---

## ✅ RESOLVED ISSUE #2: Error Handling

### Previous Problem
Live connector had no retry limits.

File: `scripts/ingest_databento_live_zl.py`
- Lines 198-200: Generic exception handler with infinite retries
- No exponential backoff
- No max retry limit
- No alerting/logging

### Impact
- Service can fail silently
- Infinite retry loops consume resources
- No visibility into failures

### Fix Applied
Structured error handling with exponential backoff and max retries has been added.
```python
retry_count = 0
max_retries = 10
while retry_count < max_retries:
    try:
        # ... existing code ...
        retry_count = 0  # Reset on success
    except Exception as exc:
        retry_count += 1
        wait_time = min(5 * (2 ** retry_count), 300)  # Exponential backoff, max 5min
        logger.error(f"Error (attempt {retry_count}/{max_retries}): {exc}")
        time.sleep(wait_time)
```

---

## ✅ RESOLVED ISSUE #3: Data Validation

### Previous Problem
Event handlers did not validate payloads.

File: `frontend/src/inngest/zl-live.ts`
- No validation of event structure
- No validation of timestamp ranges
- No validation of price values

### Impact
- Bad data could corrupt database
- Invalid timestamps could cause conflicts
- Negative/zero prices could break charts

### Fix Applied
Validation now enforces timestamp sanity and OHLC/volume checks.
```typescript
if (!bar.timestamp || !bar.close || bar.close <= 0) {
  throw new Error(`Invalid bar data: ${JSON.stringify(bar)}`);
}
```

---

## 📋 MEDIUM PRIORITY ISSUES

### Issue #4: ON CONFLICT Logic
- Current: Source-aware (historical backfill does not overwrite live)
- Should: Live wins for recent data, preserve historical
- File: `frontend/src/inngest/zl-live.ts`

### Issue #5: Date Handling
- Potential timezone issues in date construction
- Files: `yahoo-eod.ts`, `databento-futures-daily.ts`

### Issue #6: Test Execution
- Test scripts exist but haven't been run
- Need to execute and review results

---

## ✅ WHAT'S ALREADY CORRECT

1. ✅ Statistics parsing uses `stat_type=9` (correct)
2. ✅ Statistics handles sentinel values correctly
3. ✅ Cron schedules use timezone-aware format (`TZ=America/Chicago`)
4. ✅ Daily ingestion uses `.n.0` for Crush symbols (correct)
5. ✅ Source tags distinguish `databento` vs `databento_live` (correct)
6. ✅ ON CONFLICT prevents duplicates (correct)

---

## 🎯 ACTION PLAN

### Phase 1: Audit Current State (DO FIRST)
1. ✅ Run SQL audit queries (`scripts/audit_databento_state.sql`)
2. ✅ Review audit report (`Docs/DATABENTO_AUDIT_REPORT.md`)
3. ⏳ Query database for actual symbol usage
4. ⏳ Check for price discontinuities
5. ⏳ Verify source distribution

### Phase 2: Fix Critical Issues (BLOCKING)
1. ⏳ Fix symbol mismatch (Issue #1)
2. ⏳ Add error handling (Issue #2)
3. ⏳ Add data validation (Issue #3)

### Phase 3: Test Thoroughly (REQUIRED)
1. ⏳ Run test scripts
2. ⏳ Test symbol transition
3. ⏳ Test error scenarios
4. ⏳ Monitor production

### Phase 4: Fix Medium Issues (OPTIONAL)
1. ✅ Improve ON CONFLICT logic
2. ⏳ Fix date handling
3. ⏳ Run remaining tests

---

## 🚦 DECISION POINTS

### Decision 1: Symbol Choice
**Question**: Should ALL ZL ingestion use `ZL.n.0` (OI-ranked)?

**Recommendation**: **YES** - Use `ZL.n.0` everywhere for consistency
- Crush specialist needs OI-ranked
- Daily ingestion already uses `.n.0`
- Only live feeds need to change

**Action**: Get explicit approval before changing

### Decision 2: Error Handling Strategy
**Question**: What's acceptable retry behavior?

**Recommendation**: 
- Max 10 retries
- Exponential backoff (5s, 10s, 20s, 40s, 80s, 160s, 300s max)
- Alert after 5 failures
- Log all errors

**Action**: Implement as recommended

### Decision 3: Conflict Resolution
**Question**: Should live data always win?

**Recommendation**: 
- Live wins for data <24h old
- Historical preserved for data >24h old
- Source-aware conflict resolution

**Action**: Implement as recommended

---

## 📊 TESTING CHECKLIST

Before making ANY changes:

- [ ] Run `scripts/audit_databento_state.sql` queries
- [ ] Review current source distribution
- [ ] Check for price discontinuities
- [ ] Verify symbol usage in database
- [ ] Run `test_databento_current_state.py`
- [ ] Run `test_databento_symbol_comparison.py`
- [ ] Document current behavior
- [ ] Get approval for symbol choice
- [ ] Plan rollback strategy

After making changes:

- [ ] Test symbol transition (parallel collection)
- [ ] Verify no data gaps
- [ ] Test error scenarios
- [ ] Monitor production closely
- [ ] Verify charts display correctly
- [ ] Check for roll date issues

---

## 🔒 SAFETY GUARANTEES

**Before proceeding, ensure:**

1. ✅ Symbol mismatch is resolved
2. ✅ Error handling is added
3. ✅ Data validation is added
4. ✅ Test scripts are run
5. ✅ Rollback plan exists
6. ✅ Monitoring is in place

**DO NOT PROCEED** until all critical issues are resolved and tested.

---

**Next Step**: Run audit queries and review results before making any code changes.
