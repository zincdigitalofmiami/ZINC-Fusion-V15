# Databento Integration - Comprehensive Audit Report

**Date**: 2026-01-27  
**Purpose**: Read-only audit before implementing plan changes  
**Status**: ⚠️ AUDIT SNAPSHOT (2026-01-27) - See `Docs/DATABENTO_FIX_APPLIED.md` for current state

## Executive Summary

**CRITICAL FINDING**: There is a **symbol mismatch** between different ingestion paths:
- **Daily futures ingestion** (`databento-futures-daily.ts`): Uses `ZL.n.0` (OI-ranked) ✅ CORRECT
- **Live connector** (`ingest_databento_live_zl.py`): Uses `ZL.c.0` (calendar) ⚠️ MISMATCH
- **Historical 15m/1h** (`zl-15m.ts`, `zl-1h.ts`): Uses `ZL.c.0` (calendar) ⚠️ MISMATCH
- **Yahoo EOD** (`yahoo-eod.ts`): Uses `ZL.c.0` (calendar) ⚠️ MISMATCH

**Impact**: Charts will show inconsistent data - live feeds use calendar contracts while daily ingestion uses OI-ranked contracts. This will cause price discontinuities on roll dates.

---

## 1. Symbol Consistency Issues

### 1.1 Symbol Mismatch Across Ingestion Paths

| File | Symbol Used | Contract Type | Purpose | Status |
|------|-------------|---------------|---------|--------|
| `databento-futures-daily.ts` | `ZL.n.0` | OI-ranked | Daily OHLCV for `mkt.futures_1d` | ✅ Correct |
| `databento-statistics-daily.ts` | `ZL.n.0` | OI-ranked | Open Interest for `mkt.futures_1d` | ✅ Correct |
| `ingest_databento_live_zl.py` | `ZL.c.0` | Calendar | Live 15m/1h/1d for `analytics.zl_price_*` | ⚠️ **MISMATCH** |
| `zl-15m.ts` | `ZL.c.0` | Calendar | Historical 15m for `analytics.zl_price_15m` | ⚠️ **MISMATCH** |
| `zl-1h.ts` | `ZL.c.0` | Calendar | Historical 1h for `analytics.zl_price_1h` | ⚠️ **MISMATCH** |
| `yahoo-eod.ts` | `ZL.c.0` | Calendar | Daily ZL for `mkt.futures_1d` + `analytics.zl_price_1d` | ⚠️ **MISMATCH** |

### 1.2 Impact Analysis

**Problem**: 
- Daily ingestion writes `ZL.n.0` data to `mkt.futures_1d` (OI-ranked)
- Live feeds write `ZL.c.0` data to `analytics.zl_price_*` (calendar)
- Charts read from `analytics.zl_price_*` tables
- **Result**: Charts show calendar contract prices, but daily data shows OI-ranked prices

**When it breaks**:
- On roll dates, `ZL.c.0` and `ZL.n.0` diverge
- Price jumps will appear in charts
- Daily aggregates will not match intraday data

**Recommendation**: 
- **Option A (Recommended)**: Change all to `ZL.n.0` (OI-ranked) for consistency
  - Update `ingest_databento_live_zl.py`: `SYMBOL = "ZL.n.0"`
  - Update `zl-15m.ts`: `symbols: "ZL.n.0"`
  - Update `zl-1h.ts`: `symbols: "ZL.n.0"`
  - Update `yahoo-eod.ts`: `symbols: "ZL.n.0"`
- **Option B**: Change daily ingestion to `ZL.c.0` (calendar)
  - Less ideal because Crush specialist needs OI-ranked for consistency

---

## 2. Source Tag Consistency

### 2.1 Current Source Tags

| Table | Source Values Found | Purpose |
|-------|-------------------|---------|
| `analytics.zl_price_15m` | `databento`, `databento_live` | Chart data |
| `analytics.zl_price_1h` | `databento`, `databento_live` | Chart data |
| `analytics.zl_price_1d` | `databento`, `yahoo`, `databento_live` | Chart data |
| `mkt.futures_1d` | `databento`, `yahoo_eod`, `databento_live` | Training data |

