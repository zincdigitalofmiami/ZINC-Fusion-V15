# ZINC-FUSION-V15: Canonical Intelligence Stack (L0→L5)

> **Governing Principle**: Lower layers create truth. Upper layers create meaning. No layer may impersonate another.

This is a **decision support system**, not a trading system. All explanations are mathematical. The LLM at L5 is a **translator**, not an oracle.

---

## Layer Summary

| Layer | Name | Schema | Question Answered |
|-------|------|--------|-------------------|
| L0 | Raw Data | `raw` | What happened? |
| L1 | Feature Engineering | `training` | What changed? |
| L2 | Core Baseline | `model` | Where could price go? |
| L3 | Specialist Models | `model` | What does each domain think? |
| L4 | Meta-Ensemble + Attribution | `model` + `analytics` | Why does it look that way? |
| L5 | Monte Carlo + LLM | `model` + `analytics` | How should a human understand it? |

---

## L0 — Raw Data (Truth Layer)

**Schema**: `raw`

**Purpose**: Capture reality exactly as it is, with no interpretation.

### Tables

| Table | Description | Rows | Frequency |
|-------|-------------|------|-----------|
| `market_futures_1h` | Hourly OHLCV, 84 symbols | 4.97M | Hourly |
| `market_futures_1d` | Daily OHLCV | 397K | Daily |
| `fred_economic_wide_1d` | 91 macro indicators | 27K | Daily |
| `weather_noaa` | NOAA weather stations | 215K | Daily |
| `cftc_cot` | COT positioning | 6K | Weekly |
| `usda_export_sales` | Export data | 6K | Weekly |
| `usda_wasde` | Supply/demand estimates | 4K | Monthly |
| `raw_fx_spot` | FX rates | 140K | Daily |
| `raw_options_futures` | Options data | 29K | Daily |
| `news_articles` | Sentiment feeds | 288 | As available |

### Characteristics
- Source-faithful
- Timestamped
- Schema-stable
- No feature engineering
- No smoothing
- No joins across domains

### Rule
**If L0 is wrong, everything above it is wrong.**

---

## L1 — Feature Engineering (What Changed)

**Schema**: `training`

**Purpose**: Make raw data usable by models without adding opinion.

### Tables

| Table | Description | Rows |
|-------|-------------|------|
| `core_features` | Unified feature matrix for Core | 6K |
| `specialist_crush_1h/1d` | Crush spread features | 291K/23K |
| `specialist_china_1h/1d` | China demand features | 330K/27K |
| `specialist_fx_1h/1d` | Currency features | 1.1M/80K |
| `specialist_fed_1h/1d` | Fed/rates features | 669K/48K |
| `specialist_energy_1h/1d` | Energy complex features | 662K/45K |
| `specialist_biofuel_1h/1d` | RIN/biodiesel features | 518K/42K |
| `specialist_palm_1h/1d` | Palm oil features | 241K/24K |
| `specialist_volatility_1h/1d` | Vol regime features | 533K/35K |
| `specialist_substitutes_1h/1d` | Competing oils features | 377K/43K |
| `specialist_tariff_1h/1d` | Trade policy features | 497K/42K |

### Transforms Applied
- Returns, spreads, ratios
- Rolling statistics (mean, std, min, max)
- Lags (1d, 5d, 21d, 63d)
- Calendar features (day of week, month, quarter)
- Weather stress indices
- Forward-fill for mixed frequencies

### Rule
**L1 answers "what changed," not "what it means."**

---

## L2 — Core Baseline Model (Where Price Could Go)

**Schema**: `model`

**Purpose**: Produce the hero forecast and uncertainty geometry.

### Framework
- AutoGluon 1.5 TimeSeriesPredictor
- Chronos-2 (zero-shot + optional LoRA fine-tune)

### Input
- All L0 + L1 data
- 4.97M rows × 84 symbols × 95+ features
- Hourly frequency

### Configuration
```python
TimeSeriesPredictor(
    prediction_length=horizon,  # 5, 21, 63, 126 days
    target="target",
    freq="H",
    quantile_levels=[0.1, 0.5, 0.9],
    eval_metric="MASE",
)

# Quick mode: Chronos-2 only (10 min)
hyperparameters = {"Chronos-2": {"model_path": "autogluon/chronos-2"}}

# Full mode: Full AutoML ensemble (4 hours)
presets = "best_quality"
```

### Output Tables

| Table | Description |
|-------|-------------|
| `oof_predictions` (specialist='core') | Out-of-fold quantiles |
| `forecast_quantiles` | Production forecasts |

### Output Format
- P10 (floor) / P50 (median) / P90 (ceiling)
- Per symbol, per horizon, per timestamp

### Rule
**L2 defines the uncertainty geometry. It does not explain why.**

---

## L3 — Specialist Models (What Each Domain Thinks)

