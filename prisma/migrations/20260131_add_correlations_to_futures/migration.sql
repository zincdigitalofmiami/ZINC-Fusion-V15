-- Add ZL correlation columns to mkt.futures_1d
-- These pre-calculate correlations as data lands (not during training)

ALTER TABLE mkt.futures_1d
  ADD COLUMN IF NOT EXISTS zl_corr_30d DECIMAL(6, 4),
  ADD COLUMN IF NOT EXISTS zl_corr_60d DECIMAL(6, 4),
  ADD COLUMN IF NOT EXISTS zl_corr_90d DECIMAL(6, 4);

-- Create indexes for fast correlation lookups
CREATE INDEX IF NOT EXISTS idx_futures_zl_corr_30d ON mkt.futures_1d(symbol, zl_corr_30d) WHERE zl_corr_30d IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_futures_zl_corr_60d ON mkt.futures_1d(symbol, zl_corr_60d) WHERE zl_corr_60d IS NOT NULL;

-- Calculate correlations for all existing FX and key symbols
-- This is a one-time backfill, then we'll calculate on insert

COMMENT ON COLUMN mkt.futures_1d.zl_corr_30d IS
  '30-day rolling correlation with ZL (soybean oil). Critical for FX specialist to understand currency-commodity linkages.';

COMMENT ON COLUMN mkt.futures_1d.zl_corr_60d IS
  '60-day rolling correlation with ZL. Medium-term correlation signal.';

COMMENT ON COLUMN mkt.futures_1d.zl_corr_90d IS
  '90-day rolling correlation with ZL. Long-term structural correlation.';
