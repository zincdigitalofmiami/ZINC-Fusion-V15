-- Repair migration: ensure ops.ingest_run exists in drifted environments.
-- Idempotent by design.

CREATE TABLE IF NOT EXISTS ops.ingest_run (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  job_name VARCHAR NOT NULL,
  started_at TIMESTAMPTZ(6) DEFAULT NOW(),
  completed_at TIMESTAMPTZ(6),
  status VARCHAR DEFAULT 'running',
  rows_attempted INTEGER DEFAULT 0,
  rows_inserted INTEGER DEFAULT 0,
  rows_skipped INTEGER DEFAULT 0,
  rows_quarantined INTEGER DEFAULT 0,
  cursor_position JSONB,
  error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_ingest_run_job_started
  ON ops.ingest_run (job_name, started_at);

CREATE INDEX IF NOT EXISTS idx_ingest_run_job_status_completed
  ON ops.ingest_run (job_name, status, completed_at DESC);

CREATE INDEX IF NOT EXISTS idx_ingest_run_manual_refresh_gate
  ON ops.ingest_run (job_name, started_at DESC, status);
