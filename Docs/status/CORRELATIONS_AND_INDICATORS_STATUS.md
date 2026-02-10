# Correlations and Elite Indicators - Status

**Date**: January 31, 2026

---

## ✅ What's Already Done

### Elite Indicators - 100% Coverage ✅ (consolidated into mkt.futures_1d)
- **Table**: `mkt.futures_1d` (formerly `features.elite_1d`, now consolidated)
- **Rows**: 444,780+ pre-calculated indicators
- **Coverage**: 100% for all major symbols (ZL, ZS, VX, ES, NQ, FX pairs, etc.)
- **Indicators**: Hurst, Connors RSI, Fisher Transform, McGinley, TTM Squeeze, Schaff, RVI, Elder Force, KAMA, HMA, ALMA, RSI

**Status**: ✅ Consolidated into mkt.futures_1d — single table for OHLCV + indicators

---

## 🔧 What Was Just Added

### ZL Correlation Columns ✅
Added to `mkt.futures_1d`:
- `zl_corr_30d` - 30-day rolling correlation with ZL
- `zl_corr_60d` - 60-day rolling correlation  
- `zl_corr_90d` - 90-day rolling correlation

**Critical for**: FX specialist (currency-commodity linkages), Energy specialist (oil-soy correlation)

### Calculation Script Created ✅
- **File**: `scripts/calculate_zl_correlations.py`
- **Purpose**: Backfill historical correlations
- **Status**: Ready to run (needs DATABASE_URL connection string fix)

---

## 🎯 Architecture: Calculate on Insert

### Current State
1. ✅ **Elite indicators**: Consolidated into `mkt.futures_1d` (100% coverage)
2. 🔧 **ZL correlations**: Columns added, backfill script ready

### Desired State (Auto-calculation on Insert)
When new futures data lands → automatically calculate:
1. Elite indicators → `mkt.futures_1d` (indicator columns)
2. ZL correlations → `mkt.futures_1d.zl_corr_*`

### Implementation Options

**Option 1**: Database trigger (best performance)
```sql
CREATE OR REPLACE FUNCTION calculate_zl_correlation_trigger()
RETURNS TRIGGER AS $$
-- Calculate correlations when new row inserted
$$ LANGUAGE plpgsql;

CREATE TRIGGER futures_insert_calc_corr
AFTER INSERT ON mkt.futures_1d
FOR EACH ROW EXECUTE FUNCTION calculate_zl_correlation_trigger();
```

**Option 2**: Application-side (current approach)
- Inngest jobs calculate and update indicator columns in `mkt.futures_1d` after futures insert
- Works but adds latency

**Option 3**: Batch calculation (scheduled)
- Daily job recalculates last 90 days of correlations
- Simple but not real-time

---

## 📊 Current Coverage Summary

| Symbol Type | Elite Indicators | ZL Correlations | Status |
|-------------|------------------|-----------------|--------|
| ZL (target) | ✅ 100% | N/A (self) | ✅ Complete |
| FX Futures (6E, 6J, etc.) | ✅ 100% | 🔧 Ready (needs backfill) | ⚠️ Partial |
| Energy (CL, HO, RB, NG) | ✅ 100% | 🔧 Ready | ⚠️ Partial |
| Grains (ZS, ZC, ZW, ZM) | ✅ 100% | 🔧 Ready | ⚠️ Partial |
| Metals (HG, GC, SI) | ✅ 100% | 🔧 Ready | ⚠️ Partial |
| Indices (ES, NQ, VX) | ✅ 100% | 🔧 Ready | ⚠️ Partial |

---

## 🚀 Next Steps

1. **Fix DATABASE_URL connection** in Python scripts (psycopg2 SSL issue)
2. **Run correlation backfill** for all 104 symbols (~1-2 hours)
3. **Create auto-calculation trigger** for new data inserts
4. **Verify** correlations available for training

---

**Status**: Infrastructure ready, elite indicators 100% done, correlations ready to calculate
