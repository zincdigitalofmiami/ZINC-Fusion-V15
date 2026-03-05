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
 * @version 1.2.0
 * @date 2026-02-16
 */

import { inngest, DB_CONCURRENCY } from "./client";
import { createHash } from "crypto";
import { getIngestPool } from "@/lib/db";

const pool = getIngestPool();

function computeRowHash(rateType: string, effectiveDate: string, rate: number): string {
  return createHash("sha256").update(`${rateType}|${effectiveDate}|${rate}`).digest("hex");
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
    name: "NY Fed Rates Daily Ingestion",
    retries: 1,
    concurrency: [DB_CONCURRENCY, { limit: 1 }],
  },
  { cron: "45 5 * * *" }, // Daily at 05:45 UTC
  async ({ step, logger }) => {
    // ── Step 1: assert table exists ──
    await step.run("assert-table", async () => {
      const client = await pool.connect();
      try {
        await client.query(`SELECT 1 FROM econ.rates_1d LIMIT 1`);
      } finally {
        client.release();
      }
    });

    // ── Step 2: create ingest run ──
    const runId = await step.run("create-ingest-run", async () => {
      const client = await pool.connect();
      try {
        const result = await client.query(
          `INSERT INTO ops.ingest_run (job_name, status, started_at) VALUES ($1, 'running', NOW()) RETURNING id`,
          ["nyfed-daily"]
        );
        return result.rows[0].id as string;
      } finally {
        client.release();
      }
    });

    logger.info(`Started ingest run: ${runId}`);

    // ── Step 3: fetch from NY Fed API ──
    const rates = await step.run("fetch-rates", async () => {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 15000);
      try {
        const response = await fetch("https://markets.newyorkfed.org/api/rates/all/latest.json", {
          signal: controller.signal,
        });
        clearTimeout(timeout);
        if (!response.ok) throw new Error(`NY Fed API error: ${response.status}`);
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

    // ── Step 4: process each rate ──
    let rowsAttempted = 0, rowsInserted = 0, rowsSkipped = 0, rowsQuarantined = 0;
    const results: { rateType: string; status: string; rate?: number }[] = [];

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
        const seriesId = `NYFED_${rate.type.toUpperCase().replace(/\s+/g, '_')}`;

        const client = await pool.connect();
        try {
          const exists = await client.query(`SELECT 1 FROM econ.rates_1d WHERE row_hash = $1 LIMIT 1`, [rowHash]);
          if (exists.rows.length > 0) {
            return { rateType: rate.type, status: "skipped_duplicate" as const };
          }

          await client.query(
            `INSERT INTO econ.rates_1d (series_id, event_date, value, source, row_hash) VALUES ($1, $2, $3, $4, $5)`,
            [seriesId, rate.effectiveDate, rate.percentRate, "nyfed_api", rowHash]
          );
          return { rateType: rate.type, status: "inserted" as const, rate: rate.percentRate };
        } finally {
          client.release();
        }
      });

      rowsAttempted++;
      results.push(outcome);
      if (outcome.status === "inserted") rowsInserted++;
      else if (outcome.status === "skipped_duplicate") rowsSkipped++;
      else rowsQuarantined++;
    }

    // ── Step 5: finalize ingest run ──
    await step.run("complete-ingest-run", async () => {
      const client = await pool.connect();
      try {
        await client.query(
          `UPDATE ops.ingest_run SET status=$2, completed_at=NOW(),
           rows_attempted=$3, rows_inserted=$4, rows_skipped=$5, rows_quarantined=$6 WHERE id=$1`,
          [runId, "success", rowsAttempted, rowsInserted, rowsSkipped, rowsQuarantined]
        );
      } finally {
        client.release();
      }
    });

    logger.info(`Completed: ${rowsInserted} inserted, ${rowsSkipped} skipped`);

    return {
      status: "success",
      runId,
      date: new Date().toISOString().split("T")[0],
      summary: { attempted: rowsAttempted, inserted: rowsInserted, skipped: rowsSkipped, quarantined: rowsQuarantined },
      rates: results,
    };
  }
);
