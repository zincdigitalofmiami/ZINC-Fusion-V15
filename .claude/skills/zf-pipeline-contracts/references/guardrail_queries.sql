-- =============================================================================
-- ZINC-Fusion-V15 Guardrail Queries
-- Run these BEFORE and AFTER any pipeline changes
-- =============================================================================

-- =============================================================================
-- 1. QUANTILE CROSSING VIOLATIONS
-- Must satisfy: p10 <= p50 <= p90
-- =============================================================================

-- Check core
SELECT 'oof_core_1d' AS table_name, as_of_date, horizon_steps, p10, p50, p90
FROM training.oof_core_1d
WHERE p10 > p50 OR p50 > p90
LIMIT 10;

-- Check all specialists
SELECT 'oof_crush_1d' AS table_name, as_of_date, horizon_steps, p10, p50, p90
FROM training.oof_crush_1d
WHERE p10 > p50 OR p50 > p90
LIMIT 10;

SELECT 'oof_china_1d' AS table_name, as_of_date, horizon_steps, p10, p50, p90
FROM training.oof_china_1d
WHERE p10 > p50 OR p50 > p90
LIMIT 10;

SELECT 'oof_fx_1d' AS table_name, as_of_date, horizon_steps, p10, p50, p90
FROM training.oof_fx_1d
WHERE p10 > p50 OR p50 > p90
LIMIT 10;

SELECT 'oof_fed_1d' AS table_name, as_of_date, horizon_steps, p10, p50, p90
FROM training.oof_fed_1d
WHERE p10 > p50 OR p50 > p90
LIMIT 10;

SELECT 'oof_tariff_1d' AS table_name, as_of_date, horizon_steps, p10, p50, p90
FROM training.oof_tariff_1d
WHERE p10 > p50 OR p50 > p90
LIMIT 10;

SELECT 'oof_energy_1d' AS table_name, as_of_date, horizon_steps, p10, p50, p90
FROM training.oof_energy_1d
WHERE p10 > p50 OR p50 > p90
LIMIT 10;

SELECT 'oof_biofuel_1d' AS table_name, as_of_date, horizon_steps, p10, p50, p90
FROM training.oof_biofuel_1d
WHERE p10 > p50 OR p50 > p90
LIMIT 10;

SELECT 'oof_palm_1d' AS table_name, as_of_date, horizon_steps, p10, p50, p90
FROM training.oof_palm_1d
WHERE p10 > p50 OR p50 > p90
LIMIT 10;

SELECT 'oof_volatility_1d' AS table_name, as_of_date, horizon_steps, p10, p50, p90
FROM training.oof_volatility_1d
WHERE p10 > p50 OR p50 > p90
LIMIT 10;

SELECT 'oof_substitutes_1d' AS table_name, as_of_date, horizon_steps, p10, p50, p90
FROM training.oof_substitutes_1d
WHERE p10 > p50 OR p50 > p90
LIMIT 10;


-- =============================================================================
-- 2. JOIN KEY UNIQUENESS (Duplicate Detection)
-- Each table must have unique (as_of_date, horizon_steps) pairs
-- =============================================================================

SELECT 'oof_core_1d' AS table_name, as_of_date, horizon_steps, COUNT(*) AS dupes
FROM training.oof_core_1d
GROUP BY as_of_date, horizon_steps
HAVING COUNT(*) > 1;

SELECT 'oof_crush_1d' AS table_name, as_of_date, horizon_steps, COUNT(*) AS dupes
FROM training.oof_crush_1d
GROUP BY as_of_date, horizon_steps
HAVING COUNT(*) > 1;

SELECT 'oof_china_1d' AS table_name, as_of_date, horizon_steps, COUNT(*) AS dupes
FROM training.oof_china_1d
GROUP BY as_of_date, horizon_steps
HAVING COUNT(*) > 1;

-- (Pattern repeats for all 11 OOF tables)


