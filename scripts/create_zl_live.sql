-- Run this: psql $DATABASE_URL -f scripts/create_zl_live.sql

CREATE TABLE IF NOT EXISTS analytics.zl_live (
  id SERIAL PRIMARY KEY,
  price DOUBLE PRECISION NOT NULL,
  previous_close DOUBLE PRECISION,
  change DOUBLE PRECISION,
  change_pct DOUBLE PRECISION,
  day_high DOUBLE PRECISION,
  day_low DOUBLE PRECISION,
  day_open DOUBLE PRECISION,
  volume INTEGER,
  timestamp TIMESTAMPTZ,
  source VARCHAR(50),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

INSERT INTO analytics.zl_live (price, previous_close, change, change_pct, day_high, day_low, day_open, volume, timestamp, source, updated_at)
SELECT price, previous_close, change, change_percent, day_high, day_low, day_open, volume, timestamp, source, updated_at
FROM public.latest_prices WHERE symbol = 'ZL';

SELECT 'analytics.zl_live created and seeded' as status;
