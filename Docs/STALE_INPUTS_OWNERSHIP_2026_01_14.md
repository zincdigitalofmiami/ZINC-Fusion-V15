# Stale Inputs — Ownership + Column Reality (2026-01-14)

This document maps **stale raw inputs** (from `Docs/PRETRAINING_READINESS_2026_01_14.md`) to their **actual ingestion owners**, and records **verified DB column reality** so we don’t run the wrong scripts.

## Verified DB Reality (PROD)

Read-only `information_schema` checks confirm:

- All listed raw tables have a canonical **`event_date`** column, but its **type varies**:
  - `date`: `raw.cftc_cot_1w`, `raw.usda_export_sales_1w`, `raw.usda_wasde_1m`, `raw.weather_noaa_1d`
  - `timestamp` (no tz): `raw.fx_spot_1d`, `raw.epa_rin_prices_1d`
- These tables have a PK on **`id` only** (no UNIQUE/PK constraint on natural keys like `(event_date, symbol)`), so **`ON CONFLICT (event_date, …)` is not safe** unless we add a schema constraint (requires explicit approval).

Tables verified:
- `raw.cftc_cot_1w`
- `raw.usda_export_sales_1w`
- `raw.usda_wasde_1m`
- `raw.epa_rin_prices_1d`
- `raw.fx_spot_1d`
- `raw.weather_noaa_1d`

**Implication:** any ingestion/backfill that uses `ON CONFLICT (...) DO UPDATE` on these tables will error unless we add a unique constraint (schema change) or implement **row_hash idempotency** (preferred for Bronze/append-only).

## Stale Tables → Owners (Repo Reality)

### Blockers (per readiness audit)

| Table | Stale | Ingestion owner in repo | Status |
|------|------:|--------------------------|--------|
| `raw.fx_spot_1d` | ~5d | `frontend/src/inngest/fx-spot-daily.ts` | ✅ Inngest-owned (via FRED API); insert-only idempotent |
| `raw.weather_noaa_1d` | ~0d | `frontend/src/inngest/openmeteo-weather-daily.ts` + `frontend/src/inngest/noaa-weather-daily.ts` | ✅ Inngest-owned (Open-Meteo for `OM_*` + `OPENMETEO:*`; NOAA CDO for `GHCND:*`) |
| `raw.usda_wasde_1m` | ~2d | `frontend/src/inngest/usda-wasde-monthly.ts` | ✅ Inngest-owned (Cornell WASDE XML mirror); insert-only idempotent |
| `raw.epa_rin_prices_1d` | ~30d | `frontend/src/inngest/epa-rin-prices-daily.ts` | ✅ Inngest-owned (EPA Qlik JSON-RPC over WebSocket); insert-only idempotent |

### Warnings (still important for “ALL DATA” policy)

| Table | Stale | Ingestion owner in repo | Status |
|------|------:|--------------------------|--------|
| `raw.cftc_cot_1w` | ~8d | `frontend/src/inngest/cftc-weekly.ts` | ✅ Bronze-compliant (no `ON CONFLICT`; row_hash + existence checks) |
| `raw.usda_export_sales_1w` | ~13d | `frontend/src/inngest/usda-export-sales-weekly.ts` | ✅ Inngest-owned (FAS report parser); insert-only idempotent |

## Immediate Execution Implications

1) Weather + FX are now “Inngest-first” and refreshed; WASDE now has a stable ingestion path via Cornell mirror.
2) RIN prices have an ingestion owner, but EPA Qlik currently reports a latest transfer-week date of `11/24/2025` (data appears to update monthly), so the strict `stale_days_fail=28` gate may still trip until EPA publishes newer weeks.
