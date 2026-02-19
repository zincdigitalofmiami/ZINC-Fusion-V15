# ZINC-FUSION-V15 Workspace Guide

## What This Project Is

Commodity procurement forecasting system for bulk soybean oil (ZL). Provides probabilistic multi-horizon forecasts (1W/1M/3M/6M) to support procurement timing and hedging decisions. Intelligence only — no execution or trade logic.

**Client:** US Oil Solutions

## Tech Stack

- **Database:** Prisma Postgres (cloud-hosted, 12 schemas)
- **Frontend:** Next.js on Vercel with Inngest serverless functions
- **Backend:** Python 3.11, FastAPI, psycopg2
- **ML:** AutoGluon (CPU-only), custom specialist models
- **Package Manager:** uv (Python), npm (`frontend/` + `config/` for Prisma CLI)
- **Testing:** pytest (Python), npm test (frontend)
- **Tracking:** MLflow (local)

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

- **L0 Core:** 4 AutoGluon TimeSeriesPredictor ensembles (5d/21d/63d/126d), each training a 25-model zoo
- **Specialists:** 11 signal generators (domain-specific, no horizons)
- **L1 Meta:** Core models consume specialist signals as input features (no separate meta-learner)
- **L2/L3:** Calibration + Monte Carlo risk (VaR/CVaR)

### L0 Core Model Zoo (19 active models per horizon, CPU-only)

Defined in `src/fusion/core_training/config.py` → `MODEL_ZOO_FROZEN`. No presets, no time limits, explicit allowlist only.

| Category | Models | Status |
|----------|--------|--------|
| Baselines (5) | Naive, SeasonalNaive, Average, SeasonalAverage, Zero | Active |
| Statistical (10) | ETS, AutoETS, AutoARIMA, AutoCES, Theta, DynamicOptimizedTheta, NPTS, ADIDA, Croston, IMAPA | Active |
| Tabular TS (3) | DirectTabular, PerStepTabular, RecursiveTabular | Active |
| Foundation (1) | Chronos2 (120M-param, zero-shot, covariate-aware) | Active |
| Deep/ML (7) | DeepAR, TFT, DLinear, PatchTST, SimpleFeedForward, TiDE, WaveNet | Disabled (macOS ARM) |
| Pretrained (2) | Chronos (original), Toto | Disabled |

AutoGluon trains all active models and selects a WeightedEnsemble. Artifacts in `models/core_v2/{horizon}d/`.
Source of truth: `config.py` → `MODEL_ZOO_FROZEN` (frozenset, currently 19 models).

- **Target:** Future PRICE LEVEL (`close.shift(-horizon)`), NOT returns
- **Metric:** WQL (Weighted Quantile Loss)
- **Quantiles:** [0.3, 0.5, 0.7]
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
4. **OOF Predictions:** Written to `training.oof_core_1d` (p30, p50, p70 per horizon)

## Claude Hard-Coded Corrections (DO NOT REPEAT THESE ERRORS)

<!-- LAST UPDATED: 2026-02-19 by Kirk (architect) -->

These are verified facts burned in from architect corrections. Claude must never contradict these.

### 1. Specialist Count: ALWAYS 11, NEVER 10
The Big-11 specialists are: crush, china, fx, fed, tariff, energy, biofuel, palm, volatility, substitutes, **trump_effect**.
`trump_effect` (event_study model) is the 11th. It is real, it is active, it matters — especially in current tariff/trade environment.
Any code, doc, or statement that says "10 specialists" is WRONG.
Source of truth: `src/fusion/specialists/base.py` → `SPECIALIST_BUCKETS` list (11 items).

### 2. Quantiles, Visualization, and Probability Language — Full Spec

**Quantile Schema (locked):**
- Core OOF schema columns: `p30`, `p50`, `p70` — these are the forecast distribution.
- `QUANTILES = [0.3, 0.5, 0.7]` in `config.py` — locked, do not change.
- P10 / P90 exist ONLY as outlier bounds in the Monte Carlo L3 risk layer.

