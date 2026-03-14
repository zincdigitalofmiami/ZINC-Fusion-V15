# Chart, Databento, and Schema Drift Audit — 2026-03-13

**Status:** Complete  
**Scope:** Frontend chart freshness, ZL serving tables, Databento ingest path, production-vs-local drift, migration safety  
**Execution mode:** Read-only audit. No migrations, no schema changes, no data writes.

## Executive Summary

The current chart outage is a production data freshness problem, not a Databento vendor outage.

The strongest evidence is:

- The current Vercel production `DATABENTO_API_KEY` returns `401 Authentication failed` on 2026-03-13.
- A manually tested working Databento key returns `200` with valid `ohlcv-1d` ZL data on 2026-03-13.
- Production chart-serving tables are stale:
  - `analytics.price_1d` latest `2026-03-10`
  - `analytics.price_1m` latest `2026-03-11 05:30:00+00`
  - `analytics.latest_price` latest `2026-03-11 05:30:00+00`
  - `analytics.price_5m` latest `2026-03-06 05:25:00+00`
  - `analytics.price_15m` latest `2026-03-05 19:15:00+00`
  - `analytics.price_1h` latest `2026-03-05 19:00:00+00`
- Production forecasts are also stale:
  - `forecasts.production_1d` latest `as_of_date = 2026-03-04`
  - `training.matrix_1d` latest `trade_date = 2026-03-03`
  - `training.specialist_signals_1d` latest `as_of_date = 2026-03-03`
  - `training.oof_core_1d` latest `trade_date = 2026-02-20`

Local is not a safe mirror of production. The local DB is severely drifted and should be treated as toxic for migration work:

- Only `analytics.zl_live` exists under `analytics`, and it is empty.
- `analytics.price_1d`, `analytics.price_1m`, `analytics.price_5m`, `analytics.price_15m`, `analytics.price_1h`, and `analytics.latest_price` do not exist locally.
- No `mkt.*` tables exist locally.
- `prisma migrate status` reports "Database schema is up to date!" against this DB, but `prisma migrate diff` shows a massive non-empty drift and `_prisma_migrations` contains duplicate rolled-back history.

Conclusion: do not run migrations against the current local DB. Fix production data freshness first, then rebuild or re-sync local from a trusted source before any migration work.

## Audit Method

Read-only checks performed:

- Source review of the current chart, API routes, Inngest functions, Databento helpers, env loaders, and audit scripts
- Local DB schema and freshness inspection via `psql`
- Production DB inspection via temporary `vercel env pull` to `/tmp` followed by `psql`
- Production Databento credential verification via temporary env pull and direct API request
- Manual Databento vendor verification with a working key
- Repo verification gates:
  - `npm --prefix frontend run lint`
  - `npm --prefix frontend run build`
  - `npx --prefix config prisma validate --schema prisma/schema.prisma`
  - `bash scripts/prisma_status.sh`

Temporary Vercel env artifacts were created outside the repo and deleted immediately after use.

## Confirmed Findings

### P0. Production Databento credential is broken

On 2026-03-13, the production Vercel env `DATABENTO_API_KEY` returned:

- `401 auth_authentication_failed`

The same day, a manually supplied working Databento key returned:

- `200`
- valid `GLBX.MDP3` / `ohlcv-1d` ZL rows

This means Databento itself is available. The production credential or account state is the failure point.

Corroborating production alerts from `ops.pipeline_alerts`:

- `fusion-jobs-zl-daily` failed `2026-03-13 11:07:17+00` with `401 Authentication failed`
- `fusion-jobs-zl-1m-scheduled-backfill` failed `2026-03-13 06:00:36+00` with `401 Authentication failed`
- On `2026-03-12`, both jobs failed with `402 account_delinquent_invoice`

Inference: the production Databento path has moved from billing failure to invalid-auth failure. Either the key is wrong now, the account state changed, or both.

### P0. Production chart-serving tables are stale

The current frontend chart reads:

- `/api/zl/price-1d`
- `/api/zl/live`

Those routes depend on:

- `analytics.price_1d`
- `analytics.price_1m`
- `analytics.latest_price`

Production DB freshness on 2026-03-13:

| Table | Latest timestamp | Status |
| --- | --- | --- |
| `analytics.price_1d` | `2026-03-10` | stale |
| `analytics.price_1m` | `2026-03-11 05:30:00+00` | stale |
| `analytics.latest_price` | `2026-03-11 05:30:00+00` | stale |
| `analytics.price_5m` | `2026-03-06 05:25:00+00` | stale |
| `analytics.price_15m` | `2026-03-05 19:15:00+00` | stale |
| `analytics.price_1h` | `2026-03-05 19:00:00+00` | stale |

