# ZINC-FUSION-V15: SoT Schema Proposal
## Date: 2026-01-14
## Status: DRAFT - REQUIRES APPROVAL

---

## Executive Summary

This proposal updates the quantile system from P10/P50/P90 to **P30/P50/P70** for tighter operational bounds, with **calibrated P10_cal/P90_cal** for risk management. It also creates new Source-of-Truth (SoT) tables for:

1. Event probabilities
2. Price scenarios
3. Training matrices
4. Meta-learner inputs

---

## §1. QUANTILE SYSTEM CHANGE

### 1.1 Current State (P10/P50/P90)

```
P10 ─────────────────── P50 ─────────────────── P90
    Wide uncertainty band (80% interval)
    Good for risk management
    Too wide for procurement decisions
```

### 1.2 Proposed State (P30/P50/P70 + Calibrated)

```
P10_cal ──── P30 ────── P50 ────── P70 ──── P90_cal
  │           │          │          │         │
  │           └──── Operational Band ────┘    │
  │                  (40% interval)           │
  │              For Chris: BUY/WAIT          │
  └─────────── Risk Bounds (80%) ─────────────┘
              For Kevin: Extreme scenarios
```

**Rationale:**
- **P30/P70**: Tighter band (40% interval) = actionable procurement signals
- **P10_cal/P90_cal**: Conformally calibrated = guaranteed 80% coverage for risk

### 1.3 Column Changes

| Table | Current | Proposed |
|-------|---------|----------|
| `model.oof_predictions` | `pred_p10, pred_p50, pred_p90` | `pred_p30, pred_p50, pred_p70, pred_p10_cal, pred_p90_cal` |
| `model.meta_ensemble` | `p10, p50, p90` | `p30, p50, p70, p10_cal, p90_cal` |
| `forecasts.core_cone_1d` | `p10, p50, p90` | `p30, p50, p70, p10_cal, p90_cal` |
| `forecasts.forecast_quantiles` | `p10, p50, p90` | `p30, p50, p70, p10_cal, p90_cal` |
| `forecasts.ai_decision_1d` | `calibrated_p10, calibrated_p90` | `p10_cal, p90_cal` (rename only) |

---

## §2. NEW SoT TABLES

### 2.1 analytics.event_probabilities_1d

**Purpose:** Probability of specific market events occurring within forecast horizon.

```sql
CREATE TABLE analytics.event_probabilities_1d (
    id                  SERIAL PRIMARY KEY,
    as_of_date          DATE NOT NULL,
    horizon_days        INTEGER NOT NULL,  -- 5, 21, 63, 126
    
    -- Price movement probabilities
    prob_up_1pct        DECIMAL(5,4),  -- P(return > +1%)
    prob_up_3pct        DECIMAL(5,4),  -- P(return > +3%)
    prob_up_5pct        DECIMAL(5,4),  -- P(return > +5%)
    prob_down_1pct      DECIMAL(5,4),  -- P(return < -1%)
    prob_down_3pct      DECIMAL(5,4),  -- P(return < -3%)
    prob_down_5pct      DECIMAL(5,4),  -- P(return < -5%)
    
    -- Regime probabilities
    prob_high_vol       DECIMAL(5,4),  -- P(entering high vol regime)
    prob_trend_up       DECIMAL(5,4),  -- P(bullish trend)
    prob_trend_down     DECIMAL(5,4),  -- P(bearish trend)
    prob_range_bound    DECIMAL(5,4),  -- P(sideways)
    
    -- Derived from Monte Carlo
    mc_runs             INTEGER,
    confidence_level    DECIMAL(5,4),
    
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    model_version       TEXT,
    
    UNIQUE(as_of_date, horizon_days)
);

CREATE INDEX idx_event_prob_date ON analytics.event_probabilities_1d(as_of_date);
```

### 2.2 analytics.price_scenarios_1d

**Purpose:** Named price scenarios with probabilities for dashboard/Chris.

