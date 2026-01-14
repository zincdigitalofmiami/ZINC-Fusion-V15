# TIME-KEY ALIGNMENT: SURGICAL FIX REPORT
## Date: 2026-01-14
## Status: AUDIT COMPLETE - FIXES REQUIRED

---

## PROBLEM STATEMENT

Raw tables use `event_date` (or `event_time` for hourly).
Some scripts incorrectly query using `as_of_date`.
**Result: Scripts FAIL with "column does not exist" error.**

---

## VERIFIED COLUMN NAMES

| Table | Correct Column | Scripts Use |
|-------|---------------|-------------|
| `raw.market_futures_1d` | `event_date` | ❌ `as_of_date` |
| `raw.fred_observations_1d` | `event_date` | ❌ `as_of_date` |
| `raw.fx_spot_1d` | `event_date` | ❌ `as_of_date` |
| `raw.weather_noaa_1d` | `event_date` | ❌ `as_of_date` |
| `raw.epa_rin_prices_1d` | `event_date` | ❌ `as_of_date` |
| `raw.news_articles_1d` | `event_date` | ❌ `as_of_date` |
| `raw.cftc_cot_1w` | `event_date` | ✅ Uses `report_date` |

---

## FILES REQUIRING FIXES

### CRITICAL (Training/Features - will break model training)

#### 1. `scripts/generate_specialist_features.py`
**Lines to fix:**
- L519: `SELECT symbol, as_of_date` → `SELECT symbol, event_date as as_of_date`
- L521: `WHERE as_of_date >= %s` → `WHERE event_date >= %s`
- L522: `ORDER BY as_of_date` → `ORDER BY event_date`
- L538: `SELECT as_of_date, series_id` → `SELECT event_date as as_of_date, series_id`
- L540: `ORDER BY as_of_date` → `ORDER BY event_date`
- L569: `SELECT pair, as_of_date, rate` → `SELECT pair, event_date as as_of_date, rate`
- L664-666: Same pattern for epa_rin_prices_1d
- L684-704: Same pattern for weather_noaa_1d
- L754-762: Same pattern for news sentiment

**Fix pattern:** Use `event_date as as_of_date` in SELECT to maintain downstream compatibility.

#### 2. `scripts/train_direction_v15.py`
- L124-127: Uses `as_of_date` for raw.market_futures_1d

#### 3. `scripts/v15_core_training/train_core_with_oof.py`
- L104-107: Uses `as_of_date` for training.core_features (OK - training schema)
- But verify if it joins to raw tables

#### 4. `scripts/train_core_poc.py`
- L261-266: Uses `as_of_date` for raw tables

### HIGH (Operational - will break monitoring)

#### 5. `grafana/grafana_registry.py`
- L422-427: Config tuples specify wrong column name
```python
# FIX: Change as_of_date → event_date
("Market Futures (1D)", "raw.market_futures_1d", "event_date"),
("FRED Economic", "raw.fred_observations_1d", "event_date"),
# etc.
```

#### 6. `audit/audit_data.py`
- L21-29: Same pattern - hardcoded wrong column names

### MEDIUM (Utility scripts - may not be actively used)

#### 7. `scripts/backfill_missing_symbols.py`
- L153, L214: SELECT/INSERT with wrong column

#### 8. `scripts/sync_cloud_to_local.py`
- L43, L45: Config specifies wrong key column

#### 9. `scripts/backfill_sparse_sources.py`
- L202, L268, L329, L332: Uses wrong column

---

## FIX STRATEGY

### Option A: Fix at Query Level (RECOMMENDED)
Use SQL aliases: `SELECT event_date as as_of_date, ...`
- Preserves downstream code that uses `as_of_date` in DataFrames
- Minimal code changes
- Clear intent

### Option B: Fix at DataFrame Level
Query with `event_date`, then rename: `df.rename(columns={'event_date': 'as_of_date'})`
- More explicit
- More code changes

### Option C: Add Column Alias/View
Create views like `raw.v_market_futures_1d` with `as_of_date` alias
- Most invasive
- Not recommended

---

## RECOMMENDED FIX ORDER

1. **FIRST:** `scripts/generate_specialist_features.py` (blocks feature generation)
2. **SECOND:** `scripts/train_*.py` files (blocks training)
3. **THIRD:** `grafana/grafana_registry.py` (blocks monitoring)
4. **FOURTH:** `audit/*.py` files (blocks auditing)
5. **LAST:** Backfill scripts (utility only)

---

## APPROVAL NEEDED

**Ready to execute fixes?**

Estimated changes:
- 6 files
- ~30 line edits
- Pattern: `as_of_date` → `event_date as as_of_date` in SQL SELECT
- Pattern: `WHERE as_of_date` → `WHERE event_date`
- Pattern: `ORDER BY as_of_date` → `ORDER BY event_date`
