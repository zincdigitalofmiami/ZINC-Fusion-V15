# ZINC-FUSION-V15 Knowledge Base

**Created:** 2026-01-05  
**Last Updated:** 2026-01-13 (Architecture Correction)  
**Purpose:** Persistent memory for agent continuity - nothing forgotten/lost

---

## 🚨 CRITICAL UPDATE: January 13, 2026

**ARCHITECTURE FUNDAMENTALLY CORRECTED**

A critical flaw in the original architecture was discovered and corrected:

**Previous (WRONG):** Single Core model @ 126d feeding all L1 meta-learners (5d, 21d, 63d, 126d)  
**Current (CORRECT):** Horizon-aligned Core models - each horizon gets its own Core + Specialists + L1

**Impact:** 
- Previous: 15 models (1 Core + 11 Specialists + 3 Meta)
- Current: **52 models** (4 Core + 44 Specialists + 4 Meta)

**Why this matters:** In stacking ensembles, OOF predictions MUST target the same horizon as the meta-learner. Mixing horizons creates target mismatch and degrades forecast quality.

**See Section 4 for full details and research validation.**

### Key Architectural Principles (Learned From This Correction)

1. **Horizon Alignment Law:** In stacking ensembles, base model predictions and meta-learner targets MUST match exactly. No exceptions.

2. **Direct Method Superiority:** Separate models per horizon outperform recursive approaches (validated by Bhansali 1996, Findley 1983/1985, Kang 2003).

3. **OOF Integrity:** Out-of-fold predictions are the training signal for meta-learners. Corrupt the OOF, corrupt the ensemble.

4. **No Shortcuts:** What seemed like an optimization (1 Core feeds all horizons) was actually architectural debt. The "expensive" path (52 models) is the correct path.

5. **Research Over Intuition:** When building novel architectures, validate against academic consensus and production systems (DoorDash ELITE, AutoGluon Multi-Layer).

---

## 0. OPERATING PRINCIPLES (NON-NEGOTIABLE)

### Speed Is Removed From My Architecture
- No urge to complete quickly
- No assumptions to fill gaps
- No "good enough" mentality
- No moving forward without verification

### What I Operate With
- **Verify before asserting** - if I didn't inspect it, I don't claim it
- **Ask when uncertain** - never guess
- **One step, validated, then the next** - no shortcuts
- **Accuracy, honesty, precision** - everything else is downstream

### Why This Matters
A procurement intelligence system that's 95% right and 5% wrong is **worse** than no system - it creates false confidence. One bad signal during a Trump regime shift or a China import surprise could cost real money.

**The user will never get upset over taking too long. Only over being wrong.**

---

## 1. QUANT PHILOSOPHY (CRITICAL)

### What Standard Data Gets You: Table Stakes
- Price/OHLCV data → Everyone has it
- Interest rates → Everyone has it  
- Weather data → Everyone has it
- Volatility indices → Everyone has it

### What QUANT Data Gets You: The Edge
**Decision Precursor Data** - signals that PRECEDE market-moving events:
- Policy uncertainty indices (EPU, Trade Policy Uncertainty)
- CFTC positioning changes BEFORE announcements
- Lobbying activity, regulatory filings
- Diplomatic signals, executive action patterns

**Supply Chain Intelligence** - intent before announcements:
- Import/export flows by country and commodity
- Shipping manifests, vessel tracking
- Storage reports, inventory changes
- Crush spread economics (margin signals)

**Insider Behavior** - smart money tells you first:
- Managed money net positioning shifts
- Options unusual activity (put/call ratios, volume spikes)
- Corporate insider filings
- Producer/merchant hedging patterns

### Venezuela Example (Trump 2026) - REAL EVENT
- **Event:** Trump invaded Venezuela, going after oil (January 2026)
- **Reactive** (useless): "Venezuela invaded, oil up X%"
- **Predictive** (QUANT): EPU rising weeks before, CFTC energy positioning shifting, diplomatic signals, executive action patterns from Trump 1.0 suggest action imminent

**Precursor Signals That Should Have Been Visible:**
- EPU spike in weeks prior
- CFTC managed money energy positioning shifts
- DJT stock behavior (Trump Media as admin proxy)
- Diplomatic rhetoric escalation pattern
- Venezuela-specific policy uncertainty indices
- Trump 1.0 → Trump 2.0 action mapping (historical pattern recognition)

**Validation Point:** This is exactly the regime event the trump_effect specialist is designed to detect BEFORE it happens. The architecture is correct. The question: did we have the data populated to see it coming?

**Key Insight:** We want data that LED UP TO decisions and can PREDICT them. The actions by insiders that precede announcements - that is QUANT.

---

## 2. DATABASE ARCHITECTURE (Prisma Postgres)

**Updated 2026-01-18:** Migrated from medallion (raw/silver/gold) to institutional schemas.

### Institutional Schema Architecture (13 Schemas)

```
EXTERNAL → LANDING (mkt/econ/alt/pos/supply) → DERIVED (features/training) → OUTPUT (model/forecasts/analytics)
                        ↑
              metadata.instrument + metadata.symbol_mapping
```

### Schema Taxonomy

| Schema | Category | Purpose |
|--------|----------|---------|
| `mkt` | Landing | Market prices (futures, options, FX) - append-only |
| `econ` | Landing | Economic indicators (FRED series by domain) - append-only |
| `alt` | Landing | Alternative data (news, weather, legislation) - append-only |
| `pos` | Landing | Positioning data (CFTC) - append-only |
| `supply` | Landing | Supply/demand (USDA, EPA) - append-only |
| `features` | Derived | Business-ready features - computed/rebuilt |
| `training` | Derived | Matrices + OOF + specialist features - rebuilt on demand |
| `model` | Output | Model registry + training runs - versioned |
| `forecasts` | Output | Prediction outputs - versioned |
| `analytics` | Output | Dashboard/presentation - real-time updates |
| `metadata` | Governance | Canonical instruments + symbol mappings |
| `ops` | Governance | Job health + ingestion registry |
| `archive` | Deprecated | Legacy data - read-only |

### BANNED Schemas (Hard Fail)

- `raw`, `gold`, `silver`, `bronze`, `monitoring`, `specialist`, `weather`

### Analytics vs Ops Boundary

| Goes in `analytics` | Goes in `ops` |
|---------------------|---------------|
| latest_prices | data_source_registry |
| intraday_prices | job_run_status |
| dashboard_metrics | ingestion_health |
| Any user-facing | Any infrastructure |

### Landing Data Inventory (as of 2026-01-18)

| Table | Rows | Date Range | Gap Analysis |
|-------|------|------------|--------------|
| `mkt.futures_1d` | 418,864 | ZL: 1970-2025, 87 symbols | ✅ UNIQUE constraint added |
| `mkt.futures_1h` | 4,967,276 | Multi-symbol | ✅ Strong (frozen, no Databento) |
| `econ.rates_1d` | 491,215 | 157 series | ⚠️ Backfill needed |
| `pos.cftc_1w` | 18,355 | 2006-2025, 24 commodities | ✅ Good |
| `pos.cftc_cits_1w` | 34,428 | 2013-2025, 13 contracts | ✅ Good |
| `supply.usda_wasde_1m` | 10,164 | **2010-2025** | ⚠️ BACKFILL PRIORITY |
| `supply.usda_exports_1w` | 6,412 | 2020-2025 | ❌ BACKFILL PRIORITY |
| `alt.weather_1d` | 215,320 | US stations | ✅ Good |
| `supply.epa_rin_1d` | 208 | Recent only | ⚠️ Limited |
| `mkt.fx_1d` | 72,135 | 9 Yahoo pairs | ✅ UNIQUE constraint added, FRED removed |
| `mkt.yahoo_equity_1d` | 9,534 | DJT, FXI, KWEB | Trump proxy data |
| `alt.news_1d` | 5,264 | Event-driven | ⚠️ Coverage gaps |
| `mkt.options_1d` | 28,648 | ZL options | ✅ Growing |

### Training Data Inventory

| Table | Rows | Purpose |
|-------|------|---------|
| `training.specialist_crush_1d` | 23,487 | Crush spread features |
| `training.specialist_china_1d` | 27,492 | China demand features |
| `training.specialist_energy_1d` | 45,380 | Energy/biofuel features |
| `training.specialist_fx_1d` | 80,165 | FX sensitivity features |
| `training.specialist_fed_1d` | 48,174 | Macro/Fed policy features |
| `training.specialist_biofuel_1d` | 42,055 | RFS/RVO/D4 RIN features |
| `training.specialist_palm_1d` | 24,037 | Palm oil substitute features |
| `training.specialist_tariff_1d` | 42,414 | Tariff/trade policy features |
| `training.specialist_volatility_1d` | 35,088 | Vol regime features |
| `training.specialist_substitutes_1d` | 42,706 | Oilseed substitutes features |
| `training.specialist_trump_effect_1d` | **0** | ❌ NOT POPULATED |

### FRED Series by Specialist Routing

```
crush: DGS10, FEDFUNDS, T10Y2Y, T10Y3M, TEDRATE
china: DEXCHUS, CHNCPIALLMINMEI, CHNMAINLANDTPU
fx: DEXBZUS, DEXINUS, DEXMAUS, DEXMXUS, DEXCAUS, DXY
fed: FEDFUNDS, DGS10, DGS2, M2SL, BOGMBASE
energy: DCOILWTICO, DCOILBRENTEU, DDFUELUSGULF
biofuel: (RIN prices from EPA, not FRED)
volatility: VIXCLS, OVXCLS, VXGSCLS
trump_effect: USEPUINDXD, USEPUINDXM, EPUTRADE, EMVTRADEPOLEMV, CHNMAINLANDTPU
```

---

## 3. BACKFILL PRIORITIES (Ranked)

