/**
 * Biofuel / RIN Multi-RSS Daily Ingestion
 *
 * INGESTION CONTRACT:
 * - Logs each run in ops.ingest_run
 * - Computes row_hash for idempotency
 * - Append-only inserts (ON CONFLICT DO NOTHING)
 *
 * SOURCES:
 * 1. Biodiesel Magazine RSS — https://www.biodieselmagazine.com/rss/
 * 2. Renewable Fuels Association (RFA) News — https://ethanolrfa.org/feed
 * 3. Clean Fuels Alliance (formerly NBB) — https://cleanfuels.org/feed
 * 4. Biofuels Digest RSS — https://www.biofuelsdigest.com/bdigest/feed/
 * 5. DOE AFDC (Alt Fuels Data Center) — https://afdc.energy.gov/news/feed
 *
 * TARGET TABLE: alt.policy_news_event (specialist_tags: ["biofuel", "energy", "rin"])
 *
 * @author Claude (ZINC-FUSION-V15)
 * @version 1.0.0
 * @date 2026-03-03
 */

import { inngest, DB_CONCURRENCY } from "./client";
import { createHash } from "crypto";
import dbPool from "@/lib/db";

const pool = dbPool;

function computeRowHash(parts: string[]): string {
  return createHash("sha256").update(parts.join("|")).digest("hex");
}

// ---------------------------------------------------------------------------
// RSS feed definitions
// ---------------------------------------------------------------------------

interface RssFeed {
  name: string;
  url: string;
  tags: string[];
}

const BIOFUEL_FEEDS: RssFeed[] = [
  {
    name: "biodiesel_magazine",
    url: "https://www.biodieselmagazine.com/rss/",
    tags: ["biofuel", "energy", "rin", "biodiesel"],
  },
  {
    name: "renewable_fuels_association",
    url: "https://ethanolrfa.org/feed",
    tags: ["biofuel", "energy", "ethanol", "rfs"],
  },
  {
    name: "clean_fuels_alliance",
    url: "https://cleanfuels.org/feed",
    tags: ["biofuel", "energy", "rin", "biodiesel"],
  },
  {
    name: "biofuels_digest",
    url: "https://www.biofuelsdigest.com/bdigest/feed/",
    tags: ["biofuel", "energy", "rin", "renewable"],
  },
  {
    name: "doe_afdc",
    url: "https://afdc.energy.gov/news/feed",
    tags: ["biofuel", "energy", "policy", "infrastructure"],
  },
];

// ---------------------------------------------------------------------------
// RSS parsing (simple XML → items)
// ---------------------------------------------------------------------------

interface RssItem {
  title: string;
  link: string;
  pubDate: string | null;
  description: string;
  author: string | null;
}

function extractTag(xml: string, tag: string): string {
  const re = new RegExp(`<${tag}[^>]*>([\\s\\S]*?)</${tag}>`, "i");
  const m = re.exec(xml);
  if (!m) return "";
  let val = m[1].trim();
  // Strip CDATA
  if (val.startsWith("<![CDATA[")) {
    val = val.slice(9);
    if (val.endsWith("]]>")) val = val.slice(0, -3);
  }
  return val.trim();
}

function parseRssItems(xml: string): RssItem[] {
  const items: RssItem[] = [];
  const itemRegex = /<item[\s>]([\s\S]*?)<\/item>/gi;
  let match;
  while ((match = itemRegex.exec(xml)) !== null) {
    const block = match[1];
    const title = extractTag(block, "title");
    const link = extractTag(block, "link");
    const pubDate = extractTag(block, "pubDate") || extractTag(block, "dc:date") || null;
    const description = extractTag(block, "description");
    const author = extractTag(block, "dc:creator") || extractTag(block, "author") || null;
    if (title && link) {
      items.push({ title, link, pubDate, description: description.slice(0, 1000), author });
    }
  }
  return items;
}

function parseDate(dateStr: string | null): string | null {
  if (!dateStr) return null;
  const d = new Date(dateStr);
  if (isNaN(d.getTime())) return null;
  return d.toISOString().slice(0, 10);
}

