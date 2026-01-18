-- Restore model views from backup
-- Source: backup_pre_migration_20260118_114613.sql

-- Drop existing views if they exist (to allow re-running)
DROP VIEW IF EXISTS model.v_accuracy_summary CASCADE;
DROP VIEW IF EXISTS model.v_champions CASCADE;
DROP VIEW IF EXISTS model.v_data_freshness CASCADE;
DROP VIEW IF EXISTS model.v_latest_models CASCADE;
DROP VIEW IF EXISTS model.v_mase_history CASCADE;
DROP VIEW IF EXISTS model.v_oof_predictions CASCADE;
DROP VIEW IF EXISTS model.v_recent_runs CASCADE;

-- v_accuracy_summary: Aggregated prediction accuracy metrics by model and horizon
CREATE VIEW model.v_accuracy_summary AS
 SELECT model_id,
    horizon,
    count(*) AS prediction_count,
    avg(abs_error) AS avg_abs_error,
    avg(pct_error) AS avg_pct_error,
    (((sum(
        CASE
            WHEN in_80_band THEN 1
            ELSE 0
        END))::numeric / (count(*))::numeric) * (100)::numeric) AS coverage_80_pct,
    min(target_date) AS first_prediction,
    max(target_date) AS last_prediction
   FROM ops.prediction_accuracy
  GROUP BY model_id, horizon;

-- v_champions: Current champion models by horizon
CREATE VIEW model.v_champions AS
 SELECT model_id,
    model_name,
    model_type,
    horizon,
    version,
    trained_at,
    mase,
    best_model,
    training_time_seconds,
    dataset_rows
   FROM model.model_registry
  WHERE (is_champion = true)
  ORDER BY horizon;

-- v_data_freshness: Latest data quality status per source
CREATE VIEW model.v_data_freshness AS
 SELECT source,
    last_update,
    hours_since_update,
    completeness_pct,
    null_pct,
    is_stale,
    is_incomplete,
        CASE
            WHEN (is_stale OR is_incomplete) THEN 'warning'::text
            WHEN (hours_since_update > (24)::numeric) THEN 'stale'::text
            ELSE 'ok'::text
        END AS status
   FROM ops.data_quality_metrics
  WHERE (as_of_date = ( SELECT max(data_quality_metrics_1.as_of_date) AS max
           FROM ops.data_quality_metrics data_quality_metrics_1));

-- v_latest_models: Most recent model per type and horizon
CREATE VIEW model.v_latest_models AS
 SELECT DISTINCT ON (model_type, horizon) model_id,
    model_name,
    model_type,
    horizon,
    version,
    trained_at,
    mase,
    best_model,
    status,
    is_champion
   FROM model.model_registry
  ORDER BY model_type, horizon, trained_at DESC;

-- v_mase_history: Daily MASE trends by model type and horizon
CREATE VIEW model.v_mase_history AS
 SELECT date(trained_at) AS train_date,
    model_type,
    horizon,
    avg(mase) AS avg_mase,
    min(mase) AS best_mase,
    count(*) AS run_count
   FROM model.model_registry
  WHERE (mase IS NOT NULL)
  GROUP BY (date(trained_at)), model_type, horizon
  ORDER BY (date(trained_at)) DESC;

-- v_oof_predictions: Out-of-fold predictions with error metrics
CREATE VIEW model.v_oof_predictions AS
 SELECT specialist,
    horizon,
    as_of_date,
    symbol,
    pred_p30,
    pred_p50,
    pred_p70,
    pred_p10_cal,
    pred_p90_cal,
    actual,
    (actual - pred_p50) AS error,
    abs((actual - pred_p50)) AS abs_error,
        CASE
            WHEN ((actual >= pred_p10_cal) AND (actual <= pred_p90_cal)) THEN true
            ELSE false
        END AS in_calibrated_band,
    fold_id,
    created_at
   FROM model.oof_predictions
  ORDER BY as_of_date DESC;

-- v_recent_runs: Training runs from last 30 days
CREATE VIEW model.v_recent_runs AS
 SELECT run_id,
    run_name,
    model_type,
    specialist_name,
    horizon,
    started_at,
    completed_at,
    duration_seconds,
    status,
    mase,
    dataset_rows,
    training_mode
   FROM ops.training_runs
  WHERE (started_at > (now() - '30 days'::interval))
  ORDER BY started_at DESC;
