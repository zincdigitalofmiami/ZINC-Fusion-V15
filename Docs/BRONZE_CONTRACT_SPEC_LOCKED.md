# BRONZE CONTRACT SPEC — LOCKED

**Status:** LOCKED  
**Date:** January 11, 2026  
**Authority:** Kirk (Architect)

---

## PURPOSE

This document defines the institutional-grade Bronze layer contract for ZINC-FUSION-V15. Every `raw.*` table must conform to this spec to enable:

- Point-in-time (PIT) correct backtests
- Revision tracking (revisions are signal)
- Reproducible OOF training
- Quality-gated data promotion
- Audit/provenance trail

---

## BRONZE CONTRACT COLUMNS

Every `raw.*` table MUST include these columns:

### TEMPORAL (PIT Correctness)

| Column | Type | Required | Description |
|--------|------|----------|-------------|
| `event_date` | DATE | Yes | When the data happened (or `event_time` TIMESTAMPTZ for sub-daily) |
| `knowledge_time` | TIMESTAMPTZ | Yes | When we learned/ingested it. DEFAULT NOW() |

### REVISION TRACKING

| Column | Type | Required | Description |
|--------|------|----------|-------------|
| `revision_no` | INTEGER | Yes | 1 = first release, 2+ = revisions. DEFAULT 1 |
| `supersedes_id` | INTEGER | No | FK to same table's id (the row this revises) |
| `is_preliminary` | BOOLEAN | Yes | TRUE = may be revised, FALSE = final. DEFAULT TRUE |

### QUALITY GATES

| Column | Type | Required | Description |
|--------|------|----------|-------------|
| `validation_status` | VARCHAR(20) | Yes | 'pending', 'validated', 'quarantined', 'failed'. DEFAULT 'pending' |
| `quality_score` | INTEGER | No | 0-100 composite quality score |
| `anomaly_flags` | TEXT[] | No | Array of detected anomalies |

### PROVENANCE

| Column | Type | Required | Description |
|--------|------|----------|-------------|
| `source` | VARCHAR | Yes | Data source identifier ('fred_api', 'yahoo_finance', etc.) |
| `source_url` | VARCHAR | No | Specific API endpoint or URL |
| `raw_payload` | JSONB | No | Original API response for audit |
| `ingestion_batch_id` | VARCHAR | Yes | Links to ops.ingest_run |

### IDEMPOTENCY

| Column | Type | Required | Description |
|--------|------|----------|-------------|
| `row_hash` | VARCHAR(64) | Yes | SHA256 of payload for deduplication |

### ROUTING

| Column | Type | Required | Description |
|--------|------|----------|-------------|
| `specialist_tags` | TEXT[] | Yes | Deterministic routing tags per RAW_SOURCE_SPECIALIST_MAPPING |

---

## CRITICAL RULES

### 1. NO UNIQUE CONSTRAINTS ON (entity_key, event_date)

**WRONG:**
```prisma
@@unique([seriesId, asOfDate])  // Forces upsert!
```

**RIGHT:**
```prisma
@@index([seriesId, eventDate])  // Allows multiple rows (revisions)
@@index([rowHash])              // Idempotency check
```

### 2. APPEND-ONLY — NO ON CONFLICT DO UPDATE

**WRONG:**
```sql
ON CONFLICT (series_id, as_of_date) DO UPDATE SET value = EXCLUDED.value
```

**RIGHT:**
```sql
-- Check row_hash first, skip if duplicate
-- Check for revision (value changed), increment revision_no
-- INSERT only
```

### 3. ROW-LOCAL TRANSFORMS ONLY

Allowed at Bronze:
- `log_price = LN(close)`
- `row_hash = SHA256(payload)`
- Timezone normalization
- Unit normalization

NOT allowed at Bronze:
- `simple_return_1d = (close - lag)/lag` (requires historical state)
- Forward-fill (policy decision)
- Any rolling/lagged features

---

## OPS TABLES

### ops.ingest_run

```sql
CREATE TABLE ops.ingest_run (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  job_name            VARCHAR NOT NULL,
  started_at          TIMESTAMPTZ DEFAULT NOW(),
  completed_at        TIMESTAMPTZ,
  status              VARCHAR DEFAULT 'running',  -- running, success, partial, failed
  rows_attempted      INTEGER DEFAULT 0,
  rows_inserted       INTEGER DEFAULT 0,
  rows_skipped        INTEGER DEFAULT 0,
  rows_quarantined    INTEGER DEFAULT 0,
  cursor_position     JSONB,
  error_message       TEXT
);
CREATE INDEX idx_ingest_run_job ON ops.ingest_run(job_name, started_at);
```

### ops.quarantined_record

