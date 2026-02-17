# ZINC Fusion V15 - Soybean Oil Procurement Forecasting

**Institutional-grade quantitative forecasting system for US Oil Solutions**

This project implements a multi-layer ensemble ML pipeline for predicting ZL (Soybean Oil) futures prices across multiple time horizons (1W, 1M, 3M, 6M), enabling strategic procurement decisions for bulk soybean oil purchasing.

## ✅ Latest Update (Jan 2026): v3 Architecture + Data Enhancements

- **v3 Architecture adopted**: 19-model stack (4 Core + 11 Specialists as signal generators + 4 Meta)
- **Weather data** consolidated into `alt.weather_1d` (215K+ observations, 57 stations)
- **Board crush** daily calculations via `analytics.board_crush_1d`
- **Tariff deadline tracking** via `alt.tariff_deadlines`
- **EIA biodiesel** monthly ingestion via `supply.eia_biodiesel_1m`

## Table of Contents

- [Introduction](#introduction)
- [Architecture](#architecture)
- [Getting Started](#getting-started)
- [Data Pipeline](#data-pipeline)
- [Model Training](#model-training)
- [Development](#development)
- [Testing](#testing)

## Introduction

**ZINC Fusion V15** is a 4-layer hierarchical ensemble forecasting system (v3 architecture, 19 models):

- **L0 Core**: 4 AutoGluon TimeSeriesPredictor models (one per horizon: 5d, 21d, 63d, 126d; CPU-only, full Model Zoo)
- **L0 Specialists**: 11 signal generators with custom-built architectures (XGB, GBM, RF, ARDL, Ridge, GARCH, VAR, ECM, rules-based, EMA, event study) — produce horizon-agnostic signals, NOT forecasts
- **L1 Meta**: 4 stacked ensembles (one per horizon) combining Core OOF + specialist signals
- **L2 Calibration**: Conformalized Quantile Regression (CQR) producing p10_cal/p90_cal outer envelope
- **L3 Risk**: Monte Carlo simulation for VaR, CVaR, barrier probabilities

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

ZINC-FUSION-V15
Price Impact Scenarios v2: Independent Axes + Training Model Structures (Source of Truth)
Status: Canonical scope for dev build-out (new training models + scenario engine)
Core principle: Model reality, don’t moralize it.
Quantile policy: Train P30/P50/P70 everywhere; compute outer envelope P10/P90 via calibration (coverage-truth), not vibes.

1. Core Mission and “2+2=22” doctrine
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

2. Data contracts and time keys (non-negotiable)
   Time keys
   Raw: event_date (or event_time for sub-daily) is canonical.

Derived / training / forecasts: as_of_date is canonical.

This prevents PIT leakage and “silent join death.”
Mixed frequency handling (weekly/monthly in daily matrix)
Forward-fill slow series with staleness encoding (age days, release day flags, delta-on-release). This allows daily training while preserving information arrival timing.

3. Model Architecture: 19-model ensemble (v3)
   Horizons
   H ∈ {5, 21, 63, 126} days.
   Core and Meta train one model per horizon (direct multi-step; no recursive horizon mixing).
   Quantiles
   OOF/stacking quantiles: [0.30, 0.50, 0.70]

Publish: p30/p50/p70 + calibrated p10_cal/p90_cal

AutoGluon TimeSeriesPredictor supports custom quantiles via quantile_levels.

L0 Core (1 per horizon; 4 total)
Model: AutoGluon TimeSeriesPredictor (Chronos family)

Output: probabilistic multi-step forecasts (quantiles).

Training window policy (per your spec):

5d/21d: 2020+ (signal purity)

63d/126d: 2000+ (regime learning)

L0 Specialists (11 total; horizon-agnostic signal generators)
Models: custom per specialist (XGB, GBM, RF, ARDL, Ridge, GARCH, VAR, ECM, rules-based, EMA, event-study)
Output contract: signal_1 (required), signal_2 (optional), confidence (optional)
Storage: training.specialist_signals_1d
Specialists do not produce horizon forecasts and do not have OOF tables.

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

Specialist policy
Specialists run daily to generate regime/context signals consumed by Core + Meta.

L1: Meta-learner (1 per horizon; 4 total)
Purpose: learn when to trust each base model (Core + Specialists) for horizon H.
Input matrix (per horizon)
Core OOF from training.oof_core_1d (p30/p50/p70)
Specialist signals from training.specialist_signals_1d
Regime/calendar features in training.meta_inputs_1d

OOF integrity (hard rule)
Meta must train on out-of-fold Core predictions + as-of specialist signals to avoid leakage.

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

4. Intrinsic Connection Discovery and Event Probability Layer
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

5. Price Impact Scenarios v2: Independent Axes
   Design rule: axes are independent overlays (no combinatorial explosion).
   Each axis produces baseline + shock distributions, and can be toggled separately.
   5.1 Core scenario artifact (per horizon H)
   Create: analytics.price*scenarios*{H}d_1d with:
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

6. Monte Carlo settings (optimal + bonus)
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

7. Tables and artifacts dev must build
   Training matrices
   training.matrix_1d (Core features + targets)

training.specialist_signals_1d (all 11 specialists in one table)

Target columns: target_ret_5d, target_ret_21d, target_ret_63d, target_ret_126d

OOF table (single)
training.oof_core_1d
Columns:
trade_date, symbol, horizon_days, window_id (PK)
p30/p50/p70
target_value, trained_at, run_hash, matrix_version

Meta inputs (4 total)
training.meta_inputs_1d
Core OOF + specialist signals + regime/calendar features + target values

Forecast outputs (4 total)
forecasts.production\_{H}d_1d
as_of_date, forecast_date

p30/p50/p70

p10_cal/p90_cal

model_version, run_id

Scenario outputs (4 horizons × axes)
analytics.price*scenarios*{H}d_1d
axis/scenario distributions + optional scenario weights

8. Training workflow (dependency order)
   Build daily training matrices (PIT-correct + staleness encoding)

Build targets target\_{H}d

Train Core_H (H ∈ {5,21,63,126})

Train 11 specialists (horizon-agnostic signal generation)

Generate + persist OOF for Core only (single table with horizon_days)

Build `training.meta_inputs_1d` and train meta per horizon (horizon filter)

Train Meta_H per horizon

Run L2 CQR calibration → p10_cal/p90_cal

Run L3 risk engine (MC)

Build scenario overlays (EVENTS, TRUMP_EFFECT, VOLATILITY, POLICY)

Publish forecasts + scenario artifacts for dashboard

9. Validation gates (training doesn’t “pass” without these)
   Probabilistic quality
   Quantile loss / coverage checks on p30/p70 (≈40% empirical)

Calibrated envelope coverage on p10_cal/p90_cal (≈80% empirical) via conformal/CQR.

Stacking sanity
Meta must use OOF features only; avoid leakage per stacking practice and CV stacking literature.

Regime-block CV + embargo
Folds are era/regime blocks (politics/crisis/macro eras)

Embargo window around fold boundaries

10. Minimal narrative spec for Chris (dashboard-ready)
    For each horizon:
    Event probabilities (what might happen + when + probability)

Price impact scenarios (BASELINE + shock overlays by axis)

Two cones on chart:

primary: P30–P70

outer: P10_cal–P90_cal (lighter)

Scenario mixture: probability-weighted blended forecast (computed as mixture, not averaged quantiles).

If dev builds to this SoT, you get:
horizon-aligned stacked ensemble (19 models)

11 specialists integrated correctly

independent scenario overlays (EVENTS / TRUMP_EFFECT / VOL / POLICY)

calibrated outer risk envelope

MC performance tuned for speed without turning outputs into noisy garbage

### SoT v3: Prisma Cloud Readiness (Pre-Training)

Preflight report (generated from PROD `DATABASE_URL`):

- `Docs/PRETRAINING_READINESS_2026_01_14.md`
- Generator: `scripts/pretrain_readiness_audit.py`

Current verdict (2026-01-14): **NOT READY**.

- `training.matrix_1d` populated with 114 columns, 7,808 rows ✅
- `training.specialist_signals_1d` table exists with proper schema
- Landing tables (mkt._, econ._, alt._, pos._, supply.\*) receiving data
- `metadata.symbol_mapping` covers `7/104` `mkt.futures_1d` symbols (governance gap; not always a hard blocker)

### SoT v3: Model Plan + Code Location

SoT v3 model catalog + naming (19-model stack; legacy `v2_training` path retained):

- `scripts/v2_training/MODEL_CATALOG.md`
- `scripts/v2_training/README.md`

### Pre-Training Validation Commands

```bash
# Read-only DB readiness check (fails non-zero if blockers exist)
python3 scripts/pretrain_readiness_audit.py --strict

# Repo guardrail: detect synthetic/placeholder patterns in code
python3 scripts/guard_no_synthetic_code.py
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

- `mkt.futures_1d` — ZL, ZS, ZM, CL and other futures OHLCV (daily)
- `econ.rates_1d`, `econ.activity_1d`, etc. — FRED economic indicators (7 domain tables)
- `alt.weather_1d` — Weather data from key growing regions
- `features.elite_1d` — Engineered feature store
- `training.matrix_1d` — Training matrix
- `training.oof_core_1d` — Core out-of-fold predictions (single table with `horizon_days`)
- `training.specialist_signals_1d` — Specialist signal outputs

## Model Training

### Training Workflow (v3)

The v3 training workflow follows this sequence:

1. **Build training matrix**: `training.matrix_1d` from `mkt.*`, `econ.*`, `features.*` tables (PIT-correct, staleness-encoded)
2. **Train L0 Specialists (11 buckets)**: Each specialist has a unique, custom-built model architecture producing horizon-agnostic signals (`signal_1`, `signal_2`, `confidence`) → stored in `training.specialist_signals_1d`
3. **Train L0 Core (4 horizons)**: AutoGluon TimeSeriesPredictor (CPU-only, full Model Zoo). Specialist signals feed in as input features → OOF stored in `training.oof_core_1d`
4. **Build meta inputs**: Core OOF + specialist signals + regime/calendar features → `training.meta_inputs_1d`
5. **Train L1 Meta (4 horizons)**: Stacked ensemble per horizon over meta inputs
6. **L2 Calibration**: CQR produces outer envelope (p10_cal/p90_cal)
7. **L3 Risk**: Monte Carlo simulation for VaR/CVaR and barrier probabilities

Quantile contract: OOF/stacking uses p30/p50/p70. Risk cones use p10/p30/p50/p70/p90.

Run core training:

```bash
python -m fusion.core_training.run_pipeline --skip-matrix --horizons 5
```

## Scheduling

Scheduling/orchestration is handled by **Inngest** running serverless on Vercel. Inngest functions in `frontend/src/inngest/` manage daily data ingestion (Yahoo EOD, ZL intraday, board crush, FRED) and periodic jobs.

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

## Model Registry

Trained models register in Prisma `model.model_registry` with `model_id`, `model_version`, `horizon_steps`, `trained_at`, `artifact_path`, `metrics_json`.

Model artifacts are stored under `models/core_v2/` (Core) and `models/specialists/{bucket}/` (Specialists).

## Documentation

- **Prisma Schema**: `prisma/schema.prisma` - Authoritative database schema
- **Agent Guide**: `AGENTS.md` - Operational rules for AI assistants
- **Prisma Docs**: [https://www.prisma.io/docs](https://www.prisma.io/docs)
- **FRED API Docs**: [https://fred.stlouisfed.org/docs/api/](https://fred.stlouisfed.org/docs/api/)

## License

Proprietary - US Oil Solutions / ZINC Digital of Miami

## Contact

For questions or support, contact the ZINC Fusion development team.
