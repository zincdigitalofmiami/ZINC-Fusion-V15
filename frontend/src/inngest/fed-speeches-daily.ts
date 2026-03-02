/**
 * Federal Reserve Speeches RSS Ingestion
 *
 * INGESTION CONTRACT:
 * - Logs each run in ops.ingest_run
 * - Computes row_hash for idempotency (url|pubDate)
 * - Append-only inserts (skips duplicates via row_hash check)
 * - Detects hawkish/dovish sentiment from title + description keywords
 *
 * SOURCE: https://www.federalreserve.gov/feeds/speeches.xml
 * - Public RSS feed, no authentication required
 * - Contains: title, link, description, pubDate, dc:creator (speaker)
 *
 * TARGET TABLE: alt.policy_news_event (shared with farmdoc-rins, etc.)
 * specialist_tags: ["fed", "fx"]
 *
 * @author Claude (ZINC-FUSION-V15)
 * @version 1.0.0
 * @date 2026-02-26
 */

import { inngest, DB_CONCURRENCY } from "./client";
import { createHash } from "crypto";
import { XMLParser } from "fast-xml-parser";
import dbPool from "@/lib/db";

const pool = dbPool;

const FED_SPEECHES_RSS = "https://www.federalreserve.gov/feeds/speeches.xml";
const SOURCE_NAME = "federal_reserve_speeches";
const USER_AGENT = "ZINC-Fusion/1.0";
const SPECIALIST_TAGS = ["fed", "fx"];

// ---------------------------------------------------------------------------
// Sentiment keywords
// ---------------------------------------------------------------------------

const HAWKISH_KEYWORDS = [
  "inflation",
  "tightening",
  "rate hike",
  "restrictive",
  "overheating",
  "hawkish",
];

const DOVISH_KEYWORDS = [
  "easing",
  "rate cut",
  "accommodative",
  "slowdown",
  "dovish",
  "recession",
];

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface FedSpeechItem {
  title?: string;
  link?: string;
  guid?: string | { "#text"?: string };
  description?: string;
  pubDate?: string;
  "dc:creator"?: string;
  author?: string;
}

