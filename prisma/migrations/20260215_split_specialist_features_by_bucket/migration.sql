-- Split specialist feature payload storage into per-specialist tables.
-- Replaces training.specialist_features (bucket + json) with:
--   training.specialist_features_<bucket>
-- for all 11 specialists.

CREATE TABLE IF NOT EXISTS training.specialist_features_crush (
  id SERIAL PRIMARY KEY,
  as_of_date DATE NOT NULL UNIQUE,
  features JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS training.specialist_features_china (
  id SERIAL PRIMARY KEY,
  as_of_date DATE NOT NULL UNIQUE,
  features JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS training.specialist_features_fx (
  id SERIAL PRIMARY KEY,
  as_of_date DATE NOT NULL UNIQUE,
  features JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS training.specialist_features_fed (
  id SERIAL PRIMARY KEY,
  as_of_date DATE NOT NULL UNIQUE,
  features JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS training.specialist_features_tariff (
  id SERIAL PRIMARY KEY,
  as_of_date DATE NOT NULL UNIQUE,
  features JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS training.specialist_features_energy (
  id SERIAL PRIMARY KEY,
  as_of_date DATE NOT NULL UNIQUE,
  features JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS training.specialist_features_biofuel (
  id SERIAL PRIMARY KEY,
  as_of_date DATE NOT NULL UNIQUE,
  features JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS training.specialist_features_palm (
  id SERIAL PRIMARY KEY,
  as_of_date DATE NOT NULL UNIQUE,
  features JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS training.specialist_features_volatility (
  id SERIAL PRIMARY KEY,
  as_of_date DATE NOT NULL UNIQUE,
  features JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS training.specialist_features_substitutes (
  id SERIAL PRIMARY KEY,
  as_of_date DATE NOT NULL UNIQUE,
  features JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS training.specialist_features_trump_effect (
  id SERIAL PRIMARY KEY,
  as_of_date DATE NOT NULL UNIQUE,
  features JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_specialist_features_crush_date
  ON training.specialist_features_crush (as_of_date DESC);
CREATE INDEX IF NOT EXISTS idx_specialist_features_china_date
  ON training.specialist_features_china (as_of_date DESC);
CREATE INDEX IF NOT EXISTS idx_specialist_features_fx_date
  ON training.specialist_features_fx (as_of_date DESC);
CREATE INDEX IF NOT EXISTS idx_specialist_features_fed_date
  ON training.specialist_features_fed (as_of_date DESC);
CREATE INDEX IF NOT EXISTS idx_specialist_features_tariff_date
  ON training.specialist_features_tariff (as_of_date DESC);
CREATE INDEX IF NOT EXISTS idx_specialist_features_energy_date
  ON training.specialist_features_energy (as_of_date DESC);
CREATE INDEX IF NOT EXISTS idx_specialist_features_biofuel_date
  ON training.specialist_features_biofuel (as_of_date DESC);
CREATE INDEX IF NOT EXISTS idx_specialist_features_palm_date
  ON training.specialist_features_palm (as_of_date DESC);
CREATE INDEX IF NOT EXISTS idx_specialist_features_volatility_date
  ON training.specialist_features_volatility (as_of_date DESC);
CREATE INDEX IF NOT EXISTS idx_specialist_features_substitutes_date
  ON training.specialist_features_substitutes (as_of_date DESC);
CREATE INDEX IF NOT EXISTS idx_specialist_features_trump_effect_date
  ON training.specialist_features_trump_effect (as_of_date DESC);

DO $body$
BEGIN
  IF to_regclass('training.specialist_features') IS NOT NULL THEN
    EXECUTE $sql$
      INSERT INTO training.specialist_features_crush (as_of_date, features)
      SELECT as_of_date::date, COALESCE(features::jsonb, '{}'::jsonb)
      FROM training.specialist_features
      WHERE bucket = 'crush'
      ON CONFLICT (as_of_date) DO UPDATE SET features = EXCLUDED.features
    $sql$;

    EXECUTE $sql$
      INSERT INTO training.specialist_features_china (as_of_date, features)
      SELECT as_of_date::date, COALESCE(features::jsonb, '{}'::jsonb)
      FROM training.specialist_features
      WHERE bucket = 'china'
      ON CONFLICT (as_of_date) DO UPDATE SET features = EXCLUDED.features
    $sql$;

    EXECUTE $sql$
      INSERT INTO training.specialist_features_fx (as_of_date, features)
      SELECT as_of_date::date, COALESCE(features::jsonb, '{}'::jsonb)
      FROM training.specialist_features
      WHERE bucket = 'fx'
      ON CONFLICT (as_of_date) DO UPDATE SET features = EXCLUDED.features
    $sql$;

    EXECUTE $sql$
      INSERT INTO training.specialist_features_fed (as_of_date, features)
      SELECT as_of_date::date, COALESCE(features::jsonb, '{}'::jsonb)
      FROM training.specialist_features
      WHERE bucket = 'fed'
      ON CONFLICT (as_of_date) DO UPDATE SET features = EXCLUDED.features
    $sql$;

    EXECUTE $sql$
      INSERT INTO training.specialist_features_tariff (as_of_date, features)
      SELECT as_of_date::date, COALESCE(features::jsonb, '{}'::jsonb)
      FROM training.specialist_features
      WHERE bucket = 'tariff'
      ON CONFLICT (as_of_date) DO UPDATE SET features = EXCLUDED.features
    $sql$;

    EXECUTE $sql$
      INSERT INTO training.specialist_features_energy (as_of_date, features)
      SELECT as_of_date::date, COALESCE(features::jsonb, '{}'::jsonb)
      FROM training.specialist_features
      WHERE bucket = 'energy'
      ON CONFLICT (as_of_date) DO UPDATE SET features = EXCLUDED.features
    $sql$;

    EXECUTE $sql$
      INSERT INTO training.specialist_features_biofuel (as_of_date, features)
      SELECT as_of_date::date, COALESCE(features::jsonb, '{}'::jsonb)
      FROM training.specialist_features
      WHERE bucket = 'biofuel'
      ON CONFLICT (as_of_date) DO UPDATE SET features = EXCLUDED.features
    $sql$;

    EXECUTE $sql$
      INSERT INTO training.specialist_features_palm (as_of_date, features)
      SELECT as_of_date::date, COALESCE(features::jsonb, '{}'::jsonb)
      FROM training.specialist_features
      WHERE bucket = 'palm'
      ON CONFLICT (as_of_date) DO UPDATE SET features = EXCLUDED.features
    $sql$;

    EXECUTE $sql$
      INSERT INTO training.specialist_features_volatility (as_of_date, features)
      SELECT as_of_date::date, COALESCE(features::jsonb, '{}'::jsonb)
      FROM training.specialist_features
      WHERE bucket = 'volatility'
      ON CONFLICT (as_of_date) DO UPDATE SET features = EXCLUDED.features
    $sql$;

    EXECUTE $sql$
      INSERT INTO training.specialist_features_substitutes (as_of_date, features)
      SELECT as_of_date::date, COALESCE(features::jsonb, '{}'::jsonb)
      FROM training.specialist_features
      WHERE bucket = 'substitutes'
      ON CONFLICT (as_of_date) DO UPDATE SET features = EXCLUDED.features
    $sql$;

    EXECUTE $sql$
      INSERT INTO training.specialist_features_trump_effect (as_of_date, features)
      SELECT as_of_date::date, COALESCE(features::jsonb, '{}'::jsonb)
      FROM training.specialist_features
      WHERE bucket = 'trump_effect'
      ON CONFLICT (as_of_date) DO UPDATE SET features = EXCLUDED.features
    $sql$;

    EXECUTE 'DROP TABLE training.specialist_features';
  END IF;
END $body$;
