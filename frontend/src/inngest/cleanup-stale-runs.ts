/**
 * Cleanup Stale Ingest Runs
 *
 * Marks ingest runs stuck in 'running' status for >24h as timed out.
 * Prevents zombie rows from accumulating in ops.ingest_run.
 */

import { inngest } from "./client";
import { getIngestPool } from "@/lib/db";

const pool = getIngestPool();

export const cleanupStaleRuns = inngest.createFunction(
  { id: "cleanup-stale-runs", name: "Cleanup Stale Ingest Runs", retries: 1 },
  { cron: "0 6 * * *" }, // Daily at 06:00 UTC
  async ({ logger }) => {
    if (!process.env.DATABASE_URL) {
      throw new Error("DATABASE_URL not configured");
    }

    const client = await pool.connect();
    try {
      const result = await client.query(
        `UPDATE ops.ingest_run
         SET status = 'timeout',
             completed_at = NOW(),
             error_message = 'Auto-marked: running > 24h'
         WHERE status = 'running'
           AND started_at < NOW() - INTERVAL '24 hours'
         RETURNING id, job_name, started_at`
      );

      const count = result.rowCount ?? 0;
      if (count > 0) {
        for (const row of result.rows) {
          logger.warn(
            `Timed out stale run: ${row.id} (${row.job_name}, started ${row.started_at})`
          );
        }
      }

      logger.info(`Cleaned up ${count} stale ingest runs`);
      return { status: "success", timedOut: count };
    } finally {
      client.release();
    }
  }
);
