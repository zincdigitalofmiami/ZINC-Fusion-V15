# Idempotency Contracts

**Last Updated:** 2026-01-18

This document defines the idempotency contracts for all tables in the ZINC-FUSION-V15 system.

## Principles

1. **Every table has a natural key** - No table relies solely on auto-increment IDs for uniqueness
2. **Conflict policy is explicit** - Either DO UPDATE (updateable) or DO NOTHING (append-only)
3. **Re-ingestion is safe** - Running the same ingestion twice produces identical results

---

## Landing Tables (Append-Only Source Data)

| Table | Natural Key | Conflict Policy | Mutability |
|-------|-------------|-----------------|------------|
| `mkt.futures_1d` | (event_date, symbol) | DO UPDATE | Updateable |
| `mkt.futures_1h` | (event_date, symbol, hour) | DO UPDATE | Updateable |
| `mkt.fx_1d` | (event_date, pair) | DO UPDATE | Updateable |
| `mkt.options_1d` | (event_date, symbol, strike, expiry, option_type) | DO UPDATE | Updateable |
| `econ.rates_1d` | (event_date, series_id) | DO UPDATE | Updateable |
| `alt.news_1d` | (article_id) or (content_hash) | DO NOTHING | Append-only |
| `alt.weather_1d` | (event_date, station_id) | DO UPDATE | Updateable |
| `alt.legislation_1d` | (event_date, document_id) | DO NOTHING | Append-only |
| `pos.cftc_1w` | (report_date, contract_code, report_type) | DO UPDATE | Updateable |
| `supply.usda_wasde_1m` | (report_date, commodity, item) | DO UPDATE | Updateable |
| `supply.usda_exports_1w` | (report_date, commodity, country) | DO UPDATE | Updateable |
| `supply.epa_rin_1d` | (event_date, rin_type) | DO UPDATE | Updateable |

---

## Derived Tables (Computed from Landing)

| Table | Natural Key | Conflict Policy | Change Tracking |
|-------|-------------|-----------------|-----------------|
| `features.elite_1d` | (trade_date, symbol) | DO UPDATE | None |
| `features.options_1d` | (trade_date, symbol) | DO UPDATE | None |
| `training.matrix_1d` | (trade_date, symbol, matrix_version) | DO UPDATE | matrix_version |
| `training.oof_core_1d` | (trade_date, symbol, horizon_days, window_id) | DO UPDATE | run_hash |
| `training.oof_meta_1d` | (trade_date, symbol, horizon_days, window_id) | DO UPDATE | run_hash |
| `training.specialist_*_1d` | (as_of_date, symbol) | DO UPDATE | None |

---

## Output Tables (Model Artifacts)

| Table | Natural Key | Conflict Policy | Versioning |
|-------|-------------|-----------------|------------|
| `model.registry` | (model_name, version) | DO NOTHING | version column |
| `model.training_runs` | (run_id) | DO NOTHING | Append-only |
| `forecasts.forecast_quantiles` | (forecast_date, target_date, symbol, horizon_days) | DO UPDATE | forecast_date |
| `analytics.zl_price_15m` | (timestamp) | DO UPDATE | 15m bars |

---

## Conflict Resolution Patterns

### DO UPDATE Pattern (Updateable Tables)

```sql
INSERT INTO mkt.futures_1d (event_date, symbol, open, high, low, close, volume, ingested_at)
VALUES ($1, $2, $3, $4, $5, $6, $7, NOW())
ON CONFLICT (event_date, symbol) 
DO UPDATE SET 
    open = EXCLUDED.open, 
    high = EXCLUDED.high, 
    low = EXCLUDED.low, 
    close = EXCLUDED.close, 
    volume = EXCLUDED.volume, 
    updated_at = NOW();
```

### DO NOTHING Pattern (Append-Only Tables)

```sql
INSERT INTO alt.news_1d (article_id, event_date, title, content, source, content_hash, ingested_at)
VALUES ($1, $2, $3, $4, $5, $6, NOW())
ON CONFLICT (article_id) DO NOTHING;
```

### Versioned Pattern (Training Artifacts)

```sql
INSERT INTO training.oof_core_1d (trade_date, symbol, horizon_days, window_id, p30, p50, p70, run_hash, trained_at)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW())
ON CONFLICT (trade_date, symbol, horizon_days, window_id) 
DO UPDATE SET 
    p30 = EXCLUDED.p30, 
    p50 = EXCLUDED.p50, 
    p70 = EXCLUDED.p70, 
    run_hash = EXCLUDED.run_hash,
    trained_at = NOW();
```

---

## Validation Queries

### Check for Missing Natural Keys

```sql
-- Find tables without unique constraints
SELECT schemaname, tablename 
FROM pg_tables 
WHERE schemaname IN ('mkt', 'econ', 'alt', 'pos', 'supply', 'features', 'training')
  AND tablename NOT IN (
    SELECT tc.table_name 
    FROM information_schema.table_constraints tc 
    WHERE tc.constraint_type = 'UNIQUE'
  );
```

### Verify Idempotency

```sql
-- Count duplicates (should be 0 for all tables)
SELECT event_date, symbol, COUNT(*) as cnt
FROM mkt.futures_1d
GROUP BY event_date, symbol
HAVING COUNT(*) > 1;
```

---

## Change Control

- Adding new tables requires defining idempotency contract in this document
- Changing natural keys requires migration plan and approval
- Switching from DO NOTHING to DO UPDATE requires data audit

