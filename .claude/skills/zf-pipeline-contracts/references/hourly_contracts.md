# Hourly Data Contracts

Rules for working with hourly (`_1h`) grain data in ZINC-Fusion-V15.

## Available Hourly Tables

| Table | Purpose | PK |
|-------|---------|-----|
| `raw.market_futures_1h` | Hourly OHLCV for ZL, ZS, ZM, CL, etc. | `(ts_event, symbol)` |

## Derived Daily Features (from 1h)

| Table | Source | Purpose |
|-------|--------|---------|
| `features.intraday_volatility` | `raw.market_futures_1h` | Daily aggregates of intraday vol |

## Primary Key Rules

```sql
-- Hourly: ts_event (TIMESTAMP)
PRIMARY KEY (ts_event, symbol)

-- NOT as_of_date for hourly grain
```

## Hourly → Daily Aggregation Pattern

Hourly data is aggregated to daily features. OOF predictions are ONLY at daily grain.

```sql
-- Aggregate hourly to daily
CREATE TABLE features.intraday_volatility AS
SELECT 
    DATE_TRUNC('day', ts_event) AS as_of_date,
    symbol,
    
    -- Realized volatility from hourly returns
    STDDEV(LN(close / LAG(close) OVER (PARTITION BY symbol ORDER BY ts_event))) 
        * SQRT(24) AS realized_vol_1h,
    
    -- High-low range
    MAX(high) - MIN(low) AS daily_range,
    
    -- Volume profile (volume-weighted average price deviation)
    SUM(volume * ABS(close - AVG(close) OVER (PARTITION BY symbol, DATE_TRUNC('day', ts_event)))) 
        / SUM(volume) AS volume_profile,
    
    -- Overnight gap (first bar vs previous day close)
    FIRST_VALUE(open) OVER (PARTITION BY symbol, DATE_TRUNC('day', ts_event) ORDER BY ts_event) -
    LAG(LAST_VALUE(close) OVER (PARTITION BY symbol, DATE_TRUNC('day', ts_event) ORDER BY ts_event))
        OVER (PARTITION BY symbol ORDER BY DATE_TRUNC('day', ts_event)) AS overnight_gap

FROM raw.market_futures_1h
GROUP BY DATE_TRUNC('day', ts_event), symbol;
```

## Sentiment Hourly Aggregation

Sentiment scores from AI agents at hourly intervals roll up to daily:

```sql
-- Hourly sentiment (from Claude API jobs)
CREATE TABLE features.sentiment_hourly (
    ts_event TIMESTAMP NOT NULL,
    specialist VARCHAR NOT NULL,
    sentiment_score DOUBLE,
    source VARCHAR,              -- 'reuters', 'bloomberg', 'usda'
    agent_run_id VARCHAR,
    PRIMARY KEY (ts_event, specialist)
);

-- Roll up to daily with exponential decay (recent hours matter more)
CREATE TABLE features.sentiment_specialist_1d AS
SELECT 
    DATE_TRUNC('day', ts_event) AS as_of_date,
    specialist,
    
    -- Simple average
    AVG(sentiment_score) AS sentiment_mean,
    
    -- Exponentially-weighted average (half-life = 8 hours)
    SUM(sentiment_score * EXP(-0.087 * EXTRACT(HOUR FROM (CURRENT_TIMESTAMP - ts_event)))) /
        NULLIF(SUM(EXP(-0.087 * EXTRACT(HOUR FROM (CURRENT_TIMESTAMP - ts_event)))), 0) 
        AS sentiment_ema,
    
    -- Volatility of sentiment
    STDDEV(sentiment_score) AS sentiment_vol,
    
    -- Count for confidence
    COUNT(*) AS news_count

FROM features.sentiment_hourly
GROUP BY DATE_TRUNC('day', ts_event), specialist;
```

## What Does NOT Exist

| Concept | Status | Reason |
|---------|--------|--------|
| `training.oof_*_1h` | Does not exist | OOF only at daily grain |
| `_4h`, `_8h` grains | Does not exist | Only `_1h` and `_1d` |
| Hourly forecasts | Does not exist | Procurement decisions are daily |
| Hourly horizon_steps | N/A | Hourly features aggregate to daily |

## Dagster Asset Dependencies

```python
# Hourly ingestion runs every hour during market hours
@asset(
    group_name="raw_ingestion",
    description="Hourly futures OHLCV",
)
def raw_market_futures_1h():
    ...

# Daily features depend on hourly data
@asset(
    group_name="feature_engineering",
    deps=[raw_market_futures_1h],
    description="Intraday volatility from 1H data",
)
def features_intraday_volatility():
    ...
```

## Validation Queries

```sql
-- Check hourly data coverage
SELECT 
    DATE_TRUNC('day', ts_event) AS trade_date,
    symbol,
    COUNT(*) AS hourly_bars,
    MIN(ts_event) AS first_bar,
    MAX(ts_event) AS last_bar
FROM raw.market_futures_1h
WHERE ts_event >= CURRENT_DATE - INTERVAL '7 days'
GROUP BY 1, 2
ORDER BY 1 DESC, 2;

-- Verify no orphaned hourly data (should have corresponding daily)
SELECT DISTINCT DATE_TRUNC('day', h.ts_event) AS orphan_date
FROM raw.market_futures_1h h
LEFT JOIN raw.market_futures_1d d 
    ON DATE_TRUNC('day', h.ts_event) = d.as_of_date 
    AND h.symbol = d.symbol
WHERE d.as_of_date IS NULL;
```
