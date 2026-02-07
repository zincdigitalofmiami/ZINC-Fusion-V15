# Inngest Bugwork Investigation

## Bug Summary

Inngest jobs run for a few days then stall/stop. A massive Prisma DB bill resulted from what appears to be excessive data pulls that should have been ingested and cached via Inngest.

## Root Cause Analysis

Three interconnected issues are driving both the stalling and the cost:

### Root Cause 1: Duplicate Database Connection Pools (CRITICAL - Cost Driver)

**41 out of 43 Inngest function files** create their own `new Pool()` instance instead of importing the shared pool from `frontend/src/lib/db.ts`.

**Shared pool (correct)** at `frontend/src/lib/db.ts`:
```
max: 10, idleTimeoutMillis: 30000, connectionTimeoutMillis: 5000
```

**41 duplicate pools (incorrect)** across Inngest files:
```
connectionString only, no max, no idleTimeout, no connectionTimeout
```

**Impact:**
- Without `max`, each Pool defaults to **10 connections** but without `idleTimeoutMillis`, connections never close
- 41 pools x 10 connections = **410 potential open connections** to Prisma Postgres
- Prisma Postgres bills by connection-hours and query volume
- Connections left open indefinitely consume billable resources even when idle
- When multiple cron jobs fire simultaneously (every 8 hours), connection storms occur

**Affected files (all 41):**
- aei-trade.ts, argentina-crush-monthly.ts, board-crush-daily.ts, cbp-trade.ts, cftc-weekly.ts, conab-news.ts, conab-production-monthly.ts, cpo-daily.ts, databento-etf-daily.ts, databento-etf-vwap.ts, databento-futures-1h.ts, databento-futures-daily.ts, databento-fx-daily.ts, databento-options-daily.ts, databento-statistics-daily.ts, eia-biodiesel-monthly.ts, epa-rin-prices-daily.ts, farmdoc-rins.ts, federal-register.ts, fred-blog-daily.ts, fred-daily.ts, fx-databento-spot-daily.ts, fx-spot-daily.ts, glide-vegas.ts, mpob-palm-monthly.ts, nass-weekly.ts, noaa-weather-daily.ts, nyfed-daily.ts, openmeteo-weather-daily.ts, options-staleness-check.ts, profarmer-daily.ts, usda-export-sales-weekly.ts, usda-wasde-monthly.ts, zl-15m.ts, zl-1h.ts, zl-daily.ts, zl-live.ts
- Plus 4 files that create pools inside step functions: eia-today.ts, ice-releases.ts, usda-press.ts, whitehouse-press.ts

---

### Root Cause 2: N+1 Query Patterns / Row-by-Row Upserts (CRITICAL - Cost Driver)

Several high-frequency Inngest functions execute individual database queries inside loops rather than batching.

**Worst offenders:**

| Function | Pattern | Queries per Run | Frequency | Daily Query Estimate |
|----------|---------|-----------------|-----------|---------------------|
| `databento-futures-daily` | upsert per bar per symbol | ~558 | 3x/day | 1,674 |
| `databento-etf-daily` | upsert per bar per ETF | ~5,750 | 1x/day | 5,750 |
| `databento-etf-backfill` | upsert per bar per ETF (10yr) | ~57,500 | on-demand | 57,500+ |
| `glide-vegas` | INSERT per row inside transaction | ~1,000 | 4x/day | 4,000 |
| `conab-news` | hashExists + INSERT per RSS item | ~200 | 3x/day | 600 |

**Example from `databento-futures-daily.ts`:**
- Loops over 18+ symbols
- For each symbol: 1 `getMaxEventDate()` query + N upserts (one per daily bar)
- Each upsert acquires a new connection from the pool, executes, releases
- With 30 days of bars per symbol: 18 x 31 = 558 individual round-trips

**Combined daily query volume from Inngest functions: 10,000-20,000+ queries/day** in normal operation. Backfill operations can spike to 50,000+ queries.

---

### Root Cause 3: Missing Timeouts and Stalling Mechanisms (CRITICAL - Stalling Driver)

#### 3a. ProFarmer Puppeteer Scraper (`profarmer-daily.ts`)

The ProFarmer scraper is the most likely source of stalling jobs:

- **No default page timeouts:** `page.setDefaultTimeout()` is never called. Operations like `page.evaluate()` can hang indefinitely.
- **`waitUntil: 'networkidle2'`** is used for all navigation. If ProFarmer has persistent connections (analytics, WebSockets), the page never reaches "idle" and hangs until the 60s navigation timeout.
- **Browser leak on login failure (line ~478):** When login fails, the function returns without calling `browser.close()`, leaving a Chromium process running.
- **Sequential report scraping with no circuit breaker:** 4 reports scraped in sequence, each can fetch up to 15 articles at 30s timeout each = potential 20-minute runtime.
- **Backfill function:** 50 pages x 4 reports = 200 page navigations with no overall timeout.
- **Silent error swallowing:** Multiple `catch { }` blocks that break or continue without logging.

#### 3b. NOAA Weather (`noaa-weather-daily.ts`)

- **Unbounded `while(true)` loop** with 60-second sleep on rate limit (line 114)
- If the NOAA API repeatedly returns 429 (rate limit), the function sleeps 60s indefinitely
- No maximum retry count on the rate limit path

#### 3c. Functions Missing Fetch Timeouts

