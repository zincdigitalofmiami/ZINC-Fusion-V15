# Forensic DB + Inngest Operational Audit (Working)

**Date:** 2026-03-11  
**Mode:** Read-only forensic audit (code/docs evidence only)

## Checklist Checkpoint (2026-03-11)

Status key: `[ ]` open, `[~]` in progress, `[x]` done

- [x] P0 Enforce banned-schema policy in migrations (prisma/migrations guard + CI)
- [x] P1 Fix Inngest registration/manual trigger mismatches
- [x] P1 Remove runtime DDL from Inngest jobs
- [x] P1 Standardize retries/concurrency/timeout policy
- [x] P2 Clean README + stale audit/runbook drift
- [x] P2 Tighten local/cloud parity flow (model_runs_event sync + target DB clarity)

## Executive Summary

Overall state: **partially healthy, not yet operationally hardened**.

- **Prisma intent (schema/migrations only) is mostly enforced in runtime code**: active runtime access uses `pg` (TS) and `psycopg2`/SQLAlchemy (Python), and active `PrismaClient` runtime usage was not found outside deprecated scripts.
- **Database integrity has P0/P1 drift**: banned `raw` schema still exists in canonical migration history; migration SQL is not covered by schema-table guardrails.
- **Inngest is broadly wired but not bulletproof**: there is dead registration wiring, manual-trigger mismatch, runtime DDL in active jobs, inconsistent explicit retries, and timeout mismatch.
- **README truth-lock is now applied**: architecture/runtime wording is aligned to current contract; remaining doc work is local/cloud parity flow and legacy-audit historical labeling.

### Resolved vs Open (cross-check with prior audits/TODO)

