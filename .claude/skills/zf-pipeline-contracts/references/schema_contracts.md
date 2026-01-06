# Schema Contracts

Canonical table definitions for Prisma Postgres. Any deviation = contract violation.

## Schema Overview

| Schema | Purpose |
|--------|---------|
| raw | Landing zone for API ingestion |
| features | Transformed features by domain |
| training | OOF predictions and training matrices |
| curated | Production-ready feature sets |
| gold | Final forecasts and signals |
| monitoring | Pipeline health metrics |
| metadata | Lineage and audit trails |
| weather | Regional weather data |

## Time Grain Contracts

### Daily Tables (`_1d`)

Primary key: `(as_of_date, [dimension])`

```sql
as_of_date DATE NOT NULL  -- Never TIMESTAMP
```

### Hourly Tables (`_1h`)

Primary key: `(ts_event, [dimension])`

```sql
ts_event TIMESTAMP NOT NULL  -- Full timestamp for hourly grain
```

**Only these two grains exist.** No `_4h`, `_8h`, `_1w`.

## Training Tables (L0 OOF Outputs)

Every `training.oof_*` table MUST have this contract:

```sql
CREATE TABLE training.oof_{specialist}_1d (
    as_of_date DATE NOT NULL,           -- grain: daily
    horizon_steps INTEGER NOT NULL,      -- 5, 21, 63, or 126 only
    p10 DOUBLE NOT NULL,                 -- 10th percentile
    p50 DOUBLE NOT NULL,                 -- median
    p90 DOUBLE NOT NULL,                 -- 90th percentile
    run_id VARCHAR,                      -- MLflow reference (optional)
    created_at TIMESTAMP DEFAULT now(),
    PRIMARY KEY (as_of_date, horizon_steps)
);
```

### Required OOF Tables (11 total)

| Table | Model |
|-------|-------|
| training.oof_core_1d | Core TimeSeriesPredictor |
| training.oof_crush_1d | Specialist: crush |
| training.oof_china_1d | Specialist: china |
| training.oof_fx_1d | Specialist: fx |
| training.oof_fed_1d | Specialist: fed |
| training.oof_tariff_1d | Specialist: tariff |
| training.oof_energy_1d | Specialist: energy |
| training.oof_biofuel_1d | Specialist: biofuel |
| training.oof_palm_1d | Specialist: palm |
| training.oof_volatility_1d | Specialist: volatility |
| training.oof_substitutes_1d | Specialist: substitutes |

## Hourly Tables

### Raw Market Data

```sql
CREATE TABLE raw.market_futures_1h (
    ts_event TIMESTAMP NOT NULL,
    symbol VARCHAR NOT NULL,
    open DOUBLE,
    high DOUBLE,
    low DOUBLE,
    close DOUBLE,
    volume BIGINT,
    source VARCHAR DEFAULT 'yahoo',
    ingested_at TIMESTAMP DEFAULT now(),
    PRIMARY KEY (ts_event, symbol)
);
```

### Intraday Volatility Features

```sql
CREATE TABLE features.intraday_volatility (
    as_of_date DATE NOT NULL,           -- Daily aggregate from 1h data
    symbol VARCHAR NOT NULL,
    realized_vol_1h DOUBLE,             -- Intraday realized volatility
    high_low_range DOUBLE,              -- Daily H-L range from 1h bars
    volume_profile DOUBLE,              -- Volume distribution metric
    overnight_gap DOUBLE,               -- Gap from prev close
    created_at TIMESTAMP DEFAULT now(),
    PRIMARY KEY (as_of_date, symbol)
);
```

## Contract Constraints

### 1. Primary Key Uniqueness

Every row must be unique on its primary key. No duplicates allowed.

- Daily: `(as_of_date, horizon_steps)` or `(as_of_date, symbol)`
- Hourly: `(ts_event, symbol)`

### 2. Quantile Monotonicity

Must satisfy: `p10 <= p50 <= p90`

Crossing quantiles indicate model failure or data corruption.

