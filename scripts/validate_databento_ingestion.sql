-- Databento Ingestion Validation Queries
-- Run these after databento-futures-daily and databento-statistics-daily functions execute
-- 
-- Acceptance tests that prove "Crush is unblocked":
-- 1. Coverage test (OI non-null)
-- 2. Consistency test (schema lock)
-- 3. Crush specialist preflight

-- =============================================================================
-- 1. COVERAGE TEST: Open Interest Non-Null (Last 60 Trading Days)
-- =============================================================================
-- Expected: ~100% coverage for ZL/ZS/ZM (once backfilled)

WITH trading_days AS (
  SELECT generate_series(
    CURRENT_DATE - INTERVAL '90 days',  -- 90 calendar days ≈ 60 trading days
    CURRENT_DATE - INTERVAL '1 day',
    '1 day'::interval
  )::date AS event_date
  WHERE EXTRACT(DOW FROM generate_series) NOT IN (0, 6)  -- Exclude weekends
),
crush_symbols AS (
  SELECT unnest(ARRAY['ZL', 'ZS', 'ZM']) AS symbol
)
SELECT 
  s.symbol,
  COUNT(DISTINCT td.event_date) AS total_trading_days,
  COUNT(DISTINCT f.event_date) FILTER (WHERE f.open_interest IS NOT NULL) AS days_with_oi,
  ROUND(
    100.0 * COUNT(DISTINCT f.event_date) FILTER (WHERE f.open_interest IS NOT NULL) 
    / NULLIF(COUNT(DISTINCT td.event_date), 0),
    2
  ) AS oi_coverage_pct,
  COUNT(DISTINCT f.event_date) FILTER (WHERE f.volume IS NOT NULL AND f.volume > 0) AS days_with_volume,
  ROUND(
    100.0 * COUNT(DISTINCT f.event_date) FILTER (WHERE f.volume IS NOT NULL AND f.volume > 0)
    / NULLIF(COUNT(DISTINCT td.event_date), 0),
    2
  ) AS volume_coverage_pct
FROM crush_symbols s
CROSS JOIN trading_days td
LEFT JOIN mkt.futures_1d f
  ON f.symbol = s.symbol
  AND f.event_date = td.event_date
  AND f.source = 'databento'
GROUP BY s.symbol
ORDER BY s.symbol;

-- =============================================================================
-- 2. CONSISTENCY TEST: Schema Lock (Event Date Progression)
-- =============================================================================
-- Expected: All symbols have correct event_date progression, no gaps > 5 days

WITH date_gaps AS (
  SELECT 
    symbol,
    event_date,
    LAG(event_date) OVER (PARTITION BY symbol ORDER BY event_date) AS prev_date,
    event_date - LAG(event_date) OVER (PARTITION BY symbol ORDER BY event_date) AS gap_days
  FROM mkt.futures_1d
  WHERE source = 'databento'
    AND symbol IN ('ZL', 'ZS', 'ZM', 'CL', 'HO', 'RB')
    AND event_date >= CURRENT_DATE - INTERVAL '60 days'
)
SELECT 
  symbol,
  COUNT(*) AS total_rows,
  COUNT(*) FILTER (WHERE gap_days IS NULL OR gap_days <= 5) AS normal_gaps,
  COUNT(*) FILTER (WHERE gap_days > 5) AS large_gaps,
  MAX(gap_days) AS max_gap_days,
  MIN(event_date) AS earliest_date,
  MAX(event_date) AS latest_date
FROM date_gaps
GROUP BY symbol
ORDER BY symbol;

-- =============================================================================
-- 3. CRUSH SPECIALIST PREFLIGHT: Volume + Open Interest Coverage Thresholds
-- =============================================================================
-- Expected: Fail fast with explicit taxonomy if thresholds not met
-- Threshold: >= 80% coverage for both volume and OI over last 30 trading days

