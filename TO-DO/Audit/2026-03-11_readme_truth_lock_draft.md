# README Truth-Lock Record (Approved + Applied)

Date: 2026-03-11
Scope: Freeze README architecture/settings to current code + operational evidence before finalization.
Status: APPROVED + APPLIED on 2026-03-11.

## 1) Verified Facts (Resolved)

1. Core predicts future **price level** targets, not returns.
- Evidence: `src/fusion/core_training/build_matrix.py:2310-2323` (`target_price_{h}d = close.shift(-horizon)`).
- Evidence: `src/fusion/core_training/config.py:39` (`HORIZONS = [5, 21, 63, 126]`).
- Confidence: High.

2. Core optimization metric is **MAE**.
- Evidence: `src/fusion/core_training/config.py:349` (`eval_metric: str = "MAE"`).
- Confidence: High.

3. Core persisted output contract is single `predicted_price` (+ `target_value` for evaluation) in OOF table.
- Evidence: `src/fusion/core_training/config.py:303-309` (OOF columns include `predicted_price`, `target_value`).
- Evidence: `src/fusion/core_training/train_models.py:397-402` (writes `predicted_price` from predictor row `mean` fallback `0.5`).
- Evidence: `scripts/generate_production_forecasts.py:5-10`, `:145-177`, `:289-314` (production quantiles calibrated from OOF residuals around `predicted_price`).
- Confidence: High.

4. Big-11 specialist buckets include `trump_effect`.
- Evidence: `src/fusion/specialists/base.py:25-37`.
- Confidence: High.

5. Runtime DB access uses `pg` (frontend) and `psycopg2`/SQLAlchemy (Python), not PrismaClient.
- Evidence: `frontend/src/lib/db.ts:15-17` (imports `Pool` from `pg`).
- Evidence: `src/fusion/db/connection.py:41-45`, `:150-177` (`psycopg2` + SQLAlchemy read/write split).
- Evidence: `rg` scan finds `PrismaClient` only in `scripts/_deprecated/*`.
- Confidence: High.

6. Allowed schema set is 12 and includes `vegas`.
- Evidence: `prisma/schema.prisma:7-10` (`schemas = ["alt", "analytics", "econ", "features", "forecasts", "mkt", "model", "ops", "pos", "supply", "training", "vegas"]`).
- Evidence: `scripts/check_local_v15_parity.sql:3-24` enforces same 12-schema list.
- Confidence: High.

7. Banned schema policy exists in code-reference gates.
- Evidence: `scripts/check_sql_table_references.py:38-47` banned set (`raw`, `gold`, `silver`, `bronze`, `monitoring`, `specialist`, `weather`, `archive`).
- Evidence: `.pre-commit-config.yaml:35-40` runs SQL table contract check.
- Confidence: High.

8. Latest local model run evidence is recent and coherent across horizons.
- Runtime evidence (local DB target): `localhost/zinc_fusion_v15_local`.
- Latest OOF run hash: `04ac115d4a86262c`.
- Latest OOF trained window: `2026-03-04 18:17:41` to `2026-03-04 18:59:12`.
- OOF rows/horizons: `860` rows across `[5, 21, 63, 126]`.
- `training.model_runs_event` has 4 promoted success rows for this run hash with MAE + pinball metrics.
- Confidence: High for local; unknown for cloud until cloud DB is queried directly.

## 2) Active Mismatches / Caveats (Open)

1. Core quantile wording needs precision.
- Finding: AutoGluon predictor logs still include `quantile_levels` (e.g., `models/core_v2/5d/logs/predictor_log.txt:2694`, `:2853`, `:3012`).
- Impact: Saying “core produces no quantiles at all” can be interpreted as false at model-internal level.
- Recommendation wording: “Persisted core contract is single `predicted_price`; production target-zone quantiles are derived in L2/L3 residual calibration.”
- Severity: Medium.
- Confidence: High.

2. Monte Carlo probability fields are not guaranteed populated in every production row.
- Evidence: `scripts/run_monte_carlo.py:65` (`N_SIMULATIONS = 10000`) and `:658-667` writes `prob_*` + `mc_runs`.
- Runtime evidence: recent `production_1d` rows for hash `04ac115d4a86262c` contain `prob_* = NULL`, while `forward_v1_*` rows have `mc_runs=10000` and populated probabilities.
- Impact: README statement can over-promise if MC job has not run on a row set.
- Severity: Medium.
- Confidence: High.

3. Local vs cloud target ambiguity remains unless explicitly documented.
- Runtime evidence: current env resolves to local DB (`localhost/zinc_fusion_v15_local`).
- Evidence: `scripts/sync_cloud_to_local_db.py:9-13`, `:107-137`, `:260-269` expects cloud source and localhost destination, with safety checks.
- Impact: README can imply current runtime always cloud when local mirror is being used in active dev workflows.
- Severity: High.
- Confidence: High.

4. Dual Prisma config files can create confusion.
- Active wrapper path: `scripts/prisma.sh:25` and `scripts/prisma_status.sh:26` use `--config config/prisma.config.ts`.
- Additional file exists: `prisma/prisma.config.ts:1-27` with different assumptions (`DATABASE_URL` only).
- Impact: accidental invocation drift and inconsistent env behavior.
- Severity: Medium.
- Confidence: High.

## 3) Proposed README Text (Approval Candidate)

Use this wording to avoid drift while staying true to implementation:

1. Core output contract
- “Core training optimizes MAE for `target_price_{h}d` (5, 21, 63, 126).
- Persisted core contract is a single `predicted_price` per horizon in `training.oof_core_1d`.
- Production target-zone quantiles (`p30/p50/p70/p10_cal/p90_cal`) are generated downstream by residual calibration (L2/L3), not read directly from core OOF quantile columns.”

2. Probability pipeline
- “Monte Carlo probabilities (`prob_enter_zone`, `prob_touch_p10`, `prob_touch_p90`, `mc_runs`) are populated by `scripts/run_monte_carlo.py` (10,000 simulations). If MC has not been run for a row set, `prob_*` fields can remain null.”

3. Environment truth
- “Production deploy targets cloud Postgres; local development commonly targets a localhost mirror. Verify active target via env before audits/migrations.”

4. Prisma usage
- “Prisma is used for schema/migrations/validation. Runtime query paths use `pg` (frontend) and `psycopg2`/SQLAlchemy (Python).”

## 4) Approval Gate (Closed)

Approved and applied as the canonical README lock:
- [x] Core output contract wording update
- [x] Monte Carlo conditional-population wording update
- [x] Cloud vs local target clarification
- [x] Explicit Prisma runtime-policy wording
