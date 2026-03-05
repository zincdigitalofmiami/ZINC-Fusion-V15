/**
 * CBP Trade RSS Data Ingestion
 *
 * INGESTION CONTRACT
 * SOURCE: https://www.cbp.gov/rss/trade
 * Tags: tariff, legislation
 *
 * @author Claude (ZINC-FUSION-V15)
 * @version 1.1.0
 * @date 2026-02-16
 */

import { inngest, DB_CONCURRENCY } from "./client";
import { createHash } from "crypto";
import { XMLParser } from "fast-xml-parser";
import { getIngestPool } from "@/lib/db";

const pool = getIngestPool();

function computeRowHash(url: string, pubDate: string): string {
  return createHash("sha256").update(`${url}|${pubDate}`).digest("hex");
}

export const cbpTradeDaily = inngest.createFunction(
  { id: "cbp-trade-daily", name: "CBP Trade RSS Data Ingestion", retries: 3, concurrency: [DB_CONCURRENCY, { limit: 1 }] },
  { cron: "18 6 * * *" }, // Daily at 06:18 UTC
  async ({ step, logger }) => {
    // ── Step 1: assert table exists ──
    await step.run("assert-table", async () => {
      const client = await pool.connect();
      try {
        await client.query(`SELECT 1 FROM alt.policy_news_event LIMIT 1`);
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
           VALUES ($1, 'running', NOW()) RETURNING id`,
          ["cbp-trade-daily"]
        );
        return result.rows[0].id as string;
      } finally {
        client.release();
      }
    });
    logger.info(`Started ingest run: ${runId}`);

    // ── Step 3: fetch RSS feed ──
    const items = await step.run("fetch-rss", async () => {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 15000);
      try {
        const response = await fetch("https://www.cbp.gov/rss/trade", {
          headers: {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/rss+xml, application/xml, text/xml, */*"
          },
          redirect: "follow",
          signal: controller.signal,
        });
        clearTimeout(timeout);
        if (!response.ok) throw new Error(`CBP RSS error: ${response.status}`);
        const xml = await response.text();
        const parser = new XMLParser({ ignoreAttributes: false });
        const parsed = parser.parse(xml);
        return parsed?.rss?.channel?.item || [];
      } catch (err) {
        clearTimeout(timeout);
        if (err instanceof Error && err.name === 'AbortError') {
          throw new Error('CBP RSS fetch timed out after 15s');
        }
        throw err;
      }
    });

    logger.info(`Fetched ${Array.isArray(items) ? items.length : 1} items from CBP Trade RSS`);

    // ── Step 4: process each item ──
    const itemArray = Array.isArray(items) ? items : [items];
    let rowsAttempted = 0, rowsInserted = 0, rowsSkipped = 0, rowsQuarantined = 0;

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

        const client = await pool.connect();
        try {
          const exists = await client.query(`SELECT 1 FROM alt.policy_news_event WHERE row_hash=$1 LIMIT 1`, [rowHash]);
          if (exists.rows.length > 0) return { status: "skipped_duplicate" as const };

          const eventDate = parsed.toISOString().split("T")[0];
          await client.query(
            `INSERT INTO alt.policy_news_event (
               event_date, headline, content, url, published_at,
               source, raw_payload, ingestion_batch_id, row_hash, specialist_tags
             ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)`,
            [
              eventDate,
              item.title,
              item.description,
              item.link,
              pubDate,
              "cbp_rss",
              JSON.stringify(item),
              runId,
              rowHash,
              ["tariff"]
            ]
          );
          return { status: "inserted" as const };
        } finally {
          client.release();
        }
      });

      rowsAttempted++;
      if (outcome.status === "inserted") rowsInserted++;
      else if (outcome.status === "skipped_duplicate") rowsSkipped++;
      else rowsQuarantined++;
    }

    // ── Step 5: finalize ingest run ──
    await step.run("complete", async () => {
      const client = await pool.connect();
      try {
        await client.query(
          `UPDATE ops.ingest_run SET status=$2, completed_at=NOW(),
           rows_attempted=$3, rows_inserted=$4, rows_skipped=$5, rows_quarantined=$6
           WHERE id=$1`,
          [runId, "success", rowsAttempted, rowsInserted, rowsSkipped, rowsQuarantined]
        );
      } finally {
        client.release();
      }
    });

    logger.info(`Completed: ${rowsInserted} inserted, ${rowsSkipped} skipped`);
    return { status: "success", runId, inserted: rowsInserted, skipped: rowsSkipped };
  }
);
