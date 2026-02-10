-- Create critical missing supply tables for Palm, Argentina Crush, Brazil Production
-- These are ESSENTIAL for palm and crush specialists

-- Drop unused worldbank table
DROP TABLE IF EXISTS supply.worldbank_imports_1y CASCADE;

-- ============================================================================
-- 1. MPOB PALM OIL PRODUCTION (Malaysia Palm Oil Board)
-- ============================================================================
CREATE TABLE IF NOT EXISTS supply.mpob_palm_1m (
  id                    SERIAL PRIMARY KEY,
  report_month          DATE NOT NULL, -- First day of month
  production_mt         DECIMAL(12,2), -- Monthly production (metric tons)
  exports_mt            DECIMAL(12,2), -- Monthly exports
  stocks_mt             DECIMAL(12,2), -- End of month stocks
  local_consumption_mt  DECIMAL(12,2), -- Domestic consumption
  country               VARCHAR(50) DEFAULT 'Malaysia', -- Malaysia or Indonesia
  source                VARCHAR(100) DEFAULT 'MPOB',
  ingested_at           TIMESTAMPTZ DEFAULT NOW(),
  row_hash              VARCHAR(64) UNIQUE,
  raw_payload           JSONB,

  UNIQUE(report_month, country)
);

CREATE INDEX idx_mpob_palm_month ON supply.mpob_palm_1m(report_month);
CREATE INDEX idx_mpob_palm_country ON supply.mpob_palm_1m(country);

-- ============================================================================
-- 2. ARGENTINA SOYBEAN CRUSH (Ciara-CEC / Argentina Ministry)
-- ============================================================================
CREATE TABLE IF NOT EXISTS supply.argentina_crush_1m (
  id                    SERIAL PRIMARY KEY,
  report_month          DATE NOT NULL, -- First day of month
  crush_volume_mt       DECIMAL(12,2), -- Monthly crush volume (metric tons)
  capacity_utilization  DECIMAL(5,2),  -- Percentage (0-100)
  oil_production_mt     DECIMAL(12,2), -- Soybean oil output
  meal_production_mt    DECIMAL(12,2), -- Soybean meal output
  exports_oil_mt        DECIMAL(12,2), -- Oil exports
  exports_meal_mt       DECIMAL(12,2), -- Meal exports
  source                VARCHAR(100) DEFAULT 'CIARA-CEC',
  ingested_at           TIMESTAMPTZ DEFAULT NOW(),
  row_hash              VARCHAR(64) UNIQUE,
  raw_payload           JSONB,

  UNIQUE(report_month)
);

CREATE INDEX idx_argentina_crush_month ON supply.argentina_crush_1m(report_month);

-- ============================================================================
-- 3. CONAB BRAZIL PRODUCTION (Official Brazilian Crop Forecasts)
-- ============================================================================
CREATE TABLE IF NOT EXISTS supply.conab_production_1m (
  id                    SERIAL PRIMARY KEY,
  report_month          DATE NOT NULL, -- Report release date
  crop_year             VARCHAR(20),   -- e.g., "2025/2026"
  commodity             VARCHAR(50),   -- Soybeans, Corn, etc.
  production_mt         DECIMAL(12,2), -- Production forecast (metric tons)
  area_harvested_ha     DECIMAL(12,2), -- Harvested area (hectares)
  yield_mt_per_ha       DECIMAL(6,2),  -- Yield (tons/hectare)
  exports_mt            DECIMAL(12,2), -- Export forecast
  domestic_consumption_mt DECIMAL(12,2), -- Domestic use
  ending_stocks_mt      DECIMAL(12,2), -- Ending stocks
  source                VARCHAR(100) DEFAULT 'CONAB',
  ingested_at           TIMESTAMPTZ DEFAULT NOW(),
  row_hash              VARCHAR(64) UNIQUE,
  raw_payload           JSONB,

  UNIQUE(report_month, crop_year, commodity)
);

CREATE INDEX idx_conab_production_month ON supply.conab_production_1m(report_month);
CREATE INDEX idx_conab_production_commodity ON supply.conab_production_1m(commodity);
CREATE INDEX idx_conab_production_crop_year ON supply.conab_production_1m(crop_year);

-- ============================================================================
-- VERIFICATION
-- ============================================================================

SELECT
  'supply.mpob_palm_1m' as table_name,
  (SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='supply' AND table_name='mpob_palm_1m') as exists
UNION ALL
SELECT 'supply.argentina_crush_1m',
  (SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='supply' AND table_name='argentina_crush_1m')
UNION ALL
SELECT 'supply.conab_production_1m',
  (SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='supply' AND table_name='conab_production_1m')
UNION ALL
SELECT 'supply.worldbank_imports_1y (should be dropped)',
  (SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='supply' AND table_name='worldbank_imports_1y');
