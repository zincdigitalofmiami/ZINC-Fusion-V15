/**
 * Weather Features Daily (DQ Rollup)
 *
 * This job used to write derived features into `features.weather_1d`.
 * That table was removed when weather features moved to on-the-fly computation
 * from `alt.weather_1d` (see src/fusion/core_training/build_matrix.py).
 *
 * To keep pipeline monitoring clean (and avoid a permanently "failed" job),
 * we keep the function id/job_name stable and instead:
 * - validate `alt.weather_1d` freshness/completeness for tracked stations
 * - upsert a daily record into `ops.data_quality_metrics`
 *
 * No schema changes, no synthetic data.
 */

import { inngest, DB_CONCURRENCY } from "./client";
import dbPool from "@/lib/db";

const pool = dbPool;

type WeatherDqRow = {
  max_event_date: string | null;
  last_update: Date | string | null;
  hours_since_update: number | null;
  total_rows: number | null;
  expected_rows: number | null;
  completeness_pct: number | null;
  null_count: number | null;
  null_pct: number | null;
  is_stale: boolean | null;
  is_incomplete: boolean | null;
};

export const weatherFeaturesDaily = inngest.createFunction(
  {
    id: "weather-features-daily",
    name: "Weather Features Daily (DQ Rollup)",
    retries: 1,
    concurrency: [DB_CONCURRENCY, { limit: 1 }],
  },
  { cron: "10 14 * * *" }, // Daily at 14:10 UTC (after Open-Meteo weather ingestion)
  async ({ step, logger }) => {
    // ── Step 1: assert required tables exist ──
    await step.run("assert-tables", async () => {
      const client = await pool.connect();
      try {
        await client.query("SELECT 1 FROM alt.weather_1d LIMIT 1");
        await client.query("SELECT 1 FROM ops.ingest_run LIMIT 1");
        await client.query("SELECT 1 FROM ops.data_quality_metrics LIMIT 1");
      } finally {
        client.release();
      }
    });

    // ── Step 2: create ingest run ──
    const runId = await step.run("create-ingest-run", async () => {
      const client = await pool.connect();
      try {
        const result = await client.query(
          `INSERT INTO ops.ingest_run (job_name, status, started_at)
           VALUES ($1, 'running', NOW())
           RETURNING id`,
          ["weather-features-daily"],
        );
        return result.rows[0].id as string;
      } finally {
        client.release();
      }
    });

    try {
      // ── Step 3: compute DQ metrics from alt.weather_1d ──
      const metrics = await step.run("compute-dq", async () => {
        const client = await pool.connect();
        try {
          const sql = `
            WITH tracked AS (
              SELECT *
              FROM alt.weather_1d
              WHERE station_id LIKE 'OM\\_%'
                 OR station_id LIKE 'OPENMETEO:%'
            ),
            stations AS (
              SELECT COUNT(DISTINCT station_id)::int AS expected_rows
              FROM tracked
            ),
            latest AS (
              SELECT
                MAX(event_date)::date AS max_event_date,
                MAX(ingested_at) AS last_update
              FROM tracked
            ),
            day_counts AS (
              SELECT
                COUNT(*)::int AS total_rows,
                (
                  SUM(CASE WHEN tavg_c IS NULL THEN 1 ELSE 0 END) +
                  SUM(CASE WHEN prcp_mm IS NULL THEN 1 ELSE 0 END)
                )::int AS null_count
              FROM tracked
              WHERE event_date = (SELECT max_event_date FROM latest)
            )
            SELECT
              (SELECT max_event_date::text FROM latest) AS max_event_date,
              (SELECT last_update FROM latest) AS last_update,
              CASE
                WHEN (SELECT last_update FROM latest) IS NULL THEN NULL
                ELSE (EXTRACT(epoch FROM (NOW() - (SELECT last_update FROM latest))) / 3600)::float
              END AS hours_since_update,
              (SELECT total_rows FROM day_counts) AS total_rows,
              (SELECT expected_rows FROM stations) AS expected_rows,
              CASE
                WHEN (SELECT expected_rows FROM stations) > 0
                  THEN ((SELECT total_rows FROM day_counts)::numeric / (SELECT expected_rows FROM stations)::numeric) * 100
                ELSE NULL
              END AS completeness_pct,
              (SELECT null_count FROM day_counts) AS null_count,
              CASE
                WHEN (SELECT total_rows FROM day_counts) > 0
                  THEN ((SELECT null_count FROM day_counts)::numeric / ((SELECT total_rows FROM day_counts)::numeric * 2)) * 100
                ELSE NULL
              END AS null_pct,
              CASE
                WHEN (SELECT max_event_date FROM latest) IS NULL THEN NULL
                ELSE (CURRENT_DATE - (SELECT max_event_date FROM latest)) > 2
              END AS is_stale,
              CASE
                WHEN (SELECT expected_rows FROM stations) > 0
                  THEN (SELECT total_rows FROM day_counts) < (SELECT expected_rows FROM stations) * 0.9
                ELSE NULL
              END AS is_incomplete
          `;

          const res = await client.query<WeatherDqRow>(sql);
          const row = res.rows[0];
          if (!row || !row.max_event_date) {
            throw new Error("No tracked weather data found in alt.weather_1d");
          }
          return row;
        } finally {
          client.release();
        }
      });

      // ── Step 4: upsert DQ metrics ──
      await step.run("upsert-dq-metrics", async () => {
        const client = await pool.connect();
        try {
          await client.query(
            `INSERT INTO ops.data_quality_metrics
              (as_of_date, source, last_update, hours_since_update, total_rows, expected_rows, completeness_pct, null_count, null_pct, is_stale, is_incomplete, created_at)
             VALUES
              (CURRENT_DATE, 'weather-features-daily', $1, $2, $3, $4, $5, $6, $7, $8, $9, NOW())
             ON CONFLICT (as_of_date, source) DO UPDATE SET
               last_update = EXCLUDED.last_update,
               hours_since_update = EXCLUDED.hours_since_update,
               total_rows = EXCLUDED.total_rows,
               expected_rows = EXCLUDED.expected_rows,
               completeness_pct = EXCLUDED.completeness_pct,
               null_count = EXCLUDED.null_count,
               null_pct = EXCLUDED.null_pct,
               is_stale = COALESCE(EXCLUDED.is_stale, ops.data_quality_metrics.is_stale),
               is_incomplete = COALESCE(EXCLUDED.is_incomplete, ops.data_quality_metrics.is_incomplete),
               created_at = NOW()`,
            [
              metrics.last_update,
              metrics.hours_since_update,
              metrics.total_rows,
              metrics.expected_rows,
              metrics.completeness_pct,
              metrics.null_count,
              metrics.null_pct,
              metrics.is_stale,
              metrics.is_incomplete,
            ],
          );
        } finally {
          client.release();
        }
      });

      // ── Step 5: complete ingest run ──
      await step.run("complete-ingest-run", async () => {
        const client = await pool.connect();
        try {
          await client.query(
            `UPDATE ops.ingest_run
             SET status='success',
                 completed_at=NOW(),
                 rows_attempted=$2,
                 rows_inserted=1,
                 rows_skipped=0,
                 rows_quarantined=0
             WHERE id=$1`,
            [runId, metrics.expected_rows ?? 0],
          );
        } finally {
          client.release();
        }
      });

      logger.info(
        {
          max_event_date: metrics.max_event_date,
          total_rows: metrics.total_rows,
          expected_rows: metrics.expected_rows,
          completeness_pct: metrics.completeness_pct,
          hours_since_update: metrics.hours_since_update,
        },
        "Weather DQ rollup complete",
      );

      return {
        status: "success",
        runId,
        maxEventDate: metrics.max_event_date,
        totalRows: metrics.total_rows,
        expectedRows: metrics.expected_rows,
        completenessPct: metrics.completeness_pct,
      };
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      logger.error(`weather-features-daily failed: ${message}`);

      await step.run("fail-ingest-run", async () => {
        const client = await pool.connect();
        try {
          await client.query(
            `UPDATE ops.ingest_run
             SET status='failed', completed_at=NOW(), error_message=$2
             WHERE id=$1`,
            [runId, message],
          );
        } finally {
          client.release();
        }
      });

      return { status: "failed", runId, error: message };
    }
  },
);
