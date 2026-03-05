# ZINC-FUSION-V15 Code TODOs

**Created:** 2026-03-05
**Last Updated:** 2026-03-05

This file consolidates all `TODO`, `FIXME`, `XXX`, `HACK`, and `BUG` markers found in the codebase.

---

## Summary

| Category         | Count |
| ---------------- | ----- |
| Python TODOs     | 3     |
| TypeScript TODOs | 0     |
| SQL TODOs        | 0     |
| **Total**        | **3** |

---

## Python TODOs

### 1. Missing Table: `alt.crowd_beliefs_event`

**File:** [`src/fusion/features/crowd_beliefs.py`](../src/fusion/features/crowd_beliefs.py):186
**Severity:** ⚠️ Medium
**Category:** Missing Table

```python
FROM alt.crowd_beliefs_event  -- sqlref: ignore  TODO: Create table or remove feature
```

**Context:** The feature query references a table `alt.crowd_beliefs_event` that does not exist in the schema. Either create the table via migration or remove this feature from the codebase.

**Recommended Action:**

- Option A: Create `alt.crowd_beliefs_event` table with appropriate schema
- Option B: Remove the feature from `crowd_beliefs.py` if no longer needed

---

### 2. Deprecated Script: `backfill_sparse_sources.py`

**File:** [`scripts/_deprecated/backfill_sparse_sources.py`](../scripts/_deprecated/backfill_sparse_sources.py):2
**Severity:** 🔵 Low
**Category:** Deprecated Code

```python
# ⚠️ MIGRATION NOTICE: This script references raw.* tables.
# TODO: Migrate to v2 schema tables (mkt/econ/alt/pos/supply) if still needed.
```

**Context:** Script is already in `_deprecated/` folder and references banned `raw.*` schema tables. The TODO indicates it should be migrated to v2 schema if still needed.

**Recommended Action:**

- If script is still needed: Migrate to use approved schemas (mkt/econ/alt/pos/supply)
- If script is obsolete: Consider deleting entirely

---

### 3. Future Enhancement: IV/Greeks Calculation

**File:** [`scripts/ingest_databento_fx_options.py`](../scripts/ingest_databento_fx_options.py):244
**Severity:** 🔵 Low
**Category:** Future Enhancement

```python
# TODO: Calculate IV and Greeks when we have full options chain data
# For now, this serves as a template for when options data becomes available
```

**Context:** Placeholder for future options analytics functionality. Not blocking — serves as a template for when options data becomes available.

**Recommended Action:**

- No immediate action required
- Implement when full options chain data is available (likely Phase 2B per optimization plan)

---

## TypeScript TODOs

_No TODO markers found in TypeScript files._

---

## SQL TODOs

_No TODO markers found in SQL files._

---

## False Positives (Excluded)

The following were detected but are not actual TODO markers:

| File                                              | Line    | Reason                                                             |
| ------------------------------------------------- | ------- | ------------------------------------------------------------------ |
| `frontend/src/inngest/fx-databento-spot-daily.ts` | 24, 156 | Contains "invert" in comments about FX pair inversion — not a TODO |
| `scripts/_deprecated/backfill_fx_databento.py`    | 53, 133 | Contains "Invert" in comments about FX pair inversion — not a TODO |

---

## Related Planning Documents

For higher-level pending work items, see:

- [`INDEX.md`](INDEX.md) — Master work tracking index
- [`reports/optimization_plan.md`](../reports/optimization_plan.md) — Phase-based implementation plan
- [`plans/CATALOG_SOURCE_TO_SPECIALIST_MAPPING.md`](../plans/CATALOG_SOURCE_TO_SPECIALIST_MAPPING.md) — Data source integration roadmap

---

## Priority Order

| #   | File                                               | Issue              | Priority  |
| --- | -------------------------------------------------- | ------------------ | --------- |
| 1   | `src/fusion/features/crowd_beliefs.py:186`         | Missing table      | ⚠️ Medium |
| 2   | `scripts/_deprecated/backfill_sparse_sources.py:2` | Deprecated code    | 🔵 Low    |
| 3   | `scripts/ingest_databento_fx_options.py:244`       | Future enhancement | 🔵 Low    |
