# ZINC-FUSION-V15 Audit Index

**Last Updated:** 2026-03-05  
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
- `check_local_v15_parity.sql` was missing at audit time; script now exists in `scripts/`

---

### 4. Specialist Domain Audit (2026-03-05)

**Status:** ✅ COMPLETE
**Location:** `TO-DO/Audit/2026-03-05_specialist_domain_audit.md`

**Summary:**

- P0 Critical: 5/11 specialists missing model artifacts (fed, tariff, biofuel, volatility, trump_effect)
- P1 High: Staleness age computed at sync time, not data generation time
- P1 High: Palm model_type mismatch (Python: `ecm_ridge`, Inngest: `ridge`)
- P2 Medium: trump_effect has no confidence key (always fallback 0.5)
- P2 Medium: Per-bucket freshness monitoring missing (only aggregate check)
- P2 Medium: Prior audit remediation status unknown

**Verified Correct:**

- All 11 buckets present in Python, Inngest, migrations, Prisma
- Signal column naming: `sig_{bucket}_1`, `sig_{bucket}_2`, `sig_{bucket}_conf`
- Schema-to-database parity confirmed
- Cron schedules appropriate (sync at 7AM UTC, monitor at 8AM CT)

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

### Script Status

- `scripts/check_local_v15_parity.sql` exists and is tracked in this repository state.

### Documentation Drift

- Multiple copies of Pre-Rebuild Forecast Audit exist with slight naming variations
- `docs/audit/REPORT_INDEX.md` exists but references non-standard paths

---

## Recommended Next Steps

1. **Complete Phase 1A Training** — Prerequisite for Phase 4B/4C audits
2. **Execute Specialist Audit Remediation Plan** — Phases A-E from 2026-02-14 audit
3. **Resolve Vegas Schema Split** — Follow remediation steps in Vegas audit
4. **Run Local Parity Script** — execute `scripts/check_local_v15_parity.sql` against the target local DB
5. **Clean Up Audit Copies** — Consolidate Pre-Rebuild Forecast Audit references
