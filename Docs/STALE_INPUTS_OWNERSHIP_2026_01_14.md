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
| `raw.usda_wasde_1m` | ~33d | ❌ none for ongoing updates | `scripts/ingest_wasde_backfill.py` exists (backfill-only); **`www.usda.gov` is non-responsive from our runtime**, so an alternate stable host/source is required for automation |
| `raw.epa_rin_prices_1d` | ~30d | ❌ none found | EPA “RIN Trades and Price Information” is embedded in **Qlik** (`edap.epa.gov`) with iframe sheets; extraction requires a dedicated Qlik exporter (no simple HTML table/CSV link) |

### Warnings (still important for “ALL DATA” policy)

| Table | Stale | Ingestion owner in repo | Status |
|------|------:|--------------------------|--------|
| `raw.cftc_cot_1w` | ~15d | `frontend/src/inngest/cftc-weekly.ts` | ✅ Bronze-compliant (no `ON CONFLICT`; row_hash + existence checks) |
| `raw.usda_export_sales_1w` | ~20d | `frontend/src/inngest/usda-export-sales-weekly.ts` | ✅ Inngest-owned (FAS report parser); insert-only idempotent |

## Immediate Execution Implications

1) Weather + FX are now “Inngest-first” and refreshed; remaining staleness blockers are **WASDE** and **RIN prices**.
2) For the remaining blockers, the repo currently has **no scheduled ingestion path**:
   - WASDE: automation is blocked by `www.usda.gov` being non-responsive from our runtime.
   - RIN prices: the EPA page embeds a Qlik app (`edap.epa.gov`) and needs a Qlik extraction strategy (or an alternate licensed source).
