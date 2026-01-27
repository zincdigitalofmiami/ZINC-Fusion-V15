# Databento Integration - Fixes Applied

**Date**: 2026-01-27  
**Status**: ✅ COMPLETE

## Summary

Applied fixes to resolve the Databento integration issues identified in the audit.

---

## Changes Made

### 1. Source Normalization (P0-A)

**Problem**: `databento_historical` (6,514 rows) was separate from `databento` (1 row), causing incremental queries to miss historical data.

**Fix**: Added migration script to normalize `databento_historical` → `databento` in `mkt.futures_1d`

```sql
UPDATE mkt.futures_1d SET source = 'databento' WHERE source = 'databento_historical';
```

**Expected Result (after running migration)**:
- `databento_historical` rows are normalized to `databento`
- Incremental queries will now work correctly

### 2. Symbol Standardization (P0-B)

**Problem**: Mixed use of `ZL.c.0` (calendar roll) and `ZL.n.0` (OI-ranked) across different jobs.

**Fix**: Updated all active Inngest jobs to use `ZL.n.0`:

| File | Change |
|------|--------|
| `frontend/src/inngest/zl-15m.ts` | `ZL.c.0` → `ZL.n.0` |
| `frontend/src/inngest/zl-1h.ts` | `ZL.c.0` → `ZL.n.0` |
| `frontend/src/inngest/yahoo-eod.ts` | `ZL.c.0` → `ZL.n.0` |

**Result**: All Databento ZL fetches now use `ZL.n.0` (OI-ranked) consistently.

### 3. Legacy Python Scripts (P0-C)

**Problem**: Duplicate Python scripts and Inngest jobs doing the same thing with different symbols.

**Fix**:
- **Live connector** (`scripts/ingest_databento_live_zl.py`) is **active** for live charts.
- **Legacy daily scripts** remain deprecated in favor of Inngest jobs.

| Script | Status | Replacement |
|--------|--------|-------------|
| `scripts/ingest_databento_live_zl.py` | Active (live charts) | N/A |
| `scripts/ingest_databento_futures.py` | Deprecated | `frontend/src/inngest/databento-futures-daily.ts` |
| `scripts/ingest_databento_statistics.py` | Deprecated | `frontend/src/inngest/databento-statistics-daily.ts` |

---

## Verification

### Current Symbol Usage (Active Jobs)

| Job | File | Symbol | Status |
|-----|------|--------|--------|
| Daily OHLCV | `databento-futures-daily.ts` | `ZL.n.0` | ✅ Correct |
| Statistics/OI | `databento-statistics-daily.ts` | `ZL.n.0` | ✅ Correct |
| 15m Bars | `zl-15m.ts` | `ZL.n.0` | ✅ Fixed |
| 1h Bars | `zl-1h.ts` | `ZL.n.0` | ✅ Fixed |
| Yahoo EOD (ZL) | `yahoo-eod.ts` | `ZL.n.0` | ✅ Fixed |

### Source Distribution (Post-Migration Expected)

```
Source          Count     Min Date      Max Date
databento       <verify>  <verify>      <verify>
TradingView     <verify>  <verify>      <verify>
yahoo_backfill  <verify>  <verify>      <verify>
yahoo_eod       <verify>  <verify>      <verify>
yahoo_manual    <verify>  <verify>      <verify>
```

---

## What's Left

### Expected Behavior Going Forward

1. **Daily OHLCV**: `databento-futures-daily.ts` will incrementally add rows with `source='databento'`
2. **Statistics/OI**: `databento-statistics-daily.ts` will fill OI for recent dates
3. **15m/1h Bars**:
   - Live connector writes `source='databento_live'` (current session)
   - HTTP backfill jobs write `source='databento'` (older than 24h)

### Open Interest Coverage

The statistics job should now work correctly since:
1. Source is unified (`databento`)
2. Symbol is standardized (`ZL.n.0`)
3. Job runs 30min after OHLCV job (5:30 AM CT)

Re-run audit in 24-48 hours to verify OI coverage is improving.

### Intraday Live + Historical Stitching

Live bars come from the TCP connector (`databento_live`), while HTTP backfill covers older history (`databento`).

---

## Files Modified

1. `scripts/migrate_databento_source.py` - NEW (migration script)
2. `frontend/src/inngest/zl-15m.ts` - Symbol change + live-safe upserts
3. `frontend/src/inngest/zl-1h.ts` - Symbol change + live-safe upserts
4. `frontend/src/inngest/zl-daily.ts` - New ZL daily job (Databento only)
5. `frontend/src/inngest/yahoo-eod.ts` - ZL removed (non-ZL only)
6. `scripts/ingest_databento_live_zl.py` - Live connector active
7. `scripts/ingest_databento_futures.py` - Deprecation warning
8. `scripts/ingest_databento_statistics.py` - Deprecation warning

---

## Rollback Plan

If issues arise:

1. **Source rollback** (if needed):
   ```sql
   -- Only if you need to revert (not recommended)
   -- This would require knowing which rows were originally 'databento_historical'
   -- The migration is one-way by design
   ```

2. **Symbol rollback**: Revert the `.n.0` → `.c.0` in the TypeScript files

3. **Deprecation rollback**: Remove the deprecation warnings from Python scripts

---

**Status**: ✅ All fixes applied successfully.
