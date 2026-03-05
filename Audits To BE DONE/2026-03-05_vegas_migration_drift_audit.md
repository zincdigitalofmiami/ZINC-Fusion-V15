# Vegas Domain Migration & Schema Drift Audit

**Date:** 2026-03-05  
**Auditor:** Claude (Code Reviewer mode)  
**Repository:** ZINC-FUSION-V15

---

## 1. Scope

This audit covers all **Vegas locations domain** entities in the ZINC-FUSION-V15 repository:

| Prisma Model             | Location in `prisma/schema.prisma` |
| ------------------------ | ---------------------------------- |
| `vegas_casinos`          | lines 3240–3262                    |
| `vegas_cuisine_affinity` | lines 3264–3281                    |
| `vegas_daily_spend`      | lines 3283–3328                    |
| `vegas_event_entities`   | lines 3329–3347                    |
| `vegas_event_impact`     | lines 3349–3366                    |
| `vegas_event_labels`     | lines 3368–3382                    |
| `vegas_event_venues`     | lines 3398–3408                    |
| `vegas_events`           | lines 3410–3432                    |
| `vegas_export_list`      | lines 3434–3445                    |
| `vegas_fryers`           | lines 3447–3478                    |
| `vegas_restaurants`      | lines 3480–3512                    |
| `vegas_shifts`           | lines 3514–3535                    |
| `vegas_venues`           | lines 3537–3557                    |

> **Note:** There is no top-level "locations" model family; the Vegas domain (`vegas_*`) is the closest equivalent and the subject of this audit.

---

## 2. Files and Searches Reviewed

### 2.1 Prisma Schema & Migrations

| Artifact                       | Path                                                               |
| ------------------------------ | ------------------------------------------------------------------ |
| Prisma schema                  | `prisma/schema.prisma` (lines 3220–3557)                           |
| Initial Vegas tables migration | `prisma/migrations/20260114_add_vegas_intel_tables/migration.sql`  |
| PredictHQ event expansion      | `prisma/migrations/20260115_expand_predicthq_events/migration.sql` |
| Cuisine affinity seed/table    | `prisma/migrations/20260115_cuisine_affinity/migration.sql`        |
| Daily spend seed/table         | `prisma/migrations/20260115_daily_fb_spend/migration.sql`          |
| Restaurant cuisine column      | `prisma/migrations/20260115_add_restaurant_cuisine/migration.sql`  |

### 2.2 Runtime Code Paths

| File                                              | Purpose                                                                        |
| ------------------------------------------------- | ------------------------------------------------------------------------------ |
| `frontend/src/app/api/vegas/route.ts`             | Main API read endpoints (`getEvents`, `getRestaurants`, `getDailySpend`, etc.) |
| `frontend/src/app/api/vegas/sync/route.ts`        | Public sync endpoint (`POST`) with `TRUNCATE + INSERT`                         |
| `frontend/src/app/api/vegas/restaurants/route.ts` | Restaurant-specific reads                                                      |
| `frontend/src/inngest/glide-vegas.ts`             | Inngest-triggered Glide sync (TS, writes to `vegas` schema)                    |
| `src/fusion/ingestion/glide_vegas.py`             | Python Glide ingestion (writes to `ops` schema)                                |

### 2.3 Explicit Searches Performed

| Search Pattern                                                                           | Result                                                           |
| ---------------------------------------------------------------------------------------- | ---------------------------------------------------------------- |
| `SET SCHEMA vegas` or `ops.vegas_* -> vegas` in all migrations                           | **0 results** — no schema transfer migration exists              |
| `check_local_v15_parity` in `scripts/`                                                   | **0 results** — referenced file is missing                       |
| `@unique` on `glide_row_id` for `vegas_restaurants` and `vegas_casinos` in Prisma schema | **Not present** — unique constraint exists only in SQL migration |

---

## 3. Confirmed Findings

### 3.1 `glide_row_id` Constraint Checks

#### Evidence

1. **SQL migration creates unique constraints:**
   - `prisma/migrations/20260114_add_vegas_intel_tables/migration.sql` line 21:
     ```sql
     CONSTRAINT vegas_restaurants_glide_row_id_key UNIQUE (glide_row_id)
     ```
   - Same migration line 34:
     ```sql
     CONSTRAINT vegas_casinos_glide_row_id_key UNIQUE (glide_row_id)
     ```
   - Also for `vegas_fryers` (line 47), `vegas_export_list` (line 60), `vegas_shifts` (line 86).

2. **Prisma models lack `@unique`:**
   - `prisma/schema.prisma` line 3482 (`vegas_restaurants`):
     ```prisma
     glide_row_id   String?
     ```
   - `prisma/schema.prisma` line 3252 (`vegas_casinos`):
     ```prisma
     glide_row_id   String?
     ```
   - Neither field has `@unique` directive.

