-- Unify specialist storage under canonical tables:
--   - training.specialist_signals_1d (signals)
--   - training.specialist_features (payload/features)
-- Removes legacy one-off table training.specialist_trump_effect_1d.

-- Fast bucket-specific page queries (e.g., trump_effect, biofuel) without full scans.
CREATE INDEX IF NOT EXISTS idx_specialist_signals_bucket_date
  ON training.specialist_signals_1d (bucket, as_of_date DESC);

CREATE INDEX IF NOT EXISTS idx_specialist_features_bucket_date
  ON training.specialist_features (bucket, as_of_date DESC);

-- Preserve legacy trump payload rows by upserting into canonical specialist_features.
INSERT INTO training.specialist_features (bucket, as_of_date, features)
SELECT
  'trump_effect'::text AS bucket,
  as_of_date,
  (
    COALESCE(features::jsonb, '{}'::jsonb) ||
    jsonb_build_object(
      'neural_signal', signal,
      'neural_confidence', confidence,
      'legacy_source', 'training.specialist_trump_effect_1d'
    )
  )::jsonb
FROM training.specialist_trump_effect_1d
ON CONFLICT (bucket, as_of_date) DO UPDATE
SET features = (
  COALESCE(training.specialist_features.features::jsonb, '{}'::jsonb) ||
  COALESCE(EXCLUDED.features::jsonb, '{}'::jsonb)
)::jsonb;

DROP TABLE IF EXISTS training.specialist_trump_effect_1d;
