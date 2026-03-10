# Prisma + Local DB Dataflow Audit (2026-03-09)

## Scope

Audit of current data movement across Prisma schema/migrations, runtime database access, schedulers, API triggers, background workers, scripts, and manual sync paths.

## Executive Conclusion

- Prisma is the schema/migration control plane, not the runtime data plane.
- Runtime reads/writes primarily bypass PrismaClient and use direct SQL through:
  - TypeScript `pg` pool
  - Python `psycopg2` / SQLAlchemy
- Data movement is mostly one-way ingestion and serving, with operator-driven manual sync utilities for cloud↔local transfers.

## Core Evidence

- Prisma datasource and schemas defined in `prisma/schema.prisma`.
- Runtime TS DB pool in `frontend/src/lib/db.ts`.
- Runtime Python DB connection in `src/fusion/db/connection.py`.
- Inngest entrypoint and function registration in `frontend/src/app/api/inngest/route.ts` and `frontend/src/inngest/functions.ts`.
- Vercel cron config in `frontend/vercel.json`.
- Deprecated-only PrismaClient references in `scripts/_deprecated/*`.

## Database URL Resolution

- TS runtime precedence (`frontend/src/lib/db-env.ts`):
  1. `DATABASE_URL`
  2. `POSTGRES_URL`
  3. `DIRECT_DATABASE_URL`

- Python runtime precedence (`src/fusion/db/connection.py`):
  1. `DIRECT_DATABASE_URL`
  2. `POSTGRES_URL`
  3. `DATABASE_URL`

- Shared shell loader (`scripts/load_db_env.sh`) sources env in order: shell → `.env.local.audit` → `.env.local` → `.env`.

## Active Scheduler/Trigger Surfaces

1. Vercel cron
   - `frontend/vercel.json` schedules `/api/market-drivers` at `0 3 * * *`.

2. Inngest background jobs (primary async data plane)
   - Exposed at `/api/inngest`.
   - Functions exported in `frontend/src/inngest/functions.ts`.

3. Optional local cron path
   - `scripts/zl_live_burst.cron` + `scripts/run_databento_live_zl_burst.sh` + `scripts/ingest_databento_live_zl.py`.

4. Manual/API fanout triggers
   - `/api/refresh-drivers` sends Inngest events.
   - `/api/vegas/sync` runs direct DB sync from Glide.

## Primary Ingress and Transfer Paths

## A) Databento / market data

- Futures daily shards (`frontend/src/inngest/databento-futures-daily.ts`)
  - Source: Databento `ohlcv-1d`
  - Trigger: Inngest cron shards
  - DB: upsert into `mkt.futures_1d`
  - Direction: one-way ingress

- Statistics/open-interest shards (`frontend/src/inngest/databento-statistics-daily.ts`)
  - Source: Databento statistics
  - Trigger: Inngest cron shards
  - DB: upsert open interest into `mkt.futures_1d`
  - Direction: one-way ingress

- Options daily shards (`frontend/src/inngest/databento-options-daily.ts`)
  - Source: Databento definition + ohlcv + statistics
  - Trigger: Inngest cron shards
  - DB: writes `mkt.options_1d`
  - Direction: one-way ingress

- Local live burst (`scripts/ingest_databento_live_zl.py`)
  - Source: Databento live stream
  - Trigger: local cron/manual
  - DB: upserts `analytics.latest_price`, `analytics.price_1m`, `analytics.price_5m`
  - Direction: one-way ingress (+ optional Inngest event fanout)

## B) Macro/policy/supply/weather ingestors

- FRED segmented jobs (`frontend/src/inngest/fred-daily.ts`)
  - Trigger: per-segment Inngest crons
  - DB writes: `econ.*` segment tables + `ops.ingest_run` + `ops.quarantined_record`
  - Direction: one-way ingress

- USDA/WASDE/export sales/AMS, EIA/LCFS, CFTC, weather, federal register/congress/news jobs
  - Trigger: Inngest cron/event functions in `frontend/src/inngest/*`
  - DB writes: domain-specific `supply.*`, `econ.*`, `alt.*`, `pos.*`, etc.
  - Direction: one-way ingress

## C) Vegas/Glide sync

- Manual sync API (`frontend/src/app/api/vegas/sync/route.ts`)
  - Source: Glide API
  - Trigger: API `POST`
  - DB operation: transactional `TRUNCATE` + reload inserts to `vegas.vegas_*`
  - Direction: one-way ingress

- Scheduled sync (`frontend/src/inngest/glide-vegas.ts`)
  - Trigger: cron
  - DB operation: same truncate+reload pattern
  - Direction: one-way ingress

## D) API serving layer

- Most Next.js routes under `frontend/src/app/api/**/route.ts` are read paths against analytics/forecast/domain tables.
- `/api/refresh-drivers` is a trigger route (event fanout), not a direct writer.

## Prisma Model/Table Coverage

- Parsed schema contains 120 Prisma models mapped to schema-qualified tables across the approved 12 schemas.
- Temporary mapping artifact generated during audit: `reports/_tmp_prisma_model_table_map.txt`.

## Migrations and Data Movement

- Prisma migrations are primarily DDL but include some DML (`INSERT/UPDATE/DELETE`) in selected migration files.
- These are migration-time transforms, not the ongoing runtime ingestion plane.

## Active vs Legacy

### Active

- Inngest route + function exports wired.
- Vercel cron for `/api/market-drivers` present.
- Runtime direct SQL layers active by design (`pg`, `psycopg2`/SQLAlchemy).

### Legacy/Inactive indicators

- PrismaClient references found only in `scripts/_deprecated/*` in this repository state.

## Directionality

- Predominantly one-way:
  - external source → ingestion worker/script/API trigger → Postgres
  - Postgres → API responses/dashboard
- Manual cloud/local transfer scripts provide directional sync when explicitly invoked.

## Uncertainties / Gaps

- Final shell context during audit did not expose DB URL env vars, so active-now verification relied on wiring/config evidence instead of full live DB telemetry in that exact shell.
- Some trigger parsing was heuristic; exact file/line evidence was still verified for principal pathways.

## Real Architecture (Concise)

Prisma governs schema and migrations. Runtime data movement is executed by Inngest jobs, API-triggered workflows, and Python/CLI ingestors using direct SQL connections. The architecture is intentionally Prisma-bypass for runtime IO, with one-way ingestion pipelines feeding the domain tables consumed by API read routes and dashboard services.
