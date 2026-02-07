NOTE: Production is the dashboard/frontend, not the repo root.
# ZINC-FUSION-V15 – GitHub Copilot Instructions

Copilot must follow repo governance. Treat `AGENTS.md` as the primary source of truth.

## Non‑negotiables

- Do not invent schemas, tables, columns, symbols, endpoints, credentials, or file paths.
- Do not mutate Prisma schemas/tables without explicit user approval (declare exact tables/columns).
- Do not add decision/execution semantics (no "buy/sell/act now" logic).
- Keep diffs minimal and reversible; avoid unrelated refactors.
- Validate before asserting. If you didn't inspect it, don't claim it.
- **NEVER write code in chat responses unless explicitly asked.** Discuss, plan, approve first.

## Database Architecture (CRITICAL)

**Prisma Postgres is the ONLY database.** Prisma manages schema only — runtime queries use raw SQL.

- **TypeScript**: `pg` Pool via `frontend/src/lib/db.ts`
- **Python**: psycopg2/SQLAlchemy via `src/fusion/db/connection.py`

**DO NOT** suggest migrating to PrismaClient for runtime queries.

## Schema Boundaries (12 schemas)

**Landing (append-only):** `mkt`, `econ`, `alt`, `pos`, `supply`
**Derived (computed):** `features`, `training`
**Output (versioned):** `model`, `forecasts`, `analytics`
**Governance:** `metadata`, `ops`

**BANNED schemas:** `raw`, `gold`, `silver`, `bronze`, `monitoring`, `specialist`, `weather`, `archive`

## v3 Architecture (19 Models)

- **L0 Core:** 4 horizon models (AutoGluon TimeSeriesPredictor, CPU-only)
- **Specialists:** 11 signal generators with custom architectures (NOT TabularPredictors)
- **L1 Meta:** 4 stacked ensembles per horizon
- Specialists produce **signals** (no horizons). Core owns all horizon forecasting.
- OOF: 1 table (`training.oof_core_1d`), NOT 48 tables.

## Forward Fill Policy

Forward fill is OFF by default. Any use requires explicit approval. See `Docs/FORWARD_FILL_POLICY.md`.

## Canonical entrypoints

- Database: Prisma Postgres via `DATABASE_URL`
- FastAPI app: `fusion.api.server:app`
- Prisma schema: `prisma/schema.prisma`

## Validation defaults (prefer venv)

- `.venv/bin/pytest -q`