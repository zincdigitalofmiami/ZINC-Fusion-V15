-- Create analytics.price_1m table
-- The original zl_price_1m was dropped in the naming cleanup migration,
-- but active API routes and Inngest jobs write to analytics.price_1m.
-- This creates the table with the multi-symbol schema pattern.

CREATE TABLE analytics.price_1m (
  id             SERIAL PRIMARY KEY,
  symbol         VARCHAR(20) NOT NULL DEFAULT 'ZL',
  "timestamp"    TIMESTAMPTZ(6) NOT NULL,
  open           DOUBLE PRECISION NOT NULL,
  high           DOUBLE PRECISION NOT NULL,
  low            DOUBLE PRECISION NOT NULL,
  close          DOUBLE PRECISION NOT NULL,
  volume         INTEGER,
  previous_close DOUBLE PRECISION,
  change         DOUBLE PRECISION,
  change_percent DOUBLE PRECISION,
  day_high       DOUBLE PRECISION,
  day_low        DOUBLE PRECISION,
  source         VARCHAR(50),
  created_at     TIMESTAMPTZ(6) DEFAULT NOW(),
  CONSTRAINT price_1m_symbol_timestamp_key UNIQUE (symbol, "timestamp")
);

CREATE INDEX idx_price_1m_symbol ON analytics.price_1m (symbol);
