-- Schema Naming Cleanup Migration
-- Phases 2-5 of the naming convention audit
--
-- Phase 2: ZL table renames + symbol column + drops
-- Phase 3: Horizon table consolidation (12 → 3)
-- Phase 4: Grain suffix renames (10 tables)
-- Phase 5: Quantile column renames (6 columns)

-- ============================================================
-- PHASE 2A: Rename ZL tables (5 tables)
-- ============================================================

ALTER TABLE analytics.zl_price_5m RENAME TO price_5m;
ALTER TABLE analytics.zl_price_15m RENAME TO price_15m;
ALTER TABLE analytics.zl_price_1h RENAME TO price_1h;
ALTER TABLE analytics.zl_price_1d RENAME TO price_1d;
ALTER TABLE analytics.zl_latest RENAME TO latest_price;

-- ============================================================
-- PHASE 2B: Add symbol column to renamed tables
-- ============================================================

ALTER TABLE analytics.price_5m ADD COLUMN symbol VARCHAR(20) NOT NULL DEFAULT 'ZL';
ALTER TABLE analytics.price_15m ADD COLUMN symbol VARCHAR(20) NOT NULL DEFAULT 'ZL';
ALTER TABLE analytics.price_1h ADD COLUMN symbol VARCHAR(20) NOT NULL DEFAULT 'ZL';
ALTER TABLE analytics.price_1d ADD COLUMN symbol VARCHAR(20) NOT NULL DEFAULT 'ZL';
ALTER TABLE analytics.latest_price ADD COLUMN symbol VARCHAR(20) NOT NULL DEFAULT 'ZL';

-- ============================================================
-- PHASE 2C: Update constraints for multi-symbol support
-- ============================================================

-- price_5m: old unique was (timestamp), new is (symbol, timestamp)
ALTER TABLE analytics.price_5m DROP CONSTRAINT IF EXISTS zl_price_5m_timestamp_key;
ALTER TABLE analytics.price_5m ADD CONSTRAINT price_5m_symbol_timestamp_key UNIQUE (symbol, "timestamp");
CREATE INDEX IF NOT EXISTS idx_price_5m_symbol ON analytics.price_5m (symbol);

-- price_15m: old unique was (timestamp), new is (symbol, timestamp)
ALTER TABLE analytics.price_15m DROP CONSTRAINT IF EXISTS zl_price_15m_timestamp_key;
ALTER TABLE analytics.price_15m ADD CONSTRAINT price_15m_symbol_timestamp_key UNIQUE (symbol, "timestamp");
DROP INDEX IF EXISTS analytics.idx_zl_price_15m_ts;
CREATE INDEX IF NOT EXISTS idx_price_15m_ts ON analytics.price_15m ("timestamp" DESC);
CREATE INDEX IF NOT EXISTS idx_price_15m_symbol ON analytics.price_15m (symbol);

-- price_1h: old PK was (timestamp), need to restructure for multi-symbol
-- Add auto-increment id, change PK, add unique(symbol, timestamp)
ALTER TABLE analytics.price_1h DROP CONSTRAINT zl_price_1h_pkey;
ALTER TABLE analytics.price_1h ADD COLUMN id SERIAL;
ALTER TABLE analytics.price_1h ADD CONSTRAINT price_1h_pkey PRIMARY KEY (id);
ALTER TABLE analytics.price_1h ADD CONSTRAINT price_1h_symbol_timestamp_key UNIQUE (symbol, "timestamp");
DROP INDEX IF EXISTS analytics.idx_zl_price_1h_ts;
CREATE INDEX IF NOT EXISTS idx_price_1h_ts ON analytics.price_1h ("timestamp" DESC);
CREATE INDEX IF NOT EXISTS idx_price_1h_symbol ON analytics.price_1h (symbol);

-- price_1d: old PK was (event_date), need to restructure for multi-symbol
ALTER TABLE analytics.price_1d DROP CONSTRAINT zl_price_1d_pkey;
ALTER TABLE analytics.price_1d ADD COLUMN id SERIAL;
ALTER TABLE analytics.price_1d ADD CONSTRAINT price_1d_pkey PRIMARY KEY (id);
ALTER TABLE analytics.price_1d ADD CONSTRAINT price_1d_symbol_event_date_key UNIQUE (symbol, event_date);
DROP INDEX IF EXISTS analytics.idx_zl_price_1d_date;
CREATE INDEX IF NOT EXISTS idx_price_1d_date ON analytics.price_1d (event_date DESC);
CREATE INDEX IF NOT EXISTS idx_price_1d_symbol ON analytics.price_1d (symbol);

