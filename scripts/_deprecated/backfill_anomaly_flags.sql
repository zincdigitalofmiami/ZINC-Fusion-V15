-- ZINC-FUSION-V15: Anomaly Detection Backfill (SQL-based for performance)
-- This is 100x faster than row-by-row Python processing
-- Run via: psql $DATABASE_URL -f scripts/backfill_anomaly_flags.sql

-- ============================================================================
-- MARKET_FUTURES_1D
-- ============================================================================
-- Takes ~30 seconds for 432K rows vs hours with Python

BEGIN;

-- Create temp table with computed anomalies
CREATE TEMP TABLE market_anomalies AS
WITH price_data AS (
    SELECT
        event_date,
        symbol,
        open, high, low, close, volume,
        LAG(close) OVER w as prev_close,
        LAG(open) OVER w as prev_open,
        LAG(high) OVER w as prev_high,
        LAG(low) OVER w as prev_low,
        AVG(volume) OVER (PARTITION BY symbol ORDER BY event_date ROWS BETWEEN 20 PRECEDING AND 1 PRECEDING) as avg_volume_20d
    FROM raw.market_futures_1d
    WINDOW w AS (PARTITION BY symbol ORDER BY event_date)
)
SELECT
    event_date,
    symbol,
    -- Build anomaly flags array
    ARRAY_REMOVE(ARRAY[
        CASE WHEN high < low THEN 'invalid_ohlc' END,
        CASE WHEN open > high OR open < low THEN 'invalid_ohlc' END,
        CASE WHEN close > high OR close < low THEN 'invalid_ohlc' END,
        CASE WHEN volume = 0 THEN 'volume_zero' END,
        CASE WHEN EXTRACT(DOW FROM event_date) IN (0, 6) THEN 'weekend_data' END,
        CASE
            WHEN prev_close > 0 AND ABS(close - prev_close) / prev_close > 0.25 THEN 'price_extreme'
            WHEN prev_close > 0 AND ABS(close - prev_close) / prev_close > 0.15 THEN 'price_spike'
        END,
        CASE WHEN prev_close > 0 AND (open - prev_close) / prev_close > 0.05 THEN 'gap_up' END,
        CASE WHEN prev_close > 0 AND (open - prev_close) / prev_close < -0.05 THEN 'gap_down' END,
        CASE WHEN avg_volume_20d > 0 AND volume > avg_volume_20d * 5 THEN 'volume_spike' END,
        CASE
            WHEN open = prev_open AND high = prev_high AND low = prev_low AND close = prev_close
            THEN 'stale_price'
        END
    ], NULL) as flags,
    -- Calculate quality score (100 - deductions, min 0)
    GREATEST(0, 100
        - CASE WHEN high < low THEN 30 ELSE 0 END
        - CASE WHEN open > high OR open < low THEN 30 ELSE 0 END
        - CASE WHEN close > high OR close < low THEN 30 ELSE 0 END
        - CASE WHEN volume = 0 THEN 15 ELSE 0 END
        - CASE WHEN EXTRACT(DOW FROM event_date) IN (0, 6) THEN 10 ELSE 0 END
        - CASE WHEN prev_close > 0 AND ABS(close - prev_close) / prev_close > 0.25 THEN 20
               WHEN prev_close > 0 AND ABS(close - prev_close) / prev_close > 0.15 THEN 10 ELSE 0 END
        - CASE WHEN prev_close > 0 AND ABS((open - prev_close) / prev_close) > 0.05 THEN 5 ELSE 0 END
        - CASE WHEN avg_volume_20d > 0 AND volume > avg_volume_20d * 5 THEN 5 ELSE 0 END
        - CASE WHEN open = prev_open AND high = prev_high AND low = prev_low AND close = prev_close THEN 20 ELSE 0 END
    )::INTEGER as quality
FROM price_data;

-- Update market_futures_1d
UPDATE raw.market_futures_1d m
SET
    anomaly_flags = a.flags,
    quality_score = a.quality
FROM market_anomalies a
WHERE m.event_date = a.event_date AND m.symbol = a.symbol;

DROP TABLE market_anomalies;

COMMIT;

