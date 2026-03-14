# ZINC-FUSION-V15 Audit Index

**Last Updated:** 2026-03-13
**Purpose:** Track all audit reports, their status, and locations

---

## Completed Audits

### 1. Pre-Rebuild Forecast Audit (2026-03-04)

**Status:** ✅ COMPLETE  
**Canonical Location:** `docs/audit/pre_rebuild_forecast_audit_2026_03_04.md`  
**Shortcuts/Copies:**

- `PRE_REBUILD_FORECAST_AUDIT.md` (root shortcut)
- `PRE_REBUILD_FORECAST_AUDIT_2026-03-04.md` (root copy)
- `docs/audit/PRE_REBUILD_FORECAST_AUDIT_2026-03-04.md` (alternate copy)

**Summary:**

- Intentionally pre-rebuild; no matrix rebuild or retrain executed
- Production forecasts current to 2026-03-04
- Matrix/specialist signals at 2026-03-01
- Monte Carlo live (10,000 runs), pinball not persisted
- Long-horizon P10/P90 ranges too wide (stakeholder concern)

**Key Findings:**

- Data gaps: `supply.eia_biodiesel_1w` stale (2025-11-01), `supply.uco_prices_1w` stale (2026-01-01)
- Missing instrumentation: `model.shap_summary`, `training.model_runs_event` empty
- `palm` and `substitutes` specialists have frequent low/zero confidence periods

---

### 2. Specialist Audit Validation (2026-02-14)

**Status:** ✅ COMPLETE  
**Location:** `docs/audits/SPECIALIST_AUDIT_VALIDATION_20260214.md`

**Summary:**

- Validated prior `SPECIALIST_AUDIT_20260203.md` claims against code
- Confirmed: API observability mismatch (trump_effect), energy stickiness risk, retrain cadence issues
- Corrected: VAR re-estimation works, RF retrain logic exists (feature freshness is the issue)
- Added trump_effect to `/api/overview/models`

**Remediation Plan Status:**

- Phase A (Measurement discipline): Pending — requires DB queries
- Phase B (Data freshness enforcement): Pending
- Phase C (Anti-stuck logic): Pending
- Phase D (Quality control): Pending
- Phase E (Operational controls): Pending

---

### 3. Vegas Domain Migration & Schema Drift Audit (2026-03-05)

**Status:** ✅ COMPLETE  
**Location:** `TO-DO/Audit/2026-03-05_vegas_migration_drift_audit.md`  
**Backup Copy:** `Audits To BE DONE/2026-03-05_vegas_migration_drift_audit.md`

**Summary:**

- Schema split: tables created in `ops`, queries target `vegas`
- Multiple writers with different Glide App IDs
- `glide_row_id` unique constraints missing in Prisma models
- PredictHQ expansion columns missing from `vegas_events` model
- Public sync endpoint performs unguarded `TRUNCATE`
- Local DB tooling drift was identified and remediated (`db_identity_guard.py`, `sync_cloud_to_local_db.py`, `backfill_model_runs_event.py`, `check_local_v15_parity.sql`)

---

### 6. Vercel Environment & Cloud DB Audit (2026-03-11)

**Status:** ✅ COMPLETE
**Location:** `TO-DO/Audit/2026-03-11_vercel_env_cloud_db_audit.md`
**Related:** `reports/stale_review_2026-03-11.md` (Section 3)

**Summary:**

- Local workspace linked to wrong Vercel project (`frontend` with 0 env vars instead of `zinc-fusion-v15` with 44 entries)
- Cloud DB URL exists on Vercel production: `DATABASE_URL` and `POSTGRES_URL` both point to `db.prisma.io:5432/postgres`
- `CLOUD_DATABASE_URL` does not exist on Vercel — local audit convention only
- `DIRECT_DATABASE_URL` missing from Vercel (needed for migration bypass of Accelerate proxy)
- 7 env vars have trailing `\n` — potential auth failure risk
- Cloud guard passes with explicit URL injection; direct `psql` blocks on redacted credentials
- Workspace/project mismatch was resolved the same day; env pull now targets `zinc-fusion-v15` after re-link.

**Blockers for Section 3 completion:**

- None. Historical blockers were cleared on 2026-03-11 (project relink + cloud guard removal).

---

### 7. Forensic DB + Inngest Operational Audit (Working) (2026-03-11)

**Status:** 🟡 WORKING DOCUMENT
**Location:** `TO-DO/Audit/2026-03-11_forensic_db_inngest_operational_audit.md`
**Scope:** Database integrity + Inngest end-to-end wiring + operational drift register
**Checklist Checkpoint (2026-03-11):** P0 x1 complete, P1 x3 complete, P2 x2 complete (checklist fully closed).

**Summary:**

- Confirms runtime architecture is mostly aligned (`pg`/`psycopg2` for runtime, Prisma tooling for schema/migrations)
- Flags P0 migration governance gap (`raw` schema still present in canonical migration chain)
- Maps Inngest trigger-to-handler-to-DB paths; identifies dead wiring, manual trigger mismatches, runtime DDL, timeout/retry/concurrency inconsistencies
- README truth-lock approved and applied (`TO-DO/Audit/2026-03-11_readme_truth_lock_draft.md`) to align architecture/runtime wording
- Scoped parity tightening applied: `training.model_runs_event` added to cloud→local default sync; Prisma status now prints/enforces resolved DB target
- Separates resolved items (cloud-guard removal) from open risks and provides prioritized remediation sequence for items 1-6