Source mix in production shows the live path is not hot:

- `analytics.price_1m` latest rows are `source = databento_backfill`
- `analytics.price_5m` latest rows are `source = aggregated_backfill`
- `analytics.price_15m` latest rows are mostly historical `databento`, with the last `databento_live` row on `2026-01-29`
- `analytics.price_1h` latest `databento_live` row is also `2026-01-29`

This means the chart is effectively being served from stale historical/backfill artifacts, not an active live feed.

### P0. Local DB is toxic for migration work

Local DB inspection found:

- `analytics.zl_live` exists and has `0` rows
- `analytics.price_1d` does not exist
- `analytics.price_1m` does not exist
- `analytics.latest_price` does not exist
- `mkt.futures_1d` does not exist
- `mkt.fx_1d` does not exist

Yet `prisma/schema.prisma` defines the expected serving tables:

- `analytics.latest_price`
- `analytics.price_1d`
- `analytics.price_1m`
- `analytics.price_5m`
- `analytics.price_15m`
- `analytics.price_1h`

Additional drift evidence:

- `bash scripts/prisma_status.sh` reports local DB "up to date"
- `prisma migrate diff --from-config-datasource --to-schema prisma/schema.prisma` returns a large non-empty diff
- `_prisma_migrations` contains duplicate rolled-back entries, including:
  - `20260108_add_zl_live`
  - `20260115_quantile_schema_cleanup`

This is not a safe migration surface. Any "fix it with migrations" move against local right now has a high chance of making the situation worse.

### P1. The local live connector path cannot run as designed

The Python live connector at `scripts/ingest_databento_live_zl.py` depends on:

- `import databento as db`
- `DATABASE_URL`
- optional `INNGEST_EVENT_KEY`

Local environment failures:

- `.venv` does not contain the `databento` Python package
- `pyproject.toml` does not declare `databento`
- `requirements.txt` also does not declare `databento`
- `scripts/run_databento_live_zl_burst.sh` loads `.env` only
- local DB credentials currently live in root `.env.local`
- the burst script defaults `DATABENTO_SEND_INNGEST_EVENTS=0`

Impact:

- The Python connector cannot start locally in its current dependency state
- Even if fixed, the wrapper script misses the local DB env file
- Event forwarding is off by default, so derived 15m/1h/1d event updates are disabled unless explicitly overridden

### P1. ZL operational logging is incomplete

Production currently has:

- `0` rows in `ops.ingest_run` for ZL jobs matching `%zl-live%`, `%zl-daily%`, `%zl-1m%`, `%zl-15m%`, `%zl-1h%`
- `211` rows in `ops.pipeline_alerts` for those same ZL families

Interpretation:

- Failures are visible
- Successes are not reliably logged
- There is no clean job-level operational ledger for ZL price serving

This materially slows debugging because the dashboard can go stale without an equivalent success/failure history in `ops.ingest_run`.

### P1. Forecast path is stale upstream of the chart

Production forecast/training freshness:

- `forecasts.production_1d`: latest `2026-03-04`
- `training.matrix_1d`: latest `2026-03-03`
- `training.specialist_signals_1d`: latest `2026-03-03`
- `training.oof_core_1d`: latest `2026-02-20`

The forecast overlay was already disabled on the chart as a containment step because the overlay was mixing vintages and could remain stale. This audit confirms the upstream forecast path is in fact stale, not just mis-rendered.

### P2. Freshness monitoring is catching real problems, but at least one check is misleading

Production `freshness-monitor` alerts correctly flag:

- `analytics_price_1d_zl`
- `analytics_latest_price`
- `specialist_signals_any_bucket`
- `fx_cny_usd`

But `trump_effect_features` is being reported as `999` days stale even though:

- `training.specialist_features_trump_effect` has rows
- latest `as_of_date = 2026-03-03`

That points to a query/field assumption problem inside the freshness check, not just actual source staleness.

### P2. Some audit tooling is stale and no longer matches the app surface

Current scripts still target deprecated or obsolete paths:

- `scripts/audits/audit_chart_api.py` tests `/api/zl/intraday` and `/api/zl/price-1h`
- `scripts/audits/audit_e2e_data_flow.py` assumes `analytics.price_15m` plus `/api/zl/intraday`

Those scripts are no longer reliable indicators of real dashboard health.

## Code Path Notes

### Current chart path

`frontend/src/components/LightweightZlCandlestickChart.tsx` currently:

- fetches `/api/zl/price-1d?days=730`
- polls `/api/zl/live` every 10 seconds
- keeps the forecast overlay disabled via `ENABLE_FORECAST_OVERLAY = false`

