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

### L0 Core Model Zoo (25 models per horizon, CPU-only)

Defined in `src/fusion/core_training/train_models.py`. No presets, no time limits, explicit allowlist only.

| Category | Models |
|----------|--------|
| Baselines (5) | Naive, SeasonalNaive, Average, SeasonalAverage, Zero |
| Statistical (10) | ETS, AutoETS, AutoARIMA, AutoCES, Theta, DynamicOptimizedTheta, NPTS, ADIDA, Croston, IMAPA |
| Deep/ML (5) | DeepAR, TemporalFusionTransformer, DLinear, PatchTST, SimpleFeedForward |
| Neural (2) | TiDE, WaveNet |
| Tabular TS (3) | DirectTabular, PerStepTabular, RecursiveTabular |
| Pretrained (3, disabled macOS ARM) | Chronos2, Chronos, Toto |

AutoGluon trains all models and selects a WeightedEnsemble. Artifacts in `models/core_v2/{horizon}d/`.

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
