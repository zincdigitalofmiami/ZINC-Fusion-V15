\set ON_ERROR_STOP on

-- Required V15 schema set (12 schemas)
DO $$
DECLARE
    missing_schemas text;
BEGIN
    SELECT string_agg(req.schema_name, ', ' ORDER BY req.schema_name)
    INTO missing_schemas
    FROM (
        VALUES
            ('mkt'),
            ('econ'),
            ('alt'),
            ('pos'),
            ('supply'),
            ('features'),
            ('training'),
            ('model'),
            ('forecasts'),
            ('analytics'),
            ('ops'),
            ('vegas')
    ) AS req(schema_name)
    WHERE NOT EXISTS (
        SELECT 1
        FROM information_schema.schemata s
        WHERE s.schema_name = req.schema_name
    );

    IF missing_schemas IS NOT NULL THEN
        RAISE EXCEPTION 'Missing required schemas: %', missing_schemas;
    END IF;
END
$$;

-- Required audit-critical tables
DO $$
DECLARE
    missing_tables text;
BEGIN
    SELECT string_agg(req.full_name, ', ' ORDER BY req.full_name)
    INTO missing_tables
    FROM (
        VALUES
            ('forecasts', 'production_1d', 'forecasts.production_1d'),
            ('training', 'matrix_1d', 'training.matrix_1d'),
            ('training', 'specialist_signals_1d', 'training.specialist_signals_1d'),
            ('training', 'oof_core_1d', 'training.oof_core_1d'),
            ('training', 'model_runs_event', 'training.model_runs_event')
    ) AS req(schema_name, table_name, full_name)
    WHERE NOT EXISTS (
        SELECT 1
        FROM information_schema.tables t
        WHERE t.table_schema = req.schema_name
          AND t.table_name = req.table_name
    );

    IF missing_tables IS NOT NULL THEN
        RAISE EXCEPTION 'Missing required tables: %', missing_tables;
    END IF;
END
$$;

-- Health snapshot for critical tables
SELECT
    'forecasts.production_1d' AS table_name,
    COUNT(*) AS row_count,
    MIN(forecast_date)::text AS min_date,
    MAX(forecast_date)::text AS max_date
FROM forecasts.production_1d
UNION ALL
SELECT
    'training.matrix_1d',
    COUNT(*),
    MIN(trade_date)::text,
    MAX(trade_date)::text
FROM training.matrix_1d
UNION ALL
SELECT
    'training.specialist_signals_1d',
    COUNT(*),
    MIN(as_of_date)::text,
    MAX(as_of_date)::text
FROM training.specialist_signals_1d
UNION ALL
SELECT
    'training.oof_core_1d',
    COUNT(*),
    MIN(trade_date)::text,
    MAX(trade_date)::text
FROM training.oof_core_1d
UNION ALL
SELECT
    'training.model_runs_event',
    COUNT(*),
    MIN(trained_date)::text,
    MAX(trained_date)::text
FROM training.model_runs_event
ORDER BY table_name;

-- Provenance guard: if OOF exists, model_runs_event must not be empty
DO $$
DECLARE
    oof_rows bigint;
    model_rows bigint;
BEGIN
    SELECT COUNT(*) INTO oof_rows FROM training.oof_core_1d;
    SELECT COUNT(*) INTO model_rows FROM training.model_runs_event;

    IF oof_rows > 0 AND model_rows = 0 THEN
        RAISE EXCEPTION
            'training.model_runs_event is empty while training.oof_core_1d has % rows; run scripts/backfill_model_runs_event.py',
            oof_rows;
    END IF;
END
$$;

-- Informational specialist bucket coverage (Big-11 expected when populated)
DO $$
DECLARE
    signal_rows bigint;
    bucket_count int;
BEGIN
    SELECT COUNT(*) INTO signal_rows FROM training.specialist_signals_1d;

    IF signal_rows > 0 THEN
        SELECT COUNT(DISTINCT bucket) INTO bucket_count
        FROM training.specialist_signals_1d;

        RAISE NOTICE 'specialist_signals_1d rows=% distinct_buckets=% (expected 11 buckets when fully populated)', signal_rows, bucket_count;
    END IF;
END
$$;
