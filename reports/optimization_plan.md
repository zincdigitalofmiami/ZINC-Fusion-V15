# ZINC-FUSION-V15 Model Optimization Plan

**Created:** 2026-02-20
**Last Updated:** 2026-02-20

## Progress Tracker

| Phase | Status | Notes |
|-------|--------|-------|
| **Phase 0** | COMPLETE | Baseline established. See `reports/phase0_baseline_2026-02-20.md` |
| **Phase 1A** | CODE DONE, TRAINING PENDING | Seasonal features added to matrix (1,502 features). `known_covariates_names` wired. Matrix rebuilt. Need to train all 4 horizons. |
| **Phase 1B** | Pending | Price-level anchors (SMAs, percentiles) |
| **Phase 1C** | Pending | ZL term structure features |
| **Phase 1D** | Pending | WASDE surprise / export pace delta features |
| **Phase 2A** | Pending | Indonesia GAPKI palm data |
| **Phase 2B** | Pending | Fix options data pipeline |
| **Phase 2C** | Pending | China import statistics |
| **Phase 2D** | Pending | Weather forecasts (forward-looking) |
| **Phase 3A** | Pending | Test TFT on macOS ARM |
| **Phase 3B** | Pending | Test DeepAR |
| **Phase 3C** | Pending | Evaluate Chronos2 post-baseline |
| **Phase 4A** | Pending | Training window optimization |
| **Phase 4B** | Pending | Feature coverage audit |
| **Phase 4C** | Pending | Specialist signal quality audit |

### Phase 0 Baseline (for comparison)

| Horizon | Ensemble MAE | Interpretation |
|---------|-------------|----------------|
| **5d** | **$0.87** | ~1.7% error on ~$50 product |
| **21d** | **$1.37** | ~2.7% error at 1 month |
| **63d** | **$2.65** | ~5.3% error at 3 months |
| **126d** | **$3.31** | ~6.6% error at 6 months |

### Phase 1A Training Command

```bash
cd "/Volumes/Satechi Hub/ZINC-FUSION-V15"
python -c "
from fusion.core_training.train_models import run
run(horizons=[5, 21, 63, 126], symbol='ZL')
"
```

---

## Context

The Core L0 Price Predictor was recently corrected from a broken configuration (WQL metric + returns target) to the correct one (MAE metric + price target). No training run has been executed with the corrected config. The only training artifacts on disk are from a Jan 24 dry run using the old, broken config — meaning **all prior feature importance rankings, model selection weights, and OOF scores are unreliable** and must not be used to justify removing features or data sources.

The goal: formulate a phased optimization plan for the model — what to add, what to keep, what's missing — grounded in the fact that the "slightly broke" model's judgments about data utility cannot be trusted.

### Current Matrix State (verified 2026-02-20)
- **7,971 rows** (1990-01-01 to 2026-02-19)
- **1,502 features** (after Phase 1A seasonal additions) = 962 features + 532 missingness flags + 8 seasonal + 4 targets + 4 metadata
- **NaN fraction: 3.7%** overall (0.3% in recent data) — matrix is CLEAN
- **All 11 specialists populated**: 85,282 signal rows (biofuel from 2010, rest from 1990-2000)
- **66 specialist columns in matrix** (33 signals + 33 _is_missing flags)
- **Target columns present**: target_price_5d, target_price_21d, target_price_63d, target_price_126d

---

## Phase 0: Establish True Baseline (COMPLETE)

**What:** Run the FIRST training with the corrected config.

No optimization until we have a clean baseline. The current system has never been trained with:
- MAE metric (instead of WQL)
- Price target (`target_price_{h}d` instead of `target_ret_{h}d`)
- Specialist signals (the dry run had none)

