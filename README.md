# ZINC Fusion V15 - Soybean Oil Procurement Forecasting

**Institutional-grade quantitative forecasting system for US Oil Solutions**

This project implements a multi-layer ensemble ML pipeline for predicting ZL (Soybean Oil) futures prices across multiple time horizons (1W, 1M, 3M, 6M), enabling strategic procurement decisions for bulk soybean oil purchasing.

## ✅ Latest Update (Dec 21, 2025): Weather Data Consolidation Complete

**Production-grade weather infrastructure with 20 years of historical data**

- **215,320 weather observations** from 57 stations across key soybean regions
- **5 regional schemas**: `weather.us_cornbelt`, `weather.brazil_cerrado`, `weather.brazil_south`, `weather.argentina_pampas`, `weather.argentina_north`
- **Enhanced variables**: Temperature (max/min/avg), precipitation (rain/snow), wind (speed/gusts), coordinates
- **Geographic coverage**: Iowa, Illinois, Indiana, Minnesota, Nebraska, Missouri, Brazil (MT/MS/MG/PR/RS/SP), Argentina (BA/CO/SF/ER/CH/FO/SE)

## Table of Contents

- [Introduction](#introduction)
- [Architecture](#architecture)
- [Getting Started](#getting-started)
- [Data Pipeline](#data-pipeline)
- [Model Training](#model-training)
- [Development](#development)
- [Testing](#testing)

## Introduction

**ZINC Fusion V15** is a 4-layer hierarchical ensemble forecasting system:

- **L0 Layer**: 12 base models (1 Core TimeSeriesPredictor + 11 Specialist TabularPredictors)
- **L1 Layer**: Meta-learner combining OOF predictions from L0 models
- **L2 Layer**: Ensemble fusion producing probabilistic forecasts (P10-P90)
- **L3 Layer**: Monte Carlo simulation for risk metrics (VaR, CVaR)

### Key Features

- **Big-11 Bucket Taxonomy**: Domain-specific specialists for Crush, China, FX, Fed, Tariff, Energy, Biofuel, Palm, Volatility, Substitutes, Trump Effect
- **Prisma Postgres**: Cloud-hosted authoritative database for all training and operations
- **Databento Integration**: Real-time and historical market data from CME Globex

### Business Impact

- **Client**: US Oil Solutions (Las Vegas, NV)
- **Product**: Bulk soybean oil for restaurant/casino fryers
- **Proven Results**: $250K cost avoidance achieved through strategic timing
- **Decision Support**: WHEN to lock in futures, HOW MUCH to buy

## Architecture

ZINC-FUSION-V15
Price Impact Scenarios v2: Independent Axes + Training Model Structures (Source of Truth)
Status: Canonical scope for dev build-out (new training models + scenario engine)
Core principle: Model reality, don’t moralize it.
Quantile policy: Train P30/P50/P70 everywhere; compute outer envelope P10/P90 via calibration (coverage-truth), not vibes.

1) Core Mission and “2+2=22” doctrine
Mission (what we ship)
Predict events before they happen (e.g., Brazilian drought in 18 days: 68% probability)


Assign probabilities to events (e.g., EPA mandate passage: 82% likely)


Wire event probabilities into forecasting models (L0 Specialists and optionally Core consume as features)


Generate probability-weighted price forecasts (baseline vs scenario vs mixture)


Show both on dashboard: predicted events + price impacts


“2+2=22” (why we win)
We don’t win by “drought → price up.” We win by intrinsic connection discovery:
cross-correlation lead/lag


cascades (event A → B → C → price)


non-linear interactions (drivers-of-drivers)


regime conditioning (same shock behaves differently under different policy/vol regimes)



2) Data contracts and time keys (non-negotiable)
Time keys
Raw: event_date (or event_time for sub-daily) is canonical.


Derived / training / forecasts: as_of_date is canonical.


This prevents PIT leakage and “silent join death.”
Mixed frequency handling (weekly/monthly in daily matrix)
Forward-fill slow series with staleness encoding (age days, release day flags, delta-on-release). This allows daily training while preserving information arrival timing.

3) Model Architecture: 52-model horizon-aligned stack
Horizons
H ∈ {5, 21, 63, 126} days.
Each horizon has its own self-contained stack (direct multi-step; no recursive horizon mixing).
Quantiles
Train (all models): quantile_levels = [0.30, 0.50, 0.70]


Publish: p30/p50/p70 + calibrated p10_cal/p90_cal


AutoGluon TimeSeriesPredictor supports custom quantiles via quantile_levels. 

L0: Base models (12 per horizon)
L0 Core (1 per horizon; 4 total)
Model: AutoGluon TimeSeriesPredictor (Chronos family)


Output: probabilistic multi-step forecasts (quantiles). 


Training window policy (per your spec):


5d/21d: 2020+ (signal purity)


63d/126d: 2000+ (regime learning)


L0 Specialists (11 per horizon; 44 total)
Model: AutoGluon TabularPredictor in quantile mode (P30/P50/P70)


Targets: target_{H}d (ZL close at t+H)


The 11 Specialists
CRUSH


CHINA


FX


FED


TARIFF


ENERGY


BIOFUEL


PALM


VOLATILITY


SUBSTITUTES


TRUMP_EFFECT


Training window policy
5d/21d specialists: 2020+


63d/126d specialists: 2000+



L1: Meta-learner (1 per horizon; 4 total)
Purpose: learn when to trust each base model (Core + Specialists) for horizon H.
Input matrix (per horizon)
12 models × 3 quantiles = 36 OOF columns


core_p30/p50/p70


{specialist}_p30/p50/p70 for all 11 specialists


minimal regime/calendar features (see below)


OOF integrity (hard rule)
Meta must train on out-of-fold predictions from base models to avoid leakage. Stacking literature and practice use CV-level predictions for level-1 training. 

L2: Calibration (per horizon; 4 modules)
Goal: provide a truthful outer risk envelope without distorting the central band.
Method: Conformalized Quantile Regression (CQR)
Combines quantile regression with conformal prediction to achieve finite-sample coverage under exchangeability while adapting interval width to heteroskedasticity. 


Outputs
Central: p30/p50/p70 (model-native)


Outer: p10_cal/p90_cal (calibrated interval)


Monotonic repair
Enforce: p10_cal ≤ p30 ≤ p50 ≤ p70 ≤ p90_cal (quantile crossing guardrail).

L3: Risk Engine (per horizon; 4 modules)
Purpose: barrier probabilities, time-to-touch, scenario path sampling, VaR/CVaR-like summaries.

4) Intrinsic Connection Discovery and Event Probability Layer
4.1 Event probabilities (daily artifact)
Create: analytics.event_probabilities_1d
as_of_date


event_type


window_start, window_end


p_event


severity_score


confidence


drivers_topk (JSON)


4.2 “Neural” discovery modules (minimum viable)
Lead/lag scanner (correlation over lag grid; significance via permutation/surrogates)


Cascade model (event graph: A → B → C → price)


Nonlinear mapping (interaction terms and regime-conditioned relationships)


Product output: “what predicts what,” with lags and confidence.
4.3 Wiring into models
Event probabilities become first-class features in L0 Specialists (and optionally Core), e.g.:
p_brazil_drought_21d, severity_brazil_drought


p_epa_mandate_pass_21d, days_to_epa_vote


p_china_quota_shift_next_q


shipping_cost_change_14d



5) Price Impact Scenarios v2: Independent Axes
Design rule: axes are independent overlays (no combinatorial explosion).
Each axis produces baseline + shock distributions, and can be toggled separately.
5.1 Core scenario artifact (per horizon H)
Create: analytics.price_scenarios_{H}d_1d with:
as_of_date


axis (EVENTS | TRUMP_EFFECT | VOLATILITY | POLICY)


scenario_name (BASELINE / SHOCK / etc.)


p_scenario (optional, recommended)


p30/p50/p70


p10_cal/p90_cal


drivers_topk (JSON)


5.2 Scenario math (mixture, not hand-waving)
When you “blend” scenario forecasts, you are forming a mixture distribution. Mixture quantiles generally do not have a closed form; compute via mixture CDF inversion or sampling. 
Implementation default: sampling-based mixture using the same MC engine (fast, robust).

A) EVENTS axis (your existing price-impact table)
This is the “baseline vs event shocks” layer.
Example (median endpoints shown):
Baseline (no events): $57 → $61


Mandate only: $57 → $59


Drought only: $57 → $64


Both: $57 → $67 (“meltdown” scenario)


Contract: each scenario is a distribution, not a point:
store p30/p50/p70, plus p10_cal/p90_cal



B) TRUMP_EFFECT axis (drop it in, explicitly)
Operational definition (3-part)
Policy uncertainty level (news-based)

 EPU indices are constructed from newspaper coverage frequency and are designed to proxy policy-related uncertainty. 