-- latest_price: no constraint changes needed (PK is id)

-- ============================================================
-- PHASE 2D: Drop dead ZL tables
-- ============================================================

DROP TABLE IF EXISTS analytics.zl_price_1m;
DROP TABLE IF EXISTS analytics.zl_forming_bar;
DROP TABLE IF EXISTS analytics.zl_price_1d_yahoo_backup;

-- ============================================================
-- PHASE 3: Horizon table consolidation (12 → 3)
-- ============================================================

-- 3A: Create consolidated production_1d
CREATE TABLE forecasts.production_1d (
  id            SERIAL PRIMARY KEY,
  horizon       INTEGER NOT NULL,
  as_of_date    DATE NOT NULL,
  forecast_date DATE NOT NULL,
  p30           DECIMAL(10, 4),
  p50           DECIMAL(10, 4),
  p70           DECIMAL(10, 4),
  p10_cal       DECIMAL(10, 4),
  p90_cal       DECIMAL(10, 4),
  price_p30     DECIMAL(10, 4),
  price_p50     DECIMAL(10, 4),
  price_p70     DECIMAL(10, 4),
  price_p10_cal DECIMAL(10, 4),
  price_p90_cal DECIMAL(10, 4),
  current_price DECIMAL(10, 4),
  model_version TEXT,
  run_id        TEXT,
  created_at    TIMESTAMPTZ DEFAULT NOW(),
  CONSTRAINT production_1d_horizon_as_of_date_key UNIQUE (horizon, as_of_date)
);

CREATE INDEX idx_production_date ON forecasts.production_1d (as_of_date);
CREATE INDEX idx_production_horizon ON forecasts.production_1d (horizon);

-- Migrate data from 4 horizon-specific tables into consolidated table
INSERT INTO forecasts.production_1d (horizon, as_of_date, forecast_date, p30, p50, p70, p10_cal, p90_cal, price_p30, price_p50, price_p70, price_p10_cal, price_p90_cal, current_price, model_version, run_id, created_at)
SELECT 5, as_of_date, forecast_date, p30, p50, p70, p10_cal, p90_cal, price_p30, price_p50, price_p70, price_p10_cal, price_p90_cal, current_price, model_version, run_id, created_at
FROM forecasts.production_5d_1d;

INSERT INTO forecasts.production_1d (horizon, as_of_date, forecast_date, p30, p50, p70, p10_cal, p90_cal, price_p30, price_p50, price_p70, price_p10_cal, price_p90_cal, current_price, model_version, run_id, created_at)
SELECT 21, as_of_date, forecast_date, p30, p50, p70, p10_cal, p90_cal, price_p30, price_p50, price_p70, price_p10_cal, price_p90_cal, current_price, model_version, run_id, created_at
FROM forecasts.production_21d_1d;

INSERT INTO forecasts.production_1d (horizon, as_of_date, forecast_date, p30, p50, p70, p10_cal, p90_cal, price_p30, price_p50, price_p70, price_p10_cal, price_p90_cal, current_price, model_version, run_id, created_at)
SELECT 63, as_of_date, forecast_date, p30, p50, p70, p10_cal, p90_cal, price_p30, price_p50, price_p70, price_p10_cal, price_p90_cal, current_price, model_version, run_id, created_at
FROM forecasts.production_63d_1d;

INSERT INTO forecasts.production_1d (horizon, as_of_date, forecast_date, p30, p50, p70, p10_cal, p90_cal, price_p30, price_p50, price_p70, price_p10_cal, price_p90_cal, current_price, model_version, run_id, created_at)
SELECT 126, as_of_date, forecast_date, p30, p50, p70, p10_cal, p90_cal, price_p30, price_p50, price_p70, price_p10_cal, price_p90_cal, current_price, model_version, run_id, created_at
FROM forecasts.production_126d_1d;

-- Drop old production tables
DROP TABLE forecasts.production_5d_1d;
DROP TABLE forecasts.production_21d_1d;
DROP TABLE forecasts.production_63d_1d;
DROP TABLE forecasts.production_126d_1d;

