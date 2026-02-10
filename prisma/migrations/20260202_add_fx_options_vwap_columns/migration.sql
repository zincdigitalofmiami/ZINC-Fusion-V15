-- Add calculated VWAP columns to mkt.options_1d
ALTER TABLE mkt.options_1d ADD COLUMN IF NOT EXISTS close_vwap DOUBLE PRECISION;
ALTER TABLE mkt.options_1d ADD COLUMN IF NOT EXISTS ohlc_avg_vwap DOUBLE PRECISION;

COMMENT ON COLUMN mkt.options_1d.close_vwap IS 'VWAP approximation: Close price × Volume (daily aggregate)';
COMMENT ON COLUMN mkt.options_1d.ohlc_avg_vwap IS 'VWAP approximation: OHLC average × Volume (daily aggregate)';
