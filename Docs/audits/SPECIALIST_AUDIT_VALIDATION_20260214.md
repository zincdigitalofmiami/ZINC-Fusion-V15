# Specialist Audit Validation + Remediation Plan
**Date:** 2026-02-14  
**Purpose:** Validate `SPECIALIST_AUDIT_20260203.md` claims against current code and define a measurable fix plan.

## 1) Validation Result

## Confirmed
1. **API observability mismatch existed:** `overview_models()` omitted `trump_effect` while specialist registry includes it.  
2. **Energy stickiness risk is real:** `irf_signal` is computed as a scalar and injected as a constant term across all dates in one run; main components use long z-score windows, so low day-to-day movement is expected.  
3. **ML specialist retrain cadence can preserve stale behavior:** retraining is date-based (not freshness/novelty-based), so unchanged upstream features can produce effectively unchanged signals.

## Not fully accurate in prior audit
1. **"VAR never re-estimated" is incorrect:** `EnergySignalGenerator.compute()` calls `_fit_var_with_irf()` on each run when data suffices.  
2. **"RF trained once" is incorrect:** ML specialists have `_should_retrain()` logic; issue is weak feature freshness, not missing retrain code.

## Needs data-backed verification before claiming root cause
1. Coverage deficits by bucket in last 180 trading days (must be re-queried now).  
2. Current staleness of WASDE/FRED/RIN/PMI inputs (must be re-measured from DB now, not inferred from old report dates).  
3. IC degradation persistence (must be re-computed OOS with current sample).

## 2) Immediate Code Fix Applied
- Added `trump_effect` to `/api/overview/models` specialist list so API observability matches Big-11 registry.

## 3) Remediation Plan (prioritized)

### Phase A — Measurement discipline (Day 0-1)
- Recompute, from DB, for each specialist: coverage, abstain rate, max-run, input staleness p50/p95, IC_21d OOS.
- Freeze a reproducible snapshot table/file for the run (date-stamped).
- **Exit criteria:** one auditable metric table for all 11 specialists.

### Phase B — Data freshness enforcement (Day 1-3)
- Add/verify hard freshness gates per upstream dependency (WASDE, FRED commodity series, RIN, PMI).
- For stale critical inputs, output explicit abstain metadata (no silent pseudo-signals).
- **Exit criteria:** stale-input buckets fail loud in report; no implicit forward-fill behavior.

### Phase C — Anti-stuck logic (Day 2-5)
- **Energy:** replace scalar IRF contribution with time-varying signal (rolling/refit framework) and shorten responsiveness window where justified.
- **Substitutes/Palm/Crush:** add novelty checks (feature drift or changed-data trigger) so retrain/predict behavior reflects new information.
- **Biofuel:** keep explicit stale gating and require source attribution in metadata (`rin_*`, `index`, `margin_proxy`).
- **Exit criteria:** max consecutive identical-signal run <= 7 trading days for non-event specialists.

### Phase D — Quality control for negative IC (Week 2)
- Add acceptance gates before publishing new specialist model state:
  - minimum OOS IC threshold,
  - sign-stability checks,
  - baseline comparison (naive/last-value).
- **Exit criteria:** any specialist with negative OOS IC fails promotion and keeps prior model/state.

### Phase E — Operational controls (Week 2)
- Daily specialist health job with fail conditions:
  - coverage < 90% (last 180 trading days),
  - abstain rate > 10%,
  - max-run > 7,
  - stale-input breaches.
- **Exit criteria:** alerting + blocking wired into CI/ops runbook.

## 4) Non-negotiable acceptance criteria
- 11/11 specialists visible in API and registry alignment.
- Coverage >= 90% for each specialist (or explicitly approved exception for event-driven buckets).
- No hidden stale-signal behavior; stale inputs produce transparent abstain/degraded outputs.
- Promotion of specialist changes requires OOS evidence, not in-sample metrics.
