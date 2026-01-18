# ZINC-FUSION-V15 Schema Contract v2

Status: ACTIVE (migrated 2026-01-18)
Goal: Institutional-grade schema architecture with clear data lineage.

## Canonical Schemas (13 total)

### Landing Schemas (append-only source data)
- **mkt** - Market prices (futures, options, FX)
- **econ** - Economic indicators (FRED series by domain)
- **alt** - Alternative data (news, weather, legislation)
- **pos** - Positioning data (CFTC, commitments)
- **supply** - Supply/demand (USDA, EPA, trade flows)

### Derived Schemas (computed from landing)
- **features** - Business-ready features
- **training** - Model training matrices and OOF

### Output Schemas (model artifacts)
- **model** - Model registry and training runs
- **forecasts** - Prediction outputs
- **analytics** - Dashboard-facing aggregates

### Governance Schemas (operations)
- **metadata** - Instrument definitions, symbol mappings
- **ops** - Job health, ingestion registry, alerts

### Deprecated Schemas (read-only)
- **archive** - Legacy data (no new writes)

## BANNED Schemas
These schemas are deprecated and must not be used in new code:
- raw, gold, silver, bronze, monitoring, specialist, weather

Any reference to banned schemas should fail with hard error.

## Schema Responsibilities

### mkt (market prices)
Purpose: time-series market data (futures, options, FX spot).
Known tables:
- mkt.futures_1d
- mkt.futures_1h
- mkt.options_1d
- mkt.fx_1d

### econ (macro + policy)
Purpose: FRED series in domain-specific long tables.
Known tables:
- econ.rates_1d
- econ.inflation_1d
- econ.labor_1d
- econ.activity_1d
- econ.vol_indices_1d
- econ.commodities_1d
- econ.fx_1d
- econ.money_1d

### alt (alternative data)
Purpose: News, weather, legislation, and other alternative sources.
Known tables:
- alt.news_1d
- alt.weather_1d
- alt.legislation_1d

### pos (positioning)
Purpose: CFTC commitments of traders and positioning data.
Known tables:
- pos.cftc_1w

### supply (supply/demand)
Purpose: USDA, EPA, and trade flow data.
Known tables:
- supply.usda_wasde_1m
- supply.usda_exports_1w
- supply.epa_rin_1d

### features (denormalized features)
Purpose: business-ready features built from mkt + econ + weather.
Known tables:
- features.elite_1d
- features.options_1d
- features.weather_1d

### training (model inputs + OOF)
Purpose: training-only matrices, specialist features, and OOF outputs.
Known tables:
- training.matrix_1d
- training.oof_core_1d
- training.specialist_features
- training.specialist_*_1d

Note: specialist_*_1h tables live in analytics (dashboard only).

### model (registry)
Purpose: model registry, training runs, and metrics.
Known tables:
- model.model_registry
- model.training_runs
- model.oof_predictions
- model.forecast_metrics

### forecasts (predictions)
Purpose: Prediction outputs and quantile forecasts.
Known tables:
- forecasts.forecast_quantiles
- forecasts.ensemble_forecasts

### analytics (presentation)
Purpose: dashboard-facing tables and real-time displays.
Examples:
- analytics.latest_prices
- analytics.intraday_prices
- analytics.dashboard_metrics
- analytics.risk_metrics

### metadata (governance)
Purpose: canonical instruments and symbol mappings.
Examples:
- metadata.instrument
- metadata.symbol_mapping

### ops (infrastructure)
Purpose: job health, ingestion registry, system alerts.
Examples:
- ops.data_source_registry
- ops.job_run_status

## Cross-Schema Rules
- No new writes to legacy schemas (raw, gold, silver). Deprecate and migrate.
- Training uses daily data only. Intraday data is dashboard-only in analytics.
- FRED routing is centralized in `src/fusion/ingestion/router.py`.
- Feature/label horizons remain 5/21/63/126 (integers only).
- OOF quantiles use p30/p50/p70 (no prefix).
- Risk/MC quantiles remain p10/p30/p50/p70/p90 (all five required).

---

## Time Key Join Contract

Landing schemas and derived schemas use different time column names to reflect their semantic meaning:

| Schema Category | Time Column | Semantic Meaning |
|----------------|-------------|------------------|
| Landing (mkt/econ/alt/pos/supply) | `event_date` | When the event occurred in the real world |
| Derived (features/training) | `trade_date` | Business/trading day aligned |
| Forecasts | `forecast_date` + `target_date` | When forecast made + prediction target |

### Join Pattern

```sql
-- Joining landing to derived
FROM mkt.futures_1d m
JOIN features.elite_1d f ON m.event_date = f.trade_date
WHERE m.symbol = 'ZL';

-- Joining multiple landing tables
FROM mkt.futures_1d m
JOIN econ.rates_1d e ON m.event_date = e.event_date
WHERE e.series_id = 'DGS10';

-- Forecasts with target alignment
FROM forecasts.forecast_quantiles f
WHERE f.forecast_date = '2026-01-18'
  AND f.target_date = '2026-02-18';  -- 21-day horizon
```

### Future Enhancement
Consider `metadata.trading_calendar` table for business day mapping (holidays, half-days).

---

## Suffix Semantics

### Grain Suffixes (Required)

