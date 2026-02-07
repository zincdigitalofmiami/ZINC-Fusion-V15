# Frontend Endpoints - Fix Broken/Stale/Missing Data

## Configuration
- **Artifacts Path**: {@artifacts_path} -> `.zenflow/tasks/{task_id}`

---

## Workflow Steps

### [x] Step: Investigation and Planning
<!-- chat-id: cdd5e170-c10b-45dd-8be4-5907d25e7546 -->

Findings saved to `{@artifacts_path}/investigation.md`. Root causes:
- 3 missing database tables (`alt.news_1d`, `model.model_leaderboard`, `raw.fred_observations_1d`)
- 6 Inngest jobs writing to non-existent tables (silent failures)
- 3 API routes with SQL injection via template literal INTERVAL clauses
- Market drivers endpoint returns 200 + default scores when data is missing (users see fake data)
- Dashboard silently ignores forecast 404 errors (shows neutral gauges)
- No staleness enforcement on any endpoint

### [x] Step: Add missing database tables to Prisma schema
<!-- chat-id: 1eda8d44-d0f1-44c8-a72d-126c52dd7680 -->

Completed:
- Added `alt.news_1d` model to `prisma/schema.prisma` (columns: headline, source_id, source, url, source_url, published_at, event_date, content_snippet, specialist_tags, row_hash, ingested_at)
- Added `model.model_leaderboard` model (columns: run_id, model_name, rank, score_val, score_test, fit_time_seconds, pred_time_seconds, created_at)
- Added `supply.usda_nass_1d` model and fixed `nass-weekly.ts` to use it instead of banned `raw.fred_observations_1d`
- Prisma schema validates ✅

### [x] Step: Fix SQL injection in 3 API routes

Completed:
- Fixed `price-1m/route.ts` — template literal `INTERVAL '${minutes} minutes'` → parameterized `$1::interval`
- Fixed `price-5m/route.ts` — same pattern
- Fixed `intraday/route.ts` — same pattern + added input clamping
- ESLint clean on all 3 files ✅

### [x] Step: Replace mocks/placeholders with live data in market-drivers

Completed:
- Replaced FXI mock (`Promise.resolve([{ price: 0, change_20d: 0, change_5d: 0 }])`) with live CTE query against `mkt.etf_1d WHERE symbol = 'FXI'`
- Replaced BDRY mock (`Promise.resolve([{ change_20d: 0 }])`) with live CTE query against `mkt.etf_1d WHERE symbol = 'BDRY'`
- Replaced 4 specialist signal stubs (`Promise.resolve([])`) with live queries against `training.specialist_signals_1d`
- Replaced hardcoded defaults (VIX=20, crush=1.50, CNY=7.25, TPU=100) with null + null-guard scoring
- All `.catch()` fallbacks to null on query failures
- ESLint and TypeScript clean ✅

### [x] Step: Fix hash-check inconsistencies in Inngest jobs

Completed:
- Fixed `aei-trade.ts` — hash-check was against `alt.news_1d` but INSERT targets `alt.policy_news`. Changed to `alt.policy_news`.
- Fixed `cbp-trade.ts` — same fix
- Fixed `conab-news.ts` — same fix

### [x] Step: Fix TypeScript type safety in ai-intelligence.ts

Completed:
- Made `vix`, `boardCrush`, `cnyRate`, `tpu`, `fxiChange20d`, `fxiChange5d` optional in `MarketData` interface
- Fixed `!== null` → `!= null` for `ovx`, `oilShare`, `emv` (guards both null and undefined)
- Added optional chaining in `generateFallbackIntelligence` for nullable fields
- TypeScript compilation clean: `tsc --noEmit` passes with zero errors ✅

### [ ] Step: Fix silent failure responses in API routes

Read `{@artifacts_path}/investigation.md` for full context.

1. `/api/zl/chart/route.ts` - Return 404 when `rows.length === 0` instead of 200 with empty series
2. `/api/market-drivers/route.ts` - Add `data_status` field per driver ("live", "default", "stale") so clients can distinguish real data from defaults
3. `/api/vegas/brief/route.ts` - Return HTTP 503 when database connection fails for driver scores instead of 200 with ERROR in body
4. `/api/zl/forecast/route.ts` - Already returns 404 (correct), no change needed
5. Run `npm --prefix frontend run lint`

### [ ] Step: Fix client-side error handling

Read `{@artifacts_path}/investigation.md` for full context.

1. `frontend/src/app/dashboard/page.tsx:31-49` - Add error state when forecast fetch returns non-200; show "No forecast data available" instead of neutral gauges
2. `frontend/src/app/vegas-intel/page.tsx:88-122` - Add response status checks before parsing JSON
3. `ChrisTop4Drivers.tsx` - Check `data_status` field from market-drivers response; show visual indicator when data is defaulted or stale
4. Run `npm --prefix frontend run lint`

### [ ] Step: Verify all fixes

1. Run `npm --prefix frontend run lint`
2. Run `npm --prefix frontend test` (if tests exist)
3. Run `npx prisma validate --schema prisma/schema.prisma`
4. Verify no regressions in TypeScript compilation: `cd frontend && npx tsc --noEmit`
