NOTE: Production is the dashboard/frontend, not the repo root.
# Schema Migration v2 — Deployment Notice

**Date:** 2026-01-22
**Status:** COMPLETE
**Authority:** Schema Governance Team

---

## Summary

All `raw.*`, `silver.*`, `gold.*`, and `bronze.*` schema references have been migrated to the v2 domain-driven architecture. This document serves as the **official reference** for all teams.

---

## Master Canonical Table

| Old Path | New Path | Schema | Notes |
|----------|----------|--------|-------|
| `raw.market_futures_1d` | `mkt.futures_1d` | mkt | PK: `(event_date, symbol)` |
| `raw.market_futures_1h` | `mkt.futures_1h` | mkt | |
| `raw.fx_spot_1d` | `mkt.fx_1d` | mkt | |
| `raw.options_futures_1d` | `mkt.options_1d` | mkt | |
| `raw.yahoo_equity_1d` | `mkt.etf_1d` | mkt | Renamed |
| `raw.fred_observations_1d` | `econ.*` (7 tables) | econ | See FRED Routing below |
| `raw.cftc_cot_1w` | `pos.cftc_1w` | pos | Dropped `_cot` |
| `raw.usda_export_sales_1w` | `supply.usda_exports_1w` | supply | Renamed |
| `raw.usda_wasde_1m` | `supply.usda_wasde_1m` | supply | |
| `raw.epa_rin_prices_1d` | `supply.epa_rin_1d` | supply | Renamed |
| `raw.weather_noaa_1d` | `alt.weather_1d` | alt | |
| `raw.news_articles_1d` | `alt.news_1d` | alt | |
| `raw.whitehouse_actions_event` | `alt.legislation_1d` | alt | Consolidated |
| `raw.federal_register_1d` | `alt.legislation_1d` | alt | Consolidated |

---

## FRED Series Routing

The old monolithic `raw.fred_observations_1d` has been split into **7 domain-specific tables**:

| Domain Table | Series Count | Purpose |
|--------------|--------------|---------|
| `econ.rates_1d` | 39 | Interest rates, yields, spreads, FX rates |
| `econ.activity_1d` | 68 | GDP, industrial production, trade, PMIs |
| `econ.commodities_1d` | 10 | Oil, gas, agricultural commodities |
| `econ.vol_indices_1d` | 5 | VIX, OVXCLS, financial stress indices |
| `econ.inflation_1d` | 5 | CPI, PCE, PPI |
| `econ.labor_1d` | 4 | Employment, claims |
| `econ.money_1d` | 5 | Money supply, Fed balance sheet |

### Routing Module

Use the routing module for all FRED operations:

```python
from src.fusion.db.fred_routing import get_fred_table, get_fred_schema_table

# Get qualified table name
table = get_fred_table("VIXCLS")  # Returns "econ.vol_indices_1d"

# Get schema and table separately
schema, table = get_fred_schema_table("DGS10")  # Returns ("econ", "rates_1d")
```

### Key Series → Table Mapping

| Series | Table | Specialist |
|--------|-------|------------|
| `VIXCLS`, `OVXCLS`, `GVZCLS` | `econ.vol_indices_1d` | Volatility |
| `DGS10`, `DGS2`, `FEDFUNDS`, `T10Y2Y` | `econ.rates_1d` | Fed |
| `DCOILWTICO`, `DCOILBRENTEU` | `econ.commodities_1d` | Energy |
| `UNRATE`, `PAYEMS`, `ICSA` | `econ.labor_1d` | — |
| `PCEPI`, `CPIAUCSL` | `econ.inflation_1d` | — |
| `WALCL`, `M2SL` | `econ.money_1d` | Fed |
| `GDP`, `INDPRO`, `CHNMAINLANDTPU` | `econ.activity_1d` | China |

---

## Column Name Changes

| Old Column | New Column | Tables Affected |
|------------|------------|-----------------|
| `as_of_date` | `event_date` | All landing tables (`mkt.*`, `econ.*`, `pos.*`, `supply.*`, `alt.*`) |

**Note:** Feature tables (`features.*`) and training tables (`training.*`) may use `trade_date` or `as_of_date` depending on semantic meaning.

---

## Schema Boundaries

### Landing Schemas (append-only raw data)
- `mkt` — Market data (futures, FX, options, ETFs)
- `econ` — Economic indicators (FRED series by domain)
- `pos` — Positioning data (CFTC COT)
- `supply` — Supply chain (USDA, EPA RIN)
- `alt` — Alternative data (news, weather, legislation)

### Derived Schemas (computed features)
- `features` — Computed features (elite indicators, news sentiment, weather aggregates)
- `training` — Training artifacts (matrix, OOF predictions, specialist signals)

### Output Schemas (model results)
- `model` — Model registry, coefficients, SHAP values
- `forecasts` — Production forecasts
- `analytics` — Dashboard metrics, risk metrics

### Governance Schemas
- `metadata` — Data source registry, specialist drivers
- `ops` — Operational logs, ingestion tracking

---

## Forbidden Schemas

**DO NOT USE** the following schema names:
- `raw` — Deprecated
- `silver` — Deprecated
- `gold` — Deprecated
- `bronze` — Deprecated
- `monitoring` — Not in v2 architecture
- `specialist` — Use `training.*` instead
- `weather` — Use `alt.weather_1d` (computed on-the-fly at training time)

---

## New Table: `features.news_scored_1d`

Created for specialist news routing with Big 11 flags:

```sql
features.news_scored_1d (
    id, raw_news_id, published_at, headline,
    sentiment_score, sentiment_confidence, sentiment_direction, zl_impact_score,
    -- Big 11 routing flags
    affects_crush, affects_china, affects_fx, affects_fed, affects_tariff,
    affects_energy, affects_biofuel, affects_palm, affects_volatility,
    affects_substitutes, affects_trump_effect,
    -- Audit
    ingested_at, model_version
)
```

Query pattern for specialist features:
```sql
SELECT DATE(published_at) AS as_of_date, AVG(sentiment_score), COUNT(*)
FROM features.news_scored_1d
WHERE affects_crush = TRUE
GROUP BY DATE(published_at)
```

---

## Files Updated

| File | Changes |
|------|---------|
| `scripts/generate_specialist_features.py` | All `raw.*` → v2 tables |
| `scripts/ingest_all_downloads.py` | FRED routing + `mkt.futures_1d` |
| `scripts/ingest_downloads_fred.py` | FRED routing |
| `scripts/run_monte_carlo.py` | `mkt.futures_1d` |
| `scripts/find_analogs.py` | `mkt.futures_1d` |
| `audit_specialists.mjs` | All v2 tables |
| `audit-db-pg.ts` | All v2 tables |
| `prisma/schema.prisma` | Added `FeaturesNewsScored1d` model |

---

## Validation Commands

```bash
# Check for any remaining raw.* references in active scripts
grep -r '"raw"\.' scripts/*.py src/ --include="*.py" | grep -v _deprecated

# Verify FRED routing module
python -c "from src.fusion.db.fred_routing import FRED_SERIES_ROUTING; print(len(FRED_SERIES_ROUTING))"

# Test database connectivity to new tables
python -c "
from src.fusion.db.connection import get_connection
conn = get_connection()
cur = conn.cursor()
cur.execute('SELECT COUNT(*) FROM mkt.futures_1d')
print(f'mkt.futures_1d: {cur.fetchone()[0]:,} rows')
"
```

---

## Contact

Questions about schema mappings? Check the routing module or consult `AGENTS.md`.

**Schema changes require explicit approval.** Do not create new tables without governance review.