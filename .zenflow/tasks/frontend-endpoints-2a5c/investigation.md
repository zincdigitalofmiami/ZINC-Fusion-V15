# Frontend Endpoint Failures - Investigation Report

## Executive Summary

The frontend fails due to three categories of issues: **missing database tables**, **silent data defaults masking failures**, and **SQL safety issues**. The system has 24 API routes querying 30+ tables across 12 schemas, with 45+ Inngest functions populating data. When data is missing or stale, most endpoints return `200 OK` with default/placeholder values instead of error responses, making failures invisible to the user.

---

## Category 1: Missing Tables (Broken References)

### 1A. `model.model_leaderboard` - NOT IN PRISMA SCHEMA
- **Route:** `frontend/src/app/api/quant/overview/route.ts:126`
- **Impact:** `/api/quant/overview` returns 500 error
- **Fix:** Add `model_leaderboard` model to `prisma/schema.prisma` in the `model` schema, then migrate

### 1B. `alt.news_1d` - NOT IN PRISMA SCHEMA
- **Routes (6 Inngest jobs will fail on write):**
  - `frontend/src/inngest/whitehouse-press.ts`
  - `frontend/src/inngest/aei-trade.ts`
  - `frontend/src/inngest/cbp-trade.ts`
  - `frontend/src/inngest/conab-news.ts`
  - `frontend/src/inngest/ice-releases.ts`
- **Impact:** Alternative news data never gets ingested. Market drivers lose news sentiment inputs.
- **Fix:** Add `news_1d` model to `prisma/schema.prisma` in the `alt` schema with columns: `article_id`, `event_date`, `published_at`, `headline`, `content`, `url`, `author`, `source`, `zl_sentiment`, `specialist_tags`, `ingested_at`, `knowledge_time`, `row_hash`, `raw_payload`, `ingestion_batch_id`

### 1C. `raw.fred_observations_1d` - NOT IN PRISMA SCHEMA (banned schema)
- **Route:** `frontend/src/inngest/nass-weekly.ts:45,97`
- **Impact:** NASS weekly data never ingested
- **Fix:** Route to an existing schema (e.g., `econ.*` or `supply.*`) instead of `raw.*` (banned per AGENTS.md)

---

## Category 2: Silent Failures (200 OK with Placeholder Data)

### 2A. `/api/market-drivers` - Default scores mask missing data
- **File:** `frontend/src/app/api/market-drivers/route.ts:937-977`
- **When queries return 0 rows:**
  - VIX defaults to `20`
  - Crush margin defaults to `1.50`
  - CNY rate defaults to `7.25`
  - EPU/TPU defaults to `100`
- **Returns 200 OK** with these defaults. Client has no way to know data is fake.
- **Additional disabled sources:**
  - FXI (China ETF) - hardcoded 0% change (line 856-861, data quality issues)
  - BDRY (shipping) - hardcoded 0% change (line 901-909)
  - All specialist signals - empty arrays (models not trained)
- **Fix:** Add a `data_status` field per driver ("live", "default", "stale") and surface it in the UI. Return 503 if ALL queries fail.

### 2B. `/api/zl/chart` - Empty array on no data
- **File:** `frontend/src/app/api/zl/chart/route.ts:24-45`
- **Returns:** `{symbol: 'ZL', series: []}` with status 200 when no rows exist
- **Client behavior:** Renders empty chart with no error indication
- **Fix:** Return 404 when `rows.length === 0`

### 2C. `/api/vegas/brief` - Placeholder scores when DB fails
- **File:** `frontend/src/app/api/vegas/brief/route.ts:346-360`
- **Returns 200 OK** with `status: 'ERROR'` embedded in the JSON body (not HTTP status)
- **Fix:** Return HTTP 503 when database connection fails for driver scores

### 2D. Dashboard silently ignores forecast 404
- **File:** `frontend/src/app/dashboard/page.tsx:31-49`
- **When `/api/zl/forecast` returns 404:** Silently sets `forecastData = null`, removes loading spinner, shows neutral gauges (value=50)
- **Fix:** Set an error state and render an explicit "No forecast data available" message

---

## Category 3: SQL Safety Issues