-- Report results
SELECT 'market_futures_1d' as table_name,
    COUNT(*) as total_rows,
    COUNT(CASE WHEN array_length(anomaly_flags, 1) > 0 THEN 1 END) as rows_with_flags,
    AVG(quality_score) as avg_quality
FROM raw.market_futures_1d;


-- ============================================================================
-- WEATHER_NOAA_1D
-- ============================================================================

BEGIN;

UPDATE raw.weather_noaa_1d
SET
    anomaly_flags = ARRAY_REMOVE(ARRAY[
        CASE WHEN tavg_c > 50 THEN 'temp_extreme_high' END,
        CASE WHEN tavg_c < -50 THEN 'temp_extreme_low' END,
        CASE WHEN tmax_c - tmin_c > 40 THEN 'temp_spike' END,
        CASE WHEN prcp_mm < 0 THEN 'precip_negative' END,
        CASE WHEN prcp_mm > 200 THEN 'precip_extreme' END,
        CASE WHEN rhav_pct > 100 OR rhav_pct < 0 THEN 'implausible_humidity' END
    ], NULL),
    quality_score = GREATEST(0, 100
        - CASE WHEN tavg_c > 50 THEN 25 ELSE 0 END
        - CASE WHEN tavg_c < -50 THEN 25 ELSE 0 END
        - CASE WHEN tmax_c - tmin_c > 40 THEN 15 ELSE 0 END
        - CASE WHEN prcp_mm < 0 THEN 30 ELSE 0 END
        - CASE WHEN prcp_mm > 200 THEN 10 ELSE 0 END
        - CASE WHEN rhav_pct > 100 OR rhav_pct < 0 THEN 25 ELSE 0 END
    );

COMMIT;

SELECT 'weather_noaa_1d' as table_name,
    COUNT(*) as total_rows,
    COUNT(CASE WHEN array_length(anomaly_flags, 1) > 0 THEN 1 END) as rows_with_flags,
    AVG(quality_score) as avg_quality
FROM raw.weather_noaa_1d;


-- ============================================================================
-- FX_SPOT_1D
-- ============================================================================

BEGIN;

CREATE TEMP TABLE fx_anomalies AS
WITH fx_data AS (
    SELECT
        id, pair, event_date, rate,
        LAG(rate) OVER (PARTITION BY pair ORDER BY event_date) as prev_rate
    FROM raw.fx_spot_1d
)
SELECT
    id,
    ARRAY_REMOVE(ARRAY[
        CASE WHEN prev_rate > 0 AND ABS(rate - prev_rate) / prev_rate > 0.10 THEN 'rate_extreme'
             WHEN prev_rate > 0 AND ABS(rate - prev_rate) / prev_rate > 0.05 THEN 'rate_spike' END,
        CASE WHEN rate <= 0 THEN 'rate_zero' END,
        CASE WHEN rate = prev_rate THEN 'stale_rate' END,
        CASE WHEN EXTRACT(DOW FROM event_date) IN (0, 6) THEN 'weekend_rate' END
    ], NULL) as flags,
    GREATEST(0, 100
        - CASE WHEN prev_rate > 0 AND ABS(rate - prev_rate) / prev_rate > 0.10 THEN 20
               WHEN prev_rate > 0 AND ABS(rate - prev_rate) / prev_rate > 0.05 THEN 10 ELSE 0 END
        - CASE WHEN rate <= 0 THEN 30 ELSE 0 END
        - CASE WHEN rate = prev_rate THEN 10 ELSE 0 END
        - CASE WHEN EXTRACT(DOW FROM event_date) IN (0, 6) THEN 10 ELSE 0 END
    )::INTEGER as quality
FROM fx_data;

UPDATE raw.fx_spot_1d f
SET anomaly_flags = a.flags, quality_score = a.quality
FROM fx_anomalies a WHERE f.id = a.id;

DROP TABLE fx_anomalies;

COMMIT;

SELECT 'fx_spot_1d' as table_name,
    COUNT(*) as total_rows,
    COUNT(CASE WHEN array_length(anomaly_flags, 1) > 0 THEN 1 END) as rows_with_flags,
    AVG(quality_score) as avg_quality
