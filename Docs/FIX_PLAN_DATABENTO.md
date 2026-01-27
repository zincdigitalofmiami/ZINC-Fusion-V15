# Databento Integration - Fix Plan (Awaiting Approval)

**Date**: 2026-01-27  
**Status**: ⏳ **AWAITING APPROVAL** - Do not proceed until approved

## Audit Summary

✅ **Audit Complete** - See `Docs/AUDIT_RESULTS_SUMMARY.md` for details

**Key Findings**:
1. ❌ Live connector NOT writing data (no `databento_live` source found)
2. ⚠️ Symbol mismatch: Live uses `ZL.c.0`, Daily uses `ZL.n.0`
3. ✅ Daily ingestion IS working (1 row from `databento` source)
4. ✅ No source conflicts or data quality issues
5. ✅ Current Yahoo data is fresh and valid

---

## Fix Plan Overview

### Phase 1: Fix Live Connector Activation (CRITICAL)

**Problem**: Live connector exists but is not writing data

**Investigation Steps**:
1. Check if `ingest_databento_live_zl.py` is running
2. Verify Inngest event key is configured
3. Check Inngest dashboard for `zl.bar.*` events
4. Verify event handlers are registered in `route.ts`
5. Test event flow end-to-end

**Fix Actions** (if connector not running):
- Ensure connector is deployed/running
- Verify environment variables (`DATABENTO_API_KEY`, `INNGEST_EVENT_KEY`)
- Add monitoring/logging
- Test manually

**Fix Actions** (if events not reaching Inngest):
- Verify event URL is correct
- Check network connectivity
- Add retry logic
- Add error logging

**Fix Actions** (if handlers not processing):
- Verify handlers are registered
- Check Inngest function sync
- Test handlers manually
- Add error handling

### Phase 2: Fix Symbol Mismatch (HIGH PRIORITY)

**Problem**: Different ingestion paths use different symbols

**Current State**:
- Daily OHLCV: `ZL.n.0` ✅
- Daily Statistics: `ZL.n.0` ✅
- Live Connector: `ZL.c.0` ❌
- Historical 15m: `ZL.c.0` ❌
- Historical 1h: `ZL.c.0` ❌
- Yahoo EOD: `ZL.c.0` ❌

**Proposed Fix**: Change ALL to `ZL.n.0` (OI-ranked)

**Files to Modify**:
1. `scripts/ingest_databento_live_zl.py`
   - Line 32: `SYMBOL = "ZL.n.0"`

2. `frontend/src/inngest/zl-15m.ts`
   - Line 47: `symbols: "ZL.n.0"`

3. `frontend/src/inngest/zl-1h.ts`
   - Line 47: `symbols: "ZL.n.0"`

4. `frontend/src/inngest/yahoo-eod.ts`
   - Line 145: `symbols: "ZL.n.0"`

**Testing Required**:
- Run parallel collection (both symbols) for 7 days
- Compare prices - should be <0.1% difference
- Verify no data gaps after switch
- Monitor for roll date issues

**Risk**: Medium - Price discontinuities during transition
**Mitigation**: 
- Run parallel collection first
- Switch only after validation
- Keep old symbol as fallback

### Phase 3: Add Error Handling (HIGH PRIORITY)

**Problem**: Live connector has no retry limits or error handling

**Current Code** (`ingest_databento_live_zl.py` lines 198-200):
```python
except Exception as exc:
    print(f"[databento-live] error: {exc}")
    time.sleep(5)
```

**Proposed Fix**:
```python
import logging

logger = logging.getLogger(__name__)
retry_count = 0
max_retries = 10

while True:
    try:
        # ... existing code ...
        retry_count = 0  # Reset on success
    except KeyboardInterrupt:
        logger.info("Shutting down gracefully...")
        break
    except Exception as exc:
        retry_count += 1
        wait_time = min(5 * (2 ** retry_count), 300)  # Exponential backoff, max 5min
        logger.error(f"Error (attempt {retry_count}/{max_retries}): {exc}")
        
        if retry_count >= max_retries:
            logger.critical(f"Max retries reached. Shutting down.")
            break
        
        time.sleep(wait_time)
```

**Files to Modify**:
- `scripts/ingest_databento_live_zl.py`

**Testing Required**:
- Simulate network failures
- Verify exponential backoff works
- Verify max retries enforced
- Test graceful shutdown

### Phase 4: Add Data Validation (MEDIUM PRIORITY)

**Problem**: Event handlers don't validate payloads

**Current Code** (`frontend/src/inngest/zl-live.ts`):
- No validation before database writes

**Proposed Fix**:
```typescript
// Add validation function
function validateBar15m(bar: ZlBar15mEvent): void {
  if (!bar.timestamp) {
    throw new Error("Missing timestamp");
  }
  if (typeof bar.close !== "number" || bar.close <= 0) {
    throw new Error(`Invalid close price: ${bar.close}`);
  }
  if (typeof bar.open !== "number" || bar.open <= 0) {
    throw new Error(`Invalid open price: ${bar.open}`);
  }
  if (bar.high < bar.low) {
    throw new Error(`Invalid OHLC: high < low`);
  }
  // Validate timestamp is recent (not too old, not future)
  const ts = new Date(bar.timestamp);
  const now = new Date();
  const ageMs = now.getTime() - ts.getTime();
  if (ageMs > 24 * 60 * 60 * 1000) {
    throw new Error(`Timestamp too old: ${ageMs}ms`);
  }
  if (ageMs < -60 * 1000) {
    throw new Error(`Timestamp in future: ${ageMs}ms`);
  }
}

// Use in handlers
export const zlLive15m = inngest.createFunction(
  { id: "zl-live-15m", name: "ZL Live 15m Bars" },
  { event: "zl.bar.15m" },
  async ({ event }) => {
    const bar = event.data as ZlBar15mEvent;
    validateBar15m(bar);  // Validate before processing
    
    // ... rest of handler ...
  }
);
```