#### Impact

Prisma introspection / generate will not recognize these as unique keys; `prisma db pull` could drift or lose the constraint.

---

### 3.2 Missing `SET SCHEMA` Migration

#### Evidence

- Regex search for `SET SCHEMA vegas` or `ops.vegas_` → `vegas.vegas_` across all migration files returned **0 matches**.
- Initial migration (`20260114_add_vegas_intel_tables/migration.sql`) creates tables in `ops` schema:
  ```sql
  CREATE TABLE ops.vegas_restaurants (...)
  CREATE TABLE ops.vegas_casinos (...)
  ```
- Runtime API queries target `vegas` schema:
  - `frontend/src/app/api/vegas/route.ts` line 155: `FROM vegas.vegas_events`
  - `frontend/src/app/api/vegas/route.ts` line 274: `FROM vegas.vegas_restaurants`
- TypeScript writers also target `vegas`:
  - `frontend/src/inngest/glide-vegas.ts` line 59: schema constant `vegas`.
- Python writer targets `ops`:
  - `src/fusion/ingestion/glide_vegas.py` line 55: `POSTGRES_SCHEMA = "ops"`

#### Impact

Tables exist in `ops`, queries run against `vegas` — either one schema is empty, or manual intervention created `vegas` tables outside migration history. No documented cutover migration exists.

---

### 3.3 Missing `check_local_v15_parity` Script

#### Evidence

- `plans/LOCAL_DB_SETUP_FOR_AUDIT.md` line 24 references:
  ```
  scripts/check_local_v15_parity.sql
  ```
- Regex search in `scripts/` for `check_local_v15_parity` returned **0 results**.

#### Impact

Documented parity verification workflow cannot be executed; audit reproducibility is compromised.

---

## 4. Prioritized Findings Summary

| Sev    | ID  | Finding                                                                                                     | Root Cause                                               |
| ------ | --- | ----------------------------------------------------------------------------------------------------------- | -------------------------------------------------------- |
| **P0** | 1   | Schema split: tables created in `ops`, queries target `vegas`, Python writes to `ops`, TS writes to `vegas` | No canonical schema owner; no cutover migration          |
| **P0** | 2   | Public `POST /api/vegas/sync` performs `TRUNCATE` without auth                                              | Sync endpoint lacks server-side authorization            |
| **P0** | 3   | Python ingestion allowlist bug — prefixed vs non-prefixed table names                                       | Function contract mismatch after table-name refactor     |
| **P1** | 4   | Prisma `vegas_events` missing PredictHQ expansion columns                                                   | Model not reconciled after SQL-first expansion migration |
| **P1** | 5   | FK relations with `ON DELETE CASCADE` in SQL not mirrored in Prisma                                         | SQL-level FK design not in Prisma relationship graph     |
| **P1** | 6   | `glide_row_id` unique constraints missing in Prisma models                                                  | DDL constraints drifted from Prisma metadata             |
| **P1** | 7   | Generated column `spend_total` modeled as plain scalar                                                      | Generated SQL expression not in Prisma metadata          |
| **P2** | 8   | Row-by-row insert loops (N+1 writes)                                                                        | Simple implementation not scaled for full refresh        |
| **P2** | 9   | Correlated per-day subquery in `getDailySpend()`                                                            | Inefficient query pattern                                |
| **P2** | 10  | JSON-heavy joins reduce indexability                                                                        | Join keys inside JSON payload                            |
| **P3** | 11  | Views/materialized views not in Prisma governance                                                           | SQL-first operational objects without Prisma model       |
| **P3** | 12  | Missing `check_local_v15_parity.sql` script                                                                 | Process doc diverged from repository content             |

---

## 5. Remediation Steps

### 5.1 P0 Fixes

#### P0-1: Canonicalize Schema Namespace

1. Choose canonical schema: **`vegas`** (matches Prisma models + runtime API).
2. Create migration:

   ```sql
   -- Option A: Move tables
   ALTER TABLE ops.vegas_restaurants SET SCHEMA vegas;
   ALTER TABLE ops.vegas_casinos SET SCHEMA vegas;
   -- ... repeat for all vegas_* tables

   -- Option B: Create compatibility views for one release cycle
   CREATE VIEW ops.vegas_restaurants AS SELECT * FROM vegas.vegas_restaurants;
   ```

3. Update Python ingestion:
   ```python
   # src/fusion/ingestion/glide_vegas.py line 55
   POSTGRES_SCHEMA = "vegas"
   ```
