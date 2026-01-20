/**
 * USDA NASS QuickStats API Bronze Ingestion
 * 
 * BRONZE CONTRACT COMPLIANT
 * SOURCE: https://quickstats.nass.usda.gov/api/api_GET
 * Tags: crush
 * 
 * @author Claude (ZINC-FUSION-V15)
 * @version 1.0.0
 * @date 2026-01-13
 */

import { inngest } from "./client";
import { Pool, type PoolClient } from "pg";
import { createHash } from "crypto";

const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
  ssl: { rejectUnauthorized: false },
});

function computeRowHash(seriesId: string, date: string, value: string): string {
  return createHash("sha256").update(`${seriesId}|${date}|${value}`).digest("hex");
}

async function createIngestRun(client: PoolClient, jobName: string): Promise<string> {
  const result = await client.query(
    `INSERT INTO ops.ingest_run (job_name, status, started_at) VALUES ($1, 'running', NOW()) RETURNING id`,
    [jobName]
  );
  return result.rows[0].id;
}

async function updateIngestRun(
  client: PoolClient, runId: string, status: string,
  attempted: number, inserted: number, skipped: number, quarantined: number,
  errorMessage?: string
): Promise<void> {
  await client.query(
    `UPDATE ops.ingest_run SET status=$2, completed_at=NOW(),
     rows_attempted=$3, rows_inserted=$4, rows_skipped=$5, rows_quarantined=$6, error_message=$7 WHERE id=$1`,
    [runId, status, attempted, inserted, skipped, quarantined, errorMessage]
  );
}

async function hashExists(client: PoolClient, hash: string): Promise<boolean> {
  const r = await client.query(`SELECT 1 FROM econ.rates_1d WHERE row_hash=$1 LIMIT 1`, [hash]);
  return r.rows.length > 0;
}

export const nassWeekly = inngest.createFunction(
  { id: "nass-weekly", name: "USDA NASS API Bronze Ingestion", retries: 3 },
  { cron: "0 17 * * 5" }, // Fridays 11AM CT
  async ({ step, logger }) => {
    const client = await pool.connect();
    let runId: string | null = null;
    let rowsAttempted = 0, rowsInserted = 0, rowsSkipped = 0, rowsQuarantined = 0;

    try {
      const apiKey = process.env.USDA_API_KEY;
      if (!apiKey) {
        throw new Error("USDA_API_KEY not configured");
      }

      runId = await step.run("create-ingest-run", () => createIngestRun(client, "nass-weekly"));
      logger.info(`Started ingest run: ${runId}`);

      const data = await step.run("fetch-api", async () => {
        const currentYear = new Date().getFullYear();
        const stats = ["PRODUCTION", "YIELD", "AREA PLANTED"];
        interface NASSRow {
          year: number;
          commodity_desc: string;
          statisticcat_desc: string;
          Value: string;
          short_desc: string;
        }
        const allData: NASSRow[] = [];

        for (const stat of stats) {
          const url = `https://quickstats.nass.usda.gov/api/api_GET?key=${apiKey}&commodity_desc=SOYBEANS&year=${currentYear}&format=JSON&statisticcat_desc=${encodeURIComponent(stat)}`;
          const response = await fetch(url);
          if (!response.ok) {
            console.error(`NASS API error for ${stat}: ${response.status}`);
            continue;
          }
          const json = await response.json();
          if (json.data) {
            allData.push(...json.data);
          }
        }
        return allData;
      });

      logger.info(`Fetched ${data.length} records from NASS API`);

      for (const row of data) {
        rowsAttempted++;
        
        const outcome = await step.run(`ingest-${row.year}-${row.short_desc}`, async () => {
          const obsDate = `${row.year}-01-01`;
          const seriesId = `NASS_${row.commodity_desc}_${row.statisticcat_desc}`.replace(/\s+/g, '_').toUpperCase();
          const value = row.Value ? parseFloat(row.Value.replace(/,/g, "")) : null;
          
          if (value === null || isNaN(value)) {
            return { status: "skipped_invalid" as const };
          }

          const rowHash = computeRowHash(seriesId, obsDate, row.Value);

          if (await hashExists(client, rowHash)) {
            return { status: "skipped_duplicate" as const };
          }

          await client.query(
            `INSERT INTO econ.rates_1d (
               series_id, event_date, value, source, row_hash
             ) VALUES ($1,$2,$3,$4,$5)`,
            [
              seriesId,
              obsDate,
              value,
              "nass_api",
              rowHash,
            ]
          );
          return { status: "inserted" as const };
        });

        if (outcome.status === "inserted") {
          rowsInserted++;
        } else {
          rowsSkipped++;
        }
      }

      await step.run("complete", () => updateIngestRun(client, runId!, "success", rowsAttempted, rowsInserted, rowsSkipped, rowsQuarantined));
      logger.info(`NASS ingestion complete: ${rowsInserted} inserted, ${rowsSkipped} skipped`);
      return { status: "success", runId, inserted: rowsInserted, skipped: rowsSkipped };

    } catch (error) {
      const msg = error instanceof Error ? error.message : String(error);
      if (runId) await updateIngestRun(client, runId, "failed", rowsAttempted, rowsInserted, rowsSkipped, rowsQuarantined, msg);
      logger.error(`NASS API ingestion failed: ${msg}`);
      throw error;
    } finally {
      client.release();
    }
  }
);
