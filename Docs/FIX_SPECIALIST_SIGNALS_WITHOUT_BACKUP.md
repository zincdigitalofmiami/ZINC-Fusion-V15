# Fix Specialist Signals Without Backup — Plan

**Date:** 2026-01-30  
**Context:** Six specialists (biofuel, energy, fed, fx, tariff, volatility) were overwritten with degraded or broken signals. No backup exists. This plan fixes code bugs and regenerates signals.

---

## 1) Damage Summary

| Bucket      | Issue                          | Root cause |
|-------------|--------------------------------|------------|
| tariff      | Constant -1.0 (zero variance)  | Formula bug: `deadline_risk * deadline_vol_mult - 1.0` yields -1.0 when deadline_risk=0 |
| fed, fx     | Reduced variance vs prior      | Regenerated with current code; may be acceptable after tariff/crush fixed |
| crush       | 0 signals in dry-run           | `X_full.dropna()` drops all rows when any column has NaN (e.g. sparse open_interest) |
| china       | Strict validation fails        | bdry/sblk in primary but dropped by loader; fx_usdbrl duplicate |

---

## 2) Fixes (in dependency order)

### Phase A: Specialist logic (xgb_signals.py + event_signals.py)

| # | Fix | File:Location | Change |
|---|-----|---------------|--------|
| A1 | **CRUSH dropna cascade** | xgb_signals.py ~446 | Replace `X_full.dropna()` with `X_full.dropna(subset=CORE_FEATURES)` where `CORE_FEATURES = [c for c in self.config.primary_features if c in X_full.columns]`. Use same pattern at ~731 for Substitutes. |
| A2 | **CHINA primary → secondary** | xgb_signals.py 901-902 | Move `bdry_close`, `sblk_close` from `primary_features` to `secondary_features`. |
| A3 | **CHINA remove duplicate** | xgb_signals.py 912 | Remove `fx_usdbrl` from `secondary_features` (duplicate of fred_dexbzus). |
| A4 | **TARIFF constant -1.0** | event_signals.py 296 | Change `combined_risk = tariff_risk + (deadline_risk * deadline_vol_mult - 1.0)` to `combined_risk = tariff_risk + deadline_risk * (deadline_vol_mult - 1.0)` so when deadline_risk=0 the additive term is 0, not -1.0. |

### Phase B: Validation (no code change)

| # | Step | Command |
|---|------|---------|
| B1 | Crush dry-run | `python scripts/generate_specialist_signals.py --bucket crush --strict --dry-run` → exit 0, >0 signals reported |
| B2 | China dry-run | `python scripts/generate_specialist_signals.py --bucket china --strict --dry-run` → exit 0, >0 signals reported |
| B3 | Tariff sanity  | After A4, run tariff dry-run and spot-check signal_1 variance (not constant) |

### Phase C: Regenerate and verify

| # | Step | Command / check |
|---|------|------------------|
| C1 | Full signal generation | `python scripts/generate_specialist_signals.py --bucket all` (no --dry-run) |
| C2 | §8.5 GO/NO-GO SQL | Re-run aggregation by bucket: row_count, min/max date, last_180d rows, stddev(signal_1). All buckets: freshness ≤2d, coverage ≥90%, stddev > epsilon. |
| C3 | Tariff sanity        | tariff stddev(signal_1) >> 0 (e.g. > 0.1). |

---

## 3) File / line evidence

- **Crush dropna:** `src/fusion/specialists/xgb_signals.py` L446, L731.  
- **China primary/secondary:** `src/fusion/specialists/xgb_signals.py` L895-916 (primary_features and secondary_features lists).  
- **Tariff combined_risk:** `src/fusion/specialists/event_signals.py` L296.  
- **Loader (Agent 3):** ZS, china_pmi, CHNPRINTO01IXPYM already added in data_loaders.py (commit 50c1a88).

---

## 4) Risks and rollback

- **Risk:** Full regeneration overwrites all 11 buckets again. If something else is wrong, we have no backup.  
- **Mitigation:** Run Phase B (dry-runs) first; only run C1 after B1–B3 pass.  
- **Rollback:** None (no backup). Fixes are the only path.

---

## 5) Execution order

1. Implement A1 (Crush + Substitutes dropna subset).  
2. Implement A2, A3 (China primary/secondary + remove fx_usdbrl).  
3. Implement A4 (Tariff combined_risk formula).  
4. Run B1, B2, B3; fix any remaining issues.  
5. Run C1 (full generation).  
6. Run C2, C3 (§8.5 and tariff sanity).  
7. Update worklog/checklist and report.

---

## 6) Success criteria

- Crush and China strict dry-runs: exit 0, >0 signals.  
- Tariff: signal_1 has non-trivial variance (e.g. stddev > 0.1).  
- §8.5: all 11 buckets pass freshness, coverage, and variance thresholds (or documented exceptions with follow-up).
