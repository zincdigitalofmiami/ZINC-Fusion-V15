-- Add LCFS credit price series (biofuel strict input)
-- Schema: supply
-- Table: lcfs_1d (event_date -> price_usd_per_mt)

CREATE TABLE IF NOT EXISTS supply.lcfs_1d (
  event_date date PRIMARY KEY,
  price_usd_per_mt numeric(12, 4) NOT NULL,
  source text NOT NULL,
  ingestion_batch_id text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_supply_lcfs_created_at
  ON supply.lcfs_1d (created_at);