---

### 8. Chart, Databento, and Schema Drift Audit (2026-03-13)

**Status:** ✅ COMPLETE
**Location:** `TO-DO/Audit/2026-03-13_chart_databento_operational_audit.md`
**Scope:** Frontend chart freshness, Databento ingest path, production-vs-local drift, migration safety

**Summary:**

- Production chart-serving tables are stale: `analytics.price_1d` stopped at `2026-03-10`, `analytics.price_1m` and `analytics.latest_price` at `2026-03-11 05:30:00+00`, and 5m/15m/1h tables are older still
- Production forecasts are stale upstream: `forecasts.production_1d` latest `as_of_date = 2026-03-04`, with training inputs stale on `2026-03-03` and OOF on `2026-02-20`
- The production Vercel `DATABENTO_API_KEY` is currently broken (`401 Authentication failed` on 2026-03-13), while a separately tested working key returns valid ZL data the same day
- Local DB is toxic for migration work: only legacy `analytics.zl_live` exists locally, serving tables are missing, and `prisma migrate status` gives a false-clean result against a heavily drifted schema
- No migrations were run; report explicitly recommends production credential repair first and local schema rebuild/re-sync before any migration activity

---

## Pending Audits (Require Training Runs / Live DB)

### 4. Phase 4B: Feature Coverage Audit

**Status:** ⏳ PENDING  
**Source:** `reports/optimization_plan.md` (line 23)  
**Prerequisites:** Phase 1A training completion

**Scope:**

- Feature missingness analysis across training history
- Coverage percentage by feature category
- Identification of features with >10% null rate

---

### 5. Phase 4C: Specialist Signal Quality Audit

**Status:** ⏳ PENDING  
**Source:** `reports/optimization_plan.md` (line 24)  
**Prerequisites:** Phase 1A training completion

**Scope:**

- Per-specialist coverage (last 180 trading days)
- Abstain rate measurement
- Max consecutive identical-signal runs
- IC (Information Coefficient) calculation per specialist

---

## Code Debt / TODOs (Not Audits)

These are code-level issues discovered during audit searches, not audit documents:

| File                                             | Line | Issue                                      | Severity |
| ------------------------------------------------ | ---- | ------------------------------------------ | -------- |
| `src/fusion/features/crowd_beliefs.py`           | 186  | Missing table `alt.crowd_beliefs_event`    | P2       |
| `scripts/_deprecated/backfill_sparse_sources.py` | 2    | Deprecated script references `raw.*`       | P3       |
| `scripts/ingest_databento_fx_options.py`         | 244  | Future enhancement placeholder (IV/Greeks) | P3       |

---

## Audit Infrastructure Gaps

### Resolved Script Gaps

- `scripts/check_local_v15_parity.sql` created
- `scripts/sync_cloud_to_local_db.py` created (default source changed from `CLOUD_DATABASE_URL` to `DATABASE_URL`)
- `scripts/backfill_model_runs_event.py` created
- `Makefile` target: `db-parity-local`

### Removed (2026-03-11 cleanup)

- `scripts/db_identity_guard.py` — deleted (rogue AI artifact from ~Mar 5 recovery)
- `.env.local.audit` / `.env.local.audit.example` — deleted
- Makefile targets `db-guard-cloud`, `db-guard-local`, `db-guard-shadow` — removed
- `CLOUD_DATABASE_URL` concept eliminated — cloud queries use `DATABASE_URL` directly
- Orphan Vercel project `frontend` deleted; workspace re-linked to `zinc-fusion-v15`
- 7 Vercel env vars with trailing `\n` cleaned (APP_ORIGIN, EIA_API_KEY, GLIDE_BEARER_TOKEN, NOAA_API_TOKEN, PROFARMER_USERNAME, PROFARMER_PASSWORD, USDA_API_KEY)

### Remaining Blockers

- None for Vercel/DB infrastructure (resolved 2026-03-11)

### Documentation Drift

- Multiple copies of Pre-Rebuild Forecast Audit exist with slight naming variations
- `docs/audit/REPORT_INDEX.md` exists but references non-standard paths

---

## Recommended Next Steps

1. **Refresh stale data and rerun core training** — `training.matrix_1d` and `training.specialist_signals_1d` are stale, so the next model pass should start with fresh data before retraining.
2. **Run Phase 4B/4C audits on the refreshed training outputs** — feature coverage and specialist signal quality depend on the next clean training cycle.
3. **Execute Specialist Audit Remediation Plan** — Phases A-E from the 2026-02-14 specialist audit remain the next structural follow-up.
4. **Keep env hygiene checks recurring** — re-check Vercel env values for accidental formatting drift (`\n`, duplicates).
5. **Clean up audit copies** — consolidate Pre-Rebuild Forecast Audit references.
6. **Consolidate Prisma configs** — two `prisma.config.ts` files still exist (`config/` and `prisma/`); merge into one.
