# ZINC Fusion V15

Soybean oil procurement forecasting system for US Oil Solutions.

## System purpose

ZINC Fusion forecasts the future **ZL futures contract price** at four horizons and then wraps that forecast with calibrated probability for decision support.

- Core forecast: one `predicted_price` per horizon (`5d`, `21d`, `63d`, `126d`)
- Probability layer: Monte Carlo (`10,000` runs) + pinball calibration + MAE/accuracy context
- UI output: horizontal **Target Zones** (not cones/bands/funnels)

This system is intelligence-only. It does not implement trade execution logic.

## Architecture

### L0 core model

- AutoGluon TimeSeriesPredictor ensemble (CPU-only)
- Core training optimizes MAE for `target_price_{h}d` (5, 21, 63, 126)
- Persisted core contract is a single `predicted_price` per horizon in `training.oof_core_1d`
- Production target-zone quantiles (`p30/p50/p70/p10_cal/p90_cal`) are generated downstream by residual calibration (L2/L3), not read directly from core OOF quantile columns

### Specialist signal layer (Big-11)

Specialists generate contextual signals used as model inputs:

1. `crush`
2. `china`
3. `substitutes`
4. `fx`
5. `fed`
6. `tariff`
7. `energy`
8. `biofuel`
9. `palm`
10. `volatility`
11. `trump_effect`

Signals land in `training.specialist_signals_1d` and feed `training.matrix_1d`.

### L2/L3 probability engine

- L2/L3 consumes core `predicted_price`
- Produces probability statements like: `ZL has an 88% chance of hitting XX.XX by [date]`
- Dashboard renders this as Target Zones
- Monte Carlo probabilities (`prob_enter_zone`, `prob_touch_p10`, `prob_touch_p90`, `mc_runs`) are populated by `scripts/run_monte_carlo.py` (10,000 simulations). If MC has not been run for a row set, `prob_*` fields can remain null.

## Technology stack

- Frontend: Next.js (`frontend/`) on Vercel
- Orchestration: Inngest functions (`frontend/src/inngest/`)
- Backend/ML: Python (`src/`) + FastAPI + AutoGluon
- Database: Prisma Postgres (cloud)
- Production deploy targets cloud Postgres; local development commonly targets a localhost mirror. Verify active target via env before audits/migrations.
- Prisma is used for schema/migrations/validation.
- Runtime query paths use `pg` (frontend) and `psycopg2`/SQLAlchemy (Python).

## Database contract

`prisma/schema.prisma` is the schema source of truth.

### Allowed schemas (12)

`mkt`, `econ`, `alt`, `pos`, `supply`, `features`, `training`, `model`, `forecasts`, `analytics`, `ops`, `vegas`

### Banned schemas

`raw`, `gold`, `silver`, `bronze`, `monitoring`, `specialist`, `weather`, `archive`

### Prisma usage policy

- Use Prisma CLI for migrations/validation only
- Do not use PrismaClient in runtime app paths

## Repository layout

```text
ZINC-FUSION-V15/
├── src/                         # Python pipeline, ML, FastAPI
├── frontend/                    # Next.js app + Inngest functions
├── prisma/schema.prisma         # Database schema source of truth
├── prisma/migrations/           # SQL migrations
├── config/                      # Prisma CLI package.json + prisma config
└── scripts/                     # Operational and validation scripts
```

There is intentionally no root `package.json`.

- Frontend npm commands: `--prefix frontend`
- Prisma npm commands: `--prefix config` (or `scripts/prisma.sh`)

## Local setup

### Prerequisites

- Python 3.11+
- `uv`
- Node.js 22+

### Install

```bash
# Python deps
uv pip install -e ".[dev]"

# Frontend deps
npm ci --prefix frontend

# Prisma CLI deps
npm ci --prefix config
```

## Common commands

### Run frontend

```bash
npm --prefix frontend run dev
```

### Run API

```bash
python -m uvicorn fusion.api.server:app --host 0.0.0.0 --port 8000
```

### Run core pipeline

```bash
.venv/bin/python -m fusion.core_training.run_pipeline
.venv/bin/python -m fusion.core_training.run_pipeline --skip-matrix
```

### Generate specialist features/signals

```bash
.venv/bin/python scripts/generate_specialist_features.py --bucket all --start-date 2025-01-01
.venv/bin/python scripts/generate_specialist_signals.py --bucket all --start-date 2025-01-01
```

### Prisma validation/migrations

```bash
npx --prefix config prisma validate --schema prisma/schema.prisma
bash scripts/prisma.sh migrate status
```

### Quality gates

```bash
make lint
make lint-frontend
make tsc
make prisma-validate
make git-integrity
```

## Inngest operational rules

- Shared client id must remain `fusion-jobs`
- DB-touching jobs use `DB_CONCURRENCY` policy
- Side effects should execute inside `step.run()`
- New functions must be exported in `frontend/src/inngest/functions.ts` and registered in `frontend/src/app/api/inngest/route.ts`

## Additional docs

- [AGENTS.md](AGENTS.md) - architecture and operational guardrails
- [CLAUDE.md](CLAUDE.md) - project state notes
- [`TO-DO/Audit/2026-03-11_forensic_db_inngest_operational_audit.md`](TO-DO/Audit/2026-03-11_forensic_db_inngest_operational_audit.md) - working forensic audit checklist
