# ZINC-FUSION-V15 Work Tracking Index

**Created:** 2026-03-05
**Last Updated:** 2026-03-05

This index consolidates all planned work, pending tasks, and audit materials for the ZINC-FUSION-V15 project.

---

## Directory Structure

```
TO-DO/
├── INDEX.md                   # This file - master index
├── MASTER_TODO.md             # Code TODO/FIXME markers
└── Audit/                     # Audit-related materials
    ├── 2026-03-05_vegas_migration_drift_audit.md
    └── AUDIT_INDEX.md
```

---

## 📋 Audit Materials

### Canonical in `TO-DO/Audit/` (Backup Retained)

| File                                                                                                 | Status      | Description                                                              |
| ---------------------------------------------------------------------------------------------------- | ----------- | ------------------------------------------------------------------------ |
| [`Audit/2026-03-05_vegas_migration_drift_audit.md`](Audit/2026-03-05_vegas_migration_drift_audit.md) | ✅ COMPLETE | Vegas domain schema-to-database drift audit with 12 prioritized findings |
| [`Audit/AUDIT_INDEX.md`](Audit/AUDIT_INDEX.md)                                                       | ✅ COMPLETE | Master index of all audits with status tracking                          |

Backup folder kept for now (non-destructive): `Audits To BE DONE/`

### Canonical Audits (Linked, Not Moved)

These audits remain in their original locations; links provided for reference:

| File                                                                                                            | Status      | Description                                                       |
| --------------------------------------------------------------------------------------------------------------- | ----------- | ----------------------------------------------------------------- |
| [`docs/audit/pre_rebuild_forecast_audit_2026_03_04.md`](../docs/audit/pre_rebuild_forecast_audit_2026_03_04.md) | ✅ COMPLETE | Pre-rebuild forecast audit — pinball gaps, wide P10/P90 intervals |
| [`docs/audits/SPECIALIST_AUDIT_VALIDATION_20260214.md`](../docs/audits/SPECIALIST_AUDIT_VALIDATION_20260214.md) | ⏳ PENDING  | Specialist audit validation — Phases A-E remediation pending      |
| [`docs/audits/audit_results_databento.json`](../docs/audits/audit_results_databento.json)                       | ✅ COMPLETE | Databento data audit results (JSON)                               |

### Pending Audit Work (Requires Training Runs)

| Audit                                     | Status     | Prerequisites                | Source                            |
| ----------------------------------------- | ---------- | ---------------------------- | --------------------------------- |
| Phase 4B: Feature Coverage Audit          | ⏳ PENDING | Phase 1A training completion | `reports/optimization_plan.md:23` |
| Phase 4C: Specialist Signal Quality Audit | ⏳ PENDING | Phase 1A training completion | `reports/optimization_plan.md:24` |

---

## 📁 Planning Documents

### Implementation Roadmaps

| File                                                                                                | Status     | Description                                                                |
| --------------------------------------------------------------------------------------------------- | ---------- | -------------------------------------------------------------------------- |
| [`reports/optimization_plan.md`](../reports/optimization_plan.md)                                   | ⏳ PENDING | Master optimization plan with Phase 0-4 status (Phase 1A training pending) |
| [`plans/SPECIALIST_DATA_SOURCE_EXPANSION.md`](../plans/SPECIALIST_DATA_SOURCE_EXPANSION.md)         | ⏳ PENDING | 6-phase specialist signal expansion roadmap per bucket                     |
| [`plans/CATALOG_SOURCE_TO_SPECIALIST_MAPPING.md`](../plans/CATALOG_SOURCE_TO_SPECIALIST_MAPPING.md) | ⏳ PENDING | 4-phase (8-week) implementation roadmap for data source integration        |
| [`plans/LOCAL_DB_SETUP_FOR_AUDIT.md`](../plans/LOCAL_DB_SETUP_FOR_AUDIT.md)                         | 🔄 IN PROGRESS | Local DB tooling restored and local parity checks passing; cloud guard env still needs to be set in-shell |

### Phase Reports (Complete)

