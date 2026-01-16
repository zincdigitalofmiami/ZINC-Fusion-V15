-- Migration: Quantile Schema Cleanup
-- Date: 2026-01-15
-- Purpose: Remove legacy p10/p90 columns, keep only SoT v2 quantiles
--          Primary: p30/p50/p70
--          Calibrated: p10_cal/p90_cal
--
-- SAFE TO RUN: All affected tables are empty (0 rows)

-- =============================================================================
-- 1. DROP LEGACY COLUMNS FROM model.oof_predictions
-- =============================================================================
ALTER TABLE model.oof_predictions DROP COLUMN IF EXISTS pred_p10;
ALTER TABLE model.oof_predictions DROP COLUMN IF EXISTS pred_p90;

-- =============================================================================
-- 2. DROP AND RECREATE VIEW WITH CORRECT COLUMNS
-- =============================================================================
DROP VIEW IF EXISTS model.v_oof_predictions;

CREATE VIEW model.v_oof_predictions AS
SELECT
    specialist,
    horizon,
    as_of_date,
    symbol,
    pred_p30,
    pred_p50,
    pred_p70,
    pred_p10_cal,
    pred_p90_cal,
    actual,
    actual - pred_p50 AS error,
    abs(actual - pred_p50) AS abs_error,
    CASE
        WHEN actual >= pred_p10_cal AND actual <= pred_p90_cal THEN true
        ELSE false
    END AS in_calibrated_band,
    fold_id,
    created_at
FROM model.oof_predictions
ORDER BY as_of_date DESC;

-- =============================================================================
-- 3. DROP LEGACY COLUMNS FROM ops.prediction_accuracy
-- =============================================================================
ALTER TABLE ops.prediction_accuracy DROP COLUMN IF EXISTS pred_p10;
ALTER TABLE ops.prediction_accuracy DROP COLUMN IF EXISTS pred_p90;

-- Add new columns to ops.prediction_accuracy if needed
ALTER TABLE ops.prediction_accuracy ADD COLUMN IF NOT EXISTS pred_p30 NUMERIC;
ALTER TABLE ops.prediction_accuracy ADD COLUMN IF NOT EXISTS pred_p70 NUMERIC;
ALTER TABLE ops.prediction_accuracy ADD COLUMN IF NOT EXISTS pred_p10_cal NUMERIC;
ALTER TABLE ops.prediction_accuracy ADD COLUMN IF NOT EXISTS pred_p90_cal NUMERIC;

-- =============================================================================
-- 4. CREATE model.forecast_metrics TABLE FOR EVALUATION METRICS
-- =============================================================================
CREATE TABLE IF NOT EXISTS model.forecast_metrics (
    id SERIAL PRIMARY KEY,
    horizon INTEGER NOT NULL,              -- 5, 21, 63, 126
    model_version VARCHAR(50),
    trained_at TIMESTAMPTZ,

    -- Median-optimizing metrics (robust to outliers)
    mae NUMERIC(12,6),                     -- Mean Absolute Error
    mase NUMERIC(12,6),                    -- Mean Absolute Scaled Error
    wape NUMERIC(12,6),                    -- Weighted Absolute Percentage Error

    -- Mean-optimizing metrics (penalizes large errors)
    mse NUMERIC(12,6),                     -- Mean Squared Error
    rmse NUMERIC(12,6),                    -- Root Mean Squared Error
    rmsse NUMERIC(12,6),                   -- Root Mean Squared Scaled Error

    -- Probabilistic metrics
    wql NUMERIC(12,6),                     -- Weighted Quantile Loss (primary)

    -- Coverage metrics
    coverage_80 NUMERIC(5,4),              -- % of actuals within P10_cal/P90_cal
    coverage_40 NUMERIC(5,4),              -- % of actuals within P30/P70

    created_at TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT uq_forecast_metrics UNIQUE (horizon, model_version)
);

CREATE INDEX IF NOT EXISTS idx_forecast_metrics_horizon ON model.forecast_metrics(horizon);
CREATE INDEX IF NOT EXISTS idx_forecast_metrics_trained ON model.forecast_metrics(trained_at DESC);

-- =============================================================================
-- 5. VERIFY FINAL SCHEMA
-- =============================================================================
-- Run this after migration to confirm:
-- SELECT column_name FROM information_schema.columns
-- WHERE table_schema = 'model' AND table_name = 'oof_predictions'
-- ORDER BY ordinal_position;
--
-- Expected columns:
--   id, specialist, horizon, as_of_date, symbol,
--   pred_p30, pred_p50, pred_p70, pred_p10_cal, pred_p90_cal,
--   actual, fold_id, created_at, model_version