Policy action intensity (executive actions + regulatory pipeline)

 FederalRegister.gov provides a public API (no key required) for documents and metadata. 

 Presidential documents receive priority processing and appear on public inspection before publication. 


Policy category focus (trade/energy/biofuel/sanctions, etc.)

 Use categorical uncertainty (e.g., trade policy uncertainty) + Federal Register topic tagging.


Scenario states
TRUMP_BASELINE


TRUMP_ELEVATED


TRUMP_SHOCK


Mechanism
Overrides TRUMP_EFFECT feature bundle (uncertainty level/momentum, action intensity counts, category shares)


Primary effect: shifts event probabilities and cascade strengths (policy shocks), and widens tails via L2/L3, rather than forcing direction by decree.



C) VOLATILITY axis (independent)
Definition
Use implied-vol regime proxies. VIX is the canonical “expected 30-day volatility implied by SPX options.” 
(For ZL, prefer ZL IV; VIX is a global risk regime proxy.)
Scenario states
VOL_BASELINE


VOL_SPIKE (high/crisis)


Mechanism
Primarily changes distribution width and tail risk:


expands IQR (p70-p30)


increases barrier/touch probabilities


widens p10_cal/p90_cal



D) POLICY axis (independent)
Definition
“Policy friction” or “trade-policy pressure” independent of personality:
Categorical uncertainty components (trade policy uncertainty)


