NOTE: Production is the dashboard/frontend, not the repo root.
# DATABASE TRUTH
Forward fill policy: [Docs/FORWARD_FILL_POLICY.md](Docs/FORWARD_FILL_POLICY.md)


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

## BANNED SCHEMAS

These schemas are DEPRECATED and must not be used:
- `raw`, `gold`, `silver`, `bronze`, `monitoring`, `specialist`, `weather`, `archive`

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

## SPECIALIST MODEL ARCHITECTURES (v3 - CRITICAL)

> **v3**: Specialists produce SIGNALS, not OOF forecasts. NO horizons.
> Each specialist has a UNIQUE, CUSTOM-BUILT model architecture.
> Signals stored in `training.specialist_signals_1d`. Core owns all horizon forecasting.

| Specialist | Model Type | Full Architecture | Key Features |
|------------|------------|-------------------|--------------|
| `crush` | `xgb` | XGBRegressor | Board crush z-score, oil share, WASDE |
| `china` | `gbm` | GradientBoostingRegressor | Copper z-score, CNY, BRL, shipping |
| `substitutes` | `rf` | RandomForestRegressor | Spread/ratio z-scores vs canola, palm, sunflower |
| `fx` | `ardl` | statsmodels ARDL | DXY, BRL/USD, CNY/USD, MXN/USD, carry trade |
| `fed` | `ridge` | Ridge Regression | Fed Funds, DGS2, DGS10, T10Y2Y spread |
| `volatility` | `garch` | GJR-GARCH(1,1) Student-t | Asymmetric vol, VIX, VIX3M, OVX |
| `energy` | `var` | statsmodels VAR + IRF | CL, HO, RB, 3-2-1 crack |
| `palm` | `ecm` | ECM cointegration + Ridge | Palm-soy spread, coint residuals |
| `tariff` | `tree` | Rules-based EPU thresholds | USEPUINDXM, EPUTRADE |
| `biofuel` | `nlp_ema` | EMA-smoothed RIN/policy | RIN D4/D6, biodiesel margin |
| `trump_effect` | `event_study` | Event study + sentiment | EPU indices, FXI, VIX |

**Signal Output Contract:** `signal_1` (required), `signal_2` (optional), `confidence` (optional)
**Code:** `src/fusion/specialists/` | **Artifacts:** `models/specialists/{bucket}/`

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