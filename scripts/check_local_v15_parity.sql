-- ZINC-FUSION-V15 local DB parity checks
-- Usage:
--   psql "$LOCAL_DATABASE_URL" -f scripts/check_local_v15_parity.sql

\echo '=== identity ==='
SELECT current_database() AS database_name, current_user AS db_user;

\echo '=== required tables ==='
SELECT rel_name, to_regclass(rel_name) AS regclass_name
FROM unnest(
  ARRAY[
    'forecasts.production_1d',
    'training.matrix_1d',
    'training.specialist_signals_1d',
    'training.oof_core_1d'
  ]::text[]
) AS rel_name
ORDER BY rel_name;

\echo '=== row counts ==='
SELECT 'forecasts.production_1d' AS table_name, COUNT(*)::bigint AS rows FROM forecasts.production_1d
UNION ALL
SELECT 'training.matrix_1d', COUNT(*)::bigint FROM training.matrix_1d
UNION ALL
SELECT 'training.specialist_signals_1d', COUNT(*)::bigint FROM training.specialist_signals_1d
UNION ALL
SELECT 'training.oof_core_1d', COUNT(*)::bigint FROM training.oof_core_1d
ORDER BY table_name;

\echo '=== freshness markers ==='
SELECT 'forecasts.production_1d.max_as_of_date' AS metric, COALESCE(MAX(as_of_date)::text, 'NULL') AS value
FROM forecasts.production_1d
UNION ALL
SELECT 'training.matrix_1d.max_trade_date', COALESCE(MAX(trade_date)::text, 'NULL')
FROM training.matrix_1d
UNION ALL
SELECT 'training.specialist_signals_1d.max_as_of_date', COALESCE(MAX(as_of_date)::text, 'NULL')
FROM training.specialist_signals_1d
UNION ALL
SELECT 'training.oof_core_1d.max_trade_date', COALESCE(MAX(trade_date)::text, 'NULL')
FROM training.oof_core_1d;

\echo '=== forecast horizon coverage ==='
SELECT horizon, COUNT(*)::bigint AS rows
FROM forecasts.production_1d
WHERE horizon IN (5, 21, 63, 126)
GROUP BY horizon
ORDER BY horizon;

\echo '=== model run provenance ==='
SELECT
  COUNT(*)::bigint AS total_rows,
  COUNT(*) FILTER (WHERE status = 'promoted')::bigint AS promoted_rows
FROM training.model_runs_event;