// ---------------------------------------------------------------------------
// Inngest function
// ---------------------------------------------------------------------------

export const biofuelRssDaily = inngest.createFunction(
  {
    id: "biofuel-rss-daily",
    name: "Biofuel / RIN Multi-RSS Daily (5 feeds)",
    retries: 3,
    concurrency: [DB_CONCURRENCY],
  },
  { cron: "0 15 * * *" }, // Daily at 15:00 UTC
  async ({ step, logger }) => {
    const allItems = await step.run("fetch-biofuel-rss-feeds", async () => {
      const results: Array<{
        feedName: string;
        title: string;
        url: string;
        eventDate: string;
        description: string;
        author: string | null;
        tags: string[];
        rowHash: string;
      }> = [];

      for (const feed of BIOFUEL_FEEDS) {
        try {
          const controller = new AbortController();
          const timeout = setTimeout(() => controller.abort(), 15_000);
          const res = await fetch(feed.url, {
            headers: { "User-Agent": "ZINC-Fusion/1.0" },
            signal: controller.signal,
          });
          clearTimeout(timeout);

          if (!res.ok) {
            logger.warn(`${feed.name}: HTTP ${res.status}`);
            continue;
          }

          const xml = await res.text();
          const items = parseRssItems(xml);
          logger.info(`${feed.name}: ${items.length} items`);

          for (const item of items) {
            const eventDate = parseDate(item.pubDate) ?? new Date().toISOString().slice(0, 10);
            const rowHash = computeRowHash([item.link, item.pubDate ?? ""]);
            results.push({
              feedName: feed.name,
              title: item.title,
              url: item.link,
              eventDate,
              description: item.description,
              author: item.author,
              tags: feed.tags,
              rowHash,
            });
          }
        } catch (err) {
          const msg = err instanceof Error ? err.message : String(err);
          logger.warn(`${feed.name} failed: ${msg}`);
        }
      }

      return results;
    });

    logger.info(`Total RSS items across all feeds: ${allItems.length}`);

    if (allItems.length === 0) {
      return { status: "no_data", feeds: BIOFUEL_FEEDS.length };
    }

    // ── Insert into alt.policy_news_event ──
    const inserted = await step.run("insert-biofuel-news", async () => {
      const client = await pool.connect();
      let count = 0;
      try {
        const batchSize = 50;
        for (let i = 0; i < allItems.length; i += batchSize) {
          const batch = allItems.slice(i, i + batchSize);
          const values: string[] = [];
          const params: (string | null)[] = [];
          const perRow = 7;

          for (let r = 0; r < batch.length; r++) {
            const base = r * perRow;
            values.push(
              `($${base + 1}::date, $${base + 2}, $${base + 3}, $${base + 4}, $${base + 5}, $${base + 6}::text[], $${base + 7})`
            );
            const b = batch[r];
            // Format as pg array literal: {biofuel,energy,rin}
            const pgTags = `{${b.tags.join(",")}}`;
            params.push(
              b.eventDate, b.title, b.url, b.description,
              b.feedName, pgTags, b.rowHash
            );
          }

          await client.query(
            `INSERT INTO alt.policy_news_event
               (event_date, headline, url, content, source, specialist_tags, row_hash)
             VALUES ${values.join(",")}
             ON CONFLICT DO NOTHING`,
            params
          );
          count += batch.length;
        }
      } finally {
        client.release();
      }
      return count;
    });

    // ── Log ingest run ──
    await step.run("log-ingest-run", async () => {
      const client = await pool.connect();
      try {
        await client.query(
          `INSERT INTO ops.ingest_run (job_name, status, started_at, completed_at,
             rows_attempted, rows_inserted, rows_skipped, rows_quarantined)
           VALUES ($1, 'success', NOW(), NOW(), $2, $3, 0, 0)`,
          ["biofuel-rss-daily", allItems.length, inserted]
        );
      } finally {
        client.release();
      }
    });

    return { status: "success", feeds: BIOFUEL_FEEDS.length, items: allItems.length, inserted };
  }
);