**Schema**: `model`

**Purpose**: Let each domain express its own view of pressure and risk.

### Framework
- AutoGluon 1.5 TabularPredictor
- LASSO (L1) + GBM + CatBoost + XGBoost + Random Forest

### The 11 Specialists

| Bucket | Domain Intelligence | Key Features |
|--------|---------------------|--------------|
| `crush` | Crush spread, meal/oil ratio, processor margins | ZM-ZL spread, capacity utilization |
| `china` | Import demand, stockpiles, policy shifts | Dalian futures, import volumes |
| `fx` | USD strength, EM currencies | DXY, BRL, CNY, trade-weighted |
| `fed` | Rate expectations, yield curve, liquidity | Fed funds, 2Y-10Y spread |
| `tariff` | Trade policy, duties, retaliatory measures | Tariff rates, trade flows |
| `energy` | Crude, diesel, biodiesel blend economics | CL, HO, RB spreads |
| `biofuel` | RINs, mandates, blending requirements | D4 RIN prices, blend rates |
| `palm` | Palm oil production, supply disruptions | Malaysian palm, CPO prices |
| `volatility` | Realized vol, IV, regime detection | GARCH, IV percentile |
| `substitutes` | Canola, sunflower, competing oils | Spread vs alternatives |
| `trump_effect` | Trump/policy regime dynamics, trade war | Policy uncertainty, EPA waivers, trade rhetoric |

### Configuration
```python
TabularPredictor(
    label="target",
    problem_type="regression",
    eval_metric="mean_absolute_error",
    presets="best_quality",
)

hyperparameters = {
    "LR": [  # LASSO for interpretability
        {"penalty": "L1", "C": 0.01},
        {"penalty": "L1", "C": 0.1},
        {"penalty": "L1", "C": 1.0},
    ],
    "GBM": [...],
    "CAT": [...],
    "XGB": [...],
}
```

### Output Tables

| Table | Description |
|-------|-------------|
| `oof_predictions` (specialist=bucket) | Out-of-fold quantiles |
| `lasso_coefficients` | Feature weights for interpretability |

### Rule
**Specialists are allowed to disagree. Each expresses its domain's view.**

---

## L4 — Meta-Ensemble + Attribution (Why It Looks That Way)

**Schema**: `model` + `analytics`

**Purpose**: Reconcile specialists with core forecast and explain attribution.

### Framework
- AutoGluon 1.5 TabularPredictor
- LASSO + LightGBM

### Input Features (15 total)

**Base Features (12)**:
- `core_p50` - Core model median forecast
- `crush_p50`, `china_p50`, `fx_p50`, `fed_p50`, `tariff_p50`
- `energy_p50`, `biofuel_p50`, `palm_p50`, `volatility_p50`, `substitutes_p50`
- `trump_effect_p50` - Trump/policy regime dynamics forecast

**Dissent Features (3)**:
```python
specialist_std = specialists.std(axis=1)           # Agreement measure
specialist_range = specialists.max() - specialists.min()  # Spread of views
core_vs_mean = core_p50 - specialists.mean()       # Core divergence from consensus
```

### Output Tables

| Table | Schema | Description |
|-------|--------|-------------|
| `meta_ensemble` | model | Calibrated P10/P50/P90 |
| `meta_weights` | model | Source contribution weights |
| `driver_scores` | analytics | Which specialist drove the move |
| `shap_summary` | model | Feature importance rankings |
| `shap_values` | model | Per-observation SHAP values |
| `market_posture` | analytics | Overall market stance |
| `regime_probabilities` | analytics | Regime detection |

### Dissent Index Calculation
```python
dissent_index = specialist_std / (abs(core_p50) + 1e-6)
# 0 = perfect consensus
# >0.5 = high disagreement
```

### Rule
**L4 explains posture with math. It never prescribes action.**

---

## L5 — Monte Carlo + LLM Synthesis (Human Understanding)

**Schema**: `model` + `analytics`

**Purpose**: Translate probability geometry into intuition without altering math.

### L5-A: Monte Carlo Engine (Quantification)

#### Input
- L4-reconciled P10 / P50 / P90
- Volatility regime from L3
- Cross-asset correlation matrix
- Horizon-specific geometry

#### Process
```python
def simulate_paths(p10, p50, p90, horizon, vol_regime, n_sims=10000):
    """
    Asymmetric diffusion respecting quantile geometry.
    """
    # Extract implied volatility from quantile spread
    sigma_up = (p90 - p50) / 1.28    # Upper tail vol
    sigma_down = (p50 - p10) / 1.28  # Lower tail vol

    # Regime adjustment
    vol_multiplier = {'high': 1.5, 'normal': 1.0, 'low': 0.7}[vol_regime]

    paths = []
    for _ in range(n_sims):
        price = p50  # Start at median
        path = [price]

        for t in range(horizon):
            shock = np.random.normal()
            if shock > 0:
                price += shock * sigma_up * vol_multiplier * np.sqrt(1/252)
            else:
                price += shock * sigma_down * vol_multiplier * np.sqrt(1/252)
            path.append(price)

        paths.append(path)

    return np.array(paths)
```

