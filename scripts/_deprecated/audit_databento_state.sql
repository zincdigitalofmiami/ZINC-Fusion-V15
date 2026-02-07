-- Databento Integration State Audit Queries
-- Run these queries to understand current state before making changes

-- =============================================================================
-- 1. SOURCE DISTRIBUTION - Check what sources are writing to analytics tables
-- =============================================================================

SELECT 
    'zl_price_15m' as table_name,
    source, 
    COUNT(*) as count, 
    MIN(timestamp) as min_ts, 
    MAX(timestamp) as max_ts
FROM analytics.zl_price_15m
GROUP BY source
ORDER BY count DESC;

SELECT 
    'zl_price_1h' as table_name,
    source, 
    COUNT(*) as count, 
    MIN(timestamp) as min_ts, 
    MAX(timestamp) as max_ts
FROM analytics.zl_price_1h
GROUP BY source
ORDER BY count DESC;

SELECT 
    'zl_price_1d' as table_name,
    source, 
    COUNT(*) as count, 
    MIN(event_date) as min_date, 
    MAX(event_date) as max_date
FROM analytics.zl_price_1d
GROUP BY source
ORDER BY count DESC;

-- =============================================================================
-- 2. PRICE DISCONTINUITIES - Detect potential roll date issues
-- =============================================================================

-- 15m bars: Look for large price jumps (>5%)
SELECT 
    timestamp,
    close,
    LAG(close) OVER (ORDER BY timestamp) as prev_close,
    ABS(close - LAG(close) OVER (ORDER BY timestamp)) / NULLIF(LAG(close) OVER (ORDER BY timestamp), 0) * 100 as pct_change,
    source
FROM analytics.zl_price_15m
WHERE timestamp >= NOW() - INTERVAL '7 days'
ORDER BY ABS(close - LAG(close) OVER (ORDER BY timestamp)) / NULLIF(LAG(close) OVER (ORDER BY timestamp), 0) DESC NULLS LAST
LIMIT 20;

-- Daily bars: Look for large intraday changes (>5%)
SELECT 
    event_date,
    open,
    close,
    ABS(close - open) / NULLIF(open, 0) * 100 as intraday_pct_change,
    source
FROM analytics.zl_price_1d
WHERE event_date >= CURRENT_DATE - INTERVAL '30 days'
ORDER BY ABS(close - open) / NULLIF(open, 0) DESC NULLS LAST
LIMIT 20;

-- =============================================================================
-- 3. SYMBOL USAGE CHECK - Verify what symbol is being used
-- =============================================================================

-- Check mkt.futures_1d for ZL source distribution
SELECT 
    source,
    COUNT(*) as count,
    COUNT(*) FILTER (WHERE open_interest IS NOT NULL) as with_oi,
    MIN(event_date) as earliest,
    MAX(event_date) as latest
FROM mkt.futures_1d
WHERE symbol = 'ZL'
GROUP BY source
ORDER BY count DESC;

-- =============================================================================
-- 4. DATA COVERAGE GAPS - Check for missing timestamps
-- =============================================================================

-- 15m bars: Check for gaps >30 minutes
WITH gaps AS (
    SELECT 
        timestamp,
        LAG(timestamp) OVER (ORDER BY timestamp) as prev_ts,
        timestamp - LAG(timestamp) OVER (ORDER BY timestamp) as gap
    FROM analytics.zl_price_15m
    WHERE timestamp >= NOW() - INTERVAL '7 days'
    ORDER BY timestamp DESC
)
SELECT 
    prev_ts as gap_start,
    timestamp as gap_end,
    gap,
    EXTRACT(EPOCH FROM gap) / 60 as gap_minutes
FROM gaps
WHERE gap > INTERVAL '30 minutes'
LIMIT 20;

-- Daily bars: Check for missing days
WITH date_series AS (
    SELECT generate_series(
        CURRENT_DATE - INTERVAL '30 days',
        CURRENT_DATE - INTERVAL '1 day',
        '1 day'::interval
    )::date AS day
)
SELECT 
    ds.day as missing_date
FROM date_series ds
LEFT JOIN analytics.zl_price_1d z ON ds.day = z.event_date
WHERE z.event_date IS NULL
  AND EXTRACT(DOW FROM ds.day) NOT IN (0, 6)  -- Exclude weekends
ORDER BY ds.day DESC;

-- =============================================================================
-- 5. SOURCE CONFLICTS - Check for overlapping timestamps from different sources
-- =============================================================================

-- 15m: Check for same timestamp with different sources
SELECT 
    timestamp,
    array_agg(DISTINCT source) as sources,
    COUNT(*) as count