**Resolved (evidence in repo docs/config):**
- Cloud guard concept removed and local `db-parity-local` exists ([TO-DO/Audit/AUDIT_INDEX.md:145](TO-DO/Audit/AUDIT_INDEX.md#L145), [TO-DO/Audit/AUDIT_INDEX.md:152](TO-DO/Audit/AUDIT_INDEX.md#L152), [Makefile:38](Makefile#L38)).
- README truth-lock approved and applied (core output contract, MC conditional population, cloud/local clarity, Prisma runtime policy) ([README.md:20](README.md#L20), [README.md:47](README.md#L47), [README.md:55](README.md#L55), [README.md:56](README.md#L56), [TO-DO/Audit/2026-03-11_readme_truth_lock_draft.md:1](TO-DO/Audit/2026-03-11_readme_truth_lock_draft.md#L1)).
- Stale review report explicitly marked as historical/superseded snapshot ([reports/stale_review_2026-03-11.md:3](reports/stale_review_2026-03-11.md#L3)).

## Database State

### Architecture intent enforcement status

**Finding DB-01**  
Severity: **P1**  
Impact: Runtime architecture intent is mostly enforced (`pg`/`psycopg2` runtime, Prisma for schema/migrations tooling).  
Confidence: **High**  
Evidence: [frontend/src/lib/db.ts:15](frontend/src/lib/db.ts#L15), [src/fusion/db/connection.py:41](src/fusion/db/connection.py#L41), [src/fusion/db/connection.py:175](src/fusion/db/connection.py#L175), [config/prisma.config.ts:40](config/prisma.config.ts#L40), [scripts/prisma.sh:25](scripts/prisma.sh#L25), deprecated-only PrismaClient refs in [scripts/_deprecated/check_models.mjs:3](scripts/_deprecated/check_models.mjs#L3).  
Next action: Keep PrismaClient out of active paths; add CI check that blocks `@prisma/client` imports outside `config/` and `_deprecated/`.

**Finding DB-02**  
Severity: **P2**  
Impact: 12-schema architecture is declared and mostly consistent, but one config comment is stale and can mislead.  
Confidence: **High**  
Evidence: 12 schemas in [prisma/schema.prisma:9](prisma/schema.prisma#L9); stale "13 schemas" comment in [src/fusion/config.py:96](src/fusion/config.py#L96) while composed list is 12 at [src/fusion/config.py:115](src/fusion/config.py#L115).  
Next action: fix stale comment and add one schema-count assertion test.

### Integrity and migration governance

**Finding DB-03**  
Severity: **P0**  
Impact: Banned `raw` schema remains in canonical migration chain, violating current architecture policy and allowing future accidental dependence.  
Confidence: **High**  
Evidence: [prisma/migrations/0_init/migration.sql:5](prisma/migrations/0_init/migration.sql#L5), [prisma/migrations/0_init/migration.sql:8](prisma/migrations/0_init/migration.sql#L8), [prisma/migrations/0_init/migration.sql:23](prisma/migrations/0_init/migration.sql#L23).  
Next action: add explicit migration to deprecate/replace `raw.*`, plus guardrail that fails if any new migration includes banned schemas.

**Finding DB-04**  
Severity: **P0**  
Impact: Guardrails do not inspect Prisma migrations, so banned schema SQL can still land even if code hooks pass.  
Confidence: **High**  
Evidence: path filter excludes migrations in [scripts/check_sql_table_references.py:50](scripts/check_sql_table_references.py#L50), [scripts/check_sql_table_references.py:178](scripts/check_sql_table_references.py#L178); hooks only target `src|scripts|frontend/src|tests|sql` in [.pre-commit-config.yaml:39](.pre-commit-config.yaml#L39) and [.github/workflows/quality-gates.yml:89](.github/workflows/quality-gates.yml#L89).  
Next action: include `prisma/migrations/**/*.sql` in both pre-commit and CI sql-table-contract scope.

**Finding DB-05**  
Severity: **P1**  
Impact: Forbidden-table scanner exists but is not part of enforced gates; policy can silently regress.  
Confidence: **High**  
Evidence: script exists [scripts/check_forbidden_tables.sh:1](scripts/check_forbidden_tables.sh#L1); not invoked in [Makefile:14](Makefile#L14) or [scripts/verify.sh:106](scripts/verify.sh#L106).  
Next action: wire `check_forbidden_tables.sh` into `scripts/verify.sh` and CI.

**Finding DB-06**  
Severity: **P2**  
Impact: Two Prisma config files have different behavior and can cause environment-target drift.  
Confidence: **High**  
Evidence: root Prisma config uses only `DATABASE_URL` [prisma/prisma.config.ts:14](prisma/prisma.config.ts#L14); active wrapper uses direct-url fallback + shadow validation [config/prisma.config.ts:3](config/prisma.config.ts#L3), [config/prisma.config.ts:34](config/prisma.config.ts#L34).  
Next action: consolidate to one Prisma config and remove/redirect the other.

**Finding DB-07**  
Severity: **RESOLVED (was P2)**  
Impact: `prisma_status.sh` now prints resolved host/db target and supports explicit local/cloud guard mode, removing target ambiguity.  
Confidence: **High**  
Evidence: resolved target output and guard in [scripts/prisma_status.sh:53](scripts/prisma_status.sh#L53), [scripts/prisma_status.sh:55](scripts/prisma_status.sh#L55), [scripts/prisma_status.sh:61](scripts/prisma_status.sh#L61); env precedence still explicit in [scripts/load_db_env.sh:22](scripts/load_db_env.sh#L22).  
Next action: optionally set `PRISMA_STATUS_REQUIRE_TARGET` in CI/pre-push contexts that must enforce local/cloud mode.

**Finding DB-08**  
Severity: **P2**  
Impact: Local parity SQL does not assert banned-schema absence. Parity pass can coexist with policy violations.  
Confidence: **High**  
Evidence: required-schema checks only [scripts/check_local_v15_parity.sql:3](scripts/check_local_v15_parity.sql#L3) and required-table checks [scripts/check_local_v15_parity.sql:37](scripts/check_local_v15_parity.sql#L37); no banned-schema assertions present.  
Next action: add `information_schema.schemata` assertion that banned schemas do not exist.

**Finding DB-09**  
Severity: **RESOLVED (was P2)**  
Impact: cloud→local default sync now includes `training.model_runs_event`, matching parity/provenance expectations.  
Confidence: **High**  
Evidence: defaults list now includes model runs [scripts/sync_cloud_to_local_db.py:29](scripts/sync_cloud_to_local_db.py#L29), [scripts/sync_cloud_to_local_db.py:34](scripts/sync_cloud_to_local_db.py#L34); parity requirement remains [scripts/check_local_v15_parity.sql:50](scripts/check_local_v15_parity.sql#L50).  
Next action: keep sync default table set aligned with parity SQL whenever audit-critical tables change.

**Finding DB-10**  
Severity: **P3**  
Impact: `ops.data_source_registry.target_schema` still defaults to `raw`, preserving deprecated naming in metadata.  
Confidence: **High**  
Evidence: [prisma/schema.prisma:1236](prisma/schema.prisma#L1236).  
Next action: migrate default to approved schema mapping and backfill existing rows.

## Inngest Wiring State

### End-to-end map (trigger → handler → DB behavior)

1. **Manual driver refresh endpoint**  
Trigger source: `POST /api/refresh-drivers` sends Inngest events ([frontend/src/app/api/refresh-drivers/route.ts:34](frontend/src/app/api/refresh-drivers/route.ts#L34)).  
Events sent: `fred-daily-volatility`, `board-crush-daily`, `fred-daily-fx`, `fred-daily-trump-effect`, `specialist.signals-sync` ([frontend/src/app/api/refresh-drivers/route.ts:37](frontend/src/app/api/refresh-drivers/route.ts#L37)).  
Handler reality: only `specialist.signals-sync` has event-bound handler ([frontend/src/inngest/specialist-signals-sync.ts:325](frontend/src/inngest/specialist-signals-sync.ts#L325)); the others are cron-only (`{ cron: ... }`) in FRED/board-crush jobs ([frontend/src/inngest/fred-daily.ts:932](frontend/src/inngest/fred-daily.ts#L932), [frontend/src/inngest/board-crush-daily.ts:59](frontend/src/inngest/board-crush-daily.ts#L59)).

2. **Scheduled FRED ingestion**  
Trigger source: cron-segmented configs ([frontend/src/inngest/fred-daily.ts:549](frontend/src/inngest/fred-daily.ts#L549)).  
Handler creation: dynamic function builder with retries + DB concurrency ([frontend/src/inngest/fred-daily.ts:925](frontend/src/inngest/fred-daily.ts#L925)).  
DB writes: ingest runs/logs + source table inserts (same file, main loop).

3. **Specialist signal sync (manual + scheduled)**  
Trigger source: cron + manual event ([frontend/src/inngest/specialist-signals-sync.ts:305](frontend/src/inngest/specialist-signals-sync.ts#L305), [frontend/src/inngest/specialist-signals-sync.ts:325](frontend/src/inngest/specialist-signals-sync.ts#L325)).  
DB writes: `training.specialist_signals_1d` with `ON CONFLICT` idempotency ([frontend/src/inngest/specialist-signals-sync.ts:232](frontend/src/inngest/specialist-signals-sync.ts#L232), [frontend/src/inngest/specialist-signals-sync.ts:240](frontend/src/inngest/specialist-signals-sync.ts#L240)).

4. **Failure monitoring pipeline**  
Trigger source: system event `inngest/function.failed` ([frontend/src/inngest/global-failure-monitor.ts:21](frontend/src/inngest/global-failure-monitor.ts#L21)).  
DB writes: `ops.pipeline_alerts` with dedupe on `run_id` ([frontend/src/inngest/global-failure-monitor.ts:33](frontend/src/inngest/global-failure-monitor.ts#L33), [frontend/src/inngest/global-failure-monitor.ts:36](frontend/src/inngest/global-failure-monitor.ts#L36)).

### Wiring/reliability findings

**Finding ING-01**  
Severity: **P1**  
Impact: Dead function wiring; files define jobs that are not exported/registered in `/api/inngest`, so they never run.  
Confidence: **High**  
Evidence: defined exports in [frontend/src/inngest/zl-15m.ts:11](frontend/src/inngest/zl-15m.ts#L11), [frontend/src/inngest/zl-1h.ts:11](frontend/src/inngest/zl-1h.ts#L11), [frontend/src/inngest/dce-soy-oil-daily.ts:96](frontend/src/inngest/dce-soy-oil-daily.ts#L96), [frontend/src/inngest/palm-multi-source-daily.ts:195](frontend/src/inngest/palm-multi-source-daily.ts#L195), [frontend/src/inngest/biofuel-rss-daily.ts:125](frontend/src/inngest/biofuel-rss-daily.ts#L125); registry source [frontend/src/inngest/functions.ts:1](frontend/src/inngest/functions.ts#L1) (no exports for these symbols).  
Next action: either export/register these jobs or remove their files and document deprecation.

**Finding ING-02**  
Severity: **P1**  
Impact: Manual refresh endpoint reports success for events that do not map to event-bound functions; operators receive false-positive trigger feedback.  
Confidence: **High**  
Evidence: manual event sends [frontend/src/app/api/refresh-drivers/route.ts:37](frontend/src/app/api/refresh-drivers/route.ts#L37); FRED/board-crush cron-only handlers [frontend/src/inngest/fred-daily.ts:932](frontend/src/inngest/fred-daily.ts#L932), [frontend/src/inngest/board-crush-daily.ts:59](frontend/src/inngest/board-crush-daily.ts#L59); only specialist has matching manual event [frontend/src/inngest/specialist-signals-sync.ts:325](frontend/src/inngest/specialist-signals-sync.ts#L325).  
Next action: add event triggers to those jobs or change refresh endpoint to direct API/queue pattern with explicit acknowledgement.

**Finding ING-03**  
Severity: **P1**  
Impact: Runtime DDL exists in active Inngest jobs, causing schema drift outside migration governance and potential lock/contention issues in production.  
Confidence: **High**  
Evidence: DDL constants in [frontend/src/inngest/bls-monthly.ts:103](frontend/src/inngest/bls-monthly.ts#L103), [frontend/src/inngest/china-soy-imports.ts:84](frontend/src/inngest/china-soy-imports.ts#L84), [frontend/src/inngest/fas-gats-trade.ts:67](frontend/src/inngest/fas-gats-trade.ts#L67), [frontend/src/inngest/panama-canal-daily.ts:45](frontend/src/inngest/panama-canal-daily.ts#L45), [frontend/src/inngest/eia-biodiesel-weekly.ts:29](frontend/src/inngest/eia-biodiesel-weekly.ts#L29); executed at runtime via `client.query(CREATE_TABLE_SQL)` in [frontend/src/inngest/bls-monthly.ts:189](frontend/src/inngest/bls-monthly.ts#L189), [frontend/src/inngest/china-soy-imports.ts:211](frontend/src/inngest/china-soy-imports.ts#L211), [frontend/src/inngest/fas-gats-trade.ts:273](frontend/src/inngest/fas-gats-trade.ts#L273), [frontend/src/inngest/panama-canal-daily.ts:262](frontend/src/inngest/panama-canal-daily.ts#L262), [frontend/src/inngest/eia-biodiesel-weekly.ts:133](frontend/src/inngest/eia-biodiesel-weekly.ts#L133).  
Next action: move all DDL to Prisma migrations; keep runtime jobs DML-only.

**Finding ING-04**  
Severity: **P2**  
Impact: Several DB-writing jobs omit explicit `retries`, leaving behavior implicit and inconsistent with hardened operations standards.  
Confidence: **High**  
Evidence: missing retries in [frontend/src/inngest/board-crush-daily.ts:58](frontend/src/inngest/board-crush-daily.ts#L58), [frontend/src/inngest/cpo-daily.ts:183](frontend/src/inngest/cpo-daily.ts#L183), [frontend/src/inngest/zl-15m.ts:12](frontend/src/inngest/zl-15m.ts#L12), [frontend/src/inngest/zl-1h.ts:12](frontend/src/inngest/zl-1h.ts#L12), [frontend/src/inngest/zl-live.ts:82](frontend/src/inngest/zl-live.ts#L82), [frontend/src/inngest/zl-live.ts:125](frontend/src/inngest/zl-live.ts#L125), [frontend/src/inngest/whitehouse-press.ts:402](frontend/src/inngest/whitehouse-press.ts#L402).  
Next action: define explicit retry policy tiers and enforce via lint/check script.

**Finding ING-05**  
Severity: **P2**  
Impact: Not all DB-writing jobs apply shared `DB_CONCURRENCY`, weakening connection budgeting assumptions.  
Confidence: **High**  
Evidence: shared policy declared in [frontend/src/inngest/client.ts:28](frontend/src/inngest/client.ts#L28); no DB concurrency for cleanup monitor jobs in [frontend/src/inngest/cleanup-stale-runs.ts:14](frontend/src/inngest/cleanup-stale-runs.ts#L14), [frontend/src/inngest/global-failure-monitor.ts:20](frontend/src/inngest/global-failure-monitor.ts#L20).  
Next action: apply DB concurrency consistently for all DB-touching functions or document exceptions.

**Finding ING-06**  
Severity: **P2**  
Impact: Timeout configuration mismatch between route code and Vercel config can produce non-deterministic execution ceilings.  
Confidence: **High**  
Evidence: route exports 300s [frontend/src/app/api/inngest/route.ts:138](frontend/src/app/api/inngest/route.ts#L138); Vercel config sets 800s [frontend/vercel.json:9](frontend/vercel.json#L9).  
Next action: set one authoritative timeout value and enforce in CI (route + vercel.json parity check).

**Finding ING-07**  
Severity: **P3**  
Impact: Deployment assumptions are documented but still environment-sensitive (Vercel-only serveHost, local docker URL defaults).  
Confidence: **High**  
Evidence: Vercel-only serveHost logic [frontend/src/app/api/inngest/route.ts:107](frontend/src/app/api/inngest/route.ts#L107); local docker default URL [docker-compose.inngest.yml:16](docker-compose.inngest.yml#L16).  
Next action: add an explicit local runbook test that verifies docker dev URL + `/api/inngest` registration health.

## Drift and Risk Register

**R-01**  
Severity: **RESOLVED (was P1)**  
Impact: README architecture/runtime wording is aligned to current approved target-zone and DB-runtime policy contract.  
Confidence: **High**  
Evidence: truth-lock wording now present in [README.md:20](README.md#L20), [README.md:22](README.md#L22), [README.md:47](README.md#L47), [README.md:55](README.md#L55), [README.md:56](README.md#L56); approval record in [TO-DO/Audit/2026-03-11_readme_truth_lock_draft.md:1](TO-DO/Audit/2026-03-11_readme_truth_lock_draft.md#L1).  
Next action: keep README wording checks in future doc audits.

**R-02**  
Severity: **RESOLVED (was P2)**  
Impact: Audit index now reflects cleared cloud-guard blockers and current working-open items only.  
Confidence: **High**  
Evidence: cleared blocker statement [TO-DO/Audit/AUDIT_INDEX.md:93](TO-DO/Audit/AUDIT_INDEX.md#L93), working-checkpoint summary [TO-DO/Audit/AUDIT_INDEX.md:102](TO-DO/Audit/AUDIT_INDEX.md#L102).  
Next action: keep checkpoint lines synchronized after each checklist closeout.

## Open Gaps

1. **Unknown: actual live cloud DB migration/data state.**  
Needed to verify: non-redacted cloud DB access + runtime query output (`_prisma_migrations`, schema table counts, banned schema absence).

2. **Unknown: deployed Vercel env parity today (outside repo snapshot).**  
Needed to verify: fresh `vercel env pull` from correctly linked project plus sanitized comparison report.

3. **Unknown: whether dead-wired Inngest files are intentionally dormant or accidental.**  
Needed to verify: owner decision per job (`zl-15m`, `zl-1h`, `dceSoyOilDaily`, `palmMultiSourceDaily`, `biofuelRssDaily`).

4. **Unknown: explicit org policy for retry defaults.**  
Needed to verify: canonical retries matrix by job class (market data, reference data, sync, monitor).

## Prioritized Remediation Plan

1. **P0: Enforce banned-schema policy in migration SQL.**  
Action: include `prisma/migrations/**/*.sql` in SQL-table-contract checks; add explicit banned-schema assertion job.

2. **P1: Evaluate and fix manual refresh trigger semantics.**  
Action: align `/api/refresh-drivers` with event-bound handlers or remove misleading event sends; keep only verifiable triggers.

3. **P1: Harden all Inngest jobs.**  
Action: remove runtime DDL, enforce explicit retries/concurrency/timeouts, fail on partial sync errors, and standardize ingest-run/error telemetry.

4. **P1: Standardize timeout/retry/concurrency policy.**  
Action: codify one policy doc + lint script to reject non-compliant function definitions.

5. **P2: Clean docs/audit drift.**  
Action: **completed 2026-03-11** (README truth-lock applied; index/checkpoint text updated; stale snapshot marked superseded).

6. **P2: Tighten local/cloud/Vercel parity flow.**  
Action: **completed 2026-03-11** for scoped item (added `training.model_runs_event` to cloud→local sync defaults; Prisma status now prints resolved host/db target and supports `PRISMA_STATUS_REQUIRE_TARGET=local|cloud` guard).