This means current chart recovery is primarily about restoring:

- `analytics.price_1d`
- `analytics.price_1m`
- `analytics.latest_price`

### Registration drift note

Current `origin/main` source does not export/register `zl-15m` or `zl-1h` from:

- `frontend/src/inngest/functions.ts`
- `frontend/src/app/api/inngest/route.ts`

However, historical production alerts show `fusion-jobs-zl-15m` ran repeatedly on 2026-03-02 through 2026-03-13. That implies earlier deployments had a different active registration state than the current tracked source.

Because the latest production deployment is current to `main` on 2026-03-13, the safest conclusion is:

- those historical jobs were real
- they are not a dependable active refresh path going forward unless intentionally reintroduced

## What Is Safe Right Now

Safe:

- Keep the forecast overlay down on the chart
- Rotate production Databento credentials
- Trigger or rerun existing production jobs after the credential fix
- Backfill price-serving tables from Databento historical once auth is repaired
- Audit and rebuild local from a trusted baseline

Not safe:

- Running schema migrations against the current local DB
- Using the current local DB as a proxy for production correctness
- Assuming `prisma migrate status` is sufficient evidence of schema parity

## Recommended Recovery Plan

### Phase 0. Containment

1. Keep the chart forecast overlay disabled until forecast freshness and mixed-vintage handling are fixed.
2. Treat all migration work as blocked until a clean local rebuild plan exists.

### Phase 1. Restore production Databento access

1. Replace the Vercel production `DATABENTO_API_KEY` with a confirmed working key.
2. Redeploy `main`.
3. Immediately verify production Databento access with a read-only test request.

Exit criteria:

- production Databento request returns `200`
- no new `401` or `402` ZL Databento alerts in `ops.pipeline_alerts`

### Phase 2. Rehydrate chart-serving tables

1. Manually run or trigger:
   - `zl-daily`
   - `zl-1m-scheduled-backfill`
2. Verify:
   - `analytics.price_1d` moves to current market date
   - `analytics.price_1m` is within 30 minutes of now
   - `analytics.latest_price` is within 30 minutes of now
3. Decide whether `price_5m`, `price_15m`, and `price_1h` are still required by any current user-facing surface.

Exit criteria:

- chart daily route returns fresh rows
- live route returns current price without falling back to stale daily settlement

### Phase 3. Repair operational visibility

1. Add explicit success/failure logging for ZL jobs into `ops.ingest_run`.
2. Keep `ops.pipeline_alerts` for failure capture, but stop relying on it as the only operational trail.
3. Add a health query or dashboard specifically for:
   - `analytics.price_1d`
   - `analytics.price_1m`
   - `analytics.latest_price`
   - `forecasts.production_1d`

### Phase 4. Repair the local runtime, not the local schema

1. Add `databento` to the Python dependency manifest used by `.venv`.
2. Align env loading so the burst/live scripts read the same DB source as the rest of local tooling.
3. Decide explicitly whether the live connector should:
   - write direct DB rows only
   - emit Inngest events
   - do both
4. Document the ownership of the external live connector process. Right now it is an unmanaged cron-style dependency.

### Phase 5. Handle schema drift safely

1. Snapshot the current production schema and migration ledger.
2. Snapshot the local schema and migration ledger.
3. Decide between:
   - full local rebuild from trusted source, or
   - controlled cloud-to-local re-sync
4. Only after that, fix `scripts/prisma_status.sh` so it fails on:
   - duplicate rolled-back history
   - large datasource-vs-schema drift

This phase should be isolated from production freshness recovery.

### Phase 6. Repair forecast freshness

1. Trace why:
   - `training.matrix_1d` stopped at `2026-03-03`
   - `training.specialist_signals_1d` stopped at `2026-03-03`
   - `training.oof_core_1d` stopped at `2026-02-20`
   - `forecasts.production_1d` stopped at `2026-03-04`
2. Refresh the upstream data and rerun the forecast pipeline.
3. Re-enable the chart forecast overlay only after:
   - the forecast dates are current
   - mixed-vintage handling is explicit in the API/UI

## Verification Commands Run

- `npm --prefix frontend run lint`
- `npm --prefix frontend run build`
- `npx --prefix config prisma validate --schema prisma/schema.prisma`
- `bash scripts/prisma_status.sh`
- local and production `psql` inspection queries
- Databento historical API requests with:
  - a working key
  - the current production Vercel key

## File/Artifact Change Log

Files changed by this audit:

- `TO-DO/Audit/2026-03-13_chart_databento_operational_audit.md` (new report)

No code, schema, or runtime data was changed during this audit.