#### Correlation Structure
```python
# Correlated shocks using Cholesky decomposition
correlation_groups = {
    'oilseeds': ['ZL', 'ZM', 'ZS', 'BO'],
    'energy': ['CL', 'HO', 'RB'],
    'grains': ['ZC', 'ZW'],
}

L = np.linalg.cholesky(correlation_matrix)
correlated_shocks = L @ np.random.normal(size=(n_assets, n_steps))
```

#### Output Tables

| Table | Description |
|-------|-------------|
| `monte_carlo_runs` | Simulated paths + percentiles |
| `probability_distributions` | Full PDFs at each horizon |
| `risk_metrics` | VaR, CVaR, tail risk flags |

#### Rule
**Monte Carlo quantifies the space of plausible futures.**

---

### L5-B: Visual Intelligence Package (Rendering Primitives)

These are **rendering primitives**, not new models. All live in the Hero chart's future space.

| Visual | Description | When Used |
|--------|-------------|-----------|
| **Forecast Cone** | P10/P50/P90 bands | Default view |
| **Pinball Paths** | 50-200 faint MC trajectories | Risk intuition |
| **Terminal Dots** | End-state probability distribution | Decision focus |
| **Density Cloud** | Heatmap of path density | Long horizons |
| **Regime Bands** | Background zones (high/normal/low vol) | Context |

#### Rule
**Geometry communicates risk. Density communicates confidence.**

---

### L5-C: LLM Synthesis (Explanation Only)

#### Input to LLM
```python
llm_input = {
    # Forecast geometry
    "p10": forecast.p10,
    "p50": forecast.p50,
    "p90": forecast.p90,
    "horizon_days": horizon,

    # Monte Carlo summary
    "mc_p5": mc_percentiles[5],
    "mc_p95": mc_percentiles[95],
    "prob_up_5pct": prob_up_5pct,
    "prob_down_5pct": prob_down_5pct,

    # Attribution (from SHAP)
    "top_drivers": [
        {"name": "crush_p50", "impact": +0.023},
        {"name": "china_p50", "impact": -0.018},
        {"name": "energy_p50", "impact": +0.012},
    ],

    # Specialist agreement
    "dissent_index": 0.34,
    "most_bullish": "energy",
    "most_bearish": "china",

    # Regime
    "regime": "normal",
    "regime_confidence": 0.78,

    # Historical analogs
    "analogs": [
        {"period": "Jun 2018", "similarity": 0.82, "outcome": "+4.2%"},
        {"period": "Mar 2021", "similarity": 0.76, "outcome": "+8.1%"},
    ],
}
```

#### LLM Prompt Template
```
You are a commodity intelligence analyst. Summarize the following data.
DO NOT invent information. Only reference the provided data.

## Forecast Data
- P10 (floor): {p10:.2f}
- P50 (median): {p50:.2f}
- P90 (ceiling): {p90:.2f}
- Horizon: {horizon_days} days

## Monte Carlo Summary
- 5th percentile outcome: {mc_p5:.2f}
- 95th percentile outcome: {mc_p95:.2f}
- Probability of >5% move up: {prob_up_5pct:.1%}
- Probability of >5% move down: {prob_down_5pct:.1%}

## Top Drivers (from SHAP)
1. {driver_1_name}: {driver_1_impact:+.4f}
2. {driver_2_name}: {driver_2_impact:+.4f}
3. {driver_3_name}: {driver_3_impact:+.4f}

## Specialist Agreement
- Dissent index: {dissent_index:.2f} (0=consensus, 1=high disagreement)
- Most bullish specialist: {most_bullish}
- Most bearish specialist: {most_bearish}

## Current Regime
- Regime: {regime}
- Confidence: {regime_confidence:.0%}

## Historical Analogs
{analogs_formatted}

---

Provide:
1. A 3-sentence summary of the current market posture
2. Top 2 risks (with probability context)
3. Top 2 opportunities (with probability context)
4. What would have to change to invalidate this view
```

#### Output
- Natural language posture summary
- Key uncertainties in plain English
- "What would have to change" scenarios
- Confidence-weighted narrative

#### Rule
**LLM explains the math. It never invents math.**

---

### L5-D: Historical Analogs (Similarity Scoring)

