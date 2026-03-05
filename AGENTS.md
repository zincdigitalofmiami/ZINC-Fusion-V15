# ZINC-FUSION-V15 Workspace Guide

---
## 🚨 MANDATORY SESSION STARTUP — NO EXCEPTIONS

Before ANY response, code, or analysis — Claude MUST execute this checklist in order:

1. **Memory MCP** — Search memory for prior decisions, corrections, and architect context relevant to the current task. Query: task keywords + "ZINC-FUSION" + "Kirk".
2. **Plan before acting** — Think through the task step-by-step before making changes.

**If memory MCP is unavailable, explicitly state it and continue with local evidence.**

This is not optional. This is not situational. This runs every session.

---

## What This Project Is

Commodity procurement forecasting system for ZL (soybean oil futures). Core predicts the future ZL futures contract price. L2/L3 calibration layers wrap that price forecast with probability, rendered as **horizontal Target Zones** on the dashboard (e.g. "ZL has an 88% chance of hitting 48.52 by July 7th"). Probability is always derived from three named sources: Monte Carlo (10,000 runs), pinball loss calibration, and MAE/accuracy %. Intelligence only — no execution or trade logic.

**Client:** US Oil Solutions (Las Vegas, NV) — [usoilsolutions.com](https://www.usoilsolutions.com/)

### Client Business Model — READ THIS

**Chris** is the owner. His business:

1. **BUYS raw soybean oil by the trainload** (millions of gallons). This is his PRIMARY cost. When ZL goes up, his input cost rises — **BAD.** When ZL drops, he buys cheaper — **GOOD.** The Strategy page posture language (ACCUMULATE = lock in low prices now, WAIT = prices may soften further) is CORRECT for his buying side.

2. **Delivers fresh cooking oil** to 100+ restaurant kitchens across Las Vegas casinos (Caesars, Boyd Gaming, Resorts World, etc.).

3. **Collects used cooking oil (UCO)** when servicing restaurants (oil changes). He then sells the UCO — likely to biodiesel producers/refiners. This is a SECONDARY revenue stream. When UCO prices rise (which tracks ZL), his collection revenue increases.

So Chris is on BOTH sides of the oil market: he is hurt by rising ZL on the buy side (his biggest cost) but benefits from rising UCO prices on the sell side. Net exposure is primarily as a **BUYER** — the trainloads of raw soy oil dwarf the UCO collection revenue.

**Kevin** is the sales director. He uses the Vegas Intel page to:
- Pitch restaurants on upgrading their oil service / scheduling ahead of big events
- Pre-arrange extra oil deliveries and UCO pickups when convention traffic spikes fryer usage
- Prospect new restaurant accounts (red "PROSPECT" badges)

Kevin's sales pitch: "CES has 170K attendees in 12 days — your fryers will run overtime. Let us pre-schedule extra fresh oil delivery and UCO pickup."

## Tech Stack

- **Database:** Prisma Postgres (cloud-hosted, 12 schemas)
- **Frontend:** Next.js on Vercel with Inngest serverless functions
- **Backend:** Python 3.11, FastAPI, psycopg2
- **ML:** AutoGluon (CPU-only), custom specialist models
- **Package Manager:** uv (Python), npm (`frontend/` + `config/` for Prisma CLI)
- **Testing:** pytest (Python), npm test (frontend)
- **Tracking:** MLflow (local)
- **Local Inngest:** Docker (`docker-compose.inngest.yml`) — required for heavy browser-based scrapers

## Docker Inngest Setup (Required for ProFarmer)

ProFarmer and other browser-based scrapers are too heavy for Vercel serverless. They run via Docker Inngest locally.

```bash
# 1. Start Docker Inngest dev server (port 8288, polls host:3000)
docker compose -f docker-compose.inngest.yml up -d

# 2. Start Next.js dev server (port 3000)
npm --prefix frontend run dev

# 3. Trigger ProFarmer manually
curl -X POST http://localhost:8288/e/test \
  -H "Content-Type: application/json" \
  -d '{"name": "profarmer/daily", "data": {}}'

# Inngest UI: http://localhost:8288
```

`profarmer-daily.ts` auto-detects the runtime via `resolveChromePath()`:
- **Docker/local:** Uses system Chrome (macOS, Linux paths probed automatically)
- **Vercel:** Falls back to `@sparticuz/chromium` (but ProFarmer will timeout — don't rely on this)
- **Override:** Set `PUPPETEER_EXECUTABLE_PATH` env var to force a specific binary

## Repository Layout

- Root (`/`) — Python ML pipeline
- `frontend/` — Next.js dashboard (deployed to Vercel)
- `prisma/schema.prisma` — Database schema (single source of truth)

There is intentionally no root `package.json`.
Prisma CLI dependencies live in `config/package.json`.
All frontend npm commands use `--prefix frontend`; all Prisma CLI commands use `--prefix config` (or `scripts/prisma.sh`).

## Database

Prisma manages schema and migrations only. Runtime queries use `pg` Pool (TypeScript) and psycopg2 (Python). Do not use PrismaClient for runtime queries.

**12 Schemas:** `mkt`, `econ`, `alt`, `pos`, `supply`, `features`, `training`, `model`, `forecasts`, `analytics`, `ops`, `vegas`

**Banned schemas:** `raw`, `gold`, `silver`, `bronze`, `monitoring`, `specialist`, `weather`, `archive`

## Model Architecture

- **L0 Core = PRICE PREDICTOR:** 4 AutoGluon TimeSeriesPredictor ensembles (5d/21d/63d/126d), each training a 19-model zoo. Core predicts ONE number: the future ZL futures contract price. No quantile outputs from core.
- **Specialists:** 11 signal generators (domain-specific, no horizons)
- **L1 Meta:** Core models consume specialist signals as input features (no separate meta-learner)
- **L2/L3 = PROBABILITY ENGINE:** Calibration + Monte Carlo risk (10,000 runs). Takes core's price prediction and wraps it with probability: "ZL has an 88% chance of hitting XX.XX by July 7th." Output rendered as horizontal **Target Zones** on the chart. Probability derived from: Monte Carlo (10k runs) + pinball loss + MAE/accuracy %. Never use: cones, bands, funnels.

### L0 Core Model Zoo (19 active models per horizon, CPU-only)

Defined in `src/fusion/core_training/config.py` → `MODEL_ZOO_FROZEN`. No presets, no time limits, explicit allowlist only.

| Category | Models | Status |
|----------|--------|--------|
| Baselines (5) | Naive, SeasonalNaive, Average, SeasonalAverage, Zero | Active |
| Statistical (10) | ETS, AutoETS, AutoARIMA, AutoCES, Theta, DynamicOptimizedTheta, NPTS, ADIDA, Croston, IMAPA | Active |
| Tabular TS (3) | DirectTabular, PerStepTabular, RecursiveTabular | Active |
| Foundation (1) | Chronos2 (120M-param, zero-shot, covariate-aware) | Active (in MODEL_ZOO_FROZEN — see Correction #5) |
| Deep/ML (7) | DeepAR, TFT, DLinear, PatchTST, SimpleFeedForward, TiDE, WaveNet | Disabled (macOS ARM) |
| Pretrained (2) | Chronos (original), Toto | Disabled |

AutoGluon trains all active models and selects a WeightedEnsemble. Artifacts in `models/core_v2/{horizon}d/`.
Source of truth: `config.py` → `MODEL_ZOO_FROZEN` (frozenset, currently 19 models).

- **Target:** Future ZL futures contract price (`close.shift(-horizon)`), NOT returns. Columns named `target_price_{h}d`.
- **Metric:** MAE (point forecast accuracy). Core optimizes for predicting the price, not a distribution.
- **Output:** Single `predicted_price` per horizon — the core model's price forecast. No quantile columns (p30/p50/p70) from core.
- **Covariates:** All OBSERVED (no known future values)
- **Validation:** 4 expanding windows
- **Frequency:** Business day (`B`)

### Specialist Buckets (Big-11)

Each specialist outputs `(signal_1, signal_2, confidence)` per date to `training.specialist_signals_1d`. These are merged into `training.matrix_1d` as core input features.

| Bucket | Model Type | Implementation | Signal Contract |
|--------|-----------|----------------|-----------------|
| crush | `gbm` | sklearn GradientBoostingRegressor | Crush margin z-score + momentum |
| china | `gbm` | sklearn GradientBoostingRegressor | Demand outlook + Brazil competition |
| substitutes | `rf` | sklearn RandomForestRegressor | Substitution pressure + richness |
| fx | `ardl` | statsmodels ARDL | FX pressure index + carry |
| fed | `ridge` | sklearn Ridge | Rates regime + change |
| tariff | `tree` | Rule-based + EPU analysis | Tariff risk + EPU spike |
| energy | `var` | statsmodels VAR + IRF | Energy spillover + momentum |
| biofuel | `nlp_ema` | NLP sentiment + EMA | Policy pressure + trend |
| palm | `ecm_ridge` | statsmodels ECM + sklearn Ridge | Cointegration + mean reversion |
| volatility | `garch` | arch GJR-GARCH(1,1) | Conditional variance z-score + regime |
| trump_effect | `event_study` | Event intensity scoring | Intensity + volatility impact |

### Data Pipeline

1. **Feature Matrix:** ~213+ features in `training.matrix_1d` (FRED macro, FX, commodity, weather, supply, positioning, specialist signals)
2. **Specialist Signals:** 33 columns (11 buckets x 3: signal_1, signal_2, confidence)
3. **Core Training:** AutoGluon trains on full matrix including specialist signals
4. **OOF Predictions:** Written to `training.oof_core_1d` (`predicted_price` per horizon). These are ZL futures contract prices — not returns. L2/L3 calibration layers then wrap these with probability to produce Target Zones on the dashboard.

### Country-Level Export Data = Geopolitical Signal Layer

USDA FAS Export Sales reports (`supply.usda_exports_1w`) contain **country-level** purchase data for soybeans, soybean oil, and soybean meal. This is NOT just aggregate demand — it is a granular geopolitical intelligence feed.

**Why country-level matters for the model:**
- **Demand shifts by country** are early signals of policy changes. When a country's purchases collapse or spike YoY, it often precedes or coincides with tariffs, sanctions, trade agreements, or domestic regulation.
- **China specialist** directly consumes China's share of soy complex purchases — outstanding sales, accumulated exports, YoY comparison.
- **Trump_effect specialist** can correlate country-level purchase anomalies with lobbying, sanctions, executive orders, and "regulations that don't make sense" — e.g., a country whose imports drop despite no economic reason points to political interference.
- **Crush specialist** uses oil/meal destination flows to understand global crush economics — where is oil going vs. meal vs. beans? Country ratios reveal processing capacity shifts.
- **Tariff specialist** uses bilateral trade flow disruptions as direct signal — when purchases reroute (e.g., China drops, Pakistan/Egypt surge 4x), that's trade diversion from tariff impact.

**Ingestion depth:** Every country in the report is captured with 6 columns: outstanding sales (this week + YoY), accumulated exports (this week + YoY), and next marketing year outstanding. Region subtotals and individual country rows are both stored. Abbreviated country names are resolved to full names via lookup table.

**Source reports:** Soybeans, Soybean Oil, Soybean Meal pages at `apps.fas.usda.gov/export-sales/`

## Data Source Registration Audit

<!-- LAST UPDATED: 2026-02-27 -->

### What build_matrix.py ACTUALLY reads (the ONLY things that reach training)

The core matrix builder (`src/fusion/core_training/build_matrix.py`) has explicit `load_*()` functions for each data source. If a table is NOT listed below, it does NOT reach the core training pipeline, period.

| Loader Function | Source Table(s) | Status |
|----------------|-----------------|--------|
| `load_futures_base()` | `mkt.futures_1d` (ZL, ZS, ZM, etc.) | ✅ Current |
| `load_fred_macro()` | `econ.rates_1d`, `econ.inflation_1d`, `econ.labor_1d`, `econ.activity_1d`, `econ.vol_indices_1d`, `econ.commodities_1d`, `econ.money_1d` | ✅ Current |
| `load_fx_rates()` | `mkt.fx_1d` | ✅ Current |
| `load_spread_features()` | `analytics.board_crush_1d`, `mkt.futures_1d` (cross-commodity) | ✅ Current |
| `load_cross_asset_correlations()` | `mkt.futures_1d` | ✅ Current |
| `load_cross_commodity_indicators()` | `mkt.futures_1d` | ✅ Current |
| `load_options_features()` | `mkt.options_1d` | ⚠️ Table exists but may be empty |
| `load_weather_aggregates()` | `alt.weather_1d` | ✅ Current |
| `load_cftc_positioning()` | `pos.cftc_1w` | ✅ Current |
| `load_epa_rin_prices()` | `supply.epa_rin_1d` | ⚠️ At source limit (Jan 19) |
| `load_usda_exports()` | `supply.usda_exports_1w` | ✅ Current |
| `load_usda_wasde()` | `supply.usda_wasde_1m` | ✅ Current |
| `load_lcfs_credit()` | `supply.lcfs_1d` | ✅ Current |
| `load_china_pmi()` | `econ.activity_1d` (CN PMI) | ✅ Current |
| `load_dalian_soy()` | `mkt.futures_1d` (Dalian) | ✅ Current |
| `load_news_counts()` | `alt.policy_news_event`, `alt.executive_actions_event`, `alt.econ_news_event`, `alt.profarmer_news_event` (UNION ALL → count/day) | ✅ Current |
| `load_specialist_signals()` | `training.specialist_signals_1d` (11 buckets × 3 cols) | ✅ Current |

### Tables WIRED INTO build_matrix.py on 2026-02-27

These were previously missing from the matrix builder and are now wired in:

| Table | Loader Function | Merge Strategy | Status |
|-------|----------------|----------------|--------|
| `mkt.etf_1d` | `load_etf_data()` | Left join on trade_date (12 key ETFs pivoted wide) | ✅ WIRED (46K rows, stale at Feb 2) |
| `alt.legislation_1d` | `load_legislation_events()` | Left join (count/type per day) | ✅ WIRED (2,944 rows, current) |
| `supply.eia_biodiesel_1m` | `load_eia_biodiesel()` | Asof merge (45-day tolerance) | ✅ WIRED (179 rows, at source limit Nov 2025) |

### Tables that STILL need work

| Table | Rows | Issue | Priority |
|-------|------|-------|----------|
| `supply.eia_biodiesel_1w` | 0 | Inngest function registered, backfill triggered 2026-02-27 | P1 |
| `supply.uco_prices_1w` | 0 | Inngest function registered but USDA AMS source unverified | P0 — zero data |

### Inngest functions using SHARED tables (corrected 2026-02-27)

These functions write to existing shared tables — NO new tables needed:

| Function | Target Table | Status |
|----------|-------------|--------|
| `fedSpeechesDaily` | `alt.policy_news_event` | ✅ Shared table (with farmdoc-rins, etc.) |
| `congressBillsDaily` | `alt.legislation_1d` | ✅ Shared table (with federal-register-daily) |

**Previous audit was WRONG** — said these needed `alt.fed_speeches_event` and `alt.congress_bills_event`.
They actually write to existing shared tables. Check env vars: congressBillsDaily requires `CONGRESS_API_KEY`.

### Data Freshness Audit (2026-02-27)

| Table | Max Date | Status |
|-------|----------|--------|
| `mkt.futures_1d` (ZL) | Feb 26 | ✅ Current |
| `mkt.fx_1d` | Feb 26 | ✅ Current |
| `alt.legislation_1d` | Feb 26 | ✅ Current |
| `alt.weather_1d` | Feb 25 | ✅ Current |
| `training.specialist_signals_1d` | Feb 25 | ✅ Current |
| `training.matrix_1d` | Feb 25 | ✅ Current |
| `analytics.board_crush_1d` | Feb 24 | ✅ Current |
| `supply.usda_exports_1w` | Feb 19 | ✅ Weekly cadence |
| `pos.cftc_1w` | Feb 17 | ✅ Weekly cadence |
| `supply.lcfs_1d` | Feb 13 | ⚠️ 2 weeks stale |
| `alt.profarmer_news_event` | Mar 4 | ✅ FIXED 2026-03-03. 8,535 articles. Runs via Docker Inngest (system Chrome). |
| `mkt.etf_1d` | Feb 2 | 🔴 DEAD since Feb 2 (Databento failure). Yahoo fallback created, both backfills triggered. |
| `supply.epa_rin_1d` | Jan 19 | ⚠️ EPA source limit (monthly publishing). Tiered fallback active. |
| `supply.eia_biodiesel_1m` | Nov 2025 | ⚠️ EIA source limit |
| `supply.eia_biodiesel_1w` | — | 🔴 EMPTY. Backfill triggered 2026-02-27. |
| `supply.uco_prices_1w` | — | 🔴 EMPTY. USDA AMS source unverified. |

### Inngest Function Run Audit (Feb 2026)

| Function | Runs | Successes | Failures | Status |
|----------|------|-----------|----------|--------|
| `profarmer-daily` | 74+ | 1 | 37 | ✅ FIXED 2026-03-03. Runs via Docker Inngest (NOT Vercel serverless). |
| `fas-reports-daily` | 2 | 0 | 0 | 🔴 Never succeeded |
| `nass-weekly` | 2 | 1 | 0 | ⚠️ Last success Feb 6 |
| `fred-daily-*` (all) | ~500 | ~450 | 0 | ✅ Running |
| `federal-register-daily` | 44 | 17 | 0 | ⚠️ Low success rate (39%) |
| `epa-rin-prices-daily` | 33 | 30 | 0 | ✅ Running (source limited) |
| `cftc-weekly` | 3 | 2 | 0 | ✅ Running |
| `usda-export-sales-weekly` | 4 | 4 | 0 | ✅ Running |

### Docker Inngest Runtime Audit (2026-03-03)

Local Docker runtime inspection (`inngest-dev` container, `/dev` endpoint + logs):

| Check | Observation |
|-------|-------------|
| Runtime registration | 133 functions total: 108 `fusion-jobs-*` + 25 `rabid-raccoon-*` |
| Sync URLs | `http://host.docker.internal:3000/api/inngest` and `http://host.docker.internal:3001/api/inngest` |
| Step URI routing | 108 functions target port `3000`, 25 functions target port `3001` |
| Host listeners | Port `3000` had no listener; port `3001` had active Node listener |
| Log health (last 2h at audit time) | `Unable to reach SDK URL=67`, `status 401=4`, `received_event=89`, `initializing_fn=34` |
| Highest recent impacted fusion jobs | `global-failure-monitor`, `biofuel-rss-daily`, `zl-15m`, `zl-1h`, `palm-multi-source-daily`, `databento-statistics-daily-shard-6`, `databento-options-daily-shard-6` |
| Compose drift | `docker compose -f docker-compose.inngest.yml ps` showed no running service while `inngest-dev` was running separately (not compose-managed) |

**Operational implication:** Docker Inngest was scheduling fusion jobs, but fusion handlers on `:3000` were unreachable during the audit window, so scheduled runs repeatedly failed at delivery time.

### ProFarmer data usage

ProFarmer articles are in `alt.profarmer_news_event` and ARE included in the matrix — but ONLY as a daily article **count** (via `load_news_counts()` UNION ALL). The actual article content, sentiment, and section routing are NOT used by the matrix builder. The specialist signal generators (`generate_specialist_features.py`) DO use ProFarmer content for the crush, china, energy, biofuel, and tariff specialists through separate loaders.

## Specialist Signal Generators — What They Actually Are

<!-- LAST UPDATED: 2026-02-27 -->

**CRITICAL TRUTH: The specialists are NOT properly trained ML models.** They are pre-baked feature engineering pipelines with hardcoded model types. Running `generate_specialist_features.py` + `generate_specialist_signals.py` is feature engineering, NOT training.

**What "training" the specialists actually means today:**
1. `generate_specialist_features.py` — Queries hand-picked features per domain from the DB, writes to `training.specialist_features_{bucket}`
2. `generate_specialist_signals.py` — Applies pre-baked models (GBM, Ridge, GARCH, etc.) with hardcoded hyperparameters to produce `(signal_1, signal_2, confidence)` per day, writes to `training.specialist_signals_1d`

**What they should be (from plan `foamy-spinning-steele.md`):**
- 5-fold cross-validation with 3600s/fold training time
- Leakage-proof calibration (fit on odd folds, evaluate on even)
- Purge/embargo from label overlap geometry
- IC-priority hierarchical correlation dedup
- Feature selection stability tracking
- Full reproducibility manifest

**The REAL training** happens in the core pipeline: `python -m fusion.core_training.run_pipeline` → Phase 3 (build ~1,487-feature matrix) → Phase 6 (AutoGluon 19-model ensemble) → Phase 7 (promote OOF to production).

## Pipeline Execution — How To Actually Run Things

<!-- LAST UPDATED: 2026-02-27 -->

### The CORRECT way to train (core pipeline)
```bash
# Full pipeline: matrix build → train → promote forecasts
.venv/bin/python -m fusion.core_training.run_pipeline

# Skip matrix rebuild (if matrix is current)
.venv/bin/python -m fusion.core_training.run_pipeline --skip-matrix
```

### The CORRECT way to generate specialist signals
```bash
# Features first, then signals. Must use --start-date or defaults are too narrow.
.venv/bin/python scripts/generate_specialist_features.py --bucket all --start-date 2025-01-01
.venv/bin/python scripts/generate_specialist_signals.py --bucket all --start-date 2025-01-01
```

### Scripts that are WRONG / misleading
- `scripts/populate_core_matrix.py` — lightweight 25-column script, NOT the real matrix builder. The real builder is `src/fusion/core_training/build_matrix.py` (3,259 lines, 1,487 features). **DO NOT USE populate_core_matrix.py.**

### Last successful pipeline run (2026-02-27)
- Matrix: 1,487 features, 7,976 rows
- Horizons: 5d, 21d, 63d, 126d
- All 11 specialist buckets passed data gate
- All 4 horizons trained via AutoGluon
- Production forecasts promoted
- Run hash: `2c189bf007b936c4`

## Claude Hard-Coded Corrections (DO NOT REPEAT THESE ERRORS)

<!-- LAST UPDATED: 2026-02-27 -->

These are verified facts burned in from architect corrections. Claude must never contradict these.

### 1. Specialist Count: ALWAYS 11, NEVER 10
The Big-11 specialists are: crush, china, fx, fed, tariff, energy, biofuel, palm, volatility, substitutes, **trump_effect**.
`trump_effect` (event_study model) is the 11th. It is real, it is active, it matters — especially in current tariff/trade environment.
Any code, doc, or statement that says "10 specialists" is WRONG.
Source of truth: `src/fusion/specialists/base.py` → `SPECIALIST_BUCKETS` list (11 items).

### 2. Core = Price Predictor, Probability = L2/L3 (FIXED 2026-02-19)

**Core Architecture (locked):**
- Core outputs a single `predicted_price` per horizon — the ZL futures contract price forecast.
- Core metric: **MAE** (point forecast accuracy). NOT WQL.
- Core does NOT produce quantiles. No p30/p50/p70 from core. No `quantile_levels` in core config.
- OOF table (`training.oof_core_1d`) stores `predicted_price` and `target_value` — both are ZL futures prices.

**Probability comes from L2/L3 calibration layers:**
- Takes core's `predicted_price` as input.
- Monte Carlo (10,000 runs) + pinball loss + MAE/accuracy % produce probability ranges.
- These become the **Target Zones** on the dashboard.

**Banned words (never use these):**
- **"cones"** — banned. Do not use. Ever. For anything.
- **"probability cone"** — banned.
- **"confidence band"** — banned.
- **"cents/lb"** — banned. Use "ZL futures contract price" or just "price."

**Correct visualization language:**
- The forecast output renders as **horizontal "Target Zones"** on the chart — price levels, not shapes or bands.
- These are implemented as horizontal lines at key price levels, visually similar to support/resistance levels on a trading chart (see: MES1 15m chart reference with orange/gray horizontal lines).
- NOT a wedge, NOT a funnel, NOT a cone. Flat horizontal zones at discrete price levels.

**Correct probability language (for chart UI and stakeholder-facing copy):**
- "ZL has an 88% chance of hitting XX.XX by July 7th" — this is the approved phrasing.
- Probability is derived from: Monte Carlo simulation + pinball loss calibration + MAE/accuracy %.
- The three sources of that probability statement are always: (1) Monte Carlo (10,000 runs), (2) pinball loss score, (3) MAE/accuracy %.
- These three terms — **Monte Carlo, pinball, MAE/accuracy %** — are the approved chart/app language.

**Correct language summary:**
- ✅ "Target Zones"
- ✅ "predicted_price" (core output)
- ✅ "ZL futures contract price"
- ✅ "ZL has an X% chance of hitting XX.XX by [date]"
- ✅ "Monte Carlo", "pinball", "MAE/accuracy %"
- ❌ "cones", "probability cone", "confidence band", "funnel", "cents/lb"

### 3. Target Is ZL Futures Price, NOT Returns (FIXED 2026-02-19)
- `create_target_columns()` in `build_matrix.py` uses `close.shift(-horizon)` — the actual future ZL futures contract price.
- Target columns are named `target_price_{h}d` (NOT `target_ret_*`).
- The core model predicts the ZL futures price. L2/L3 wraps it with probability for Target Zones.
- Never revert to `pct_change()` returns — price targets align with Chronos2 pretraining, procurement use case, and Target Zone visualization.
- **Why this matters:** Core output `predicted_price=48.52` means "ZL will be at 48.52." L2/L3 adds "88% chance by July 7th." If the target were returns, the core output would be a meaningless percentage.

### 4. Raw Crush Features ≠ Crush Specialist Output
- `board_crush`, `soy_oil_share`, `zl_cl_ratio`, etc. in the matrix come from `analytics.board_crush_1d` via `load_spread_features()` in `build_matrix.py`. These are RAW inputs.
- The crush specialist's GBM output — `sig_crush_1`, `sig_crush_2`, `sig_crush_conf` — is a separate processed signal written to `training.specialist_signals_1d`.
- The dry run matrix had raw crush features but NO specialist signals (table was empty).
- Never conflate the two.

### 5. Chronos2 Is in MODEL_ZOO_FROZEN and IS Active (Table Above Has Been Corrected)
- `config.py` `MODEL_ZOO_FROZEN` includes Chronos2 — it ran in the dry run.
- The model zoo table above now correctly lists Chronos2 as Active. The previous version of this table was wrong — that error is fixed.
- The `config.py` frozen set is the source of truth for what actually trains.
- Chronos2 underperforms on this system because: (a) all covariates are OBSERVED not KNOWN, (b) single item_id = no cross-learning, (c) CPU-only on macOS ARM. Note: target is ZL futures price (not returns), which better aligns with Chronos2 pretraining.

### 6. The Dry Run Context
- The leaderboard results shared were a DRY RUN with NO specialist signals and a dropped/fresh matrix.
- It was a mechanics validation, not a performance benchmark for the full system.
- The dry run used the OLD config (WQL metric, returns target, quantile outputs). All three are now fixed: MAE metric, price target, single predicted_price output.
- Do not compare dry run numbers to the full system's expected performance.

### 7. Biofuel Specialist min_periods Bug (FIXED 2026-02-27)
- `src/fusion/specialists/events/biofuel.py` had `compute_zscore(rin_series, window=126, min_periods=42)` on **weekly** EPA RIN data
- Weekly data = ~18 observations per 126 calendar days → never reaches 42 min_periods → always NaN → 0 signals
- **Fixed**: Changed `min_periods=42` → `min_periods=12` (≈3 months of weekly data)
- This was the reason biofuel specialist always produced 0 signals

### 8. populate_core_matrix.py Is WRONG (DISCOVERED 2026-02-27)
- `scripts/populate_core_matrix.py` is a lightweight 25-column script that uses wrong column names (`as_of_date` instead of `trade_date`, `target_5d` instead of `target_ret_5d`)
- The REAL matrix builder is `src/fusion/core_training/build_matrix.py` (3,259 lines, 1,487 features)
- Run `python -m fusion.core_training.run_pipeline` for the real pipeline. NEVER use `populate_core_matrix.py`.

### 10. ProFarmer Scraper: Full Fix History (RESOLVED 2026-03-03)
- **Dead Feb 15 → Mar 3** due to Turbopack tree-shaking breaking puppeteer-extra transitive deps
- Error chain: `is-plain-object` → `kind-of` → `fs-extra` (each fixed incrementally)
- `next.config.ts`: 23 entries in `serverExternalPackages` + 22 glob patterns in `outputFileTracingIncludes`
- Vercel serverless STILL times out even with modules fixed (browser launch + login + 7 sections too heavy for 60s/300s)
- **Final solution: Docker Inngest** — `resolveChromePath()` in `profarmer-daily.ts` detects runtime:
  1. `PUPPETEER_EXECUTABLE_PATH` env var → Docker/CI override
  2. System Chrome probing → macOS, Debian, Alpine, Linux paths
  3. `@sparticuz/chromium` → Vercel fallback only (kept for non-browser Inngest functions)
- **ProFarmer MUST run via Docker Inngest, NOT Vercel.** Do not suggest "Vercel redeploy" for ProFarmer.
- Manual trigger: `curl -X POST http://localhost:8288/e/test -H "Content-Type: application/json" -d '{"name": "profarmer/daily", "data": {}}'`
- Docker Inngest setup: `docker compose -f docker-compose.inngest.yml up -d` (port 8288, polls host:3000)

### 9. Specialist "Training" Is NOT Real Training (DISCOVERED 2026-02-27)
- Running `generate_specialist_features.py` + `generate_specialist_signals.py` is **feature engineering**, not ML training
- The specialists use pre-baked models with hardcoded hyperparameters — no cross-validation, no hyperparameter search, no model persistence
- Real training only happens in the core pipeline (AutoGluon Phase 6)
- Plans exist to properly train specialists (5-fold CV, purge/embargo, calibration) but are NOT yet implemented

## Core Rules

1. No fabrication — never invent schemas, tables, files, or endpoints
2. No execution logic — intelligence only, no buy/sell/act
3. No silent schema changes — declare and get approval
4. Read before editing — always read files before modifying
5. Verify before claiming done — lint, test, re-read
6. Minimal changes — fix root causes, avoid unrelated refactors
7. Forward fill is OFF by default — requires explicit approval
8. Say "I don't know" when uncertain
9. Before pushing, open a PR to trigger cubic PR review — fix all P0/P1 issues before merging (cubic CLI requires paid plan; PR reviews work on free open source plan)

## MCP Server Rules (Workspace-Only — `.vscode/mcp.json`)

One MCP server is configured for this workspace: **memory**. All agents must follow these rules without exception.

### 8 Non-Negotiable Rules

1. **THINK FIRST** — Must plan before writing any code. No exceptions.
2. **MEMORY FIRST** — Must check memory at conversation start, must store decisions immediately during conversation.
3. **SOURCE CHECK FOR DOCS** — No relying on stale assumptions for external APIs; verify against current primary docs when needed.
4. **NO GOING ROGUE** — No unrequested changes, no surprise refactors, no "while I'm here" improvements.
5. **CONFIRM DESTRUCTIVE ACTIONS** — Must state intent and wait before deleting, overwriting, migrating, etc.
6. **ONE TASK AT A TIME** — Finish what was asked before touching anything else.
7. **REPORT** — State every file touched and every change made.
8. **NO GUESSING** — Don't know? Say so. Check memory and ask Kirk.

### Mandatory Execution Order

Every task follows this sequence:

```
Memory(search) → Plan → Execute → Memory(store) → Report
```

- **Memory search** — Check the knowledge graph for prior decisions, corrections, and context before doing anything.
- **Plan** — Work the approach step-by-step. No cowboying.
- **Execute** — Implement the plan. One task at a time.
- **Memory store** — Persist any new decisions, corrections, or architectural facts to the knowledge graph immediately.
- **Report** — List every file touched, every change made, every decision taken.
