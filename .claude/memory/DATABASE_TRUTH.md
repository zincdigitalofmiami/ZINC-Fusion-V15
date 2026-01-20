# DATABASE TRUTH

**Last Updated:** 2026-01-18 (Institutional Schema Migration)

## THERE IS ONLY ONE DATABASE

**Prisma Postgres** - that's it. Nothing else.

- Connection: `DATABASE_URL` in `.env`
- Schema: `prisma/schema.prisma`

## THERE IS NO

- Local database
- Second database

## DEPLOYMENT

- Frontend: Vercel (Next.js + Inngest)
- Database: Prisma Postgres (cloud-hosted)

## SCHEMA TAXONOMY (14 Schemas)

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

**Isolated (separate business domain):**
- `vegas` - Vegas CRM (restaurants, casinos, events, intel sheets)

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

## ZL TIME SERIES

**Active (analytics schema):**
- `analytics.zl_price_15m` - ZL 15m bars
- `analytics.zl_price_1h` - ZL 1h bars
- `analytics.zl_price_1d` - ZL 1d bars (dashboard copy of mkt.futures_1d)

ZL is the only instrument with intraday tracking (15m/1h). Other instruments use daily data only.

## SPECIALIST → TABLE ROUTING (Big 11)

| Specialist | Data Nature | Primary Tables |
|------------|-------------|----------------|
| `crush` | 100% Quant | mkt.futures_1d (ZL/ZS/ZM), pos.cftc_1w |
| `china` | 70/30 Quant/Qual | mkt.futures_1d (HG), mkt.fx_1d (CNY), alt.news_1d |
| `fx` | 100% Quant | mkt.fx_1d |
| `fed` | 100% Quant | econ.rates_1d |
| `tariff` | 40/60 Quant/Qual | econ.rates_1d (EPU), alt.news_1d, alt.legislation_1d |
| `energy` | 100% Quant | mkt.futures_1d (CL/HO), econ.commodities_1d |
| `biofuel` | 80/20 Quant/Qual | supply.epa_rin_1d, alt.news_1d |
| `palm` | 80/20 Quant/Qual | mkt.futures_1d (FCPO), alt.news_1d |
| `volatility` | 100% Quant | econ.vol_indices_1d, econ.rates_1d |
| `substitutes` | 100% Quant | mkt.futures_1d, econ.commodities_1d |
| `trump_effect` | 50/50 Quant/Qual | econ.rates_1d (EPU), alt.news_1d, alt.legislation_1d |

**Pure Quantitative (6):** crush, fx, fed, energy, volatility, substitutes
**Require News Sentiment (5):** china, tariff, biofuel, palm, trump_effect

News items in `alt.news_1d` are tagged with specialist names via `frontend/src/lib/specialist-classifier.ts`.
