-- Repair migration: ensure training.specialist_features_trump_effect exists in drifted envs.
-- Idempotent by design.

CREATE TABLE IF NOT EXISTS training.specialist_features_trump_effect (
  id SERIAL PRIMARY KEY,
  as_of_date DATE NOT NULL,
  features JSONB NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_specialist_features_trump_effect_as_of_date
  ON training.specialist_features_trump_effect (as_of_date);

CREATE INDEX IF NOT EXISTS idx_specialist_features_trump_effect_date
  ON training.specialist_features_trump_effect (as_of_date DESC);
