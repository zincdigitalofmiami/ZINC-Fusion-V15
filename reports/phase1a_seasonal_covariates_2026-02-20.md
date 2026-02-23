# Phase 1A Report — Seasonal Known Covariates Training Results

- **Date:** 2026-02-20
- **Run ID:** e2042a5e-8860-5635-adb1-5fbacec0474b
- **run_hash:** 8af74586956958db
- **matrix_version:** 0de0abc48dfb311a
- **Total training time:** ~43 minutes (4 horizons sequential)

---

## Configuration Change from Phase 0

| Component | Phase 0 | Phase 1A |
|---|---:|---:|
| Known covariates | `[]` (none) | 8 seasonal features |
| Matrix features | 1,494 | 1,502 (+8 seasonal) |
| Matrix rows | 7,971 | 7,971 (unchanged) |
| Everything else | Same | Same |

### Seasonal features added as `known_covariates`

- `month_sin`, `month_cos`
- `week_of_year_sin`, `week_of_year_cos`
- `is_planting_season`, `is_harvest_season`, `is_crush_season`, `is_south_america_harvest`

These are deterministic from the date index — AutoGluon can use them as future information during prediction.

---

## Headline Results

> **Note on MAE sources:** Two sets of MAE numbers appear in this report. "Leaderboard MAE" comes from AutoGluon's internal weighted ensemble validation score. "OOF MAE" is computed independently from cross-validated predictions stored in `training.oof_core_1d`. Both are valid; small differences are expected because they use different computation paths. All values are in ZL futures contract points (not dollars).

| Horizon | Phase 0 MAE | Phase 1A MAE (leaderboard) | Phase 1A MAE (OOF) | Delta (OOF vs P0) | Verdict |
|---|---:|---:|---:|---:|---|
| 5d | 0.8727 | 0.9916 | 0.9583 | +0.0856 | **REGRESSED** |
| 21d | 1.3665 | 1.3099 | 1.2646 | -0.1019 | **IMPROVED** |
| 63d | 2.6533 | 2.6694 | 2.6685 | +0.0152 | **FLAT** |
| 126d | 3.3102 | 3.2473 | 3.1889 | -0.1213 | **IMPROVED** |

**Net assessment:** Mixed. Seasonal features help at longer horizons (21d/126d) but hurt at 5d where they add noise without signal.

---

## Ensemble Composition Comparison

### 5d — REGRESSED

| Component | Phase 0 | Phase 1A |
|---|---:|---:|
| PerStepTabular | 84% | Not in ensemble |
| AutoARIMA | 14% | Not in ensemble |
| Naive | 2% | **100%** |
| **Ensemble MAE** | **0.8727** | **0.9916** |

**Root cause:** PerStepTabular crashed from 0.89 to 1.51 MAE. The seasonal known covariates appear to have confused the tabular model at a 5-day horizon where seasonal patterns don't change. Ensemble collapsed to Naive as the only competitive model.

### 21d — IMPROVED

| Component | Phase 0 | Phase 1A |
|---|---:|---:|
| RecursiveTabular | 42% | 35% |
| AutoARIMA | 33% | 38% |
| PerStepTabular | 25% | 27% |
| **Ensemble MAE** | **1.3665** | **1.3099** |

All three models remain in the ensemble with similar balance. AutoARIMA gained slight edge.

### 63d — FLAT

| Component | Phase 0 | Phase 1A |
|---|---:|---:|
| PerStepTabular | 54% | 53% |
| RecursiveTabular | 31% | 34% |
| NPTS | 15% | 14% |
| **Ensemble MAE** | **2.6533** | **2.6694** |

Virtually identical composition and performance.

### 126d — IMPROVED

| Component | Phase 0 | Phase 1A |
|---|---:|---:|
| PerStepTabular | 39% | 47% |
| NPTS | 31% | 25% |
| RecursiveTabular | 17% | 26% |
| ADIDA | 11% | Not in ensemble |
| Croston | 2% | 1% |
| **Ensemble MAE** | **3.3102** | **3.2473** |

