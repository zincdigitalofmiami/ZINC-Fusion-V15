# Core Model Refactor - Quick Reference Guide
## File-by-File Action Checklist

This document provides the EXACT file paths and line numbers to change for the Core model refactor.

---

## Layer 1: Training Layer ✅ NO CHANGES NEEDED

### Current State: CORRECT
- **File:** `src/fusion/core_training/config.py`
- **Line 31:** `QUANTILES = [0.3, 0.5, 0.7]` ✅
- **Status:** Already trains P30/P50/P70 correctly

### No Action Required
The training layer is already configured correctly. P30/P50/P70 are the trained quantiles.

---

## Layer 2: Calibration Layer 🔴 NEW FILES REQUIRED

### Files to Create

**1. `src/fusion/calibration/__init__.py`**
```python
"""Tail calibration module for extending P30/P70 to P10/P90."""
from .tail_calibration import calibrate_tails, apply_calibration

__all__ = ['calibrate_tails', 'apply_calibration']
```

**2. `src/fusion/calibration/tail_calibration.py`**
```python
"""
Tail Calibration Algorithm
===========================

Computes P10 and P90 as calibrated extensions of P30 and P70 using
empirical coverage from out-of-fold predictions.

Algorithm:
1. Load OOF predictions (p30/p50/p70) from training.oof_core_1d
2. Load actual returns from mkt.futures_1d
3. Compute residuals: actual - p50
4. Fit tail distribution to residuals
5. Compute offsets: p10_offset = quantile(residuals, 0.10), p90_offset = quantile(residuals, 0.90)
6. Validate coverage: ~10% of actuals < (p30 + p10_offset), ~90% < (p70 + p90_offset)
7. Return calibration parameters
"""

from typing import Dict, Tuple
import pandas as pd
import numpy as np
from scipy import stats


def calibrate_tails(
    oof_df: pd.DataFrame,  # Columns: trade_date, p30, p50, p70, horizon_days
    actuals_df: pd.DataFrame,  # Columns: trade_date, actual_return
    horizon: int,
    target_coverage_p10: float = 0.10,
    target_coverage_p90: float = 0.90,
) -> Dict[str, float]:
    """
    Compute tail calibration offsets for given horizon.
    
    Returns:
        {
            'p10_offset': float,  # Offset from p30
            'p90_offset': float,  # Offset from p70
            'coverage_p10': float,  # Realized coverage
            'coverage_p90': float,  # Realized coverage
            'sample_size': int,
        }
    """
    # Merge OOF predictions with actuals
    merged = pd.merge(
        oof_df[oof_df['horizon_days'] == horizon],
        actuals_df,
        on='trade_date',
        how='inner'
    )
    
    if len(merged) < 100:
        raise ValueError(f"Insufficient data for calibration: {len(merged)} samples (need ≥100)")
    
    # Compute residuals
    residuals = merged['actual_return'] - merged['p50']
    
    # Empirical quantiles from residuals
    p10_offset = np.percentile(residuals, 10)
    p90_offset = np.percentile(residuals, 90)
    
    # Compute calibrated tails
    merged['p10_cal'] = merged['p30'] + p10_offset
    merged['p90_cal'] = merged['p70'] + p90_offset
    
    # Validate coverage
    coverage_p10 = (merged['actual_return'] < merged['p10_cal']).mean()
    coverage_p90 = (merged['actual_return'] < merged['p90_cal']).mean()
    
    return {
        'p10_offset': float(p10_offset),
        'p90_offset': float(p90_offset),
        'coverage_p10': float(coverage_p10),
        'coverage_p90': float(coverage_p90),
        'sample_size': len(merged),
    }


def apply_calibration(
    p30: float,
    p70: float,
    calib_params: Dict[str, float],
) -> Tuple[float, float]:
    """
    Apply calibration offsets to compute p10_cal and p90_cal.
    
    Returns:
        (p10_cal, p90_cal)
    """
    p10_cal = p30 + calib_params['p10_offset']
    p90_cal = p70 + calib_params['p90_offset']
    return p10_cal, p90_cal


def validate_monotonicity(p10_cal: float, p30: float, p50: float, p70: float, p90_cal: float) -> bool:
    """Validate quantile monotonicity: p10_cal ≤ p30 ≤ p50 ≤ p70 ≤ p90_cal."""
    if not (p10_cal <= p30 <= p50 <= p70 <= p90_cal):
        raise ValueError(f"Monotonicity violation: {p10_cal} {p30} {p50} {p70} {p90_cal}")
    return True
```