### 3A. SQL Injection via Template Literals in INTERVAL Clauses
- **Files affected:**
  - `frontend/src/app/api/zl/price-1m/route.ts:37`
  - `frontend/src/app/api/zl/price-5m/route.ts:37`
  - `frontend/src/app/api/zl/intraday/route.ts:33`
- **Pattern:** `WHERE timestamp >= NOW() - INTERVAL '${variable} minutes'` (direct string interpolation)
- **Correct pattern (used in price-1d and price-1h):** `WHERE event_date >= CURRENT_DATE - $1::interval` with parameterized `[`${days} days`]`
- **Fix:** Convert all three routes to use parameterized queries like the working routes

---

## Category 4: Data Staleness

### 4A. No staleness enforcement on any endpoint
- **Stale data is served as current with no warning:**
  - VIX could be 8+ hours old (FRED update cycle)
  - EPU (USEPUINDXM) could be 45+ days old (monthly publication)
  - Board crush could be 24h old
  - CNY/USD could be 5+ days old (FRED lag)
  - Forecasts age is unknown (no training pipeline defined in frontend)
- **market-drivers has a `data_quality` object** but only flags age, doesn't block stale data
- **Fix:** Add configurable staleness thresholds. If data exceeds threshold, mark it explicitly as stale in the response AND in the UI.

### 4B. Forecast tables may never get populated
- **No Inngest function writes to `forecasts.production_*d_1d` tables**
- These are presumably populated by the Python training pipeline
- If training hasn't run, forecast endpoints always return 404
- **Fix:** Add a monitoring check or Inngest function that validates forecast freshness

---

## Category 5: Connection Pool Exhaustion

### 5A. `/api/market-drivers` runs 21 parallel queries
- **File:** `frontend/src/app/api/market-drivers/route.ts`
- **Pool max:** 4 connections (configurable via `PGPOOL_MAX`)
- **Risk:** Under concurrent load, 21 queries from a single request can exhaust the pool
- **Fix:** Increase pool size to 8-10, or batch the market-drivers queries into fewer calls

---

## Proposed Fix Priority

| Priority | Issue | Category | Impact |
|----------|-------|----------|--------|
| P0 | Add `alt.news_1d` table to schema | Missing table | 6 Inngest jobs broken |
| P0 | Add `model.model_leaderboard` to schema | Missing table | Quant overview page broken |
| P0 | Fix SQL injection in 3 routes | SQL safety | Security vulnerability |
| P1 | Fix `nass-weekly.ts` to use valid schema | Missing table | Data ingestion broken |
| P1 | Return proper error codes instead of 200+defaults | Silent failures | Users see fake data |
| P1 | Add error states to dashboard when forecasts unavailable | Silent failures | Misleading UI |
| P2 | Add data staleness thresholds and UI warnings | Staleness | Users trust stale data |
| P2 | Increase connection pool / batch market-drivers queries | Performance | Reliability under load |
| P3 | Add missing timestamp indexes on zl_price_1m, zl_price_5m | Performance | Slow queries |
| P3 | Add ESLint to CI quality gates | CI/CD | Code quality drift |

---

## Affected Components Summary

### API Routes with Issues (8 routes):
1. `/api/zl/price-1m` - SQL injection
2. `/api/zl/price-5m` - SQL injection
3. `/api/zl/intraday` - SQL injection
4. `/api/zl/chart` - Silent empty response
5. `/api/zl/forecast` - Proper 404, but client ignores it
6. `/api/market-drivers` - Default scores mask failures
7. `/api/vegas/brief` - Error hidden in response body
8. `/api/quant/overview` - Queries non-existent table

### Inngest Jobs with Issues (7 jobs):
1. `whitehouse-press` - Writes to non-existent `alt.news_1d`
2. `aei-trade` - Same
3. `cbp-trade` - Same
4. `conab-news` - Same
5. `ice-releases` - Same
6. `nass-weekly` - Writes to banned `raw.fred_observations_1d`
7. (No job populates `forecasts.production_*d_1d`)

### Client Pages with Issues (3 pages):
1. `/app/dashboard/page.tsx` - Silently ignores forecast errors
2. `/app/vegas-intel/page.tsx` - No error handling on API responses
3. `ChrisTop4Drivers.tsx` - Cannot detect default/placeholder data
