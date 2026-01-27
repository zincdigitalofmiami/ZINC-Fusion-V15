# Cohesive Specialist Signals Fix Plan (Strict Data, Fail-Closed)

Status: TODO (unchecked)
Last updated: 2026-01-26

## Principle 0 -- Define "Critical" and Enforce It
- [ ] 0.1 Create bucket-by-bucket critical data contract: per bucket define critical_features, critical_sources (table + cadence + max staleness), and cadence-normalization rules (ffill windows and staleness representation).
- [ ] 0.2 Default runtime mode STRICT_DATA=true with hard failures on missing or stale critical inputs and no proxy substitutions.
- [ ] 0.2a Emergency mode only when ALLOW_EMERGENCY_FALLBACKS=true is explicitly set; each fallback writes an audit row, forces confidence near zero, sets status EMERGENCY_PROXY, and requires an override reason string.

## Phase 1 -- Fix the Biggest Root Cause: Silent Degradation
- [x] 1.1 Update base.py validate_inputs to check critical_features (not just primary) and return missing lists; in strict mode, missing criticals raise and fail at generation.
- [x] 1.2 Remove or disable per-bucket validation overrides that weaken criticality (Biofuel): in strict mode require agreed RIN and LCFS minimal set; allow forward-fill within SLA only; stale beyond SLA hard fails.
- [x] 1.3 Make generate_specialist_signals.py fail loud: critical source load failures are hard errors; print root cause; write run report; exit non-zero in strict mode or mark bucket failed in partial mode.

## Phase 2 -- Continuous Ingestion (WASDE is Non-Negotiable)
- [ ] 2.1 Replace one-time WASDE backfill with continuous ingestion: create scripts/ingest_wasde_continuous.py, detect newest release, ingest monthly with revisions (vintage_date), track publish_date, and enforce SLA (max 45 days).
- [ ] 2.2 Implement continuous ingestion and health checks for other critical sources (EPA RIN, LCFS, shipping indices, palm proxies, term structure inputs) with cadence + max staleness.
- [ ] 2.3 Ensure critical sources are implemented and continuously ingested; remove any "fetch not implemented" sources from the critical contract.

## Phase 3 -- Naming and Wiring Consistency (No More Silent Skips)
- [ ] 3.1 Add a single alias map and apply it in matrix build or specialist input prep (example: usd_cny mapped from the actual FRED series).
- [ ] 3.2 Extend health checks to report alias resolution status: resolved column, source column, last valid date.

## Phase 4 -- Data Gates: Enforce SLAs Before Signals Run
- [ ] 4.1 Add preflight gate script scripts/data_gate_specialists.py to check critical source tables (exist, recent rows, SLA staleness) and matrix sig_{bucket}_1 coverage; emit PASS or FAIL with remediation; strict mode blocks run, emergency mode records override and degrades confidence.
- [ ] 4.2 Create analytics.data_health_1d table to store daily results (last_seen_date per source, null-rate per sig column, buckets failing vs passing). Note: requires explicit DB approval.

## Phase 5 -- Specialist Behavior Changes (Strict by Default)
- [ ] 5.1 Biofuel: RIN and LCFS are critical; remove ZL-only fallback in strict mode; forward-fill only within SLA; stale or insufficient data fails bucket (strict) or marks failed (partial).
- [ ] 5.2 Crush: WASDE required and fresh; if supply.usda_wasde_1m is stale beyond SLA, fail; add wasde_age_days and release flags; enforce monthly-to-daily forward-fill with staleness checks.
- [ ] 5.3 Remove silent try/except swallowing in generate_specialist_signals.py; collect errors then fail; always print root cause and missing tables or columns.

## Phase 6 -- Centralize Config (Minimal but Sufficient)
- [ ] 6.1 Add src/fusion/config/specialist_config.yaml with critical features, per-source SLA (cadence + max staleness), lookback or min_data_points where needed, model_type, and output columns.
- [ ] 6.2 Fix .env loading path resolution once so scripts behave consistently.

## Phase 7 -- Tests and Proof
- [ ] 7.1 Add strict-mode tests: each specialist fails when critical inputs are missing and passes with valid inputs; outputs are non-constant.
- [ ] 7.2 Add integration test: full generation on recent 1y window; verify all 11 buckets write training.specialist_signals_1d; training.matrix_1d has populated sig_{bucket}_1 on recent trade_date; health report is green.
- [ ] 7.3 Optional ablation check: core performance with or without each bucket's signals.

## Minimal UI and Docs Updates (No New Terms)
- [ ] Align UI and docs vocabulary to existing terms: Posture (ACCUMULATE / COVER / DEFER), Downside Risk, Confidence Bands, Probability Surface.

## Updated Success Criteria (Strict)
- [ ] WASDE ingestion is continuous, automated, tracked, and SLA-enforced.
- [ ] Every bucket's critical sources meet freshness SLAs.
- [ ] No bucket produces green signals when critical inputs are missing.
- [ ] training.specialist_signals_1d has all 11 buckets for >= 90% of trade days in the last 30 days.
- [ ] training.matrix_1d has non-null sig_{bucket}_1 for all buckets on those days.
- [ ] Emergency fallback requires explicit override, leaves an audit trail, and forces degraded status/confidence.

## Priority (Do This First)
- [ ] Start with Phase 2.1 (continuous WASDE) and Phase 4 (data gate).