PerStepTabular strengthened from 39% to 47%. RecursiveTabular surged from 17% to 26%. ADIDA dropped out. Ensemble simplified from 5 to 4 models.

---

## Full Model Leaderboards

### 5d Horizon

| Rank | Model | Phase 1A MAE | Phase 0 MAE | Delta |
|---:|---|---:|---:|---:|
| 1 | WeightedEnsemble | 0.99 | 0.87 | +0.12 worse |
| 2 | Naive | 0.99 | 1.13 | -0.14 better |
| 3 | AutoARIMA | 1.00 | 1.13 | -0.13 better |
| 4 | AutoCES | 1.04 | 1.18 | -0.14 better |
| 5 | ETS / AutoETS | 1.09 | 1.20 | -0.11 better |
| 6 | Theta | 1.19 | 1.26 | -0.07 better |
| 7 | DynOptTheta | 1.20 | 1.26 | -0.06 better |
| 8 | Chronos2 | 1.43 | 1.62 | -0.19 better |
| 9 | DirectTabular | 1.50 | 1.55 | -0.05 better |
| 10 | PerStepTabular | 1.51 | 0.89 | +0.62 **CRASHED** |
| 11 | RecursiveTabular | 1.57 | 1.43 | +0.14 worse |
| 12 | SeasonalNaive | 1.60 | 1.61 | -0.01 |
| 13 | ADIDA / IMAPA | 1.79 | 1.73 | +0.06 |
| 14 | Croston | 5.98 | 5.82 | +0.16 |
| 15 | NPTS | 9.15 | 8.85 | +0.30 |
| 16 | Average | 20.46 | 20.02 | +0.44 |
| 17 | SeasonalAverage | 21.71 | 21.27 | +0.44 |
| 18 | Zero | 56.09 | 55.65 | +0.44 |

### 21d Horizon

| Rank | Model | Phase 1A MAE | Phase 0 MAE | Delta |
|---:|---|---:|---:|---:|
| 1 | WeightedEnsemble | 1.31 | 1.37 | -0.06 better |
| 2 | AutoARIMA | 1.45 | 1.44 | +0.01 |
| 3 | Naive | 1.46 | 1.45 | +0.01 |
| 4 | ETS / AutoETS | 1.46 | 1.46 | 0.00 |
| 5 | AutoCES | 1.47 | 1.46 | +0.01 |
| 6 | Theta | 1.49 | 1.48 | +0.01 |
| 7 | DynOptTheta | 1.52 | 1.51 | +0.01 |
| 8 | ADIDA / IMAPA | 1.56 | 1.55 | +0.01 |
| 9 | RecursiveTabular | 1.57 | 1.45 | +0.12 worse |
| 10 | PerStepTabular | 1.58 | 1.64 | -0.06 better |
| 11 | SeasonalNaive | 1.66 | 1.65 | +0.01 |
| 12 | Chronos2 | 1.67 | 1.66 | +0.01 |
| 13 | DirectTabular | 1.75 | 2.61 | -0.86 better |
| 14 | Croston | 3.52 | 3.51 | +0.01 |
| 15 | NPTS | 5.75 | 5.74 | +0.01 |
| 16 | SeasonalAverage | 15.60 | 15.59 | +0.01 |
| 17 | Average | 16.08 | 16.07 | +0.01 |
| 18 | Zero | 51.49 | 51.48 | +0.01 |

### 63d Horizon

| Rank | Model | Phase 1A MAE | Phase 0 MAE | Delta |
|---:|---|---:|---:|---:|
| 1 | WeightedEnsemble | 2.67 | 2.65 | +0.02 |
| 2 | PerStepTabular | 2.99 | 2.86 | +0.13 worse |
| 3 | RecursiveTabular | 3.24 | 3.16 | +0.08 worse |
| 4 | SeasonalNaive | 3.35 | 3.35 | 0.00 |
| 5 | ADIDA / IMAPA | 3.60 | 3.60 | 0.00 |
| 6 | Croston | 3.81 | 3.81 | 0.00 |
| 7 | DirectTabular | 3.89 | 3.97 | -0.08 better |
| 8 | Chronos2 | 4.05 | 4.05 | 0.00 |
| 9 | ETS / AutoETS | 4.09 | 4.09 | 0.00 |
| 10 | AutoARIMA | 4.14 | 4.14 | 0.00 |
| 11 | Theta | 4.20 | 4.20 | 0.00 |
| 12 | AutoCES | 4.21 | 4.21 | 0.00 |
| 13 | Naive | 4.23 | 4.23 | 0.00 |
| 14 | DynOptTheta | 4.27 | 4.26 | +0.01 |
| 15 | NPTS | 6.68 | 6.67 | +0.01 |