-- =============================================================================
-- 3. HORIZON ENCODING VIOLATIONS
-- Only valid values: 5, 21, 63, 126
-- =============================================================================

SELECT 'oof_core_1d' AS table_name, horizon_steps, COUNT(*) AS rows
FROM training.oof_core_1d
WHERE horizon_steps NOT IN (5, 21, 63, 126)
GROUP BY horizon_steps;

SELECT 'oof_crush_1d' AS table_name, horizon_steps, COUNT(*) AS rows
FROM training.oof_crush_1d
WHERE horizon_steps NOT IN (5, 21, 63, 126)
GROUP BY horizon_steps;

-- (Repeat for all specialists)


-- =============================================================================
-- 4. SCHEMA DRIFT DETECTION
-- Compare expected columns vs actual columns
-- =============================================================================

WITH expected_cols AS (
    SELECT column_name FROM (
        VALUES 
            ('as_of_date'),
            ('horizon_steps'),
            ('p10'),
            ('p50'),
            ('p90'),
            ('run_id'),
            ('created_at')
    ) AS t(column_name)
)
SELECT 
    'oof_core_1d' AS table_name,
    'MISSING' AS issue,
    e.column_name
FROM expected_cols e
WHERE e.column_name NOT IN (
    SELECT column_name 
    FROM information_schema.columns
    WHERE table_schema = 'training' AND table_name = 'oof_core_1d'
)
UNION ALL
SELECT 
    'oof_core_1d' AS table_name,
    'UNEXPECTED' AS issue,
    c.column_name
FROM information_schema.columns c
WHERE c.table_schema = 'training' 
  AND c.table_name = 'oof_core_1d'
  AND c.column_name NOT IN (SELECT column_name FROM expected_cols);


-- =============================================================================
-- 5. NULL CHECK (Required columns)
-- =============================================================================

SELECT 'oof_core_1d' AS table_name, 'as_of_date NULL' AS issue, COUNT(*) AS violations
FROM training.oof_core_1d WHERE as_of_date IS NULL
UNION ALL
SELECT 'oof_core_1d', 'horizon_steps NULL', COUNT(*)
FROM training.oof_core_1d WHERE horizon_steps IS NULL
UNION ALL
SELECT 'oof_core_1d', 'p10 NULL', COUNT(*)
FROM training.oof_core_1d WHERE p10 IS NULL
UNION ALL
SELECT 'oof_core_1d', 'p50 NULL', COUNT(*)
FROM training.oof_core_1d WHERE p50 IS NULL
UNION ALL
SELECT 'oof_core_1d', 'p90 NULL', COUNT(*)
FROM training.oof_core_1d WHERE p90 IS NULL;


-- =============================================================================
-- 6. DATE TYPE CHECK
-- as_of_date should be DATE, not TIMESTAMP (for _1d tables)
-- ts_event should be TIMESTAMP (for _1h tables)
-- =============================================================================

-- Check daily tables use DATE
SELECT table_schema, table_name, column_name, data_type
FROM information_schema.columns
WHERE column_name = 'as_of_date'
  AND table_schema IN ('training', 'curated', 'gold', 'features')
  AND data_type != 'DATE';

-- Check hourly tables use TIMESTAMP
SELECT table_schema, table_name, column_name, data_type
FROM information_schema.columns
WHERE column_name = 'ts_event'
  AND table_schema IN ('raw', 'features')
  AND data_type NOT LIKE '%TIMESTAMP%';


-- =============================================================================
-- 7. META-ENSEMBLE JOIN FANOUT CHECK
-- Verify 1:1 join ratio when building meta_ensemble
-- =============================================================================