-- 3B: Create consolidated price_scenarios_1d
CREATE TABLE analytics.price_scenarios_1d (
  id            SERIAL PRIMARY KEY,
  horizon       INTEGER NOT NULL,
  as_of_date    DATE NOT NULL,
  axis          TEXT NOT NULL,
  scenario_name TEXT NOT NULL,
  p_scenario    DECIMAL(5, 4),
  p30           DECIMAL(10, 4),
  p50           DECIMAL(10, 4),
  p70           DECIMAL(10, 4),
  p10_cal       DECIMAL(10, 4),
  p90_cal       DECIMAL(10, 4),
  price_p30     DECIMAL(10, 4),
  price_p50     DECIMAL(10, 4),
  price_p70     DECIMAL(10, 4),
  drivers_topk  JSONB,
  display_order INTEGER,
  color_code    TEXT,
  model_version TEXT,
  created_at    TIMESTAMPTZ DEFAULT NOW(),
  CONSTRAINT price_scenarios_1d_horizon_date_axis_name_key UNIQUE (horizon, as_of_date, axis, scenario_name)
);

CREATE INDEX idx_scenarios_axis ON analytics.price_scenarios_1d (axis);
CREATE INDEX idx_scenarios_date ON analytics.price_scenarios_1d (as_of_date);
CREATE INDEX idx_scenarios_horizon ON analytics.price_scenarios_1d (horizon);

-- Old scenario tables are empty (0 rows) — just drop them
DROP TABLE analytics.price_scenarios_5d_1d;
DROP TABLE analytics.price_scenarios_21d_1d;
DROP TABLE analytics.price_scenarios_63d_1d;
DROP TABLE analytics.price_scenarios_126d_1d;

-- 3C: Create consolidated event_probabilities_1d
CREATE TABLE analytics.event_probabilities_1d (
  id             SERIAL PRIMARY KEY,
  horizon        INTEGER NOT NULL,
  as_of_date     DATE NOT NULL,
  event_type     TEXT NOT NULL,
  window_start   DATE,
  window_end     DATE,
  p_event        DECIMAL(5, 4),
  severity_score DECIMAL(5, 4),
  confidence     DECIMAL(5, 4),
  drivers_topk   JSONB,
  model_version  TEXT,
  created_at     TIMESTAMPTZ DEFAULT NOW(),
  CONSTRAINT event_probabilities_1d_horizon_date_type_key UNIQUE (horizon, as_of_date, event_type)
);

CREATE INDEX idx_event_prob_date ON analytics.event_probabilities_1d (as_of_date);
CREATE INDEX idx_event_prob_type ON analytics.event_probabilities_1d (event_type);
CREATE INDEX idx_event_prob_horizon ON analytics.event_probabilities_1d (horizon);

-- Old event_probabilities tables are empty (0 rows) — just drop them
DROP TABLE analytics.event_probabilities_5d_1d;
DROP TABLE analytics.event_probabilities_21d_1d;
DROP TABLE analytics.event_probabilities_63d_1d;
DROP TABLE analytics.event_probabilities_126d_1d;

-- ============================================================
-- PHASE 4: Grain suffix renames (10 tables)
-- ============================================================

-- Alt schema (6 tables)
ALTER TABLE alt.econ_news RENAME TO econ_news_event;
ALTER TABLE alt.executive_actions RENAME TO executive_actions_event;
ALTER TABLE alt.ice_enforcement RENAME TO ice_enforcement_event;
ALTER TABLE alt.policy_news RENAME TO policy_news_event;
ALTER TABLE alt.profarmer_news RENAME TO profarmer_news_event;
ALTER TABLE alt.tariff_deadlines RENAME TO tariff_deadlines_static;

-- Features schema (1 table)
ALTER TABLE features.intel_drops RENAME TO intel_drops_event;

-- Training schema (3 tables)
ALTER TABLE training.model_runs RENAME TO model_runs_event;
ALTER TABLE training.realized_volatility RENAME TO realized_volatility_1d;
ALTER TABLE training.volatility_surface RENAME TO volatility_surface_1d;

-- ============================================================
-- PHASE 5: Quantile column renames (6 columns)
-- ============================================================

-- core_mc_1d: q10→p10, q50→p50, q90→p90
ALTER TABLE forecasts.core_mc_1d RENAME COLUMN q10 TO p10;
ALTER TABLE forecasts.core_mc_1d RENAME COLUMN q50 TO p50;
ALTER TABLE forecasts.core_mc_1d RENAME COLUMN q90 TO p90;

-- prediction_accuracy: pred_p50→p50, pred_p10→p10, pred_p90→p90
ALTER TABLE ops.prediction_accuracy RENAME COLUMN pred_p50 TO p50;
ALTER TABLE ops.prediction_accuracy RENAME COLUMN pred_p10 TO p10;
ALTER TABLE ops.prediction_accuracy RENAME COLUMN pred_p90 TO p90;