### 2.2 Source Tag Issues

**Issue**: Multiple source tags for same data type:
- `databento` (historical HTTP)
- `databento_live` (live TCP)
- Both write to same tables

**Impact**: 
- Can't distinguish historical vs live data easily
- Potential conflicts if both write same timestamp

**Recommendation**: 
- Keep `databento_live` for live feeds (distinct from historical)
- Keep `databento` for historical HTTP pulls
- This is actually correct - they serve different purposes

---

## 3. Data Flow Analysis

### 3.1 Current Data Flows

```
LIVE PATH (Real-time):
  Databento Live API (TCP)
    → ingest_databento_live_zl.py (Python)
    → Inngest events (zl.bar.15m, zl.bar.1h, zl.bar.1d)
    → zl-live.ts handlers
    → analytics.zl_price_15m/1h/1d (source='databento_live')
    → Charts

HISTORICAL PATH (24h delayed):
  Databento HTTP API
    → zl-15m.ts (Inngest, hourly)
    → zl-1h.ts (Inngest, hourly)
    → analytics.zl_price_15m/1h (source='databento')
    → Charts

DAILY PATH (Historical):
  Databento HTTP API
    → databento-futures-daily.ts (Inngest, daily 5AM CT)
    → mkt.futures_1d (source='databento')
    → Crush specialist training

DAILY PATH (Yahoo fallback):
  Yahoo Finance API
    → yahoo-eod.ts (Inngest, daily 5AM CT)
    → mkt.futures_1d (source='yahoo_eod')
    → analytics.zl_price_1d (source='yahoo')
    → Charts
```

### 3.2 Potential Conflicts

**Conflict 1**: Live and historical both write to `analytics.zl_price_15m`
- Live writes real-time (current session)
- Historical writes 24h+ old data
- **Resolution**: ON CONFLICT handles this, but timestamps shouldn't overlap

**Conflict 2**: `yahoo-eod.ts` and `databento-futures-daily.ts` both write ZL to `mkt.futures_1d`
- Yahoo uses `ZL.c.0` (calendar)
- Databento uses `ZL.n.0` (OI-ranked)
- **Resolution**: Source tags differ, but symbol mismatch still causes confusion

**Conflict 3**: `yahoo-eod.ts` syncs ZL to `analytics.zl_price_1d`
- Uses `ZL.c.0` (calendar)
- May conflict with live `zl.bar.1d` events
- **Resolution**: ON CONFLICT handles, but symbol mismatch remains

---

## 4. Code Quality Issues

### 4.1 Missing Error Handling

**File**: `ingest_databento_live_zl.py`
- Line 198-200: Generic exception handler with 5s sleep
- **Issue**: No exponential backoff, no max retries, no alerting
- **Risk**: Silent failures, infinite retry loops

**Recommendation**: Add structured error handling:
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

### 4.2 Missing Validation

**File**: `zl-live.ts`
- No validation of event payload structure
- No validation of timestamp ranges
- **Risk**: Bad data could corrupt database

**Recommendation**: Add validation:
```typescript
if (!bar.timestamp || !bar.close || bar.close <= 0) {
  throw new Error(`Invalid bar data: ${JSON.stringify(bar)}`);
}
```

### 4.3 Date Handling Issues

**File**: `yahoo-eod.ts`
- Line 159-163: Date construction from UTC components
- **Issue**: May not handle timezone correctly
- **Risk**: Off-by-one day errors

**File**: `databento-futures-daily.ts`
- Line 184-188: Similar date construction
- **Issue**: Same potential timezone issues

---

## 5. Database Schema Issues

### 5.1 Table Structure

**Tables**: `analytics.zl_price_15m`, `analytics.zl_price_1h`, `analytics.zl_price_1d`

**Issues**:
- `zl_price_15m`: Uses `id` as primary key, `timestamp` as unique
- `zl_price_1h`: Uses `timestamp` as primary key
- `zl_price_1d`: Uses `event_date` as primary key
- **Inconsistency**: Mixed primary key strategies

