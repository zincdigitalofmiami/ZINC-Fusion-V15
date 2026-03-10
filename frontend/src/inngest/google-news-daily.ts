/**
 * Google News RSS Daily — segmented lane ingestion for policy/news context.
 *
 * Source: Google News RSS (free, no API key).
 * URL: https://news.google.com/rss/search?q={encoded_query}&hl=en-US&gl=US&ceid=US:en
 *
 * IMPORTANT CONTRACTS:
 * - This remains confirmation/context enrichment only (not primary presidential action counters).
 * - Strict date policy: rows with missing/invalid pubDate are rejected.
 * - Freshness gate: stale historical rows are rejected before insert.
 */

import { inngest, DB_CONCURRENCY } from "./client";
import { getIngestPool } from "@/lib/db";
import {
  hashFields,
  createIngestRun,
  finalizeIngestRun,
  failIngestRun,
} from "./utils";

const pool = getIngestPool();
const JOB_NAME = "google-news-daily";
const SOURCE_NAME = "google_news";
const USER_AGENT = "Mozilla/5.0 (ZINC-Fusion/1.0)";
const GOOGLE_NEWS_RSS_BASE = "https://news.google.com/rss/search";
const DAY_MS = 24 * 60 * 60 * 1000;
const SOURCE_MAX_LENGTH = 100;

export const MAX_NEWS_ITEM_AGE_DAYS = 21;
const MAX_FUTURE_SKEW_DAYS = 1;

export interface GoogleNewsLane {
  slug: string;
  label: string;
  queries: string[];
  baseTags: string[];
}

/**
 * Explicit Google News lanes required by product contract.
 * Lane identity is preserved in `source` and specialist tags.
 */
export const GOOGLE_NEWS_LANES: GoogleNewsLane[] = [
  {
    slug: "ice_immigration",
    label: "ICE / Immigration",
    queries: [
      "ICE funding hiring Homeland Security budget enforcement policy",
      "Department of Homeland Security immigration funding detention facilities",
      "ICE shelter housing contract procurement federal immigration",
      "White House border security executive action ICE operations",
    ],
    baseTags: ["trump_effect", "tariff"],
  },
  {
    slug: "war_military",
    label: "War / Military",
    queries: [
      "U.S. military deployment Middle East Pentagon policy action",
      "administration defense contractor deal Middle East security",
      "White House national security aid package force posture",
      "presidential foreign policy military escalation de-escalation",
    ],
    baseTags: ["energy", "trump_effect"],
  },
  {
    slug: "soybean_oil",
    label: "Soybean Oil",
    queries: [
      "soybean oil futures policy biofuel mandate tariff",
      "soybean oil trade flow policy export import",
      "soybean oil alternatives palm oil canola sunflower market",
      "palm oil industry news supply export Indonesia Malaysia",
    ],
    baseTags: ["crush", "substitutes", "energy"],
  },
  {
    slug: "soybean_agriculture",
    label: "Soybean Agriculture",
    queries: [
      "China soybean supply demand import outlook",
      "China soybean trade U.S. Brazil tariff policy",
      "USDA soybean export sales policy update",
      "soybean agriculture federal policy acreage logistics",
    ],
    baseTags: ["china", "crush", "tariff"],
  },
  {
    slug: "trump_actions",
    label: "Trump Actions",
    queries: [
      "Trump executive order trade tariff sanctions action",
      "Trump discussions with foreign leaders bilateral deal policy",
      "Trump administration lobbying White House policy influence",
      "Trump family administration business deal scrutiny",
    ],
    baseTags: ["trump_effect", "tariff"],
  },
  {
    slug: "legislation",
    label: "Legislation",
    queries: [
      "Congress agriculture trade bill tariff oversight",
      "federal legislation soybean oil biofuel tax credit",
      "Senate House trade policy legislation customs enforcement",
      "lobbying disclosure bill White House trade policy",
    ],
    baseTags: ["tariff", "fed", "biofuel"],
  },
  {
    slug: "biofuel",
    label: "Biofuel",
    queries: [
      "renewable fuel standard biodiesel policy",
      "EPA biofuel mandate soybean oil",
      "renewable diesel policy U.S.",
    ],
    baseTags: ["biofuel", "energy", "crush"],
  },
];