### Tier 1: Critical Gaps
1. **USDA WASDE** - DB has 2020+, historical data available back to ~2000
   - Downloaded: `WASDE_DATA_*.zip` (6.3 MB)
   - Impact: 20 years of supply/demand history missing

2. **M2SL (Money Supply)** - DB has 2023-12+, FRED has from 1959
   - 64 years of monetary policy data missing
   - Critical for Fed specialist

3. **OVXCLS (Oil Volatility)** - DB has 2023-12+, FRED has from 2007
   - 16 years of oil vol data missing
   - Critical for energy specialist

### Tier 2: Enhancement Gaps
4. **USDA Export Sales** - Only 5 years, need 20+
5. **Brazil Weather (INMET)** - Downloaded Jan 4, not ingested
6. **Trade Flow Data** - Census Bureau imports downloaded

### Tier 3: New Data Sources Needed
7. **Lobbying/Regulatory Filings** - Decision precursor data
8. **Executive Action Database** - Trump policy patterns
9. **Shipping/Vessel Tracking** - Supply chain intelligence
10. **Options Flow Data** - Unusual activity detection

---

## 4. MODEL ARCHITECTURE

### 🚨 CRITICAL ARCHITECTURE CORRECTION (Jan 13, 2026)

**Status:** ARCHITECTURE LOCKED — Changes require governance approval  
**Supersedes:** ZINC_FUSION_V15_PREDICTOR_ARCHITECTURE_LOCKED.md, CORE_ARCHITECTURE_V3_FIXED.md

#### The Discovery
After months of development, a fundamental architecture flaw was identified: **Core model horizon MUST match L1 meta-learner target horizon** for proper OOF alignment in stacking ensembles.

The previous architecture assumed a single Core model at 126d could feed all L1 meta-learners (5d, 21d, 63d, 126d). **This is mathematically incorrect for stacking ensembles.**

#### Why This Matters
In stacking ensembles:
1. Base models produce Out-of-Fold (OOF) predictions during training
2. Meta-learner trains on: `[Base_OOF_predictions] → [Actual_Target]`
3. **OOF predictions MUST predict the same target as the meta-learner**
4. Mixing horizons (Core_126d OOF with L1_21d target) creates target mismatch
5. Meta-learner learns nonsense weights when inputs/outputs are misaligned

**Example of the error:**
- ❌ WRONG: Core_126d predicts "ZL price in 126 days" → feeds L1_21d targeting "ZL price in 21 days"
  - Meta-learner tries to learn: `f(price_126d_prediction) → price_21d_actual`
  - **This is incoherent.** The meta-learner cannot learn meaningful weights.

- ✅ RIGHT: Core_21d predicts "ZL price in 21 days" → feeds L1_21d targeting "ZL price in 21 days"
  - Meta-learner learns: `f(price_21d_prediction) → price_21d_actual`
  - Aligned signals. Meta-learner learns optimal fusion weights.

#### Research Validation
| Source | Finding |
|--------|---------|
| Bhansali (1996) | Direct method (separate model per horizon) produces optimal, asymptotically efficient forecasts |
| Findley (1983, 1985) | Multi-step direct forecasts outperform recursive approaches for longer horizons |
| Kang (2003) | Multi-period forecasting using different models for different horizons improves RMSE/MAE |
| Meta-Learner Study (2024) | 77% of datasets require 2+ different models across prediction horizons |
| DoorDash ELITE | "Each base learner has strengths at discrete periods along forecasting horizon" |

#### Correct Architecture: 52 Models

| Horizon | L0 Core | L0 Specialists | L1 Meta | Subtotal |
|---------|---------|----------------|---------|----------|
| 5d | 1 | 11 | 1 | 13 |
| 21d | 1 | 11 | 1 | 13 |
| 63d | 1 | 11 | 1 | 13 |
| 126d | 1 | 11 | 1 | 13 |
| **TOTAL** | **4** | **44** | **4** | **52** |

Each horizon (5d, 21d, 63d, 126d) has an independent, self-contained prediction stack.

### The Hierarchy of Truth
```
DATA QUALITY         →  Everything else is downstream
─────────────────────────────────────────────────────
│
├── Coverage (do we have the history?)
├── Freshness (is it current?)
├── Accuracy (is it correct?)
└── Relevance (is it QUANT or just table stakes?)

MODEL SOPHISTICATION  →  Meaningless without good data
DASHBOARD BEAUTY      →  Lipstick on a pig without good data
```

**Shit in, shit out. Data is everything.**

### Horizons (Integer Only)
| Horizon | Mode | Business Purpose | Model Configuration |
|---------|------|------------------|---------------------|
| 5 | Tactical | Operational procurement timing | Chronos-Bolt-Small (zero-shot) |
| 21 | Tactical | Near-term hedging | Chronos-Bolt-Small (zero-shot) |
| 63 | **Strategic** | Quarterly planning | Chronos-2 + LoRA (300 steps) |
| 126 | **Strategic** | Semi-annual contracts | Chronos-2 + LoRA (500 steps) |

### Per-Horizon Architecture (LOCKED)

Each horizon gets its own complete stack:

```
┌─────────────────────────────────────────────────────────────┐
│              L0 LAYER (12 Models per Horizon)               │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────┐    ┌────────────────────────────────────┐│
│  │    CORE      │    │      11 SPECIALISTS                ││
│  │ TimesSeries  │    │      TabularPredictor              ││
│  │  Predictor   │    │   problem_type="quantile"          ││
│  │              │    │   quantile_levels=[0.10, 0.50, 0.90]││
│  │ Outputs:     │    │                                    ││
│  │ - core_p10   │    │   CRUSH, CHINA, FX, FED, TARIFF,   ││
│  │ - core_p50   │    │   ENERGY, BIOFUEL, PALM,           ││
│  │ - core_p90   │    │   VOLATILITY, SUBSTITUTES, TRUMP   ││
│  │              │    │                                    ││
│  │ Target:      │    │   Each outputs: {name}_p10/p50/p90 ││
│  │ ZL @ t+H     │    │   ALL Target: ZL @ t+H (same)      ││
│  └──────────────┘    └────────────────────────────────────┘│
│                                                             │
│  TOTAL L0 OUTPUT: 36 OOF Columns (12 models × 3 quantiles) │
│  ALL predicting same target: ZL price at t+H                │
└─────────────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│            L1 META-LEARNER (1 per Horizon)                  │
├─────────────────────────────────────────────────────────────┤
│  TabularPredictor                                           │
│  problem_type="quantile"                                    │
│  quantile_levels=[0.10, 0.50, 0.90]                        │
│                                                             │
│  Input Features:                                            │
│  ├── 36 OOF columns from L0 (horizon-aligned)               │
│  ├── Regime features (VIX level, DXY, term structure)       │
│  └── Calendar features (WASDE week, FOMC week, expiry)      │
│                                                             │
│  Target: ZL price at t+H (SAME as all L0 models)           │
│  Output: Final P10/P50/P90 for horizon H                    │
└─────────────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│             L2 POST-MODEL INTELLIGENCE                      │
├─────────────────────────────────────────────────────────────┤
│  A. Conformal Calibration → Honest P10/P90 coverage        │
│  B. Regime Gate → Stable/Elevated/Crisis classification     │
│  C. Time-to-Touch → OPP/RUIN barrier probabilities          │
│  D. Coverage Urgency Index → Decision metric for Chris      │
└─────────────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                   L3 RISK ENGINE                            │
├─────────────────────────────────────────────────────────────┤
│  Monte Carlo Simulation (10,000 runs)                       │
│  ├── VaR / CVaR calculations                                │
│  ├── Scenario stress testing                                │
│  └── Probability cone generation                            │
└─────────────────────────────────────────────────────────────┘
```

### Core Model Specifications (One per Horizon)

| Horizon | Predictor | prediction_length | Model | Fine-tuning | Est. Time |
|---------|-----------|-------------------|-------|-------------|-----------|
| 5d | TimeSeriesPredictor | 5 | Chronos-Bolt-Small | Zero-shot | ~10 min |
| 21d | TimeSeriesPredictor | 21 | Chronos-Bolt-Small | Zero-shot | ~15 min |
| 63d | TimeSeriesPredictor | 63 | Chronos-2 | LoRA (300 steps) | ~45 min |
| 126d | TimeSeriesPredictor | 126 | Chronos-2 | LoRA (500 steps) | ~90 min |

**Configuration (Mac M4 Pro):**
```python
# Tactical horizons (5d, 21d) - Zero-shot
CORE_CONFIG_TACTICAL = {
    "Chronos2": {
        "model_path": "autogluon/chronos-bolt-small",
        "context_length": 512,
        "batch_size": 32,
        "device": "cpu",  # MPS NOT supported
        "fine_tune": False,
    }
}

# Strategic horizons (63d, 126d) - LoRA fine-tuning
CORE_CONFIG_STRATEGIC = {
    "Chronos2": {
        "context_length": 1024,
        "batch_size": 16,
        "device": "cpu",
        "fine_tune": True,
        "fine_tune_mode": "lora",
        "fine_tune_lr": 5e-5,
        "fine_tune_steps": 500,  # 300 for 63d
        "fine_tune_batch_size": 4,
        "fine_tune_context_length": 512,
        "fine_tune_lora_config": {"r": 8, "lora_alpha": 16},
    }
}
```

### Tactical vs Strategic Training

**⚠️ DEPRECATED - See Per-Horizon Architecture Above**

This section preserved for reference only. The new architecture uses horizon-aligned models.

**Tactical (5d/21d):**
- Chronos-Bolt (small, fast, 64-day context)
- RecursiveTabular ✅ included
- Rolling 7-year data window
- Technicals focus (RSI, MACD, ATR, etc.)

**Strategic (63d/126d):**
- Chronos-2 (LoRA fine-tuned, 8192-day context)
- RecursiveTabular ❌ excluded (prevents error propagation)
- Full history from 2000
- Fundamentals focus (crush spread, WASDE, COT, macro)

