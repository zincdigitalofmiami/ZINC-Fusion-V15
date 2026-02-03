-- Add ZL correlation columns to mkt.fx_1d
ALTER TABLE mkt.fx_1d ADD COLUMN IF NOT EXISTS zl_corr_30d DOUBLE PRECISION;
ALTER TABLE mkt.fx_1d ADD COLUMN IF NOT EXISTS zl_corr_60d DOUBLE PRECISION;
ALTER TABLE mkt.fx_1d ADD COLUMN IF NOT EXISTS zl_corr_90d DOUBLE PRECISION;

COMMENT ON COLUMN mkt.fx_1d.zl_corr_30d IS '30-day rolling correlation with ZL (soybean oil)';
COMMENT ON COLUMN mkt.fx_1d.zl_corr_60d IS '60-day rolling correlation with ZL';
COMMENT ON COLUMN mkt.fx_1d.zl_corr_90d IS '90-day rolling correlation with ZL';