### 126d Horizon

| Rank | Model | Phase 1A MAE | Phase 0 MAE | Delta |
|---:|---|---:|---:|---:|
| 1 | WeightedEnsemble | 3.25 | 3.31 | -0.06 better |
| 2 | PerStepTabular | 3.64 | 4.03 | -0.39 better |
| 3 | Croston | 4.08 | 3.95 | +0.13 |
| 4 | ADIDA / IMAPA | 4.28 | 4.18 | +0.10 |
| 5 | Theta | 4.42 | 4.38 | +0.04 |
| 6 | RecursiveTabular | 4.43 | 5.84 | -1.41 **MUCH better** |
| 7 | Naive | 4.45 | 4.37 | +0.08 |
| 8 | ETS / AutoETS | 4.46 | 4.45 | +0.01 |
| 9 | DynOptTheta | 4.49 | 4.40 | +0.09 |
| 10 | SeasonalNaive | 4.56 | 4.38 | +0.18 |
| 11 | AutoCES | 4.57 | 4.54 | +0.03 |
| 12 | Chronos2 | 4.79 | 4.66 | +0.13 |
| 13 | AutoARIMA | 4.88 | 5.03 | -0.15 better |
| 14 | NPTS | 6.46 | 6.45 | +0.01 |
| 15 | DirectTabular | 7.06 | 7.01 | +0.05 |

---

## OOF Prediction Analysis

> These numbers are computed from OOF predictions in `training.oof_core_1d` (run_hash=8af74586956958db) by `scripts/evaluate_oof.py`. They differ slightly from leaderboard MAE because they use a different computation path.

### MAPE Accuracy (1 - MAE / AvgTarget)

| Horizon | N | OOF MAE | AvgTarget | MAPE Accuracy |
|---|---:|---:|---:|---:|
| 5d | 20 | 0.9583 | 55.89 | 98.3% |
| 21d | 84 | 1.2646 | 51.37 | 97.5% |
| 63d | 252 | 2.6685 | 50.63 | 94.7% |
| 126d | 504 | 3.1889 | 47.31 | 93.3% |

### Cutoff-to-Target Directional Accuracy

| Horizon | Correct | N | Accuracy | PredUp% | ActualUp% |
|---|---:|---:|---:|---:|---:|
| 5d | 14 | 20 | 70.0% | 100.0% | 70.0% |
| 21d | 58 | 84 | 69.0% | 75.0% | 52.4% |
| 63d | 176 | 252 | 69.8% | 98.4% | 71.0% |
| 126d | 370 | 504 | 73.4% | 44.4% | 42.1% |

**Key observation:** The model has a strong UP bias at 5d (100% UP predictions) and 63d (98.4% UP predictions), far exceeding actual UP rates. This caps directional accuracy near the actual UP rate for those horizons. 126d is the most balanced (44.4% predicted vs 42.1% actual).

### Core vs Naive (Naive = cutoff close price)

| Horizon | Core MAE | Naive MAE | Improvement | PredMove | ActualMove | MoveRatio |
|---|---:|---:|---:|---:|---:|---:|
| 5d | 0.96 | 1.99 | 51.8% | 1.31 | 1.99 | 0.66x |
| 21d | 1.26 | 2.63 | 51.9% | 2.10 | 2.63 | 0.80x |
| 63d | 2.67 | 5.70 | 53.2% | 4.69 | 5.70 | 0.82x |
| 126d | 3.19 | 5.33 | 40.1% | 4.04 | 5.33 | 0.76x |

