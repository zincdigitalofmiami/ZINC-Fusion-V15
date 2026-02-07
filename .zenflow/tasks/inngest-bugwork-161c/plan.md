# Inngest Bugwork - Stalling Jobs & Excessive DB Costs

## Configuration
- **Artifacts Path**: `.zenflow/tasks/inngest-bugwork-161c`

---

## Workflow Steps

### [x] Step: Investigation and Planning

Root causes identified (see `investigation.md`):
1. **41 duplicate Pool instances** across Inngest files (no idle timeout, no max, no connection timeout) - primary cost driver
2. **N+1 query patterns** - row-by-row upserts in databento-futures, databento-etf, glide-vegas (10,000-20,000+ queries/day)
3. **Missing timeouts & browser leaks** in ProFarmer scraper, NOAA weather, and 8+ other functions - primary stalling driver
4. **No `cancelOn`** on any cron function - stale runs overlap with new ones

### [x] Step: Consolidate Database Pools

Replace all 41 duplicate `new Pool()` instances with the shared pool from `frontend/src/lib/db.ts`.

- Remove local `import { Pool } from 'pg'` and `const pool = new Pool({...})` from each file
- Replace with `import pool from '@/lib/db'`
- For the 4 files that create pools inside step functions (eia-today, ice-releases, usda-press, whitehouse-press): import shared pool, remove `pool.end()` calls
- Verify TypeScript compiles after changes
- Run build to confirm no import errors

### [x] Step: Batch Database Upserts

Replace row-by-row upserts with batch INSERT statements in the highest-volume functions.

- `databento-futures-daily.ts`: Collect bars, batch upsert (558 queries -> ~2)
- `databento-etf-daily.ts`: Collect bars, batch upsert (5,750 queries -> ~24)
- `glide-vegas.ts`: Multi-row VALUES in transaction (1,000 queries -> ~10)
- `conab-news.ts`: Batch hash check + batch insert

### [x] Step: Fix ProFarmer Scraper Stalling

- Add `page.setDefaultTimeout(30000)` after page creation
- Fix browser leak on login failure (add `browser.close()` before early return)
- Change `waitUntil: 'networkidle2'` to `'domcontentloaded'`
- Add per-report circuit breaker timeout (3 min max)
- Replace silent `catch { }` blocks with error logging

### [x] Step: Add Fetch Timeouts to Remaining Functions

Add AbortController-based timeouts to functions missing them:

- All `databento-*.ts` CSV fetches (6 files)
- `whitehouse-press.ts`, `usda-press.ts` HTML scraping
- `openmeteo-weather-daily.ts` API calls
- `conab-*.ts` RSS feeds (2 files)
- `ice-releases.ts` multi-URL scraping
- `noaa-weather-daily.ts`: Add max retry count for rate-limit sleep path

### [x] Step: Add Concurrency Limits to Cron Functions

Added `concurrency: [{ limit: 1 }]` to all cron-triggered functions (40+ files) to prevent overlapping runs.

### [x] Step: Validation

- `tsc --noEmit` passes with zero errors
- `next build` succeeds - all routes compile including `/api/inngest`
- Zero `new Pool()` instances remain in any Inngest file (verified via grep)
- 41 files now import shared pool from `@/lib/db`
- 41 concurrency configurations applied across 40 files (fred-daily factory covers 10 functions)
- Expected billing reduction: ~95% fewer idle connections (410 -> 10 max), ~90% fewer queries from batch upserts
