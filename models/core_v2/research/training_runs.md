# Core Training Run History

## Run 4: Price Target (2026-02-19) — FIRST PRICE TARGET RUN

**Config:**
- Horizon: 126d
- Target: `target_price_126d` (close.shift(-126)) — ZL futures price
- Metric: WQL (old config — MAE code change happened after this run started)
- Quantiles: [0.3, 0.5, 0.7] (old config)
- Validation: 4 expanding windows, freq=B
- Data: 9,322 rows, 29.4% NaN, 1 time series
- Specialist signals: present in matrix but ALL non-informative (NaN)
- Runtime: 1,111.54s (~18.5 min)

**Leaderboard (WQL, higher=better, sign-flipped):**

| Rank | Model | WQL | Train Time | Notes |
|------|-------|-----|------------|-------|
| 1 | WeightedEnsemble | -0.0691 | 1.2s | Best |
| 2 | PerStepTabular | -0.0776 | 405s | CatBoost per-step |
| 3 | SeasonalNaive | -0.0815 | 0.4s | |
| 4 | Theta | -0.0817 | 5.6s | |
| 5 | Naive | -0.0818 | 0.5s | |
| 6 | DynOptTheta | -0.0824 | 7.0s | |
| 7 | ADIDA | -0.0827 | 4.6s | |
| 8 | IMAPA | -0.0827 | 1.7s | |
| 9 | Croston | -0.0832 | 2.0s | |
| 10 | ETS | -0.0844 | 3.1s | |
| 11 | AutoETS | -0.0844 | 3.2s | |
| 12 | Chronos2 | -0.0868 | 437s + 138s val | 575s total, biggest time sink |
| 13 | DirectTabular | -0.0900 | 40.6s | CatBoost direct |
| 14 | AutoCES | -0.0937 | 21.0s | |
| 15 | AutoARIMA | -0.0955 | 7.0s | |
| 16 | RecursiveTabular | -0.1217 | 12.4s | |
| 17 | NPTS | -0.1439 | 2.0s | |
| 18 | Average | -0.1924 | 0.4s | |
| 19 | SeasonalAverage | -0.1952 | 0.4s | |
| 20 | Zero | -0.5809 | 1.7s | |

**Ensemble Weights:**
- PerStepTabular: 51%
- SeasonalNaive: 20%
- DirectTabular: 14%
- NPTS: 10%
- RecursiveTabular: 3%
- Croston: 2%

**Key Observations:**
- Price target produces much more sensible rankings vs returns target
- PerStepTabular (CatBoost) dominates ensemble — expected for tabular features
- SeasonalNaive picks up ZL seasonal price patterns (20% weight)
- Chronos2 mid-pack (-0.0868) — better relative standing than with returns
- Zero model properly last (predicting 0 price = terrible)
- Still no specialist signals — this is core-alone baseline on price target

---

## Run 3: Returns Target with Full Zoo (2026-02-18 20:30) — DUPLICATE

Identical to Run 2 (deterministic seed=123, same data). Skipping.

---

## Run 2: Returns Target with Full Zoo (2026-02-18 19:32)

**Config:**
- Horizon: 126d
- Target: `target_ret_126d` (pct_change returns) — OLD, WRONG
- Metric: WQL, Quantiles: [0.3, 0.5, 0.7]
- Data: 9,321 rows, 24.1% NaN
- Runtime: 945.25s

**Best:** WeightedEnsemble -0.8936 WQL
**Ensemble:** NPTS 38%, PerStepTabular 21%, Zero 18%, AutoCES 12%, Average 12%

**Why this was wrong:** Zero model getting 18% weight = predicting 0% return = "price stays flat". That's a reasonable returns bet but useless for price forecasting. The ensemble was gaming returns not predicting prices.

---

## Run 1: Original Dry Run (2026-01-24)

**Config:**
- Horizon: 126d
- Target: `target_ret_126d` (returns) — OLD, WRONG
- Metric: WQL, Quantiles: [0.3, 0.5, 0.7]
- Data: 14,502 rows, 43.6% NaN
- 17 models (no Chronos2, no AutoCES)
- Runtime: 424.69s

**Best:** WeightedEnsemble -0.6052 WQL
**Ensemble:** AutoARIMA 33%, NPTS 14%, PerStepTabular 53%

**Context:** Mechanics validation only. No specialist signals. Different matrix (more rows, more NaN).
