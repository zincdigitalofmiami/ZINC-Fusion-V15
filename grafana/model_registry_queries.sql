-- ============================================================================
-- ZINC-FUSION-V15: Grafana Dashboard Queries for Model Registry
-- ============================================================================
-- These queries are designed for Grafana PostgreSQL data source
-- Copy/paste into Grafana panels as needed
-- ============================================================================

-- ============================================================================
-- 1. MODEL REGISTRY OVERVIEW
-- ============================================================================

-- Panel: Model Status Overview (Stat/Gauge)
-- Shows count of models by status
SELECT
    status,
    COUNT(*) as count
FROM model.model_registry
GROUP BY status
ORDER BY count DESC;

-- Panel: Champion Models Table
SELECT
    model_name as "Model",
    horizon as "Horizon",
    ROUND(mase::numeric, 4) as "MASE",
    best_model as "Best Algorithm",
    trained_at as "Trained At"
FROM model.model_registry
WHERE is_champion = TRUE
ORDER BY horizon;

-- Panel: All Models Table
SELECT
    model_id as "Model ID",
    model_type as "Type",
    horizon as "Horizon",
    ROUND(mase::numeric, 4) as "MASE",
    status as "Status",
    CASE WHEN is_champion THEN '🏆' ELSE '' END as "Champion",
    trained_at as "Last Trained"
FROM model.model_registry
ORDER BY model_type, horizon;

-- ============================================================================
-- 2. DATA FRESHNESS DASHBOARD
-- ============================================================================

-- Panel: Data Source Freshness (Table with status colors)
-- Use value mappings: <24h=green, 24-48h=yellow, >48h=red
SELECT
    source as "Data Source",
    total_rows as "Rows",
    ROUND(hours_since_update::numeric, 1) as "Hours Since Update",
    to_char(last_update, 'YYYY-MM-DD HH24:MI') as "Last Update",
    CASE
        WHEN hours_since_update < 24 THEN 'OK'
        WHEN hours_since_update < 48 THEN 'Warning'
        ELSE 'Stale'
    END as "Status"
FROM ops.data_quality_metrics
WHERE as_of_date = CURRENT_DATE
ORDER BY hours_since_update DESC;

-- Panel: Data Freshness Gauge (for single source)
-- Replace 'Market Futures (1H)' with desired source
SELECT
    hours_since_update as "Hours"
FROM ops.data_quality_metrics
WHERE as_of_date = CURRENT_DATE
  AND source = 'Market Futures (1H)';

-- ============================================================================
-- 3. MODEL PERFORMANCE TRACKING
-- ============================================================================

-- Panel: MASE by Horizon (Bar Chart)
SELECT
    horizon || 'd' as "Horizon",
    ROUND(mase::numeric, 4) as "MASE"
FROM model.model_registry
WHERE is_champion = TRUE AND mase IS NOT NULL
ORDER BY horizon;

-- Panel: MASE History Over Time (Time Series)
-- Use for tracking model improvement
SELECT
    train_date as time,
    horizon || 'd' as metric,
    best_mase as "MASE"
FROM model.v_mase_history
WHERE train_date > NOW() - INTERVAL '90 days'
ORDER BY train_date;

-- Panel: Training Runs Timeline (Table)
SELECT
    run_name as "Run",
    model_type as "Type",
    horizon || 'd' as "Horizon",
    status as "Status",
    ROUND(duration_seconds::numeric / 60, 1) as "Duration (min)",
    ROUND(mase::numeric, 4) as "MASE",
    started_at as "Started"
FROM ops.training_runs
ORDER BY started_at DESC
LIMIT 20;

-- ============================================================================
-- 4. PREDICTION ACCURACY (when populated)
-- ============================================================================

-- Panel: 80% Coverage Rate by Model
SELECT
    model_id as "Model",
    horizon || 'd' as "Horizon",
    ROUND(coverage_80_pct::numeric, 1) as "80% Coverage %",
    prediction_count as "Predictions"
FROM model.v_accuracy_summary
ORDER BY coverage_80_pct DESC;

-- Panel: Prediction Error Distribution
SELECT
    model_id,
    horizon,
    prediction_date as time,
    abs_error as "Absolute Error"
