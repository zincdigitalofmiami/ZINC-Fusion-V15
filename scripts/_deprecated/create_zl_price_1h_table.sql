-- Create analytics.zl_price_1h table for 1-hour ZL bars
-- Schema: analytics (dashboard layer)
-- Grain: _1h (hourly time series)
-- Purpose: Isolated hourly price data for charting (2 years max from Yahoo)

CREATE TABLE IF NOT EXISTS analytics.zl_price_1h (
    timestamp       TIMESTAMPTZ PRIMARY KEY,
    open            NUMERIC(10,4) NOT NULL,
    high            NUMERIC(10,4) NOT NULL,
    low             NUMERIC(10,4) NOT NULL,
    close           NUMERIC(10,4) NOT NULL,
    volume          BIGINT NOT NULL DEFAULT 0,
    source          VARCHAR(50) NOT NULL DEFAULT 'yahoo',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_zl_price_1h_timestamp ON analytics.zl_price_1h(timestamp DESC);

-- Verify
SELECT COUNT(*) as row_count FROM analytics.zl_price_1h;