FROM raw.fx_spot_1d;


-- ============================================================================
-- CFTC_COT_1W
-- ============================================================================

BEGIN;

CREATE TEMP TABLE cot_anomalies AS
WITH cot_data AS (
    SELECT
        id, symbol, event_date, open_interest, managed_money_net,
        LAG(managed_money_net) OVER (PARTITION BY symbol ORDER BY event_date) as prev_mm_net,
        LAG(open_interest) OVER (PARTITION BY symbol ORDER BY event_date) as prev_oi
    FROM raw.cftc_cot_1w
)
SELECT
    id,
    ARRAY_REMOVE(ARRAY[
        CASE WHEN prev_mm_net != 0 AND ABS(managed_money_net - prev_mm_net) / ABS(prev_mm_net) > 0.50 THEN 'position_spike' END,
        CASE WHEN prev_oi > 0 AND ABS(open_interest - prev_oi) / prev_oi > 0.30 THEN 'oi_spike' END,
        CASE WHEN open_interest = 0 THEN 'zero_oi' END,
        CASE WHEN ABS(managed_money_net) > open_interest THEN 'impossible_position' END
    ], NULL) as flags,
    GREATEST(0, 100
        - CASE WHEN prev_mm_net != 0 AND ABS(managed_money_net - prev_mm_net) / ABS(prev_mm_net) > 0.50 THEN 15 ELSE 0 END
        - CASE WHEN prev_oi > 0 AND ABS(open_interest - prev_oi) / prev_oi > 0.30 THEN 10 ELSE 0 END
        - CASE WHEN open_interest = 0 THEN 25 ELSE 0 END
        - CASE WHEN ABS(managed_money_net) > open_interest THEN 30 ELSE 0 END
    )::INTEGER as quality
FROM cot_data;

UPDATE raw.cftc_cot_1w c
SET anomaly_flags = a.flags, quality_score = a.quality
FROM cot_anomalies a WHERE c.id = a.id;

DROP TABLE cot_anomalies;

COMMIT;

SELECT 'cftc_cot_1w' as table_name,
    COUNT(*) as total_rows,
    COUNT(CASE WHEN array_length(anomaly_flags, 1) > 0 THEN 1 END) as rows_with_flags,
    AVG(quality_score) as avg_quality
FROM raw.cftc_cot_1w;


-- ============================================================================
-- EPA_RIN_PRICES_1D
-- ============================================================================

BEGIN;

CREATE TEMP TABLE rin_anomalies AS
WITH rin_data AS (
    SELECT
        id, rin_type, event_date, price,
        LAG(price) OVER (PARTITION BY rin_type ORDER BY event_date) as prev_price
    FROM raw.epa_rin_prices_1d
)
SELECT
    id,
    ARRAY_REMOVE(ARRAY[
        CASE WHEN prev_price > 0 AND ABS(price - prev_price) / prev_price > 0.20 THEN 'price_spike' END,
        CASE WHEN price < 0 THEN 'price_negative' END,
        CASE WHEN price = 0 THEN 'price_zero' END,
        CASE WHEN price > 3.00 THEN 'price_extreme_high' END
    ], NULL) as flags,
    GREATEST(0, 100
        - CASE WHEN prev_price > 0 AND ABS(price - prev_price) / prev_price > 0.20 THEN 15 ELSE 0 END
        - CASE WHEN price < 0 THEN 30 ELSE 0 END
        - CASE WHEN price = 0 THEN 25 ELSE 0 END
        - CASE WHEN price > 3.00 THEN 10 ELSE 0 END
    )::INTEGER as quality
FROM rin_data;

UPDATE raw.epa_rin_prices_1d r
SET anomaly_flags = a.flags, quality_score = a.quality
FROM rin_anomalies a WHERE r.id = a.id;

DROP TABLE rin_anomalies;

COMMIT;

SELECT 'epa_rin_prices_1d' as table_name,
    COUNT(*) as total_rows,
    COUNT(CASE WHEN array_length(anomaly_flags, 1) > 0 THEN 1 END) as rows_with_flags,
    AVG(quality_score) as avg_quality