FROM model.prediction_accuracy
WHERE prediction_date > NOW() - INTERVAL '30 days'
ORDER BY prediction_date;

-- ============================================================================
-- 5. OOF PREDICTIONS
-- ============================================================================

-- Panel: Latest OOF Predictions (Table)
-- Updated 2026-01-17: Use p30/p50/p70 OOF quantiles (no core prefix)
SELECT
    specialist as "Model",
    horizon || 'd' as "Horizon",
    as_of_date as "Target Date",
    ROUND(pred_p50::numeric, 2) as "P50",
    ROUND(pred_p30::numeric, 2) as "P30",
    ROUND(pred_p70::numeric, 2) as "P70",
    ROUND(actual::numeric, 2) as "Actual",
    ROUND(error::numeric, 2) as "Error",
    CASE
        WHEN actual >= pred_p30 AND actual <= pred_p70 THEN '✓'
        ELSE '✗'
    END as "In P30-P70 Band"
FROM model.v_oof_predictions
WHERE actual IS NOT NULL
ORDER BY as_of_date DESC
LIMIT 50;

-- Panel: OOF Coverage by Specialist
SELECT
    specialist as "Model",
    horizon || 'd' as "Horizon",
    COUNT(*) as "Predictions",
    SUM(CASE WHEN actual >= pred_p30 AND actual <= pred_p70 THEN 1 ELSE 0 END) as "In Band",
    ROUND(
        100.0 * SUM(CASE WHEN actual >= pred_p30 AND actual <= pred_p70 THEN 1 ELSE 0 END) / COUNT(*),
        1
    ) as "P30-P70 Coverage %"
FROM model.v_oof_predictions
WHERE actual IS NOT NULL
GROUP BY specialist, horizon
ORDER BY specialist, horizon;

-- ============================================================================
-- 6. SPECIALIST MODELS
-- ============================================================================

-- Panel: Specialist Model Status
SELECT
    REPLACE(model_id, 'zinc-fusion-specialist-', '') as "Specialist",
    status as "Status",
    ROUND(mase::numeric, 4) as "MASE",
    trained_at as "Last Trained"
FROM model.model_registry
WHERE model_type = 'specialist'
ORDER BY model_id;

-- ============================================================================
-- 7. SYSTEM HEALTH
-- ============================================================================

-- Panel: Row Counts by Data Source (for monitoring growth)
SELECT
    source as "Source",
    total_rows as "Rows"
FROM ops.data_quality_metrics
WHERE as_of_date = CURRENT_DATE
ORDER BY total_rows DESC;

-- Panel: Stale Data Sources Count (Stat)
SELECT
    COUNT(*) as "Stale Sources"
FROM ops.data_quality_metrics
WHERE as_of_date = CURRENT_DATE
  AND is_stale = TRUE;

-- Panel: Total Models Registered (Stat)
SELECT COUNT(*) as "Total Models"
FROM model.model_registry;

-- Panel: Production Models Count (Stat)
SELECT COUNT(*) as "Production Models"
FROM model.model_registry
WHERE status = 'production';

-- ============================================================================
-- 8. TRAINING ANALYTICS
-- ============================================================================

-- Panel: Average Training Time by Model Type
SELECT
    model_type as "Type",
    ROUND(AVG(training_time_seconds)::numeric / 60, 1) as "Avg Time (min)"
FROM model.model_registry
WHERE training_time_seconds IS NOT NULL
GROUP BY model_type;

-- Panel: Training Success Rate (last 30 days)
SELECT
    status as "Status",
    COUNT(*) as "Count"
FROM ops.training_runs
WHERE started_at > NOW() - INTERVAL '30 days'
GROUP BY status;

-- ============================================================================
-- GRAFANA VARIABLES (for dropdowns)
-- ============================================================================

-- Variable: $horizon
SELECT DISTINCT horizon || 'd' as __text, horizon as __value
FROM model.model_registry
WHERE horizon IS NOT NULL
ORDER BY horizon;

-- Variable: $model_type
SELECT DISTINCT model_type as __text, model_type as __value
FROM model.model_registry
ORDER BY model_type;

-- Variable: $data_source
SELECT DISTINCT source as __text, source as __value
FROM ops.data_quality_metrics
ORDER BY source;
