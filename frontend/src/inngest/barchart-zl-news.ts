/**
 * Barchart ZL News (Soybean Oil) Bronze Ingestion
 *
 * Source: https://www.barchart.com/futures/quotes/ZL*0/news
 *
 * Contract:
 * - Writes real, source-derived records only (no synthetic/fallback rows).
 * - Uses event_date as canonical time key for raw schema.
 * - Fails loudly if parsing breaks (better empty than wrong).
 */

import { inngest } from "./client";
import { Pool, type PoolClient } from "pg";
import { createHash } from "crypto";
import { classifySpecialists } from "../lib/specialist-classifier";

const BARCHART_ZL_NEWS_URL = "https://www.barchart.com/futures/quotes/ZL*0/news";
const BARCHART_CORE_API_NEWS_URL = "https://www.barchart.com/proxies/core-api/v1/news/stories";
const BARCHART_SYMBOL = "ZL*0";
const SOURCE = "barchart";
const BUCKET_NAME = "barchart_zl";
// Dynamic tagging - ZL news always gets "crush", plus any detected from headline
const DEFAULT_TAGS = ["crush"];

const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
  ssl: { rejectUnauthorized: false },
});

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

function coerceString(value: unknown): string | null {
  if (typeof value === "string" && value.trim()) return value.trim();
  return null;
}

type BarchartStoryArticle = {
  id?: string;
  title?: string;
  slug?: string;
  published?: string;
  updated?: string;
  summary?: string;
  [k: string]: unknown;
};

function buildBarchartStoryUrl(id: string, slug: string | null): string {
  const safeSlug = slug ? slug : "story";
  return `https://www.barchart.com/story/news/${id}/${safeSlug}`;
}

function parseBarchartTimestampToIso(value: string): string | null {
  const s = value.trim();
  // Examples:
  // - "2025-11-19 15:13:39"
  // - "2025-11-19 15:13:39 +0000"
  const m = s.match(/^(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2}:\d{2})(?:\s+([+-]\d{4}))?$/);
  if (!m) return null;

  const date = m[1];
  const time = m[2];
  const offset = m[3];

  if (offset) {
    const off = `${offset.slice(0, 3)}:${offset.slice(3)}`;
    const dt = new Date(`${date}T${time}${off}`);
    return Number.isNaN(dt.getTime()) ? null : dt.toISOString();
  }

  const dt = new Date(`${date}T${time}Z`);
  return Number.isNaN(dt.getTime()) ? null : dt.toISOString();
}

function parseBarchartStoryPayloadToArticles(payload: unknown): ParsedArticle[] {
  if (!payload || typeof payload !== "object") return [];
  const root = payload as Record<string, unknown>;
  const data = root.data;
  if (!Array.isArray(data)) return [];

  const articles: ParsedArticle[] = [];

  for (const symbolGroup of data) {
    if (!symbolGroup || typeof symbolGroup !== "object") continue;
    const group = symbolGroup as Record<string, unknown>;
    const groupArticles = group.articles;
    if (!Array.isArray(groupArticles)) continue;

    for (const rawArticle of groupArticles) {
      if (!rawArticle || typeof rawArticle !== "object") continue;
      const a = rawArticle as BarchartStoryArticle;

      const id = coerceString(a.id);
      const headline = coerceString(a.title);
      const slug = coerceString(a.slug);
      const updated = coerceString(a.updated);
      const published = coerceString(a.published);
      const summary = coerceString(a.summary) ?? undefined;

      if (!id || !headline || (!updated && !published)) continue;

      const publishedIso =
        (updated ? parseBarchartTimestampToIso(updated) : null) ??
        (published ? parseBarchartTimestampToIso(published) : null);
      if (!publishedIso) continue;

      const url = buildBarchartStoryUrl(id, slug);
      const rowHash = computeRowHash(url, publishedIso);
      const eventDate = publishedIso.slice(0, 10);

      articles.push({
        headline,
        url,
        publishedAt: publishedIso,
        eventDate,
        content: summary,
        rawPayload: rawArticle as Record<string, unknown>,
        rowHash,
      });
    }
  }

  return articles;
}

function getSetCookieHeaders(res: Response): string[] {
  const headersAny = res.headers as unknown as { getSetCookie?: () => string[] };
  if (typeof headersAny.getSetCookie === "function") {
    return headersAny.getSetCookie();
  }
  const raw = res.headers.get("set-cookie");
  return raw ? [raw] : [];
}

