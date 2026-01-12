/**
 * ICE Releases RSS Bronze Ingestion
 * 
 * BRONZE CONTRACT COMPLIANT
 * SOURCE: https://www.ice.gov/rss
 * Tags: trump_effect, legislation, volatility
 * 
 * @author Claude (ZINC-FUSION-V15)
 * @version 1.0.0
 * @date 2026-01-11
 */

import { inngest } from "./client";
import { Pool } from "pg";
import { createHash } from "crypto";
import { XMLParser } from "fast-xml-parser";

const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
  ssl: { rejectUnauthorized: false },
});

function computeRowHash(url: string, pubDate: string): string {
  return createHash("sha256").update(`${url}|${pubDate}`).digest("hex");
}

async function createIngestRun(client: any, jobName: string): Promise<string> {
  const result = await client.query(
    `INSERT INTO ops.ingest_run (job_name, status, started_at) VALUES ($1, 'running', NOW()) RETURNING id`,
    [jobName]
  );
  return result.rows[0].id;
}

async function updateIngestRun(
  client: any, runId: string, status: string,
  attempted: number, inserted: number, skipped: number, quarantined: number,
  errorMessage?: string
): Promise<void> {
  await client.query(
    `UPDATE ops.ingest_run SET status=$2, completed_at=NOW(),
     rows_attempted=$3, rows_inserted=$4, rows_skipped=$5, rows_quarantined=$6, error_message=$7 WHERE id=$1`,
    [runId, status, attempted, inserted, skipped, quarantined, errorMessage]
  );
}

async function hashExists(client: any, table: string, hash: string): Promise<boolean> {
  const r = await client.query(`SELECT 1 FROM ${table} WHERE row_hash=$1 LIMIT 1`, [hash]);
  return r.rows.length > 0;
}

export const iceReleasesDaily = inngest.createFunction(
  { id: "ice-releases-daily", name: "ICE Releases RSS Bronze Ingestion", retries: 3 },
  { cron: "0 13 * * 1-5" }, // 7AM CT
  async ({ step, logger }) => {
    const client = await pool.connect();
    let runId: string | null = null;
    let rowsAttempted = 0, rowsInserted = 0, rowsSkipped = 0, rowsQuarantined = 0;

    try {
      await step.run("ensure-table", async () => {
        await client.query(`
          CREATE TABLE IF NOT EXISTS raw.ice_releases_event (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            event_date DATE NOT NULL,
            title TEXT,
            description TEXT,
            link TEXT,
            pub_date TIMESTAMPTZ,
            guid TEXT,
            knowledge_time TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            revision_no INTEGER NOT NULL DEFAULT 1,
            is_preliminary BOOLEAN DEFAULT false,
            validation_status TEXT DEFAULT 'validated',
            source_url TEXT,
            raw_payload JSONB,
            ingestion_batch_id UUID,
            row_hash TEXT NOT NULL,
            specialist_tags TEXT[] NOT NULL
          )
        `);
        await client.query(`CREATE INDEX IF NOT EXISTS idx_ice_releases_hash ON raw.ice_releases_event(row_hash)`);
        await client.query(`CREATE INDEX IF NOT EXISTS idx_ice_releases_tags ON raw.ice_releases_event USING GIN(specialist_tags)`);
      });

      runId = await step.run("create-ingest-run", () => createIngestRun(client, "ice-releases-daily"));
      logger.info(`Started ingest run: ${runId}`);

      const items = await step.run("fetch-rss", async () => {
        const response = await fetch("https://www.ice.gov/rss", {
          headers: { "User-Agent": "ZINC-Fusion/1.0" }
        });
        if (!response.ok) throw new Error(`ICE RSS error: ${response.status}`);
        const xml = await response.text();
        const parser = new XMLParser({ ignoreAttributes: false });
        const parsed = parser.parse(xml);
        return parsed?.rss?.channel?.item || parsed?.feed?.entry || [];
      });

      logger.info(`Fetched ${Array.isArray(items) ? items.length : 1} items from ICE RSS`);

      const itemArray = Array.isArray(items) ? items : [items];
      const batchResult = await step.run("process-items", async () => {
        let batchAttempted = 0;
        let batchInserted = 0;
        let batchSkipped = 0;

        for (const item of itemArray) {
          batchAttempted++;
          const pubDate = item.pubDate || item.published || item.updated || new Date().toISOString();
          const link = item.link?.["@_href"] || item.link || "";
          const rowHash = computeRowHash(link || item.guid || item.id, pubDate);

          if (await hashExists(client, "raw.ice_releases_event", rowHash)) {
            batchSkipped++;
            continue;
          }

          const eventDate = new Date(pubDate).toISOString().split("T")[0];
          const title = item.title?.["#text"] || item.title || "";
          const description = item.description || item.summary?.["#text"] || item.summary || "";

          await client.query(
            `INSERT INTO raw.ice_releases_event (
               event_date, title, description, link, pub_date, guid,
               source_url, raw_payload, ingestion_batch_id, row_hash, specialist_tags
             ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)`,
            [
              eventDate, title, description, link, pubDate, item.guid || item.id,
              "https://www.ice.gov/rss", JSON.stringify(item), runId, rowHash,
              ["trump_effect", "legislation", "volatility"]
            ]
          );
          batchInserted++;
        }

        return { attempted: batchAttempted, inserted: batchInserted, skipped: batchSkipped };
      });

      rowsAttempted += batchResult.attempted;
      rowsInserted += batchResult.inserted;
      rowsSkipped += batchResult.skipped;

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