**Actions:**
1. Ensure all 11 specialist signals are populated in `training.specialist_signals_1d`
2. Rebuild `training.matrix_1d` with current build_matrix.py (includes specialists)
3. Train all 4 horizons (5d/21d/63d/126d) with the 19-model frozen zoo
4. Extract OOF predictions, run audit, log results
5. Compare baseline MAE/price scores against the old WQL/returns audit

**Files:** `src/fusion/core_training/train_models.py`, `src/fusion/core_training/build_matrix.py`
**Verification:** OOF audit report with per-horizon MAE, skill, directional accuracy

**Results:** See `reports/phase0_baseline_2026-02-20.md`

---

## Phase 1: Feature Engineering — Price-Level Features (Week 1-2)

The switch from returns to price fundamentally changes which features matter. Returns strip out level information; price prediction rewards features that anchor to absolute levels.

### 1A. Add Seasonal Calendar Features (COMPLETE — code done, training pending)

Soybean oil has strong seasonal patterns driven by planting (Apr-Jun), harvest (Sep-Nov), and crush demand (Oct-Mar). These are **known future values** — the only category we'd have.

**Added to build_matrix.py (`create_seasonal_features()`):**
- `month_sin` / `month_cos` (circular encoding of month)
- `week_of_year_sin` / `week_of_year_cos` (circular encoding)
- `is_planting_season` (Apr-Jun binary)
- `is_harvest_season` (Sep-Nov binary)
- `is_crush_season` (Oct-Mar binary)
- `is_south_america_harvest` (Mar-May binary)

**Architectural change:** Moved into `known_covariates_names` in train_models.py. Was `[]` — now `SEASONAL_FEATURES` from config.py. This unlocks AutoGluon's ability to use future information for models that support it (Chronos2, Tabular models).

**Files changed:**
- `src/fusion/core_training/config.py` — Added `SEASONAL_FEATURES` list
- `src/fusion/core_training/build_matrix.py` — Added `create_seasonal_features()` function + call in `run()`
- `src/fusion/core_training/train_models.py` — Imported `SEASONAL_FEATURES`, set `known_covariates_names=SEASONAL_FEATURES`

**Matrix rebuilt:** 1,502 features, 7,971 rows. Matrix version: f5fa8b897c6bdb2b

### 1B. Add Price-Level Anchor Features (HIGH PRIORITY)

Tree-based models need absolute reference points to predict price levels.

**Add to build_matrix.py:**
- `sma_50d` / `sma_200d` — simple moving averages of ZL close
- `ema_21d` — exponential moving average
- `price_vs_sma200` — distance from 200-day MA (mean-reversion signal)
- `price_percentile_1y` / `price_percentile_5y` — where is price in its N-year range
- `yoy_price_change` — year-over-year price change (seasonal level)
- `52w_high_pct` / `52w_low_pct` — distance from 52-week high/low

**Files:** `build_matrix.py` (extend `load_futures_base()` or add new function)

### 1C. Add ZL Term Structure Features (HIGH PRIORITY)

Currently the matrix uses only front-month ZL close. Futures term structure is one of the strongest commodity price predictors — it directly reflects market expectations of future supply/demand.

**Add:**
- `zl_spread_1_2` — front vs 2nd month spread
- `zl_term_slope` — regression slope across available months
- `zl_contango_flag` — binary: is curve in contango?
- `zl_basis` — cash vs futures spread (if data available)

**Prerequisite:** Check if Databento provides multi-contract ZL data. If not, this requires a new ingestion pipeline for continuous contract spreads.

**Files:** New ingestion function or extend `databento-futures-daily.ts`, `build_matrix.py`

### 1D. Enhance Supply-Demand Delta Features (MEDIUM PRIORITY)

Currently WASDE features are raw levels. What moves prices is the *surprise* — the delta from expectations.

**Add:**
- `wasde_zs_production_mom` — month-over-month change in production estimate
- `wasde_zs_stocks_mom` — MoM change in ending stocks
- `usda_export_pace_vs_forecast` — cumulative exports vs USDA annual forecast (ratio)

