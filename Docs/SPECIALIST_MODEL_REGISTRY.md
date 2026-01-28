NOTE: Production is the dashboard/frontend, not the repo root.
# ZINC-FUSION-V15: Specialist Model Registry (v3 Architecture)

> **CRITICAL**: Each specialist has a UNIQUE, CUSTOM model architecture.
> These are NOT generic AutoGluon fits. Do NOT confuse with the L0 OOF training pipeline.

## Architecture Shift (v2 → v3)

| Version | Design | Count |
|---------|--------|-------|
| **v2** | 44 specialist models (11 buckets × 4 horizons) producing forecasts | 44 |
| **v3** | 11 signal generators producing compact signals fed to Core | 11 |

**Key Change**: Specialists are now **signal generators**, not forecasters. The Core model owns all horizon forecasting.
Specialists are **unaffected** by the Core CPU-only policy.

---

## The Big 11 Specialists - Model Types

| Specialist | Class | File | Model Type | Architecture |
|------------|-------|------|------------|---------------|
| **crush** | `CrushSignalGenerator` | `xgb_signals.py` | `xgb` | XGBRegressor |
| **china** | `ChinaSignalGenerator` | `xgb_signals.py` | `gbm` | GradientBoostingRegressor |
| **substitutes** | `SubstitutesSignalGenerator` | `xgb_signals.py` | `rf` | RandomForestRegressor |
| **fx** | `FxSignalGenerator` | `ardl_signals.py` | `ardl` | statsmodels ARDL |
| **fed** | `FedSignalGenerator` | `ardl_signals.py` | `ridge` | Weighted z-score composite (ridge-style) |
| **volatility** | `VolatilitySignalGenerator` | `garch_signals.py` | `garch` | GJR-GARCH(1,1) Student-t |
| **energy** | `EnergySignalGenerator` | `var_signals.py` | `var` | statsmodels VAR + IRF |
| **palm** | `PalmSignalGenerator` | `ecm_signals.py` | `ecm` | ECM cointegration + Ridge |
| **tariff** | `TariffSignalGenerator` | `event_signals.py` | `tree` | Rules-based (EPU thresholds) |
| **biofuel** | `BiofuelSignalGenerator` | `event_signals.py` | `nlp_ema` | EMA-smoothed RIN/LCFS/margin proxy |
| **trump_effect** | `TrumpEffectSignalGenerator` | `event_signals.py` | `event_study` | Event study + EPU decomposition + proxy composites |

---

## Signal Flow Architecture

```
                    SPECIALIST SIGNAL GENERATORS
                    (11 unique model architectures)
                              │
                              ▼
              ┌───────────────────────────────────┐
              │   training.specialist_signals_1d   │
              │   (signal_1, signal_2, confidence) │
              └───────────────────────────────────┘
                              │
                              ▼
              ┌───────────────────────────────────┐
              │       training.matrix_1d          │
              │   (Core features + specialist     │
              │    signals as input columns)      │
              └───────────────────────────────────┘
                              │
                              ▼
              ┌───────────────────────────────────┐
              │     L0 Core + L1 Meta Models      │
              │   (horizon-specific forecasting)  │
              └───────────────────────────────────┘
```

---

## Implementation Details by Group

### Group A: Tree-Based ML (xgb_signals.py)

**CRUSH** - XGBoost Regressor
- Purpose: Margin-driven production incentives
- Signal 1: Model prediction of forward ZL return
- Signal 2: 21-day crush momentum
- Features:
  - `crush_zscore`: Board crush z-score (CME formula, 126d window)
  - `oil_share_zscore`: Oil share of crush value (126d window)
  - `crush_margin_regime`: Categorical regime (-2=very_low to +2=very_high) *(NEW Jan 2026)*
  - WASDE fundamentals (ending stocks, crush volume, exports)
- Data Source: `analytics.board_crush_1d` (pre-calculated) or computed from ZS/ZL/ZM
- Persistence: `models/specialists/crush/model.joblib`

**CHINA** - GradientBoostingRegressor
- Purpose: Demand shifts and shipment intensity
- Signal 1: Model prediction of forward ZL return
- Signal 2: Brazil competition signal (BRL weakness)
- Features: Copper z-score (demand proxy), CNY, BRL, shipping indices
- Persistence: `models/specialists/china/model.joblib`

**SUBSTITUTES** - RandomForestRegressor
- Purpose: Switching behavior among soft oils
- Signal 1: Model prediction of forward ZL return
- Signal 2: ZL richness score vs substitutes
- Features: Spread/ratio z-scores vs canola, palm, sunflower
- Persistence: `models/specialists/substitutes/model.joblib`

### Group B: Econometric Models

**FX** - ARDL (ardl_signals.py)
- Purpose: Currency pressure on export competitiveness
- Signal 1: FX pressure index (ARDL-based)
- Signal 2: Carry trade signal (interest rate differentials)
- Features: DXY, BRL/USD, CNY/USD, MXN/USD, carry trade rates
- Model: Autoregressive Distributed Lag with optimal lag selection
- Persistence: `models/specialists/fx/ardl_model.joblib`

**FED** - Weighted Z-Score Composite (ardl_signals.py)
- Purpose: Macro rate regime influence
- Signal 1: Rates regime score
- Signal 2: Regime change momentum
- Features: Fed Funds, DGS10, DGS2 (curve), DGS3MO (short end), T10YIE (breakeven if available), NFCI
- Model: Weighted z-score composite (ridge-style), no fitted estimator

