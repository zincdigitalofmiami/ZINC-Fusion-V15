# TIME-KEY ALIGNMENT: SURGICAL FIX REPORT
## Date: 2026-01-14
## Status: FIXES APPLIED (CODE)

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
| `raw.cftc_cot_1w` | `event_date` | ❌ `report_date` (legacy scripts) |
| `raw.usda_export_sales_1w` | `event_date` | ❌ `report_date` (legacy scripts) |
| `raw.usda_wasde_1m` | `event_date` | ❌ `report_date` (legacy scripts) |

---

## FILES FIXED / UPDATED

### Training / Feature Generation

#### `scripts/generate_specialist_features.py`
- Fixed all raw-table queries to use `event_date` (aliasing to `as_of_date` in DataFrames where needed).
- Fixed legacy `report_date` usage for `raw.cftc_cot_1w`, `raw.usda_export_sales_1w`, `raw.usda_wasde_1m`.

#### `scripts/ingest_comprehensive.py` (utility ingestion)
- Fixed raw inserts to use `event_date` (no more `as_of_date` columns in `raw.*`).
- Removed invalid `ON CONFLICT (series_id, event_date)` inference for FRED (table has no such UNIQUE constraint).

#### `scripts/ingest_wasde_backfill.py` (legacy backfill)
- Fixed `report_date` → `event_date` for `raw.usda_wasde_1m`.

### Monitoring / Ops / Utilities

#### `scripts/sync_cloud_to_local.py`
- Fixed incremental keys: `raw.market_futures_1h` uses `event_time`; `training.*_1h` uses `as_of_time` (not `ts_event`).

#### `scripts/audit-freshness.ts`
- Fixed event vs ingest timestamp columns per table (`ingested_at` vs `created_at`, `event_time` for 1h).

#### Yahoo / Intraday helpers
- `scripts/ingest_yahoo_eod.py`: fixed to write `raw.market_futures_1d.event_date` (no `as_of_date` in raw schema).
- `scripts/ingest_yahoo_15m.py`: fixed ZL previous-close lookup to order by `event_date`.
- `scripts/fetch_zl_price.py`: fixed ZL previous-close lookup to order by `event_date`.

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

## Notes

- Backups like `scripts/generate_specialist_features.py.backup.*` may still contain legacy column names; they are not part of the active pipeline.