**3. `scripts/calibrate_tails.py`**
```python
#!/usr/bin/env python3
"""
Run tail calibration and persist to database.

Usage:
    python scripts/calibrate_tails.py --horizon 21
    python scripts/calibrate_tails.py --all
    python scripts/calibrate_tails.py --horizon 21 --dry-run
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import argparse
import logging
from datetime import datetime
import pandas as pd
from fusion.db.connection import DatabaseConnections
from fusion.calibration.tail_calibration import calibrate_tails

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

HORIZONS = [5, 21, 63, 126]


def load_oof_data(engine, horizon: int) -> pd.DataFrame:
    """Load OOF predictions for calibration."""
    query = """
        SELECT 
            trade_date,
            horizon_days,
            AVG(p30) as p30,
            AVG(p50) as p50,
            AVG(p70) as p70
        FROM training.oof_core_1d
        WHERE horizon_days = %s
        GROUP BY trade_date, horizon_days
        ORDER BY trade_date
    """
    return pd.read_sql(query, engine, params=(horizon,))


def load_actuals(engine) -> pd.DataFrame:
    """Load actual returns for validation."""
    query = """
        SELECT 
            event_date as trade_date,
            (close / LAG(close, 5) OVER (ORDER BY event_date) - 1) as actual_return_5d,
            (close / LAG(close, 21) OVER (ORDER BY event_date) - 1) as actual_return_21d,
            (close / LAG(close, 63) OVER (ORDER BY event_date) - 1) as actual_return_63d,
            (close / LAG(close, 126) OVER (ORDER BY event_date) - 1) as actual_return_126d
        FROM mkt.futures_1d
        WHERE symbol = 'ZL' AND close IS NOT NULL
        ORDER BY event_date
    """
    return pd.read_sql(query, engine)


def persist_calibration(conn, horizon: int, calib_params: dict, dry_run: bool = False):
    """Persist calibration parameters to database."""
    if dry_run:
        logger.info(f"[DRY RUN] Would persist: {calib_params}")
        return
    
    query = """
        INSERT INTO model.tail_calibration_params 
            (horizon_days, calibration_date, p10_offset, p90_offset, coverage_p10, coverage_p90, sample_size)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (horizon_days, calibration_date) 
        DO UPDATE SET
            p10_offset = EXCLUDED.p10_offset,
            p90_offset = EXCLUDED.p90_offset,
            coverage_p10 = EXCLUDED.coverage_p10,
            coverage_p90 = EXCLUDED.coverage_p90,
            sample_size = EXCLUDED.sample_size
    """
    with conn.cursor() as cur:
        cur.execute(query, (
            horizon,
            datetime.now().date(),
            calib_params['p10_offset'],
            calib_params['p90_offset'],
            calib_params['coverage_p10'],
            calib_params['coverage_p90'],
            calib_params['sample_size'],
        ))
    conn.commit()


def main():
    parser = argparse.ArgumentParser(description='Run tail calibration')
    parser.add_argument('--horizon', type=int, choices=[5, 21, 63, 126], help='Horizon to calibrate')
    parser.add_argument('--all', action='store_true', help='Calibrate all horizons')
    parser.add_argument('--dry-run', action='store_true', help='Dry run (no database writes)')
    args = parser.parse_args()
    
    horizons = HORIZONS if args.all else [args.horizon] if args.horizon else [21]
    
    db_conn = DatabaseConnections()
    engine = db_conn.get_read_engine()
    write_conn = db_conn.get_write_connection()
    
    try:
        actuals_df = load_actuals(engine)
        logger.info(f"Loaded {len(actuals_df)} actual return observations")
        
        for horizon in horizons:
            logger.info(f"\n{'='*60}")
            logger.info(f"Calibrating tails for horizon {horizon}d...")
            logger.info(f"{'='*60}")
            
            # Load OOF predictions
            oof_df = load_oof_data(engine, horizon)
            logger.info(f"  Loaded {len(oof_df)} OOF predictions")
            
            # Prepare actuals for this horizon
            actuals_h = actuals_df[['trade_date', f'actual_return_{horizon}d']].copy()
            actuals_h.columns = ['trade_date', 'actual_return']
            actuals_h = actuals_h.dropna()
            
            # Run calibration
            calib_params = calibrate_tails(oof_df, actuals_h, horizon)
            
            # Report results
            logger.info(f"\n  Calibration Results:")
            logger.info(f"    P10 offset: {calib_params['p10_offset']:+.6f}")
            logger.info(f"    P90 offset: {calib_params['p90_offset']:+.6f}")
            logger.info(f"    P10 coverage: {calib_params['coverage_p10']:.1%} (target: 10%)")
            logger.info(f"    P90 coverage: {calib_params['coverage_p90']:.1%} (target: 90%)")
            logger.info(f"    Sample size: {calib_params['sample_size']}")
            
            # Persist
            persist_calibration(write_conn, horizon, calib_params, dry_run=args.dry_run)
            
            if not args.dry_run:
                logger.info(f"  ✅ Calibration persisted to model.tail_calibration_params")
    
    finally:
        write_conn.close()


if __name__ == '__main__':
    main()
```