Rulemaking pipeline category focus (Federal Register tagging)


Scenario states
POLICY_BASELINE


POLICY_TIGHTENING


Mechanism
Increases likelihood and severity of policy-relevant cascades:


tariffs/retaliation risk


biofuel mandate/waiver risk


sanctions/export controls risk


Modifies skew/asymmetry (policy shocks are rarely symmetric)



6) Monte Carlo settings (optimal + bonus)
Production default (optimal)
N = 5,000


Variance reduction ON


randomized low-discrepancy sampling (e.g., Sobol)


antithetic variates


Regime escalation


elevated/high shock regimes → N = 10,000


crisis → N = 20,000 (if needed for tail stability)


Dev / smoke (bonus)
N = 2,000, deterministic seed, variance reduction ON



7) Tables and artifacts dev must build
Training matrices
training.core_matrix_1d (Core features + target_{H}d)


training.specialist_{bucket}_1d for each specialist


Target columns: target_5d, target_21d, target_63d, target_126d


OOF tables (48 total)
Pattern: training.oof_{model}_{H}d_1d
Columns:
as_of_date (PK)


{model}_p30/p50/p70


target_{H}d


Meta inputs (4 total)
training.meta_inputs_{H}d_1d
join all OOF columns + regime/calendar features + target_{H}d


Forecast outputs (4 total)
forecasts.production_{H}d_1d
as_of_date, forecast_date


p30/p50/p70


p10_cal/p90_cal


model_version, run_id


Scenario outputs (4 horizons × axes)
analytics.price_scenarios_{H}d_1d
axis/scenario distributions + optional scenario weights



8) Training workflow (dependency order)
Build daily training matrices (PIT-correct + staleness encoding)


Build targets target_{H}d


Train Core_H (H ∈ {5,21,63,126})


Train 11 specialists × H


Generate + persist OOF for all L0 models


Build meta input tables per horizon


Train Meta_H per horizon


Run L2 CQR calibration → p10_cal/p90_cal 


Run L3 risk engine (MC)


Build scenario overlays (EVENTS, TRUMP_EFFECT, VOLATILITY, POLICY)


Publish forecasts + scenario artifacts for dashboard



9) Validation gates (training doesn’t “pass” without these)
Probabilistic quality
Quantile loss / coverage checks on p30/p70 (≈40% empirical)


Calibrated envelope coverage on p10_cal/p90_cal (≈80% empirical) via conformal/CQR. 


Stacking sanity
Meta must use OOF features only; avoid leakage per stacking practice and CV stacking literature. 


Regime-block CV + embargo
Folds are era/regime blocks (politics/crisis/macro eras)


Embargo window around fold boundaries



10) Minimal narrative spec for Chris (dashboard-ready)
For each horizon:
Event probabilities (what might happen + when + probability)


Price impact scenarios (BASELINE + shock overlays by axis)


Two cones on chart:


primary: P30–P70


outer: P10_cal–P90_cal (lighter)


Scenario mixture: probability-weighted blended forecast (computed as mixture, not averaged quantiles). 



If dev builds to this SoT, you get:
horizon-aligned stacked ensemble (52 models)


11 specialists integrated correctly


independent scenario overlays (EVENTS / TRUMP_EFFECT / VOL / POLICY)


calibrated outer risk envelope


