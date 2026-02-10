-- CreateSchema
CREATE SCHEMA IF NOT EXISTS "public";

-- CreateSchema
CREATE SCHEMA IF NOT EXISTS "raw";

-- CreateTable
CREATE TABLE "raw"."market_futures_1d" (
    "as_of_date" DATE NOT NULL,
    "symbol" TEXT NOT NULL,
    "open" DOUBLE PRECISION,
    "high" DOUBLE PRECISION,
    "low" DOUBLE PRECISION,
    "close" DOUBLE PRECISION,
    "volume" BIGINT,
    "source" TEXT,
    "ingested_at" TIMESTAMP(3) DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "market_futures_1d_pkey" PRIMARY KEY ("as_of_date","symbol")
);

-- CreateTable
CREATE TABLE "raw"."fred_economic_wide_1d" (
    "trade_date" DATE NOT NULL,

    CONSTRAINT "fred_economic_wide_1d_pkey" PRIMARY KEY ("trade_date")
);

-- CreateTable
CREATE TABLE "raw_market_futures" (
    "id" SERIAL NOT NULL,
    "symbol" TEXT NOT NULL,
    "as_of_date" TIMESTAMP(3) NOT NULL,
    "open" DOUBLE PRECISION NOT NULL,
    "high" DOUBLE PRECISION NOT NULL,
    "low" DOUBLE PRECISION NOT NULL,
    "close" DOUBLE PRECISION NOT NULL,
    "volume" INTEGER,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "open_interest" BIGINT,

    CONSTRAINT "raw_market_futures_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "raw_fred_observations" (
    "id" SERIAL NOT NULL,
    "series_id" TEXT NOT NULL,
    "as_of_date" TIMESTAMP(3) NOT NULL,
    "value" DOUBLE PRECISION,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "source" VARCHAR(50),

    CONSTRAINT "raw_fred_observations_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "raw_fx_spot" (
    "id" SERIAL NOT NULL,
    "pair" TEXT NOT NULL,
    "as_of_date" TIMESTAMP(3) NOT NULL,
    "rate" DOUBLE PRECISION NOT NULL,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "raw_fx_spot_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "raw_weather_observations" (
    "id" SERIAL NOT NULL,
    "station_id" TEXT NOT NULL,
    "as_of_date" TIMESTAMP(3) NOT NULL,
    "temp_max" DOUBLE PRECISION,
    "temp_min" DOUBLE PRECISION,
    "precip" DOUBLE PRECISION,
    "humidity" DOUBLE PRECISION,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "raw_weather_observations_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "raw_epa_rin_prices" (
    "id" SERIAL NOT NULL,
    "rin_type" TEXT NOT NULL,
    "as_of_date" TIMESTAMP(3) NOT NULL,
    "price" DOUBLE PRECISION NOT NULL,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "raw_epa_rin_prices_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "raw_cftc_cot" (
    "id" SERIAL NOT NULL,
    "contract_code" TEXT NOT NULL,
    "as_of_date" TIMESTAMP(3) NOT NULL,
    "commercial_long" INTEGER,
    "commercial_short" INTEGER,
    "non_commercial_long" INTEGER,
    "non_commercial_short" INTEGER,
    "open_interest" INTEGER,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "raw_cftc_cot_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "cv_folds" (
    "id" SERIAL NOT NULL,
    "as_of_date" TIMESTAMP(3) NOT NULL,
    "horizon" INTEGER NOT NULL,
    "fold_id" INTEGER NOT NULL,
    "is_train" BOOLEAN NOT NULL,
    "is_val" BOOLEAN NOT NULL,

    CONSTRAINT "cv_folds_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "specialist_features" (
    "id" SERIAL NOT NULL,
    "bucket" TEXT NOT NULL,
    "as_of_date" TIMESTAMP(3) NOT NULL,
    "features" JSONB NOT NULL,

    CONSTRAINT "specialist_features_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "core_features" (
    "id" SERIAL NOT NULL,
    "as_of_date" TIMESTAMP(3) NOT NULL,
    "features" JSONB NOT NULL,

    CONSTRAINT "core_features_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "oof_predictions" (
    "id" SERIAL NOT NULL,
    "source" TEXT NOT NULL,
    "as_of_date" TIMESTAMP(3) NOT NULL,
    "horizon" INTEGER NOT NULL,
    "fold_id" INTEGER NOT NULL,
    "p10" DOUBLE PRECISION NOT NULL,
    "p50" DOUBLE PRECISION NOT NULL,
    "p90" DOUBLE PRECISION NOT NULL,
    "model_version" TEXT NOT NULL,
    "trained_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "oof_predictions_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "lasso_coefficients" (
    "id" SERIAL NOT NULL,
    "bucket" TEXT NOT NULL,
    "horizon" INTEGER NOT NULL,
    "feature_name" TEXT NOT NULL,
    "coefficient" DOUBLE PRECISION NOT NULL,
    "is_active" BOOLEAN NOT NULL,
    "model_version" TEXT NOT NULL,
    "trained_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "lasso_coefficients_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "meta_ensemble" (
    "id" SERIAL NOT NULL,
    "as_of_date" TIMESTAMP(6) NOT NULL,
    "horizon" INTEGER NOT NULL,
    "p10" DOUBLE PRECISION NOT NULL,
    "p50" DOUBLE PRECISION NOT NULL,
    "p90" DOUBLE PRECISION NOT NULL,
    "model_version" VARCHAR(100) NOT NULL,
    "trained_at" TIMESTAMP(6) NOT NULL,

    CONSTRAINT "meta_ensemble_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "forecast_quantiles" (
    "id" SERIAL NOT NULL,
    "symbol" TEXT NOT NULL,
    "as_of_date" TIMESTAMP(3) NOT NULL,
    "horizon" INTEGER NOT NULL,
    "p10" DOUBLE PRECISION NOT NULL,
    "p50" DOUBLE PRECISION NOT NULL,
    "p90" DOUBLE PRECISION NOT NULL,
    "prob_up" DOUBLE PRECISION NOT NULL,
    "regime" TEXT,
    "confidence" DOUBLE PRECISION,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "forecast_quantiles_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "driver_scores" (
    "id" SERIAL NOT NULL,
    "symbol" TEXT NOT NULL,
    "as_of_date" TIMESTAMP(3) NOT NULL,
    "bucket" TEXT NOT NULL,
    "score" DOUBLE PRECISION NOT NULL,
    "contribution" DOUBLE PRECISION NOT NULL,
    "direction" TEXT NOT NULL,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "driver_scores_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "chart_overlays" (
    "id" SERIAL NOT NULL,
    "symbol" TEXT NOT NULL,
    "overlay_type" TEXT NOT NULL,
    "start_date" TIMESTAMP(3) NOT NULL,
    "end_date" TIMESTAMP(3),
    "label" TEXT NOT NULL,
    "color" TEXT,
    "metadata" JSONB,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "chart_overlays_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "procurement_actions" (
    "id" SERIAL NOT NULL,
    "symbol" TEXT NOT NULL,
    "as_of_date" TIMESTAMP(3) NOT NULL,
    "action" TEXT NOT NULL,
    "confidence" DOUBLE PRECISION NOT NULL,
    "rationale" TEXT,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "procurement_actions_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "value_timing_windows" (
    "id" SERIAL NOT NULL,
    "symbol" TEXT NOT NULL,
    "as_of_date" TIMESTAMP(3) NOT NULL,
    "horizon_days" INTEGER NOT NULL,
    "tail_proximity" DOUBLE PRECISION NOT NULL,
    "probability_lift" DOUBLE PRECISION NOT NULL,
    "confidence_adjusted_lift" DOUBLE PRECISION NOT NULL,
    "regime_dampening" DOUBLE PRECISION,
    "window_start_week" INTEGER,
    "window_end_week" INTEGER,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "value_timing_windows_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "specialist_drivers" (
    "id" SERIAL NOT NULL,
    "driver_id" TEXT NOT NULL,
    "description" TEXT NOT NULL,

    CONSTRAINT "specialist_drivers_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "risk_metrics" (
    "id" SERIAL NOT NULL,
    "as_of_date" TIMESTAMP(6) NOT NULL,
    "horizon" INTEGER NOT NULL,
    "var_01" DOUBLE PRECISION NOT NULL,
    "var_05" DOUBLE PRECISION NOT NULL,
    "var_10" DOUBLE PRECISION NOT NULL,
    "cvar_05" DOUBLE PRECISION NOT NULL,
    "prob_up" DOUBLE PRECISION NOT NULL,
    "prob_up_5pct" DOUBLE PRECISION NOT NULL,
    "prob_down_5pct" DOUBLE PRECISION NOT NULL,
    "regime" VARCHAR(20) NOT NULL,
    "tail_risk_flag" BOOLEAN NOT NULL,
    "created_at" TIMESTAMP(6) DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "risk_metrics_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "monte_carlo_runs" (
    "id" SERIAL NOT NULL,
    "symbol" TEXT NOT NULL,
    "as_of_date" TIMESTAMP(3) NOT NULL,
    "horizon" INTEGER NOT NULL,
    "num_sims" INTEGER NOT NULL,
    "percentiles" JSONB NOT NULL,
    "correlations" JSONB,
    "model_version" TEXT NOT NULL,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "monte_carlo_runs_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "model_registry" (
    "id" SERIAL NOT NULL,
    "model_id" TEXT NOT NULL,
    "source" TEXT NOT NULL,
    "horizon" INTEGER NOT NULL,
    "version" TEXT NOT NULL,
    "trained_at" TIMESTAMP(3) NOT NULL,
    "metrics" JSONB NOT NULL,
    "artifact_path" TEXT NOT NULL,
    "fold_id" INTEGER,
    "is_active" BOOLEAN NOT NULL DEFAULT true,

    CONSTRAINT "model_registry_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "data_quality_log" (
    "id" SERIAL NOT NULL,
    "table_name" TEXT NOT NULL,
    "check_date" TIMESTAMP(3) NOT NULL,
    "row_count" INTEGER NOT NULL,
    "null_count" INTEGER NOT NULL,
    "latest_date" TIMESTAMP(3) NOT NULL,
    "oldest_date" TIMESTAMP(3) NOT NULL,
    "issues" JSONB,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "data_quality_log_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "training_run_log" (
    "id" SERIAL NOT NULL,
    "run_id" TEXT NOT NULL,
    "horizon" INTEGER NOT NULL,
    "phase" TEXT NOT NULL,
    "status" TEXT NOT NULL,
    "started_at" TIMESTAMP(3) NOT NULL,
    "completed_at" TIMESTAMP(3),
    "error_message" TEXT,
    "metrics" JSONB,

    CONSTRAINT "training_run_log_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "options_greeks" (
    "id" SERIAL NOT NULL,
    "instrument_id" BIGINT,
    "raw_symbol" VARCHAR(50),
    "underlying" VARCHAR(10),
    "as_of_date" DATE,
    "expiration_date" DATE,
    "strike_price" DECIMAL(12,4),
    "option_type" VARCHAR(1),
    "open" DECIMAL(10,4),
    "high" DECIMAL(10,4),
    "low" DECIMAL(10,4),
    "close" DECIMAL(10,4),
    "volume" BIGINT,
    "open_interest" BIGINT,
    "underlying_price" DECIMAL(10,4),
    "risk_free_rate" DECIMAL(8,6),
    "implied_volatility" DECIMAL(8,6),
    "delta" DECIMAL(8,6),
    "gamma" DECIMAL(10,8),
    "theta" DECIMAL(10,6),
    "vega" DECIMAL(10,6),
    "days_to_expiry" INTEGER,
    "moneyness" VARCHAR(10),
    "expiry_bucket" VARCHAR(5),
    "created_at" TIMESTAMP(6) DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "options_greeks_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "options_features" (
    "id" SERIAL NOT NULL,
    "underlying" VARCHAR(10),
    "as_of_date" DATE,
    "expiry_bucket" VARCHAR(5),
    "iv_atm_call" DECIMAL(8,6),
    "iv_atm_put" DECIMAL(8,6),
    "iv_skew" DECIMAL(8,6),
    "iv_term_structure" DECIMAL(8,6),
    "iv_percentile_30d" DECIMAL(5,2),
    "iv_rank" DECIMAL(5,2),
    "delta_weighted_oi_call" DECIMAL(18,4),
    "delta_weighted_oi_put" DECIMAL(18,4),
    "gamma_exposure" DECIMAL(18,4),
    "net_gamma" DECIMAL(18,4),
    "vega_exposure" DECIMAL(18,4),
    "theta_decay" DECIMAL(18,4),
    "put_call_ratio_volume" DECIMAL(8,4),
    "put_call_ratio_oi" DECIMAL(8,4),
    "total_volume" BIGINT,
    "total_open_interest" BIGINT,
    "skew_zscore" DECIMAL(6,4),
    "gamma_flip_level" DECIMAL(10,4),
    "max_pain_strike" DECIMAL(10,4),
    "created_at" TIMESTAMP(6) DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "options_features_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "volatility_surface" (
    "id" SERIAL NOT NULL,
    "underlying" VARCHAR(10),
    "as_of_date" DATE,
    "surface_data" JSONB,
    "atm_vol" DECIMAL(8,6),
    "skew_25d" DECIMAL(8,6),
    "butterfly_25d" DECIMAL(8,6),
    "term_slope" DECIMAL(8,6),
    "created_at" TIMESTAMP(6) DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "volatility_surface_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "cftc_cot" (
    "id" SERIAL NOT NULL,
    "report_date" DATE NOT NULL,
    "symbol" VARCHAR(20) NOT NULL,
    "open_interest" BIGINT,
    "prod_merc_long" BIGINT,
    "prod_merc_short" BIGINT,
    "swap_long" BIGINT,
    "swap_short" BIGINT,
    "managed_money_long" BIGINT,
    "managed_money_short" BIGINT,
    "other_rept_long" BIGINT,
    "other_rept_short" BIGINT,
    "nonrept_long" BIGINT,
    "nonrept_short" BIGINT,
    "prod_merc_net" BIGINT,
    "swap_net" BIGINT,
    "managed_money_net" BIGINT,
    "other_rept_net" BIGINT,
    "nonrept_net" BIGINT,
    "managed_money_net_pct_oi" DOUBLE PRECISION,
    "prod_merc_net_pct_oi" DOUBLE PRECISION,
    "source" VARCHAR(50),
    "ingested_at" TIMESTAMP(6) DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "cftc_cot_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "fred_series_metadata" (
    "id" SERIAL NOT NULL,
    "series_id" VARCHAR(50) NOT NULL,
    "title" VARCHAR(500),
    "observation_start" DATE,
    "observation_end" DATE,
    "frequency" VARCHAR(50),
    "units" VARCHAR(200),
    "seasonal_adjustment" VARCHAR(100),
    "last_updated" TIMESTAMP(6),
    "source" VARCHAR(200),
    "notes" TEXT,
    "created_at" TIMESTAMP(6) DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "fred_series_metadata_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "meta_weights" (
    "id" SERIAL NOT NULL,
    "source" VARCHAR(50) NOT NULL,
    "horizon" INTEGER NOT NULL,
    "weight" DOUBLE PRECISION NOT NULL,
    "model_version" VARCHAR(100) NOT NULL,
    "trained_at" TIMESTAMP(6) NOT NULL,

    CONSTRAINT "meta_weights_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "raw_options_futures" (
    "id" SERIAL NOT NULL,
    "symbol" VARCHAR(50) NOT NULL,
    "as_of_date" DATE NOT NULL,
    "open" DOUBLE PRECISION,
    "high" DOUBLE PRECISION,
    "low" DOUBLE PRECISION,
    "close" DOUBLE PRECISION,
    "volume" BIGINT,
    "open_interest" BIGINT,
    "expiration" DATE,
    "strike" DOUBLE PRECISION,
    "option_type" VARCHAR(10),
    "created_at" TIMESTAMP(6) DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "raw_options_futures_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "usda_export_sales" (
    "id" SERIAL NOT NULL,
    "report_date" DATE NOT NULL,
    "commodity" VARCHAR(100) NOT NULL,
    "destination_country" VARCHAR(100),
    "net_sales_mt" DOUBLE PRECISION,
    "exports_mt" DOUBLE PRECISION,
    "outstanding_sales_mt" DOUBLE PRECISION,
    "source" VARCHAR(50),
    "ingested_at" TIMESTAMP(6) DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "usda_export_sales_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "usda_wasde" (
    "id" SERIAL NOT NULL,
    "report_date" DATE NOT NULL,
    "commodity" VARCHAR(100) NOT NULL,
    "country" VARCHAR(100),
    "metric" VARCHAR(200),
    "value" DOUBLE PRECISION,
    "unit" VARCHAR(50),
    "source" VARCHAR(50),
    "ingested_at" TIMESTAMP(6) DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "usda_wasde_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "weather_noaa" (
    "id" SERIAL NOT NULL,
    "station_id" VARCHAR(50) NOT NULL,
    "as_of_date" DATE NOT NULL,
    "tavg_c" DOUBLE PRECISION,
    "tmin_c" DOUBLE PRECISION,
    "tmax_c" DOUBLE PRECISION,
    "prcp_mm" DOUBLE PRECISION,
    "snow_mm" DOUBLE PRECISION,
    "region" VARCHAR(100),
    "ingested_at" TIMESTAMP(6) DEFAULT CURRENT_TIMESTAMP,
    "awnd_ms" DOUBLE PRECISION,
    "specialist_bucket" VARCHAR(50),
    "country" VARCHAR(50),

    CONSTRAINT "weather_noaa_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "dashboard_metrics" (
    "id" SERIAL NOT NULL,
    "metric_type" VARCHAR(50) NOT NULL,
    "as_of_date" DATE NOT NULL,
    "symbol" VARCHAR(20),
    "horizon" INTEGER,
    "value" DOUBLE PRECISION,
    "metadata" JSONB,
    "updated_at" TIMESTAMP(6) DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "dashboard_metrics_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "garch_forecasts" (
    "id" SERIAL NOT NULL,
    "symbol" VARCHAR(20) NOT NULL,
    "as_of_date" DATE NOT NULL,
    "horizon" INTEGER NOT NULL,
    "conditional_vol" DOUBLE PRECISION NOT NULL,
    "annualized_vol" DOUBLE PRECISION NOT NULL,
    "var_01" DOUBLE PRECISION,
    "var_05" DOUBLE PRECISION,
    "cvar_05" DOUBLE PRECISION,
    "vol_lower" DOUBLE PRECISION,
    "vol_upper" DOUBLE PRECISION,
    "model_type" VARCHAR(50),
    "model_version" VARCHAR(100),
    "created_at" TIMESTAMP(6) DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "garch_forecasts_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "garch_parameters" (
    "id" SERIAL NOT NULL,
    "symbol" VARCHAR(20) NOT NULL,
    "model_type" VARCHAR(50) NOT NULL,
    "p" INTEGER NOT NULL,
    "q" INTEGER NOT NULL,
    "omega" DOUBLE PRECISION NOT NULL,
    "alpha" JSONB NOT NULL,
    "beta" JSONB NOT NULL,
    "gamma" JSONB,
    "distribution" VARCHAR(20),
    "df" DOUBLE PRECISION,
    "log_likelihood" DOUBLE PRECISION,
    "aic" DOUBLE PRECISION,
    "bic" DOUBLE PRECISION,
    "model_version" VARCHAR(100),
    "trained_at" TIMESTAMP(6),
    "created_at" TIMESTAMP(6) DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "garch_parameters_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "probability_distributions" (
    "id" SERIAL NOT NULL,
    "symbol" VARCHAR(20) NOT NULL,
    "as_of_date" DATE NOT NULL,
    "horizon" INTEGER NOT NULL,
    "percentile" DOUBLE PRECISION NOT NULL,
    "value" DOUBLE PRECISION NOT NULL,
    "model_version" VARCHAR(100),
    "created_at" TIMESTAMP(6) DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "probability_distributions_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "realized_volatility" (
    "id" SERIAL NOT NULL,
    "symbol" VARCHAR(20) NOT NULL,
    "as_of_date" DATE NOT NULL,
    "window_days" INTEGER NOT NULL,
    "realized_vol" DOUBLE PRECISION NOT NULL,
    "parkinson_vol" DOUBLE PRECISION,
    "garman_klass_vol" DOUBLE PRECISION,
    "yang_zhang_vol" DOUBLE PRECISION,
    "annualized" BOOLEAN DEFAULT true,
    "created_at" TIMESTAMP(6) DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "realized_volatility_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "regime_probabilities" (
    "id" SERIAL NOT NULL,
    "as_of_date" DATE NOT NULL,
    "regime_type" VARCHAR(50) NOT NULL,
    "regime_name" VARCHAR(100) NOT NULL,
    "probability" DOUBLE PRECISION NOT NULL,
    "confidence" DOUBLE PRECISION,
    "drivers" JSONB,
    "model_version" VARCHAR(100),
    "created_at" TIMESTAMP(6) DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "regime_probabilities_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "scenario_analysis" (
    "id" SERIAL NOT NULL,
    "scenario_id" VARCHAR(100) NOT NULL,
    "scenario_name" VARCHAR(200) NOT NULL,
    "as_of_date" DATE NOT NULL,
    "horizon" INTEGER NOT NULL,
    "assumptions" JSONB NOT NULL,
    "base_forecast" DOUBLE PRECISION,
    "scenario_forecast" DOUBLE PRECISION,
    "impact_pct" DOUBLE PRECISION,
    "probability" DOUBLE PRECISION,
    "confidence" VARCHAR(20),
    "model_version" VARCHAR(100),
    "created_at" TIMESTAMP(6) DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "scenario_analysis_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "shap_summary" (
    "id" SERIAL NOT NULL,
    "horizon" INTEGER NOT NULL,
    "feature_name" VARCHAR(100) NOT NULL,
    "mean_abs_shap" DOUBLE PRECISION NOT NULL,
    "std_shap" DOUBLE PRECISION,
    "rank" INTEGER,
    "model_version" VARCHAR(100),
    "trained_at" TIMESTAMP(6),
    "created_at" TIMESTAMP(6) DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "shap_summary_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "shap_values" (
    "id" SERIAL NOT NULL,
    "as_of_date" DATE NOT NULL,
    "horizon" INTEGER NOT NULL,
    "feature_name" VARCHAR(100) NOT NULL,
    "shap_value" DOUBLE PRECISION NOT NULL,
    "base_value" DOUBLE PRECISION,
    "prediction" DOUBLE PRECISION,
    "model_version" VARCHAR(100),
    "created_at" TIMESTAMP(6) DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "shap_values_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "vol_regimes" (
    "id" SERIAL NOT NULL,
    "symbol" VARCHAR(20) NOT NULL,
    "as_of_date" DATE NOT NULL,
    "regime" VARCHAR(20) NOT NULL,
    "regime_prob" DOUBLE PRECISION,
    "transition_probs" JSONB,
    "smoothed_prob" DOUBLE PRECISION,
    "model_type" VARCHAR(50),
    "model_version" VARCHAR(100),
    "created_at" TIMESTAMP(6) DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "vol_regimes_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE INDEX "raw_market_futures_symbol_idx" ON "raw_market_futures"("symbol");

-- CreateIndex
CREATE INDEX "raw_market_futures_as_of_date_idx" ON "raw_market_futures"("as_of_date");

-- CreateIndex
CREATE INDEX "idx_futures_date" ON "raw_market_futures"("as_of_date");

-- CreateIndex
CREATE INDEX "idx_futures_symbol" ON "raw_market_futures"("symbol");

-- CreateIndex
CREATE UNIQUE INDEX "raw_market_futures_symbol_as_of_date_key" ON "raw_market_futures"("symbol", "as_of_date");

-- CreateIndex
CREATE INDEX "raw_fred_observations_series_id_idx" ON "raw_fred_observations"("series_id");

-- CreateIndex
CREATE INDEX "raw_fred_observations_as_of_date_idx" ON "raw_fred_observations"("as_of_date");

-- CreateIndex
CREATE INDEX "idx_fred_date" ON "raw_fred_observations"("as_of_date");

-- CreateIndex
CREATE INDEX "idx_fred_series" ON "raw_fred_observations"("series_id");

-- CreateIndex
CREATE UNIQUE INDEX "raw_fred_observations_series_id_as_of_date_key" ON "raw_fred_observations"("series_id", "as_of_date");

-- CreateIndex
CREATE INDEX "raw_fx_spot_pair_idx" ON "raw_fx_spot"("pair");

-- CreateIndex
CREATE INDEX "raw_fx_spot_as_of_date_idx" ON "raw_fx_spot"("as_of_date");

-- CreateIndex
CREATE UNIQUE INDEX "raw_fx_spot_pair_as_of_date_key" ON "raw_fx_spot"("pair", "as_of_date");

-- CreateIndex
CREATE INDEX "raw_weather_observations_station_id_idx" ON "raw_weather_observations"("station_id");

-- CreateIndex
CREATE INDEX "raw_weather_observations_as_of_date_idx" ON "raw_weather_observations"("as_of_date");

-- CreateIndex
CREATE UNIQUE INDEX "raw_weather_observations_station_id_as_of_date_key" ON "raw_weather_observations"("station_id", "as_of_date");

-- CreateIndex
CREATE INDEX "raw_epa_rin_prices_rin_type_idx" ON "raw_epa_rin_prices"("rin_type");

-- CreateIndex
CREATE INDEX "raw_epa_rin_prices_as_of_date_idx" ON "raw_epa_rin_prices"("as_of_date");

-- CreateIndex
CREATE UNIQUE INDEX "raw_epa_rin_prices_rin_type_as_of_date_key" ON "raw_epa_rin_prices"("rin_type", "as_of_date");

-- CreateIndex
CREATE INDEX "raw_cftc_cot_contract_code_idx" ON "raw_cftc_cot"("contract_code");

-- CreateIndex
CREATE INDEX "raw_cftc_cot_as_of_date_idx" ON "raw_cftc_cot"("as_of_date");

-- CreateIndex
CREATE UNIQUE INDEX "raw_cftc_cot_contract_code_as_of_date_key" ON "raw_cftc_cot"("contract_code", "as_of_date");

-- CreateIndex
CREATE INDEX "cv_folds_horizon_idx" ON "cv_folds"("horizon");

-- CreateIndex
CREATE INDEX "cv_folds_as_of_date_idx" ON "cv_folds"("as_of_date");

-- CreateIndex
CREATE UNIQUE INDEX "cv_folds_as_of_date_horizon_fold_id_key" ON "cv_folds"("as_of_date", "horizon", "fold_id");

-- CreateIndex
CREATE INDEX "specialist_features_bucket_idx" ON "specialist_features"("bucket");

-- CreateIndex
CREATE INDEX "specialist_features_as_of_date_idx" ON "specialist_features"("as_of_date");

-- CreateIndex
CREATE UNIQUE INDEX "specialist_features_bucket_as_of_date_key" ON "specialist_features"("bucket", "as_of_date");

-- CreateIndex
CREATE UNIQUE INDEX "core_features_as_of_date_key" ON "core_features"("as_of_date");

-- CreateIndex
CREATE INDEX "core_features_as_of_date_idx" ON "core_features"("as_of_date");

-- CreateIndex
CREATE INDEX "oof_predictions_source_idx" ON "oof_predictions"("source");

-- CreateIndex
CREATE INDEX "oof_predictions_horizon_idx" ON "oof_predictions"("horizon");

-- CreateIndex
CREATE INDEX "oof_predictions_as_of_date_idx" ON "oof_predictions"("as_of_date");

-- CreateIndex
CREATE UNIQUE INDEX "oof_predictions_source_as_of_date_horizon_fold_id_key" ON "oof_predictions"("source", "as_of_date", "horizon", "fold_id");

-- CreateIndex
CREATE INDEX "lasso_coefficients_bucket_idx" ON "lasso_coefficients"("bucket");

-- CreateIndex
CREATE INDEX "lasso_coefficients_horizon_idx" ON "lasso_coefficients"("horizon");

-- CreateIndex
CREATE INDEX "lasso_coefficients_is_active_idx" ON "lasso_coefficients"("is_active");

-- CreateIndex
CREATE UNIQUE INDEX "lasso_coefficients_bucket_horizon_feature_name_model_versio_key" ON "lasso_coefficients"("bucket", "horizon", "feature_name", "model_version");

-- CreateIndex
CREATE INDEX "idx_meta_ensemble_horizon" ON "meta_ensemble"("horizon");

-- CreateIndex
CREATE UNIQUE INDEX "meta_ensemble_as_of_date_horizon_key" ON "meta_ensemble"("as_of_date", "horizon");

-- CreateIndex
CREATE INDEX "forecast_quantiles_symbol_idx" ON "forecast_quantiles"("symbol");

-- CreateIndex
CREATE INDEX "forecast_quantiles_horizon_idx" ON "forecast_quantiles"("horizon");

-- CreateIndex
CREATE INDEX "forecast_quantiles_as_of_date_idx" ON "forecast_quantiles"("as_of_date");

-- CreateIndex
CREATE UNIQUE INDEX "forecast_quantiles_symbol_as_of_date_horizon_key" ON "forecast_quantiles"("symbol", "as_of_date", "horizon");

-- CreateIndex
CREATE INDEX "driver_scores_symbol_idx" ON "driver_scores"("symbol");

-- CreateIndex
CREATE INDEX "driver_scores_bucket_idx" ON "driver_scores"("bucket");

-- CreateIndex
CREATE INDEX "driver_scores_as_of_date_idx" ON "driver_scores"("as_of_date");

-- CreateIndex
CREATE UNIQUE INDEX "driver_scores_symbol_as_of_date_bucket_key" ON "driver_scores"("symbol", "as_of_date", "bucket");

-- CreateIndex
CREATE INDEX "chart_overlays_symbol_idx" ON "chart_overlays"("symbol");

-- CreateIndex
CREATE INDEX "chart_overlays_overlay_type_idx" ON "chart_overlays"("overlay_type");

-- CreateIndex
CREATE INDEX "chart_overlays_start_date_idx" ON "chart_overlays"("start_date");

-- CreateIndex
CREATE INDEX "procurement_actions_symbol_idx" ON "procurement_actions"("symbol");

-- CreateIndex
CREATE INDEX "procurement_actions_as_of_date_idx" ON "procurement_actions"("as_of_date");

-- CreateIndex
CREATE UNIQUE INDEX "procurement_actions_symbol_as_of_date_key" ON "procurement_actions"("symbol", "as_of_date");

-- CreateIndex
CREATE INDEX "value_timing_windows_symbol_idx" ON "value_timing_windows"("symbol");

-- CreateIndex
CREATE INDEX "value_timing_windows_horizon_days_idx" ON "value_timing_windows"("horizon_days");

-- CreateIndex
CREATE INDEX "value_timing_windows_as_of_date_idx" ON "value_timing_windows"("as_of_date");

-- CreateIndex
CREATE UNIQUE INDEX "value_timing_windows_symbol_as_of_date_horizon_days_key" ON "value_timing_windows"("symbol", "as_of_date", "horizon_days");

-- CreateIndex
CREATE UNIQUE INDEX "specialist_drivers_driver_id_key" ON "specialist_drivers"("driver_id");

-- CreateIndex
CREATE UNIQUE INDEX "risk_metrics_as_of_date_horizon_key" ON "risk_metrics"("as_of_date", "horizon");

-- CreateIndex
CREATE INDEX "monte_carlo_runs_symbol_idx" ON "monte_carlo_runs"("symbol");

-- CreateIndex
CREATE INDEX "monte_carlo_runs_horizon_idx" ON "monte_carlo_runs"("horizon");

-- CreateIndex
CREATE INDEX "monte_carlo_runs_as_of_date_idx" ON "monte_carlo_runs"("as_of_date");

-- CreateIndex
CREATE UNIQUE INDEX "monte_carlo_runs_symbol_as_of_date_horizon_model_version_key" ON "monte_carlo_runs"("symbol", "as_of_date", "horizon", "model_version");

-- CreateIndex
CREATE UNIQUE INDEX "model_registry_model_id_key" ON "model_registry"("model_id");

-- CreateIndex
CREATE INDEX "model_registry_source_idx" ON "model_registry"("source");

-- CreateIndex
CREATE INDEX "model_registry_horizon_idx" ON "model_registry"("horizon");

-- CreateIndex
CREATE INDEX "model_registry_is_active_idx" ON "model_registry"("is_active");

-- CreateIndex
CREATE INDEX "data_quality_log_table_name_idx" ON "data_quality_log"("table_name");

-- CreateIndex
CREATE INDEX "data_quality_log_check_date_idx" ON "data_quality_log"("check_date");

-- CreateIndex
CREATE UNIQUE INDEX "training_run_log_run_id_key" ON "training_run_log"("run_id");

-- CreateIndex
CREATE INDEX "training_run_log_horizon_idx" ON "training_run_log"("horizon");

-- CreateIndex
CREATE INDEX "training_run_log_phase_idx" ON "training_run_log"("phase");

-- CreateIndex
CREATE INDEX "training_run_log_status_idx" ON "training_run_log"("status");

-- CreateIndex
CREATE INDEX "idx_options_greeks_date" ON "options_greeks"("as_of_date");

-- CreateIndex
CREATE INDEX "idx_options_greeks_expiry" ON "options_greeks"("expiry_bucket");

-- CreateIndex
CREATE INDEX "idx_options_greeks_moneyness" ON "options_greeks"("moneyness");

-- CreateIndex
CREATE INDEX "idx_options_greeks_underlying" ON "options_greeks"("underlying");

-- CreateIndex
CREATE UNIQUE INDEX "options_greeks_instrument_id_as_of_date_key" ON "options_greeks"("instrument_id", "as_of_date");

-- CreateIndex
CREATE INDEX "idx_options_features_date" ON "options_features"("as_of_date");

-- CreateIndex
CREATE INDEX "idx_options_features_underlying" ON "options_features"("underlying");

-- CreateIndex
CREATE UNIQUE INDEX "options_features_underlying_as_of_date_expiry_bucket_key" ON "options_features"("underlying", "as_of_date", "expiry_bucket");

-- CreateIndex
CREATE INDEX "idx_vol_surface_date" ON "volatility_surface"("as_of_date");

-- CreateIndex
CREATE INDEX "idx_vol_surface_underlying" ON "volatility_surface"("underlying");

-- CreateIndex
CREATE UNIQUE INDEX "volatility_surface_underlying_as_of_date_key" ON "volatility_surface"("underlying", "as_of_date");

-- CreateIndex
CREATE INDEX "idx_cftc_date" ON "cftc_cot"("report_date");

-- CreateIndex
CREATE INDEX "idx_cftc_symbol" ON "cftc_cot"("symbol");

-- CreateIndex
CREATE UNIQUE INDEX "cftc_cot_report_date_symbol_key" ON "cftc_cot"("report_date", "symbol");

-- CreateIndex
CREATE UNIQUE INDEX "fred_series_metadata_series_id_key" ON "fred_series_metadata"("series_id");

-- CreateIndex
CREATE INDEX "idx_meta_weights_horizon" ON "meta_weights"("horizon");

-- CreateIndex
CREATE UNIQUE INDEX "meta_weights_source_horizon_model_version_key" ON "meta_weights"("source", "horizon", "model_version");

-- CreateIndex
CREATE INDEX "idx_options_date" ON "raw_options_futures"("as_of_date");

-- CreateIndex
CREATE INDEX "idx_options_symbol" ON "raw_options_futures"("symbol");

-- CreateIndex
CREATE UNIQUE INDEX "raw_options_futures_symbol_as_of_date_key" ON "raw_options_futures"("symbol", "as_of_date");

-- CreateIndex
CREATE INDEX "idx_usda_commodity" ON "usda_export_sales"("commodity");

-- CreateIndex
CREATE INDEX "idx_usda_date" ON "usda_export_sales"("report_date");

-- CreateIndex
CREATE INDEX "idx_usda_exports_commodity" ON "usda_export_sales"("commodity");

-- CreateIndex
CREATE INDEX "idx_usda_exports_date" ON "usda_export_sales"("report_date");

-- CreateIndex
CREATE UNIQUE INDEX "usda_export_sales_report_date_commodity_destination_country_key" ON "usda_export_sales"("report_date", "commodity", "destination_country");

-- CreateIndex
CREATE INDEX "idx_wasde_commodity" ON "usda_wasde"("commodity");

-- CreateIndex
CREATE INDEX "idx_wasde_date" ON "usda_wasde"("report_date");

-- CreateIndex
CREATE UNIQUE INDEX "usda_wasde_report_date_commodity_country_metric_key" ON "usda_wasde"("report_date", "commodity", "country", "metric");

-- CreateIndex
CREATE INDEX "idx_weather_bucket" ON "weather_noaa"("specialist_bucket");

-- CreateIndex
CREATE INDEX "idx_weather_date" ON "weather_noaa"("as_of_date");

-- CreateIndex
CREATE INDEX "idx_weather_region" ON "weather_noaa"("region");

-- CreateIndex
CREATE UNIQUE INDEX "weather_noaa_station_id_as_of_date_key" ON "weather_noaa"("station_id", "as_of_date");

-- CreateIndex
CREATE INDEX "idx_dashboard_date" ON "dashboard_metrics"("as_of_date");

-- CreateIndex
CREATE INDEX "idx_dashboard_type" ON "dashboard_metrics"("metric_type");

-- CreateIndex
CREATE UNIQUE INDEX "dashboard_metrics_metric_type_as_of_date_symbol_horizon_key" ON "dashboard_metrics"("metric_type", "as_of_date", "symbol", "horizon");

-- CreateIndex
CREATE INDEX "idx_garch_forecast_date" ON "garch_forecasts"("as_of_date");

-- CreateIndex
CREATE INDEX "idx_garch_forecast_symbol" ON "garch_forecasts"("symbol");

-- CreateIndex
CREATE UNIQUE INDEX "garch_forecasts_symbol_as_of_date_horizon_model_version_key" ON "garch_forecasts"("symbol", "as_of_date", "horizon", "model_version");

-- CreateIndex
CREATE INDEX "idx_garch_params_symbol" ON "garch_parameters"("symbol");

-- CreateIndex
CREATE UNIQUE INDEX "garch_parameters_symbol_model_type_p_q_model_version_key" ON "garch_parameters"("symbol", "model_type", "p", "q", "model_version");

-- CreateIndex
CREATE INDEX "idx_prob_dist_date" ON "probability_distributions"("as_of_date");

-- CreateIndex
CREATE INDEX "idx_prob_dist_symbol" ON "probability_distributions"("symbol");

-- CreateIndex
CREATE UNIQUE INDEX "probability_distributions_symbol_as_of_date_horizon_percent_key" ON "probability_distributions"("symbol", "as_of_date", "horizon", "percentile");

-- CreateIndex
CREATE INDEX "idx_realized_vol_date" ON "realized_volatility"("as_of_date");

-- CreateIndex
CREATE INDEX "idx_realized_vol_symbol" ON "realized_volatility"("symbol");

-- CreateIndex
CREATE UNIQUE INDEX "realized_volatility_symbol_as_of_date_window_days_key" ON "realized_volatility"("symbol", "as_of_date", "window_days");

-- CreateIndex
CREATE INDEX "idx_regime_prob_date" ON "regime_probabilities"("as_of_date");

-- CreateIndex
CREATE UNIQUE INDEX "regime_probabilities_as_of_date_regime_type_regime_name_key" ON "regime_probabilities"("as_of_date", "regime_type", "regime_name");

-- CreateIndex
CREATE INDEX "idx_scenario_date" ON "scenario_analysis"("as_of_date");

-- CreateIndex
CREATE UNIQUE INDEX "scenario_analysis_scenario_id_as_of_date_horizon_key" ON "scenario_analysis"("scenario_id", "as_of_date", "horizon");

-- CreateIndex
CREATE INDEX "idx_shap_summary_horizon" ON "shap_summary"("horizon");

-- CreateIndex
CREATE UNIQUE INDEX "shap_summary_horizon_feature_name_model_version_key" ON "shap_summary"("horizon", "feature_name", "model_version");

-- CreateIndex
CREATE INDEX "idx_shap_values_date" ON "shap_values"("as_of_date");

-- CreateIndex
CREATE INDEX "idx_shap_values_horizon" ON "shap_values"("horizon");

-- CreateIndex
CREATE UNIQUE INDEX "shap_values_as_of_date_horizon_feature_name_model_version_key" ON "shap_values"("as_of_date", "horizon", "feature_name", "model_version");

-- CreateIndex
CREATE INDEX "idx_vol_regime_date" ON "vol_regimes"("as_of_date");

-- CreateIndex
CREATE INDEX "idx_vol_regime_symbol" ON "vol_regimes"("symbol");

-- CreateIndex
CREATE UNIQUE INDEX "vol_regimes_symbol_as_of_date_model_version_key" ON "vol_regimes"("symbol", "as_of_date", "model_version");