**Files:** `build_matrix.py` (extend `load_usda_wasde()` and `load_usda_exports()`)

---

## Phase 2: Data Enrichment — Fill Critical Gaps (Week 2-4)

### 2A. Indonesia Palm Oil Data (CRITICAL)

**Gap:** Palm specialist uses Malaysia MPOB only. Indonesia produces ~60% of global CPO. The specialist is blind to majority of world supply.

**Action:** Add GAPKI (Indonesian Palm Oil Association) monthly production data
- Production, exports, domestic consumption
- New ingestion job: `gapki-palm-monthly.ts`
- New table: `supply.gapki_palm_1m`
- Merge into matrix alongside MPOB data

**Impact:** Palm specialist effectiveness estimated +30%

### 2B. Fix Options Data Pipeline (MEDIUM)

**Gap:** `mkt.options_1d` is stale (last update 2026-02-13). Options implied volatility is the market's own forward-looking price distribution.

**Action:**
- Diagnose why `databento-options-daily.ts` stopped updating
- Restore daily options flow
- Add IV features to matrix: ATM implied vol, put/call OI ratio, IV skew, IV term structure
- Feed IV directly to volatility specialist

**Files:** `frontend/src/inngest/databento-options-daily.ts`, `build_matrix.py` (extend `load_options_features()`)

### 2C. China Soybean Import Statistics (MEDIUM)

**Gap:** China specialist uses indirect proxies (CNY, ETFs, PMI). Direct import volume data would be a much stronger signal.

**Action:** Add monthly China soybean/soybean oil import data from China customs or GACC
- New table: `supply.china_imports_1m`
- Columns: soybean_imports_mt, soybean_oil_imports_mt, yoy_change

### 2D. Weather Forecasts — Forward-Looking (LOW-MEDIUM)

**Gap:** Only historical observations. NOAA 5-10 day forecasts would help tactical horizons.

**Action:** Add NOAA GFS forecast data for the 4 crop regions
- Forecast temperature and precipitation anomalies
- New table: `alt.weather_forecast_1d`

---

## Phase 3: Model Zoo Expansion — Deep Learning (Week 4+)

### 3A. Test TFT Stability on macOS ARM

**The case for TFT:** The Temporal Fusion Transformer's Variable Selection Network is theoretically ideal for the 213-feature matrix. It can dynamically zero-out irrelevant FRED features and learn non-linear interactions between specialist signals across horizons. The research document's ML argument for TFT is sound, even though its API details were wrong.

**Safety protocol:**
1. Add `KMP_DUPLICATE_LIB_OK=True` to environment safeguards in train_models.py (before torch import)
2. Keep `PYTORCH_MPS_ENABLED=0` (CPU-only)
3. Test TFT **in isolation** first — train a single horizon (126d) with ONLY TFT enabled
4. Conservative config: `hidden_dim=32`, `batch_size=32`, `epochs=50`
5. Monitor memory usage (must stay under 20GB to leave room for OS)

**If stable:** Add to MODEL_ZOO_FROZEN. Expected to dramatically improve 63d/126d horizons.
**If unstable:** Document the failure mode and defer to Linux server.

**Files:** `train_models.py:25-36` (env vars), `config.py:375-401` (MODEL_ZOO_FROZEN)

### 3B. Test DeepAR (After TFT Proven Stable)

**Conservative config:** `num_layers=2`, `hidden_dim=40`
**Same safety protocol as 3A.**

### 3C. Evaluate Chronos2 Performance Post-Baseline

Chronos2 is already in the zoo but hasn't been tested with MAE/price. After Phase 0, check:
- Does Chronos2 make it into the WeightedEnsemble?
- What weight does it receive per horizon?
- If it underperforms, investigate: is it the observed-only covariate limitation?

---

## Phase 4: Training Configuration Optimization (Ongoing)

### 4A. Training Window Analysis