### Database Schema Changes

**File:** `prisma/schema.prisma`

**Add new model after `training.specialist_signals_1d` (around line 3133):**
```prisma
model tail_calibration_params {
  id                Int       @id @default(autoincrement())
  horizon_days      Int
  calibration_date  DateTime  @db.Date
  p10_offset        Decimal   @db.Decimal(10, 6)
  p90_offset        Decimal   @db.Decimal(10, 6)
  coverage_p10      Float
  coverage_p90      Float
  sample_size       Int
  created_at        DateTime  @default(now()) @db.Timestamp(6)
  
  @@unique([horizon_days, calibration_date])
  @@index([horizon_days])
  @@index([calibration_date])
  @@schema("model")
}
```

**Run migration:**
```bash
scripts/prisma.sh migrate dev --name add-tail-calibration-params
```

---

## Layer 3: Probability Layer 🔴 MODIFY EXISTING FILES

### File: `scripts/run_monte_carlo.py`

**Add after line 100 (after RiskMetrics dataclass):**
```python
def compute_zone_entry_probability(
    paths: np.ndarray,  # Shape: (N_SIMS, horizon_days)
    p30: float,
    p70: float,
) -> float:
    """
    Compute probability that any path enters [p30, p70] zone within horizon.
    
    Returns:
        Probability (0 to 1) that path enters zone at least once
    """
    # Check if ANY timestep in each path falls within [p30, p70]
    enters_zone = np.zeros(len(paths), dtype=bool)
    for i, path in enumerate(paths):
        enters_zone[i] = np.any((path >= p30) & (path <= p70))
    
    return float(enters_zone.mean())


def compute_tail_touch_probability(
    paths: np.ndarray,
    p10_cal: float,
    p90_cal: float,
) -> Tuple[float, float]:
    """
    Compute probability that path touches p10_cal or p90_cal tails.
    
    Returns:
        (prob_touch_p10, prob_touch_p90)
    """
    touch_p10 = np.any(paths <= p10_cal, axis=1).mean()
    touch_p90 = np.any(paths >= p90_cal, axis=1).mean()
    
    return float(touch_p10), float(touch_p90)
```

**Modify the main simulation loop (find around line 300-400):**

Look for where paths are generated and add after path simulation:
```python
# After: paths = simulate_monte_carlo_paths(...)

# Compute zone-entry probability
prob_enter_zone = compute_zone_entry_probability(paths, p30, p70)
prob_touch_p10, prob_touch_p90 = compute_tail_touch_probability(paths, p10_cal, p90_cal)

logger.info(f"  Probability enter [p30, p70]: {prob_enter_zone:.1%}")
logger.info(f"  Probability touch p10: {prob_touch_p10:.1%}")
logger.info(f"  Probability touch p90: {prob_touch_p90:.1%}")
```

**Modify database INSERT (find around line 500-600):**

Look for INSERT INTO forecasts.core_mc_1d and add new columns:
```python
query = """
    INSERT INTO forecasts.core_mc_1d (
        forecast_date, horizon_days, s0,
        p10, p50, p90,
        mu_annual, sigma_annual,
        mc_p10_final, mc_p50_final, mc_p90_final,
        mc_min_p10, mc_max_p90,
        opp, ruin,
        var_95, cvar_95,
        prob_enter_p30_p70_within_h,  -- NEW
        prob_touch_p10,                -- NEW
        prob_touch_p90,                -- NEW
        runs, seed
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (forecast_date, horizon_days) DO UPDATE SET ...
"""
```

### Database Schema Changes

**File:** `prisma/schema.prisma`

