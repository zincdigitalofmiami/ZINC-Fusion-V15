NOTE: Production is the dashboard/frontend, not the repo root.
# ZINC Fusion V15 - Soybean Oil Procurement Forecasting
Forward fill policy: [Docs/FORWARD_FILL_POLICY.md](Docs/FORWARD_FILL_POLICY.md)


**Institutional-grade quantitative forecasting system for US Oil Solutions**

This project implements a multi-layer ensemble ML pipeline that produces probabilistic multi-horizon forecasts for ZL (Soybean Oil) (5d, 21d, 63d, 126d). **Specialists do not produce horizon forecasts** — they are **custom signal generators** (horizon-agnostic) that feed Core and the meta-learner.

## Latest Update (January 2026): SoT v2 Production Ready

**Hierarchical ensemble now in production**

- **L0 Core**: AutoGluon TimeSeriesPredictor per horizon (CPU-only, full Model Zoo allowlist)
- **L0 Specialists**: 11 specialist signal generators (unchanged)
- **L1 Meta**: 4 stacking ensemble models combining OOF predictions
- **L2 Calibration**: CQR (Conformalized Quantile Regression) for outer envelopes
- **L3 Risk Engine**: Monte Carlo simulation for VaR/CVaR metrics

## Table of Contents

- [Introduction](#introduction)
- [Architecture](#architecture)
- [Getting Started](#getting-started)
- [Data Pipeline](#data-pipeline)
- [Model Training](#model-training)
- [Development](#development)
- [Testing](#testing)

## Introduction

**ZINC Fusion V15** is a 5-layer hierarchical ensemble forecasting system:

- **L0 Layer**: Core (AutoGluon Model Zoo per horizon) + 11 specialist signal generators
- **L1 Layer**: Meta-learner combining OOF predictions from L0 models
- **L2 Layer**: Ensemble fusion producing probabilistic forecasts (P30-P70)
- **L3 Layer**: Calibration via CQR for outer envelope (P10-P90)
- **L4 Layer**: Monte Carlo simulation for risk metrics (VaR, CVaR)

### Key Features

- **Big-11 Bucket Taxonomy**: Domain-specific specialists for Crush, China, FX, Fed, Tariff, Energy, Biofuel, Palm, Volatility, Substitutes, Trump Effect
- **Prisma Postgres**: Cloud-hosted authoritative database for all training and operations
- **Data Pipeline**: Historical backfill (complete) + Yahoo Finance daily topfill + FRED macro indicators

### Business Impact

- **Client**: US Oil Solutions (Las Vegas, NV)
- **Product**: Bulk soybean oil for restaurant/casino fryers
- **Proven Results**: $250K cost avoidance achieved through strategic timing
- **Decision Support**: WHEN to lock in futures, HOW MUCH to buy

## Architecture

### Price Impact Scenarios v2: Independent Axes + Training Model Structures (Source of Truth)

**Status**: Canonical scope for dev build-out (new training models + scenario engine)

**Core principle**: Model reality, don't moralize it.

**Quantile policy**: Train P30/P50/P70 everywhere; compute outer envelope P10/P90 via calibration (coverage-truth), not vibes.

### 1) Core Mission and "2+2=22" doctrine

#### Mission (what we ship)

1. Predict events before they happen (e.g., Brazilian drought in 18 days: 68% probability)
2. Assign probabilities to events (e.g., EPA mandate passage: 82% likely)
3. Wire event probabilities into the **signal layer** (L0 Specialists) and optionally into Core as features
4. Generate probability-weighted price forecasts (baseline vs scenario vs mixture)
5. Show both on dashboard: predicted events + price impacts

#### "2+2=22" (why we win)

We don't win by "drought → price up." We win by intrinsic connection discovery:

- cross-correlation lead/lag
- cascades (event A → B → C → price)
- non-linear interactions (drivers-of-drivers)
- regime conditioning (same shock behaves differently under different policy/vol regimes)

### 2) Data contracts and time keys (non-negotiable)

#### Time keys

- **Raw**: `event_date` (or `event_time` for sub-daily) is canonical.
- **Training matrices**: `trade_date` is canonical (daily bar alignment).
- **Signals + forecasts**: `as_of_date` is canonical (what we knew/produced *as of* that date).
- **Forecast target date**: production forecast tables also carry `forecast_date` (the date being predicted).

This prevents PIT leakage and "silent join death."

#### Mixed frequency handling (weekly/monthly in daily matrix)

Forward-fill slow series with staleness encoding (age days, release day flags, delta-on-release). This allows daily training while preserving information arrival timing.

### 3) Model Architecture: Core + Specialists + Meta stack

#### Horizons

H ∈ {5, 21, 63, 126} days. Each horizon has its own self-contained stack (direct multi-step; no recursive horizon mixing).

#### Quantiles

- **Train (all models)**: `quantile_levels = [0.30, 0.50, 0.70]`
- **Publish**: p30/p50/p70 + calibrated p10_cal/p90_cal

AutoGluon TimeSeriesPredictor supports custom quantiles via `quantile_levels`.

#### L0: Base models (Core + Specialists)

**L0 Core (per horizon)**

- Model: AutoGluon TimeSeriesPredictor (CPU-only, explicit full Model Zoo allowlist)
- Output: probabilistic multi-step forecasts (quantiles)
- Selection: AutoGluon trains many models and selects/ensembles the best on validation

**L0 Specialists (11 total)**

- Model: Custom domain signal generators (see `src/fusion/specialists/`)
- Targets: signals only (Core owns horizons)

**The 11 Specialists**: CRUSH, CHINA, FX, FED, TARIFF, ENERGY, BIOFUEL, PALM, VOLATILITY, SUBSTITUTES, TRUMP_EFFECT

#### L1: Meta-learner (1 per horizon; 4 total)

**Purpose**: learn when to trust each base model (Core + Specialists) for horizon H.

**Input matrix (per horizon)**:

- Core OOF quantiles + specialist signals
- `core_p30/p50/p70`
- `{specialist}_signal_1`, `{specialist}_signal_2` (optional), `{specialist}_confidence` (optional)
- minimal regime/calendar features

**OOF integrity (hard rule)**: Meta must train on out-of-fold predictions from base models to avoid leakage.

#### L2: Calibration (per horizon; 4 modules)

**Goal**: provide a truthful outer risk envelope without distorting the central band.

**Method**: Conformalized Quantile Regression (CQR) - combines quantile regression with conformal prediction to achieve finite-sample coverage under exchangeability while adapting interval width to heteroskedasticity.

**Outputs**:

- Central: p30/p50/p70 (model-native)
- Outer: p10_cal/p90_cal (calibrated interval)

**Monotonic repair**: Enforce p10_cal ≤ p30 ≤ p50 ≤ p70 ≤ p90_cal (quantile crossing guardrail).

#### L3: Risk Engine (per horizon; 4 modules)

**Purpose**: barrier probabilities, time-to-touch, scenario path sampling, VaR/CVaR-like summaries.

### 4) Intrinsic Connection Discovery and Event Probability Layer

#### 4.1 Event probabilities (daily artifact)

Table: `analytics.event_probabilities_1d`

- `trade_date`, `event_type`, `window_start`, `window_end`
- `p_event`, `severity_score`, `confidence`
- `drivers_topk` (JSON)

#### 4.2 "Neural" discovery modules (minimum viable)

- Lead/lag scanner (correlation over lag grid; significance via permutation/surrogates)
- Cascade model (event graph: A → B → C → price)
- Nonlinear mapping (interaction terms and regime-conditioned relationships)

Product output: "what predicts what," with lags and confidence.

#### 4.3 Wiring into models

Event probabilities become first-class features in L0 Specialists (and optionally Core), e.g.:

- `p_brazil_drought_21d`, `severity_brazil_drought`
- `p_epa_mandate_pass_21d`, `days_to_epa_vote`
- `p_china_quota_shift_next_q`
- `shipping_cost_change_14d`

### 5) Price Impact Scenarios v2: Independent Axes

**Design rule**: axes are independent overlays (no combinatorial explosion). Each axis produces baseline + shock distributions, and can be toggled separately.

#### 5.1 Core scenario artifact (per horizon H)

Table: `analytics.price_scenarios_{H}d_1d` with:

- `trade_date`, `axis` (EVENTS | TRUMP_EFFECT | VOLATILITY | POLICY)
- `scenario_name` (BASELINE / SHOCK / etc.)
- `p_scenario` (optional, recommended)
- `p30/p50/p70`, `p10_cal/p90_cal`
- `drivers_topk` (JSON)

#### 5.2 Scenario math (mixture, not hand-waving)

When you "blend" scenario forecasts, you are forming a mixture distribution. Mixture quantiles generally do not have a closed form; compute via mixture CDF inversion or sampling. Implementation default: sampling-based mixture using the same MC engine (fast, robust).

**A) EVENTS axis**: Baseline vs event shocks layer

**B) TRUMP_EFFECT axis**: Policy uncertainty level, action intensity, category focus

**C) VOLATILITY axis**: Implied-vol regime proxies (VIX, ZL IV)

**D) POLICY axis**: Trade-policy pressure independent of personality

### 6) Monte Carlo settings (optimal + bonus)

**Production default (optimal)**:

- N = 5,000
- Variance reduction ON (randomized low-discrepancy sampling, antithetic variates)

**Regime escalation**:

- elevated/high shock regimes → N = 10,000
- crisis → N = 20,000 (if needed for tail stability)

### 7) Tables and artifacts

#### Training tables

| Table | Purpose |
|-------|---------|
| `training.matrix_1d` | Core features + `target_{H}d` |
| `training.specialist_features` | Specialist input features |
| `training.oof_core_1d` | Core OOF with `horizon_days` column |
| `training.specialist_signals_1d` | Specialist signals (signal_1/signal_2/confidence) |
| `training.meta_inputs_1d` | Core OOF + specialist signals + regime/calendar + `target_{H}d` |

#### Output tables

| Table | Purpose |
|-------|---------|
| `forecasts.production_{H}d_1d` | Production forecasts per horizon |
| `analytics.price_scenarios_{H}d_1d` | Scenario distributions |
| `ops.training_runs` | Training run tracking |

### 8) Training workflow (dependency order)

1. Build daily training matrices (PIT-correct + staleness encoding)
2. Build targets `target_{H}d`
3. Train Core_H (H ∈ {5,21,63,126})
4. Generate 11 specialist signals (no horizons)
5. Persist Core OOF + specialist signals
6. Build meta input tables per horizon
7. Train Meta_H per horizon
8. Run L2 CQR calibration → p10_cal/p90_cal
9. Run L3 risk engine (MC)
10. Build scenario overlays (EVENTS, TRUMP_EFFECT, VOLATILITY, POLICY)
11. Publish forecasts + scenario artifacts for dashboard

### 9) Validation gates (training doesn't "pass" without these)

**Probabilistic quality**:

- Quantile loss / coverage checks on p30/p70 (≈40% empirical)
- Calibrated envelope coverage on p10_cal/p90_cal (≈80% empirical) via conformal/CQR

**Stacking sanity**: Meta must use OOF features only; avoid leakage per stacking practice.

**Regime-block CV + embargo**: Folds are era/regime blocks (politics/crisis/macro eras) with embargo window around fold boundaries.

### 10) Dashboard spec (for Chris)

For each horizon:

1. Event probabilities (what might happen + when + probability)
2. Price impact scenarios (BASELINE + shock overlays by axis)
3. Two cones on chart:
   - primary: P30–P70
   - outer: P10_cal–P90_cal (lighter)
4. Scenario mixture: probability-weighted blended forecast (computed as mixture, not averaged quantiles)

---

## SoT v2: Model Plan + Code Location

SoT v2 model catalog + naming (Core + Specialists + Meta):

- `scripts/v2_training/MODEL_CATALOG.md`
- `scripts/v2_training/README.md`

## Getting Started

### Prerequisites

- Python 3.10-3.14
- [uv](https://docs.astral.sh/uv/) package manager (recommended)

### Installation

```bash
# Clone the repository
git clone https://github.com/zincdigitalofmiami/ZINC-Fusion-V15.git
cd ZINC-Fusion-V15

# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies
uv pip install -e ".[dev]"
```

### Running the API

Start the FastAPI server:

```bash
python -m uvicorn fusion.api.server:app --host 0.0.0.0 --port 8000
```

### Database Setup

**Prisma Postgres** is the authoritative database. Connection via `DATABASE_URL` in `.env`.

```bash
# Pull current schema
npx prisma db pull

# Generate client
npx prisma generate
```

## Data Pipeline

All data operations use Prisma Postgres. Key tables:

- `mkt.futures_1d` - ZL, ZS, ZM, CL futures OHLCV
- `econ.rates_1d`, `econ.activity_1d`, `econ.commodities_1d`, `econ.vol_indices_1d`, `econ.inflation_1d`, `econ.labor_1d`, `econ.money_1d` - FRED macro indicators (routed by domain)
- `alt.weather_1d` - Weather data from key growing regions
- `training.oof_core_1d` - Core out-of-fold quantiles for stacking (p30/p50/p70)
- `training.specialist_signals_1d` - Specialist signals (signal_1/signal_2/confidence), no horizons

## Model Training

### Training Workflow (Core + Specialists)

1. **Core Feature Matrix**: Build `training.matrix_1d` from all sources.
2. **Core Training (CPU-only, Full Model Zoo)**:
   - Run `python -m fusion.core_training.run_pipeline --skip-matrix`
   - Use an explicit Model Zoo allowlist in `hyperparameters={...}` (no presets).
   - No time limits; AutoGluon trains all models and selects/ensembles the best.
3. **Specialists (unchanged)**: 11 domain signal generators in `src/fusion/specialists/`.
4. **Meta + Risk Layers**: consume Core OOF + specialist signals downstream.

### Core Training Policy (CPU-only, Full Model Zoo)

Core runs **CPU-only** (no MPS, no CUDA). Set environment guards **before**
importing torch/autogluon:

```
TOKENIZERS_PARALLELISM=false
OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES
AUTOGLUON_DISABLE_RAY=1
PYTORCH_ENABLE_MPS_FALLBACK=1
device = "cpu"
```

Core must try **ALL** AutoGluon-TimeSeries Model Zoo models via an explicit
allowlist in `hyperparameters={...}` (model names may omit the “Model” suffix).

### Which models are tried (Model Zoo allowlist)

- **Baselines:** Naive, SeasonalNaive, Average, SeasonalAverage, Zero
- **Statistical:** ETS, AutoETS, AutoARIMA, AutoCES, Theta, NPTS, ADIDA, Croston, IMAPA
- **Deep/ML:** DeepAR, TemporalFusionTransformer, DLinear, PatchTST, SimpleFeedForward
- **Neural:** TiDE, WaveNet
- **Tabular TS:** DirectTabular, PerStepTabular, RecursiveTabular
- **Pretrained:** Chronos2, Chronos, Toto

If the installed AutoGluon version exposes additional Model Zoo entries, include
them too.

### How AutoGluon selects the final model

AutoGluon trains the full allowlist, ranks models on internal
validation/backtests, and typically selects a **WeightedEnsemble** as best.

### Verification checklist (log evidence)

- Run `python -m fusion.core_training.run_pipeline --skip-matrix --horizons 5`
- Run `python -m fusion.core_training.run_pipeline --skip-matrix`
- Confirm logs show the full allowlist and a WeightedEnsemble selection

## Scheduling

**Production orchestration lives in the frontend** (Vercel Inngest).

- Inngest functions: `frontend/src/inngest/`
- Inngest route handler: `frontend/src/app/api/inngest/route.ts`

Offline training orchestration lives in `scripts/` and the `src/fusion/` training packages.

## Development

### Local Development Workflow

1. Make code changes in `src/fusion/`
2. Restart the API server
3. Commit changes to Git

### Project Structure

```
ZINC-Fusion-V15/
├── src/
│   └── fusion/
│       ├── api/                    # FastAPI service
│       └── core_training/          # SoT v2 training package
├── prisma/
│   └── schema.prisma              # Prisma schema (authoritative)
├── scripts/
│   ├── v2_training/               # SoT v2 training scripts
│   └── neural_sentiment_scoring.py # Sentiment pipeline
├── models/                        # Trained model artifacts
├── pyproject.toml                 # Python dependencies
└── README.md                      # This file
```

### Environment Variables

Required environment variables in `.env`:

```bash
# Database (REQUIRED)
DATABASE_URL="postgres://..."      # Prisma Postgres connection

# Economic Data (ongoing updates)
FRED_API_KEY="your_fred_api_key"   # FRED API key
```

Load environment variables before running:

```bash
source .env
python -m uvicorn fusion.api.server:app --host 0.0.0.0 --port 8000
```

## Deployment

- **Database**: Prisma Postgres (cloud-hosted, no local setup required)
- **Backend**: FastAPI server connecting to Prisma
- **UI**: Vercel deployment (Next.js + Inngest)

### Adding Dependencies

```bash
uv pip install -e ".[dev]"
```

## Testing

Run tests using pytest:

```bash
pytest tests/ -v
```

## Model Registry

ZINC Fusion V15 uses GrafanaRegistry for model tracking, writing directly to Prisma.

See `src/fusion/model_registry/` for implementation.

## Documentation

- **Docker Config**: `docker/README.md` - Docker Compose stack documentation
- **Prisma Schema**: `prisma/schema.prisma` - Authoritative database schema
- **Agent Guide**: `AGENTS.md` - Operational rules for AI assistants
- **Prisma Docs**: `https://www.prisma.io/docs`
- **FRED API Docs**: `https://fred.stlouisfed.org/docs/api/`

## License

Proprietary - US Oil Solutions / ZINC Digital of Miami

## Contact

For questions or support, contact the ZINC Fusion development team.