```sql
CREATE TABLE analytics.price_scenarios_1d (
    id                  SERIAL PRIMARY KEY,
    as_of_date          DATE NOT NULL,
    horizon_days        INTEGER NOT NULL,
    scenario_name       TEXT NOT NULL,  -- 'bull_breakout', 'bear_crash', 'base_case', etc.
    
    -- Scenario definition
    price_target        DECIMAL(10,4),
    price_low           DECIMAL(10,4),
    price_high          DECIMAL(10,4),
    expected_return_pct DECIMAL(8,4),
    
    -- Probability
    probability         DECIMAL(5,4),
    confidence          DECIMAL(5,4),
    
    -- Drivers
    primary_driver      TEXT,          -- 'china_demand', 'energy_rally', etc.
    driver_strength     DECIMAL(5,4),
    
    -- For UI
    display_order       INTEGER,
    color_code          TEXT,          -- '#22c55e' for bullish, '#ef4444' for bearish
    
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    
    UNIQUE(as_of_date, horizon_days, scenario_name)
);
```

### 2.3 training.core_matrix_1d

**Purpose:** Denormalized feature matrix for Core model training.

```sql
CREATE TABLE training.core_matrix_1d (
    id                  SERIAL PRIMARY KEY,
    as_of_date          DATE NOT NULL,
    
    -- Target (for each horizon)
    target_5d           DECIMAL(10,4),
    target_21d          DECIMAL(10,4),
    target_63d          DECIMAL(10,4),
    target_126d         DECIMAL(10,4),
    
    -- ZL price features
    zl_close            DECIMAL(10,4),
    zl_return_1d        DECIMAL(10,6),
    zl_return_5d        DECIMAL(10,6),
    zl_return_21d       DECIMAL(10,6),
    zl_vol_21d          DECIMAL(10,6),
    zl_vol_63d          DECIMAL(10,6),
    
    -- Soy complex
    zs_close            DECIMAL(10,4),
    zm_close            DECIMAL(10,4),
    board_crush         DECIMAL(10,4),
    oil_share           DECIMAL(10,6),
    
    -- Calendar features
    day_of_week         INTEGER,
    month               INTEGER,
    is_wasde_week       BOOLEAN,
    is_fomc_week        BOOLEAN,
    is_expiry_week      BOOLEAN,
    is_quarter_end      BOOLEAN,
    
    -- Regime indicators
    vol_regime          TEXT,          -- 'low', 'normal', 'high', 'crisis'
    trend_regime        TEXT,          -- 'up', 'down', 'sideways'
    
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    
    UNIQUE(as_of_date)
);

CREATE INDEX idx_core_matrix_date ON training.core_matrix_1d(as_of_date);
```

### 2.4 training.meta_inputs_5d (×4 horizons)

**Purpose:** Joined OOF predictions from all specialists for L1 meta-learner.

```sql
-- One table per horizon: meta_inputs_5d, meta_inputs_21d, meta_inputs_63d, meta_inputs_126d

CREATE TABLE training.meta_inputs_5d (
    id                  SERIAL PRIMARY KEY,
    as_of_date          DATE NOT NULL,
    
    -- Actuals
    actual_price        DECIMAL(10,4),
    actual_return       DECIMAL(10,6),
    
    -- Core OOF (3 quantiles)
    core_p30            DECIMAL(10,4),
    core_p50            DECIMAL(10,4),
    core_p70            DECIMAL(10,4),
    
    -- Specialist OOF (3 quantiles × 10 specialists = 30 columns)
    crush_p30           DECIMAL(10,4),
    crush_p50           DECIMAL(10,4),
    crush_p70           DECIMAL(10,4),
    
    china_p30           DECIMAL(10,4),
    china_p50           DECIMAL(10,4),
    china_p70           DECIMAL(10,4),
    
    fx_p30              DECIMAL(10,4),
    fx_p50              DECIMAL(10,4),
    fx_p70              DECIMAL(10,4),
    
    fed_p30             DECIMAL(10,4),
    fed_p50             DECIMAL(10,4),
    fed_p70             DECIMAL(10,4),
    
    tariff_p30          DECIMAL(10,4),
    tariff_p50          DECIMAL(10,4),
    tariff_p70          DECIMAL(10,4),
    
    energy_p30          DECIMAL(10,4),
    energy_p50          DECIMAL(10,4),
    energy_p70          DECIMAL(10,4),
    
    biofuel_p30         DECIMAL(10,4),
    biofuel_p50         DECIMAL(10,4),
    biofuel_p70         DECIMAL(10,4),
    
    palm_p30            DECIMAL(10,4),
    palm_p50            DECIMAL(10,4),
    palm_p70            DECIMAL(10,4),
    
    volatility_p30      DECIMAL(10,4),
    volatility_p50      DECIMAL(10,4),
    volatility_p70      DECIMAL(10,4),
    
    substitutes_p30     DECIMAL(10,4),
    substitutes_p50     DECIMAL(10,4),
    substitutes_p70     DECIMAL(10,4),
    
    trump_effect_p30    DECIMAL(10,4),
    trump_effect_p50    DECIMAL(10,4),
    trump_effect_p70    DECIMAL(10,4),
    
    -- Regime features (for regime-aware fusion)
    vol_regime          TEXT,
    trend_regime        TEXT,
    
    -- Metadata
    cv_fold             INTEGER,       -- Which fold this came from
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    
    UNIQUE(as_of_date, cv_fold)
);

CREATE INDEX idx_meta_inputs_5d_date ON training.meta_inputs_5d(as_of_date);

-- Repeat for 21d, 63d, 126d horizons
```