#### Similarity Calculation
```python
def find_analogs(current_state, historical_states, top_n=5):
    """
    Find historical periods with similar characteristics.
    """
    scores = []

    for hist in historical_states:
        # Similarity components
        p50_sim = 1 - abs(current_state.p50 - hist.p50) / abs(current_state.p50)
        spread_sim = 1 - abs(current_state.spread - hist.spread) / current_state.spread
        regime_match = 1.0 if current_state.regime == hist.regime else 0.0
        driver_corr = spearman_correlation(current_state.driver_ranks, hist.driver_ranks)

        # Weighted score
        score = (
            0.30 * p50_sim +
            0.25 * spread_sim +
            0.25 * regime_match +
            0.20 * driver_corr
        )

        scores.append({
            "period": hist.period,
            "similarity": score,
            "actual_outcome": hist.forward_return,
        })

    return sorted(scores, key=lambda x: x["similarity"], reverse=True)[:top_n]
```

#### Output Table

| Table | Description |
|-------|-------------|
| `historical_analogs` | Similar periods with outcomes |

---

## Data Flow Diagram

```
                            L0: raw.*
                                │
                                ▼
                        L1: training.*
                      (feature engineering)
                                │
            ┌───────────────────┴───────────────────┐
            ▼                                       ▼
    L2: Core (Chronos-2)                  L3: Specialists ×10
    TimeSeriesPredictor                   TabularPredictor
    P10/P50/P90 geometry                  P10/P50/P90 + LASSO
            │                                       │
            └───────────────┬───────────────────────┘
                            ▼
                L4: Meta-Ensemble + Attribution
                ├── Reconciled P10/P50/P90
                ├── SHAP driver scores
                ├── Dissent index
                └── Regime classification
                            │
            ┌───────────────┼───────────────┐
            ▼               ▼               ▼
        L5-A:           L5-B:           L5-C:
    Monte Carlo        Visuals       LLM Synthesis
    10K simulations    Rendering     Plain English
    Risk metrics       primitives    explanation
            │               │               │
            └───────────────┴───────────────┘
                            │
                            ▼
                Dashboard / API / Decision Support
```

---

## Implementation Files

| Layer | Script | Status |
|-------|--------|--------|
| L0 | `scripts/ingest_*.py` | ✅ Complete |
| L1 | `scripts/build_features.py` | ✅ Complete |
| L2 | `scripts/train_core_chronos.py` | ✅ Complete |
| L3 | `scripts/train_specialist.py` | ✅ Complete |
| L4 | `scripts/train_meta_ensemble.py` | ✅ Complete (with dissent features) |
| L5-A | `scripts/run_monte_carlo.py` | ✅ Complete (asymmetric vol + regime) |
| L5-C | `scripts/generate_synthesis.py` | ✅ Complete (structured LLM prompts) |
| L5-D | `scripts/find_analogs.py` | ✅ Complete (similarity scoring) |

---

## Database Schema Additions Needed

```sql
-- L5-A: Monte Carlo
CREATE TABLE "model"."monte_carlo_paths" (
    id SERIAL PRIMARY KEY,
    as_of_date DATE NOT NULL,
    horizon INTEGER NOT NULL,
    symbol VARCHAR(20) DEFAULT 'ZL',
    path_id INTEGER NOT NULL,
    percentiles JSONB NOT NULL,  -- {5: x, 25: x, 50: x, 75: x, 95: x}
    created_at TIMESTAMP DEFAULT NOW()
);

-- L5-C: LLM Synthesis
CREATE TABLE "analytics"."llm_synthesis" (
    id SERIAL PRIMARY KEY,
    as_of_date DATE NOT NULL,
    horizon INTEGER NOT NULL,
    input_data JSONB NOT NULL,
    summary TEXT NOT NULL,
    risks JSONB NOT NULL,
    opportunities JSONB NOT NULL,
    invalidation_triggers JSONB,
    model_used VARCHAR(50),
    created_at TIMESTAMP DEFAULT NOW()
);

-- L5-D: Historical Analogs
CREATE TABLE "analytics"."historical_analogs" (
    id SERIAL PRIMARY KEY,
    as_of_date DATE NOT NULL,
    horizon INTEGER NOT NULL,
    analog_period VARCHAR(50) NOT NULL,
    similarity_score NUMERIC(5,4) NOT NULL,
    actual_outcome NUMERIC(8,4),
    components JSONB,  -- {p50_sim, spread_sim, regime_match, driver_corr}
    created_at TIMESTAMP DEFAULT NOW()
);
```

---

## Governing Principles

1. **Lower layers create truth. Upper layers create meaning.**
2. **No layer may impersonate another.**
3. **L2 and L3 are allowed to disagree.** L4 reconciles, not suppresses.
4. **All explanations must be mathematical.** LLM summarizes math, doesn't invent it.
5. **This is decision support, not trading.** No buy/sell signals, only intelligence.
6. **Monte Carlo quantifies uncertainty.** No sliders, no user control.
7. **Visuals are rendering primitives.** They reveal geometry, not create it.

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2025-12-30 | Initial L0→L5 architecture |