WITH recent_trading_days AS (
  SELECT generate_series(
    CURRENT_DATE - INTERVAL '45 days',  -- 45 calendar days ≈ 30 trading days
    CURRENT_DATE - INTERVAL '1 day',
    '1 day'::interval
  )::date AS event_date
  WHERE EXTRACT(DOW FROM generate_series) NOT IN (0, 6)
),
crush_coverage AS (
  SELECT 
    f.symbol,
    COUNT(DISTINCT td.event_date) AS total_days,
    COUNT(DISTINCT f.event_date) FILTER (WHERE f.volume IS NOT NULL AND f.volume > 0) AS volume_days,
    COUNT(DISTINCT f.event_date) FILTER (WHERE f.open_interest IS NOT NULL) AS oi_days,
    ROUND(
      100.0 * COUNT(DISTINCT f.event_date) FILTER (WHERE f.volume IS NOT NULL AND f.volume > 0)
      / NULLIF(COUNT(DISTINCT td.event_date), 0),
      2
    ) AS volume_coverage_pct,
    ROUND(
      100.0 * COUNT(DISTINCT f.event_date) FILTER (WHERE f.open_interest IS NOT NULL)
      / NULLIF(COUNT(DISTINCT td.event_date), 0),
      2
    ) AS oi_coverage_pct
  FROM recent_trading_days td
  CROSS JOIN (SELECT DISTINCT symbol FROM mkt.futures_1d WHERE symbol IN ('ZL', 'ZS', 'ZM')) s
  LEFT JOIN mkt.futures_1d f
    ON f.symbol = s.symbol
    AND f.event_date = td.event_date
    AND f.source = 'databento'
  GROUP BY f.symbol
)
SELECT 
  symbol,
  volume_coverage_pct,
  oi_coverage_pct,
  CASE 
    WHEN volume_coverage_pct >= 80 AND oi_coverage_pct >= 80 THEN 'PASS'
    WHEN volume_coverage_pct < 80 AND oi_coverage_pct < 80 THEN 'FAIL: Volume < 80% AND OI < 80%'
    WHEN volume_coverage_pct < 80 THEN 'FAIL: Volume < 80%'
    WHEN oi_coverage_pct < 80 THEN 'FAIL: OI < 80%'
    ELSE 'UNKNOWN'
  END AS preflight_status
FROM crush_coverage
ORDER BY symbol;

-- =============================================================================
-- 4. DATA QUALITY: Source Distribution
-- =============================================================================
-- Check how many rows come from Databento vs Yahoo for each symbol

SELECT 
  symbol,
  source,
  COUNT(*) AS row_count,
  MIN(event_date) AS earliest_date,
  MAX(event_date) AS latest_date,
  COUNT(*) FILTER (WHERE volume IS NOT NULL AND volume > 0) AS rows_with_volume,
  COUNT(*) FILTER (WHERE open_interest IS NOT NULL) AS rows_with_oi
FROM mkt.futures_1d
WHERE symbol IN ('ZL', 'ZS', 'ZM', 'CL', 'HO', 'RB')
  AND event_date >= CURRENT_DATE - INTERVAL '60 days'
GROUP BY symbol, source
ORDER BY symbol, source;

-- =============================================================================
-- 5. ROW HASH VERIFICATION: Check for Duplicates
-- =============================================================================
-- Expected: No duplicate row_hashes for same (event_date, symbol) pairs

SELECT 
  symbol,
  event_date,
  COUNT(*) AS duplicate_count,
  array_agg(DISTINCT source) AS sources,
  array_agg(DISTINCT row_hash) AS hashes
FROM mkt.futures_1d
WHERE source = 'databento'
  AND symbol IN ('ZL', 'ZS', 'ZM', 'CL', 'HO', 'RB')
GROUP BY symbol, event_date
HAVING COUNT(*) > 1
ORDER BY symbol, event_date DESC
LIMIT 20;