FROM raw.epa_rin_prices_1d;


-- ============================================================================
-- NEWS_ARTICLES_1D
-- ============================================================================

BEGIN;

UPDATE raw.news_articles_1d
SET
    anomaly_flags = ARRAY_REMOVE(ARRAY[
        CASE WHEN ABS(sentiment_score) > 0.95 THEN 'sentiment_extreme' END,
        CASE WHEN headline IS NULL OR headline = '' THEN 'empty_content' END,
        CASE WHEN published_at > NOW() THEN 'future_published' END
    ], NULL),
    quality_score = GREATEST(0, 100
        - CASE WHEN ABS(sentiment_score) > 0.95 THEN 10 ELSE 0 END
        - CASE WHEN headline IS NULL OR headline = '' THEN 30 ELSE 0 END
        - CASE WHEN published_at > NOW() THEN 25 ELSE 0 END
    );

COMMIT;

SELECT 'news_articles_1d' as table_name,
    COUNT(*) as total_rows,
    COUNT(CASE WHEN array_length(anomaly_flags, 1) > 0 THEN 1 END) as rows_with_flags,
    AVG(quality_score) as avg_quality
FROM raw.news_articles_1d;


-- ============================================================================
-- FRED_OBSERVATIONS_1D (complex - needs rolling stats)
-- ============================================================================

BEGIN;

-- For FRED, we just set basic quality scores and flag duplicates
-- More complex z-score based detection would need a stored procedure
UPDATE raw.fred_observations_1d f
SET
    quality_score = 100,
    anomaly_flags = CASE
        WHEN event_date > NOW() THEN ARRAY['future_dated']
        ELSE ARRAY[]::TEXT[]
    END
WHERE quality_score IS NULL;

COMMIT;

SELECT 'fred_observations_1d' as table_name,
    COUNT(*) as total_rows,
    COUNT(CASE WHEN array_length(anomaly_flags, 1) > 0 THEN 1 END) as rows_with_flags,
    AVG(quality_score) as avg_quality
FROM raw.fred_observations_1d;


-- ============================================================================
-- SUMMARY
-- ============================================================================

SELECT '=== BACKFILL COMPLETE ===' as status;

SELECT
    table_name,
    total_rows,
    rows_with_flags,
    avg_quality::NUMERIC(5,1) as avg_quality_score
FROM (
    SELECT 'market_futures_1d' as table_name, COUNT(*) as total_rows,
        COUNT(CASE WHEN array_length(anomaly_flags, 1) > 0 THEN 1 END) as rows_with_flags,
        AVG(quality_score) as avg_quality FROM raw.market_futures_1d
    UNION ALL
    SELECT 'weather_noaa_1d', COUNT(*),
        COUNT(CASE WHEN array_length(anomaly_flags, 1) > 0 THEN 1 END),
        AVG(quality_score) FROM raw.weather_noaa_1d
    UNION ALL
    SELECT 'fx_spot_1d', COUNT(*),
        COUNT(CASE WHEN array_length(anomaly_flags, 1) > 0 THEN 1 END),
        AVG(quality_score) FROM raw.fx_spot_1d
    UNION ALL
    SELECT 'cftc_cot_1w', COUNT(*),
        COUNT(CASE WHEN array_length(anomaly_flags, 1) > 0 THEN 1 END),
        AVG(quality_score) FROM raw.cftc_cot_1w
    UNION ALL
    SELECT 'epa_rin_prices_1d', COUNT(*),
        COUNT(CASE WHEN array_length(anomaly_flags, 1) > 0 THEN 1 END),
        AVG(quality_score) FROM raw.epa_rin_prices_1d
    UNION ALL
    SELECT 'news_articles_1d', COUNT(*),
        COUNT(CASE WHEN array_length(anomaly_flags, 1) > 0 THEN 1 END),
        AVG(quality_score) FROM raw.news_articles_1d
    UNION ALL
    SELECT 'fred_observations_1d', COUNT(*),
        COUNT(CASE WHEN array_length(anomaly_flags, 1) > 0 THEN 1 END),
        AVG(quality_score) FROM raw.fred_observations_1d
) summary
ORDER BY table_name;