4. Remove duplicate writer paths (choose one: Inngest vs API sync vs Python ingestion).

#### P0-2: Secure Sync Endpoint

1. Add server-side auth guard at `frontend/src/app/api/vegas/sync/route.ts` `POST()` handler.
2. Replace `TRUNCATE` + row-loop with staged load-and-swap pattern:
   ```sql
   BEGIN;
   CREATE TEMP TABLE staging_restaurants (LIKE vegas.vegas_restaurants INCLUDING ALL);
   COPY staging_restaurants FROM ...;
   TRUNCATE vegas.vegas_restaurants;
   INSERT INTO vegas.vegas_restaurants SELECT * FROM staging_restaurants;
   COMMIT;
   ```

#### P0-3: Fix Python Ingestion Allowlist Bug

Update `src/fusion/ingestion/glide_vegas.py`:

```python
# Line ~161 in save_to_postgres()
# Pass logical names only, apply prefix once
table_name = f"vegas_{logical_name}"  # prefix applied here
assert table_name in ALLOWED_TABLES, f"Unknown table: {table_name}"
```

Add regression test for `ingest_single_table()`.

---

### 5.2 P1 Fixes

#### P1-4: Reconcile `vegas_events` Model

Add missing columns to `prisma/schema.prisma` at `vegas_events` (line 3410):

```prisma
model vegas_events {
  // ... existing fields ...
  rank              Int?
  local_rank        Int?
  aviation_rank     Int?
  phq_attendance    Int?
  geo_lat           Float?
  geo_lon           Float?
  scope             String?
  place_hierarchies String[]
  // ... etc. per migration
  @@schema("vegas")
}
```

Run: `npx --prefix config prisma migrate dev --name align_vegas_events`

#### P1-5: Add Prisma Relations for FKs

Update child models (e.g., `vegas_event_venues`, `vegas_event_labels`, `vegas_event_impact`, `vegas_event_entities`):

```prisma
model vegas_event_venues {
  id       BigInt        @id @default(autoincrement())
  event_id String
  event    vegas_events  @relation(fields: [event_id], references: [event_id], onDelete: Cascade)
  // ...
  @@schema("vegas")
}
```

Run orphan cleanup before migration:

```sql
DELETE FROM vegas.vegas_event_venues
WHERE event_id NOT IN (SELECT event_id FROM vegas.vegas_events);
```

#### P1-6: Add `@unique` for `glide_row_id`

Update `prisma/schema.prisma`:

```prisma
model vegas_restaurants {
  // ...
  glide_row_id   String?   @unique
  // ...
}

model vegas_casinos {
  // ...
  glide_row_id   String?   @unique
  // ...
}
```

Pre-migration dedupe:

```sql
DELETE FROM vegas.vegas_restaurants a
USING vegas.vegas_restaurants b
WHERE a.id < b.id AND a.glide_row_id = b.glide_row_id;
```

#### P1-7: Mark `spend_total` as DB-Generated

```prisma
model vegas_daily_spend {
  // ...
  spend_total Float? @default(dbgenerated())
  // ...
}
```

---

### 5.3 P2 Fixes

#### P2-8: Batch Writes

Replace row loops with batched inserts or `COPY`:

```typescript
// frontend/src/inngest/glide-vegas.ts
const values = rows
  .map((r) => `(${escape(r.id)}, ${escape(r.data)})`)
  .join(",");
await pool.query(
  `INSERT INTO vegas.vegas_restaurants (id, data) VALUES ${values}`,
);
```

#### P2-9: Rewrite `getDailySpend()`

Pre-aggregate event counts:

```sql
WITH event_counts AS (
  SELECT date, COUNT(*) AS event_count
  FROM vegas.vegas_events
  GROUP BY date
)
SELECT s.*, ec.event_count
FROM vegas.vegas_daily_spend s
LEFT JOIN event_counts ec ON s.date = ec.date
ORDER BY s.date DESC;
```

#### P2-10: Promote JSON Join Keys

Add typed columns:

```sql
ALTER TABLE vegas.vegas_restaurants ADD COLUMN casino_id TEXT;
ALTER TABLE vegas.vegas_restaurants ADD COLUMN display_name TEXT;
CREATE INDEX idx_restaurants_casino_id ON vegas.vegas_restaurants(casino_id);
```

Update ingestion to populate these columns from JSON payload.

---

### 5.4 P3 Fixes

#### P3-11: Views Governance

Either:

- Add Prisma `@@view` models (Prisma 4.14+), or
- Create `prisma/excluded_objects.txt` manifest documenting SQL-only objects.

#### P3-12: Restore Parity Script