---

## §3. MIGRATION STRATEGY

### 3.1 Phase 1: Add New Columns (Non-Breaking)

```sql
-- Add new quantile columns alongside existing
ALTER TABLE model.oof_predictions 
    ADD COLUMN pred_p30 DECIMAL(10,4),
    ADD COLUMN pred_p70 DECIMAL(10,4),
    ADD COLUMN pred_p10_cal DECIMAL(10,4),
    ADD COLUMN pred_p90_cal DECIMAL(10,4);

-- Similar for other tables...
```

### 3.2 Phase 2: Create New Tables

```sql
-- Execute CREATE TABLE statements from §2
```

### 3.3 Phase 3: Update Training Code

```python
# Change quantile_levels in config
QUANTILE_LEVELS = [0.10, 0.30, 0.50, 0.70, 0.90]

# Training outputs P10/P30/P50/P70/P90
# P10/P90 go to calibration layer
# P30/P50/P70 are operational outputs
```

### 3.4 Phase 4: Backfill & Deprecate

```sql
-- After validation, drop old columns
ALTER TABLE model.oof_predictions 
    DROP COLUMN pred_p10,
    DROP COLUMN pred_p90;
```

---

## §4. IMPACT ANALYSIS

### 4.1 Tables Affected

| Table | Action | Risk |
|-------|--------|------|
| `model.oof_predictions` | Add columns, later drop | LOW - empty |
| `model.meta_ensemble` | Add columns | LOW - 3K rows |
| `forecasts.*` | Add columns | LOW - all empty |
| `model.model_registry` | Rename metrics | MEDIUM - 18 rows |

### 4.2 Code Changes Required

| File | Change |
|------|--------|
| `config/quantiles.py` | Update QUANTILE_LEVELS |
| `training/core_trainer.py` | Output new quantiles |
| `training/specialist_trainer.py` | Output new quantiles |
| `training/meta_trainer.py` | Consume 33→36 OOF columns |
| `inference/forecaster.py` | Output new schema |
| `dashboard/api.py` | Serve new fields |

### 4.3 Dashboard Impact

- **Chris (Procurement):** P30/P70 = tighter "Buying Zone"
- **Kevin (Sales):** P10_cal/P90_cal = extreme scenario bounds
- **UI:** Need to update cone visualization

---

## §5. APPROVAL CHECKLIST

- [ ] **Kirk**: Quantile change P10/P50/P90 → P30/P50/P70
- [ ] **Kirk**: New table `analytics.event_probabilities_1d`
- [ ] **Kirk**: New table `analytics.price_scenarios_1d`
- [ ] **Kirk**: New table `training.core_matrix_1d`
- [ ] **Kirk**: New tables `training.meta_inputs_{horizon}d` (×4)
- [ ] **Kirk**: Migration strategy (non-breaking first)

---

## §6. DDL SUMMARY

**New Tables (6):**
```
analytics.event_probabilities_1d
analytics.price_scenarios_1d
training.core_matrix_1d
training.meta_inputs_5d
training.meta_inputs_21d
training.meta_inputs_63d
training.meta_inputs_126d
```

**Altered Tables (6):**
```
model.oof_predictions      -- Add p30, p70, p10_cal, p90_cal
model.meta_ensemble        -- Add p30, p70, p10_cal, p90_cal
forecasts.core_cone_1d     -- Add p30, p70, p10_cal, p90_cal
forecasts.forecast_quantiles -- Add p30, p70, p10_cal, p90_cal
forecasts.core_mc_1d       -- Add p30, p70 variants
forecasts.ai_decision_1d   -- Rename calibrated_* to *_cal
```

---

*DRAFT - Awaiting Kirk approval before execution*
