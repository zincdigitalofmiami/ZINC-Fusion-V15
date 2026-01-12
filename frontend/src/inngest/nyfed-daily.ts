/**
 * NY Fed Rates Daily Bronze Ingestion
 * 
 * BRONZE CONTRACT COMPLIANT:
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
 * @version 1.0.0 - Bronze Contract
 * @date 2026-01-11
 */

import { inngest } from "./client";
import { Pool } from "pg";
import { createHash } from "crypto";

// Database connection pool
const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
  ssl: { rejectUnauthorized: false },
});

// =============================================================================
// BRONZE HELPER FUNCTIONS
// =============================================================================

function computeRowHash(rateType: string, effectiveDate: string, rate: number): string {
  return createHash("sha256").update(`${rateType}|${effectiveDate}|${rate}`).digest("hex");
}

async function createIngestRun(client: any, jobName: string): Promise<string> {
  const result = await client.query(
    `INSERT INTO ops.ingest_run (job_name, status, started_at)
     VALUES ($1, 'running', NOW())
     RETURNING id`,
    [jobName]
  );
  return result.rows[0].id;
}

async function updateIngestRun(
  client: any,
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

async function hashExists(client: any, tableName: string, rowHash: string): Promise<boolean> {
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
  },
  { cron: "0 12 * * 1-5" }, // 6AM CT = 12 UTC, Mon-Fri (after NY Fed publishes)
  async ({ step, logger }) => {
    const client = await pool.connect();
    let runId: string | null = null;

    let rowsAttempted = 0;
    let rowsInserted = 0;
    let rowsSkipped = 0;
    let rowsQuarantined = 0;
    const results: { rateType: string; status: string; rate?: number }[] = [];

    try {
      // Step 1: Ensure table exists
      await step.run("ensure-table", async () => {
        await client.query(`
          CREATE TABLE IF NOT EXISTS raw.nyfed_rates_1d (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            event_date DATE NOT NULL,
            rate_type TEXT NOT NULL,
            percent_rate NUMERIC(10,6),
            percentile_1 NUMERIC(10,6),
            percentile_25 NUMERIC(10,6),
            percentile_75 NUMERIC(10,6),
            percentile_99 NUMERIC(10,6),
            volume_billions NUMERIC(12,3),
            footnote_id TEXT,
            -- Bronze columns
            knowledge_time TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            revision_no INTEGER NOT NULL DEFAULT 1,
            supersedes_id UUID REFERENCES raw.nyfed_rates_1d(id),
            is_preliminary BOOLEAN DEFAULT false,
            validation_status TEXT DEFAULT 'validated',
            quality_score NUMERIC(3,2) DEFAULT 1.0,
            anomaly_flags TEXT[] DEFAULT '{}',
            source_url TEXT,
            raw_payload JSONB,
            ingestion_batch_id UUID,
            row_hash TEXT NOT NULL,
            specialist_tags TEXT[] NOT NULL
          )
        `);
        await client.query(`CREATE INDEX IF NOT EXISTS idx_nyfed_row_hash ON raw.nyfed_rates_1d(row_hash)`);
        await client.query(`CREATE INDEX IF NOT EXISTS idx_nyfed_tags ON raw.nyfed_rates_1d USING GIN(specialist_tags)`);
        await client.query(`CREATE INDEX IF NOT EXISTS idx_nyfed_event_date ON raw.nyfed_rates_1d(event_date)`);
        await client.query(`CREATE INDEX IF NOT EXISTS idx_nyfed_rate_type ON raw.nyfed_rates_1d(rate_type)`);
      });

      // Step 2: Create ingest run
      runId = await step.run("create-ingest-run", async () => {
        return await createIngestRun(client, "nyfed-daily");
      });

      logger.info(`Started ingest run: ${runId}`);

      // Step 3: Fetch from NY Fed API
      const rates = await step.run("fetch-rates", async () => {
        const response = await fetch("https://markets.newyorkfed.org/api/rates/all/latest.json");
        if (!response.ok) {
          throw new Error(`NY Fed API error: ${response.status}`);
        }
        const json: NYFedResponse = await response.json();
        return json.refRates || [];
      });

      logger.info(`Fetched ${rates.length} rates from NY Fed`);

      // Step 4: Process each rate
      for (const rate of rates) {
        await step.run(`ingest-${rate.type}`, async () => {
          rowsAttempted++;

          if (!rate.effectiveDate || !rate.type) {
            results.push({ rateType: rate.type || "UNKNOWN", status: "skipped_invalid" });
            rowsSkipped++;
            return;
          }

          const rowHash = computeRowHash(rate.type, rate.effectiveDate, rate.percentRate || 0);

          if (await hashExists(client, "raw.nyfed_rates_1d", rowHash)) {
            results.push({ rateType: rate.type, status: "skipped_duplicate" });
            rowsSkipped++;
            return;
          }

          await client.query(
            `INSERT INTO raw.nyfed_rates_1d (
               event_date, rate_type, percent_rate,
               percentile_1, percentile_25, percentile_75, percentile_99,
               volume_billions, footnote_id,
               knowledge_time, revision_no, is_preliminary, validation_status,
               source_url, raw_payload, ingestion_batch_id, row_hash, specialist_tags
             ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, NOW(), 1, false, 'validated', $10, $11, $12, $13, $14)`,
            [
              rate.effectiveDate,
              rate.type,
              rate.percentRate,
              rate.percentPercentile1,
              rate.percentPercentile25,
              rate.percentPercentile75,
              rate.percentPercentile99,
              rate.volumeInBillions,
              rate.footnoteId,
              "https://markets.newyorkfed.org/api/rates/all/latest.json",
              JSON.stringify(rate),
              runId,
              rowHash,
              ["fed"], // FED specialist
            ]
          );

          results.push({ rateType: rate.type, status: "inserted", rate: rate.percentRate });
          rowsInserted++;
        });
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