Create or restore `scripts/check_local_v15_parity.sql`, or update `plans/LOCAL_DB_SETUP_FOR_AUDIT.md` to reference current parity workflow.

---

## 6. Safe Rollout Order

| Step | Action                                                                                                               | Risk                |
| ---- | -------------------------------------------------------------------------------------------------------------------- | ------------------- |
| 1    | Lock down / remove public `POST /api/vegas/sync`                                                                     | Security            |
| 2    | Freeze duplicate writers; pick one canonical ingestion path                                                          | Data integrity      |
| 3    | **Migration Set A:** Namespace reconciliation, Prisma model alignment, unique constraints, generated-column metadata | Non-destructive     |
| 4    | Run data reconciliation: dedupe `glide_row_id`, orphan cleanup for FK validation                                     | Data prep           |
| 5    | **Migration Set B:** Validate FKs, add typed join columns, add indexes                                               | Constraints + perf  |
| 6    | Deploy batched writes, advisory locking, staged swap                                                                 | Ingestion stability |
| 7    | Deprecate legacy compatibility views after one release cycle                                                         | Cleanup             |
| 8    | Final parity gate: `scripts/prisma_status.sh` + `scripts/check_sql_table_references.py`                              | Verification        |

---

## 7. Appendix: Evidence References

| Item                                    | File                                                               | Line(s)            |
| --------------------------------------- | ------------------------------------------------------------------ | ------------------ |
| Initial table creation in `ops`         | `prisma/migrations/20260114_add_vegas_intel_tables/migration.sql`  | 15, 28, 41, 54, 80 |
| Unique constraints in SQL               | same file                                                          | 21, 34, 47, 60, 86 |
| PredictHQ expansion columns             | `prisma/migrations/20260115_expand_predicthq_events/migration.sql` | 19–40              |
| FK with `ON DELETE CASCADE`             | same file                                                          | 79, 94, 112, 137   |
| View `vegas_hospitality_demand`         | same file                                                          | 158–169            |
| Materialized view `vegas_event_summary` | same file                                                          | 175–207            |
| Generated column `spend_total`          | `prisma/migrations/20260115_daily_fb_spend/migration.sql`          | 18                 |
| Prisma `vegas_restaurants` model        | `prisma/schema.prisma`                                             | 3480–3512          |
| Prisma `vegas_casinos` model            | `prisma/schema.prisma`                                             | 3240–3262          |
| Prisma `vegas_events` model             | `prisma/schema.prisma`                                             | 3410–3432          |
| Python `POSTGRES_SCHEMA = "ops"`        | `src/fusion/ingestion/glide_vegas.py`                              | 55                 |
| TS Glide App ID                         | `frontend/src/inngest/glide-vegas.ts`                              | 8                  |
| Python Glide App ID                     | `src/fusion/ingestion/glide_vegas.py`                              | 45                 |
| API reads from `vegas` schema           | `frontend/src/app/api/vegas/route.ts`                              | 155, 274           |
| Public sync `TRUNCATE`                  | `frontend/src/app/api/vegas/sync/route.ts`                         | 97                 |
| Missing parity script reference         | `plans/LOCAL_DB_SETUP_FOR_AUDIT.md`                                | 24                 |

---

## 8. Post-Audit Closure Update (2026-03-05)

This section captures follow-through work completed after the initial audit snapshot.

### 8.1 Local DB Tooling Restored

Created missing tooling referenced by the audit/plan docs:

- `scripts/check_local_v15_parity.sql`
- `scripts/sync_cloud_to_local_db.py`
- `scripts/backfill_model_runs_event.py`
- `scripts/db_identity_guard.py`
- `Makefile` targets: `db-guard-cloud`, `db-guard-local`, `db-guard-shadow`, `db-parity-local`
- `.env.local.audit.example` template

### 8.2 Verified Local Parity + Provenance

Executed against `zinc_fusion_v15_local`:

- `db-guard-local` => PASS
- `db-guard-shadow` => PASS
- `db-parity-local` => PASS
- `backfill_model_runs_event.py` => upserted 14 grouped `run_hash + horizon_days` rows

Post-backfill parity snapshot:

- `forecasts.production_1d`: 24 rows
- `training.matrix_1d`: 7,982 rows
- `training.specialist_signals_1d`: 85,411 rows
- `training.oof_core_1d`: 964 rows
- `training.model_runs_event`: 14 rows
- specialist distinct buckets: 11

### 8.3 Remaining Blocker

- `db-guard-cloud` still fails in this shell because cloud DB URL env vars are unset.
- Next step: set `CLOUD_DATABASE_URL` (or direct cloud DB env var aliases) and rerun `make db-guard-cloud`.

---

**End of Audit Report**
