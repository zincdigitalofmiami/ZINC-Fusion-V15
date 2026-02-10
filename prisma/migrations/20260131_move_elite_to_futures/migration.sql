-- Move ALL elite indicators from features.elite_1d to mkt.futures_1d
-- This eliminates the JOIN and puts everything in ONE table

-- Add all elite indicator columns to mkt.futures_1d
-- Use DOUBLE PRECISION for flexibility (matches features.elite_1d types)
ALTER TABLE mkt.futures_1d
  -- Tier 1: Institutional Gems
  ADD COLUMN IF NOT EXISTS hurst_exponent DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS hurst_regime VARCHAR(20),
  ADD COLUMN IF NOT EXISTS connors_rsi DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS fisher_transform DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS fisher_signal DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS mcginley_dynamic DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS ttm_squeeze_on BOOLEAN,
  ADD COLUMN IF NOT EXISTS ttm_squeeze_momentum DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS schaff_trend_cycle DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS rvi DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS rvi_signal DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS elder_force_index DOUBLE PRECISION,

  -- Tier 2: Optimized Moving Averages
  ADD COLUMN IF NOT EXISTS kama_10 DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS hma_20 DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS alma_50 DOUBLE PRECISION,

  -- Tier 2: RSI Variants
  ADD COLUMN IF NOT EXISTS rsi_2 DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS rsi_14 DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS cumulative_rsi DOUBLE PRECISION,

  -- Tier 2: MACD
  ADD COLUMN IF NOT EXISTS macd DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS macd_signal DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS macd_histogram DOUBLE PRECISION,

  -- Tier 2: CCI
  ADD COLUMN IF NOT EXISTS cci_14 DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS cci_50 DOUBLE PRECISION,

  -- Tier 3: Volatility Regime
  ADD COLUMN IF NOT EXISTS atr_10 DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS atr_50 DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS atr_ratio DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS garman_klass_vol DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS yang_zhang_vol DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS bb_percent_b DOUBLE PRECISION,

  -- Tier 4: Volume/Flow
  ADD COLUMN IF NOT EXISTS cmf_21 DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS volume_zscore DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS unusual_volume BOOLEAN,

  -- Calculated returns
  ADD COLUMN IF NOT EXISTS returns_1d DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS log_returns_1d DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS range_pct DOUBLE PRECISION;

-- Create indexes for key indicators
CREATE INDEX IF NOT EXISTS idx_futures_hurst ON mkt.futures_1d(symbol, hurst_exponent) WHERE hurst_exponent IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_futures_rsi_14 ON mkt.futures_1d(symbol, rsi_14) WHERE rsi_14 IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_futures_ttm_squeeze ON mkt.futures_1d(symbol, ttm_squeeze_on) WHERE ttm_squeeze_on IS NOT NULL;

-- Migrate data from features.elite_1d to mkt.futures_1d
UPDATE mkt.futures_1d f
SET
  hurst_exponent = e.hurst_exponent,
  hurst_regime = e.hurst_regime,
  connors_rsi = e.connors_rsi,
  fisher_transform = e.fisher_transform,
  fisher_signal = e.fisher_signal,
  mcginley_dynamic = e.mcginley_dynamic,
  ttm_squeeze_on = e.ttm_squeeze_on,
  ttm_squeeze_momentum = e.ttm_squeeze_momentum,
  schaff_trend_cycle = e.schaff_trend_cycle,
  rvi = e.rvi,
  rvi_signal = e.rvi_signal,
  elder_force_index = e.elder_force_index,
  kama_10 = e.kama_10,
  hma_20 = e.hma_20,
  alma_50 = e.alma_50,
  rsi_2 = e.rsi_2,
  rsi_14 = e.rsi_14,
  cumulative_rsi = e.cumulative_rsi,
  macd = e.macd,
  macd_signal = e.macd_signal,
  macd_histogram = e.macd_histogram,
  cci_14 = e.cci_14,
  cci_50 = e.cci_50,
  atr_10 = e.atr_10,
  atr_50 = e.atr_50,
  atr_ratio = e.atr_ratio,
  garman_klass_vol = e.garman_klass_vol,
  yang_zhang_vol = e.yang_zhang_vol,
  bb_percent_b = e.bb_percent_b,
  cmf_21 = e.cmf_21,
  volume_zscore = e.volume_zscore,
  unusual_volume = e.unusual_volume,
  returns_1d = e.returns_1d,
  log_returns_1d = e.log_returns_1d,
  range_pct = e.range_pct
FROM features.elite_1d e
WHERE f.symbol = e.symbol
  AND f.event_date = e.trade_date;

-- Verify migration
SELECT
  'Migration verification' as check,
  COUNT(*) as futures_rows,
  COUNT(hurst_exponent) as with_hurst,
  COUNT(rsi_14) as with_rsi,
  COUNT(macd) as with_macd
FROM mkt.futures_1d
WHERE hurst_exponent IS NOT NULL;
