/**
 * Barchart ZL News (Soybean Oil) Bronze Ingestion
 *
 * Source: https://www.barchart.com/futures/quotes/ZL*0/news
 *
 * Contract:
 * - Writes real, source-derived records only (no synthetic/fallback rows).
 * - Uses raw.event_date as canonical time key for raw schema.
 * - Fails loudly if parsing breaks (better empty than wrong).
 */

import { inngest } from "./client";
import { Pool, type PoolClient } from "pg";
import { createHash } from "crypto";

const BARCHART_ZL_NEWS_URL = "https://www.barchart.com/futures/quotes/ZL*0/news";
const SOURCE = "barchart";
const BUCKET_NAME = "barchart_zl";
const TAGS = ["core", "crush"];

const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
  ssl: { rejectUnauthorized: false },
});

type JsonLdValue = Record<string, unknown> | unknown[] | null;

type ParsedArticle = {
  headline: string;
  url: string;
  publishedAt: string; // ISO string
  eventDate: string; // YYYY-MM-DD
  content?: string;
  rawPayload: Record<string, unknown>;
  rowHash: string;
};

function computeRowHash(url: string, publishedAtIso: string): string {
  return createHash("sha256").update(`${url}|${publishedAtIso}`).digest("hex");
}

function safeJsonParse(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

function normalizeToArray(value: unknown): Record<string, unknown>[] {
  if (!value) return [];
  if (Array.isArray(value)) return value.filter((v): v is Record<string, unknown> => typeof v === "object" && v !== null);
  if (typeof value === "object") return [value as Record<string, unknown>];
  return [];
}

function extractJsonLdObjects(html: string): Record<string, unknown>[] {
  const blocks: string[] = [];
  const re = /<script[^>]*type=["']application\/ld\+json["'][^>]*>([\s\S]*?)<\/script>/gi;
  let match: RegExpExecArray | null = null;
  while ((match = re.exec(html)) !== null) {
    blocks.push(match[1] ?? "");
  }

  const objects: Record<string, unknown>[] = [];
  for (const rawBlock of blocks) {
    const parsed = safeJsonParse(rawBlock) as JsonLdValue;
    const candidates = normalizeToArray(parsed);
    for (const candidate of candidates) {
      const graph = candidate["@graph"];
      if (Array.isArray(graph)) {
        objects.push(...normalizeToArray(graph));
      } else {
        objects.push(candidate);
      }
    }
  }

  return objects;
}

function coerceString(value: unknown): string | null {
  if (typeof value === "string" && value.trim()) return value.trim();
  return null;
}

function resolveUrl(value: string): string {
  if (value.startsWith("http://") || value.startsWith("https://")) return value;
  if (value.startsWith("/")) return `https://www.barchart.com${value}`;
  return value;
}

function parseArticlesFromJsonLd(objects: Record<string, unknown>[]): ParsedArticle[] {
  const articles: ParsedArticle[] = [];

  for (const obj of objects) {
    const type = obj["@type"];
    const types = Array.isArray(type) ? type : [type];
    const isNewsArticle = types.some((t) => String(t).toLowerCase() === "newsarticle");
    if (!isNewsArticle) continue;

    const headline = coerceString(obj.headline) ?? coerceString(obj.name);
    const url = coerceString(obj.url);
    const published = coerceString(obj.datePublished);

    if (!headline || !url || !published) {
      continue;
    }

    const publishedAt = new Date(published);
    if (Number.isNaN(publishedAt.getTime())) {
      continue;
    }

    const publishedIso = publishedAt.toISOString();
    const eventDate = publishedIso.slice(0, 10);
    const resolvedUrl = resolveUrl(url);
    const rowHash = computeRowHash(resolvedUrl, publishedIso);

    const articleBody = coerceString(obj.articleBody);
    const description = coerceString(obj.description);
    const content = articleBody ?? description ?? undefined;

    articles.push({
      headline,
      url: resolvedUrl,
      publishedAt: publishedIso,
      eventDate,
      content,
      rawPayload: obj,
      rowHash,
    });
  }

  return articles;
}

async function createIngestRun(client: PoolClient, jobName: string): Promise<string> {
  const result = await client.query(
    `INSERT INTO ops.ingest_run (job_name, status, started_at) VALUES ($1, 'running', NOW()) RETURNING id`,
    [jobName]
  );
  return result.rows[0].id;
}

async function updateIngestRun(
  client: PoolClient,
  runId: string,
  status: string,
  attempted: number,
  inserted: number,
  skipped: number,
  quarantined: number,
  errorMessage?: string
): Promise<void> {
  await client.query(
    `UPDATE ops.ingest_run SET status=$2, completed_at=NOW(),
     rows_attempted=$3, rows_inserted=$4, rows_skipped=$5, rows_quarantined=$6, error_message=$7 WHERE id=$1`,
    [runId, status, attempted, inserted, skipped, quarantined, errorMessage]
  );
}

async function verifyRawNewsTable(client: PoolClient): Promise<void> {
  const result = await client.query(
    `
    SELECT column_name
    FROM information_schema.columns
    WHERE table_schema='raw' AND table_name='news_articles_event'
    `,
  );
  const cols = new Set<string>(result.rows.map((r) => String(r.column_name)));
  const required = [
    "event_date",
    "headline",
    "content",
    "source",
    "published_at",
    "bucket_name",
    "source_url",
    "raw_payload",
    "ingestion_batch_id",
    "row_hash",
    "specialist_tags",
  ];
  const missing = required.filter((c) => !cols.has(c));
  if (missing.length > 0) {
    throw new Error(
      `raw.news_articles_event missing required columns: ${missing.join(", ")}`
    );
  }
}

async function rowHashExists(client: PoolClient, rowHash: string): Promise<boolean> {
  const r = await client.query(
    `SELECT 1 FROM raw.news_articles_event WHERE row_hash=$1 LIMIT 1`,
    [rowHash]
  );
  return r.rows.length > 0;
}

export const barchartZlNewsDaily = inngest.createFunction(
  { id: "barchart-zl-news-daily", name: "Barchart ZL News Bronze Ingestion", retries: 3 },
  { cron: "30 14 * * 1-5" }, // 8:30AM CT
  async ({ step, logger }) => {
    const client = await pool.connect();
    let runId: string | null = null;
    let rowsAttempted = 0;
    let rowsInserted = 0;
    let rowsSkipped = 0;
    let rowsQuarantined = 0;

    try {
      await step.run("verify-table", async () => {
        await verifyRawNewsTable(client);
      });

      runId = await step.run("create-ingest-run", () =>
        createIngestRun(client, "barchart-zl-news-daily")
      );

      const html = await step.run("fetch", async () => {
        const response = await fetch(BARCHART_ZL_NEWS_URL, {
          headers: { "User-Agent": "ZINC-Fusion/1.0" },
        });
        if (!response.ok) {
          throw new Error(`Barchart fetch error: ${response.status}`);
        }
        return await response.text();
      });

      const parsed = await step.run("parse", async () => {
        const objects = extractJsonLdObjects(html);
        const articles = parseArticlesFromJsonLd(objects);
        return articles;
      });

      if (parsed.length === 0) {
        throw new Error(
          "Parsed 0 NewsArticle items from JSON-LD; page structure may have changed."
        );
      }

      logger.info(`Parsed ${parsed.length} candidate articles from Barchart`);

      for (const article of parsed) {
        const outcome = await step.run(`ingest-${article.rowHash.slice(0, 12)}`, async () => {
          if (await rowHashExists(client, article.rowHash)) {
            return { status: "skipped_duplicate" as const };
          }

          await client.query(
            `INSERT INTO raw.news_articles_event (
              event_date, headline, content, source, published_at, bucket_name,
              source_url, raw_payload, ingestion_batch_id, row_hash, specialist_tags
            ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)`,
            [
              article.eventDate,
              article.headline,
              article.content ?? null,
              SOURCE,
              article.publishedAt,
              BUCKET_NAME,
              article.url,
              JSON.stringify(article.rawPayload),
              runId,
              article.rowHash,
              TAGS,
            ]
          );

          return { status: "inserted" as const };
        });

        rowsAttempted++;
        if (outcome.status === "inserted") rowsInserted++;
        else rowsSkipped++;
      }

      await step.run("complete", () =>
        updateIngestRun(
          client,
          runId!,
          "success",
          rowsAttempted,
          rowsInserted,
          rowsSkipped,
          rowsQuarantined
        )
      );

      return {
        status: "success",
        runId,
        inserted: rowsInserted,
        skipped: rowsSkipped,
      };
    } catch (error) {
      const msg = error instanceof Error ? error.message : String(error);
      if (runId) {
        await updateIngestRun(
          client,
          runId,
          "failed",
          rowsAttempted,
          rowsInserted,
          rowsSkipped,
          rowsQuarantined,
          msg
        );
      }
      throw error;
    } finally {
      client.release();
    }
  }
);

