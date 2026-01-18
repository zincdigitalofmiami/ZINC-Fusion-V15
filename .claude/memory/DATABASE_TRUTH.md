# DATABASE TRUTH

**Last Updated:** 2026-01-18 (Institutional Schema Migration)

## THERE IS ONLY ONE DATABASE

**Prisma Postgres** - that's it. Nothing else.

- Connection: `DATABASE_URL` in `.env`
- Schema: `prisma/schema.prisma`

## THERE IS NO

- Local database
- DuckDB
- MotherDuck
- Second database

## DEPLOYMENT

- Frontend: Vercel (Next.js + Inngest)
- Database: Prisma Postgres (cloud-hosted)

## SCHEMA TAXONOMY (13 Schemas)

**Landing (append-only source data):**
- `mkt` - Market prices (futures, options, FX)
- `econ` - Economic indicators (FRED series by domain)
- `alt` - Alternative data (news, weather, legislation)
- `pos` - Positioning data (CFTC)
- `supply` - Supply/demand (USDA, EPA, trade flows)

**Derived (computed from landing):**
- `features` - Business-ready features (elite_1d, options_1d, weather_1d)
- `training` - Training matrices and OOF outputs

**Output (model artifacts):**
- `model` - Model registry and training runs
- `forecasts` - Prediction outputs
- `analytics` - Dashboard-facing aggregates

**Governance:**
- `metadata` - Instrument definitions, symbol mappings
- `ops` - Job health, ingestion registry

**Deprecated (read-only):**
- `archive` - Legacy data (no new writes)

## BANNED SCHEMAS

These schemas are DEPRECATED and must not be used:
- `raw`, `gold`, `silver`, `bronze`, `monitoring`, `specialist`, `weather`

Any reference to banned schemas in new code should fail with hard error.

## TIME KEY SEMANTICS

- Landing schemas: `event_date` (when event occurred)
- Derived schemas: `trade_date` (trading day aligned)
- Forecasts: `forecast_date` (when forecast made) + `target_date` (prediction target)

## BEFORE EDITING ANY DATABASE-RELATED CODE

1. Query the actual database to verify table/column exists
2. Check `prisma/schema.prisma` for the model definition
3. Confirm the schema matches reality
4. Verify using institutional schema taxonomy (not legacy raw/gold/silver)

## ZL IS THE ONLY INTRADAY INSTRUMENT

- `analytics.zl_live` - ZL live price (single row)
- `analytics.zl_intraday` - ZL 15m bars

There are NO generic `intraday_prices` or `latest_prices` tables for multiple symbols.
