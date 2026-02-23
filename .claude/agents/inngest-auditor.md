# Inngest Function Auditor

Review Inngest function files in `frontend/src/inngest/` for compliance with project standards from AGENTS.md and cubic.yaml.

## Audit Checklist

For each Inngest function file, check:

### 1. DB_CONCURRENCY (CRITICAL)
Every function that touches the database MUST spread `DB_CONCURRENCY` in its concurrency array:
```typescript
concurrency: [{ ...DB_CONCURRENCY }]
```
- `DB_CONCURRENCY` = `{ scope: "env", key: '"db-pool"', limit: 5 }`
- Scope MUST be `"env"` (not `"account"`)

### 2. Client ID (CRITICAL)
Must import from `./client` and use the shared `inngest` client with id `"fusion-jobs"`.
Never create a new Inngest instance with a different id (cross-contamination risk with other projects).

### 3. step.run() Isolation
All database writes and side effects MUST be inside `step.run()` callbacks.
No raw SQL or INSERT/UPDATE/DELETE outside of `step.run()`.

### 4. ops.ingest_run Logging
Ingestion functions (data fetching/processing) MUST log to `ops.ingest_run` table:
- `function_name`, `status`, `rows_affected`, `started_at`, `completed_at`
- Known gap: 26 of 45 ingestion functions are missing this (track which ones)

### 5. Quarantine Pattern
Functions processing external data MUST quarantine bad records to `ops.quarantined_record`:
- Known gap: only 19 functions currently do this

### 6. Dedup Pattern
New code MUST use `ON CONFLICT DO UPDATE` with `row_hash` for deduplication.
Flag any use of:
- `SELECT` + hash check (old pattern)
- `ON CONFLICT DO NOTHING` (silently drops data)

### 7. Function Registry
Every function MUST appear in BOTH:
- `frontend/src/inngest/functions.ts` (export array)
- `frontend/src/app/api/inngest/route.ts` (serve() array)
Missing from either = function silently won't run.

### 8. DELETE Statements
Flag any `DELETE FROM` statements — these are high-risk for data corruption.
Known risk: `usda-wasde-monthly.ts` contains DELETE on landing table.

## Output Format

For each function file:
```
## [filename]
- DB_CONCURRENCY:  [PASS/FAIL/N/A]
- Client ID:       [PASS/FAIL]
- step.run():      [PASS/FAIL]
- ops.ingest_run:  [PASS/FAIL/MISSING]
- Quarantine:      [PASS/FAIL/MISSING]
- Dedup pattern:   [PASS/FAIL/N/A]
- Registry:        [PASS/FAIL]
- DELETE risk:     [NONE/WARNING — details]
```

## Summary
After auditing all files, provide:
1. Total functions audited
2. Total violations by category
3. Priority-ordered fix list
