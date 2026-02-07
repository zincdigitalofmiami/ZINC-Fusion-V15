/**
 * NY Fed Rates Daily Data Ingestion
 *
 * INGESTION CONTRACT:
 * - Logs each run in ops.ingest_run
 * - Computes row_hash for idempotency
 * - Assigns specialist_tags per RAW_SOURCE_SPECIALIST_MAPPING.md
 * - Append-only inserts (no upserts)
 *
 * SOURCE: https://markets.newyorkfed.org/api/rates/all/latest.json
 * - No API key required (public API)
 * - Returns SOFR, EFFR, OBFR, TGCR, BGCR rates
 *
 * Tags: fed
 *
 * @author Claude (ZINC-FUSION-V15)
 * @version 1.1.0
 * @date 2026-02-07
 */

import { inngest } from "./client";
import pool from "@/lib/db";
import type { PoolClient } from "pg";
import { createHash } from "crypto";
import dbPool from "@/lib/db";

// =============================================================================
// HELPER FUNCTIONS
// =============================================================================

function computeRowHash(rateType: string, effectiveDate: string, rate: number): string {
  return createHash("sha256").update(`${rateType}|${effectiveDate}|${rate}`).digest("hex");
}

async function createIngestRun(client: PoolClient, jobName: string): Promise<string> {
  const result = await client.query(
    `INSERT INTO ops.ingest_run (job_name, status, started_at)
     VALUES ($1, 'running', NOW())
     RETURNING id`,
    [jobName]
  );
  return result.rows[0].id;
}

async function updateIngestRun(
  client: PoolClient,
  runId: string,
  status: string,
  rowsAttempted: number,
  rowsInserted: number,
  rowsSkipped: number,
  rowsQuarantined: number,
  errorMessage?: string
): Promise<void> {
  await client.query(
    `UPDATE ops.ingest_run
     SET status = $2, completed_at = NOW(),
         rows_attempted = $3, rows_inserted = $4,
         rows_skipped = $5, rows_quarantined = $6,
         error_message = $7
     WHERE id = $1`,
    [runId, status, rowsAttempted, rowsInserted, rowsSkipped, rowsQuarantined, errorMessage]
  );
}

async function hashExists(client: PoolClient, tableName: string, rowHash: string): Promise<boolean> {
  const result = await client.query(
    `SELECT 1 FROM ${tableName} WHERE row_hash = $1 LIMIT 1`,
    [rowHash]
  );
  return result.rows.length > 0;
}

// =============================================================================
// NY FED API TYPES
// =============================================================================

interface NYFedRate {
  effectiveDate: string;
  type: string;
  percentRate?: number;
  percentPercentile1?: number;
  percentPercentile25?: number;
  percentPercentile75?: number;
  percentPercentile99?: number;
  volumeInBillions?: number;
  footnoteId?: string;
}

interface NYFedResponse {
  refRates: NYFedRate[];
}

// =============================================================================
// MAIN INNGEST FUNCTION
// =============================================================================

export const nyfedDaily = inngest.createFunction(
  {
    id: "nyfed-daily",
    name: "NY Fed Rates Daily Bronze Ingestion",
    retries: 3,
    concurrency: [{ limit: 1 }],
  },
  { cron: "12 */8 * * *" }, // Every 8 hours at :12 UTC
  async ({ step, logger }) => {
    const client = await pool.connect();
    let runId: string | null = null;

    let rowsAttempted = 0;
    let rowsInserted = 0;
    let rowsSkipped = 0;
    let rowsQuarantined = 0;
    const results: { rateType: string; status: string; rate?: number }[] = [];

    try {
      await step.run("assert-table", async () => {
        // Fail loudly if the table doesn't exist (no silent DDL in prod).
        await client.query(`SELECT 1 FROM econ.rates_1d LIMIT 1`);
      });

      // Step 2: Create ingest run
      runId = await step.run("create-ingest-run", async () => {
        return await createIngestRun(client, "nyfed-daily");
      });

      logger.info(`Started ingest run: ${runId}`);

      // Step 3: Fetch from NY Fed API with timeout
      const rates = await step.run("fetch-rates", async () => {
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 15000); // 15s timeout
        try {
          const response = await fetch("https://markets.newyorkfed.org/api/rates/all/latest.json", {
            signal: controller.signal,
          });
          clearTimeout(timeout);
          if (!response.ok) {
            throw new Error(`NY Fed API error: ${response.status}`);
          }
          const json: NYFedResponse = await response.json();
          return json.refRates || [];
        } catch (err) {
          clearTimeout(timeout);
          if (err instanceof Error && err.name === 'AbortError') {
            throw new Error('NY Fed API fetch timed out after 15s');
          }
          throw err;
        }
      });

      logger.info(`Fetched ${rates.length} rates from NY Fed`);

      // Step 4: Process each rate
      for (const rate of rates) {
        const outcome = await step.run(`ingest-${rate.type}`, async () => {
          if (!rate.effectiveDate || !rate.type) {
            return { rateType: rate.type || "UNKNOWN", status: "quarantined_missing_keys" as const };
          }

          if (typeof rate.percentRate !== "number" || !Number.isFinite(rate.percentRate)) {
            return { rateType: rate.type, status: "quarantined_missing_rate" as const };
          }

          const parsedDate = new Date(rate.effectiveDate);
          if (Number.isNaN(parsedDate.getTime())) {
            return { rateType: rate.type, status: "quarantined_bad_date" as const };
          }

          const rowHash = computeRowHash(rate.type, rate.effectiveDate, rate.percentRate);

          if (await hashExists(client, "econ.rates_1d", rowHash)) {
            return { rateType: rate.type, status: "skipped_duplicate" as const };
          }

          // Map NYFED rate type to series_id format
          const seriesId = `NYFED_${rate.type.toUpperCase().replace(/\s+/g, '_')}`;

          await client.query(
            `INSERT INTO econ.rates_1d (
               series_id, event_date, value, source, row_hash
             ) VALUES ($1, $2, $3, $4, $5)`,
            [
              seriesId,
              rate.effectiveDate,
              rate.percentRate,
              "nyfed_api",
              rowHash,
            ]
          );

          return { rateType: rate.type, status: "inserted" as const, rate: rate.percentRate };
        });

        rowsAttempted++;
        results.push(outcome);
        if (outcome.status === "inserted") rowsInserted++;
        else if (outcome.status === "skipped_duplicate") rowsSkipped++;
        else rowsQuarantined++;
      }

      // Step 5: Complete ingest run
      await step.run("complete-ingest-run", async () => {
        await updateIngestRun(client, runId!, "success", rowsAttempted, rowsInserted, rowsSkipped, rowsQuarantined);
      });

      logger.info(`Completed: ${rowsInserted} inserted, ${rowsSkipped} skipped`);

      return {
        status: "success",
        runId,
        date: new Date().toISOString().split("T")[0],
        summary: { attempted: rowsAttempted, inserted: rowsInserted, skipped: rowsSkipped, quarantined: rowsQuarantined },
        rates: results,
      };

    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error);
      if (runId) {
        await updateIngestRun(client, runId, "failed", rowsAttempted, rowsInserted, rowsSkipped, rowsQuarantined, errorMsg);
      }
      logger.error(`Ingest run failed: ${errorMsg}`);
      return { status: "failed", runId, error: errorMsg };

    } finally {
      client.release();
    }
  }
);
