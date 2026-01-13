/**
 * EIA Today in Energy RSS Bronze Ingestion
 * 
 * BRONZE CONTRACT COMPLIANT
 * SOURCE: https://www.eia.gov/rss/todayinenergy.xml
 * Tags: energy
 * 
 * @author Claude (ZINC-FUSION-V15)
 * @version 1.0.0
 * @date 2026-01-13
 */

import { inngest } from "./client";
import { Pool, type PoolClient } from "pg";
import { createHash } from "crypto";
import { XMLParser } from "fast-xml-parser";

const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
  ssl: { rejectUnauthorized: false },
});

function computeRowHash(url: string, pubDate: string): string {
  return createHash("sha256").update(`${url}|${pubDate}`).digest("hex");
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
  const r = await client.query(`SELECT 1 FROM raw.news_articles_1d WHERE row_hash=$1 LIMIT 1`, [hash]);
  return r.rows.length > 0;
}

export const eiaDaily = inngest.createFunction(
  { id: "eia-daily", name: "EIA Today in Energy RSS Bronze Ingestion", retries: 3 },
  { cron: "0 16 * * 1-5" }, // 10AM CT weekdays
  async ({ step, logger }) => {
    const client = await pool.connect();
    let runId: string | null = null;
    let rowsAttempted = 0, rowsInserted = 0, rowsSkipped = 0, rowsQuarantined = 0;

    try {
      runId = await step.run("create-ingest-run", () => createIngestRun(client, "eia-daily"));
      logger.info(`Started ingest run: ${runId}`);

      const items = await step.run("fetch-rss", async () => {
        const response = await fetch("https://www.eia.gov/rss/todayinenergy.xml", {
          headers: { "User-Agent": "ZINC-Fusion/1.0" }
        });
        if (!response.ok) throw new Error(`EIA RSS error: ${response.status}`);
        const xml = await response.text();
        const parser = new XMLParser({ ignoreAttributes: false });
        const parsed = parser.parse(xml);
        return parsed?.rss?.channel?.item || [];
      });

      logger.info(`Fetched ${Array.isArray(items) ? items.length : 1} items from EIA RSS`);

      const itemArray = Array.isArray(items) ? items : [items];
      for (const item of itemArray) {
        rowsAttempted++;
        
        const outcome = await step.run(`ingest-${item.guid || item.link}`, async () => {
          const pubDate = item.pubDate || new Date().toISOString();
          const rowHash = computeRowHash(item.link || item.guid, pubDate);

          if (await hashExists(client, rowHash)) {
            return { status: "skipped_duplicate" as const };
          }

          const eventDate = new Date(pubDate).toISOString().split("T")[0];
          const categories = item.category ? (Array.isArray(item.category) ? item.category : [item.category]) : [];
          const author = item["dc:creator"] || item.author || "";

          await client.query(
            `INSERT INTO raw.news_articles_1d (
               event_date, headline, content, url, published_at, author,
               source, source_url, raw_payload, ingestion_batch_id, row_hash, specialist_tags
             ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)`,
            [
              eventDate, item.title, item.description, item.link, pubDate, author,
              "eia_rss",
              "https://www.eia.gov/rss/todayinenergy.xml",
              JSON.stringify(item), runId, rowHash,
              ["energy"]
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
      logger.info(`Completed: ${rowsInserted} inserted, ${rowsSkipped} skipped`);
      return { status: "success", runId, inserted: rowsInserted, skipped: rowsSkipped };

    } catch (error) {
      const msg = error instanceof Error ? error.message : String(error);
      if (runId) await updateIngestRun(client, runId, "failed", rowsAttempted, rowsInserted, rowsSkipped, rowsQuarantined, msg);
      logger.error(`EIA RSS ingestion failed: ${msg}`);
      throw error;
    } finally {
      client.release();
    }
  }
);