**Impact**: 
- `zl_price_15m` has redundant `id` column
- All three tables have different key structures

**Recommendation**: 
- Standardize on `timestamp`/`event_date` as primary key (remove `id` from `zl_price_15m`)
- Or keep as-is if there's a reason for the difference

### 5.2 ON CONFLICT Behavior

**File**: `zl-live.ts`
- Lines 58-69, 106-112, 144-150: ON CONFLICT DO UPDATE
- **Issue**: Always overwrites existing data, even if source differs
- **Risk**: Live data could overwrite historical data incorrectly

**Example**:
```sql
ON CONFLICT (timestamp) DO UPDATE SET
  open = EXCLUDED.open,  -- Always overwrites
  ...
```

**Recommendation**: Add source check:
```sql
ON CONFLICT (timestamp) DO UPDATE SET
  open = CASE 
    WHEN EXCLUDED.source = 'databento_live' THEN EXCLUDED.open
    WHEN mkt.source IS NULL THEN EXCLUDED.open
    ELSE mkt.open
  END,
  ...
```

---

## 6. Plan Implementation Issues

### 6.1 Plan vs Reality

**Plan says**:
- Use `.n.0` for Crush-relevant symbols (ZL/ZS/ZM) ✅ Implemented in daily
- Use `.c.0` for Energy symbols ✅ Implemented in daily
- **BUT**: Plan doesn't address live feeds or historical 15m/1h

**Reality**:
- Daily ingestion: ✅ Correct (uses `.n.0` for ZL)
- Live feeds: ❌ Wrong (uses `.c.0` for ZL)
- Historical 15m/1h: ❌ Wrong (uses `.c.0` for ZL)

### 6.2 Missing Implementation

**Plan Phase 1**: ✅ Complete (statistics parsing added)
**Plan Phase 2**: ✅ Complete (OHLCV daily function exists)
**Plan Phase 3**: ✅ Complete (statistics daily function exists)
**Plan Phase 4**: ✅ Complete (functions exported)
**Plan Phase 5**: ✅ Complete (scheduling configured)

**BUT**: Plan doesn't address:
- Live connector symbol choice
- Historical 15m/1h symbol choice
- Symbol consistency across all paths

---

## 7. Testing Gaps

### 7.1 Missing Tests

**No tests for**:
- Symbol consistency across ingestion paths
- Source tag conflicts
- ON CONFLICT behavior with different sources
- Date/timezone handling
- Error recovery in live connector

### 7.2 Test Scripts Created But Not Run

**Test scripts exist** (from previous work):
- `test_databento_current_state.py`
- `test_databento_symbol_comparison.py`
- `test_databento_live_connector.py`
- etc.

**Status**: Scripts created but results not reviewed

**Recommendation**: Run all test scripts and review results before proceeding

---

## 8. Critical Stoppers

### 8.1 MUST FIX BEFORE PROCEEDING

1. **Symbol Mismatch** ⚠️ **CRITICAL**
   - All ZL ingestion must use same symbol (`ZL.n.0` recommended)
   - Affects: `ingest_databento_live_zl.py`, `zl-15m.ts`, `zl-1h.ts`, `yahoo-eod.ts`

2. **Error Handling** ⚠️ **HIGH**
   - Live connector needs retry limits and exponential backoff
   - Affects: `ingest_databento_live_zl.py`

3. **Data Validation** ⚠️ **HIGH**
   - Event handlers need payload validation
   - Affects: `zl-live.ts`

### 8.2 SHOULD FIX

4. **ON CONFLICT Logic** ⚠️ **MEDIUM**
   - Add source-aware conflict resolution
   - Affects: `zl-live.ts`

5. **Date Handling** ⚠️ **MEDIUM**
   - Standardize date construction
   - Affects: Multiple files

6. **Test Execution** ⚠️ **MEDIUM**
   - Run existing test scripts
   - Review results

---

## 9. Recommendations

### 9.1 Immediate Actions (Before Any Code Changes)

1. **Run Test Scripts**
   ```bash
   python scripts/test_databento_current_state.py
   python scripts/test_databento_symbol_comparison.py
   # Review all results
   ```