```sql
CREATE TABLE ops.quarantined_record (
  id                  SERIAL PRIMARY KEY,
  source_table        VARCHAR NOT NULL,
  ingest_run_id       UUID REFERENCES ops.ingest_run(id),
  attempted_at        TIMESTAMPTZ DEFAULT NOW(),
  raw_payload         JSONB NOT NULL,
  validation_errors   TEXT[] NOT NULL,
  severity            VARCHAR DEFAULT 'error',  -- warning, error, critical
  resolution_status   VARCHAR DEFAULT 'pending',
  resolved_at         TIMESTAMPTZ,
  resolved_by         VARCHAR
);
CREATE INDEX idx_quarantine_table ON ops.quarantined_record(source_table);
CREATE INDEX idx_quarantine_status ON ops.quarantined_record(resolution_status);
```

### metadata.source

```sql
CREATE TABLE metadata.source (
  id                  VARCHAR PRIMARY KEY,  -- 'fred_api', 'cftc_api', etc.
  name                VARCHAR NOT NULL,
  api_url             VARCHAR,
  default_confidence  DECIMAL(3,2) NOT NULL,  -- 0.00-1.00
  expected_lag_minutes INTEGER,
  revisions_expected  BOOLEAN DEFAULT FALSE,
  release_schedule    VARCHAR,
  tag_rules           JSONB,  -- { "series_pattern": ["tags"] }
  is_active           BOOLEAN DEFAULT TRUE,
  created_at          TIMESTAMPTZ DEFAULT NOW()
);
```

---

## TABLE UPGRADE SEQUENCE

| # | Table | Current Status | Priority |
|---|-------|----------------|----------|
| 1 | `raw.fred_observations_1d` | EXISTS - needs upgrade | **P0** (template) |
| 2 | `raw.cftc_cot_1w` | EXISTS - needs upgrade | P0 |
| 3 | `raw.market_futures_1d` | EXISTS - needs upgrade | P0 |
| 4 | `raw.market_futures_1h` | EXISTS - needs upgrade | P1 |
| 5 | `raw.fx_spot_1d` | EXISTS - needs upgrade | P1 |
| 6 | `raw.epa_rin_prices_1d` | EXISTS - needs upgrade | P1 |
| 7 | `raw.usda_wasde_1m` | EXISTS - needs upgrade | P1 |
| 8 | `raw.usda_export_sales_1w` | EXISTS - needs upgrade | P1 |
| 9 | `raw.news_articles_1d` | EXISTS - needs upgrade | P2 |
| 10 | `raw.weather_noaa_1d` | EXISTS - needs upgrade | P2 |
| 11 | `raw.options_futures_1d` | EXISTS - needs upgrade | P2 |
| 12 | `raw.fred_series_metadata` | EXISTS - metadata, minimal changes | P3 |
| 13 | `raw.yahoo_equity_1d` | EXISTS - needs upgrade | P2 |
| 14 | `raw.crowd_beliefs_event` | EXISTS - needs upgrade | P2 |
| 15-29 | New tables from MAPPING doc | MISSING - create with contract | P1-P2 |

---

## SOURCE CONFIDENCE REGISTRY

| Source ID | Name | Confidence | Revisions Expected |
|-----------|------|------------|-------------------|
| `fred_api` | FRED | 0.95 | Yes (GDP, employment) |
| `cftc_api` | CFTC | 0.95 | No |
| `yahoo_finance` | Yahoo Finance | 0.75 | No |
| `usda_wasde` | USDA WASDE | 0.95 | Yes |
| `usda_fas` | USDA FAS | 0.90 | Yes |
| `epa_emts` | EPA EMTS | 0.90 | No |
| `eia_api` | EIA | 0.90 | Yes |
| `noaa_cdo` | NOAA | 0.85 | No |
| `polymarket` | Polymarket | 0.70 | No |
| `scrapecreators` | ScrapeCreators | 0.60 | No |

---

## SPECIALIST TAG RULES

From RAW_SOURCE_SPECIALIST_MAPPING.md:

### FRED Series → Tags

| Series Pattern | Tags |
|----------------|------|
| DFF, FEDFUNDS, DGS*, T10Y2Y | fed |
| DEXBZUS, DEXCHUS, DEXARUS, DTWEX* | fx |
| VIXCLS, STLFSI4, NFCI, BAMLH* | volatility |
| USEPUINDXD, EPUTRADE | trump_effect, volatility |
| DCOILWTICO, DCOILBRENTEU | energy |

### CFTC Symbol → Tags

| Symbol | Tags |
|--------|------|
| ZL, ZS, ZM | crush |
| CL, HO | energy |
| All | volatility (aggregate) |

### Market Futures → Tags

| Symbol | Tags |
|--------|------|
| ZL | core, crush |
| ZS | core, crush |
| ZM | core, crush |
| CL | core, energy |
| HO | core, energy, biofuel |
| HG | china |

---

## EXECUTION PATTERN

For each table:

1. **Verify current state** (row count, columns)
2. **Generate ALTER TABLE** migration SQL
3. **Backfill** existing rows with defaults
4. **Update Prisma schema**
5. **Rewrite Inngest job** to Bronze pattern
6. **Test** with one ingestion cycle
7. **Document** completion

---

*LOCKED — Kirk Authority*