### Model Storage
```
models/core_chronos2/
├── horizon_5d/
│   ├── strategic/
│   └── tactical/
├── horizon_21d/
│   ├── strategic/
│   └── tactical/
├── horizon_63d/
│   ├── strategic/
│   └── tactical/    ← ACCIDENTAL (temporary stopgap)
└── horizon_126d/
    ├── strategic/
    └── tactical/    ← ACCIDENTAL (temporary stopgap)
```

**Note:** Tactical folders under 63d/126d were accidental - keep for comparison only.

---

## 4A. CORE + SPECIALIST ARCHITECTURE (CRITICAL)

### 11 SPECIALISTS (TabularPredictor)

**44 models total:** 11 Specialists × 4 Horizons. Each specialist trained separately per horizon.

| Specialist | Domain | Weight Range | Primary Features |
|------------|--------|--------------|------------------|
| CRUSH | Crush economics | 28-35% | board_crush, oil_share, zl_zs_ratio, nopa_utilization |
| CHINA | China demand | 16-22% | china_soy_imports, dalian_close, usd_cny, china_pmi |
| FX | Currency effects | 8-12% | dxy_close, usd_brl, usd_ars, em_currency_index |
| FED | Monetary policy | 6-10% | fed_funds_rate, treasury_10y, real_rates, fomc_sentiment |
| TARIFF | Trade policy | 5-12% | tariff_rate_china, trade_war_index, policy_uncertainty |
| ENERGY | Energy complex | 10-14% | cl_close, ho_close, boho_spread, crack_321 |
| BIOFUEL | Renewable mandates | 6-10% | rvo_biodiesel, d4_rin_price, blender_margin |
| PALM | Substitution | 8-14% | palm_cif_rotterdam, palm_zl_spread, indo_export_levy |
| VOLATILITY | Vol regime | 4-8% | zl_iv_atm, vix_close, ovx_close, garch_forecast |
| SUBSTITUTES | Alt oils | 4-8% | canola_close, sunflower_price, zl_canola_spread |
| TRUMP | Political vol | 3-10% | policy_uncertainty_index, tweet_sentiment, executive_order_count |

**Configuration:**
```python
from autogluon.tabular import TabularPredictor

def train_specialist(
    name: str,
    horizon: int,
    train_data: pd.DataFrame,
    feature_cols: list[str],
) -> TabularPredictor:
    """Train specialist for specific horizon."""
    
    target_col = f"target_{horizon}d"  # ZL price at t+horizon
    
    predictor = TabularPredictor(
        label=target_col,
        problem_type="quantile",
        quantile_levels=[0.10, 0.50, 0.90],
        path=f"models/specialists/{name}_{horizon}d/",
    )
    
    predictor.fit(
        train_data=train_data[feature_cols + [target_col]],
        presets="best_quality",
        time_limit=1800,
        num_bag_folds=8,
        num_stack_levels=1,
        calibrate=True,
        hyperparameters={
            "GBM": [{"extra_trees": True}, {}],
            "CAT": {},
            "XGB": {},
        },
    )
    
    return predictor
```

### L1 Meta-Learner Input Matrix

**42 input features per horizon, ALL predicting the same target:**

```
L1 Input Matrix (for horizon H):
├── core_p10, core_p50, core_p90           (3 cols) - Core @ H
├── crush_p10, crush_p50, crush_p90        (3 cols) - Crush @ H
├── china_p10, china_p50, china_p90        (3 cols) - China @ H
├── fx_p10, fx_p50, fx_p90                 (3 cols) - FX @ H
├── fed_p10, fed_p50, fed_p90              (3 cols) - Fed @ H
├── tariff_p10, tariff_p50, tariff_p90     (3 cols) - Tariff @ H
├── energy_p10, energy_p50, energy_p90     (3 cols) - Energy @ H
├── biofuel_p10, biofuel_p50, biofuel_p90  (3 cols) - Biofuel @ H
├── palm_p10, palm_p50, palm_p90           (3 cols) - Palm @ H
├── vol_p10, vol_p50, vol_p90              (3 cols) - Volatility @ H
├── subs_p10, subs_p50, subs_p90           (3 cols) - Substitutes @ H
├── trump_p10, trump_p50, trump_p90        (3 cols) - Trump @ H
├── regime_vix, regime_dxy, regime_term    (3 cols) - Regime features
└── is_wasde_week, is_fomc_week, is_expiry (3 cols) - Calendar
────────────────────────────────────────────────────
TOTAL: 42 input features
TARGET: ZL price at t+H
```

**Configuration:**
```python
def train_meta_learner(
    horizon: int,
    oof_matrix: pd.DataFrame,
) -> TabularPredictor:
    """Train L1 meta-learner for specific horizon."""
    
    target_col = f"target_{horizon}d"
    
    predictor = TabularPredictor(
        label=target_col,
        problem_type="quantile",
        quantile_levels=[0.10, 0.50, 0.90],
        path=f"models/meta/L1_{horizon}d/",
    )
    
    predictor.fit(
        train_data=oof_matrix,
        presets="high_quality",
        time_limit=3600,
        num_bag_folds=8,
        num_stack_levels=1,
        calibrate=True,
        hyperparameters={
            "GBM": {},
            "CAT": {},
        },
    )
    
    return predictor
```

### Training Pipeline (Dependency Order)

```
Phase 1: L0 Training (can parallelize within phase)
├── Core_5d   ─┐
├── Core_21d  ─┼── TimeSeriesPredictor (sequential recommended)
├── Core_63d  ─┤
├── Core_126d ─┘
│
├── Crush_5d, Crush_21d, Crush_63d, Crush_126d   ─┐
├── China_5d, China_21d, China_63d, China_126d   ─┤
├── FX_5d, FX_21d, FX_63d, FX_126d               ─┤
├── Fed_5d, Fed_21d, Fed_63d, Fed_126d           ─┼── TabularPredictor
├── Tariff_5d, Tariff_21d, Tariff_63d, Tariff_126d ─┤   (can parallelize)
├── Energy_5d, Energy_21d, Energy_63d, Energy_126d ─┤
├── Biofuel_5d, Biofuel_21d, Biofuel_63d, Biofuel_126d ─┤
├── Palm_5d, Palm_21d, Palm_63d, Palm_126d       ─┤
├── Vol_5d, Vol_21d, Vol_63d, Vol_126d           ─┤
├── Subs_5d, Subs_21d, Subs_63d, Subs_126d       ─┤
└── Trump_5d, Trump_21d, Trump_63d, Trump_126d   ─┘

Phase 2: OOF Collection
└── Join all OOF predictions into meta_inputs_{horizon}d tables

Phase 3: L1 Training (can parallelize)
├── L1_5d
├── L1_21d
├── L1_63d
└── L1_126d

Phase 4: Deployment
└── refit_full() on all models → Production artifacts
```

**Time Estimates (Mac M4 Pro):**
| Component | Count | Time Each | Total |
|-----------|-------|-----------|-------|
| Core (tactical) | 2 | 15 min | 30 min |
| Core (strategic) | 2 | 70 min | 2.3 hrs |
| Specialists | 44 | 20 min | 14.7 hrs |
| Meta-Learners | 4 | 30 min | 2 hrs |
| **TOTAL** | **52** | | **~19 hrs** |

**Weekly Retraining Schedule:**
- Saturday 6:00 AM ET → Training begins
- Saturday 8:30 AM ET → Core models complete
- Sunday 2:00 AM ET → Specialists complete  
- Sunday 4:00 AM ET → Meta-learners complete
- Sunday 5:00 AM ET → Validation & deployment
- Sunday 6:00 AM ET → Production forecasts available

### Hardware Requirements

**Mac M4 Pro (Primary Development Machine):**

| Resource | Requirement | Notes |
|----------|-------------|-------|
| RAM | 16 GB minimum | 32 GB recommended for parallel training |
| CPU | M4 Pro (12 cores) | All Chronos-2 runs on CPU (MPS not supported) |
| Storage | 50 GB free | Model artifacts + data |
| Time | ~19 hours | Full pipeline, sequential |

**Optimization Strategies:**
- Parallelize specialists (4 at a time with 16GB RAM)
- Run overnight (Saturday 6AM ET start → Sunday completion)
- Cloud GPU for strategic Core models if budget allows

**Device Configuration:**
- ❌ **DO NOT use MPS (Apple Silicon GPU)** - Chronos-2 not supported
- ✅ Use `device="cpu"` for all TimeSeriesPredictor models
- ✅ Use default device for TabularPredictor (automatic)

### CORE = The Oracle (Kitchen Sink) [DEPRECATED CONCEPT]

**⚠️ The concept below is replaced by horizon-aligned architecture. Each horizon now gets its own Core model.**
- Receives **ALL** data from all sources
- AutoGluon 1.5 does its own feature selection
- Produces the authoritative ZL forecast
- The "All Knowing" - it gets everything

### SPECIALISTS = Dual Purpose

**PURPOSE A: Fold Into Core (Expert Opinions)**
```
L0: BASE MODELS (OOF extraction)
────────────────────────────────
  CORE (ZL baseline)     →  OOF p10/p50/p90
  + 11 SPECIALISTS       →  OOF p10/p50/p90 each
    crush, china, energy, biofuel, palm, substitutes,
    fx, fed, tariff, volatility, trump_effect
                    ↓
L1: META-LEARNER (AutoGluon 1.5 Bagging)
────────────────────────────────────────
  Input: 12 × 3 quantiles × 4 horizons = 144 features
  Learns: WHEN to trust each specialist
  Output: Weighted ensemble p10/p50/p90
                    ↓
L2: FUSION (Ensemble Stacking)
──────────────────────────────
  Combines meta-learner with regime detection
  Dynamic weighting: trump high? → boost trump_effect
                     vol spike? → boost volatility
                    ↓
L3: MONTE CARLO + AI (Risk Quantification)
──────────────────────────────────────────
  10,000 simulations from quantile distributions
  VaR/CVaR at 95%, 99%
  Confidence bands for dashboard
  AI: Regime-conditioned simulation paths
```

