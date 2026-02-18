-- Add ops.pipeline_alerts table.
-- Written by the global-failure-monitor Inngest function to record every function
-- that exhausts all its retries. Provides SQL-queryable visibility into pipeline failures
-- without requiring manual checks of the Inngest dashboard.

CREATE TABLE IF NOT EXISTS ops.pipeline_alerts (
  id           SERIAL PRIMARY KEY,
  function_id  VARCHAR NOT NULL,
  run_id       VARCHAR NOT NULL UNIQUE,
  error_message TEXT,
  error_name   VARCHAR,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pipeline_alerts_function_id
  ON ops.pipeline_alerts (function_id);

CREATE INDEX IF NOT EXISTS idx_pipeline_alerts_created_at
  ON ops.pipeline_alerts (created_at DESC);