### 3. Horizon Encoding

`horizon_steps` must be one of: `5, 21, 63, 126`

| horizon_steps | Human Label | Trading Days |
|---------------|-------------|--------------|
| 5 | 1W | 1 week |
| 21 | 1M | 1 month |
| 63 | 3M | 3 months |
| 126 | 6M | 6 months |

Never store string horizons ("1w", "1m") in DB—integers only.

### 4. Date/Time Type Rules

| Grain | Column | Type |
|-------|--------|------|
| `_1d` | `as_of_date` | DATE (not TIMESTAMP) |
| `_1h` | `ts_event` | TIMESTAMP |

## Feature Tables

Feature tables in `features.*` follow this pattern:

```sql
CREATE TABLE features.{domain}_1d (
    as_of_date DATE NOT NULL,
    symbol VARCHAR,
    -- feature columns vary by domain
    created_at TIMESTAMP DEFAULT now(),
    PRIMARY KEY (as_of_date, symbol)
);
```

## Sentiment Features (Per Specialist)

```sql
CREATE TABLE features.sentiment_specialist_1d (
    as_of_date DATE NOT NULL,
    specialist VARCHAR NOT NULL,      -- 'crush', 'china', etc.
    sentiment_score DOUBLE,           -- -1 to +1 polarity
    sentiment_confidence DOUBLE,      -- 0 to 1 model confidence
    news_volume_24h INTEGER,
    sentiment_momentum_3d DOUBLE,
    sentiment_momentum_7d DOUBLE,
    agent_model VARCHAR,              -- 'claude-sonnet-4.5' when AI-scored
    PRIMARY KEY (as_of_date, specialist)
);
```

## Gold Tables (Forecasts)

```sql
CREATE TABLE gold.forecasts_ensemble_1d (
    as_of_date DATE NOT NULL,
    horizon_steps INTEGER NOT NULL,
    p10 DOUBLE NOT NULL,
    p50 DOUBLE NOT NULL,
    p90 DOUBLE NOT NULL,
    signal VARCHAR,                   -- BUY, HOLD, SELL
    confidence DOUBLE,
    run_id VARCHAR,
    created_at TIMESTAMP DEFAULT now(),
    PRIMARY KEY (as_of_date, horizon_steps)
);
```

## Meta-Ensemble Table (L1 Input)

```sql
CREATE TABLE training.meta_ensemble_1d (
    as_of_date DATE NOT NULL,
    horizon_steps INTEGER NOT NULL,
    -- OOF from each L0 model (33 columns: 11 models × 3 quantiles)
    core_p10 DOUBLE, core_p50 DOUBLE, core_p90 DOUBLE,
    crush_p10 DOUBLE, crush_p50 DOUBLE, crush_p90 DOUBLE,
    china_p10 DOUBLE, china_p50 DOUBLE, china_p90 DOUBLE,
    fx_p10 DOUBLE, fx_p50 DOUBLE, fx_p90 DOUBLE,
    fed_p10 DOUBLE, fed_p50 DOUBLE, fed_p90 DOUBLE,
    tariff_p10 DOUBLE, tariff_p50 DOUBLE, tariff_p90 DOUBLE,
    energy_p10 DOUBLE, energy_p50 DOUBLE, energy_p90 DOUBLE,
    biofuel_p10 DOUBLE, biofuel_p50 DOUBLE, biofuel_p90 DOUBLE,
    palm_p10 DOUBLE, palm_p50 DOUBLE, palm_p90 DOUBLE,
    volatility_p10 DOUBLE, volatility_p50 DOUBLE, volatility_p90 DOUBLE,
    substitutes_p10 DOUBLE, substitutes_p50 DOUBLE, substitutes_p90 DOUBLE,
    -- target
    target_return DOUBLE,
    PRIMARY KEY (as_of_date, horizon_steps)
);
```

This table is built by joining all 11 `training.oof_*_1d` tables on `(as_of_date, horizon_steps)`.