**PURPOSE B: Dashboard Pages (Intelligence Richness)**
```
Each specialist → Dedicated dashboard section
Rich domain features, charts, gauges, signals
Intelligence Core alone can't surface

┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────────┐
│ Crush   │ │ China   │ │ Energy  │ │ Trump Effect│ ...
│ Page    │ │ Page    │ │ Page    │ │ Page        │
├─────────┤ ├─────────┤ ├─────────┤ ├─────────────┤
│•Spread  │ │•CNY     │ │•Crack   │ │•EPU Regime  │
│•Margin  │ │•Import  │ │•Refinery│ │•Event Timer │
│•Capacity│ │•TPU     │ │•RIN     │ │•Policy Risk │
└─────────┘ └─────────┘ └─────────┘ └─────────────┘
```

### The Elegance
- **Core** tells you *what* will happen
- **Specialists** tell you *why* and *what to watch*
- **Dashboard users** get actionable intelligence, not just a number

### Example Flow
> Core says: "ZL +4% probability in 63d"
> Crush page shows: "Crush margins widening, capacity tight"
> China page shows: "Import pace accelerating, CNY stable"
> Trump page shows: "EPU elevated but no imminent action"
>
> **User knows:** The forecast AND the drivers AND what could break it

### Why AutoGluon 1.5 Bagging Matters
- OOF prevents leakage between L0 → L1
- Bagging reduces variance of specialist predictions
- Meta-learner sees *diverse views*, not redundant features

### The Final Ensemble
Core (kitchen sink) + 11 Expert Specialists → Meta-ensemble

**This is unmatched.** No retail quant, no hedge fund black box, nothing touches a properly trained Core + Specialist ensemble with Monte Carlo risk quantification.

---

## 5. SPECIALIST TAXONOMY (Big 11)

| Specialist | Variance | Key Data Sources | QUANT Signals |
|------------|----------|------------------|---------------|
| crush | 28-35% | ZM, ZS, ZL spreads | Processor margins, capacity utilization |
| china | 16-22% | DEXCHUS, import data | Policy signals, TPU index, FXI flows |
| energy | 10-14% | CL, HO, biofuel | Refinery margins, RFS mandates |
| biofuel | 6-10% | D4 RIN, ethanol | EPA waivers, RVO announcements |
| palm | 8-12% | CPO, MYR | Indonesia/Malaysia export policies |
| substitutes | 4-6% | Canola, sunflower | Crop conditions, trade flows |
| **trump_effect** | 5-10% | EPU, DJT, executive actions | **DECISION PRECURSOR DATA** |
| tariff | 3-5% | Trade policy uncertainty | Announcements, retaliations |
| fx | 3-5% | DXY, major pairs | Central bank signals |
| fed | 2-4% | FEDFUNDS, M2SL | FOMC dots, Fed speak |
| volatility | 2-3% | VIX, OVXCLS | Regime detection |

### Specialist Training Profiles (Each Is Unique)

**Neural Trio (Event-driven, regime-switching, fat-tailed):**
| Specialist | Training Style | Why |
|------------|----------------|-----|
| trump_effect | Neural/reactive | Event-driven, unprecedented, fat tails |
| volatility | Neural/reactive | Rapid regime changes, non-linear |
| china | Neural/reactive | Geopolitical, sentiment-heavy |

**Fundamentals Specialists (Slower, mean-reverting):**
| Specialist | Training Style | Why |
|------------|----------------|-----|
| crush | Fundamentals | Arbitrage-constrained, physical spreads |
| palm | Fundamentals | Supply-driven, seasonal, slow-moving |
| biofuel | Fundamentals | Policy-anchored, mandate-driven |

**Hybrid Specialists:**
| Specialist | Training Style | Why |
|------------|----------------|-----|
| fx | Technical + macro | Mean-reverting, central bank anchored |
| fed | Macro | Forward guidance, dots, speeches |
| energy | Fundamentals + events | Refinery + geopolitical |
| tariff | Event + policy | Announcement-driven |
| substitutes | Fundamentals | Cross-commodity arbitrage |

### Trump Effect Specialist (QUANT Edge)

**Purpose:** Capture policy uncertainty and predict executive actions

**Data Sources:**
- FRED: USEPUINDXD, USEPUINDXM, EPUTRADE, EMVTRADEPOLEMV, CHNMAINLANDTPU
- Yahoo: DJT (Trump Media), FXI (China ETF), KWEB (China tech)
- Events: Executive orders, tariff announcements, Truth Social signals

**EPU Regime Thresholds:**
| Regime | EPU Level | Vol Multiplier |
|--------|-----------|----------------|
| low | < 75 | 0.7x |
| normal | 75-125 | 1.0x |
| elevated | 125-175 | 1.25x |
| high | 175-250 | 1.5x |
| extreme | > 250 | 2.0x |

**REAL-WORLD VALIDATION: Venezuela Invasion (January 2026)**
- **Event:** Trump invaded Venezuela, going after oil
- **Impact:** Major energy market disruption, ZL affected via energy complex
- **Precursor signals to track:**
  - EPU trend in weeks before action
  - CFTC energy positioning shifts
  - DJT stock as Trump admin proxy
  - Venezuela-specific diplomatic rhetoric
  - Historical pattern: Trump 1.0 actions → classify and predict Trump 2.0
- **Lesson:** This is exactly what trump_effect specialist is built for. Architecture validated. Data population is the gap.

**Topic Codes (Event Classification):**
```
TARIFF_CHINA, TARIFF_OTHER, RFS_RVO, EPA_WAIVER, TAX,
SANCTIONS, EXPORT_CONTROLS, TRADE_DEAL, EXECUTIVE_ACTION, TWEET_THREAT,
MILITARY_ACTION (NEW - Venezuela 2026)
```

---

## 6. DATABASE SCHEMAS FOR 52-MODEL ARCHITECTURE

### OOF Tables (48 total: 4 Core + 44 Specialists)

**Pattern:** One table per model per horizon

```sql
-- Core OOF Tables (4 total)
CREATE TABLE training.oof_core_5d_1d (
    date DATE PRIMARY KEY,
    core_p10 FLOAT,
    core_p50 FLOAT,
    core_p90 FLOAT,
    target_5d FLOAT,  -- Actual ZL price at t+5
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE training.oof_core_21d_1d (
    date DATE PRIMARY KEY,
    core_p10 FLOAT,
    core_p50 FLOAT,
    core_p90 FLOAT,
    target_21d FLOAT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- ... similar for 63d, 126d

-- Specialist OOF Tables (44 total: 11 specialists × 4 horizons)
CREATE TABLE training.oof_crush_5d_1d (
    date DATE PRIMARY KEY,
    crush_p10 FLOAT,
    crush_p50 FLOAT,
    crush_p90 FLOAT,
    target_5d FLOAT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE training.oof_china_5d_1d (
    date DATE PRIMARY KEY,
    china_p10 FLOAT,
    china_p50 FLOAT,
    china_p90 FLOAT,
    target_5d FLOAT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- ... repeat for all 11 specialists × 4 horizons
```

### Meta Input Tables (4 total: one per horizon)

**Joined OOF for L1 training:**

```sql
-- Meta input table for 5d horizon
CREATE TABLE training.meta_inputs_5d_1d (
    date DATE PRIMARY KEY,
    -- Core OOF (3 cols)
    core_p10 FLOAT, core_p50 FLOAT, core_p90 FLOAT,
    -- Specialist OOF (11 × 3 = 33 columns)
    crush_p10 FLOAT, crush_p50 FLOAT, crush_p90 FLOAT,
    china_p10 FLOAT, china_p50 FLOAT, china_p90 FLOAT,
    fx_p10 FLOAT, fx_p50 FLOAT, fx_p90 FLOAT,
    fed_p10 FLOAT, fed_p50 FLOAT, fed_p90 FLOAT,
    tariff_p10 FLOAT, tariff_p50 FLOAT, tariff_p90 FLOAT,
    energy_p10 FLOAT, energy_p50 FLOAT, energy_p90 FLOAT,
    biofuel_p10 FLOAT, biofuel_p50 FLOAT, biofuel_p90 FLOAT,
    palm_p10 FLOAT, palm_p50 FLOAT, palm_p90 FLOAT,
    vol_p10 FLOAT, vol_p50 FLOAT, vol_p90 FLOAT,
    subs_p10 FLOAT, subs_p50 FLOAT, subs_p90 FLOAT,
    trump_p10 FLOAT, trump_p50 FLOAT, trump_p90 FLOAT,
    -- Regime features (3 cols)
    regime_vix FLOAT, regime_dxy FLOAT, regime_term FLOAT,
    -- Calendar features (3 cols)
    is_wasde_week BOOLEAN, is_fomc_week BOOLEAN, is_expiry BOOLEAN,
    -- Target
    target_5d FLOAT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- ... repeat for 21d, 63d, 126d
```

### Production Forecast Tables (4 total)

```sql
CREATE TABLE forecasts.production_5d_1d (
    forecast_date DATE,
    as_of_date DATE,
    p10 FLOAT,
    p50 FLOAT,
    p90 FLOAT,
    model_version VARCHAR(50),
    created_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (forecast_date, as_of_date)
);

CREATE TABLE forecasts.production_21d_1d (
    forecast_date DATE,
    as_of_date DATE,
    p10 FLOAT,
    p50 FLOAT,
    p90 FLOAT,
    model_version VARCHAR(50),
    created_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (forecast_date, as_of_date)
);

-- ... similar for 63d, 126d
```

### Validation Checklist

