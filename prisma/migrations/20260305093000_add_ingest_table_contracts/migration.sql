-- Add missing ingestion contract tables to Prisma-managed schema.

CREATE TABLE IF NOT EXISTS econ.bls_1m (
  id SERIAL PRIMARY KEY,
  series_id VARCHAR(30) NOT NULL,
  event_date DATE NOT NULL,
  value DOUBLE PRECISION NOT NULL,
  series_name VARCHAR(120),
  specialist_tags TEXT[] NOT NULL DEFAULT '{}',
  source VARCHAR(30) DEFAULT 'bls_api',
  row_hash VARCHAR(64) NOT NULL,
  ingested_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(series_id, event_date)
);
CREATE INDEX IF NOT EXISTS idx_bls_1m_date ON econ.bls_1m(event_date);
CREATE INDEX IF NOT EXISTS idx_bls_1m_series ON econ.bls_1m(series_id);

CREATE TABLE IF NOT EXISTS supply.china_imports_1m (
  id SERIAL PRIMARY KEY,
  report_month DATE NOT NULL,
  commodity VARCHAR(50) NOT NULL,
  symbol VARCHAR(30) NOT NULL,
  partner_country VARCHAR(100) DEFAULT 'World',
  value_usd DOUBLE PRECISION,
  quantity_mt DOUBLE PRECISION,
  source VARCHAR(30) DEFAULT 'comtrade',
  specialist_tags TEXT[] NOT NULL DEFAULT '{china,crush}',
  row_hash VARCHAR(64) NOT NULL,
  ingested_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(report_month, symbol, partner_country)
);
CREATE INDEX IF NOT EXISTS idx_china_imports_month ON supply.china_imports_1m(report_month);
CREATE INDEX IF NOT EXISTS idx_china_imports_symbol ON supply.china_imports_1m(symbol);

CREATE TABLE IF NOT EXISTS supply.fas_gats_1m (
  id SERIAL PRIMARY KEY,
  report_month DATE NOT NULL,
  commodity VARCHAR(50) NOT NULL,
  symbol VARCHAR(30) NOT NULL,
  partner_country VARCHAR(100) NOT NULL DEFAULT 'World',
  value_usd DOUBLE PRECISION,
  quantity_mt DOUBLE PRECISION,
  flow VARCHAR(10) NOT NULL DEFAULT 'export',
  source VARCHAR(30) DEFAULT 'fas_gats',
  specialist_tags TEXT[] NOT NULL DEFAULT '{tariff,china,crush}',
  row_hash VARCHAR(64) NOT NULL,
  ingested_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(report_month, symbol, partner_country, flow)
);
CREATE INDEX IF NOT EXISTS idx_fas_gats_month ON supply.fas_gats_1m(report_month);
CREATE INDEX IF NOT EXISTS idx_fas_gats_symbol ON supply.fas_gats_1m(symbol);
CREATE INDEX IF NOT EXISTS idx_fas_gats_partner ON supply.fas_gats_1m(partner_country);

CREATE TABLE IF NOT EXISTS supply.panama_canal_1d (
  id SERIAL PRIMARY KEY,
  event_date DATE NOT NULL UNIQUE,
  transits_panamax INTEGER,
  transits_neopanamax INTEGER,
  transits_total INTEGER,
  max_draft_ft DOUBLE PRECISION,
  booking_slots INTEGER,
  advisory_text TEXT,
  source VARCHAR(30) DEFAULT 'pancanal',
  specialist_tags TEXT[] NOT NULL DEFAULT '{tariff,crush,china}',
  row_hash VARCHAR(64) NOT NULL,
  ingested_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_panama_canal_date ON supply.panama_canal_1d(event_date);