/** Cross-tag keywords for specialist routing. */
const CROSS_TAG_KEYWORDS: Record<string, string[]> = {
  crush: ["crush", "soybean oil", "soy oil", "processing", "soy meal"],
  china: ["china", "chinese", "beijing", "xi jinping", "soybean imports", "soybean trade"],
  substitutes: ["palm oil", "canola", "rapeseed", "sunflower", "olive oil", "soybean alternatives"],
  fx: ["dollar", "currency", "forex", "exchange rate", "yuan", "real"],
  fed: ["federal reserve", "fomc", "interest rate", "monetary policy", "inflation"],
  tariff: ["tariff", "trade war", "sanctions", "import duty", "trade policy", "ustr", "customs"],
  energy: ["crude oil", "opec", "petroleum", "natural gas", "energy"],
  biofuel: ["biodiesel", "renewable diesel", "rin", "biofuel", "ethanol", "saf"],
  palm: ["palm oil", "mpob", "indonesia", "malaysia palm"],
  volatility: ["volatility", "vix", "risk", "market crash", "sell-off"],
  trump_effect: [
    "trump",
    "executive order",
    "presidential",
    "white house",
    "homeland security",
    "ice",
    "lobbying",
    "state visit",
    "foreign leader",
  ],
};

export interface ParsedGoogleNewsItem {
  headline: string;
  url: string | null;
  publishedAt: string; // ISO timestamp
  eventDate: string; // YYYY-MM-DD (UTC)
  pubSource: string;
}

interface PreparedRow {
  eventDate: string;
  publishedAt: string;
  headline: string;
  url: string | null;
  source: string;
  specialistTags: string[];
  rowHash: string;
}

interface LanePreparationStats {
  attempted: number;
  stale: number;
  invalidDate: number;
  deduped: number;
  prepared: number;
}

function laneTag(slug: string): string {
  return `lane_${slug}`;
}

function sanitizePublicationSource(pubSource: string): string {
  const trimmed = pubSource.trim().replace(/\s+/g, " ");
  const noSlash = trimmed.replace(/[/]+/g, "-");
  return noSlash.length > 0 ? noSlash : "unknown";
}

export function buildLaneSourceValue(laneSlug: string, pubSource: string): string {
  const lanePart = laneSlug.trim();
  const sourcePart = sanitizePublicationSource(pubSource);
  const raw = `${SOURCE_NAME}/${lanePart}/${sourcePart}`;
  if (raw.length <= SOURCE_MAX_LENGTH) return raw;
  return raw.slice(0, SOURCE_MAX_LENGTH);
}

/**
 * Strict freshness check for news rows.
 * - Rejects invalid timestamps.
 * - Rejects future dates beyond a small skew allowance.
 * - Rejects stale rows older than maxAgeDays.
 */
export function isPublishedAtFresh(
  publishedAtIso: string,
  now: Date = new Date(),
  maxAgeDays: number = MAX_NEWS_ITEM_AGE_DAYS,
): boolean {
  const ts = Date.parse(publishedAtIso);
  if (Number.isNaN(ts)) return false;

  const ageMs = now.getTime() - ts;
  if (ageMs < -MAX_FUTURE_SKEW_DAYS * DAY_MS) return false;
  if (ageMs > maxAgeDays * DAY_MS) return false;
  return true;
}

/**
 * Parse Google News RSS XML.
 * Rows without valid pubDate are rejected by design.
 */
