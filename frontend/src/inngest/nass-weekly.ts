/**
 * USDA NASS QuickStats API Data Ingestion
 *
 * INGESTION CONTRACT:
 * - Logs each run in ops.ingest_run
 * - Computes row_hash for idempotency
 * - Append-only inserts (no upserts)
 *
 * SOURCE: https://quickstats.nass.usda.gov/api/api_GET
 * Tags: crush
 *
 * @author Claude (ZINC-FUSION-V15)
 * @version 1.1.0
 * @date 2026-02-16
 */

import { inngest, DB_CONCURRENCY } from "./client";
import { createHash } from "crypto";
import { getIngestPool } from "@/lib/db";

const pool = getIngestPool();

// PoolClient helper functions removed — SQL inlined inside step.run() closures
// to prevent stale connections across Inngest durable execution boundaries.

function computeRowHash(seriesId: string, date: string, value: string): string {
  return createHash("sha256").update(`${seriesId}|${date}|${value}`).digest("hex");
}

export const nassWeekly = inngest.createFunction(
  { id: "nass-weekly", name: "USDA NASS API Data Ingestion", retries: 3, concurrency: [DB_CONCURRENCY] },
  { cron: "0 2 * * 6" }, // Saturdays 02:00 UTC
  async ({ step, logger }) => {
    const apiKey = process.env.USDA_API_KEY;
    if (!apiKey) {
      throw new Error("USDA_API_KEY not configured");
    }

    // ── Step 1: create ingest run ──
    const runId = await step.run("create-ingest-run", async () => {
      const client = await pool.connect();
      try {
        const result = await client.query(
          `INSERT INTO ops.ingest_run (job_name, status, started_at) VALUES ($1, 'running', NOW()) RETURNING id`,
          ["nass-weekly"]
        );
        return result.rows[0].id as string;
      } finally {
        client.release();
      }
    });

    logger.info(`Started ingest run: ${runId}`);

    // ── Step 2: fetch from NASS API ──
    const data = await step.run("fetch-api", async () => {
      const currentYear = new Date().getFullYear();
      // Also fetch previous year for complete crop cycle data
      const years = [currentYear - 1, currentYear];
      const allData: Array<{ year: string; commodity_desc: string; statisticcat_desc: string; Value: string }> = [];

      for (const year of years) {
        const url = `https://quickstats.nass.usda.gov/api/api_GET?key=${apiKey}&commodity_desc=SOYBEANS&year=${year}&format=JSON&statisticcat_desc=PRODUCTION,YIELD,AREA PLANTED`;
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 30_000);
        try {
          const response = await fetch(url, { signal: controller.signal });
          clearTimeout(timeout);
          if (!response.ok) {
            const text = await response.text().catch(() => "");
            throw new Error(`NASS API error ${response.status} for year ${year}: ${text}`);
          }
          const json = await response.json();
          if (json.data) allData.push(...json.data);
        } catch (err) {
          clearTimeout(timeout);
          if (err instanceof Error && err.name === "AbortError") {
            throw new Error(`NASS API timeout after 30s for year ${year}`);
          }
          throw err;
        }
      }

      return allData;
    });

    logger.info(`Fetched ${data.length} records from NASS API`);

    // ── Step 3: insert records (batched in one step) ──
    const batchResult = await step.run("insert-records-batch", async () => {
      let rowsAttempted = 0, rowsInserted = 0, rowsSkipped = 0;

      const client = await pool.connect();
      try {
        for (const row of data) {
          rowsAttempted++;
          const obsDate = `${row.year}-01-01`;
          const seriesId = `NASS_${row.commodity_desc}_${row.statisticcat_desc}`.replace(/\s+/g, '_').toUpperCase();
          const value = row.Value ? parseFloat(row.Value.replace(/,/g, "")) : null;

          if (value === null || isNaN(value)) {
            rowsSkipped++;
            continue;
          }

          const rowHash = computeRowHash(seriesId, obsDate, row.Value);

          const exists = await client.query(
            `SELECT 1 FROM econ.activity_1d WHERE row_hash=$1 LIMIT 1`,
            [rowHash]
          );
          if (exists.rows.length > 0) {
            rowsSkipped++;
            continue;
          }

          await client.query(
            `INSERT INTO econ.activity_1d (event_date, series_id, value, source, row_hash) VALUES ($1,$2,$3,$4,$5)`,
            [obsDate, seriesId, value, "nass_api", rowHash]
          );
          rowsInserted++;
        }
      } finally {
        client.release();
      }

      return { attempted: rowsAttempted, inserted: rowsInserted, skipped: rowsSkipped };
    });

    // ── Step 4: finalize ingest run ──
    await step.run("complete-ingest-run", async () => {
      const client = await pool.connect();
      try {
        await client.query(
          `UPDATE ops.ingest_run SET status=$2, completed_at=NOW(),
           rows_attempted=$3, rows_inserted=$4, rows_skipped=$5, rows_quarantined=$6 WHERE id=$1`,
          [runId, "success", batchResult.attempted, batchResult.inserted, batchResult.skipped, 0]
        );
      } finally {
        client.release();
      }
    });

    logger.info(`NASS ingestion complete: ${batchResult.inserted} inserted, ${batchResult.skipped} skipped`);
    return { status: "success", runId, inserted: batchResult.inserted, skipped: batchResult.skipped };
  }
);