| Suffix | Meaning | Example |
|--------|---------|---------|
| `_1h` | Hourly bars | `mkt.futures_1h` |
| `_1d` | Daily bars | `mkt.futures_1d` |
| `_1w` | Weekly snapshot | `pos.cftc_1w` |
| `_1m` | Monthly snapshot | `supply.usda_wasde_1m` |
| `_event` | Event-driven (no fixed frequency) | `alt.news_event` |
| `_static` | Reference/lookup data | `metadata.instrument_static` |

### BANNED Patterns

| Pattern | Example | Why Banned | Use Instead |
|---------|---------|------------|-------------|
| Horizon in table name | `oof_core_5d_1d` | Creates table proliferation | `horizon_days` column |
| Symbol in table name | `oof_core_zl_1d` | Creates table proliferation | `symbol` column |
| No grain suffix | `market_futures` | Ambiguous granularity | `mkt.futures_1d` |

---

## Quantile Naming Contract

### Standard Quantile Columns

| Context | Pattern | Example |
|---------|---------|---------|
| OOF tables | `p30`, `p50`, `p70` (no prefix) | `training.oof_core_1d.p50` |
| Forecast output | `p10`, `p50`, `p90` or `p30`, `p50`, `p70` | `forecasts.forecast_quantiles.p50` |
| Multi-family rows | Prefix + quantile | `core_p30`, `meta_p30` |
| Risk/MC tables | All five: `p10`, `p30`, `p50`, `p70`, `p90` | `forecasts.mc_simulation.p10` |

### BANNED Patterns

| Pattern | Example | Why Banned |
|---------|---------|------------|
| camelCase | `coreP30`, `predP50` | Inconsistent with snake_case convention |
| pred_ prefix | `pred_p30`, `pred_p50` | Redundant - context is prediction |
| q prefix | `q10`, `q50` | Use `p` for percentile consistently |

---

## Time Column Semantics (as_of_date Audit)

### Approved Time Column Names

| Column | Type | Semantic Meaning | Use Case |
|--------|------|------------------|----------|
| `event_date` | DATE | When event occurred in real world | Landing tables |
| `trade_date` | DATE | Business/trading day aligned | Derived tables |
| `forecast_date` | DATE | When forecast was made | Forecast outputs |
| `target_date` | DATE | Prediction target date | Forecast outputs |
| `report_date` | DATE | Official report release date | pos.cftc_1w, supply.usda_wasde_1m |
| `as_of_date` | DATE | Snapshot effective time | Specialist features, analytics |
| `created_at` | TIMESTAMPTZ | Row insertion time | All tables (audit) |
| `ingested_at` | TIMESTAMPTZ | Data ingestion time | Landing tables |
| `trained_at` | TIMESTAMPTZ | Model training time | OOF tables |

### as_of_date Usage Classification

| Usage Type | Correct? | Example Table |
|------------|----------|---------------|
| Snapshot effective time | ✅ | `training.specialist_*_1d.as_of_date` |
| Feature computation date | ✅ | `features.trump_effect_1d.as_of_date` |
| Event occurrence date | ❌ → use `event_date` | Landing tables |
| Record creation time | ❌ → use `created_at` | Audit columns |

---

## Idempotency Contracts

### Landing Tables

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

### Derived Tables

| Table | Natural Key | Conflict Policy | Change Tracking |
|-------|-------------|-----------------|-----------------|
| `features.elite_1d` | (trade_date, symbol) | DO UPDATE | None |
| `features.options_1d` | (trade_date, symbol) | DO UPDATE | None |
| `training.matrix_1d` | (trade_date, symbol, matrix_version) | DO UPDATE | matrix_version |
| `training.oof_core_1d` | (trade_date, symbol, horizon_days, window_id) | DO UPDATE | run_hash |
| `training.oof_*_1d` | (trade_date, symbol, horizon_days, window_id) | DO UPDATE | run_hash |

### Conflict Resolution Patterns

```sql
-- DO UPDATE pattern (updateable tables)
INSERT INTO mkt.futures_1d (event_date, symbol, open, high, low, close, volume)
VALUES ($1, $2, $3, $4, $5, $6, $7)
ON CONFLICT (event_date, symbol)
DO UPDATE SET open = EXCLUDED.open, high = EXCLUDED.high,
              low = EXCLUDED.low, close = EXCLUDED.close,
              volume = EXCLUDED.volume, updated_at = NOW();

-- DO NOTHING pattern (append-only tables)
INSERT INTO alt.news_1d (article_id, event_date, title, content, source)
VALUES ($1, $2, $3, $4, $5)
ON CONFLICT (article_id) DO NOTHING;
```

---

## Schema Count Contract

### Active Schemas (12)

| Category | Schemas | Count |
|----------|---------|-------|
| Landing | mkt, econ, alt, pos, supply | 5 |
| Derived | features, training | 2 |
| Output | model, forecasts, analytics | 3 |
| Governance | metadata, ops | 2 |
| **Total Active** | | **12** |

### Deprecated Schemas (1)

| Schema | Status | Contents |
|--------|--------|----------|
| archive | Read-only | public_intraday_prices, public_latest_prices |

### Total: 12 active + 1 deprecated = 13 schemas

---

## Change Control
- Schema creation, renames, or drops require explicit approval.
- Any contract change must update docs + code + tests together.