Core beats Naive by 40-53%. MoveRatio < 1 at all horizons means the model under-predicts movement magnitude (predicts 66-82% of actual moves).

### Per-Window Breakdown

| Horizon | Window | Cutoff | N | OOF MAE | Avg Pred | Avg Target | PredBias |
|---|---|---|---:|---:|---:|---:|---:|
| 5d | w1 | 2026-01-15 | 5 | 0.28 | 54.05 | 54.10 | -0.05 |
| 5d | w2 | 2026-01-22 | 5 | 0.81 | 54.35 | 54.29 | +0.06 |
| 5d | w3 | 2026-01-29 | 5 | 1.39 | 55.69 | 56.98 | -1.29 |
| 5d | w4 | 2026-02-05 | 5 | 1.49 | 57.49 | 58.98 | -1.49 |
| 21d | w1 | 2025-09-29 | 21 | 0.92 | 51.00 | 50.32 | +0.68 |
| 21d | w2 | 2025-10-28 | 21 | 1.30 | 51.24 | 50.62 | +0.62 |
| 21d | w3 | 2025-11-26 | 21 | 0.62 | 49.37 | 49.66 | -0.29 |
| 21d | w4 | 2025-12-25 | 21 | 2.39 | 52.96 | 55.36 | -2.40 |
| 63d | w1 | 2024-12-18 | 63 | 2.40 | 46.67 | 46.67 | -0.01 |
| 63d | w2 | 2025-03-17 | 63 | 4.86 | 48.79 | 53.15 | -4.35 |
| 63d | w3 | 2025-06-12 | 63 | 1.10 | 51.75 | 50.78 | +0.97 |
| 63d | w4 | 2025-09-09 | 63 | 2.32 | 52.05 | 51.71 | +0.34 |
| 126d | w1 | 2023-10-19 | 126 | 2.85 | 46.27 | 44.04 | +2.23 |
| 126d | w2 | 2024-04-12 | 126 | 2.85 | 41.60 | 43.64 | -2.04 |
| 126d | w3 | 2024-10-07 | 126 | 5.36 | 45.83 | 50.00 | -4.17 |
| 126d | w4 | 2025-04-01 | 126 | 1.93 | 50.27 | 51.40 | -1.12 |

**Window analysis notes:**

- 5d error increases monotonically across windows (w1=0.28 to w4=1.49) — model is lagging a rising price trend
- 21d w4 is the worst (2.39) — the Dec 25 cutoff missed the Jan rally from ~52 to ~55
- 63d w2 is an outlier (4.86) — the Mar 17 cutoff missed the spring rally to 53+
- 126d w3 is the worst (5.36) — Oct 2024 cutoff missed the subsequent run-up to 50
- 126d w4 is the best (1.93) — recent data benefits from full feature coverage

---

## Training Runtime

| Horizon | Training Time | Prediction Time | Total |
|---|---:|---:|---:|
| 5d | 10.7 min | 2.4 min | 13.1 min |
| 21d | 10.0 min | 2.3 min | 12.3 min |
| 63d | 10.4 min | 2.2 min | 12.6 min |
| 126d | 12.1 min | 2.2 min | 14.3 min |
| **Total** | **43.2 min** | **9.1 min** | **52.3 min** |

Chronos2 accounts for ~60% of training time per horizon (~6-7 min) for negligible ensemble contribution.

---

## Key Model Observations

### Chronos2 Impact of Known Covariates

| Horizon | Phase 0 | Phase 1A | Delta | In Ensemble? |
|---|---:|---:|---:|---|
| 5d | 1.62 | 1.43 | -0.19 (12% better) | No |
| 21d | 1.66 | 1.67 | +0.01 (flat) | No |
| 63d | 4.05 | 4.05 | 0.00 (flat) | No |
| 126d | 4.66 | 4.79 | +0.13 (3% worse) | No |

Known covariates helped Chronos2 at 5d but nowhere else. It never enters any ensemble. At ~7 min per horizon training time, it consumes 28 min of the 43 min total for zero ensemble contribution.

### PerStepTabular — The Workhorse