**Current:** Full history (~60 years, 14,600 rows, 43% NaN)
**Issue:** Pre-2000 data has almost no macro features — only price. The model learns two different regimes: sparse-feature (pre-2000) and rich-feature (post-2000).

**Action:** After Phase 0 baseline, experiment with `tactical_window_start` and `strategic_window_start` in config.py:
- Tactical (5d/21d): Try training from 2005+ (20 years, most features present)
- Strategic (63d/126d): Try training from 2000+ (25 years)
- Compare OOF scores against full-history baseline

### 4B. Feature Coverage Audit

After Phase 0, run a per-feature NaN analysis:
- Which features have >50% NaN? When do they start having data?
- Group features by coverage era: pre-1990, 1990-2000, 2000-2010, 2010+
- This informs whether truncating training history is worth the row reduction

### 4C. Specialist Signal Quality Audit

After Phase 0, measure each specialist's actual contribution:
- Information Coefficient (IC) of each specialist signal vs realized target
- Compare core MAE with specialists vs without specialists
- Identify any specialists that degrade performance (abstain rate, staleness)

---

## What NOT to Remove

Per the user's directive — the broken model's judgments about feature utility are unreliable:

1. **KEEP all 150 FRED series** — Under price prediction, slow-moving macro indicators (CPI, M2, rates) have direct cointegration with price levels. The WQL/returns model couldn't see this relationship because returns strip out levels.

2. **KEEP all 28 weather features** — Weather drives supply shocks that affect absolute price. The returns model saw weather as noise; the price model should capture weather→supply→price transmission.

3. **KEEP all 33 specialist signals** — Never tested in a training run. Must be evaluated clean.

4. **KEEP baselines (Average, Zero, Naive, SeasonalNaive, SeasonalAverage)** — Under price prediction, baselines serve different purposes. Average predicts the historical mean price (not zero return). SeasonalAverage captures annual price cycles. They keep the ensemble honest and act as regularization anchors.

5. **KEEP cross-commodity indicators (144 columns)** — ZL price is driven by substitution effects (CPO, canola), upstream (ZS), co-products (ZM), energy (CL, HO for biodiesel), and macro (DX, ES). All 8 technical indicators per symbol might matter when predicting price levels.

6. **KEEP cross-asset correlations (45 columns)** — Rolling correlations capture regime shifts in cross-market relationships that directly inform price trajectory.

---

## Verification Protocol

After each phase, run this verification gate:

1. `python -m fusion.core_training.build_matrix` — rebuild training.matrix_1d
2. `python -c "from fusion.core_training.train_models import run; run(horizons=[5,21,63,126], symbol='ZL')"` — train all 4 horizons
3. Compare per-horizon: MAE, skill, directional accuracy, ensemble weights
4. Log which models entered the WeightedEnsemble and at what weights
5. Store results in `reports/` with timestamp for historical comparison

---

## Priority Summary

| Priority | Phase | Action | Impact |
|----------|-------|--------|--------|
| **P0** | Phase 0 | Run first clean MAE/price training with specialists | DONE — Establishes true baseline |
| **P1** | Phase 1A | Seasonal calendar features + known_covariates | CODE DONE — Training pending |
| **P1** | Phase 1B | Price-level anchors (SMAs, percentiles) | Gives tree models reference points |
| **P1** | Phase 1C | ZL term structure features | Strongest commodity price predictor |
| **P2** | Phase 2A | Indonesia palm data (GAPKI) | Fills 60% supply blind spot |
| **P2** | Phase 2B | Fix options data pipeline | Forward-looking volatility |
| **P2** | Phase 1D | WASDE surprise / export pace features | Supply-demand deltas |
| **P3** | Phase 3A | Test TFT on Mac ARM | Potential game-changer for 63d/126d |
| **P3** | Phase 2C | China import statistics | Direct demand signal |
| **P4** | Phase 4A | Training window optimization | Reduce NaN, improve density |