**Files to Modify**:
- `frontend/src/inngest/zl-live.ts`

**Testing Required**:
- Test with invalid data
- Test with missing fields
- Test with out-of-range timestamps
- Verify errors are logged

### Phase 5: Improve ON CONFLICT Logic (MEDIUM PRIORITY)

**Problem**: Always overwrites, even when it shouldn't

**Current Code** (`frontend/src/inngest/zl-live.ts`):
```typescript
ON CONFLICT (timestamp) DO UPDATE SET
  open = EXCLUDED.open,  // Always overwrites
  ...
```

**Proposed Fix**:
```typescript
ON CONFLICT (timestamp) DO UPDATE SET
  open = CASE 
    WHEN EXCLUDED.source = 'databento_live' AND (mkt.source IS NULL OR mkt.source = 'databento_live' OR EXTRACT(EPOCH FROM (NOW() - mkt.timestamp)) < 86400) 
    THEN EXCLUDED.open
    ELSE mkt.open
  END,
  ...
```

**Rationale**: 
- Live data wins for recent data (<24h)
- Historical data preserved for older data
- Prevents overwriting historical with stale live data

**Files to Modify**:
- `frontend/src/inngest/zl-live.ts`

**Testing Required**:
- Test conflict scenarios
- Verify source-aware updates
- Test timestamp-based logic

---

## Implementation Order

### Step 1: Investigation (DO FIRST)
1. ✅ Run audit queries
2. ⏳ Check live connector status
3. ⏳ Verify Inngest event flow
4. ⏳ Test event handlers

### Step 2: Fix Live Connector (BLOCKING)
1. ⏳ Ensure connector is running
2. ⏳ Fix any configuration issues
3. ⏳ Add monitoring/logging
4. ⏳ Verify data starts flowing

### Step 3: Fix Symbol Mismatch (HIGH)
1. ⏳ Get approval for symbol choice
2. ⏳ Run parallel collection test
3. ⏳ Change all to `ZL.n.0`
4. ⏳ Monitor for issues

### Step 4: Add Error Handling (HIGH)
1. ⏳ Add retry logic to live connector
2. ⏳ Add logging
3. ⏳ Test error scenarios

### Step 5: Add Validation (MEDIUM)
1. ⏳ Add validation functions
2. ⏳ Update event handlers
3. ⏳ Test with invalid data

### Step 6: Improve Conflict Logic (MEDIUM)
1. ⏳ Update ON CONFLICT clauses
2. ⏳ Test conflict scenarios
3. ⏳ Verify source-aware updates

---

## Testing Plan

### Pre-Fix Testing
- ✅ Audit current state
- ⏳ Verify live connector status
- ⏳ Test event flow manually

### Post-Fix Testing
- ⏳ Verify live connector writes data
- ⏳ Verify symbol consistency
- ⏳ Test error scenarios
- ⏳ Test validation
- ⏳ Monitor production for 24 hours

### Validation Queries
```sql
-- Verify live data is flowing
SELECT source, COUNT(*), MAX(timestamp)
FROM analytics.zl_price_15m
WHERE timestamp >= NOW() - INTERVAL '1 hour'
GROUP BY source;

-- Verify symbol consistency (check prices match)
SELECT 
    DATE_TRUNC('day', timestamp) as day,
    AVG(close) as avg_close,
    source
FROM analytics.zl_price_15m
WHERE timestamp >= NOW() - INTERVAL '7 days'
GROUP BY day, source
ORDER BY day DESC;
```

---

## Risk Assessment

### High Risk Changes
1. **Symbol Change**: Could cause price discontinuities
   - **Mitigation**: Parallel collection, gradual switch
   
2. **Live Connector Activation**: Could cause conflicts
   - **Mitigation**: Source-aware conflict resolution

### Medium Risk Changes
1. **Error Handling**: Could change behavior
   - **Mitigation**: Test thoroughly, monitor closely

2. **Validation**: Could reject valid data
   - **Mitigation**: Test with real data samples

### Low Risk Changes
1. **ON CONFLICT Logic**: Additive only
   - **Mitigation**: Test conflict scenarios

---

## Approval Checklist

Before proceeding with fixes, confirm:

- [ ] Audit results reviewed and understood
- [ ] Live connector status verified
- [ ] Symbol choice approved (`ZL.n.0` everywhere)
- [ ] Error handling strategy approved
- [ ] Validation strategy approved
- [ ] Testing plan approved
- [ ] Rollback plan understood

---

## Rollback Plan

If issues occur:

1. **Symbol Change Rollback**:
   - Revert code changes
   - Restart with old symbol
   - No data loss (just switch symbol)

2. **Live Connector Rollback**:
   - Stop connector
   - Disable event handlers (comment out)
   - Yahoo ingestion continues

3. **Error Handling Rollback**:
   - Revert to simple exception handler
   - No data impact

---

## Questions for Approval

1. **Symbol Choice**: Confirm all ZL ingestion should use `ZL.n.0`?
   - ✅ Recommended: Yes, use `ZL.n.0` everywhere

2. **Error Handling**: Accept exponential backoff with max 10 retries?
   - ✅ Recommended: Yes

3. **Validation**: Accept proposed validation rules?
   - ✅ Recommended: Yes

4. **Conflict Resolution**: Accept source-aware conflict resolution?
   - ✅ Recommended: Yes

5. **Testing**: Run parallel collection before symbol switch?
   - ✅ Recommended: Yes, 7 days minimum

---

**Status**: ⏳ **AWAITING APPROVAL**

**Next Step**: Review this plan and approve fixes before proceeding.
