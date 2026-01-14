# Inngest Governance + Schema Fix Report (2026-01-14)

## Executive Summary

Eliminated silent failure modes and governance violations in Inngest ingestion:

- Fixed **time-key / column mismatches** (e.g., `report_date`/`as_of_date` vs real `event_date`).
- Removed **unsafe `ON CONFLICT (...)`** usage where the DB has no matching UNIQUE constraint.
- Removed **silent DDL** (`CREATE TABLE IF NOT EXISTS`, `CREATE SCHEMA IF NOT EXISTS`) from Inngest/vegas sync flows.
- Removed **hardcoded Glide bearer token** and enforced env-only credentials.

This keeps the system aligned with repo policy: **real data only**, **fail loudly**, **no silent schema changes**.

## Fixes Applied

### 1) CFTC Weekly (Inngest)
**File:** `frontend/src/inngest/cftc-weekly.ts`

- Uses `event_date` (DB reality) and does **insert-only**.
- Uses **idempotency checks** (event+symbol existence + `row_hash` existence).
- Logs all runs to `ops.ingest_run`.
- **No `ON CONFLICT`** (table has no UNIQUE key on `(event_date, symbol)`).

### 2) Additional stale-source ingestion (Inngest)

- `frontend/src/inngest/fx-spot-daily.ts` → `raw.fx_spot_1d` (FRED series → pairs)
- `frontend/src/inngest/noaa-weather-daily.ts` → `raw.weather_noaa_1d` (NOAA CDO)
- `frontend/src/inngest/usda-export-sales-weekly.ts` → `raw.usda_export_sales_1w` (FAS `complete.htm` parser)

### 3) Removed silent DDL from Inngest jobs

The following jobs now **assert the table exists** and fail loudly if not (no auto-creation in prod):

- `frontend/src/inngest/aei-trade.ts`
- `frontend/src/inngest/cbp-trade.ts`
- `frontend/src/inngest/conab-news.ts`
- `frontend/src/inngest/farmdoc-rins.ts`
- `frontend/src/inngest/nyfed-daily.ts`
- `frontend/src/inngest/glide-vegas.ts`

### 4) Glide remains strictly READ ONLY

Glide API usage is limited to the **read-only** `queryTables` endpoint:

- `frontend/src/inngest/glide-vegas.ts`
- `frontend/src/app/api/vegas/sync/route.ts`
- `src/fusion/ingestion/glide_vegas.py`

Enforcements:
- No hardcoded bearer tokens; requires `GLIDE_BEARER_TOKEN`.
- No other Glide endpoints are used.
- Writes occur only to Prisma Postgres (`ops.vegas_*`) to support the dashboard.

## Remaining Gaps (Not Yet Implemented)

- `raw.usda_wasde_1m`: needs a stable real source for **ongoing updates** (no Inngest owner today). `scripts/ingest_wasde_backfill.py` is available for backfill/repair runs and now uses the correct `event_date` column.
- `raw.epa_rin_prices_1d`: needs a reliable real endpoint (no synthetic backfill).

## References

- Prisma schema: `prisma/schema.prisma`
- Freshness checker: `scripts/check_freshness.py`
- Pretraining audit: `scripts/pretrain_readiness_audit.py`
