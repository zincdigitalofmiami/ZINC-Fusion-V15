\set ON_ERROR_STOP on

DROP TABLE IF EXISTS pg_temp.trump_effect_diagnostic;
CREATE TEMP TABLE trump_effect_diagnostic (
  failure_mode text NOT NULL,
  table_exists boolean NOT NULL,
  row_count bigint,
  max_as_of_date date,
  weighted_action_score_presence bigint,
  action_velocity_presence bigint,
  neural_signal_presence bigint,
  neural_confidence_presence bigint,
  missing_key_rows bigint,
  non_numeric_rows bigint,
  stale_days integer,
  checked_at timestamptz NOT NULL DEFAULT now()
);

DO $$
DECLARE
  table_reg regclass;
  v_row_count bigint := 0;
  v_max_date date := NULL;
  v_weighted_presence bigint := 0;
  v_velocity_presence bigint := 0;
  v_neural_presence bigint := 0;
  v_conf_presence bigint := 0;
  v_missing_key_rows bigint := 0;
  v_non_numeric_rows bigint := 0;
  v_stale_days integer := NULL;
  v_failure_mode text := 'HEALTHY';
BEGIN
  table_reg := to_regclass('training.specialist_features_trump_effect');

  IF table_reg IS NULL THEN
    INSERT INTO trump_effect_diagnostic (
      failure_mode,
      table_exists,
      row_count,
      max_as_of_date,
      weighted_action_score_presence,
      action_velocity_presence,
      neural_signal_presence,
      neural_confidence_presence,
      missing_key_rows,
      non_numeric_rows,
      stale_days
    ) VALUES (
      'MISSING_TABLE',
      false,
      0,
      NULL,
      0,
      0,
      0,
      0,
      0,
      0,
      NULL
    );
    RETURN;
  END IF;

  EXECUTE '
    SELECT COUNT(*), MAX(as_of_date)
    FROM training.specialist_features_trump_effect
  ' INTO v_row_count, v_max_date;

  IF v_row_count = 0 THEN
    INSERT INTO trump_effect_diagnostic (
      failure_mode,
      table_exists,
      row_count,
      max_as_of_date,
      weighted_action_score_presence,
      action_velocity_presence,
      neural_signal_presence,
      neural_confidence_presence,
      missing_key_rows,
      non_numeric_rows,
      stale_days
    ) VALUES (
      'EMPTY_TABLE',
      true,
      0,
      NULL,
      0,
      0,
      0,
      0,
      0,
      0,
      NULL
    );
    RETURN;
  END IF;

  v_stale_days := GREATEST(0, CURRENT_DATE - v_max_date);

  EXECUTE '
    SELECT
      COUNT(*) FILTER (WHERE features ? ''weighted_action_score''),
      COUNT(*) FILTER (WHERE features ? ''action_velocity''),
      COUNT(*) FILTER (WHERE features ? ''neural_signal''),
      COUNT(*) FILTER (WHERE features ? ''neural_confidence'')
    FROM training.specialist_features_trump_effect
  ' INTO
    v_weighted_presence,
    v_velocity_presence,
    v_neural_presence,
    v_conf_presence;

  EXECUTE '
    SELECT COUNT(*)
    FROM training.specialist_features_trump_effect
    WHERE NOT (
      features ? ''weighted_action_score''
      AND features ? ''action_velocity''
      AND features ? ''neural_signal''
      AND features ? ''neural_confidence''
    )
  ' INTO v_missing_key_rows;

  EXECUTE '
    SELECT COUNT(*)
    FROM training.specialist_features_trump_effect
    WHERE
      (features ? ''weighted_action_score'' AND COALESCE(NULLIF(features->>''weighted_action_score'', ''''), ''__EMPTY__'') !~ ''^-?[0-9]+(\.[0-9]+)?$'')
      OR (features ? ''action_velocity'' AND COALESCE(NULLIF(features->>''action_velocity'', ''''), ''__EMPTY__'') !~ ''^-?[0-9]+(\.[0-9]+)?$'')
      OR (features ? ''neural_signal'' AND COALESCE(NULLIF(features->>''neural_signal'', ''''), ''__EMPTY__'') !~ ''^-?[0-9]+(\.[0-9]+)?$'')
      OR (features ? ''neural_confidence'' AND COALESCE(NULLIF(features->>''neural_confidence'', ''''), ''__EMPTY__'') !~ ''^-?[0-9]+(\.[0-9]+)?$'')
  ' INTO v_non_numeric_rows;

  IF v_missing_key_rows > 0 THEN
    v_failure_mode := 'KEY_DRIFT';
  ELSIF v_non_numeric_rows > 0 THEN
    v_failure_mode := 'CAST_DRIFT';
  ELSIF v_stale_days > 14 THEN
    v_failure_mode := 'STALE_ONLY';
  END IF;

  INSERT INTO trump_effect_diagnostic (
    failure_mode,
    table_exists,
    row_count,
    max_as_of_date,
    weighted_action_score_presence,
    action_velocity_presence,
    neural_signal_presence,
    neural_confidence_presence,
    missing_key_rows,
    non_numeric_rows,
    stale_days
  ) VALUES (
    v_failure_mode,
    true,
    v_row_count,
    v_max_date,
    v_weighted_presence,
    v_velocity_presence,
    v_neural_presence,
    v_conf_presence,
    v_missing_key_rows,
    v_non_numeric_rows,
    v_stale_days
  );
END;
$$;

SELECT * FROM trump_effect_diagnostic;
