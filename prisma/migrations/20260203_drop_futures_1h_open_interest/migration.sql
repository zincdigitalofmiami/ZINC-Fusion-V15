-- Drop all-NULL open_interest from mkt.futures_1h and enforce uniqueness
ALTER TABLE mkt.futures_1h
  DROP COLUMN IF EXISTS open_interest;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'uq_mkt_futures_1h_symbol_time'
  ) THEN
    ALTER TABLE mkt.futures_1h
      ADD CONSTRAINT uq_mkt_futures_1h_symbol_time UNIQUE (symbol, event_time);
  END IF;
END $$;