These functions make HTTP requests without AbortController timeouts:
- All `databento-*.ts` files (6 files) - CSV downloads from Databento
- `whitehouse-press.ts` - HTML scraping
- `usda-press.ts` - HTML scraping
- `openmeteo-weather-daily.ts` - Weather API
- `conab-*.ts` (2 files) - RSS feeds
- `ice-releases.ts` - HTML scraping of 20+ URLs

#### 3d. No `cancelOn` Configuration

Zero Inngest functions use `cancelOn`. This means once a job starts, it cannot be externally cancelled by a newer run. If a stalled job eventually retries, it creates duplicate processing.

---

## How These Issues Interact (Cascade Failure)

1. **Cron fires every 8 hours** - ~30 functions start simultaneously
2. **Each creates its own Pool** - 30 new Pool instances, potentially 300 new DB connections
3. **N+1 queries begin** - Hundreds of individual queries per function
4. **DB connection limit approached** - Queries start queuing, timeouts increase
5. **Some functions stall** on external API calls (Databento CSV download, ProFarmer scraping, NOAA rate limit)
6. **Stalled functions hold Pool connections open** - idle connections never release (no `idleTimeoutMillis`)
7. **Next cron cycle fires** - Creates another 300 connections on top of stale ones
8. **Connection exhaustion** - New jobs fail to connect, retry, creating more load
9. **Prisma DB bills accumulate** - Hundreds of idle connections billed by connection-time, thousands of queries billed by volume

---

## Affected Components

| Component | Impact | Severity |
|-----------|--------|----------|
| All 41 Inngest function files | Duplicate Pool instances | CRITICAL |
| `databento-futures-daily.ts` | N+1 upserts (558/run) | HIGH |
| `databento-etf-daily.ts` | N+1 upserts (5,750/run) | HIGH |
| `glide-vegas.ts` | Row-by-row INSERT in transaction | HIGH |
| `profarmer-daily.ts` | Browser leak + no timeouts | HIGH (stalling) |
| `noaa-weather-daily.ts` | Unbounded rate-limit sleep | MEDIUM (stalling) |
| 6x `databento-*.ts` files | Missing fetch timeouts | MEDIUM (stalling) |
| `frontend/src/lib/db.ts` | Correct but unused by Inngest | N/A (reference) |

---

## Proposed Solution

### Fix 1: Consolidate Database Pools (Highest Priority - Cost Reduction)

Replace all 41 duplicate `new Pool()` instances with a single shared import.

**Approach:** All Inngest files should import from `frontend/src/lib/db.ts`:
```typescript
import pool from '@/lib/db';
// or: import pool, { query } from '@/lib/db';
```

Remove the local `const pool = new Pool({...})` from each file.

**Expected impact:** Reduces max connections from ~410 to 10. Idle connections auto-close after 30s. Connection timeout drops from 30s default to 5s.

### Fix 2: Batch Database Operations (High Priority - Cost Reduction)

Replace row-by-row upserts with batch INSERT statements.

**For `databento-futures-daily.ts` and similar:**
- Collect all rows in memory first
- Execute a single multi-row INSERT with ON CONFLICT
- Reduces 558 queries to ~1-2 per run

**For `glide-vegas.ts`:**
- Use multi-row VALUES clauses (batches of 100-500 rows)
- Reduces 1,000 individual INSERTs to ~10

### Fix 3: Add Timeouts to All External Fetches (High Priority - Stalling)

Add AbortController-based timeouts to all HTTP/API calls that lack them:
- All `databento-*.ts` CSV fetches
- `whitehouse-press.ts`, `usda-press.ts` HTML scraping
- `openmeteo-weather-daily.ts` API calls
- `conab-*.ts` RSS feeds
- `ice-releases.ts` multi-URL scraping

### Fix 4: Fix ProFarmer Scraper (High Priority - Stalling)

1. Add `page.setDefaultTimeout(30000)` after page creation
2. Fix browser leak on login failure (add `browser.close()` before early return)
3. Change `waitUntil: 'networkidle2'` to `'domcontentloaded'`
4. Add overall timeout/circuit breaker per report (max 3 minutes)
5. Replace silent `catch { }` blocks with proper error logging

### Fix 5: Fix NOAA Weather Unbounded Loop (Medium Priority - Stalling)

Add a maximum retry count (e.g., 5) for the rate-limit sleep path in the `while(true)` loop.

### Fix 6: Add `cancelOn` to Cron Functions (Medium Priority - Operational)

Add `cancelOn` configuration to prevent stale runs from overlapping with new ones. When a new cron trigger fires, the previous incomplete run should be cancelled.

---

## Validation Plan

After implementing fixes:
1. Check Prisma DB connection count: `SELECT count(*) FROM pg_stat_activity`
2. Monitor query volume in Prisma dashboard before/after
3. Verify Inngest job completion rates in Inngest dashboard
4. Confirm no jobs stall beyond 5 minutes
5. Watch Prisma billing for reduction in connection-hours and query volume

---

## Implementation Priority Order

1. **Fix 1: Consolidate Pools** - Single biggest cost driver, mechanical change
2. **Fix 4: ProFarmer timeouts** - Most likely stalling source
3. **Fix 2: Batch upserts** - Second biggest cost driver (databento-futures, databento-etf, glide-vegas)
4. **Fix 3: Add fetch timeouts** - Prevents stalling in 8+ functions
5. **Fix 5: NOAA loop guard** - Targeted fix
6. **Fix 6: cancelOn** - Operational improvement