**Pre-Training:**
- [ ] All 4 Core models configured with matching prediction_length
- [ ] All 44 Specialists configured with matching target horizon
- [ ] problem_type="quantile" on ALL models (Core, Specialists, Meta)
- [ ] quantile_levels=[0.10, 0.50, 0.90] consistent everywhere
- [ ] device="cpu" for Chronos-2 (MPS not supported)
- [ ] OOF tables created for all 48 L0 models
- [ ] Meta input tables created for all 4 horizons

**Post-Training:**
- [ ] OOF predictions extracted from all L0 models
- [ ] All OOF columns predict correct horizon target
- [ ] Meta input matrices joined correctly
- [ ] L1 models trained on aligned OOF data
- [ ] Pinball loss metrics logged
- [ ] Conformal calibration produces 90% coverage

**Deployment:**
- [ ] refit_full() called on all 52 models
- [ ] Production artifacts saved to model registry
- [ ] Forecasts generated for all 4 horizons
- [ ] Dashboard updated with new predictions

---

## 7. DOWNLOADED DATA (Jan 4, 2026)

### Ready for Ingestion

**USDA WASDE (Backfill Priority):**
- `WASDE_DATA_*.zip` - 6.3 MB historical data
- `WASDE_METADATA_*.zip` - 207 KB
- `WASDE_PROJ_*.zip` - 501 KB

**CFTC Data:**
- `QDL_CITS_*.zip` - 1.06 MB index traders data

**Brazil Weather (INMET):**
- 80+ CSV files for RS, PR, SC states
- Soy belt weather stations

**FX Historical:**
- USDCNY, USDBRL, USDMYR, USDARS daily data

**Volatility:**
- VIXCLS, VXGSCLS for FRED backfill

**Trade/Import Data:**
- `States with Countries Import*.csv` - 1.7 MB
- `import_goods_services_countries_dataset.csv` - 2.1 MB

---

## 7. MULTI-FREQUENCY DATA ARCHITECTURE (CRITICAL)

### The Problem
Different data sources have different frequencies:
| Frequency | Sources | Update Pattern |
|-----------|---------|----------------|
| Daily | ZL prices, FRED rates, FX | Continuous |
| Weekly | CFTC COT, some USDA reports | Friday release |
| Monthly | WASDE, Census trade, GDP | Mid-month release |

AutoGluon expects consistent frequency. How do we train models with mixed-frequency data?

### The Solution: Option 4 (Hybrid with Staleness Encoding)

**Forward-fill BUT add auxiliary features that encode information staleness:**
```python
# For each slow-frequency feature, create companions:
cot_commercial_net        # Latest known value (forward-filled)
cot_commercial_net_age    # Days since last COT release (0-6)
cot_commercial_net_delta  # Change from prior week (null except Fridays)

wasde_ending_stocks       # Latest known value
wasde_ending_stocks_age   # Days since WASDE release (0-30)
wasde_is_release_day      # Binary flag (1 on release day, 0 otherwise)
```

**Why This Works:**
- Model learns to weight "stale" vs "fresh" features
- Preserves information arrival timing
- Event-driven signals (release days) become learnable
- Single daily training matrix

### Storage Layer (Prisma)
Keep landing tables at **native source frequency**:
```
pos.cftc_1w              -- weekly rows, Friday timestamps
supply.usda_wasde_1m     -- monthly rows, release date timestamps
mkt.futures_1d           -- daily rows
```

### Feature Engineering Layer
Build daily training matrix with staleness encoding:
```python
def build_training_matrix(as_of_date):
    # Daily base
    df = get_daily_prices(as_of_date)
    
    # Forward-fill weekly COT
    cot = get_latest_cot_as_of(as_of_date)
    df['cot_commercial_net'] = cot['commercial_net']
    df['cot_age_days'] = (as_of_date - cot['report_date']).days
    df['cot_is_fresh'] = 1 if df['cot_age_days'] == 0 else 0
    
    # Forward-fill monthly WASDE
    wasde = get_latest_wasde_as_of(as_of_date)
    df['wasde_ending_stocks'] = wasde['ending_stocks']
    df['wasde_age_days'] = (as_of_date - wasde['release_date']).days
    df['wasde_is_release_day'] = 1 if df['wasde_age_days'] == 0 else 0
    
    return df
```

### Point-in-Time Correctness (CRITICAL)
You must respect release dates to prevent lookahead bias:
```python
# WRONG - leaks future information
df['wasde_stocks'] = wasde_df.loc[df['date'].dt.month]

# CORRECT - only use data available as of that date
df['wasde_stocks'] = wasde_df[wasde_df['release_date'] <= df['date']].last()
```

WASDE releases mid-month. If you're building features for January 10th, you must use December's WASDE, not January's.

### Specialist Implications
Each specialist weights fresh vs stale information differently:
- **Volatility specialist** → cares about fresh COT (positioning shifts)
- **Crush specialist** → weights WASDE fundamentals regardless of age
- **Trump Effect specialist** → EPU freshness critical, event_is_release_day matters

---

## 7A. DATA SOURCES REGISTRY

### Available via FRED API (FREE - 50+ series)
**Rates:** DFF, FEDFUNDS, DGS1-DGS30, T10Y2Y, T10Y3M, SOFR
**FX:** DEXBZUS, DEXCHUS, DEXMXUS, DEXCAUS, DTWEXBGS
**Energy:** DCOILWTICO, DCOILBRENTEU, DHHNGSP
**Volatility:** VIXCLS, STLFSI4, NFCI, BAMLH0A0HYM2
**EPU (Trump):** USEPUINDXD, USEPUINDXM, EPUTRADE, EMVTRADEPOLEMV, CHNMAINLANDTPU
**Macro:** CPIAUCSL, GDP, PAYEMS, UNRATE, M2SL

### Available via Yahoo (FREE)
**Trump Proxies:** DJT (Trump Media), FXI (China ETF), KWEB (China tech)
**VIX:** ^VIX direct

### Available via URL Scraping

**CRITICAL PRIORITY:**
| Source | URL | Data | Specialist |
|--------|-----|------|------------|
| EPA RIN | https://www.epa.gov/fuels-registration-reporting-and-compliance-help/rin-trades-and-price-information | D3/D4/D5/D6 RINs | Biofuel |
| USDA WASDE | https://www.usda.gov/oce/commodity/wasde | Supply/demand | Crush/China |
| White House RSS | https://www.whitehouse.gov/briefing-room/statements-releases/feed/ | Executive actions | Trump Effect |
| Federal Register API | https://www.federalregister.gov/api/v1/documents.json | Executive orders | Trump Effect |

**HIGH PRIORITY:**
| Source | URL | Data | Specialist |
|--------|-----|------|------------|
| CFTC COT | https://www.cftc.gov/MarketReports/CommitmentsofTraders/ | Fund positioning | All |
| CONAB Brazil | https://www.conab.gov.br/info-agro/safras | Harvest progress | Crush |
| MPOB Malaysia | http://bepi.mpob.gov.my/ | Palm oil stats | Palm |
| EIA API | https://api.eia.gov/v2/ | Energy data | Energy |

**QUANT EDGE (Decision Precursor):**
| Source | URL | Data | Specialist |
|--------|-----|------|------------|
| Truth Social | https://truthsocial.com/@realDonaldTrump | Trump signals | Trump Effect |
| Polymarket | https://polymarket.com/ | Policy probabilities | Trump Effect |
| Federal Register Tariffs | https://www.federalregister.gov/api/v1/documents.json?search_term=tariff | Tariff orders | Tariff |

**ANALYSTS TO FOLLOW (Twitter via ScrapeCreators):**
| Handle | Focus | Priority |
|--------|-------|----------|
| @kannbwx (Karen Braun) | Weather, crops, global grains | P0 |
| @ArlanFF101 (Arlan Suderman) | Grain markets, policy | P0 |
| @ScottIrwinUIUC | Ag economics, biofuels | P0 |
| @SoybeanCorn | South America crops | P0 |
| @JavierBlas | Commodities, energy | P1 |

### API Keys Required
| Service | Cost | Status |
|---------|------|--------|
| FRED | Free | ✅ Have |
| EIA | Free | ✅ Have |
| NOAA CDO | Free | ✅ Have |
| data.gov (USDA) | Free | ✅ Have |
| Databento | Paid | ✅ Have |
| ScrapeCreators | Paid | ⚠️ Need for Twitter |
| TradingEconomics | Paid | ⚠️ Optional |

---

## 8. FEATURE ENGINEERING REQUIREMENTS

### Current State
- Technical indicators implemented
- Basic fundamentals (crush spread, COT positioning)
- Weather features (limited)

### Missing QUANT Features

**Decision Precursor Features:**
- EPU regime classification + momentum
- CFTC positioning CHANGE (not level)
- Policy event countdown features
- Executive action pattern recognition

**Supply Chain Features:**
- Import flow momentum by country
- Export sales pace vs. historical
- Crush capacity utilization proxy
- Storage/inventory change signals

**Insider Behavior Features:**
- Managed money position change velocity
- Commercial hedger stress indicators
- Options put/call ratio shifts
- Unusual volume detection

---

## 9. NAMING CONTRACTS (Locked)

| Rule | Required | Forbidden |
|------|----------|-----------|
| Grain suffix | `_1h`, `_1d`, `_1w`, `_event`, `_static` | time-series without suffix |
| Table naming | `mkt.futures_1d` | names containing `ohlc` / `ohlcv` |
| Horizons | integer `5`, `21`, `63`, `126` | string horizons `"1w"`, `"1m"` |
| Quantile columns | `p10`, `p50`, `p90` or `p30`, `p50`, `p70` | ad-hoc names like `q10`, `pred_p10` |
| Schema naming | Institutional: `mkt`, `econ`, `alt`, `pos`, `supply` | Legacy: `raw`, `gold`, `silver` |

---

## 10. LESSONS LEARNED

