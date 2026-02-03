-- Add columns for all 15 Databento statistics schema stat types to mkt.options_1d
-- Existing: open_interest (9), bid (8), ask (7), change (12), premium/settlement (3)
-- New: opening_price_stat (1), indicative_opening (2), session_low_stat (4), session_high_stat (5),
--      cleared_volume (6), fixing_price (10), close_stat (11), vwap (13), implied_volatility (14), delta (15)

ALTER TABLE "mkt"."options_1d" ADD COLUMN IF NOT EXISTS "opening_price_stat" DOUBLE PRECISION;
ALTER TABLE "mkt"."options_1d" ADD COLUMN IF NOT EXISTS "indicative_opening" DOUBLE PRECISION;
ALTER TABLE "mkt"."options_1d" ADD COLUMN IF NOT EXISTS "session_low_stat" DOUBLE PRECISION;
ALTER TABLE "mkt"."options_1d" ADD COLUMN IF NOT EXISTS "session_high_stat" DOUBLE PRECISION;
ALTER TABLE "mkt"."options_1d" ADD COLUMN IF NOT EXISTS "cleared_volume" BIGINT;
ALTER TABLE "mkt"."options_1d" ADD COLUMN IF NOT EXISTS "fixing_price" DOUBLE PRECISION;
ALTER TABLE "mkt"."options_1d" ADD COLUMN IF NOT EXISTS "close_stat" DOUBLE PRECISION;
ALTER TABLE "mkt"."options_1d" ADD COLUMN IF NOT EXISTS "vwap" DOUBLE PRECISION;
ALTER TABLE "mkt"."options_1d" ADD COLUMN IF NOT EXISTS "implied_volatility" DOUBLE PRECISION;
ALTER TABLE "mkt"."options_1d" ADD COLUMN IF NOT EXISTS "delta" DOUBLE PRECISION;
