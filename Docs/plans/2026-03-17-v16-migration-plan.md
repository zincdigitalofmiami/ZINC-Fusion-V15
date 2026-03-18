# ZINC-FUSION-V16 Migration Plan

## Clean-Room Rebuild on Supabase

**Date:** 2026-03-17
**Status:** Approved design — ready for execution
**Approach:** Audit-first blueprint — product requirements drive architecture, not V15 code

---

## Table of Contents

1. [Principles](#1-principles)
2. [Product Surface — What V16 Must Deliver](#2-product-surface--what-v16-must-deliver)
3. [Target Architecture](#3-target-architecture)
4. [Schema Design (9 Schemas)](#4-schema-design-9-schemas)
5. [Job Architecture — Replacing Inngest](#5-job-architecture--replacing-inngest)
6. [API Surface](#6-api-surface)
7. [Auth & Security Model](#7-auth--security-model)
8. [Python Pipeline Rebuild](#8-python-pipeline-rebuild)
9. [Frontend Wireframe](#9-frontend-wireframe)
10. [Evaluation Gates & Quality Checks](#10-evaluation-gates--quality-checks)
11. [Phased Execution Sequence](#11-phased-execution-sequence)
12. [Risk Matrix](#12-risk-matrix)
13. [Highest-Value Validation Steps](#13-highest-value-validation-steps)
14. [Dependency-Aware Remediation Sequence](#14-dependency-aware-remediation-sequence)

---

## 1. Principles

### What V16 Is

- A from-scratch rebuild — **no code transferred from V15**
- V15 stays live as reference and rollback during the entire build
- V15 is a reference for *what the product does*, not a source of code to port
- Purpose: eliminate all drift, errors, mismatches, legacy baggage, Inngest complexity

### What V16 Is Not

- Not a migration-in-place
- Not a refactor of V15
- Not a copy-paste with cleanup
- Not allowed to inherit: the old Prisma migration chain, copied `.vercel/` state, hand-copied `.env.local` habits, the Inngest estate, dead pages, dead jobs, or unclear contracts

### Non-Negotiable Rules

1. No old migration history crosses the boundary
2. Every table must have a reader AND a writer
3. Every page must justify its data dependencies
4. Every job must justify its existence
5. Start from the screen, not the schema
6. Clone the chart with zero changes — settings were hard-won
7. Clone the landing page design — specific and intentional
8. ProFarmer is mandatory ($500/month)
9. 11 specialists — never 10. `trump_effect` is the 11th.
10. Target = future price level. Target Zones = horizontal lines. Never cones, bands, or funnels.

---

## 2. Product Surface — What V16 Must Deliver

### Primary Users & Their Needs

| User | Need | V16 Surface |
|------|------|-------------|
| **Chris** (owner, US Oil Solutions — BUYS raw soybean oil by the trainload) | Know where ZL price is heading to time purchases | Dashboard chart + Target Zones + Strategy posture |
| **Chris** | Understand what's driving price | Top 4 Drivers, Regime state, Specialist signals |
| **Kevin** (sales director) | Pitch restaurants, time service visits around events | Vegas Intel page |
| **Both** | Policy/legislation impact on soy oil | Legislation page |
| **Both** | Market sentiment read | Sentiment page |

### V16 Page Surface (6 pages — Quant dropped)

1. **`/`** — Landing page (CLONE from V15 — specific design to preserve)
2. **`/dashboard`** — ZL candlestick chart (CLONE) + Target Zones + live price + regime + drivers + cards
3. **`/strategy`** — Posture recommendation, contract impact calculator, factor waterfall (keep content, redesign layout)
4. **`/legislation`** — Federal Register / policy tracking (clean rebuild)
5. **`/sentiment`** — News sentiment, CoT positioning, narrative (keep first 3-4 rows)
6. **`/vegas-intel`** — Restaurant/casino event intelligence (keep ALL content, better layout — events = everything)

### Critical Data Contracts

| Contract | Powers | Freshness |
|----------|--------|-----------|
| ZL OHLCV daily | Chart rendering | Daily by market close |
| ZL OHLCV 1h | Intraday chart | Hourly during session |
| ZL live/latest price | Live ticker, status bar | Real-time or near-RT |
| Forecast Target Zones | P30/P50/P70 horizontal zones on chart | After each model run |
| Specialist signals | Driver attribution, regime | Daily after pipeline |
| Monte Carlo / probability | Probability statements | After each MC run |
| Regime state | Dashboard regime chip | Daily |
| Legislation events | Legislation page | Daily |
| News/sentiment | Sentiment page | Daily |
| Vegas operations | Vegas Intel page | Event-driven |

### What Dies (V15 baggage that does NOT cross)

- 34 Prisma migrations
- 104 Inngest functions (replaced by pg_cron + Vercel Cron + Python workers)
- Docker Inngest local dev container and healing scripts
- Duplicate/overlapping data ingestion jobs
- Dead tables (`eia_biodiesel_1w` with 0 rows, `uco_prices_1w` with 0 rows)
- Tables with no reader (orphaned)
- `inngest_receipts` table
- Quant page (dropped)
- The entire `.vercel/` state
- Manual `.env.local` habits
- Over-normalized Vegas tables (17 → 7)
- ProFarmer Docker complexity (rebuilt as Python Playwright)

---

## 3. Target Architecture

### Stack

| Layer | V15 (current) | V16 (target) |
|-------|---------------|--------------|
| **Database** | Prisma Postgres (cloud) | Supabase Postgres |
| **Schema mgmt** | Prisma + 34 migrations | Supabase migrations (SQL-first) |
| **Frontend** | Next.js on Vercel | Next.js on Vercel (new project) + Chanui dashboard template |
| **Scheduling** | Inngest (104 functions, Docker) | pg_cron + Vercel Cron (~25 routes) |
| **DB client (TS)** | pg.Pool + Prisma for validation | Supabase JS client + pg.Pool for bulk |
| **DB client (Python)** | psycopg2 direct | psycopg2 direct to Supabase Postgres |
| **ML** | AutoGluon (local, CPU) | AutoGluon (local, CPU) — rebuilt clean |
| **Specialists** | 11 Python signal generators | 11 Python signal generators — rebuilt clean |
| **Auth** | Custom cookie-based | Supabase Auth |
| **Env mgmt** | Manual .env.local | Vercel <> Supabase integration, `vercel env pull` |
| **UI system** | Mixed CSS + shadcn/ui | Chanui template + shadcn/ui + ZINC Fusion brand tokens |

### Local vs Cloud Supabase — Recommendation

| Scenario | Recommendation | Why |
|----------|---------------|-----|
| **Frontend dev** | Local Supabase (`supabase start`) | Fast iteration, no cloud cost, isolated |
| **Python training/inference** | **Cloud Supabase directly** | Training writes large matrices (1500+ cols). Local Supabase means syncing artifacts to cloud afterward — extra step with drift risk. Write directly to cloud. |
| **Data ingestion crons** | Cloud Supabase | Crons run on Vercel/pg_cron against production DB |
| **CI/testing** | Local Supabase | Ephemeral, seeded with fixtures |

**Guard rail:** Create a `training` Postgres role that can only write to `training.*` and `forecasts.*` schemas. The Python pipeline uses this role. Frontend service role is read-only on those schemas.

### Architecture Diagram

```
+-----------------------------------------------------------+
|                      BROWSER                               |
|  Next.js App (Vercel) -- 6 pages                          |
|  Supabase JS client for auth + reads                      |
+---------------------------+-------------------------------+
                            |
+---------------------------v-------------------------------+
|                       VERCEL                               |
|  App Router pages + API routes                             |
|  Vercel Cron (~25 consolidated ingestion triggers)         |
|  Env: auto-injected via Supabase integration               |
+---------------------------+-------------------------------+
                            |
+---------------------------v-------------------------------+
|                      SUPABASE                              |
|  Postgres (9 schemas: mkt, econ, alt, supply, training,   |
|            forecasts, analytics, ops, vegas)                |
|  pg_cron (DB-level scheduled maintenance)                  |
|  Auth (user authentication)                                |
|  RLS policies per schema                                   |
+---------------------------+-------------------------------+
                            |
+---------------------------v-------------------------------+
|              LOCAL / EXTERNAL COMPUTE                      |
|  Python ML Pipeline (rebuilt from scratch)                  |
|  - build_matrix -> training.matrix_1d                      |
|  - train_models -> model artifacts + training.* tables     |
|  - generate_forecasts -> forecasts.* tables                |
|  - run_monte_carlo -> forecasts.monte_carlo_*              |
|  - generate_specialist_signals -> training.specialist_*    |
|  - generate_target_zones -> forecasts.target_zones (NEW)   |
|  Writes directly to Cloud Supabase via psycopg2            |
|                                                            |
|  ProFarmer Scraper (Python Playwright, system cron)        |
+------------------------------------------------------------+
```

---

## 4. Schema Design (9 Schemas)

### Schema Consolidation (12 -> 9)

| Dropped | Reason | Absorbed Into |
|---------|--------|---------------|
| `features` | 3 intermediate tables — training artifacts | `training` |
| `model` | 3 tables — part of training lifecycle | `training` |
| `pos` | 1 table (`cftc_1w`) — it's market data | `mkt` |

### Schema: `mkt` (Market Data + Positioning)

| Table | Purpose | Writer | Reader | Granularity |
|-------|---------|--------|--------|-------------|
| `price_1d` | ZL daily OHLCV — powers the chart | Vercel Cron: zl-daily | Dashboard chart, all pages | Daily |
| `price_1h` | ZL hourly bars | Vercel Cron: zl-intraday | Intraday chart view | Hourly |
| `price_15m` | ZL 15-min bars | Vercel Cron: zl-intraday | Intraday chart zoom | 15min |
| `price_1m` | ZL 1-min bars (90-day retention) | Vercel Cron: zl-intraday | Fine-grain chart | 1min |
| `latest_price` | Most recent ZL price + timestamp | Vercel Cron: zl-intraday, pg_cron rollup | Status bar, live ticker | Real-time |
| `futures_1d` | 84 commodity/index futures daily | Vercel Cron: databento-futures | Specialist features, cross-asset | Daily |
| `options_1d` | ZL options chain | Vercel Cron: databento-options | Vol surface | Daily |
| `fx_1d` | FX rates | Vercel Cron: fx-daily | FX specialist | Daily |
| `etf_1d` | Sector/commodity ETFs | Vercel Cron: etf-daily | Substitutes specialist | Daily |
| `vol_surface` | ZL implied vol surface | Derived from options_1d | Volatility specialist | Daily |
| `cftc_1w` | CFTC positioning (absorbed from `pos`) | Vercel Cron: cftc-weekly | Sentiment page, CoT | Weekly |

### Schema: `econ` (Macro/Economic)

| Table | Purpose | Writer | Reader | Granularity |
|-------|---------|--------|--------|-------------|
| `rates_1d` | Interest rates, yields, SOFR, Fed Funds | Vercel Cron: fred | Fed specialist, trump_effect specialist | Daily |
| `inflation_1d` | CPI, PPI, PCE | Vercel Cron: fred | Macro context | Monthly |
| `labor_1d` | Employment, claims | Vercel Cron: fred | Macro context | Weekly/Monthly |
| `activity_1d` | GDP, industrial production, crop progress | Vercel Cron: fred, nass-weekly | Macro context | Varies |
| `money_1d` | M2, reserves | Vercel Cron: fred | Fed specialist | Monthly |
| `vol_indices_1d` | VIX, MOVE, OVX | Vercel Cron: fred | Volatility specialist | Daily |
| `commodities_1d` | FRED commodity prices (crude, gas, palm, soy, tallow PPI, UCO proxies) | Vercel Cron: fred, palm-oil | Multiple specialists | Daily |
| `weather_1d` | Temperature, precipitation, drought indices | Vercel Cron: weather | Weather features, supply context | Daily |

### Schema: `alt` (Alternative Intel)

| Table | Purpose | Writer | Reader | Granularity |
|-------|---------|--------|--------|-------------|
| `profarmer_news` | ProFarmer articles ($500/mo, mandatory) | Python Playwright scraper | Sentiment page, biofuel specialist | Daily |
| `legislation_1d` | Federal Register regulations | Vercel Cron: legislation | Legislation page | Daily |
| `executive_actions` | White House executive orders | Vercel Cron: legislation | Legislation page, tariff specialist | Daily |
| `congress_bills` | Congressional bills (NEW — V15 had no table) | Vercel Cron: legislation | Legislation page | Daily |
| `fed_speeches` | Fed speeches (NEW — V15 had no table) | Vercel Cron: legislation | Fed specialist | Daily |
| `ice_enforcement` | ICE trade enforcement | Vercel Cron: trade-policy | Tariff specialist | Daily |
| `news_events` | Aggregated news with `source` discriminator column (Google, CONAB, FRED Blog, ESMIS, CBP, AEI, FarmDoc, biofuel RSS) | Vercel Cron: news, trade-policy, biofuel-policy | Sentiment page | Daily |
| `tariff_deadlines` | Upcoming tariff dates/actions | Vercel Cron: trade-policy | Strategy page, tariff specialist | Event-driven |

**Design note:** `news_events` consolidates V15's separate tables (`econ_news`, `policy_news`, `cbp_trade`, `aei_trade`, `farmdoc_rins`, `fas_news`, `esmis_publications`, `biofuel_policy`) into a single table with a `source` column and `specialist_tags[]` array. This is cleaner — one table to query for the sentiment page, filterable by source or tag.

### Schema: `supply` (Physical Supply Chain)

| Table | Purpose | Writer | Reader | Granularity |
|-------|---------|--------|--------|-------------|
| `usda_exports_1w` | Country-level export sales (soybeans, oil, meal) | Vercel Cron: usda-exports | China specialist, tariff specialist | Weekly |
| `usda_wasde_1m` | WASDE crop forecasts | Vercel Cron: usda-wasde | Strategy page, supply context | Monthly |
| `eia_biodiesel_1m` | Biodiesel production | Vercel Cron: eia-biodiesel | Biofuel specialist | Monthly |
| `epa_rin_1d` | RIN credit prices | Vercel Cron: biofuel-policy | Biofuel specialist | Daily |
| `lcfs_credits_1w` | Low Carbon Fuel Standard credits | Vercel Cron: biofuel-policy | Biofuel specialist | Weekly |
| `conab_production_1m` | Brazil crop production | Vercel Cron: supply-monthly | China specialist, palm specialist | Monthly |
| `china_imports_1m` | Chinese soy complex imports | Vercel Cron: supply-monthly | China specialist | Monthly |
| `argentina_crush_1m` | Argentina crush margins | Vercel Cron: supply-monthly | Crush specialist | Monthly |
| `mpob_palm_1m` | Malaysia palm production | Vercel Cron: supply-monthly | Palm specialist | Monthly |
| `panama_canal_1d` | Canal transit data | Vercel Cron: panama-canal | Supply logistics context | Daily |
| `fas_gats_1m` | Global trade flows | Vercel Cron: supply-monthly | Trade context | Monthly |

**Dropped from V15:** `eia_biodiesel_1w` (0 rows, never worked), `uco_prices_1w` (0 rows). UCO/tallow tracked via FRED PPI proxies in `econ.commodities_1d`.

### Schema: `training` (Entire ML Lifecycle)

| Table | Purpose | Writer | Reader | Granularity |
|-------|---------|--------|--------|-------------|
| `matrix_1d` | Feature matrix (~1500 cols) | Python: build_matrix | Python: train_models | Daily rows |
| `specialist_features_crush` | Crush specialist raw features | Python: generate_specialist_features | Python: generate_specialist_signals | Daily |
| `specialist_features_china` | China specialist raw features | Python: generate_specialist_features | Python: generate_specialist_signals | Daily |
| `specialist_features_fx` | FX specialist raw features | Python: generate_specialist_features | Python: generate_specialist_signals | Daily |
| `specialist_features_fed` | Fed specialist raw features | Python: generate_specialist_features | Python: generate_specialist_signals | Daily |
| `specialist_features_tariff` | Tariff specialist raw features | Python: generate_specialist_features | Python: generate_specialist_signals | Daily |
| `specialist_features_energy` | Energy specialist raw features | Python: generate_specialist_features | Python: generate_specialist_signals | Daily |
| `specialist_features_biofuel` | Biofuel specialist raw features | Python: generate_specialist_features | Python: generate_specialist_signals | Daily |
| `specialist_features_palm` | Palm specialist raw features | Python: generate_specialist_features | Python: generate_specialist_signals | Daily |
| `specialist_features_volatility` | Volatility specialist raw features | Python: generate_specialist_features | Python: generate_specialist_signals | Daily |
| `specialist_features_substitutes` | Substitutes specialist raw features | Python: generate_specialist_features | Python: generate_specialist_signals | Daily |
| `specialist_features_trump_effect` | Trump effect specialist raw features | Python: generate_specialist_features | Python: generate_specialist_signals | Daily |
| `specialist_signals_1d` | Composite signals (11x3 = 33 cols) | Python: generate_specialist_signals | Python: build_matrix (merged into matrix) | Daily |
| `oof_core_1d` | Out-of-fold predictions | Python: train_models | Analytics derivation, model evaluation | Per training run |
| `training_runs` | Training run metadata | Python: train_models | Ops monitoring | Per run |
| `model_registry` | Active model versions (absorbed from `model`) | Python: train_models | Python: forward inference | Per model |
| `model_audit` | Model performance tracking (absorbed from `model`) | Python: evaluation scripts | Dashboard accuracy metrics | Per run |
| `prediction_accuracy` | Realized vs predicted (absorbed from `model`) | Python: evaluation scripts | Dashboard accuracy metrics | Daily |
| `board_crush_1d` | Soy crush margins (absorbed from `features`) | Vercel Cron: board-crush | Crush specialist | Daily |

### Schema: `forecasts` (All Forecast Outputs)

| Table | Purpose | Writer | Reader | Granularity |
|-------|---------|--------|--------|-------------|
| `production_1d` | Forward price forecasts per horizon | Python: generate_forward_forecasts | Dashboard Target Zones, strategy | Per forecast run |
| `garch_forecasts` | Conditional volatility forecasts | Python: run_garch | Volatility context, MC input | Per run |
| `monte_carlo_runs` | 10,000 MC simulation results | Python: run_monte_carlo | Probability distributions | Per run |
| `probability_distributions` | Probability distribution data | Python: run_monte_carlo | Analytics | Per horizon |
| `target_zones` | **NEW** — Pre-computed P30/P50/P70 serving table | Python: generate_target_zones | Dashboard chart overlay (direct read) | Per forecast run |
| `forecast_summary_1d` | Human-readable forecast summary | Python: post-processing | Strategy page, brief | Per run |

**Key V16 change:** `target_zones` is a dedicated serving table. V15 derived Target Zones on-the-fly from scattered forecast tables. V16 pre-computes and serves them clean.

### Schema: `analytics` (Dashboard Serving Layer)

| Table | Purpose | Writer | Reader | Granularity |
|-------|---------|--------|--------|-------------|
| `driver_attribution_1d` | Top N price drivers | Python: post-training analysis | Dashboard drivers card | Daily |
| `regime_state_1d` | Current market regime | Python: regime classification | Dashboard regime chip | Daily |
| `market_posture` | ACCUMULATE/WAIT/DEFER recommendation | Python: strategy engine | Strategy page | Daily |
| `risk_metrics` | Portfolio risk summary | Python: risk calculation | Strategy page | Daily |
| `dashboard_metrics` | Pre-computed dashboard numbers | pg_cron: materialized view refresh | Dashboard stat cards | Hourly |
| `chart_overlays` | Pivot lines, support/resistance | Vercel Cron or pg_cron | Chart rendering | Daily |

### Schema: `ops` (Operational Health)

| Table | Purpose | Writer | Reader | Granularity |
|-------|---------|--------|--------|-------------|
| `ingest_run` | Job execution log (replaces inngest_receipts) | Every Vercel Cron route | Freshness monitoring | Per run |
| `data_quality_log` | Data quality issues | Validation checks in writers | Alerting | Event-driven |
| `pipeline_alerts` | Staleness/failure alerts | pg_cron: freshness check | Ops monitoring | Daily |
| `source_registry` | Canonical list of all data sources + status | Manual / migration seed | Reference | Static |

**Dropped from V15:** `quarantined_record` (overbuilt), `data_quality_metrics` (overlaps with log), `inngest_receipts` (Inngest is dead), `ablation_results` (research artifact).

### Schema: `vegas` (Vegas Operations)

| Table | Purpose | Writer | Reader | Granularity |
|-------|---------|--------|--------|-------------|
| `restaurants` | Restaurant accounts | Manual / Glide sync | Vegas Intel page | Event-driven |
| `casinos` | Casino properties | Manual | Vegas Intel page | Static |
| `events` | Vegas events (CES, SEMA, March Madness) — **this is everything** | Manual / Vercel Cron | Vegas Intel page, event impact | Event-driven |
| `venues` | Event venue mapping | Manual | Vegas Intel page | Static |
| `fryers` | Fryer equipment tracking | Manual / Glide sync | Vegas Intel page | Event-driven |
| `customer_scores` | Restaurant scoring/priority | Derived | Vegas Intel page | Periodic |
| `event_impact` | Event -> oil demand impact | Derived | Vegas Intel page | Event-driven |

**Consolidated from V15's 17 tables.** V16 drops over-normalized structure (`shifts`, `shift_casinos`, `shift_restaurants`, `cuisine_affinity`, `cuisine_match`, `event_labels`, `event_entities`, `event_profiles`, `daily_spend`) and uses fewer tables with richer JSON columns where appropriate.

---

## 5. Job Architecture — Replacing Inngest

### The V15 Problem

104 Inngest functions running through a Docker Inngest dev container locally + Vercel serverless in production. Single point of orchestration failure, port conflicts (3000/8288), complex multi-layer healing scripts, serveHost drift incidents.

### V16 Job Homes — 4 Tiers

| Tier | Home | What Goes Here | Why |
|------|------|----------------|-----|
| **A** | **Vercel Cron -> API Route** | All ~80 light data ingestion crons | Simple: cron hits endpoint, endpoint fetches external API, writes to Supabase. No orchestrator needed. |
| **B** | **Supabase pg_cron** | DB-internal operations | Runs inside Postgres, zero network hops, SQL-native |
| **C** | **Python workers (local/CI)** | Training pipeline, specialist signals, forecast generation, Monte Carlo, GARCH | Long-running compute, needs Python libs |
| **D** | **Dedicated service** | ProFarmer scraper | Needs browser runtime |

### Tier A: Vercel Cron -> API Route (~25 consolidated routes)

V15 had 104 fragmented Inngest functions. V16 consolidates to ~25 Vercel Cron routes.

**Consolidation map:**

| V16 Route | Replaces (V15 Inngest) | Schedule | Target Schema |
|-----------|----------------------|----------|---------------|
| `/api/cron/zl-daily` | `zl-daily` | Daily 6:05 CT | mkt |
| `/api/cron/zl-intraday` | `zl-1h`, `zl-15m`, `zl-1m-intraday-refresh` | Every 15m during session | mkt |
| `/api/cron/databento-futures` | 5 futures shards + 5 statistics shards + `databento-futures-1h` + `futures-legacy-symbols-nightly` | Daily 2 AM CT | mkt |
| `/api/cron/databento-options` | 5 options shards | Daily | mkt |
| `/api/cron/fx-daily` | `databento-fx-daily`, `fx-spot-daily`, `fx-databento-spot-daily` | Daily | mkt |
| `/api/cron/etf-daily` | `databento-etf-daily`, `databento-etf-vwap`, `yahoo-etf-fallback` | Daily 8 PM ET | mkt |
| `/api/cron/indices-daily` | `yahooIndicesDaily` | Daily | mkt |
| `/api/cron/fred` | 12 FRED functions (Fed, FX, Energy, Biofuel, Crush, Palm, Vol, Trump, China, General) | Every 8h | econ |
| `/api/cron/cftc-weekly` | `cftcWeekly` | Friday 4 PM ET | mkt |
| `/api/cron/usda-exports` | `usdaExportSalesWeekly` | Thursday | supply |
| `/api/cron/usda-wasde` | `usdaWasdeMonthly` | Monthly | supply |
| `/api/cron/eia-biodiesel` | `eiaBiodieselMonthly` | Monthly | supply |
| `/api/cron/supply-monthly` | CONAB, Argentina, MPOB, China imports, FAS GATS (5 functions) | Monthly (staggered) | supply |
| `/api/cron/panama-canal` | `panamaCanalDaily` | Daily | supply |
| `/api/cron/weather` | NOAA + OpenMeteo + weather features (3 functions) | Daily | econ |
| `/api/cron/legislation` | Federal Register + Congress bills + WhiteHouse + Fed speeches (4 functions) | Daily | alt |
| `/api/cron/news` | Google News + CONAB news + FRED Blog + ESMIS (4 functions) | Daily | alt |
| `/api/cron/trade-policy` | CBP + AEI + ICE (3 functions) | Daily | alt |
| `/api/cron/biofuel-policy` | EPA RIN + FarmDoc + LCFS + biofuel RSS (4 functions) | Daily/Weekly | supply, alt |
| `/api/cron/board-crush` | `boardCrushDaily` | Daily | training |
| `/api/cron/palm-oil` | CPO + palm multi-source (3 functions) | Daily | mkt, econ |
| `/api/cron/specialist-sync` | `specialistSignalsSync` | Daily | training |
| `/api/cron/market-drivers` | Existing Vercel cron | Daily | analytics |
| `/api/cron/freshness-check` | `freshnessMonitor` | Daily | ops |
| `/api/cron/nyfed-daily` | `nyfedDaily` | Daily | econ |

**Vercel Cron limit:** 40 jobs on Pro plan. ~25 routes is well within limit.

### Tier B: Supabase pg_cron (~5 DB-internal jobs)

| Job | SQL Operation | Schedule |
|-----|--------------|----------|
| Retention: delete old 1m bars | `DELETE FROM mkt.price_1m WHERE trade_date < now() - interval '90 days'` | Daily |
| Stale run cleanup | `UPDATE ops.ingest_run SET status='TIMEOUT' WHERE started_at < now() - interval '24h' AND status='RUNNING'` | Daily |
| Materialized view refresh | `REFRESH MATERIALIZED VIEW analytics.dashboard_summary` | Hourly |
| Latest price rollup | `INSERT INTO mkt.latest_price SELECT ... FROM mkt.price_1h ...` | Hourly |
| Data freshness alert | SQL function checking max dates across critical tables | Daily |

### Tier C: Python Workers (~8 scripts)

| Script | What It Does | Writes To | Trigger |
|--------|-------------|-----------|---------|
| `build_matrix.py` | Assemble feature matrix | training.matrix_1d | Manual / system cron |
| `train_models.py` | AutoGluon training (4 horizons) | training.*, model artifacts | Manual (training gate) |
| `generate_specialist_features.py` | 11 specialist feature generators | training.specialist_features_* | Manual / system cron |
| `generate_specialist_signals.py` | Composite signal extraction | training.specialist_signals_1d | After features |
| `generate_forward_forecasts.py` | Forward inference | forecasts.production_1d | After training |
| `run_monte_carlo.py` | 10,000 MC runs per horizon | forecasts.monte_carlo_*, forecasts.probability_* | After forecasts |
| `run_garch.py` | GJR-GARCH volatility | forecasts.garch_forecasts | After price data |
| `generate_target_zones.py` | **NEW** — Pre-compute P30/P50/P70 serving data | forecasts.target_zones | After Monte Carlo |
| `refresh_fred_api.py` | Full FRED history backfill (130+ series) | econ.* | Weekly system cron |

### Tier D: ProFarmer — Special Handling

ProFarmer is $500/month and mandatory. Requires a headless browser.

**V16 approach:** Rebuild as a Python script using Playwright, triggered by system cron on the local/dev machine. Writes directly to cloud Supabase. Falls back to GitHub Actions scheduled workflow for redundancy if local machine is offline.

| Aspect | V15 | V16 |
|--------|-----|-----|
| Runtime | Puppeteer-extra (Node.js) via Docker Inngest | Playwright (Python) via system cron |
| Hosting | Docker container on local machine | Direct Python script on local machine |
| Fallback | None (if Docker down, no scraping) | GitHub Actions scheduled workflow |
| Browser | System Chrome via `resolveChromePath()` | Playwright-managed Chromium |
| Complexity | 23 serverExternalPackages, healing scripts | Single Python script, no Docker |

### Cron Auth Pattern

Every `/api/cron/*` route verifies a `CRON_SECRET` header:

```
Vercel injects CRON_SECRET -> route checks Authorization header -> rejects unauthorized calls
```

This replaces Inngest's signing key mechanism. Simple, proven, no orchestrator dependency.

---

## 6. API Surface

### Read Routes (dashboard-facing, ~15 routes)

| Route | Returns | Source Table(s) |
|-------|---------|-----------------|
| `/api/zl/price-1d` | ZL daily OHLCV for chart | mkt.price_1d |
| `/api/zl/price-1h` | ZL hourly bars | mkt.price_1h |
| `/api/zl/intraday` | ZL 15m/1m bars | mkt.price_15m, mkt.price_1m |
| `/api/zl/live` | Latest price + timestamp | mkt.latest_price |
| `/api/zl/target-zones` | P30/P50/P70 zone data for chart overlay | forecasts.target_zones |
| `/api/zl/forecast` | Forecast summary (horizon, predicted price, probability) | forecasts.production_1d, forecasts.forecast_summary_1d |
| `/api/dashboard/metrics` | Pre-computed dashboard stats | analytics.dashboard_metrics |
| `/api/dashboard/drivers` | Top 4 price drivers | analytics.driver_attribution_1d |
| `/api/dashboard/regime` | Current regime state | analytics.regime_state_1d |
| `/api/strategy/posture` | ACCUMULATE/WAIT/DEFER + rationale | analytics.market_posture |
| `/api/sentiment/overview` | News sentiment + CoT positioning | alt.news_events, mkt.cftc_1w |
| `/api/legislation/feed` | Legislation + executive actions feed | alt.legislation_1d, alt.executive_actions, alt.congress_bills |
| `/api/vegas/intel` | Restaurants, events, impact, customer data | vegas.* |
| `/api/health` | DB connectivity + data freshness check | ops.ingest_run |

### Cron Routes (~25 routes)

All under `/api/cron/*`, protected by `CRON_SECRET` header. See Section 5 Tier A for full list.

### Auth Routes

| Route | Purpose |
|-------|---------|
| `/api/auth/callback` | Supabase Auth callback |
| `/api/auth/check` | Session validation |

### Dropped from V15

- `/api/zl/brief` — fold into forecast
- `/api/zl/context` — fold into dashboard metrics
- `/api/zl/raw` — unnecessary
- `/api/zl/chart` — redundant with price-1d
- `/api/zl/price-5m` — unnecessary granularity
- `/api/policy/section-brief` — merge into legislation feed
- `/api/refresh-drivers` — drivers refresh via cron
- `/api/epu` — fold into dashboard metrics
- `/api/weather-risk` — fold into dashboard
- `/api/quant/overview` — quant page dropped

---

## 7. Auth & Security Model

### V15 Problem

Custom cookie-based auth with unclear RLS enforcement. Service-role key used for all DB reads, bypassing Supabase RLS policies. No clear separation between public reads and admin writes.

### V16 Auth Design

**Two access tiers:**

| Tier | Who | Supabase Key | Can Do |
|------|-----|-------------|--------|
| **Dashboard user** (Chris, Kevin) | Authenticated via Supabase Auth | `anon` key + JWT | Read all dashboard-facing tables via API routes |
| **System** (cron jobs, Python pipeline) | Service role | `service_role` key | Write to all tables, bypasses RLS |

### RLS Strategy

| Schema | RLS | Policy |
|--------|-----|--------|
| `mkt`, `econ`, `alt`, `supply` | ON | `SELECT` for authenticated users, `INSERT/UPDATE` for service_role only |
| `training`, `forecasts` | ON | `SELECT` for authenticated users, `INSERT/UPDATE/DELETE` for service_role only |
| `analytics` | ON | `SELECT` for authenticated users, writes only from pg_cron or service_role |
| `ops` | ON | `SELECT` for service_role only (not user-facing) |
| `vegas` | ON | `SELECT` for authenticated users, writes for service_role |

### API Route Auth Pattern

```
Browser -> /api/zl/price-1d -> middleware checks Supabase session cookie
  -> if valid: query with supabase client (respects RLS)
  -> if not: 401

Vercel Cron -> /api/cron/fred -> checks CRON_SECRET header
  -> if valid: query with service_role client (bypasses RLS)
  -> if not: 401
```

### Environment Variables

| Variable | Source | Used By |
|----------|--------|---------|
| `NEXT_PUBLIC_SUPABASE_URL` | Supabase integration | Browser client |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Supabase integration | Browser client |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase integration | Server-side routes, cron |
| `DATABASE_URL` | Supabase integration | Python pipeline (psycopg2 direct, port 5432) |
| `DATABASE_POOLER_URL` | Supabase integration | Python short reads (port 6543) |
| `CRON_SECRET` | Vercel env settings | Cron route protection |
| `DATABENTO_API_KEY` | Vercel env settings | Market data ingestion |
| `FRED_API_KEY` | Vercel env settings | FRED ingestion |
| `PROFARMER_*` | Local env only | ProFarmer scraper (never on Vercel) |

### Security Rules

1. No `service_role` key exposed to browser — ever
2. All browser reads go through API routes with JWT/session validation
3. `NEXT_PUBLIC_*` vars contain only anon key and URL — no secrets
4. Python pipeline uses direct connection (port 5432) for bulk writes — not pooler
5. ProFarmer credentials never deployed to Vercel
6. No manual `.env` copying — all env management through Vercel integration + `vercel env pull`

---

## 8. Python Pipeline Rebuild

### Pipeline Phases

```
Phase 1: Data Ingestion     <-- Vercel Cron handles this (not Python)
Phase 2: Feature Assembly    <-- build_matrix.py
Phase 3: Specialist Features <-- generate_specialist_features.py
Phase 4: Specialist Signals  <-- generate_specialist_signals.py
Phase 5: Core Training       <-- train_models.py (AutoGluon, 4 horizons)
Phase 6: Forward Inference   <-- generate_forward_forecasts.py
Phase 7: Monte Carlo         <-- run_monte_carlo.py (10,000 runs)
Phase 8: GARCH               <-- run_garch.py
Phase 9: Post-Processing     <-- generate_target_zones.py (NEW)
```

### What Changes from V15

| Aspect | V15 | V16 |
|--------|-----|-----|
| **DB connection** | psycopg2 -> Prisma Postgres | psycopg2 -> Supabase Postgres (direct for writes, pooler for reads) |
| **Config** | Scattered across modules | Single `config.py` with frozen model zoo, schema constants |
| **Matrix builder** | 1,487 features, accumulated drift columns | Clean rebuild — only features with a reader. Intentional count. |
| **Specialist features** | 11 buckets, some with ffill bugs, EIA zeros | 11 buckets, clean loaders, explicit null policy per source |
| **Model artifacts** | `models/core_v2/{horizon}d/` local files | Same local structure, `model_registry` in Supabase tracks promotions |
| **Forward inference** | Two scripts existed (old OOF-based + new forward) | Single `generate_forward_forecasts.py` — forward only |
| **Target Zones** | Derived on-the-fly in API routes | Pre-computed by `generate_target_zones.py`, written to `forecasts.target_zones` |
| **Package manager** | uv | uv (keep) |
| **Testing** | pytest with ~16% coverage | pytest — rebuild tests alongside pipeline |

### New Script: `generate_target_zones.py`

V15 scattered Target Zone computation across API routes and Monte Carlo outputs. V16 has a dedicated post-processing step:

```
Reads:  forecasts.production_1d + forecasts.monte_carlo_runs + forecasts.garch_forecasts
Computes: P30/P50/P70 price levels per horizon
Writes: forecasts.target_zones (serving table)
Dashboard reads: forecasts.target_zones directly -- no on-the-fly computation
```

### Pipeline Runner

```bash
# Full pipeline
python -m fusion.pipeline run --all

# Individual phases
python -m fusion.pipeline run --phase matrix
python -m fusion.pipeline run --phase specialists
python -m fusion.pipeline run --phase train
python -m fusion.pipeline run --phase forecast
python -m fusion.pipeline run --phase monte-carlo
python -m fusion.pipeline run --phase target-zones

# Dry run (shows what would happen, no writes)
python -m fusion.pipeline run --all --dry-run
```

### Connection Strategy

```
Cloud Supabase connection string:
  Direct (port 5432): for long training writes — no pooler timeout
  Pooled (port 6543): for short reads/queries

Env vars:
  SUPABASE_DB_URL       = direct connection
  SUPABASE_POOLER_URL   = pooled connection
```

### Training Gate (carried from V15 — still mandatory)

**NEVER start model training without explicit user approval.** The pipeline runner has a `--dry-run` flag. Training writes are gated behind a confirmation prompt.

### Model Architecture (unchanged conceptually)

- **L0 Core:** 4 AutoGluon TimeSeriesPredictor ensembles (5d/21d/63d/126d), each training 19-model zoo
- **Target:** Future ZL futures contract price (`close.shift(-horizon)`), columns named `target_price_{h}d`
- **Metric:** MAE (point forecast accuracy)
- **Output:** Single `predicted_price` per horizon
- **Covariates:** All OBSERVED (no known future values)
- **Validation:** 4 expanding windows
- **Frequency:** Business day (`B`)
- **L2/L3:** Calibration + Monte Carlo wraps price prediction with probability -> Target Zones

### Big-11 Specialists (unchanged conceptually)

| Bucket | Model Type | Signal Contract |
|--------|-----------|-----------------|
| crush | GBM | Crush margin z-score + momentum |
| china | GBM | Demand outlook + Brazil competition |
| substitutes | RF | Substitution pressure + richness |
| fx | ARDL | FX pressure index + carry |
| fed | Ridge | Rates regime + change |
| tariff | Rule-based | Tariff risk + EPU spike |
| energy | VAR | Energy spillover + momentum |
| biofuel | NLP + EMA | Policy pressure + trend |
| palm | ECM + Ridge | Cointegration + mean reversion |
| volatility | GJR-GARCH | Conditional variance z-score + regime |
| trump_effect | Event study | Intensity + volatility impact |

---

## 9. Frontend Wireframe

### Shell: Chanui Dashboard Template

Chanui provides the authenticated dashboard shell — sidebar nav, header bar, content area, responsive layout. V16 installs it fully and customizes with ZINC Fusion brand tokens.

### Page Map (6 pages)

```
/                   -> Landing page (CLONE from V15)
/dashboard          -> Main dashboard (CLONE chart + cards, Chanui shell)
/strategy           -> Strategy posture (keep content, redesign layout)
/legislation        -> Legislation tracking (clean rebuild)
/sentiment          -> News + CoT (keep first 3-4 rows)
/vegas-intel        -> Vegas operations (keep ALL, better layout)
```

### Landing Page (`/`)

**Directive: CLONE.** The V15 landing page design is specific and intentional. V16 reproduces it faithfully inside the Chanui template's public (non-authenticated) shell.

**Elements to preserve exactly:**
- Hero composition with headline + proof + CTA
- NeuralSphere or equivalent premium visual
- Product module cards
- Trust/proof strip (horizons, specialists, update SLA)
- Method section narrative
- Logo + brand identity
- Typography and spacing intent

**Layout reference:**

```
+-------------------------------------------------------------+
| Top Nav: logo | product | methodology | access | CTA         |
+-------------------------------------------------------------+
| Hero:                                                        |
| Left: headline + proof + CTA                                 |
| Right: live chart teaser / animated data object              |
+-------------------------------------------------------------+
| Trust / proof strip: horizons | specialists | update SLA     |
+-------------------------------------------------------------+
| Product modules: Dashboard | Strategy | Policy | Intel       |
+-------------------------------------------------------------+
| Method section: How the intelligence stack works             |
+-------------------------------------------------------------+
| CTA / Footer                                                 |
+-------------------------------------------------------------+
```

### Dashboard (`/dashboard`)

**Directive: CLONE chart, keep cards.**

| Zone | Content | Notes |
|------|---------|-------|
| **Chart area** | LightweightZlCandlestickChart — cloned exactly. ForecastTargetsPrimitive for Target Zones. PivotLinesPrimitive for pivots. Watermark. All settings preserved. | **Do not modify chart settings. They were hard-won.** |
| **Status bar** | Live price, last update, regime chip, data freshness | mkt.latest_price, analytics.regime_state_1d |
| **Cards row** | Dashboard stat cards — keep exactly as-is | analytics.dashboard_metrics |
| **Drivers** | Top 4 drivers card (ChrisTop4Drivers) | analytics.driver_attribution_1d |
| **Regime** | Regime analysis chart | analytics.regime_state_1d |

**Specialist highlight cards (planned — add in future sprint):**

These key elements need to be highlighted on the dashboard as cards. Not V16 launch blockers but planned additions:

- **Weather** risk card — drought/temperature impact on soy crop
- **Crush** margin card — current board crush, oil share, ratios
- **Volatility** regime card — current GARCH regime, VIX/OVX context
- **China** demand card — import trends, YoY comparison
- **Legislation** alert card — latest regulations affecting soy oil/biofuel
- **Used Cooking Oil (UCO)** price card — tallow/grease PPI proxies
- **Palm Oil** supply card — MPOB production, CPO price, substitution pressure

### Sentiment (`/sentiment`)

**Directive: Keep first 3-4 rows from V15.**

| Row | Content | Status |
|-----|---------|--------|
| 1 | Sentiment overview / headline metrics | KEEP |
| 2 | News feed with sentiment tags and source filtering | KEEP |
| 3 | CoT positioning / CFTC visualization | KEEP |
| 4 | Narrative summary | KEEP (if in top rows) |
| Lower | Deeper analytics | Defer |

### Vegas Intel (`/vegas-intel`)

**Directive: Keep ALL. Events = everything. Better layout.**

| Element | Status | Notes |
|---------|--------|-------|
| **Events calendar/feed** | KEEP — this is everything | CES, SEMA, March Madness, conventions |
| **Intel buttons** | KEEP | AI-powered sales strategy recommendations |
| **Restaurant data** | KEEP | Real customer API data, real oil volumes used |
| **Casino/venue mapping** | KEEP | Which properties, which events |
| **AI sales strategy** | KEEP — this is the gold feature | Personalized pitch generation matched with real customer data |
| **Fryer tracking** | KEEP | Equipment lifecycle, service scheduling |
| **Layout** | REDESIGN | Better information hierarchy, same content |

### Strategy (`/strategy`)

**Directive: Keep content, rethink layout.**

| Element | Status |
|---------|--------|
| Market posture (ACCUMULATE/WAIT/DEFER) | KEEP |
| Contract impact calculator | KEEP |
| Factor waterfall | KEEP |
| FusionBrain visualization | EVALUATE — keep if product-relevant |
| Risk metrics | KEEP |
| Specialist signal summary | KEEP |
| Layout | REDESIGN — needs more thought, better hierarchy |

### Legislation (`/legislation`)

Clean rebuild. Feed of Federal Register rules, executive actions, congressional bills, with specialist tags and relevance scoring.

### Design Token Layer

V16 tokens for Chanui customization:

- Colors (brand palette from V15 logo)
- Spacing
- Radii
- Elevation
- Motion rules (subtle on data pages, richer on landing)
- Chart accent colors
- Typography
- Data-state colors (bullish/bearish/neutral)

---

## 10. Evaluation Gates & Quality Checks

### Gate 1: Supabase Foundation Verification

**Before any feature work:**

| Check | Evidence Required |
|-------|-------------------|
| Supabase project created and reachable | `supabase status` returns healthy |
| Local Supabase starts cleanly | `supabase start` succeeds, all services green |
| Vercel <> Supabase integration active | Env vars auto-populated in Vercel project settings |
| `vercel env pull` works in V16 repo | `.env.local` generated with correct Supabase keys |
| DB health route responds | `GET /api/health` returns `{ ok: true }` from local and preview |
| Direct psycopg2 connection from Python | Connection test passes against cloud Supabase |
| V16 repo is NOT linked to V15 Vercel project | `vercel ls` shows only `zinc-fusion-v16` |

### Gate 2: Schema Integrity

**After schema creation, before any writes:**

| Check | Evidence Required |
|-------|-------------------|
| All 9 schemas exist | `\dn` in psql lists exactly 9 |
| Every table has a primary key | No heap-only tables |
| Every table has `created_at` timestamp | Audit trail |
| Every table with external data has `ingested_at` | Freshness tracking |
| Every table referenced by an API route exists | Route -> table trace complete |
| No orphan tables (no reader AND no writer) | Full dependency map |
| RLS enabled on all tables | `rowsecurity = true` for all |
| Indexes on all date/symbol columns | `\di` confirms indexes |

### Gate 3: Auth & Security Verification

| Check | Evidence Required |
|-------|-------------------|
| `CRON_SECRET` set in Vercel env | Vercel dashboard confirms |
| Every `/api/cron/*` route checks `CRON_SECRET` | Code review of each route |
| No `service_role` key in browser-accessible code | Grep for key in client components = 0 results |
| `NEXT_PUBLIC_*` vars contain only anon key and URL | No secrets in public vars |
| RLS policies block unauthenticated reads | Test: anon request without JWT -> rejected |
| Supabase Auth callback route works | Login -> callback -> session -> authenticated read succeeds |
| Python pipeline uses direct connection for bulk writes | Connection string check |

### Gate 4: Data Flow Verification

| Check | Evidence Required |
|-------|-------------------|
| Each Vercel Cron route writes expected rows | Manual trigger -> DB row count increases |
| Each API read route returns expected shape | Sample response matches contract |
| Chart renders with real data from Supabase | Visual inspection on preview deploy |
| Target Zones render on chart | ForecastTargetsPrimitive draws P30/P50/P70 lines |
| Live price updates | latest_price timestamp is recent |
| Freshness monitor fires and reports correctly | After 24h, check ops.pipeline_alerts |

### Gate 5: Python Pipeline Verification

| Check | Evidence Required |
|-------|-------------------|
| `build_matrix.py` writes to training.matrix_1d in cloud Supabase | Row count > 0, column count matches |
| All 11 specialist feature generators complete | specialist_features_{bucket} has rows for each |
| `generate_specialist_signals.py` produces 33 signal columns | Check specialist_signals_1d |
| Training run completes for all 4 horizons | training_runs has 4 new rows |
| Forward inference writes to forecasts.production_1d | Predicted prices exist per horizon |
| Monte Carlo writes 10,000 runs | monte_carlo_runs count check |
| `generate_target_zones.py` produces P30/P50/P70 | target_zones has rows |
| Dashboard reads Target Zones correctly | Chart overlay matches Python output |

### Gate 6: Parity Verification (V15 vs V16)

| Check | Evidence Required |
|-------|-------------------|
| `/api/zl/price-1d` — same OHLCV data | Diff V15 vs V16 responses |
| `/api/zl/live` — same latest price | Compare timestamps and values |
| Target Zones — same P30/P50/P70 levels | Side-by-side chart comparison |
| Dashboard cards — same metrics | Screenshot comparison |
| Sentiment page — same news feed | Visual comparison |
| Vegas Intel — same events/restaurants | Data comparison |

---

## 11. Phased Execution Sequence

Each phase has entry criteria, deliverables, and exit criteria. No phase starts until the prior phase's exit criteria are met.

### Phase 0: Infrastructure Foundation

**Entry:** New Supabase project created, new Vercel project created, new Git repo initialized.

| Step | Action | Exit Evidence |
|------|--------|---------------|
| 0.1 | Create Supabase project (Pro plan) | Dashboard accessible, connection string works |
| 0.2 | Create Vercel project `zinc-fusion-v16` | `vercel ls` shows project |
| 0.3 | Install Supabase <> Vercel integration | Env vars auto-populated |
| 0.4 | Init Next.js app with Chanui dashboard template | `npm run dev` renders template |
| 0.5 | Install shadcn/ui component library | `npx shadcn-ui init` succeeds |
| 0.6 | Set up local Supabase (`supabase init` + `supabase start`) | Local stack healthy |
| 0.7 | Create `/api/health` route | Returns `{ ok: true }` from local + preview |
| 0.8 | Verify Python psycopg2 connects to cloud Supabase | Connection test passes |
| 0.9 | Copy brand assets (logo, watermark, icons) into `public/` | Assets render on preview |
| 0.10 | Set up `uv` Python environment with clean `pyproject.toml` | `uv sync` succeeds |

**Exit criteria:** Health route live on preview, Python connects to cloud, brand assets visible, Chanui shell renders.

### Phase 1: Schema & Seed

**Entry:** Phase 0 complete.

| Step | Action | Exit Evidence |
|------|--------|---------------|
| 1.1 | Create all 9 schemas via Supabase migration | `\dn` shows 9 schemas |
| 1.2 | Create `mkt.*` tables (11 tables) | All tables exist with correct columns |
| 1.3 | Create `econ.*` tables (8 tables) | All tables exist |
| 1.4 | Create `alt.*` tables including NEW congress_bills + fed_speeches (8 tables) | All tables exist |
| 1.5 | Create `supply.*` tables (11 tables) | All tables exist |
| 1.6 | Create `training.*` tables including absorbed features + model tables (19 tables) | All tables exist |
| 1.7 | Create `forecasts.*` tables including NEW target_zones (6 tables) | All tables exist |
| 1.8 | Create `analytics.*` tables (6 tables) | All tables exist |
| 1.9 | Create `ops.*` tables (4 tables) | All tables exist |
| 1.10 | Create `vegas.*` tables — consolidated design (7 tables) | All tables exist |
| 1.11 | Enable RLS on all tables | `rowsecurity = true` for all |
| 1.12 | Create RLS policies (authenticated read, service_role write) | Policy tests pass |
| 1.13 | Create indexes on all date/symbol columns | `\di` confirms indexes |
| 1.14 | Seed `ops.source_registry` with all data sources | Registry populated |
| 1.15 | Run Gate 2 (Schema Integrity) checks | All checks pass |

**Exit criteria:** All tables exist, RLS active, indexes created, Gate 2 passes.

### Phase 2: Read Path — Chart & Live Price

**Entry:** Phase 1 complete. This is the most critical phase — if the chart doesn't work, nothing else matters.

| Step | Action | Exit Evidence |
|------|--------|---------------|
| 2.1 | Seed `mkt.price_1d` with V15 historical data (manual export/import) | 2+ years of ZL daily bars in Supabase |
| 2.2 | Build `/api/zl/price-1d` read route | Returns OHLCV JSON matching V15 format |
| 2.3 | Clone LightweightZlCandlestickChart into V16 | Chart renders with real data from Supabase |
| 2.4 | Clone ForecastTargetsPrimitive | Target Zone lines render (placeholder data OK) |
| 2.5 | Clone PivotLinesPrimitive | Pivot lines render |
| 2.6 | Clone chart watermark | Watermark visible |
| 2.7 | Build `/api/zl/live` read route | Returns latest price |
| 2.8 | Clone useZlLivePrice hook | Status bar shows live price |
| 2.9 | Clone dashboard cards (exact copy) | Cards render with placeholder/seeded data |
| 2.10 | Build `/api/zl/price-1h` route | Hourly data serves correctly |
| 2.11 | Parity check: V15 chart vs V16 chart side-by-side | Visually identical |

**Exit criteria:** Chart renders identically to V15 with real historical data. Live price route works. Cards render.

### Phase 3: Landing Page

**Entry:** Phase 2 complete (chart works).

| Step | Action | Exit Evidence |
|------|--------|---------------|
| 3.1 | Clone V15 landing page design into Chanui public shell | Landing page renders |
| 3.2 | Preserve hero composition, typography, spacing | Visual match to V15 |
| 3.3 | Preserve NeuralSphere or equivalent premium visual | Animation renders |
| 3.4 | Product module cards | Cards render with correct copy |
| 3.5 | Trust/proof strip | Horizons, specialists, update SLA visible |
| 3.6 | Chart teaser section (can use the real chart component) | Chart preview renders |
| 3.7 | CTA -> dashboard flow | Click-through works |
| 3.8 | Logo in header | Brand identity correct |

**Exit criteria:** Landing page is visually faithful to V15. CTA leads to dashboard.

### Phase 4: Data Ingestion — Critical Cron Routes

**Entry:** Phase 2 complete. Chart needs fresh data, not just seed data.

| Step | Action | Exit Evidence |
|------|--------|---------------|
| 4.1 | Build `/api/cron/zl-daily` (ZL daily OHLCV from Databento) | New rows in mkt.price_1d after cron fires |
| 4.2 | Build `/api/cron/zl-intraday` (1h + 15m from Databento) | Intraday bars populating |
| 4.3 | Build `/api/cron/fred` (consolidated — all FRED series in one route) | econ.* tables updating |
| 4.4 | Build `/api/cron/databento-futures` (consolidated — all futures + stats) | mkt.futures_1d updating |
| 4.5 | Build `/api/cron/databento-options` (consolidated) | mkt.options_1d updating |
| 4.6 | Build `/api/cron/fx-daily` | mkt.fx_1d updating |
| 4.7 | Build `/api/cron/etf-daily` | mkt.etf_1d updating |
| 4.8 | Build `/api/cron/cftc-weekly` | mkt.cftc_1w updating |
| 4.9 | Set up `CRON_SECRET` and auth middleware for all cron routes | Unauthorized requests rejected |
| 4.10 | Configure `vercel.json` cron schedules for steps 4.1-4.8 | Crons firing on schedule |
| 4.11 | Build `/api/cron/freshness-check` | ops.pipeline_alerts populating |

**Exit criteria:** Chart shows today's data. Core market tables updating on schedule. Freshness monitoring active.

### Phase 5: Python Pipeline Rebuild

**Entry:** Phase 4 complete (data flowing into Supabase).

| Step | Action | Exit Evidence |
|------|--------|---------------|
| 5.1 | Rebuild `config.py` — frozen model zoo, schema constants, DB URLs | Config loads cleanly |
| 5.2 | Rebuild `build_matrix.py` — reads from Supabase, assembles features | training.matrix_1d has rows with expected column count |
| 5.3 | Rebuild specialist feature generators (all 11) | training.specialist_features_{bucket} populated |
| 5.4 | Rebuild `generate_specialist_signals.py` | training.specialist_signals_1d has 33 signal columns |
| 5.5 | Rebuild `train_models.py` — AutoGluon, 4 horizons, frozen zoo | Training completes, artifacts saved, training_runs logged |
| 5.6 | Rebuild `generate_forward_forecasts.py` | forecasts.production_1d has predicted prices |
| 5.7 | Rebuild `run_monte_carlo.py` — 10,000 runs | forecasts.monte_carlo_runs populated |
| 5.8 | Rebuild `run_garch.py` | forecasts.garch_forecasts populated |
| 5.9 | Build NEW `generate_target_zones.py` | forecasts.target_zones has P30/P50/P70 per horizon |
| 5.10 | Rebuild `pipeline.py` runner (orchestrates all phases) | `python -m fusion.pipeline run --all` completes |
| 5.11 | Run Gate 5 (Python Pipeline Verification) | All checks pass |

**Exit criteria:** Full pipeline runs end-to-end against cloud Supabase. Target Zones appear on dashboard chart.

### Phase 6: Remaining Data Ingestion Crons

**Entry:** Phase 4 complete.

| Step | Action | Exit Evidence |
|------|--------|---------------|
| 6.1 | Build `/api/cron/supply-monthly` (CONAB, Argentina, MPOB, China, FAS) | supply.* tables updating |
| 6.2 | Build `/api/cron/usda-exports` + `/api/cron/usda-wasde` | supply.usda_* updating |
| 6.3 | Build `/api/cron/eia-biodiesel` | supply.eia_biodiesel_1m updating |
| 6.4 | Build `/api/cron/biofuel-policy` (EPA RIN, FarmDoc, LCFS, RSS) | supply + alt tables updating |
| 6.5 | Build `/api/cron/legislation` (Federal Register, Congress, WhiteHouse, Fed speeches) | alt.* tables updating |
| 6.6 | Build `/api/cron/news` (Google News, CONAB, FRED Blog, ESMIS) | alt.news_events updating |
| 6.7 | Build `/api/cron/trade-policy` (CBP, AEI, ICE) | alt.* tables updating |
| 6.8 | Build `/api/cron/weather` (NOAA, OpenMeteo, features) | econ.weather_1d updating |
| 6.9 | Build `/api/cron/board-crush` | training.board_crush_1d updating |
| 6.10 | Build `/api/cron/palm-oil` | mkt/econ palm tables updating |
| 6.11 | Build `/api/cron/panama-canal` | supply.panama_canal_1d updating |
| 6.12 | Build ProFarmer scraper (Python Playwright, system cron) | alt.profarmer_news populating |
| 6.13 | Set up pg_cron jobs (retention, stale cleanup, materialized views, freshness) | pg_cron schedule visible in Supabase dashboard |
| 6.14 | Configure all remaining vercel.json cron schedules | All crons firing |

**Exit criteria:** All data sources feeding Supabase. ProFarmer scraping. pg_cron running DB maintenance.

### Phase 7: Dashboard Completion + Analytics Routes

**Entry:** Phase 5 complete (forecasts exist).

| Step | Action | Exit Evidence |
|------|--------|---------------|
| 7.1 | Build `/api/zl/target-zones` route | Returns P30/P50/P70 from forecasts.target_zones |
| 7.2 | Wire Target Zones into chart | Horizontal zone lines render with real forecast data |
| 7.3 | Build `/api/dashboard/drivers` route | Returns top 4 drivers |
| 7.4 | Wire ChrisTop4Drivers card | Drivers display with real data |
| 7.5 | Build `/api/dashboard/regime` route | Returns regime state |
| 7.6 | Wire regime chip + RegimeAnalysisChart | Regime renders |
| 7.7 | Build `/api/dashboard/metrics` route | Returns dashboard stats |
| 7.8 | Wire all dashboard cards with live data | Cards show real numbers |
| 7.9 | Run Gate 6 (Parity Verification) for dashboard | V16 dashboard matches V15 |

**Specialist highlight cards (noted for future sprint):**
- Weather risk card
- Crush margin card
- Volatility regime card
- China demand card
- Legislation alert card
- UCO/tallow price card
- Palm oil supply card

**Exit criteria:** Dashboard fully functional with real data. Target Zones rendering. Cards live. Parity with V15 confirmed.

### Phase 8: Secondary Pages

**Entry:** Phase 7 complete.

| Step | Action | Exit Evidence |
|------|--------|---------------|
| 8.1 | Build `/api/sentiment/overview` route | Returns news + CoT data |
| 8.2 | Rebuild Sentiment page — first 3-4 rows from V15 | Sentiment overview, news feed, CoT, narrative render |
| 8.3 | Build `/api/legislation/feed` route | Returns legislation + executive actions + congress bills |
| 8.4 | Rebuild Legislation page | Feed renders with tags and relevance |
| 8.5 | Build `/api/strategy/posture` route | Returns ACCUMULATE/WAIT/DEFER + rationale |
| 8.6 | Rebuild Strategy page — keep content, redesign layout | Posture, calculator, waterfall, risk metrics render |
| 8.7 | Build `/api/vegas/intel` route | Returns events, restaurants, scores, customer data |
| 8.8 | Rebuild Vegas Intel page — ALL content, better layout. Events = everything. Intel buttons + AI sales strategy + real customer API data + real oil usage = gold. | All elements render |
| 8.9 | Parity check: all pages vs V15 | Functionality matches or exceeds |

**Exit criteria:** All 6 pages (Landing, Dashboard, Strategy, Legislation, Sentiment, Vegas Intel) operational.

### Phase 9: Auth, Security, Observability

**Entry:** Phase 8 complete.

| Step | Action | Exit Evidence |
|------|--------|---------------|
| 9.1 | Implement Supabase Auth (login flow for Chris/Kevin) | Login flow works |
| 9.2 | Protect all dashboard routes (middleware) | Unauthenticated -> redirect to login |
| 9.3 | Run Gate 3 (Auth & Security Verification) | All checks pass |
| 9.4 | Set up error tracking (Sentry or Vercel Analytics) | Errors captured |
| 9.5 | Set up uptime monitoring for critical routes | Alerts configured |
| 9.6 | Set up Supabase database alerts (storage, connection count) | Alerts configured |

**Exit criteria:** Auth working, security gates pass, monitoring live.

### Phase 10: Parallel Validation & Cutover

**Entry:** All prior phases complete.

| Step | Action | Exit Evidence |
|------|--------|---------------|
| 10.1 | Run V15 + V16 side by side for 1 week | Both serving, compare outputs daily |
| 10.2 | Run Gate 6 (Parity Verification) — full suite | All parity checks pass |
| 10.3 | Run Gate 4 (Data Flow Verification) — full suite | All data flows verified |
| 10.4 | Freeze V15 changes | No new V15 deploys |
| 10.5 | Switch DNS/routing to V16 | V16 serves production traffic |
| 10.6 | Monitor for 48h | No errors, data fresh, charts correct |
| 10.7 | Keep V15 as rollback for 2 weeks | Rollback available |
| 10.8 | Retire V15 | Archive repo, disable Vercel project |

**Exit criteria:** V16 is production. V15 is archived.

---

## 12. Risk Matrix

### Prioritized Risks

| # | Risk | Likelihood | Impact | Mitigation |
|---|------|-----------|--------|------------|
| **R1** | Chart rendering breaks during clone | Medium | **Critical** | Clone exactly, do not refactor. Test on preview with real data before proceeding. |
| **R2** | Vercel Cron 40-job limit hit | Low | High | 25 routes is well within limit. Monitor count. Consolidate aggressively. |
| **R3** | Supabase connection pooler timeouts during Python training writes | Medium | High | Use direct connection (port 5432) for bulk writes, not pooler. Set `statement_timeout`. |
| **R4** | ProFarmer scraper breaks in Playwright rebuild | Medium | High ($500/mo) | Build Playwright version early. Test against ProFarmer site. Keep V15 scraper as fallback. |
| **R5** | Specialist feature generators produce different signals after rebuild | Medium | High | Validate V16 outputs against V15 outputs row-by-row before training. |
| **R6** | AutoGluon model performance degrades on clean matrix | Medium | Medium | Expected — clean matrix has different features. Retrain and evaluate. Dry run first. |
| **R7** | FRED/Databento/USDA API changes between builds | Low | Medium | Use V15 as reference for API contracts. Check docs before building each cron. |
| **R8** | Supabase RLS blocks legitimate reads | Medium | Medium | Test RLS policies explicitly in Gate 3. |
| **R9** | Vegas Intel data sync breaks (Glide integration) | Low | Medium | Evaluate Glide sync separately. |
| **R10** | Local vs cloud Supabase schema drift | Medium | Medium | Supabase CLI migrations as single source of truth. Never manual DDL. |
| **R11** | Vercel Cron routes timeout (300s max on Pro) | Low | Medium | All routes are light. ProFarmer stays external. Monitor execution times. |
| **R12** | Env variable mismatch between environments | Low | Low | Vercel <> Supabase integration. `vercel env pull` for local. No manual .env copying. |

---

## 13. Highest-Value Validation Steps

Run these first — they reveal architectural problems fastest:

1. **Can Python connect to cloud Supabase and write a row?** If this fails, the entire training pipeline design is blocked.
2. **Does the chart render with seeded data from Supabase?** If this fails, the core product is broken.
3. **Does a single Vercel Cron route fire, fetch data, and write to Supabase?** If this fails, the entire ingestion architecture is wrong.
4. **Does Supabase Auth work with the Chanui template?** If this fails, the auth design needs rework.
5. **Can `build_matrix.py` read from Supabase and assemble features?** If this fails, the Python <> Supabase data flow needs debugging.

---

## 14. Dependency-Aware Remediation Sequence

If something breaks, fix in this order (upstream first):

```
Supabase connectivity
  -> Schema correctness
    -> RLS policies
      -> Seed data
        -> Chart rendering (MOST CRITICAL)
          -> Cron routes (ZL daily first)
            -> FRED/macro crons
              -> Python pipeline
                -> Specialist features
                  -> Training
                    -> Forecasts
                      -> Target Zones
                        -> Dashboard wiring
                          -> Secondary pages
                            -> Auth
                              -> Monitoring
```

---

## Appendix A: V15 Reference Files

These V15 files serve as reference for what V16 must deliver. They are NOT copied — they are studied for contracts and behavior.

### Chart (CLONE — most critical)
- [`frontend/src/components/LightweightZlCandlestickChart.tsx`](frontend/src/components/LightweightZlCandlestickChart.tsx)
- [`frontend/src/lib/charts/ForecastTargetsPrimitive.ts`](frontend/src/lib/charts/ForecastTargetsPrimitive.ts)
- [`frontend/src/lib/charts/PivotLinesPrimitive.ts`](frontend/src/lib/charts/PivotLinesPrimitive.ts)
- [`frontend/src/lib/charts/pivots.ts`](frontend/src/lib/charts/pivots.ts)
- [`frontend/src/hooks/useZlLivePrice.ts`](frontend/src/hooks/useZlLivePrice.ts)

### Landing Page (CLONE)
- [`frontend/src/app/page.tsx`](frontend/src/app/page.tsx)
- [`frontend/src/components/viz/NeuralSphere.tsx`](frontend/src/components/viz/NeuralSphere.tsx)

### Dashboard
- [`frontend/src/app/dashboard/page.tsx`](frontend/src/app/dashboard/page.tsx)
- [`frontend/src/components/StatusBar.tsx`](frontend/src/components/StatusBar.tsx)
- [`frontend/src/components/ChrisTop4Drivers.tsx`](frontend/src/components/ChrisTop4Drivers.tsx)
- [`frontend/src/components/RegimeAnalysisChart.tsx`](frontend/src/components/RegimeAnalysisChart.tsx)

### Pages
- [`frontend/src/app/strategy/page.tsx`](frontend/src/app/strategy/page.tsx)
- [`frontend/src/app/legislation/page.tsx`](frontend/src/app/legislation/page.tsx)
- [`frontend/src/app/sentiment/page.tsx`](frontend/src/app/sentiment/page.tsx)
- [`frontend/src/app/vegas-intel/page.tsx`](frontend/src/app/vegas-intel/page.tsx)

### Brand Assets (KEEP)
- [`frontend/public/logo.svg`](frontend/public/logo.svg)
- [`frontend/public/chart_watermark.svg`](frontend/public/chart_watermark.svg)
- [`frontend/public/ZINC Fusion Icon Transparent (6000 X 3000 Px) (2000 X 2000 Px) - 1.svg`](frontend/public/ZINC%20Fusion%20Icon%20Transparent%20%286000%20X%203000%20Px%29%20%282000%20X%202000%20Px%29%20-%201.svg)
- [`frontend/public/head.glb`](frontend/public/head.glb)

### Shell & Styling
- [`frontend/src/app/layout.tsx`](frontend/src/app/layout.tsx)
- [`frontend/src/components/Header.tsx`](frontend/src/components/Header.tsx)
- [`frontend/src/app/globals.css`](frontend/src/app/globals.css)

### Inngest Estate (reference for what jobs did — NOT for porting)
- [`frontend/src/inngest/functions.ts`](frontend/src/inngest/functions.ts) — barrel export of all functions
- [`frontend/src/app/api/inngest/route.ts`](frontend/src/app/api/inngest/route.ts) — registration hub

### Python Pipeline (reference for what scripts did — NOT for porting)
- [`src/fusion/core_training/config.py`](src/fusion/core_training/config.py) — model zoo
- [`src/fusion/core_training/build_matrix.py`](src/fusion/core_training/build_matrix.py) — feature assembly
- [`src/fusion/core_training/train_models.py`](src/fusion/core_training/train_models.py) — training
- [`scripts/generate_forward_forecasts.py`](scripts/generate_forward_forecasts.py) — inference
- [`scripts/run_monte_carlo.py`](scripts/run_monte_carlo.py) — MC simulation
- [`scripts/run_garch.py`](scripts/run_garch.py) — GARCH
- [`scripts/generate_specialist_features.py`](scripts/generate_specialist_features.py) — specialist features
- [`scripts/generate_specialist_signals.py`](scripts/generate_specialist_signals.py) — specialist signals

## Appendix B: Banned Words & Required Language

### Banned (never use)
- "cones" / "probability cone"
- "confidence band"
- "funnel"
- "cents/lb"
- "10 specialists" (there are 11)

### Required
- "Target Zones" (horizontal price zones)
- "predicted_price" (core output)
- "ZL futures contract price"
- "ZL has an X% chance of hitting XX.XX by [date]"
- "Monte Carlo", "pinball", "MAE/accuracy %"

## Appendix C: Data Source Reference

### Paid Sources
- **ProFarmer** ($500/month) — mandatory, 8,535+ articles
- **Databento** — ZL futures, options, statistics, FX, ETF OHLCV

### Free API Sources
- FRED (130+ series) — rates, inflation, commodities, vol indices
- CFTC — weekly CoT positioning
- USDA FAS — export sales, WASDE
- EIA — biodiesel production
- EPA — RIN credit prices
- NOAA / Open-Meteo — weather
- Federal Register — regulations
- Congress.gov — bills
- White House — executive actions
- Google News — sentiment feed
- CONAB — Brazil crop production
- MPOB — Malaysia palm (needs API key)
- Panama Canal Authority — transit data

### FRED PPI Proxies for UCO/Tallow
- `WPU06410132` — Tallow PPI
- `PCU3116133116132` — Rendering PPI
- Stored in `econ.commodities_1d`, consumed by biofuel specialist