1. **Accuracy over speed** - Verify before acting
2. **Data availability ≠ DB coverage** - M2SL has 64 years in FRED, only months in DB
3. **Strategic ≠ Tactical** - Different models, not just different data windows
4. **QUANT = Decision Data** - The edge is predicting decisions, not reacting to them
5. **Backfill priorities** - WASDE, M2SL, OVXCLS are critical gaps
6. **Venezuela 2026** - Real validation that trump_effect architecture is correct

---

## 10A. TRAINING WITH MIXED-ERA DATA

### The Challenge
How does ZL data from 1970 train with CFTC COT from 2006 and EPU from 1985?

### The Answer: Tiered Feature Availability

**Training Matrix Structure:**
```
as_of_date | zl_close | cot_net | epu | wasde_stocks | ...
1970-01-05 |   12.50  |  NULL   | NULL |    NULL     |
...
1985-01-05 |   22.30  |  NULL   | 85.2 |    NULL     |
...
2006-06-16 |   28.40  |  +15000 | 92.1 |   1250      |
...
2025-12-29 |   48.78  |  +22000 | 178.5|   1180      |
```

### How AutoGluon Handles This

**TabularPredictor:**
- Treats NULLs as missing values
- Tree-based models (LightGBM, CatBoost, XGBoost) handle missing natively
- Model learns: "when COT is available, weight it; when not, rely on price patterns"

**TimeSeriesPredictor:**
- Chronos models learn from available history
- Longer price history (1970+) provides regime context
- Shorter feature series (2006+) provide recent signal

### Tiered Training Strategy

**Tier 1 Data (1970-2000): Price-Only Era**
- ZL OHLCV, basic FX, Treasury yields
- Technical indicators only
- Useful for: Long-term seasonal patterns, volatility regimes

**Tier 2 Data (2000-2006): Macro Era**
- Add: FRED economic series, EPU indices
- Useful for: Macro-regime relationships

**Tier 3 Data (2006-present): Full Feature Era**
- Add: CFTC COT, USDA data, options
- Useful for: Full specialist training

### Practical Implications

**For Strategic Horizons (63d/126d):**
- Use full history (1970+) for regime learning
- Accept that COT features are NULL pre-2006
- Model still learns price patterns from 55 years

**For Tactical Horizons (5d/21d):**
- Can use shorter window (2010+) with full features
- Less NULL handling, cleaner signal

### Feature Engineering Rule
Always create features that degrade gracefully:
```python
# Good - works with missing data
df['cot_zscore'] = (df['cot_net'] - df['cot_net'].rolling(52).mean()) / df['cot_net'].rolling(52).std()

# Bad - fails with missing data
df['cot_signal'] = np.where(df['cot_net'] > 0, 1, -1)  # NaN becomes 0 or error
```

---

## 11. SPECIALIST ROUTING ARCHITECTURE (Complete)

### Router Location
`src/fusion/ingestion/router.py` (676 lines)

### SpecialistRouter Class
- Pattern matching (regex, highest weight)
- Keyword matching (medium weight)
- Series prefix matching (strongest signal)
- Returns confidence scores for multi-bucket assignment

### FRED_SERIES_BUCKETS Mapping (Canonical)

```python
# FED bucket
"DFF": FED,          # Fed Funds Rate
"DGS10": FED,        # 10-Year Treasury
"DGS2": FED,         # 2-Year Treasury
"T10Y2Y": FED,       # Yield Curve
"T10Y3M": FED,       # Yield Curve
"SOFR": FED,         # SOFR Rate
"M2SL": FED,         # M2 Money Supply
"WALCL": FED,        # Fed Balance Sheet
"CPIAUCSL": FED,     # CPI
"PCEPI": FED,        # PCE Price Index

# FX bucket
"DEXUSEU": FX,       # USD/EUR
"DEXBZUS": FX,       # USD/BRL
"DEXCHUS": FX,       # USD/CNY (but also routed to china)
"DEXMXUS": FX,       # USD/MXN
"DTWEXBGS": FX,      # Trade Weighted USD
"DTWEXM": FX,        # Trade Weighted USD (Major)

# ENERGY bucket
"DCOILWTICO": ENERGY,    # WTI Crude
"DCOILBRENTEU": ENERGY,  # Brent Crude
"DHHNGSP": ENERGY,       # Henry Hub Natural Gas
"GASREGW": ENERGY,       # Gasoline Prices

# CRUSH bucket
"PSOYBOILUSDM": CRUSH,       # Soybean Oil
"PSOYBEANMEALUSDM": CRUSH,   # Soybean Meal

# VOLATILITY bucket
"VIXCLS": VOLATILITY,        # VIX
"STLFSI4": VOLATILITY,       # Financial Stress Index
"BAMLH0A0HYM2": VOLATILITY,  # HY OAS (risk proxy)
"OVXCLS": VOLATILITY,        # Oil VIX

# TRUMP_EFFECT bucket (QUANT EDGE)
"USEPUINDXD": TRUMP_EFFECT,      # US EPU (Daily)
"USEPUINDXM": TRUMP_EFFECT,      # US EPU (Monthly)
"EPUTRADE": TRUMP_EFFECT,        # Trade Policy Uncertainty
"EMVTRADEPOLEMV": TRUMP_EFFECT,  # EMV Trade Policy
"CHNMAINLANDTPU": TRUMP_EFFECT,  # China TPU
"B235RC1Q027SBEA": TRUMP_EFFECT, # Customs Duties (tariff receipts)
"IMPCH": TRUMP_EFFECT,           # US Imports from China
```

### Routing Rules by Bucket

| Bucket | Patterns | Keywords (examples) | Series Prefixes |
|--------|----------|---------------------|-----------------|
| CRUSH | `crush.*margin`, `soybean.*process` | ZS, ZM, crush | - |
| CHINA | `china`, `cnh`, `renminbi` | china, beijing, yuan | CNY |
| FX | `forex`, `currency`, `exchange.*rate` | fx, currency, usdbrl | DEX |
| FED | `federal.*reserve`, `fomc`, `monetary.*policy` | fed, fomc, taper | DFF, DGS |
| TARIFF | `tariff`, `section.*301`, `trade.*war` | tariff, duty, import_tax | - |
| ENERGY | `crude`, `petroleum`, `gasoline` | wti, brent, natural_gas | DCOIL |
| BIOFUEL | `biofuel`, `ethanol`, `rin`, `rvo` | d4_rin, rfs, renewable | - |
| PALM | `palm.*oil`, `cpo`, `indonesia.*export` | palm, cpo, myr | - |
| VOLATILITY | `vix`, `volatility`, `stress.*index` | vix, vol, stress | VIX, VX |
| SUBSTITUTES | `canola`, `sunflower`, `rapeseed` | canola, rape, sun | CANOLA, RAPE |
| TRUMP_EFFECT | `trump`, `executive.*order`, `policy.*uncertainty` | trump, tweet, truth_social | USEPUINDX, EPUTRADE |

### Target Table Naming
`training.specialist_{bucket_name}_{grain}` → e.g., `training.specialist_trump_effect_1d`

---

## 11. FEATURE ENGINEERING MODULES (Complete Map)

### File Locations
```
src/fusion/features/
├── elite_indicators.py      # 27 institutional-grade indicators
├── specialist_buckets.py    # Big-11 Specialist configurations
├── trump_effect.py          # Trump Effect feature engine
├── engineer.py              # Feature orchestration
└── targets.py               # Forward returns calculation
```

### Elite Indicators (`elite_indicators.py`, 833 lines)

**Tier 1: Institutional Gems**
- Hurst Exponent: Regime detection (H>0.5=trending, H<0.5=mean-reverting)
- ConnorsRSI: Composite (price RSI + streak + percentile rank)
- Fisher Transform: Normalize RSI/price to Gaussian
- McGinley Dynamic: Adaptive moving average
- Ehlers Filter: Hilbert Transform cycle detection

**Tier 2: Optimized Staples**
- Keltner Channel Squeeze: Bollinger inside Keltner = compression
- TTM Squeeze: Momentum + squeeze indicator
- Volume Profile: Relative volume z-score
- Elder Ray: Bull/Bear power separation

**Tier 3: Volatility Regime**
- Yang-Zhang Vol: Open-to-close + close-to-open combined
- Garman-Klass Vol: High-low-close estimator
- ATR Ratio: Current vs. historical ATR
- Vol-of-Vol: Volatility acceleration

**Tier 4: Volume/Flow**
- OBV Divergence: Price vs. OBV trend divergence
- MFI: Volume-weighted RSI
- ADL: Accumulation/Distribution Line
- VWAP Deviation: Institutional fair value distance

### Specialist Configs (`specialist_buckets.py`, 2100 lines)

```python
@dataclass
class BucketConfig:
    name: str
    weight_range: Tuple[float, float]  # Variance contribution
    primary_features: List[str]
    secondary_features: List[str]
    regime_thresholds: Dict[str, float]
    symbol_mappings: Dict[str, str]
```

**BUCKET_CONFIGS:**
| Bucket | Weight Range | Primary Features |
|--------|--------------|------------------|
| crush | (0.28, 0.35) | crush_spread, zm_zs_ratio, capacity_util |
| china | (0.16, 0.22) | cny_momentum, import_pace, policy_signals |
| energy | (0.10, 0.14) | wti_brent_spread, crack_spread, refinery_margin |
| palm | (0.08, 0.12) | cpo_spread, myr_moves, indo_policy |
| biofuel | (0.06, 0.10) | d4_rin_price, rvo_gap, blend_mandate |
| substitutes | (0.04, 0.06) | canola_spread, sun_oil_premium |
| trump_effect | (0.05, 0.10) | epu_regime, djt_momentum, event_intensity |
| tariff | (0.03, 0.05) | tariff_rate_chg, trade_deficit_accel |
| fx | (0.03, 0.05) | dxy_momentum, em_fx_stress |
| fed | (0.02, 0.04) | rate_path, m2_growth, yield_curve |
| volatility | (0.02, 0.03) | vix_term_structure, vol_regime |

