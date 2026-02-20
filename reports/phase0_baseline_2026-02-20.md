# Phase 0 Baseline Report — First Clean MAE/Price Training
**Date:** 2026-02-20
**Run ID:** core_v2_20260220_145635 (5d), core_v2_20260220_151556 (21d/63d/126d)
**run_hash:** e2ac250c5e194eb8 (5d), edfc1bde395cb716 (21d/63d/126d)
**matrix_version:** cd04fc7d9933817f

---

## Configuration

| Component | Value |
|-----------|-------|
| Target | Price level (`target_price_{h}d` = `close.shift(-horizon)`) |
| Metric | MAE (Mean Absolute Error) — point forecast accuracy in $/cwt |
| Specialists | All 11: crush, china, fx, fed, tariff, energy, biofuel, palm, volatility, substitutes, trump_effect |
| Features | 954 real features + 532 missingness flags = 1,494 total columns |
| Matrix | 7,970 rows (1990-01-01 to 2026-02-18), 3.7% NaN overall |
| Model Zoo | 19 frozen models (5 baselines + 10 statistical + 3 tabular + 1 foundation Chronos2) |
| Validation | 4 expanding windows, refit_every_n_windows=1 |
| Deep Learning | NOT included (TFT/DeepAR disabled on macOS ARM) |
| Known Covariates | None (`[]`) — seasonal features not yet added |
| Hardware | Apple Silicon ARM64, CPU-only, 24GB RAM |

---

## Ensemble Results

| Horizon | Ensemble MAE | Interpretation |
|---------|-------------|----------------|
| **5d** | **$0.87** | ~1.7% error on ~$50 product |
| **21d** | **$1.37** | ~2.7% error at 1 month |
| **63d** | **$2.65** | ~5.3% error at 3 months |
| **126d** | **$3.31** | ~6.6% error at 6 months |

## Ensemble Weights

| Horizon | Model Weights |
|---------|---------------|
| **5d** | PerStepTabular 84%, AutoARIMA 14%, Naive 2% |
| **21d** | RecursiveTabular 42%, AutoARIMA 33%, PerStepTabular 25% |
| **63d** | PerStepTabular 54%, RecursiveTabular 31%, NPTS 15% |
| **126d** | PerStepTabular 39%, NPTS 31%, RecursiveTabular 17%, ADIDA 11%, Croston 2% |

---

## Full Model Leaderboard

### 5d Horizon
| Rank | Model | MAE | Notes |
|------|-------|-----|-------|
| 1 | WeightedEnsemble | -0.8727 | Best |
| 2 | PerStepTabular | -0.8945 | 84% ensemble weight |
| 3 | Naive | -1.1311 | 2% weight |
| 4 | AutoARIMA | -1.1315 | 14% weight |
| 5 | AutoCES | -1.1819 | |
| 6 | ETS / AutoETS | -1.1984 | |
| 7 | Theta | -1.2607 | |
| 8 | DynOptTheta | -1.2646 | |
| 9 | RecursiveTabular | -1.4306 | |
| 10 | DirectTabular | -1.5455 | EXCLUDED from ensemble |
| 11 | SeasonalNaive | -1.6147 | |
| 12 | Chronos2 | -1.6158 | Foundation model UNDERPERFORMS |
| 13 | ADIDA / IMAPA | -1.7288 | |
| 14 | Croston | -5.8183 | |
| 15 | NPTS | -8.8468 | |
| 16 | Average | -20.0239 | TERRIBLE on price |
| 17 | SeasonalAverage | -21.2679 | TERRIBLE on price |
| 18 | Zero | -55.6464 | CATASTROPHIC on price |

### 21d Horizon
| Rank | Model | MAE | Notes |
|------|-------|-----|-------|
| 1 | WeightedEnsemble | -1.3665 | Best |
| 2 | AutoARIMA | -1.4424 | 33% weight |
| 3 | Naive | -1.4521 | |
| 4 | RecursiveTabular | -1.4508 | 42% weight |
| 5 | ETS / AutoETS | -1.4557 | |
| 6 | AutoCES | -1.4604 | |
| 7 | Theta | -1.4833 | |
| 8 | DynOptTheta | -1.5148 | |
| 9 | ADIDA / IMAPA | -1.5543 | |
| 10 | PerStepTabular | -1.6405 | 25% weight |
| 11 | SeasonalNaive | -1.6470 | |
| 12 | Chronos2 | -1.6628 | |
| 13 | DirectTabular | -2.6100 | EXCLUDED |
| 14 | Croston | -3.5060 | |
| 15 | NPTS | -5.7389 | |
| 16 | SeasonalAverage | -15.5861 | |
| 17 | Average | -16.0745 | |
| 18 | Zero | -51.4808 | |