**ENERGY** - VAR with IRF (var_signals.py)
- Purpose: Spillovers from energy complex
- Signal 1: Energy spillover score (IRF-based)
- Signal 2: Spillover momentum
- Features: CL (crude), HO (heating oil), RB (gasoline), 3-2-1 crack
- Model: Vector Autoregression with Impulse Response Functions
- Persistence: `models/specialists/energy/var_model.joblib`

**PALM** - ECM + Ridge (ecm_signals.py)
- Purpose: Substitution pressure from FCPO
- Signal 1: Model prediction based on ECM features
- Signal 2: Mean reversion speed (half-life proxy)
- Features: Palm-soy spread, cointegration residuals, FX conversion
- Model: Error Correction Model for cointegration + Ridge for prediction
- Persistence: `models/specialists/palm/model.joblib`

### Group C: Volatility Models

**VOLATILITY** - GJR-GARCH (garch_signals.py)
- Purpose: Regime risk and variance shifts
- Signal 1: Volatility regime level (0-3: low/normal/high/crisis)
- Signal 2: Regime shift probability
- Features:
  - ZL realized volatility (21-day rolling, annualized)
  - VIX spot (30-day implied)
  - `vix_term_slope`: VIX - VIX3M (positive = backwardation = fear)
  - `vix_term_slope_normalized`: (VIX3M - VIX) / VIX *(NEW Jan 2026)*
  - OVX (oil volatility), GVZ (gold volatility)
  - VVIX (vol of vol)
- Backwardation Detection: VIX > VIX3M triggers crisis regime boost
- Model: GJR-GARCH(1,1) with Student-t errors (asymmetric volatility)
- Lookback: 504 days (2 years) for GARCH stability

### Group D: Event-Based Models (event_signals.py)

**TARIFF** - Rules-based
- Purpose: Discrete policy shocks on trade flows
- Signal 1: Combined tariff risk (EPU + deadline risk)
- Signal 2: EPU spike indicator (event detection)
- Features:
  - EPU indices (USEPUINDXM, EPUTRADE, EMVTRADEPOLEMV)
  - `deadline_risk_score`: Sigmoid-based urgency (accelerates at 90 days) *(NEW Jan 2026)*
  - `deadline_vol_multiplier`: Volatility adjustment (1.0-1.5) *(NEW Jan 2026)*
  - `min_days_to_deadline`: Days until nearest policy expiration
  - Tariff regime (pre-war/active/phase-one/trump-2.0)
- Data Source: `alt.tariff_deadlines` for policy expiration dates
- Key Deadlines: Nov 10, 2026 (Section 301), Dec 31, 2026 (China ag)
- Model: Rule-based on EPU thresholds + deadline risk + event intensity

**BIOFUEL** - EMA Smoothed Policy Proxy
- Purpose: Regulatory demand shifts (RFS, 45Z, CI scoring)
- Signal 1: Policy pressure score (RIN z-score or margin proxy)
- Signal 2: RIN momentum (fast vs slow EMA)
- Features: RIN D4/D6 prices, LCFS credits, biodiesel margin
- Model: EMA-smoothed price signals + policy regime detection (no NLP)

**TRUMP_EFFECT** - Event Study
- Purpose: Trade/rhetoric risk premium
- Signal 1: Event intensity (trade tension + China exposure)
- Signal 2: Trade uncertainty share (trade EPU / total EPU)
- Features: EPU indices, FXI (China ETF), VIX
- Model: Event study methodology with EPU decomposition + regime amplification (no sentiment model)

---

## Signal Contract (All Specialists)

```python
@dataclass
class SignalOutput:
    as_of_date: date        # Date for which signal is computed
    bucket: str             # Specialist bucket name
    signal_1: float         # Primary signal (REQUIRED)
    signal_2: float | None  # Secondary signal (optional)
    confidence: float | None # Model confidence 0-1 (optional)
    model_type: str         # Model class (xgb, garch, ecm, etc.)
```

**Rules**:
- Signals are **horizon-agnostic** (Core owns horizons: 5d, 21d, 63d, 126d)
- No decision semantics (no buy/sell outputs)
- All signals normalized to comparable scales (typically z-scores or 0-1)

---

## Trained Model Artifacts

```
models/specialists/
├── crush/
│   ├── model.joblib
│   ├── scaler.joblib
│   └── metadata.joblib
├── china/
│   ├── model.joblib
│   ├── scaler.joblib
│   └── metadata.joblib
├── substitutes/
│   ├── model.joblib
│   ├── scaler.joblib
│   └── metadata.joblib
├── palm/
│   ├── model.joblib
│   ├── scaler.joblib
│   └── metadata.joblib
├── fx/ardl_model.joblib
├── energy/var_model.joblib
└── (volatility, tariff, biofuel, trump_effect persist no model artifacts)
```

---

## DO NOT CONFUSE WITH

| This | Is NOT |
|------|--------|
| Specialist signal generators | AutoGluon TabularPredictor fits |
| Signal outputs (signal_1, signal_2) | Multi-horizon forecasts |
| `src/fusion/specialists/` code | `scripts/v2_training/train_l0_specialist.py` |
| Custom domain models (ARDL, GARCH, VAR) | Generic ML models |

---

## Code Locations

| Component | Location |
|-----------|----------|
| Signal generator code | `src/fusion/specialists/` |
| Base classes & contracts | `src/fusion/specialists/base.py` |
| Generator registry | `src/fusion/specialists/__init__.py` |
| Trained model artifacts | `models/specialists/{bucket}/` |
| Signal storage (Prisma) | `training.specialist_signals_1d` |

---

*Last updated: 2026-01-24*
*Verified from actual implementation code*