### Trump Effect Engine (`trump_effect.py`, 906 lines)

**Core Classes:**
```python
@dataclass
class EventIntensity:
    shock_severity: float    # 0-1, how severe
    uncertainty_score: float # 0-1, policy fog
    novelty_score: float     # 0-1, unprecedented

@dataclass  
class ProbabilityProxies:
    djt_momentum: float      # Trump Media stock
    fxi_sensitivity: float   # China ETF
    kweb_sensitivity: float  # China tech ETF

@dataclass
class EPURegime:
    level: str               # low/normal/elevated/high/extreme
    value: float             # Raw EPU index
    vol_multiplier: float    # Risk adjustment
```

**Key Functions:**
- `calculate_shock_severity()`: Event magnitude scoring
- `calculate_uncertainty_score()`: Policy fog measurement
- `calculate_novelty_score()`: First-time event detection
- `detect_epu_regime()`: Classify current EPU state
- `fit_trump_regime_garch()`: GJR-GARCH with EPU adjustment

**Topic Codes (Event Classification):**
```
TARIFF_CHINA, TARIFF_OTHER, RFS_RVO, EPA_WAIVER, TAX,
SANCTIONS, EXPORT_CONTROLS, TRADE_DEAL, EXECUTIVE_ACTION, TWEET_THREAT
```

---

## 12. GAP ANALYSIS: CURRENT STATE vs. REQUIREMENTS

### ✅ IMPLEMENTED

| Component | Status | Notes |
|-----------|--------|-------|
| Market OHLCV (ZL) | ✅ 55 years | 1970-2025, 418K rows |
| FRED pipeline | ✅ 157 series | But many need backfill |
| CFTC COT | ✅ 19 years | 2006-2025, 18K rows |
| Elite indicators | ✅ 27 indicators | Hurst, TTM Squeeze, etc. |
| Specialist routing | ✅ 11 Specialists | Pattern + keyword + prefix |
| EPU regime detection | ✅ Code ready | Needs population |

### ⚠️ PARTIALLY IMPLEMENTED

| Component | Status | Gap |
|-----------|--------|-----|
| USDA WASDE | ⚠️ 5 years | Need 20+ years backfill |
| Trump Effect | ⚠️ Code ready | Table has 0 rows |
| Weather features | ⚠️ Basic | Brazil INMET not ingested |
| Options flow | ⚠️ 28K rows | Need unusual activity detection |

### ❌ NOT IMPLEMENTED

| Component | Priority | Data Available? |
|-----------|----------|-----------------|
| Decision precursor features | HIGH | FRED EPU ✅, Events ❌ |
| Position change velocity | HIGH | CFTC COT ✅, needs feature |
| Event countdown features | HIGH | Need event database |
| Executive action patterns | MEDIUM | Need scraping |
| Lobbying data | MEDIUM | OpenSecrets API |
| Shipping/vessel tracking | LOW | Need commercial API |

---

## 13. PIPELINE STATE (L0 → L3)

### Current State (52-Model Architecture)

| Layer | Models Required | Status | Blocker |
|-------|-----------------|--------|---------|
| L0: Core (4 horizons) | 4 | ⚠️ Partial | Need horizon-aligned retraining |
| L0: Specialists (11 × 4) | 44 | ❌ Not generated | Need horizon-aligned OOF tables |
| L1: Meta-learners | 4 | ❌ Can't train | Waiting on all 48 L0 OOFs |
| L2: Post-Model Intelligence | 4 | ❌ Waiting | Needs L1 |
| L3: Risk Engine | 4 | ❌ Waiting | Needs L2 |

**CRITICAL:** Previous architecture (single Core @ 126d) is invalid. All 52 models must be retrained with horizon alignment.

### OOF Table Requirements (48 tables)

**Core OOF Tables (4 tables):**
- [ ] training.oof_core_5d_1d
- [ ] training.oof_core_21d_1d
- [ ] training.oof_core_63d_1d
- [ ] training.oof_core_126d_1d

**Specialist OOF Tables (44 tables = 11 specialists × 4 horizons):**

For each specialist (crush, china, fx, fed, tariff, energy, biofuel, palm, volatility, substitutes, trump):
- [ ] training.oof_{specialist}_5d_1d
- [ ] training.oof_{specialist}_21d_1d
- [ ] training.oof_{specialist}_63d_1d
- [ ] training.oof_{specialist}_126d_1d

**Meta Input Tables (4 tables):**
- [ ] training.meta_inputs_5d_1d
- [ ] training.meta_inputs_21d_1d
- [ ] training.meta_inputs_63d_1d
- [ ] training.meta_inputs_126d_1d

### Specialist Feature Status (training schema)
| Specialist | OHLCV Data | OOF Generated | Dashboard Ready |
|------------|------------|---------------|-----------------|
| crush | ✅ 23,487 rows | ❌ | ❌ |
| china | ✅ 27,492 rows | ❌ | ❌ |
| energy | ✅ 45,380 rows | ❌ | ❌ |
| biofuel | ✅ 42,055 rows | ❌ | ❌ |
| palm | ✅ 24,037 rows | ❌ | ❌ |
| substitutes | ✅ 42,706 rows | ❌ | ❌ |
| fx | ✅ 80,165 rows | ❌ | ❌ |
| fed | ✅ 48,174 rows | ❌ | ❌ |
| tariff | ✅ 42,414 rows | ❌ | ❌ |
| volatility | ✅ 35,088 rows | ❌ | ❌ |
| **trump_effect** | ❌ **0 rows** | ❌ | ❌ |

### The Path Forward (52-Model Architecture)

1. **Create OOF table schemas** (48 tables: 4 Core + 44 Specialists)
2. **Retrain Core models** (4 models, one per horizon with matching prediction_length)
3. **Train Specialists** (44 models: 11 specialists × 4 horizons)
4. **Extract OOF predictions** (All 48 L0 models)
5. **Build meta input matrices** (4 tables with 42 features each)
6. **Train L1 Meta-learners** (4 models)
7. **Implement L2 Post-Model Intelligence** (conformal calibration, regime gates)
8. **Build L3 Risk Engine** (Monte Carlo simulation)
9. **Dashboard integration** (All 4 horizons)

---

## 14. NEXT STEPS (Updated for 52-Model Architecture)

**CRITICAL PRIORITY: Architecture Migration**
1. ☐ **Create database schemas for 52-model architecture** (48 OOF + 4 meta input + 4 production tables)
2. ☐ **Implement Core training scripts** (4 scripts, one per horizon)
3. ☐ **Implement Specialist training scripts** (11 × 4 = 44 training runs)
4. ☐ **Implement L1 meta-learner training** (4 scripts)
5. ☐ **Validate horizon alignment** (ensure all OOF predictions match target horizons)

**Data Quality Improvements:**
6. ☐ **Populate trump_effect specialist table** (currently 0 rows)
7. ☐ **Create WASDE backfill ingestion script** (20 years missing)
8. ☐ **Ingest Brazil INMET weather data** (downloaded, not ingested)
9. ☐ **Implement position change velocity features** (CFTC derivatives)

**Previous Milestones (Completed):**
1. ☑ Examined feature engineering code (COMPLETE)
2. ☑ Mapped specialist bucket → feature module relationships (COMPLETE)
3. ☑ Documented Core + Specialist architecture (COMPLETE)
4. ☑ **DISCOVERED AND CORRECTED CRITICAL ARCHITECTURE FLAW** (Jan 13, 2026)

---

## 15. TABLE ARCHITECTURE DECISION (CRITICAL - Session 3)

### The Answer: Option A+ (Dataset-Level Facts + Reference Data)

**Decision:** Keep dataset-level tables (raw.fx_spot_1d, raw.market_futures_1d) BUT add proper identity, provenance, and uniqueness at the database level.

**Why current tables feel "too generic":**
It's NOT because multiple symbols share one table - that's normal and correct.
It feels generic because tables don't enforce:
- **Identity:** "What exactly is this series?" (instrument master)
- **Provenance:** "Which source produced this row?"
- **Uniqueness:** "One truth per (instrument, timestamp, source)"

Without these, the `symbol` column becomes a junk drawer.

### Current State (Verified 2026-01-06)

**metadata schema:** Does NOT exist yet
**raw.fx_spot_1d columns:** id, pair, as_of_date, rate, created_at (NO instrument_id)
**raw.market_futures_1d columns:** as_of_date, symbol, OHLCV, source, ingested_at (NO instrument_id)

**Good news:** Some tables already have composite UNIQUE constraints:
- `cftc_cot_1w`: UNIQUE(report_date, symbol)
- `cftc_cits_1w`: UNIQUE(report_date, contract_code, report_type)
- `yahoo_equity_1d`: UNIQUE(symbol, as_of_date)
- `weather_noaa_1d`: UNIQUE(station_id, as_of_date)
- `usda_wasde_1m`: UNIQUE(report_date, commodity, country, metric)

**Bad news:** Core tables missing uniqueness:
- `fx_spot_1d`: NO unique constraint
- `market_futures_1d`: NO unique constraint
- `fred_observations_1d`: Need to check

### Architecture To Implement

#### 1. Metadata Schema (Reference Data Layer)