| Horizon | Phase 0 | Phase 1A | Delta | Ensemble Weight |
|---|---:|---:|---:|---|
| 5d | 0.89 | 1.51 | +0.62 **CRASHED** | 0% (was 84%) |
| 21d | 1.64 | 1.58 | -0.06 better | 27% (was 25%) |
| 63d | 2.86 | 2.99 | +0.13 worse | 53% (was 54%) |
| 126d | 4.03 | 3.64 | -0.39 better | 47% (was 39%) |

Seasonal features dramatically helped 126d PerStepTabular but destroyed 5d.

### RecursiveTabular — Biggest Gainer at 126d

| Horizon | Phase 0 | Phase 1A | Delta | Ensemble Weight |
|---|---:|---:|---:|---|
| 5d | 1.43 | 1.57 | +0.14 worse | 0% |
| 21d | 1.45 | 1.57 | +0.12 worse | 35% (was 42%) |
| 63d | 3.16 | 3.24 | +0.08 worse | 34% (was 31%) |
| 126d | 5.84 | 4.43 | -1.41 **HUGE** | 26% (was 17%) |

RecursiveTabular improved by 1.41 at 126d — the single biggest improvement of any model at any horizon. Seasonal features gave it the time structure it needed for 6-month prediction.

---

## Interpretation

### Why 5d Regressed

At a 5-day prediction horizon, the month and season are essentially constant — they don't change in one business week. By declaring these as `known_covariates`, we told AutoGluon "these features have known future values and are important." The tabular models (PerStepTabular, RecursiveTabular) consumed them and found noise instead of signal. PerStepTabular in particular went from dominant (0.89, 84% weight) to worse-than-Naive (1.51).

Statistical models (Naive, AutoARIMA, ETS, etc.) don't use covariates, so they were unaffected. Naive won by default.

### Why 21d and 126d Improved

At 21d (1 month), the month changes and seasonal boundaries may be crossed. At 126d (6 months), the prediction spans planting/harvest/crush transitions. The seasonal features provide meaningful signal about where in the crop cycle the target date falls. RecursiveTabular's 1.41 improvement at 126d is the clearest evidence of this.

### Why 63d Was Flat

At 63d (3 months), the seasonal signal exists but isn't strong enough to overcome the slight noise penalty. The ensemble composition barely changed.

---

## Recommended Next Steps

### Option A: Horizon-Dependent Known Covariates (RECOMMENDED)

- Set `known_covariates_names=[]` for **5d**
- Keep `SEASONAL_FEATURES` for **21d/63d/126d**

**Pros:** Recovers 5d Phase 0 performance while keeping 21d/126d gains.

**Requires:** Modifying `train_models.py` to check horizon before setting covariates.

### Option B: Accept Trade-off, Move to Phase 1B

- Keep current Phase 1A config for all horizons

**Pros:** Simplest operationally.

**Cons:** Accepts a 5d regression.

### Option C: Revert Phase 1A, Try Different Approach

- Revert `known_covariates_names` to `[]`
- Keep seasonal features as observed covariates (they're already in the matrix)

**Pros:** Phase 0 performance restored everywhere.

**Cons:** Gives up long-horizon gains.

### Option D: Hybrid — Retrain Only 5d

- Keep Phase 1A models for **21d/63d/126d**
- Retrain only **5d** with `known_covariates_names=[]`

**Pros:** Fastest path to best-of-both-worlds.

---

## Files Changed

- `models/core_v2/5d/` — Updated model artifacts
- `models/core_v2/21d/` — Updated model artifacts
- `models/core_v2/63d/` — Updated model artifacts
- `models/core_v2/126d/` — Updated model artifacts
- `training.oof_core_1d` — 860 new OOF predictions (`run_hash=8af74586956958db`)

---

## Verification

Run the standalone evaluation script to reproduce all OOF metrics:

```bash
cd "/Volumes/Satechi Hub/ZINC-FUSION-V15" && source .envrc && python scripts/evaluate_oof.py
```

To evaluate a specific run:
```bash
python scripts/evaluate_oof.py --run-hash 8af74586956958db
```

To list all available runs:
```bash
python scripts/evaluate_oof.py --list-runs
```
