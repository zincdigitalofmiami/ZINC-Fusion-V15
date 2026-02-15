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

- **L0 Core:** 4 AutoGluon models (5d/21d/63d/126d horizons)
- **Specialists:** 11 signal generators (domain-specific, no horizons)
- **L1 Meta:** 4 meta-learners combining core + specialist signals
- **L2/L3:** Calibration + Monte Carlo risk (VaR/CVaR)

## Core Rules

1. No fabrication — never invent schemas, tables, files, or endpoints
2. No execution logic — intelligence only, no buy/sell/act
3. No silent schema changes — declare and get approval
4. Read before editing — always read files before modifying
5. Verify before claiming done — lint, test, re-read
6. Minimal changes — fix root causes, avoid unrelated refactors
7. Forward fill is OFF by default — requires explicit approval
8. Say "I don't know" when uncertain
