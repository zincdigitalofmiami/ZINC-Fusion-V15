# BRONZE MIGRATION TRACKER

**Status:** ✅ DATABASE MIGRATION COMPLETE  
**Started:** January 11, 2026  
**Completed:** January 11, 2026  
**Authority:** Kirk (Architect)

---

## OVERVIEW

Upgraded all `raw.*` tables from "dump and overwrite" to institutional-grade Bronze layer with:
- ✅ PIT correctness (event_date + knowledge_time)
- ✅ Revision tracking (revision_no, supersedes_id)
- ✅ Quality gates (validation_status, quality_score, anomaly_flags)
- ✅ Provenance (source, source_url, raw_payload, ingestion_batch_id)
- ✅ Idempotency (row_hash - SHA256)
- ✅ Routing (specialist_tags[])
- ✅ UNIQUE constraints DROPPED (append-only enabled)

**Total Rows Migrated:** 6,274,507

**Reference Docs:**
- `BRONZE_CONTRACT_SPEC_LOCKED.md` — Column definitions and rules
- `RAW_SOURCE_SPECIALIST_MAPPING.md` — Table inventory and tag routing

---

## MIGRATION STATUS

| # | Table | Rows | DB Migration | Prisma Model | Inngest Job | Status |
|---|-------|------|--------------|--------------|-------------|--------|
| 1 | `raw.fred_observations_1d` | 505,724 | ✅ APPLIED | ✅ UPDATED | ✅ BRONZE | ✅ **COMPLETE** |
| 2 | `raw.cftc_cot_1w` | 18,372 | ✅ APPLIED | ✅ UPDATED | PENDING | ✅ **COMPLETE** |
| 3 | `raw.market_futures_1d` | 432,152 | ✅ APPLIED | ✅ UPDATED | PENDING | ✅ **COMPLETE** |
| 4 | `raw.market_futures_1h` | 4,967,276 | ✅ APPLIED | ✅ UPDATED | PENDING | ✅ **COMPLETE** |
| 5 | `raw.fx_spot_1d` | 72,135 | ✅ APPLIED | ✅ UPDATED | PENDING | ✅ **COMPLETE** |
| 6 | `raw.epa_rin_prices_1d` | 208 | ✅ APPLIED | ✅ UPDATED | PENDING | ✅ **COMPLETE** |
| 7 | `raw.usda_wasde_1m` | 12,548 | ✅ APPLIED | 🟡 PENDING | PENDING | ✅ **DB DONE** |
| 8 | `raw.usda_export_sales_1w` | 9,712 | ✅ APPLIED | 🟡 PENDING | PENDING | ✅ **DB DONE** |
| 9 | `raw.news_articles_1d` | 2,878 | ✅ APPLIED | 🟡 PENDING | PENDING | ✅ **DB DONE** |
| 10 | `raw.weather_noaa_1d` | 215,320 | ✅ APPLIED | 🟡 PENDING | PENDING | ✅ **DB DONE** |
| 11 | `raw.options_futures_1d` | 28,648 | ✅ APPLIED | 🟡 PENDING | PENDING | ✅ **DB DONE** |
| 12 | `raw.fred_series_metadata` | 27 | ⬜ SKIP | ⬜ SKIP | N/A | ⬜ **METADATA** |
| 13 | `raw.yahoo_equity_1d` | 9,534 | ✅ APPLIED | 🟡 PENDING | PENDING | ✅ **DB DONE** |
| 14 | `raw.crowd_beliefs_event` | 0 | ⬜ NEW | ⬜ EXISTS | PENDING | ⬜ **NEW TABLE** |

---

## CHANGES APPLIED TO ALL TABLES

### Columns Added (12 Bronze Contract Fields)
```
knowledge_time      TIMESTAMPTZ   -- PIT correctness
revision_no         INTEGER       -- Version tracking
supersedes_id       INTEGER       -- Links to prior version
is_preliminary      BOOLEAN       -- Data quality flag
validation_status   VARCHAR(20)   -- Gate status
quality_score       INTEGER       -- 0-100 quality metric
anomaly_flags       TEXT[]        -- Detection tags
source_url          VARCHAR       -- Provenance link
raw_payload         JSONB         -- Original API response
ingestion_batch_id  VARCHAR       -- Pipeline run ID
row_hash            VARCHAR(64)   -- SHA256 idempotency
specialist_tags     TEXT[]        -- Routing array
```

### Columns Renamed
- `as_of_date` → `event_date` (all tables)
- `report_date` → `event_date` (CFTC, USDA tables)
- `ts_event` → `event_time` (market_futures_1h)

### Constraints Dropped
- All `@@unique` constraints on (entity, date) pairs
- Enables append-only ingestion with revision tracking

### Indexes Created (per table)
- `idx_*_symbol_event` — Entity + date lookup
- `idx_*_knowledge_time` — PIT queries
- `idx_*_row_hash` — Idempotency check
- `idx_*_specialist_tags` — GIN array routing

---

## SPECIALIST TAG DISTRIBUTION

| Tag | Tables | Total Rows |
|-----|--------|------------|
| volatility | CFTC, futures, options | ~3.3M |
| fx | FRED, fx_spot, futures | ~1.4M |
| fed | FRED, CFTC, futures | ~1.4M |
| general | Various | ~1.1M |
| energy | FRED, CFTC, futures | ~700K |
| substitutes | CFTC, futures | ~560K |
| crush | CFTC, futures, USDA | ~250K |
| china | FRED, CFTC, futures, USDA | ~230K |
| biofuel | FRED, EPA, futures | ~65K |
| palm | futures | ~4K |

---

## NEXT STEPS

### Phase 2: Prisma Schema Alignment
Update remaining Prisma models to match Bronze contract:
- [ ] UsdaWasde1m
- [ ] UsdaExportSales1w
- [ ] NewsArticles1d
- [ ] WeatherNoaa1d
- [ ] OptionsFutures1d
- [ ] YahooEquity1d

### Phase 3: Inngest Job Rewrites
Convert all ingestion jobs to Bronze pattern:
```typescript
// 7-STAGE BRONZE PATTERN
1. extract()     — API call
2. validate()    — Schema check
3. dedupe()      — row_hash lookup
4. tag()         — specialist_tags assignment
5. insert()      — Append-only INSERT (no upsert!)
6. quarantine()  — Bad rows to ops.quarantined_record
7. log()         — Run metadata to ops.ingest_run
```

### Phase 4: OPS Tables
- [ ] Create `ops.ingest_run` — Pipeline tracking
- [ ] Create `ops.quarantined_record` — Validation failures
- [ ] Create `metadata.source` — Source confidence registry

---

## AUDIT LOG

| Timestamp | Action | Details |
|-----------|--------|---------|
| 2026-01-11 15:00 | Started | Created BRONZE_CONTRACT_SPEC_LOCKED.md |
| 2026-01-11 15:07 | Table 1 | fred_observations_1d migrated (505K rows) |
| 2026-01-11 15:12 | Table 2 | cftc_cot_1w migrated (18K rows) |
| 2026-01-11 15:15 | Tables 3-4 | market_futures_1d/1h confirmed (5.4M rows) |
| 2026-01-11 15:18 | Tables 5-13 | Remaining tables migrated (350K rows) |
| 2026-01-11 15:20 | Prisma | Schema validated, client regenerated |
| 2026-01-11 15:25 | Complete | All 12 active tables Bronze-compliant |