export function parseRssXml(xml: string): ParsedGoogleNewsItem[] {
  const items: ParsedGoogleNewsItem[] = [];
  const itemRegex = /<item>([\s\S]*?)<\/item>/g;
  let match: RegExpExecArray | null;

  while ((match = itemRegex.exec(xml)) !== null) {
    const item = match[1];

    const titleMatch = /<title>([\s\S]*?)<\/title>/.exec(item);
    const linkMatch = /<link>([\s\S]*?)<\/link>/.exec(item);
    const pubDateMatch = /<pubDate>([\s\S]*?)<\/pubDate>/.exec(item);
    const sourceMatch = /<source[^>]*>([\s\S]*?)<\/source>/.exec(item);

    if (!titleMatch?.[1]?.trim()) continue;
    if (!pubDateMatch?.[1]?.trim()) continue;

    const parsedDate = new Date(pubDateMatch[1].trim());
    if (Number.isNaN(parsedDate.getTime())) continue;

    const headline = titleMatch[1]
      .trim()
      .replace(/&amp;/g, "&")
      .replace(/&lt;/g, "<")
      .replace(/&gt;/g, ">")
      .replace(/&quot;/g, '"')
      .replace(/&#39;/g, "'");

    const publishedAt = parsedDate.toISOString();

    items.push({
      headline,
      url: linkMatch?.[1]?.trim() || null,
      publishedAt,
      eventDate: publishedAt.slice(0, 10),
      pubSource: sourceMatch?.[1]?.trim() || "Google News",
    });
  }

  return items;
}

/**
 * Compute specialist tags using lane defaults + keyword enrichment.
 */
export function computeSpecialistTags(
  headline: string,
  lane: GoogleNewsLane,
): string[] {
  const tags = new Set<string>([...lane.baseTags, laneTag(lane.slug)]);
  const headlineLower = headline.toLowerCase();

  for (const [bucket, keywords] of Object.entries(CROSS_TAG_KEYWORDS)) {
    if (tags.has(bucket)) continue;
    for (const kw of keywords) {
      if (headlineLower.includes(kw)) {
        tags.add(bucket);
        break;
      }
    }
  }

  return Array.from(tags).sort();
}

export function prepareLaneRows(
  lane: GoogleNewsLane,
  rawItems: ParsedGoogleNewsItem[],
  now: Date = new Date(),
): { rows: PreparedRow[]; stats: LanePreparationStats } {
  const seenHashes = new Set<string>();
  const rows: PreparedRow[] = [];
  const stats: LanePreparationStats = {
    attempted: rawItems.length,
    stale: 0,
    invalidDate: 0,
    deduped: 0,
    prepared: 0,
  };

  for (const item of rawItems) {
    if (!item.eventDate || !item.publishedAt || Number.isNaN(Date.parse(item.publishedAt))) {
      stats.invalidDate += 1;
      continue;
    }

    if (!isPublishedAtFresh(item.publishedAt, now)) {
      stats.stale += 1;
      continue;
    }

    const rowHash = hashFields(
      item.headline,
      item.eventDate,
      lane.slug,
      item.pubSource,
    );

    if (seenHashes.has(rowHash)) {
      stats.deduped += 1;
      continue;
    }

    seenHashes.add(rowHash);
    rows.push({
      eventDate: item.eventDate,
      publishedAt: item.publishedAt,
      headline: item.headline,
      url: item.url,
      source: buildLaneSourceValue(lane.slug, item.pubSource),
      specialistTags: computeSpecialistTags(item.headline, lane),
      rowHash,
    });
  }

  stats.prepared = rows.length;
  return { rows, stats };
}

async function fetchRss(query: string): Promise<ParsedGoogleNewsItem[]> {
  const url = `${GOOGLE_NEWS_RSS_BASE}?q=${encodeURIComponent(query)}&hl=en-US&gl=US&ceid=US:en`;
  try {
    const res = await fetch(url, {
      headers: { "User-Agent": USER_AGENT },
      signal: AbortSignal.timeout(15000),
    });
    if (!res.ok) return [];

    const xml = await res.text();
    return parseRssXml(xml);
  } catch {
    return [];
  }
}

export const googleNewsDaily = inngest.createFunction(
  {
    id: "google-news-daily",
    name: "Google News Daily (Segmented Lanes)",
    retries: 2,
    concurrency: [DB_CONCURRENCY],
  },
  { cron: "0 13 * * *" }, // Daily at 13:00 UTC (8 AM CT)
  async ({ step, logger }) => {
    const runId = await step.run("create-ingest-run", async () => {
      return createIngestRun(pool, JOB_NAME);
    });

    try {
      let totalFetched = 0;
      let totalPrepared = 0;
      let totalInserted = 0;
      let totalSkipped = 0;
      let totalStale = 0;
      let totalInvalidDate = 0;

      for (const lane of GOOGLE_NEWS_LANES) {
        const fetchedItems = await step.run(`fetch-${lane.slug}`, async () => {
          const all: ParsedGoogleNewsItem[] = [];
          for (const query of lane.queries) {
            const items = await fetchRss(query);
            all.push(...items);
            await new Promise((resolve) => setTimeout(resolve, 500));
          }

          logger.info(`${lane.slug}: fetched ${all.length} items across ${lane.queries.length} queries`);
          return all;
        });

        totalFetched += fetchedItems.length;

        const { rows, stats } = prepareLaneRows(lane, fetchedItems, new Date());
        totalPrepared += stats.prepared;
        totalStale += stats.stale;
        totalInvalidDate += stats.invalidDate;

        if (rows.length === 0) {
          logger.info(
            `${lane.slug}: prepared 0 rows (stale=${stats.stale}, invalid_date=${stats.invalidDate}, deduped=${stats.deduped})`,
          );
          continue;
        }

        const result = await step.run(`insert-${lane.slug}`, async () => {
          const client = await pool.connect();
          let inserted = 0;
          let skipped = 0;

          try {
            const batchSize = 100;
            for (let i = 0; i < rows.length; i += batchSize) {
              const batch = rows.slice(i, i + batchSize);
              const values: string[] = [];
              const params: (string | string[] | null)[] = [];

              for (let r = 0; r < batch.length; r++) {
                const base = r * 7;
                values.push(
                  `($${base + 1}, $${base + 2}::timestamptz, $${base + 3}, $${base + 4}, $${base + 5}, $${base + 6}::text[], $${base + 7})`,
                );
                params.push(
                  batch[r].eventDate,
                  batch[r].publishedAt,
                  batch[r].headline,
                  batch[r].url,
                  batch[r].source,
                  batch[r].specialistTags,
                  batch[r].rowHash,
                );
              }

              const res = await client.query(
                `INSERT INTO alt.policy_news_event
                 (event_date, published_at, headline, url, source, specialist_tags, row_hash)
                 VALUES ${values.join(",")}
                 ON CONFLICT (row_hash) WHERE row_hash IS NOT NULL DO NOTHING`,
                params,
              );

              inserted += res.rowCount ?? 0;
              skipped += batch.length - (res.rowCount ?? 0);
            }
          } finally {
            client.release();
          }

          return { inserted, skipped };
        });

        totalInserted += result.inserted;
        totalSkipped += result.skipped;

        logger.info(
          `${lane.slug}: prepared=${stats.prepared}, stale=${stats.stale}, invalid_date=${stats.invalidDate}, deduped=${stats.deduped}, inserted=${result.inserted}, skipped=${result.skipped}`,
        );
      }

      await step.run("finalize-ingest-run", async () => {
        await finalizeIngestRun(pool, runId, {
          status: "success",
          rowsAttempted: totalFetched,
          rowsInserted: totalInserted,
          rowsSkipped: totalSkipped + totalStale + totalInvalidDate,
        });
      });

      logger.info(
        `Google News Daily complete: fetched=${totalFetched}, prepared=${totalPrepared}, inserted=${totalInserted}, skipped=${totalSkipped}, stale_rejected=${totalStale}, invalid_date_rejected=${totalInvalidDate}`,
      );

      return {
        status: "success",
        fetched: totalFetched,
        prepared: totalPrepared,
        inserted: totalInserted,
        skipped: totalSkipped,
        staleRejected: totalStale,
        invalidDateRejected: totalInvalidDate,
      };
    } catch (err) {
      await step.run("fail-ingest-run", async () => {
        await failIngestRun(pool, runId, err);
      });
      throw err;
    }
  },
);