**Banned words (never use these):**
- **"cones"** — banned. Do not use. Ever. For anything.
- **"probability cone"** — banned.
- **"confidence band"** — banned.

**Correct visualization language:**
- The forecast output renders as **horizontal "Target Zones"** on the chart — price levels, not shapes or bands.
- These are implemented as horizontal lines at key price levels, visually similar to support/resistance levels on a trading chart (see: MES1 15m chart reference with orange/gray horizontal lines).
- NOT a wedge, NOT a funnel, NOT a cone. Flat horizontal zones at discrete price levels.

**Correct probability language (for chart UI and stakeholder-facing copy):**
- "X% probability of this price area in N months" — this is the approved phrasing.
- Probability is derived from: Monte Carlo simulation + pinball loss calibration + MAE/accuracy %.
- Example approved phrase: "72% probability ZL trades in the 48–52 range within 6 months"
- The three sources of that probability statement are always: (1) Monte Carlo (10,000 runs), (2) pinball loss score, (3) MAE/accuracy %.
- These three terms — **Monte Carlo, pinball, MAE/accuracy %** — are the approved chart/app language.

**Correct language summary:**
- ✅ "Target Zones"
- ✅ "P30/50/70 forecast distribution"
- ✅ "P10/P90 outlier bounds (Monte Carlo)"
- ✅ "X% probability of this price area in N months"
- ✅ "Monte Carlo", "pinball", "MAE/accuracy %"
- ❌ "cones", "probability cone", "confidence band", "funnel"

### 3. Target Is Price Level, NOT Returns (FIXED 2026-02-19)
- `create_target_columns()` in `build_matrix.py` uses `close.shift(-horizon)` — the actual future price of ZL.
- Target columns are named `target_price_{h}d` (NOT `target_ret_*`).
- The model predicts PRICE LEVELS in cents/lb — directly usable as Target Zones on the dashboard.
- Never revert to `pct_change()` returns — price-level targets align with Chronos2 pretraining, procurement use case, and Target Zone visualization.

### 4. Raw Crush Features ≠ Crush Specialist Output
- `board_crush`, `soy_oil_share`, `zl_cl_ratio`, etc. in the matrix come from `analytics.board_crush_1d` via `load_spread_features()` in `build_matrix.py`. These are RAW inputs.
- The crush specialist's GBM output — `sig_crush_1`, `sig_crush_2`, `sig_crush_conf` — is a separate processed signal written to `training.specialist_signals_1d`.
- The dry run matrix had raw crush features but NO specialist signals (table was empty).
- Never conflate the two.

### 5. Chronos2 Is in MODEL_ZOO_FROZEN (Active) Despite AGENTS.md Table Listing It as Disabled
- `config.py` `MODEL_ZOO_FROZEN` includes Chronos2 — it ran in the dry run.
- AGENTS.md model zoo table incorrectly lists Chronos2 under "disabled macOS ARM".
- The `config.py` frozen set is the source of truth for what actually trains.
- Chronos2 underperforms on this system because: (a) all covariates are OBSERVED not KNOWN, (b) single item_id = no cross-learning, (c) target is currently returns not price (mismatch with pretraining), (d) CPU-only on macOS ARM.

### 6. The Dry Run Context
- The leaderboard results shared were a DRY RUN with NO specialist signals and a dropped/fresh matrix.
- It was a mechanics validation, not a performance benchmark for the full system.
- WeightedEnsemble WQL of -0.747 (5d) / -0.709 (21d) is the FLOOR — Core alone, blind, no specialists.
- Do not compare these numbers to the full system's expected performance.

## Core Rules

1. No fabrication — never invent schemas, tables, files, or endpoints
2. No execution logic — intelligence only, no buy/sell/act
3. No silent schema changes — declare and get approval
4. Read before editing — always read files before modifying
5. Verify before claiming done — lint, test, re-read
6. Minimal changes — fix root causes, avoid unrelated refactors
7. Forward fill is OFF by default — requires explicit approval
8. Say "I don't know" when uncertain
9. Before committing, run `cubic review` to catch bugs — fix all P0/P1 issues before pushing
