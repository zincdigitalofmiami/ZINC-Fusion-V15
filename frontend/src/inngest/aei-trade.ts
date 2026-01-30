/**
 * AEI Think Tank RSS Ingestion (Trade Policy feed)
 * 
 * BRONZE CONTRACT COMPLIANT
 * 
 * @author Claude (ZINC-FUSION-V15)
 * @version 2.0.0
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

async function hashExists(client: PoolClient, table: string, hash: string): Promise<boolean> {
  const r = await client.query(`SELECT 1 FROM ${table} WHERE row_hash=$1 LIMIT 1`, [hash]);
  return r.rows.length > 0;
}

export const aeiTradeDaily = inngest.createFunction(
  { id: "aei-trade-daily", name: "AEI Trade Policy RSS Bronze Ingestion", retries: 3 },
  { cron: "0 */8 * * *" }, // Every 8 hours (0:00, 8:00, 16:00 UTC)
  async ({ step, logger }) => {
    const client = await pool.connect();
    let runId: string | null = null;
    let rowsAttempted = 0, rowsInserted = 0, rowsSkipped = 0, rowsQuarantined = 0;

    try {
      await step.run("assert-table", async () => {
        // Fail loudly if the table doesn't exist (no silent DDL in prod).
        await client.query(`SELECT 1 FROM alt.news_1d LIMIT 1`);
      });

      runId = await step.run("create-ingest-run", () => createIngestRun(client, "aei-trade-daily"));
      logger.info(`Started ingest run: ${runId}`);

      const items = await step.run("fetch-rss", async () => {
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 15000); // 15s timeout
        try {
          const response = await fetch("https://www.aei.org/tag/trade-policy/feed/", {
            headers: {
              "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
              "Accept": "application/rss+xml, application/xml, text/xml, */*"
            },
            redirect: "follow",
            signal: controller.signal,
          });
          clearTimeout(timeout);
          if (!response.ok) throw new Error(`AEI RSS error: ${response.status}`);
          const xml = await response.text();
          const parser = new XMLParser({ ignoreAttributes: false });
          const parsed = parser.parse(xml);
          return parsed?.rss?.channel?.item || [];
        } catch (err) {
          clearTimeout(timeout);
          if (err instanceof Error && err.name === 'AbortError') {
            throw new Error('AEI RSS fetch timed out after 15s');
          }
          throw err;
        }
      });

      logger.info(`Fetched ${Array.isArray(items) ? items.length : 1} items from AEI Trade Policy`);

      const itemArray = Array.isArray(items) ? items : [items];
      for (const item of itemArray) {
        const stepId = String(item.guid || item.link || "unknown");
        const outcome = await step.run(`ingest-${stepId}`, async () => {
          const pubDate: string | undefined = item.pubDate;
          if (!pubDate) return { status: "quarantined_missing_pub_date" as const };

          const link: string | undefined = item.link || item.guid;
          if (!link) return { status: "quarantined_missing_link" as const };

          const parsed = new Date(pubDate);
          if (Number.isNaN(parsed.getTime())) return { status: "quarantined_bad_pub_date" as const };

          const rowHash = computeRowHash(link, pubDate);

          if (await hashExists(client, "alt.news_1d", rowHash)) {
            return { status: "skipped_duplicate" as const };
          }

          const eventDate = parsed.toISOString().split("T")[0];
          const categories = item.category ? (Array.isArray(item.category) ? item.category : [item.category]) : [];
          const author = item["dc:creator"] || item.author || "";

          await client.query(
            `INSERT INTO alt.news_1d (
               event_date, headline, content, url, published_at, author,
               source, raw_payload, ingestion_batch_id, row_hash, specialist_tags
             ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)`,
            [
              eventDate,
              item.title,
              item.description,
              item.link,
              pubDate,
              author,
              "aei_rss",
              JSON.stringify(item),
              runId,
              rowHash,
              ["tariff", "trump_effect"]
            ]
          );
          return { status: "inserted" as const };
        });

        rowsAttempted++;
        if (outcome.status === "inserted") rowsInserted++;
        else if (outcome.status === "skipped_duplicate") rowsSkipped++;
        else rowsQuarantined++;
      }

      await step.run("complete", () => updateIngestRun(client, runId!, "success", rowsAttempted, rowsInserted, rowsSkipped, rowsQuarantined));
      logger.info(`Completed: ${rowsInserted} inserted, ${rowsSkipped} skipped`);
      return { status: "success", runId, inserted: rowsInserted, skipped: rowsSkipped };

    } catch (error) {
      const msg = error instanceof Error ? error.message : String(error);
      if (runId) await updateIngestRun(client, runId, "failed", rowsAttempted, rowsInserted, rowsSkipped, rowsQuarantined, msg);
      throw error;
    } finally {
      client.release();
    }
  }
);