WITH join_counts AS (
    SELECT 
        c.as_of_date,
        c.horizon_steps,
        COUNT(DISTINCT cr.as_of_date) AS crush_matches,
        COUNT(DISTINCT ch.as_of_date) AS china_matches
    FROM training.oof_core_1d c
    LEFT JOIN training.oof_crush_1d cr 
        ON c.as_of_date = cr.as_of_date AND c.horizon_steps = cr.horizon_steps
    LEFT JOIN training.oof_china_1d ch 
        ON c.as_of_date = ch.as_of_date AND c.horizon_steps = ch.horizon_steps
    GROUP BY c.as_of_date, c.horizon_steps
)
SELECT *
FROM join_counts
WHERE crush_matches != 1 OR china_matches != 1
LIMIT 10;


-- =============================================================================
-- 8. ROW COUNT CONSISTENCY
-- All OOF tables should have similar row counts per horizon
-- =============================================================================

SELECT 
    'Row counts by horizon' AS check_type,
    horizon_steps,
    (SELECT COUNT(*) FROM training.oof_core_1d WHERE horizon_steps = h.horizon_steps) AS core,
    (SELECT COUNT(*) FROM training.oof_crush_1d WHERE horizon_steps = h.horizon_steps) AS crush,
    (SELECT COUNT(*) FROM training.oof_china_1d WHERE horizon_steps = h.horizon_steps) AS china,
    (SELECT COUNT(*) FROM training.oof_fx_1d WHERE horizon_steps = h.horizon_steps) AS fx,
    (SELECT COUNT(*) FROM training.oof_fed_1d WHERE horizon_steps = h.horizon_steps) AS fed,
    (SELECT COUNT(*) FROM training.oof_tariff_1d WHERE horizon_steps = h.horizon_steps) AS tariff,
    (SELECT COUNT(*) FROM training.oof_energy_1d WHERE horizon_steps = h.horizon_steps) AS energy,
    (SELECT COUNT(*) FROM training.oof_biofuel_1d WHERE horizon_steps = h.horizon_steps) AS biofuel,
    (SELECT COUNT(*) FROM training.oof_palm_1d WHERE horizon_steps = h.horizon_steps) AS palm,
    (SELECT COUNT(*) FROM training.oof_volatility_1d WHERE horizon_steps = h.horizon_steps) AS volatility,
    (SELECT COUNT(*) FROM training.oof_substitutes_1d WHERE horizon_steps = h.horizon_steps) AS substitutes
FROM (SELECT DISTINCT horizon_steps FROM training.oof_core_1d) h
ORDER BY horizon_steps;


-- =============================================================================
-- 9. HOURLY DATA COVERAGE CHECK
-- Verify hourly data has expected bar counts
-- =============================================================================

SELECT 
    DATE_TRUNC('day', ts_event) AS trade_date,
    symbol,
    COUNT(*) AS hourly_bars,
    MIN(EXTRACT(HOUR FROM ts_event)) AS first_hour,
    MAX(EXTRACT(HOUR FROM ts_event)) AS last_hour
FROM raw.market_futures_1h
WHERE ts_event >= CURRENT_DATE - INTERVAL '7 days'
GROUP BY 1, 2
HAVING COUNT(*) < 6  -- Less than 6 hours = suspicious gap
ORDER BY 1 DESC, 2;


-- =============================================================================
-- 10. SENTIMENT SPECIALIST COVERAGE
-- All 11 specialists should have sentiment features
-- =============================================================================

SELECT
    specialist,
    COUNT(*) AS days_with_sentiment,
    MIN(as_of_date) AS first_date,
    MAX(as_of_date) AS last_date
FROM features.sentiment_specialist_1d
GROUP BY specialist
ORDER BY specialist;

-- Check for missing specialists
SELECT s.specialist AS missing_specialist
FROM (VALUES ('crush'), ('china'), ('fx'), ('fed'), ('tariff'),
             ('energy'), ('biofuel'), ('palm'), ('volatility'), ('substitutes'),
             ('trump_effect')
     ) AS s(specialist)
LEFT JOIN (
    SELECT DISTINCT specialist FROM features.sentiment_specialist_1d
) f ON s.specialist = f.specialist
WHERE f.specialist IS NULL;