**Modify `forecasts.core_mc_1d` (lines 859-885):**
```prisma
model core_mc_1d {
  id            Int       @id @default(autoincrement())
  forecast_date DateTime  @db.Date
  horizon_days  Int
  s0            Float
  p10           Float
  p50           Float
  p90           Float
  mu_annual     Float?
  sigma_annual  Float?
  mc_p10_final  Float?
  mc_p50_final  Float?
  mc_p90_final  Float?
  mc_min_p10    Float?
  mc_max_p90    Float?
  opp           Float?
  ruin          Float?
  var_95        Float?
  cvar_95       Float?
  
  // NEW: Zone-entry probabilities
  prob_enter_p30_p70_within_h  Float?
  prob_touch_p10               Float?
  prob_touch_p90               Float?
  
  runs          Int?      @default(5000)
  seed          Int?
  created_at    DateTime? @default(now()) @db.Timestamp(6)

  @@unique([forecast_date, horizon_days])
  @@index([forecast_date], map: "idx_core_mc_forecast_date")
  @@index([prob_enter_p30_p70_within_h])  // NEW
  @@schema("forecasts")
}
```

**Run migration:**
```bash
scripts/prisma.sh migrate dev --name add-zone-entry-probabilities
```

---

## Layer 4: Serving/UI Contract 🔄 MODIFY EXISTING FILES

### File: `scripts/generate_production_forecasts.py`

**Add after `get_latest_oof_by_horizon()` function (around line 95):**
```python
def load_calibration_params(engine, horizon: int) -> dict:
    """Load latest calibration parameters for horizon."""
    query = """
        SELECT p10_offset, p90_offset, coverage_p10, coverage_p90
        FROM model.tail_calibration_params
        WHERE horizon_days = %s
        ORDER BY calibration_date DESC
        LIMIT 1
    """
    df = pd.read_sql(query, engine, params=(horizon,))
    if len(df) == 0:
        logger.warning(f"No calibration params found for horizon {horizon}d - using defaults")
        return {'p10_offset': -0.05, 'p90_offset': 0.05, 'coverage_p10': 0.10, 'coverage_p90': 0.90}
    return df.iloc[0].to_dict()


def get_latest_probabilities(engine, horizon: int) -> dict:
    """Fetch latest Monte Carlo probabilities for horizon."""
    query = """
        SELECT 
            prob_enter_p30_p70_within_h as prob_enter_zone,
            prob_touch_p10,
            prob_touch_p90
        FROM forecasts.core_mc_1d
        WHERE horizon_days = %s
        ORDER BY forecast_date DESC
        LIMIT 1
    """
    df = pd.read_sql(query, engine, params=(horizon,))
    if len(df) == 0:
        logger.warning(f"No MC probabilities found for horizon {horizon}d")
        return {'prob_enter_zone': None, 'prob_touch_p10': None, 'prob_touch_p90': None}
    return df.iloc[0].to_dict()
```

**Modify `upsert_production_forecast()` function (around line 97-130):**

Add calibration and probability loading:
```python
def upsert_production_forecast(conn, horizon: int, row: dict) -> bool:
    """Upsert a single forecast row into the production table."""
    
    # Load calibration parameters
    calib_params = load_calibration_params(conn, horizon)
    
    # Compute calibrated tails
    p10_cal = row['p30'] + calib_params['p10_offset']
    p90_cal = row['p70'] + calib_params['p90_offset']
    
    # Load probabilities
    probs = get_latest_probabilities(conn, horizon)
    
    # Validate monotonicity
    assert p10_cal <= row['p30'] <= row['p50'] <= row['p70'] <= p90_cal, \
        f"Monotonicity violation: {p10_cal} {row['p30']} {row['p50']} {row['p70']} {p90_cal}"
    
    query = """
        INSERT INTO forecasts.forecast_summary_1d (
            forecast_date, horizon_days,
            p10_cal, p30, p50, p70, p90_cal,
            prob_enter_zone,  -- NEW
            model_version
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (forecast_date, horizon_days) DO UPDATE SET
            p10_cal = EXCLUDED.p10_cal,
            p30 = EXCLUDED.p30,
            p50 = EXCLUDED.p50,
            p70 = EXCLUDED.p70,
            p90_cal = EXCLUDED.p90_cal,
            prob_enter_zone = EXCLUDED.prob_enter_zone
    """
    
    with conn.cursor() as cur:
        cur.execute(query, (
            row['trade_date'],
            horizon,
            float(p10_cal),
            float(row['p30']),
            float(row['p50']),
            float(row['p70']),
            float(p90_cal),
            probs['prob_enter_zone'],  # NEW
            'core-v3',
        ))
    conn.commit()
    return True
```

### Database Schema Changes

**File:** `prisma/schema.prisma`

