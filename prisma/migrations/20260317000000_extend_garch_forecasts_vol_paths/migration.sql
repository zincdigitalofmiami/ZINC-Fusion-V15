-- Extend garch_forecasts with full volatility path artifacts
-- for the standalone GARCH producer stage (run_garch.py).

ALTER TABLE "forecasts"."garch_forecasts"
  ADD COLUMN "daily_vol_path"      JSONB,
  ADD COLUMN "annualized_vol_path" JSONB,
  ADD COLUMN "upside_vol_mult"     DOUBLE PRECISION,
  ADD COLUMN "downside_vol_mult"   DOUBLE PRECISION,
  ADD COLUMN "persistence"         DOUBLE PRECISION,
  ADD COLUMN "gamma"               DOUBLE PRECISION,
  ADD COLUMN "lookback_days"       INTEGER,
  ADD COLUMN "regime"              VARCHAR(20),
  ADD COLUMN "regime_multiplier"   DOUBLE PRECISION,
  ADD COLUMN "source_start_date"   DATE,
  ADD COLUMN "source_end_date"     DATE;