2. **Query Database for Current State**
   ```sql
   -- Check symbol usage in source data
   SELECT source, COUNT(*), MIN(timestamp), MAX(timestamp)
   FROM analytics.zl_price_15m
   GROUP BY source;
   
   -- Check for price discontinuities
   SELECT timestamp, close, 
          LAG(close) OVER (ORDER BY timestamp) as prev_close,
          ABS(close - LAG(close) OVER (ORDER BY timestamp)) / LAG(close) OVER (ORDER BY timestamp) * 100 as pct_change
   FROM analytics.zl_price_15m
   WHERE timestamp >= NOW() - INTERVAL '7 days'
   ORDER BY pct_change DESC
   LIMIT 20;
   ```

3. **Document Current Behavior**
   - What symbol is actually being used in production?
   - Are there any roll date issues visible?
   - What's the source distribution?

### 9.2 Fix Strategy

**Phase 1: Symbol Standardization** (CRITICAL)
- Change all ZL ingestion to `ZL.n.0`
- Update: `ingest_databento_live_zl.py`, `zl-15m.ts`, `zl-1h.ts`, `yahoo-eod.ts`
- Test: Verify no data gaps after change

**Phase 2: Error Handling** (HIGH)
- Add retry logic to live connector
- Add validation to event handlers
- Test: Simulate failures

**Phase 3: Conflict Resolution** (MEDIUM)
- Improve ON CONFLICT logic
- Test: Verify source-aware updates

**Phase 4: Testing** (ONGOING)
- Run all test scripts
- Monitor production after changes

---

## 10. Risk Assessment

### 10.1 High Risk Changes

**Changing symbol from `.c.0` to `.n.0`**:
- **Risk**: Price discontinuities during transition
- **Mitigation**: 
  - Run parallel collection first (both symbols)
  - Compare prices for 7 days
  - Switch only after validation
  - Keep old symbol as fallback

**Modifying live connector**:
- **Risk**: Service interruption
- **Mitigation**:
  - Deploy to staging first
  - Monitor closely
  - Have rollback plan

### 10.2 Low Risk Changes

**Adding error handling**:
- **Risk**: Minimal (additive only)
- **Mitigation**: Test error scenarios

**Adding validation**:
- **Risk**: May reject some valid data
- **Mitigation**: Test with real data samples

---

## 11. Conclusion

### 11.1 Current State

✅ **Working**:
- Daily Databento ingestion (OHLCV + OI)
- Live connector emitting events
- Inngest handlers processing events
- Statistics parsing (stat_type=9)

⚠️ **Issues**:
- Symbol mismatch across ingestion paths
- Missing error handling in live connector
- Missing validation in event handlers
- Inconsistent ON CONFLICT behavior

### 11.2 Next Steps

1. **DO NOT PROCEED** with plan implementation until:
   - Symbol mismatch is resolved
   - Error handling is added
   - Test scripts are run and reviewed

2. **Create Fix Plan**:
   - Document exact changes needed
   - Get approval for symbol choice
   - Plan rollback strategy

3. **Test Thoroughly**:
   - Run all test scripts
   - Test error scenarios
   - Test symbol transition

---

## 12. Questions for Clarification

1. **Symbol Choice**: Should ALL ZL ingestion use `ZL.n.0` (OI-ranked) or `ZL.c.0` (calendar)?
   - Current: Daily uses `.n.0`, Live uses `.c.0`
   - Recommendation: Use `.n.0` everywhere for consistency

2. **Source Tags**: Should we distinguish `databento` vs `databento_live`?
   - Current: Both exist, serve different purposes
   - Recommendation: Keep both (they're correct)

3. **Conflict Resolution**: Should live data always win, or should we preserve historical?
   - Current: Live always overwrites
   - Recommendation: Live wins for recent data (<24h), historical for older

4. **Error Handling**: What's the acceptable retry strategy?
   - Current: Infinite retries with 5s sleep
   - Recommendation: Exponential backoff with max retries

---

**END OF AUDIT REPORT**

**Status**: ⚠️ **BLOCKED** - Critical issues must be resolved before proceeding