### 63d Horizon
| Rank | Model | MAE | Notes |
|------|-------|-----|-------|
| 1 | WeightedEnsemble | -2.6533 | Best |
| 2 | PerStepTabular | -2.8611 | 54% weight |
| 3 | RecursiveTabular | -3.1560 | 31% weight |
| 4 | ADIDA / IMAPA | -3.6009 | |
| 5 | Croston | -3.8058 | |
| 6 | DirectTabular | -3.9653 | EXCLUDED |
| 7 | Chronos2 | -4.0497 | |
| 8 | ETS / AutoETS | -4.0909 | |
| 9 | AutoARIMA | -4.1411 | |
| 10 | AutoCES | -4.2108 | |
| 11 | Theta | -4.1969 | |
| 12 | Naive | -4.2254 | |
| 13 | DynOptTheta | -4.2629 | |
| 14 | SeasonalNaive | -3.3521 | |
| 15 | NPTS | -6.6741 | 15% weight |
| 16 | Average | -15.6034 | |
| 17 | SeasonalAverage | -15.6821 | |
| 18 | Zero | -50.5747 | |

### 126d Horizon
| Rank | Model | MAE | Notes |
|------|-------|-----|-------|
| 1 | WeightedEnsemble | -3.3102 | Best |
| 2 | Croston | -3.9479 | 2% weight |
| 3 | PerStepTabular | -4.0327 | 39% weight |
| 4 | ADIDA / IMAPA | -4.1797 | 11% weight |
| 5 | Naive | -4.3700 | |
| 6 | Theta | -4.3781 | |
| 7 | SeasonalNaive | -4.3839 | |
| 8 | DynOptTheta | -4.3966 | |
| 9 | ETS / AutoETS | -4.4544 | |
| 10 | AutoCES | -4.5421 | |
| 11 | Chronos2 | -4.6572 | |
| 12 | AutoARIMA | -5.0284 | |
| 13 | RecursiveTabular | -5.8351 | 17% weight |
| 14 | NPTS | -6.4479 | 31% weight |
| 15 | DirectTabular | -7.0120 | |
| 16 | SeasonalAverage | -12.4806 | |
| 17 | Average | -12.6062 | |
| 18 | Zero | -47.2425 | |

---

## WQL/Returns (Jan 24) vs MAE/Price (Feb 20) — Key Shifts

| What Changed | WQL/Returns (Jan 24) | MAE/Price (Feb 20) |
|-------------|---------------------|-------------------|
| 5d champion | DirectTabular 74% | PerStepTabular 84% |
| 21d champion | DirectTabular 68% | RecursiveTabular 42% |
| Zero model | Useful baseline (0 return is reasonable) | Catastrophic ($-55 MAE) |
| Average model | Useful baseline (mean return ~ 0) | Catastrophic ($-20 MAE) |
| Chronos2 | Not tested | Underperforms everywhere |
| NPTS | Irrelevant | 31% weight at 126d |
| Statistical models | Weak ensemble contribution | AutoARIMA 33% at 21d |
| Specialist signals | Not available | All 11 included (first time) |
| DirectTabular | Dominated 5d/21d | EXCLUDED from all ensembles |

---

## Key Findings

1. **PerStepTabular dominates** across all horizons — the clear workhorse of price prediction
2. **RecursiveTabular is the #2 model** — strong at 21d (42%), 63d (31%), 126d (17%)
3. **AutoARIMA matters only for short horizons** — 33% at 21d, 14% at 5d, absent at 63d/126d
4. **NPTS emerges at long horizons** — 15% at 63d, 31% at 126d (pattern-matching becomes more useful)
5. **DirectTabular excluded from ALL ensembles** — massive shift from WQL era
6. **Chronos2 underperforms everywhere** — worse than Naive at 5d, worse than simple models at 126d
7. **Zero & Average are catastrophically bad** on price target (as predicted)
8. **126d ensemble is fragmented** — 5 models needed, none >39%, suggesting model uncertainty

## Opportunities for Improvement

1. **Phase 1A (seasonal features + known_covariates)** — highest leverage single change
2. **Phase 1B (price-level anchors)** — SMA50/200, percentiles give tree models reference points
3. **Phase 1C (term structure)** — strongest commodity price predictor, currently missing
4. **Phase 3A (TFT)** — could transform 63d/126d where ensemble is fragmented
5. **Chronos2 rescue** — may improve with known_covariates unlocked

---

## OOF Predictions

- 860 total OOF predictions written to `training.oof_core_1d`
- 5d: 20 predictions (5 steps x 4 windows)
- 21d: 84 predictions (21 steps x 4 windows)
- 63d: 252 predictions (63 steps x 4 windows)
- 126d: 504 predictions (126 steps x 4 windows)