interface SentimentResult {
  sentiment: "hawkish" | "dovish" | "neutral";
  hawkishHits: string[];
  dovishHits: string[];
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function computeRowHash(url: string, pubDate: string): string {
  return createHash("sha256").update(`${url}|${pubDate}`).digest("hex");
}

/**
 * Scan text for hawkish/dovish keyword matches and classify overall sentiment.
 */
function detectSentiment(title: string, description: string): SentimentResult {
  const text = `${title} ${description}`.toLowerCase();

  const hawkishHits = HAWKISH_KEYWORDS.filter((kw) => text.includes(kw));
  const dovishHits = DOVISH_KEYWORDS.filter((kw) => text.includes(kw));

  let sentiment: "hawkish" | "dovish" | "neutral";
  if (hawkishHits.length > dovishHits.length) {
    sentiment = "hawkish";
  } else if (dovishHits.length > hawkishHits.length) {
    sentiment = "dovish";
  } else if (hawkishHits.length > 0 && dovishHits.length > 0) {
    sentiment = "neutral"; // mixed signals
  } else {
    sentiment = "neutral";
  }

  return { sentiment, hawkishHits, dovishHits };
}

/**
 * Extract the GUID string from an RSS item that may be a string or an object.
 */
function extractGuid(item: FedSpeechItem): string | undefined {
  if (typeof item.guid === "string") return item.guid;
  if (item.guid && typeof item.guid === "object") return item.guid["#text"];
  return undefined;
}

// ---------------------------------------------------------------------------
// Inngest function
// ---------------------------------------------------------------------------

export const fedSpeechesDaily = inngest.createFunction(
  {
    id: "fed-speeches-daily",
    name: "Federal Reserve Speeches RSS Ingestion",
    retries: 3,
    concurrency: [DB_CONCURRENCY, { limit: 1 }],
  },
  { cron: "0 18 * * *" }, // Daily at 18:00 UTC
  async ({ step, logger }) => {
    // ── Step 1: assert table exists ──
    await step.run("assert-table", async () => {
      const client = await pool.connect();
      try {
        await client.query("SELECT 1 FROM alt.policy_news_event LIMIT 1");
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
          ["fed-speeches-daily"]
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
      const timeout = setTimeout(() => controller.abort(), 15_000);
      try {
        const response = await fetch(FED_SPEECHES_RSS, {
          headers: { "User-Agent": USER_AGENT },
          redirect: "follow",
          signal: controller.signal,
        });
        clearTimeout(timeout);

        if (!response.ok) {
          throw new Error(`Fed speeches RSS error: ${response.status} ${response.statusText}`);
        }

        const xml = await response.text();
        const parser = new XMLParser({
          ignoreAttributes: false,
          // dc:creator uses namespace prefix
        });
        const parsed = parser.parse(xml);

        // RSS 2.0 structure: rss > channel > item
        const channel = parsed?.rss?.channel;
        if (!channel) {
          throw new Error("Fed speeches RSS: no channel element found");
        }

        const rawItems = channel.item;
        if (!rawItems) return [];
        return (Array.isArray(rawItems) ? rawItems : [rawItems]) as FedSpeechItem[];
      } catch (err) {
        clearTimeout(timeout);
        if (err instanceof Error && err.name === "AbortError") {
          throw new Error("Fed speeches RSS fetch timed out after 15s");
        }
        throw err;
      }
    });

    logger.info(`Fetched ${items.length} items from Federal Reserve speeches RSS`);

    // ── Step 4: process each item ──
    const itemArray = Array.isArray(items) ? items : [items];
    let rowsAttempted = 0;
    let rowsInserted = 0;
    let rowsSkipped = 0;
    let rowsQuarantined = 0;

    for (const item of itemArray) {
      const link = item.link || extractGuid(item);
      const stepId = link ? createHash("md5").update(link).digest("hex").slice(0, 12) : `item-${rowsAttempted}`;

      const outcome = await step.run(`ingest-${stepId}`, async () => {
        const pubDate = item.pubDate;
        if (!pubDate) return { status: "quarantined_missing_pub_date" as const };

        const url = item.link || extractGuid(item);
        if (!url) return { status: "quarantined_missing_link" as const };

        const parsed = new Date(pubDate);
        if (Number.isNaN(parsed.getTime())) return { status: "quarantined_bad_pub_date" as const };

        const rowHash = computeRowHash(url, pubDate);

        const client = await pool.connect();
        try {
          // Check for duplicate
          const exists = await client.query(
            "SELECT 1 FROM alt.policy_news_event WHERE row_hash = $1 LIMIT 1",
            [rowHash]
          );
          if (exists.rows.length > 0) return { status: "skipped_duplicate" as const };

          const eventDate = parsed.toISOString().split("T")[0];
          const title = item.title || "";
          const description = item.description || "";
          const speaker = item["dc:creator"] || item.author || "";

          // Sentiment detection
          const { sentiment, hawkishHits, dovishHits } = detectSentiment(title, description);

          // Build content with sentiment annotation
          const contentParts = [description];
          if (hawkishHits.length > 0 || dovishHits.length > 0) {
            contentParts.push(
              `\n[Sentiment: ${sentiment}]` +
              (hawkishHits.length > 0 ? ` Hawkish: ${hawkishHits.join(", ")}` : "") +
              (dovishHits.length > 0 ? ` Dovish: ${dovishHits.join(", ")}` : "")
            );
          }

          const rawPayload = JSON.stringify({
            ...item,
            _sentiment: sentiment,
            _hawkish_keywords: hawkishHits,
            _dovish_keywords: dovishHits,
          });

          await client.query(
            `INSERT INTO alt.policy_news_event (
               event_date, headline, content, url, published_at, author,
               source, raw_payload, ingestion_batch_id, row_hash, specialist_tags
             ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)`,
            [
              eventDate,
              title,
              contentParts.join(""),
              url,
              pubDate,
              speaker,
              SOURCE_NAME,
              rawPayload,
              runId,
              rowHash,
              SPECIALIST_TAGS,
            ]
          );
          return { status: "inserted" as const, sentiment };
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

    logger.info(
      `Fed speeches complete: ${rowsInserted} inserted, ${rowsSkipped} skipped, ${rowsQuarantined} quarantined`
    );

    return {
      status: "success",
      runId,
      attempted: rowsAttempted,
      inserted: rowsInserted,
      skipped: rowsSkipped,
      quarantined: rowsQuarantined,
    };
  }
);