FROM analytics.zl_price_15m
WHERE timestamp >= NOW() - INTERVAL '7 days'
GROUP BY timestamp
HAVING COUNT(DISTINCT source) > 1
ORDER BY timestamp DESC
LIMIT 20;

-- 1h: Check for same timestamp with different sources
SELECT 
    timestamp,
    array_agg(DISTINCT source) as sources,
    COUNT(*) as count
FROM analytics.zl_price_1h
WHERE timestamp >= NOW() - INTERVAL '7 days'
GROUP BY timestamp
HAVING COUNT(DISTINCT source) > 1
ORDER BY timestamp DESC
LIMIT 20;

-- Daily: Check for same date with different sources
SELECT 
    event_date,
    array_agg(DISTINCT source) as sources,
    COUNT(*) as count
FROM analytics.zl_price_1d
WHERE event_date >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY event_date
HAVING COUNT(DISTINCT source) > 1
ORDER BY event_date DESC
LIMIT 20;

-- =============================================================================
-- 6. VOLUME CONSISTENCY - Check volume patterns
-- =============================================================================

-- 15m bars: Volume per day
SELECT 
    DATE_TRUNC('day', timestamp) as day,
    COUNT(*) as bars_per_day,
    SUM(volume) as total_volume,
    AVG(volume) as avg_volume,
    MIN(volume) as min_volume,
    MAX(volume) as max_volume,
    source
FROM analytics.zl_price_15m
WHERE timestamp >= NOW() - INTERVAL '7 days'
GROUP BY DATE_TRUNC('day', timestamp), source
ORDER BY day DESC, source;

-- =============================================================================
-- 7. RECENT DATA CHECK - Verify latest data freshness
-- =============================================================================

-- Latest 15m bar
SELECT 
    '15m' as interval,
    MAX(timestamp) as latest_timestamp,
    MAX(timestamp) - NOW() as age,
    source
FROM analytics.zl_price_15m
GROUP BY source;

-- Latest 1h bar
SELECT 
    '1h' as interval,
    MAX(timestamp) as latest_timestamp,
    MAX(timestamp) - NOW() as age,
    source
FROM analytics.zl_price_1h
GROUP BY source;

-- Latest daily bar
SELECT 
    '1d' as interval,
    MAX(event_date) as latest_date,
    CURRENT_DATE - MAX(event_date) as days_old,
    source
FROM analytics.zl_price_1d
GROUP BY source;

-- =============================================================================
-- 8. DATA QUALITY CHECK - Verify data integrity
-- =============================================================================

-- Check for NULL prices
SELECT 
    'zl_price_15m' as table_name,
    COUNT(*) FILTER (WHERE close IS NULL) as null_closes,
    COUNT(*) FILTER (WHERE open IS NULL) as null_opens,
    COUNT(*) FILTER (WHERE high IS NULL) as null_highs,
    COUNT(*) FILTER (WHERE low IS NULL) as null_lows,
    COUNT(*) as total_rows
FROM analytics.zl_price_15m
WHERE timestamp >= NOW() - INTERVAL '7 days';

-- Check for invalid prices (negative or zero)
SELECT 
    'zl_price_15m' as table_name,
    COUNT(*) FILTER (WHERE close <= 0) as invalid_closes,
    COUNT(*) FILTER (WHERE high < low) as invalid_ohlc,
    COUNT(*) as total_rows
FROM analytics.zl_price_15m
WHERE timestamp >= NOW() - INTERVAL '7 days';

-- =============================================================================
-- SUMMARY QUERIES - Quick overview
-- =============================================================================

-- Overall summary
SELECT 
    'Summary' as check_type,
    (SELECT COUNT(*) FROM analytics.zl_price_15m WHERE timestamp >= NOW() - INTERVAL '7 days') as zl_15m_last_7d,
    (SELECT COUNT(*) FROM analytics.zl_price_1h WHERE timestamp >= NOW() - INTERVAL '7 days') as zl_1h_last_7d,
    (SELECT COUNT(*) FROM analytics.zl_price_1d WHERE event_date >= CURRENT_DATE - INTERVAL '30 days') as zl_1d_last_30d,
    (SELECT COUNT(DISTINCT source) FROM analytics.zl_price_15m) as unique_sources_15m,
    (SELECT COUNT(DISTINCT source) FROM analytics.zl_price_1h) as unique_sources_1h,
    (SELECT COUNT(DISTINCT source) FROM analytics.zl_price_1d) as unique_sources_1d;