| File                                                                                                        | Status      | Description                                                      |
| ----------------------------------------------------------------------------------------------------------- | ----------- | ---------------------------------------------------------------- |
| [`reports/phase0_baseline_2026-02-20.md`](../reports/phase0_baseline_2026-02-20.md)                         | ✅ COMPLETE | Phase 0 baseline MAE/price training results                      |
| [`reports/phase1a_seasonal_covariates_2026-02-20.md`](../reports/phase1a_seasonal_covariates_2026-02-20.md) | ✅ COMPLETE | Phase 1A seasonal covariates training results with Options A/B/C |

### Session Memory (Reference)

| File                                                                                                    | Status      | Description                                            |
| ------------------------------------------------------------------------------------------------------- | ----------- | ------------------------------------------------------ |
| [`memory/ZINC_FUSION_SESSION_2026_03_05.md`](../memory/ZINC_FUSION_SESSION_2026_03_05.md)               | ✅ COMPLETE | Session notes with specialist data source mapping work |
| [`memory/ZINC_FUSION_EOD_DRIFT_LOCK_2026_03_05.md`](../memory/ZINC_FUSION_EOD_DRIFT_LOCK_2026_03_05.md) | ⏳ PENDING  | EOD drift lock with immediate next steps               |

---

## 📊 Phase Status Summary

### Optimization Plan Phases

| Phase | Name                    | Status       | Notes                |
| ----- | ----------------------- | ------------ | -------------------- |
| P0    | Baseline                | ✅ COMPLETE  | Baseline established |
| P1A   | Seasonal Features       | 🔄 CODE DONE | Training pending     |
| P1B   | Price-Level Anchors     | ⏳ PENDING   | —                    |
| P1C   | ZL Term Structure       | ⏳ PENDING   | —                    |
| P1D   | WASDE Surprise          | ⏳ PENDING   | —                    |
| P2A   | Indonesia Palm Data     | ⏳ PENDING   | —                    |
| P2B   | Fix Options Pipeline    | ⏳ PENDING   | —                    |
| P2C   | China Import Stats      | ⏳ PENDING   | —                    |
| P2D   | Weather Forecasts       | ⏳ PENDING   | —                    |
| P3A   | Test TFT on ARM         | ⏳ PENDING   | —                    |
| P3B   | Test DeepAR             | ⏳ PENDING   | —                    |
| P3C   | Evaluate Chronos2       | ⏳ PENDING   | —                    |
| P4A   | Training Window Opt     | ⏳ PENDING   | —                    |
| P4B   | Feature Coverage Audit  | ⏳ PENDING   | —                    |
| P4C   | Specialist Signal Audit | ⏳ PENDING   | —                    |

### Data Source Integration Phases (8-Week Roadmap)

| Phase   | Weeks | Focus                                 | Status     |
| ------- | ----- | ------------------------------------- | ---------- |
| Phase 1 | 1-2   | Critical Data Fixes & COT Integration | ⏳ PENDING |
| Phase 2 | 3-4   | Policy News & USDA Core Data          | ⏳ PENDING |
| Phase 3 | 5-6   | Weather, Trade Flows, Energy Details  | ⏳ PENDING |
| Phase 4 | 7-8   | Foreign Sources & Final Enhancements  | ⏳ PENDING |

### Specialist Audit Remediation Phases

| Phase   | Focus                      | Status     |
| ------- | -------------------------- | ---------- |
| Phase A | Measurement Discipline     | ⏳ PENDING |
| Phase B | Data Freshness Enforcement | ⏳ PENDING |
| Phase C | Anti-Stuck Logic           | ⏳ PENDING |
| Phase D | Quality Control            | ⏳ PENDING |
| Phase E | Operational Controls       | ⏳ PENDING |

---

## 🔗 Quick Links

- **Code TODOs:** See [`MASTER_TODO.md`](MASTER_TODO.md)
- **Vegas Audit:** See [`Audit/2026-03-05_vegas_migration_drift_audit.md`](Audit/2026-03-05_vegas_migration_drift_audit.md)
- **Optimization Plan:** See [`../reports/optimization_plan.md`](../reports/optimization_plan.md)
- **Implementation Roadmap:** See [`../plans/CATALOG_SOURCE_TO_SPECIALIST_MAPPING.md`](../plans/CATALOG_SOURCE_TO_SPECIALIST_MAPPING.md)

---

## Legend

| Symbol | Meaning               |
| ------ | --------------------- |
| ✅     | Complete              |
| ⏳     | Pending               |
| 🔄     | In Progress / Partial |
| ❌     | Blocked               |
