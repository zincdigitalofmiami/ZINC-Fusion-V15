# Inngest Job Schema Fix Report

## Executive Summary

Fixed critical schema mismatches causing CFTC and Yahoo EOD jobs to fail silently (0 rows inserted).

## Root Cause

Jobs were trying to INSERT into column names that don't exist in the Prisma-managed database schema:

| Job | Used Column | Actual Column | Impact |
|-----|-------------|---------------|---------|
| **cftc-weekly** | `report_date` | `event_date` | 0 rows inserted (silently failing) |
| **yahoo-eod** | `as_of_date` | `event_date` | 0 rows inserted (silently failing) |

## Fixes Applied

### 1. CFTC Weekly (cftc-weekly.ts)
**Change**: `report_date` → `event_date` in INSERT statement

**Status**: ✅ Column name fixed
**Deployed**: Committed `fc7ae8c` to main, pushed to GitHub

**Remaining Issue**: Job uses `ON CONFLICT (event_date, symbol) DO UPDATE` but the table has no UNIQUE constraint on these columns - only `id` is primary key. This violates:
- Bronze Contract ("append-only, no upserts")
- PostgreSQL requirements (ON CONFLICT needs unique constraint)

**Recommendation**: Refactor to use `row_hash` idempotency pattern like `federal-register` job.

### 2. Yahoo EOD (yahoo-eod.ts)
**Change**: `as_of_date` → `event_date` in INSERT statement

**Status**: ✅ Column name fixed, ✅ ON CONFLICT will work
**Deployed**: Committed `fc7ae8c` to main, pushed to GitHub

**Note**: `market_futures_1d` has `PRIMARY KEY (event_date, symbol)` so the `ON CONFLICT` clause works correctly.

## Verification

```sql
-- Tested direct INSERT with event_date column
INSERT INTO raw.market_futures_1d 
  (event_date, symbol, open, high, low, close, volume, source, ingested_at)
VALUES ('2026-01-12', 'TEST', 100.0, 101.0, 99.0, 100.5, 1000, 'test_fix', NOW());
-- ✅ SUCCESS
```

## Schema Governance Findings

### Tables NOT in Prisma Schema (Created Dynamically)

6 jobs create tables via `CREATE TABLE IF NOT EXISTS` (outside Prisma governance):

| Job | Table | Status |
|-----|-------|--------|
| nyfed-daily | `raw.nyfed_rates_1d` | ⚠️ Not in Prisma |
| ice-releases | `raw.ice_releases_event` | ⚠️ Not in Prisma |
| aei-trade | `raw.aei_articles_event` | ⚠️ Not in Prisma |
| cbp-trade | `raw.cbp_trade_event` | ⚠️ Not in Prisma |
| conab-news | `raw.conab_news_event` | ⚠️ Not in Prisma |
| farmdoc-rins | `raw.farmdoc_articles_event` | ⚠️ Not in Prisma |

**Impact**: These tables exist and work, but lack:
- Type safety (Prisma Client doesn't know about them)
- Migration tracking
- Schema documentation

**Recommendation**: Add these 6 event tables to `prisma/schema.prisma` and generate migration.

## Column Naming Patterns (Intentional Design)

Verified these are NOT drift - they're semantically correct:

| Table | Column | Reason |
|-------|--------|--------|
| `epa_rin_prices_1d` | `price` | Single price per RIN type |
| `fred_observations_1d` | `value` | Economic indicator value (not a price) |
| `fx_spot_1d` | `rate` | Exchange rate (not OHLCV) |
| `market_futures_*` | `close` | OHLCV data - close is one of four prices |
| `zl_live` | `price` | Current price (real-time ticker) |

## Next Steps

### Priority 1: Test in Production
- [ ] Wait for next scheduled run (Yahoo: 5AM CT Mon-Fri, CFTC: 4PM ET Friday)
- [ ] Monitor `ops.ingest_run` for `rows_inserted > 0`
- [ ] Verify freshness with `scripts/check_freshness.py`

### Priority 2: CFTC Bronze Compliance
- [ ] Remove `ON CONFLICT` clause from CFTC job
- [ ] Implement `row_hash` idempotency check (like federal-register job)
- [ ] Test with Bronze Contract validator

### Priority 3: Governance
- [ ] Add 6 event tables to Prisma schema
- [ ] Run `prisma db pull` to generate types
- [ ] Generate migration for tracking

### Priority 4: RSS/XML Jobs
- [ ] Create jobs for Priority 0 sources from `.claude/memory/INNGEST_DATA_SOURCES.md`
- [ ] farm_policy_news, farmdoc_daily, reuters_commodities, usda_press

## Files Changed

```
frontend/src/inngest/cftc-weekly.ts    (report_date → event_date)
frontend/src/inngest/yahoo-eod.ts      (as_of_date → event_date)
```

## Commit

```
fc7ae8c - fix(inngest): correct column names for CFTC and Yahoo jobs
```

## References

- Prisma schema: `prisma/schema.prisma` (lines 12-59 for CFTC, 149-177 for market_futures)
- Bronze Contract: `AGENTS.md` (append-only, row_hash idempotency)
- Freshness checker: `scripts/check_freshness.py`