function parseCookieKV(setCookie: string): { name: string; value: string } | null {
  const first = setCookie.split(";")[0] ?? "";
  const idx = first.indexOf("=");
  if (idx <= 0) return null;
  const name = first.slice(0, idx).trim();
  const value = first.slice(idx + 1).trim();
  if (!name || !value) return null;
  return { name, value };
}

async function fetchBarchartStoryFeed(): Promise<unknown> {
  // Barchart core-api proxy requires CSRF cookies. Bootstrap a session from the public page.
  const seed = await fetch(BARCHART_ZL_NEWS_URL, {
    headers: { "User-Agent": "ZINC-Fusion/1.0" },
  });
  if (!seed.ok) {
    throw new Error(`Barchart seed page fetch failed: ${seed.status}`);
  }

  const cookies = new Map<string, string>();
  for (const h of getSetCookieHeaders(seed)) {
    const kv = parseCookieKV(h);
    if (kv) cookies.set(kv.name, kv.value);
  }

  const xsrf = cookies.get("XSRF-TOKEN");
  if (!xsrf) {
    throw new Error("Barchart seed did not return XSRF-TOKEN cookie");
  }

  const cookieHeader = Array.from(cookies.entries())
    .map(([k, v]) => `${k}=${v}`)
    .join("; ");

  const apiUrl = new URL(BARCHART_CORE_API_NEWS_URL);
  apiUrl.searchParams.set("raw", "1");
  apiUrl.searchParams.set("symbols", BARCHART_SYMBOL);
  apiUrl.searchParams.set("limit", "50");

  const res = await fetch(apiUrl.toString(), {
    headers: {
      "User-Agent": "ZINC-Fusion/1.0",
      "X-Requested-With": "XMLHttpRequest",
      "X-XSRF-TOKEN": decodeURIComponent(xsrf),
      Cookie: cookieHeader,
      Accept: "application/json",
    },
  });

  if (!res.ok) {
    throw new Error(`Barchart core-api news fetch failed: ${res.status}`);
  }

  return await res.json();
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

async function verifyNewsTable(client: PoolClient): Promise<void> {
  const result = await client.query(
    `
    SELECT column_name
    FROM information_schema.columns
    WHERE table_schema='alt' AND table_name='news_1d'
    `,
  );
  const cols = new Set<string>(result.rows.map((r) => String(r.column_name)));
  const required = [
    "event_date",
    "headline",
    "content",
    "source",
    "published_at",
    "url",
    "raw_payload",
    "ingestion_batch_id",
    "row_hash",
    "specialist_tags",
  ];
  const missing = required.filter((c) => !cols.has(c));
  if (missing.length > 0) {
    throw new Error(`alt.news_1d missing required columns: ${missing.join(", ")}`);
  }
}

async function rowHashExists(client: PoolClient, rowHash: string): Promise<boolean> {
  const r = await client.query(
    `SELECT 1 FROM alt.news_1d WHERE row_hash=$1 LIMIT 1`,
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
        await verifyNewsTable(client);
      });

      runId = await step.run("create-ingest-run", () =>
        createIngestRun(client, "barchart-zl-news-daily")
      );

      const parsed = await step.run("fetch+parse", async () => {
        const payload = await fetchBarchartStoryFeed();
        return parseBarchartStoryPayloadToArticles(payload);
      });

      if (parsed.length === 0) {
        throw new Error(
          "Parsed 0 Barchart story items; source or API payload may have changed."
        );
      }

      logger.info(`Parsed ${parsed.length} candidate articles from Barchart`);

      for (const article of parsed) {
        const outcome = await step.run(`ingest-${article.rowHash.slice(0, 12)}`, async () => {
          if (await rowHashExists(client, article.rowHash)) {
            return { status: "skipped_duplicate" as const };
          }

          // Dynamic tagging using shared classifier
          const detectedTags = classifySpecialists(article.headline);
          // Ensure "crush" is always present for ZL news, merge with detected
          const tags = Array.from(new Set([...DEFAULT_TAGS, ...detectedTags.filter(t => t !== "general")]));

          await client.query(
            `INSERT INTO alt.news_1d (
              event_date, headline, content, source, published_at,
              url, raw_payload, ingestion_batch_id, row_hash, specialist_tags
            ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)`,
            [
              article.eventDate,
              article.headline,
              article.content ?? null,
              SOURCE,
              article.publishedAt,
              article.url,
              JSON.stringify(article.rawPayload),
              runId,
              article.rowHash,
              tags,
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