**Modify `forecasts.forecast_summary_1d` (lines 902-929):**
```prisma
model forecast_summary_1d {
  id                Int       @id @default(autoincrement())
  forecast_date     DateTime  @db.Date
  horizon_days      Int
  opp               Float?
  ruin              Float?
  calibrated_p10    Float?    // DEPRECATED - use p10_cal
  calibrated_p90    Float?    // DEPRECATED - use p90_cal
  coverage_error    Float?
  regime            String?   @db.VarChar(20)
  regime_multiplier Float?    @default(1.0)
  narrative         String?
  top_driver_1      String?   @db.VarChar(50)
  top_driver_2      String?   @db.VarChar(50)
  top_driver_3      String?   @db.VarChar(50)
  model_version     String?   @db.VarChar(50)
  ai_model          String?   @db.VarChar(50)
  generated_at      DateTime? @default(now()) @db.Timestamp(6)
  p30               Float?
  p50               Float?
  p70               Float?
  p10_cal           Float?
  p90_cal           Float?
  prob_enter_zone   Float?    // NEW: Primary probability metric
  prob_touch_p10    Float?    // NEW: Downside tail risk
  prob_touch_p90    Float?    // NEW: Upside tail opportunity

  @@unique([forecast_date, horizon_days], map: "ai_decision_1d_forecast_date_horizon_days_key")
  @@index([forecast_date], map: "idx_ai_decision_forecast_date")
  @@index([prob_enter_zone])  // NEW
  @@schema("forecasts")
}
```

**Run migration:**
```bash
scripts/prisma.sh migrate dev --name add-probabilities-to-forecast-summary
```

### File: `src/fusion/api/server.py`

**Modify `/api/forecast/quantiles` endpoint (find around line 574-600):**

Change from:
```python
@app.get("/api/forecast/quantiles")
def forecast_quantiles(horizon: int = Query(21, ge=5, le=126)):
    rows = _fetch_rows("""
        SELECT forecast_date, p30, p50, p70
        FROM forecasts.forecast_summary_1d
        WHERE horizon_days = %s
        ORDER BY forecast_date DESC
        LIMIT 1
    """, [horizon])
    
    return {"quantiles": rows[0] if rows else None}
```

To:
```python
@app.get("/api/forecast/quantiles")
def forecast_quantiles(horizon: int = Query(21, ge=5, le=126)):
    rows = _fetch_rows("""
        SELECT 
            forecast_date,
            p10_cal,
            p30,
            p50,
            p70,
            p90_cal,
            prob_enter_zone,
            prob_touch_p10,
            prob_touch_p90
        FROM forecasts.forecast_summary_1d
        WHERE horizon_days = %s
        ORDER BY forecast_date DESC
        LIMIT 1
    """, [horizon])
    
    if not rows:
        return {"quantiles": None, "headline_probability": None}
    
    return {
        "quantiles": rows[0],
        "headline_probability": rows[0].get("prob_enter_zone"),
    }
```

---

## Summary: Files to Touch

### New Files (6)
1. `src/fusion/calibration/__init__.py`
2. `src/fusion/calibration/tail_calibration.py`
3. `scripts/calibrate_tails.py`
4. `CORE_MODEL_REFACTOR_SPEC.md` (this document)
5. `CORE_MODEL_REFACTOR_QUICK_REF.md` (this file)
6. `tests/test_core_refactor_integration.py` (validation)

### Modified Files (4)
1. `prisma/schema.prisma` - Add 3 models/columns
2. `scripts/run_monte_carlo.py` - Add zone-entry calculation
3. `scripts/generate_production_forecasts.py` - Add calibration application
4. `src/fusion/api/server.py` - Update forecast endpoints

### Migrations (3)
1. `add-tail-calibration-params`
2. `add-zone-entry-probabilities`
3. `add-probabilities-to-forecast-summary`

---

## Validation Commands

```bash
# 1. Run calibration
python scripts/calibrate_tails.py --horizon 21 --dry-run
python scripts/calibrate_tails.py --all

# 2. Run Monte Carlo with zone-entry
python scripts/run_monte_carlo.py --horizon 21

# 3. Generate forecasts with calibration
python scripts/generate_production_forecasts.py

# 4. Test API endpoint
curl http://localhost:8000/api/forecast/quantiles?horizon=21 | jq

# 5. Verify database
psql $DATABASE_URL -c "SELECT * FROM forecasts.forecast_summary_1d ORDER BY forecast_date DESC LIMIT 3;"
```

---

**Last Updated:** 2026-02-13  
**Quick Reference Version:** 1.0
