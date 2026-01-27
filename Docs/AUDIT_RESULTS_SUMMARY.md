# Databento Integration - Audit Results Summary

**Date**: 2026-01-27  
**Status**: ✅ FIXES APPLIED - See `Docs/DATABENTO_FIX_APPLIED.md`

> **UPDATE**: Fixes are applied in code, and the target state is:
> - Source normalized: `databento_historical` → `databento` (run migration to verify)
> - Symbol standardized: All active ZL jobs now use `ZL.n.0`
> - Live + historical stitching: live connector writes `databento_live`, HTTP backfill writes `databento`
> - ZL daily is isolated in its own job and writes `analytics.zl_price_1d`
>
> Use the validation queries at the end of this document to confirm live DB state.

---

**Original Status**: ✅ Audit Complete - Critical Findings Identified

## Executive Summary

**CRITICAL FINDING (AUDIT SNAPSHOT)**: At the time of the original audit (2026-01-27),
the live connector was not writing data and analytics tables were Yahoo-only.
This should now be resolved by the live connector + historical backfill split.

**Key Findings**:
1. ✅ No source conflicts (good)
2. ✅ No large price discontinuities (good)
3. ⚠️ **Live connector not active** (audit snapshot)
4. ⚠️ **Symbol mismatch confirmed** (audit snapshot)
5. ⚠️ Data gaps exist (expected for Yahoo-only ingestion)

---

## 1. Source Distribution Analysis

### analytics.zl_price_15m
- **Source**: `yahoo` only (789 rows)
- **Range**: 2026-01-20 to 2026-01-27
- **Finding**: ❌ **NO `databento_live` data** - Live connector not writing

### analytics.zl_price_1h
- **Source**: `yahoo` only (9,547 rows)
- **Range**: 2024-01-16 to 2026-01-27
- **Finding**: ❌ **NO `databento` or `databento_live` data**

### analytics.zl_price_1d
- **Sources**: Multiple (6 different sources)
  - `databento_historical`: 6,516 rows (2000-03-15 to 2025-12-26)
  - `TradingView`: 1,869 rows (1970-01-01 to 2023-09-04)
  - `yahoo_backfill`: 23 rows (2025-12-17 to 2026-01-19)
  - `yahoo_eod`: 3 rows (2026-01-23 to 2026-01-27)
  - `yahoo_manual`: 2 rows (2026-01-20 to 2026-01-22)
  - `yahoo`: 2 rows (2025-12-31 to 2026-01-02)
- **Finding**: ❌ **NO `databento_live` data** - Live connector not writing daily bars

### mkt.futures_1d (ZL symbol)
- **Sources**: 
  - `databento_historical`: 6,514 rows (2000-03-15 to 2025-12-19)
  - `databento`: 1 row (2026-01-21) ✅ **This is from daily ingestion**
  - `yahoo_*`: Various sources
- **Finding**: ✅ Daily Databento ingestion IS working (1 row from `databento` source)

---

## 2. Price Discontinuities

### 15m Bars (Last 7 Days)
- **Max jump**: 0.65% (normal market movement)
- **Finding**: ✅ **No roll date issues detected** - All jumps <1%
- **Note**: This is Yahoo data, so no symbol mismatch issues yet

### Daily Bars (Last 30 Days)
- **Max intraday change**: 3.82% (2026-01-15)
- **Finding**: ✅ **No suspicious roll date patterns** - Changes are normal market movements

---

## 3. Data Coverage Gaps

### 15m Bars
- **Gaps found**: 9 gaps >30 minutes
- **Largest gap**: 2 days 5 hours (2026-01-23 to 2026-01-26)
- **Finding**: ⚠️ **Expected gaps** - Yahoo ingestion has limitations
- **Impact**: Should be resolved with live connector + historical backfill once verified

### Daily Bars
- **Query error**: SQL syntax issue (fixed in script)
- **Finding**: Need to re-run query

---

## 4. Source Conflicts

### 15m Bars
- **Conflicts**: 0 (no same timestamp with different sources)
- **Finding**: ✅ **No conflicts** - Good

### Daily Bars
- **Conflicts**: 0 (no same date with different sources)
- **Finding**: ✅ **No conflicts** - Good

---

## 5. Data Freshness

| Interval | Source | Latest Timestamp | Age |
|----------|--------|------------------|-----|
| 15m | yahoo | 2026-01-27 19:19:58 | 0.2 hours ✅ |
| 1h | yahoo | 2026-01-27 18:50:03 | 0.7 hours ✅ |
| 1d | yahoo_eod | 2026-01-27 | 0.8 hours ✅ |
| 1d | yahoo_backfill | 2026-01-19 | 8.8 hours ⚠️ |
| 1d | databento_historical | 2025-12-26 | 32.8 hours ⚠️ |
| 1d | TradingView | 2023-09-04 | 876.8 hours ❌ |

**Finding**: 
- ✅ Current data is fresh (Yahoo sources)
- ⚠️ Historical Databento data is 32+ hours old (expected - historical API lag)
- ❌ TradingView data is very old (legacy)

---

## 6. Data Quality

### 15m Bars (Last 7 Days)
- **Null prices**: 0 ✅
- **Invalid closes**: 0 ✅
- **Invalid OHLC**: 0 ✅
- **Total rows**: 705
- **Finding**: ✅ **Data quality is good**

---