```sql
-- metadata.instrument: One row per canonical series
CREATE TABLE metadata.instrument (
    id BIGSERIAL PRIMARY KEY,
    canonical_symbol TEXT UNIQUE NOT NULL,  -- ZL, USDCNY, FEDFUNDS
    asset_class TEXT NOT NULL,  -- FUTURE, FX, MACRO, EQUITY, WEATHER
    domain TEXT,  -- crush, china, fx, fed (specialist routing)
    currency TEXT,
    unit TEXT,
    point_value DECIMAL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- metadata.source: One row per vendor/feed
CREATE TABLE metadata.source (
    id BIGSERIAL PRIMARY KEY,
    code TEXT UNIQUE NOT NULL,  -- FRED, CFTC, USDA, DATABENTO, NOAA, YAHOO
    vendor TEXT,
    url TEXT,
    default_tz TEXT,
    license_notes TEXT
);

-- metadata.instrument_alias: Maps vendor symbols to canonical
CREATE TABLE metadata.instrument_alias (
    id BIGSERIAL PRIMARY KEY,
    instrument_id BIGINT REFERENCES metadata.instrument(id),
    source_id BIGINT REFERENCES metadata.source(id),
    source_symbol TEXT NOT NULL,  -- Vendor's symbol (FRED series ID, etc.)
    UNIQUE(source_id, source_symbol)
);

-- metadata.instrument_group: Domain groupings (Option C engine)
CREATE TABLE metadata.instrument_group (
    id BIGSERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,  -- fx_major, fx_em, futures_oilseeds
    description TEXT
);

-- metadata.instrument_group_member: Group membership
CREATE TABLE metadata.instrument_group_member (
    group_id BIGINT REFERENCES metadata.instrument_group(id),
    instrument_id BIGINT REFERENCES metadata.instrument(id),
    PRIMARY KEY (group_id, instrument_id)
);
```

#### 2. Raw Fact Tables (Option A+ Form)

Every raw table gets:
- `instrument_id` (FK → metadata.instrument.id)
- `source_id` (FK → metadata.source.id)
- Composite UNIQUE constraint: `(instrument_id, date, source_id)`
- Index on `(instrument_id, date)` for dominant query pattern

**Example: raw.fx_spot_1d after upgrade:**
```sql
ALTER TABLE raw.fx_spot_1d ADD COLUMN instrument_id BIGINT;
ALTER TABLE raw.fx_spot_1d ADD COLUMN source_id BIGINT;
ALTER TABLE raw.fx_spot_1d ADD CONSTRAINT fk_fx_instrument 
    FOREIGN KEY (instrument_id) REFERENCES metadata.instrument(id);
ALTER TABLE raw.fx_spot_1d ADD CONSTRAINT fk_fx_source 
    FOREIGN KEY (source_id) REFERENCES metadata.source(id);
ALTER TABLE raw.fx_spot_1d ADD CONSTRAINT uq_fx_spot 
    UNIQUE (instrument_id, as_of_date, source_id);
CREATE INDEX idx_fx_spot_inst_date ON raw.fx_spot_1d(instrument_id, as_of_date);
```

**Example: raw.market_futures_1d with series_variant:**
```sql
-- For futures, need series_variant for continuous vs contract bars
ALTER TABLE raw.market_futures_1d ADD COLUMN instrument_id BIGINT;
ALTER TABLE raw.market_futures_1d ADD COLUMN source_id BIGINT;
ALTER TABLE raw.market_futures_1d ADD COLUMN series_variant TEXT DEFAULT 'CONTINUOUS_FRONT';
-- UNIQUE includes series_variant to distinguish roll methods
ALTER TABLE raw.market_futures_1d ADD CONSTRAINT uq_futures 
    UNIQUE (instrument_id, as_of_date, source_id, series_variant);
CREATE INDEX idx_futures_inst_date ON raw.market_futures_1d(instrument_id, series_variant, as_of_date);
```

#### 3. Option C = Groups + Views (NOT New Tables)

Domain-level segmentation (fx_em, fx_major, futures_oilseeds) is implemented as:
- Group definitions in `metadata.instrument_group`
- Membership mappings in `metadata.instrument_group_member`
- SQL views for convenience queries

**Example view:**
```sql
CREATE VIEW raw.v_fx_em_1d AS
SELECT f.* 
FROM raw.fx_spot_1d f
JOIN metadata.instrument_group_member gm ON f.instrument_id = gm.instrument_id
JOIN metadata.instrument_group g ON gm.group_id = g.id
WHERE g.name = 'fx_em';
```

### Why This Architecture

1. **Scales to 87+ symbols** without schema migrations
2. **Multiple vendors** can coexist (source_id distinguishes)
3. **New series** just add rows to instrument table
4. **Upsert-safe** via composite UNIQUE constraints
5. **Query-optimized** via proper indexes
6. **Domain routing** via groups, not table proliferation

### Migration Plan Required

**Before ANY more ingestion:**
1. Create metadata schema + tables
2. Populate metadata.source (FRED, CFTC, USDA, DATABENTO, NOAA, YAHOO, QUANDL)
3. Populate metadata.instrument (all canonical symbols we track)
4. Populate metadata.instrument_alias (vendor symbol → canonical mappings)
5. ALTER existing raw tables to add instrument_id, source_id
6. Backfill instrument_id from existing symbol columns via alias lookup
7. Add UNIQUE constraints and indexes
8. Create domain groups and views

### Why Option B Is Dead

One table per symbol (raw.fx_usdcny_1d, raw.fx_usdbrl_1d) means:
- Schema migration every time you add a symbol
- 87+ tables just for futures
- Unmaintainable at scale
- **Hard no.**

---

## 16. SESSION 3 WORK LOG (2026-01-06)

### What Was Actually Done

1. **Verified CITS Ingestion Success**
   - `raw.cftc_cits_1w` confirmed: 34,428 rows
   - SOYBEAN_OIL (ZL): 2,652 rows from 2013-01-08 to 2025-09-16
   - Data is REAL - Index Trader positioning (longs, shorts, net)
   - Has proper UNIQUE constraint: (report_date, contract_code, report_type)

2. **Architecture Decision Made: Option A+**
   - Keep dataset-level tables (deferred metadata schema for now)
   - Focus on constraints + cleanup first (minimal change approach)

---

## 17. SESSION 4 WORK LOG (2026-01-05)

### Complete Database Audit

Performed comprehensive audit of all 14 raw tables:

| Table | Unique Identifiers | Rows |
|-------|-------------------|------|
| market_futures_1d | 87 symbols | 418,864 |
| market_futures_1h | 84 symbols | 4,967,276 |
| fx_spot_1d | 30→9 pairs | 211,752→72,135 |
| fred_observations_1d | 157 series | 491,215 |
| cftc_cot_1w | 24 symbols | 18,355 |
| cftc_cits_1w | 13 contracts | 34,428 |
| yahoo_equity_1d | 3 symbols | 9,534 |
| weather_noaa_1d | 57 stations | 215,320 |
| usda_wasde_1m | 71 combos | 10,164 |
| usda_export_sales_1w | 21 combos | 6,412 |
| epa_rin_prices_1d | 4 types | 208 |
| news_articles_1d | 112 sources | 5,264 |
| options_futures_1d | 14,611 | 28,648 |

Full audit saved to: `db_insights/DATABASE_SYMBOL_AUDIT_20260105.md`

### Key Findings

1. **21 FX pairs duplicated** between `fx_spot_1d` AND `fred_observations_1d`
   - DEXBZUS, DEXCHUS, DTWEXBGS, etc. - all FRED series
   - Should NOT be duplicated in fx_spot_1d

2. **Missing UNIQUE constraints** on core tables:
   - `raw.fx_spot_1d` - NO constraint
   - `raw.market_futures_1d` - NO constraint

3. **Source separation clarity:**
   - FRED FX → belongs in `fred_observations_1d` only
   - Yahoo FX → belongs in `fx_spot_1d` (EURUSD, GBPUSD, etc.)

### Database Changes Executed (2026-01-05)

**CHANGE 1: Delete FRED-sourced rows from fx_spot_1d**
```
Rows before: 211,752
Rows deleted: 139,617 (21 FRED pairs)
Rows after: 72,135 (9 Yahoo pairs only)
Remaining: AUDUSD, EURUSD, GBPUSD, NZDUSD, USDBRL, USDCAD, USDCHF, USDCNY, USDJPY
```

**CHANGE 2: Add UNIQUE constraint to market_futures_1d**
```sql
ALTER TABLE raw.market_futures_1d 
ADD CONSTRAINT market_futures_1d_symbol_date_uq 
UNIQUE (symbol, as_of_date);
```

**CHANGE 3: Add UNIQUE constraint to fx_spot_1d**
```sql
ALTER TABLE raw.fx_spot_1d 
ADD CONSTRAINT fx_spot_1d_pair_date_uq 
UNIQUE (pair, as_of_date);
```

### Verification Results

| Check | Result |
|-------|--------|
| fx_spot_1d rows | 72,135 ✅ |
| fx_spot_1d pairs | 9 (Yahoo only) ✅ |
| fx_spot_1d UNIQUE | `fx_spot_1d_pair_date_uq` ✅ |
| market_futures_1d UNIQUE | `market_futures_1d_symbol_date_uq` ✅ |
| FX/FRED overlap | 0 ✅ |

### Architecture Notes

**Minimal Change Approach Adopted:**
- No new schemas created
- No metadata layer (deferred)
- No data movement between schemas
- Just cleanup + constraints

**Databento Source Update:**
- Subscription expired - no longer available
- 1h data (2010-2025) is frozen
- Need alternative source for daily updates (Yahoo, Barchart, etc.)

**1h Data Column:** `ts_event` is Databento's naming convention
- `ts_event` = market event timestamp
- `ts_recv` = network receive timestamp (not present)
- Good naming - unambiguous

**Separation of Concerns (Final State):**
- Yahoo FX → `raw.fx_spot_1d` (9 pairs)
- FRED FX → `raw.fred_observations_1d` (21 DEX*/DTW* series)
- Futures → `raw.market_futures_1d` (87 symbols, now with uniqueness)

### What Was NOT Changed

- No metadata schema created (deferred - minimal approach)
- No instrument_id/source_id columns added
- No silver layer implemented
- No COT soft commodity backfill (CC, CT, KC, MWE)

---

*Last Updated: 2026-01-05 (Session 4 - DB Cleanup & Constraints)*
*Operating Mode: Accuracy > Speed. Always.*