MC performance tuned for speed without turning outputs into noisy garbage




```

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
- `raw_market_futures` - ZL, ZS, ZM, CL futures OHLCV
- `raw_fred_observations` - Economic indicators
- `raw_weather_observations` - Weather data from key growing regions
- `driver_scores` - Normalized specialist driver scores
- `oof_predictions` - Out-of-fold predictions for stacking

## Model Training

### Training Workflow

The ZINC Fusion V15 training workflow follows a strict sequence:

1. **Canonical Features (Gold)**: Use `features.driver_scores_1d` as the canonical feature matrix.
2. **Train L0 Specialists (Per-Bucket)**:
    - Train each of the 11 Specialists with its own unique model family (independent pipelines).
    - Extract OOF predictions per bucket (before any refit_full).
    - Apply per‑bucket bagging to reduce variance.
3. **Join & Stack**: Horizontally stack all specialist OOF/bagged outputs.
4. **Train L1 Meta‑Learner**: Stacking model over specialist outputs.
5. **L2 Fusion**: Probabilistic fusion with uncertainty quantification (quantiles).
6. **L3 Risk**: Monte Carlo VaR/CVaR and risk metrics.

See [`QUANT_V15_Complete.ipynb`](./QUANT_V15_Complete.ipynb) for the complete training specification.

Canonical Feature Table
- The canonical features table is `features.driver_scores_1d` which provides normalized 0-100 scores for all 11 specialist drivers.
- Training tables follow the pattern `training.specialist_{bucket}_1d` where bucket is one of: crush, china, fx, fed, tariff, energy, biofuel, palm, volatility, substitutes, trump_effect.

## Scheduling

Scheduling/orchestration has been removed from this repository.

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
├── prisma/
│   └── schema.prisma              # Prisma schema (authoritative)
├── scripts/
│   ├── train_*.py                 # Training scripts
│   └── ingest_*.py                # Data ingestion scripts
├── models/                        # Trained model artifacts
├── pyproject.toml                 # Python dependencies
└── README.md                      # This file
```

### Environment Variables

Required environment variables in `.env`:

```bash
# Database (REQUIRED)
DATABASE_URL="postgres://..."      # Prisma Postgres connection

# Market Data
DATABENTO_API_KEY="db-..."         # Databento API key

# Economic Data
FRED_API_KEY="your_fred_api_key"   # FRED API key

# MLflow (for experiment tracking)
MLFLOW_TRACKING_URI=http://localhost:5001
MLFLOW_S3_ENDPOINT_URL=http://localhost:9000
AWS_ACCESS_KEY_ID=mlflow
AWS_SECRET_ACCESS_KEY=mlflow123
```

Load environment variables before running:

```bash
source .env
python -m uvicorn fusion.api.server:app --host 0.0.0.0 --port 8000
```

## Deployment

- **Database**: Prisma Postgres (cloud-hosted, no local setup required)
- **Backend**: FastAPI server connecting to Prisma
- **UI**: Optional Vercel deployment

### Adding Dependencies

```bash
uv pip install -e ".[dev]"
```

## Testing

Run tests using pytest:

```bash
pytest tests/ -v
```

## MLflow Experiment Tracking

ZINC Fusion V15 uses MLflow for experiment tracking and model registry.

### Quick Start

```bash
# Start MLflow stack (PostgreSQL + MinIO + MLflow)
./scripts/start-mlflow.sh
```

### Access Points

| Service | URL | Credentials |
|---------|-----|-------------|
| MLflow UI | http://localhost:5001 | None |
| MinIO Console | http://localhost:9001 | mlflow / mlflow123 |

### Sync Prisma Data to MLflow

```bash
DATABASE_URL="postgres://..." python scripts/sync_prisma_to_mlflow.py --all
```

See [Docs/MLFLOW_SETUP.md](./Docs/MLFLOW_SETUP.md) for full documentation.

## Documentation

- **MLflow Setup**: `Docs/MLFLOW_SETUP.md` - Experiment tracking configuration
- **Docker Config**: `docker/README.md` - Docker Compose stack documentation
- **Prisma Schema**: `prisma/schema.prisma` - Authoritative database schema
- **Agent Guide**: `AGENTS.md` - Operational rules for AI assistants
- **Prisma Docs**: [https://www.prisma.io/docs](https://www.prisma.io/docs)
- **Databento Docs**: [https://databento.com/docs](https://databento.com/docs)

## License

Proprietary - US Oil Solutions / ZINC Digital of Miami

## Contact

For questions or support, contact the ZINC Fusion development team.