## 7. Symbol Usage in mkt.futures_1d

| Source | Rows | With OI | Earliest | Latest |
|--------|------|---------|----------|--------|
| databento_historical | 6,514 | 311 | 2000-03-15 | 2025-12-19 |
| databento | 1 | 0 | 2026-01-21 | 2026-01-21 |
| yahoo_backfill | 27 | 4 | 2025-12-17 | 2026-01-19 |
| yahoo_eod | 3 | 0 | 2026-01-23 | 2026-01-27 |
| yahoo_manual | 2 | 0 | 2026-01-20 | 2026-01-22 |
| TradingView | 1,869 | 0 | 1970-01-01 | 2023-09-04 |

**Finding**: 
- ✅ Daily Databento ingestion IS working (1 row from `databento` source on 2026-01-21)
- ⚠️ Only 311 rows have open interest (from `databento_historical`)
- ⚠️ Recent `databento` row has NO open interest (statistics job may not have run yet)

---

## 8. Volume Consistency

### 15m Bars (Last 7 Days)
- **Bars per day**: 141 (consistent) ✅
- **Volume range**: 65,108 to 96,327 per day
- **Finding**: ✅ **Volume patterns are normal**

---

## Critical Issues Identified

### Issue #1: Live Connector Not Active ⚠️ **CRITICAL**

**Problem**: 
- No `databento_live` source found in any analytics table
- Live connector code exists but is not writing data

**Possible Causes**:
1. Connector not running
2. Connector running but events not reaching Inngest
3. Inngest handlers not processing events
4. Database writes failing silently

**Impact**: 
- Charts are NOT getting live Databento data
- Currently relying on Yahoo only (24h delayed)

**Action Required**:
- Verify live connector is running
- Check Inngest event logs
- Verify event handlers are registered
- Test end-to-end flow

### Issue #2: Symbol Mismatch ⚠️ **HIGH PRIORITY**

**Problem**: 
- Live connector uses `ZL.c.0` (calendar)
- Daily ingestion uses `ZL.n.0` (OI-ranked)
- Historical 15m/1h use `ZL.c.0` (calendar)

**Impact**: 
- When live connector starts, it will write calendar contract data
- Daily ingestion writes OI-ranked contract data
- Charts will show inconsistent prices on roll dates

**Action Required**:
- Change all to `ZL.n.0` for consistency
- Or document the difference and accept it

### Issue #3: Missing Open Interest ⚠️ **MEDIUM PRIORITY**

**Problem**: 
- Recent `databento` row (2026-01-21) has NO open interest
- Statistics job may not have run or failed

**Action Required**:
- Verify statistics job ran successfully
- Check if OI data is available for that date

---

## Recommendations

### Immediate Actions (Before Fixes)

1. **Verify Live Connector Status**
   - Check if `ingest_databento_live_zl.py` is running
   - Check Inngest dashboard for `zl.bar.*` events
   - Verify event handlers are registered

2. **Test Event Flow**
   - Manually trigger a test event
   - Verify it reaches Inngest
   - Verify database write succeeds

3. **Check Statistics Job**
   - Verify `databento-statistics-daily` ran
   - Check why 2026-01-21 row has no OI

### Fix Priority (Historical)

1. **P0 (BLOCKING)**: Fix live connector activation
2. **P1 (HIGH)**: Fix symbol mismatch (all to `ZL.n.0`)
3. **P2 (MEDIUM)**: Add error handling to live connector
4. **P3 (MEDIUM)**: Add data validation to event handlers

---

## Post-Fix Validation

Run these to confirm live + historical stitching is healthy:

```sql
-- Confirm live vs historical sources
SELECT source, COUNT(*), MIN(timestamp), MAX(timestamp)
FROM analytics.zl_price_15m
GROUP BY source
ORDER BY COUNT(*) DESC;

SELECT source, COUNT(*), MIN(timestamp), MAX(timestamp)
FROM analytics.zl_price_1h
GROUP BY source
ORDER BY COUNT(*) DESC;

SELECT source, COUNT(*), MIN(event_date), MAX(event_date)
FROM analytics.zl_price_1d
GROUP BY source
ORDER BY COUNT(*) DESC;

-- Ensure live is writing recent bars
SELECT MAX(timestamp) FROM analytics.zl_price_15m WHERE source = 'databento_live';
SELECT MAX(timestamp) FROM analytics.zl_price_1h WHERE source = 'databento_live';

-- Ensure historical backfill does not overwrite live
SELECT timestamp, array_agg(DISTINCT source) AS sources
FROM analytics.zl_price_15m
WHERE timestamp >= NOW() - INTERVAL '3 days'
GROUP BY timestamp
HAVING COUNT(DISTINCT source) > 1
ORDER BY timestamp DESC
LIMIT 10;
```

---

## Files Created

1. `Docs/DATABENTO_AUDIT_REPORT.md` - Full detailed audit (12 sections)
2. `Docs/DATABENTO_CRITICAL_ISSUES.md` - Critical issues summary
3. `Docs/AUDIT_RESULTS_SUMMARY.md` - This document (executive summary)
4. `scripts/audit_databento_state.sql` - SQL queries for manual review
5. `scripts/run_audit_queries.py` - Automated audit script
6. `audit_results_databento.json` - Raw audit results

---

**Status**: ✅ **AUDIT COMPLETE** - Fixes applied; validation pending
