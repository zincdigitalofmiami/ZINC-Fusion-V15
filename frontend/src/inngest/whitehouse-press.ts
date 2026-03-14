/**
 * White House Policy Ingestion (COMPREHENSIVE - ALL TARGETED URLs)
 *
 * Hits 20+ TARGETED White House endpoints organized by category:
 *
 * PRESIDENTIAL ACTIONS:
 * - /presidential-actions/executive-orders/
 * - /presidential-actions/presidential-memoranda/
 * - /presidential-actions/proclamations/
 * - /presidential-actions/nominations-appointments/
 *
 * POLICY ISSUES:
 * - /issues/trade/ (TRADE POLICY - CRITICAL)
 * - /issues/border-immigration/ (ICE, immigration)
 * - /issues/economy/ (economic policy)
 * - /issues/economy/energy/ (energy policy)
 * - /issues/national-security/
 * - /issues/doge/ (DOGE/gov efficiency)
 * - /issues/safe-communities/
 *
 * NEWS/CONTENT:
 * - /briefings-statements/
 * - /fact-sheets/
 * - /remarks/
 * - /news/
 *
 * RSS FEEDS:
 * - /briefing-room/statements-releases/feed/
 *
 * Routes to: tariff, trump_effect, energy, china specialists
 * Table: alt.executive_actions_event
 */

import {
  inngest,
  DB_CONCURRENCY,
  RETRIES,
  HTTP_TIMEOUT_MS,
} from "./client";
import { createHash } from "crypto";
import { classifySpecialists as classifyByKeywords } from "../lib/specialist-classifier";
import dbPool from "@/lib/db";

const DATABASE_URL = process.env.DATABASE_URL || process.env.POSTGRES_URL;

interface WhiteHouseItem {
  title: string;
  link: string;
  pubDate?: string;
  description?: string;
  sourceCategory: string;
}

// =============================================================================
// ALL TARGETED WHITE HOUSE URLS
// =============================================================================

const WHITEHOUSE_SOURCES = {
  // Presidential Actions - CRITICAL for trump_effect
  presidentialActions: {
    executiveOrders:
      "https://www.whitehouse.gov/presidential-actions/executive-orders/",
    memoranda:
      "https://www.whitehouse.gov/presidential-actions/presidential-memoranda/",
    proclamations:
      "https://www.whitehouse.gov/presidential-actions/proclamations/",
    nominations:
      "https://www.whitehouse.gov/presidential-actions/nominations-appointments/",
  },

  // Policy Issues - CRITICAL for specialists
  issues: {
    trade: "https://www.whitehouse.gov/issues/trade/", // tariff specialist
    borderImmigration: "https://www.whitehouse.gov/issues/border-immigration/", // trump_effect / ICE
    economy: "https://www.whitehouse.gov/issues/economy/", // fed specialist
    energy: "https://www.whitehouse.gov/issues/economy/energy/", // energy specialist
    nationalSecurity: "https://www.whitehouse.gov/issues/national-security/", // trump_effect
    doge: "https://www.whitehouse.gov/issues/doge/", // trump_effect
  },

  // News & Statements
  news: {
    briefings: "https://www.whitehouse.gov/briefings-statements/",
    factSheets: "https://www.whitehouse.gov/fact-sheets/",
    remarks: "https://www.whitehouse.gov/remarks/",
    news: "https://www.whitehouse.gov/news/",
    articles: "https://www.whitehouse.gov/articles/",
  },

  // RSS Feeds
  rss: {
    statementsReleases:
      "https://www.whitehouse.gov/briefing-room/statements-releases/feed/",
  },
};

// Specialist routing rules
const SOURCE_TO_SPECIALISTS: Record<string, string[]> = {
  // Presidential Actions
  executiveOrders: [],
  memoranda: [],
  proclamations: [],
  nominations: [],

  // Issues
  trade: ["tariff", "china"],
  borderImmigration: ["trump_effect"],
  economy: ["fed", "trump_effect"],
  energy: ["energy", "biofuel"],
  nationalSecurity: ["trump_effect", "china"],
  doge: ["trump_effect"],

  // News
  briefings: [],
  factSheets: [],
  remarks: [],
  news: [],
  articles: [],

  // RSS
  statementsReleases: [],
};

const EXECUTE_ACTION_TAG = "execute_action";

type WhiteHouseDocumentType =
  | "executive_order"
  | "presidential_memorandum"
  | "proclamation"
  | "nomination_appointment"
  | "briefing_statement"
  | "fact_sheet"
  | "remarks"
  | "news"
  | "issue_page"
  | "other";

function inferDocumentType(item: WhiteHouseItem): WhiteHouseDocumentType {
  const link = item.link.toLowerCase();
  const title = item.title.toLowerCase();

  if (
    item.sourceCategory === "executiveOrders" ||
    link.includes("/presidential-actions/executive-orders/")
  ) {
    return "executive_order";
  }
  if (
    item.sourceCategory === "memoranda" ||
    link.includes("/presidential-actions/presidential-memoranda/")
  ) {
    return "presidential_memorandum";
  }
  if (
    item.sourceCategory === "proclamations" ||
    link.includes("/presidential-actions/proclamations/")
  ) {
    return "proclamation";
  }
  if (
    item.sourceCategory === "nominations" ||
    link.includes("/presidential-actions/nominations-appointments/")
  ) {
    return "nomination_appointment";
  }

  if (
    item.sourceCategory === "factSheets" ||
    link.includes("/fact-sheets") ||
    link.includes("/fact-sheet")
  ) {
    return "fact_sheet";
  }
  if (
    item.sourceCategory === "briefings" ||
    link.includes("/briefings-statements") ||
    link.includes("/briefing-room")
  ) {
    return "briefing_statement";
  }
  if (item.sourceCategory === "remarks" || link.includes("/remarks/")) {
    return "remarks";
  }
  if (item.sourceCategory === "news" || link.includes("/news/")) {
    return "news";
  }
  if (link.includes("/issues/")) {
    return "issue_page";
  }

  // Fallback heuristics
  if (
    title.startsWith("executive order") ||
    title.includes(" executive order ")
  ) {
    return "executive_order";
  }
  if (title.startsWith("proclamation") || title.includes(" proclamation")) {
    return "proclamation";
  }
  if (
    title.includes("presidential memorandum") ||
    title.includes("presidential action")
  ) {
    return "presidential_memorandum";
  }

  return "other";
}

function isExecuteAction(
  item: WhiteHouseItem,
  docType: WhiteHouseDocumentType,
): boolean {
  // Strict default: only true presidential action documents qualify
  if (
    docType === "executive_order" ||
    docType === "presidential_memorandum" ||
    docType === "proclamation"
  ) {
    return true;
  }

  // Allow a narrow set of major actions even if not in presidential-actions pages
  // (e.g., major war actions, sanctions, national emergency)
  const text = `${item.title} ${item.description || ""}`.toLowerCase();
  const majorActionSignals = [
    "national emergency",
    "emergency declaration",
    "authorization for use of military force",
    "airstrike",
    "military strike",
    "deployment",
    "sanctions",
    "executive action",
    "presidential determination",
    "presidential directive",
    "trade agreement signed",
    "trade deal signed",
    "agreement signed",
  ];

  return majorActionSignals.some((s) => text.includes(s));
}

async function fetchAndParseRSS(url: string): Promise<WhiteHouseItem[]> {
  let response: Response;
  try {
    response = await fetch(url, {
      headers: {
        "User-Agent": "Mozilla/5.0 (compatible; ZINC-FUSION/1.0)",
        Accept: "application/rss+xml, application/xml, text/xml",
      },
      signal: AbortSignal.timeout(HTTP_TIMEOUT_MS.LONG),
    });
  } catch (error) {
    if (error instanceof Error && error.name === "AbortError") {
      console.log(`RSS fetch timeout after ${HTTP_TIMEOUT_MS.LONG}ms: ${url}`);
      return [];
    }
    console.log(`RSS fetch error for ${url}:`, error);
    return [];
  }

  if (!response.ok) {
    console.log(`RSS fetch failed: ${response.status} for ${url}`);
    return [];
  }

  const text = await response.text();
  const items: WhiteHouseItem[] = [];
  const itemMatches = text.match(/<item>[\s\S]*?<\/item>/g) || [];

  for (const itemXml of itemMatches.slice(0, 25)) {
    const titleMatch = itemXml.match(
      /<title><!\[CDATA\[(.*?)\]\]><\/title>|<title>(.*?)<\/title>/,
    );
    const linkMatch = itemXml.match(/<link>(.*?)<\/link>/);
    const pubDateMatch = itemXml.match(/<pubDate>(.*?)<\/pubDate>/);
    const descMatch = itemXml.match(
      /<description><!\[CDATA\[([\s\S]*?)\]\]><\/description>|<description>([\s\S]*?)<\/description>/,
    );

    if (titleMatch && linkMatch) {
      items.push({
        title: (titleMatch[1] || titleMatch[2] || "").trim(),
        link: linkMatch[1] || "",
        pubDate: pubDateMatch?.[1] || "",
        description: descMatch?.[1] || descMatch?.[2] || "",
        sourceCategory: "statementsReleases",
      });
    }
  }

  return items;
}

async function scrapePage(
  url: string,
  sourceKey: string,
): Promise<WhiteHouseItem[]> {
  try {
    const response = await fetch(url, {
      headers: {
        "User-Agent":
          "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        Accept: "text/html,application/xhtml+xml",
      },
      signal: AbortSignal.timeout(HTTP_TIMEOUT_MS.LONG),
    });

    if (!response.ok) {
      console.log(`Page fetch returned ${response.status} for ${url}`);
      return [];
    }

    const html = await response.text();
    const items: WhiteHouseItem[] = [];

    // Pattern 1: Article links with specific paths
    const patterns = [
      // Presidential actions with dates
      /<a[^>]*href="(https:\/\/www\.whitehouse\.gov\/presidential-actions\/\d{4}\/\d{2}\/[^"]+)"[^>]*>([^<]+)<\/a>/gi,
      // Briefings/statements
      /<a[^>]*href="(https:\/\/www\.whitehouse\.gov\/briefing-room\/[^"]+)"[^>]*>([^<]+)<\/a>/gi,
      // Fact sheets
      /<a[^>]*href="(https:\/\/www\.whitehouse\.gov\/fact-sheet[^"]*)"[^>]*>([^<]+)<\/a>/gi,
      // Remarks
      /<a[^>]*href="(https:\/\/www\.whitehouse\.gov\/remarks\/[^"]+)"[^>]*>([^<]+)<\/a>/gi,
      // Articles
      /<a[^>]*href="(https:\/\/www\.whitehouse\.gov\/articles\/[^"]+)"[^>]*>([^<]+)<\/a>/gi,
      // Issues subpages
      /<a[^>]*href="(https:\/\/www\.whitehouse\.gov\/issues\/[^"]+\/[^"]+)"[^>]*>([^<]+)<\/a>/gi,
      // News
      /<a[^>]*href="(https:\/\/www\.whitehouse\.gov\/news\/[^"]+)"[^>]*>([^<]+)<\/a>/gi,
      // Wire
      /<a[^>]*href="(https:\/\/www\.whitehouse\.gov\/wire\/[^"]+)"[^>]*>([^<]+)<\/a>/gi,
      // Briefings-statements with dates
      /<a[^>]*href="(https:\/\/www\.whitehouse\.gov\/briefings-statements\/[^"]+)"[^>]*>([^<]+)<\/a>/gi,
    ];

    const seen = new Set<string>();

    for (const pattern of patterns) {
      let match;
      while ((match = pattern.exec(html)) !== null) {
        const link = match[1];
        const title = match[2].trim();

        // Skip if already seen, too short, or navigation text
        if (
          seen.has(link) ||
          title.length < 10 ||
          title.includes("Read More") ||
          title.includes("View All") ||
          title === "Read"
        ) {
          continue;
        }

        seen.add(link);
        items.push({
          title,
          link,
          sourceCategory: sourceKey,
        });
      }
    }

    return items.slice(0, 30); // Max 30 per page
  } catch (error) {
    console.error(`Error scraping ${url}:`, error);
    return [];
  }
}

function generateRowHash(item: WhiteHouseItem): string {
  const content = `${item.title}|${item.link}`;
  return createHash("sha256").update(content).digest("hex");
}

function classifySpecialists(item: WhiteHouseItem): string[] {
  // Start with source-based classification (contextual hints)
  const baseSpecialists = SOURCE_TO_SPECIALISTS[item.sourceCategory] || [];
  const specialists = new Set<string>(baseSpecialists);

  // Use shared keyword classifier for content-based tagging
  const text = `${item.title} ${item.description || ""}`;
  const keywordTags = classifyByKeywords(text);

  // Merge keyword-detected tags (exclude "general" if we have source-based tags)
  for (const tag of keywordTags) {
    if (tag !== "general") {
      specialists.add(tag);
    }
  }

  const docType = inferDocumentType(item);
  if (
    docType === "executive_order" ||
    docType === "presidential_memorandum" ||
    docType === "proclamation"
  ) {
    specialists.add("trump_effect");
  }

  if (isExecuteAction(item, docType)) {
    specialists.add(EXECUTE_ACTION_TAG);
    specialists.add("trump_effect");
  }

  return Array.from(specialists);
}

export const whitehouseDaily = inngest.createFunction(
  {
    id: "whitehouse-comprehensive-daily",
    name: "White House Comprehensive (20+ URLs)",
    retries: RETRIES.CRON_INGEST,
    concurrency: [DB_CONCURRENCY],
  },
  { cron: "TZ=America/New_York 0 7 * * *" },
  async ({ step }) => {
    const allItems: WhiteHouseItem[] = [];
    const sourceCounts: Record<string, number> = {};

    // Step 1: Fetch RSS
    const rssItems = await step.run("fetch-rss-feed", async () => {
      const items = await fetchAndParseRSS(
        WHITEHOUSE_SOURCES.rss.statementsReleases,
      );
      return items;
    });
    allItems.push(...rssItems);
    sourceCounts["rss_statementsReleases"] = rssItems.length;

    // Step 2: Scrape Presidential Actions (most important)
    const presActionsItems = await step.run(
      "scrape-presidential-actions",
      async () => {
        const items: WhiteHouseItem[] = [];
        for (const [key, url] of Object.entries(
          WHITEHOUSE_SOURCES.presidentialActions,
        )) {
          const pageItems = await scrapePage(url, key);
          items.push(...pageItems);
          // Small delay between requests
          await new Promise((r) => setTimeout(r, 500));
        }
        return items;
      },
    );
    allItems.push(...presActionsItems);
    sourceCounts["presidentialActions"] = presActionsItems.length;

    // Step 3: Scrape Policy Issues (trade, immigration, energy, etc.)
    const issuesItems = await step.run("scrape-policy-issues", async () => {
      const items: WhiteHouseItem[] = [];
      for (const [key, url] of Object.entries(WHITEHOUSE_SOURCES.issues)) {
        const pageItems = await scrapePage(url, key);
        items.push(...pageItems);
        await new Promise((r) => setTimeout(r, 500));
      }
      return items;
    });
    allItems.push(...issuesItems);
    sourceCounts["policyIssues"] = issuesItems.length;

    // Step 4: Scrape News sections
    const newsItems = await step.run("scrape-news-sections", async () => {
      const items: WhiteHouseItem[] = [];
      for (const [key, url] of Object.entries(WHITEHOUSE_SOURCES.news)) {
        const pageItems = await scrapePage(url, key);
        items.push(...pageItems);
        await new Promise((r) => setTimeout(r, 500));
      }
      return items;
    });
    allItems.push(...newsItems);
    sourceCounts["news"] = newsItems.length;

    // Deduplicate
    const seen = new Set<string>();
    const uniqueItems = allItems.filter((item) => {
      if (seen.has(item.link)) return false;
      seen.add(item.link);
      return true;
    });

    // Step 5: Insert into database
    const result = await step.run("insert-articles", async () => {
      if (!DATABASE_URL) {
        throw new Error("DATABASE_URL not configured");
      }

      const pool = dbPool;

      let inserted = 0;
      let skipped = 0;

      for (const item of uniqueItems) {
        const rowHash = generateRowHash(item);
        const specialists = classifySpecialists(item);
        const publishedAt = item.pubDate ? new Date(item.pubDate) : new Date();

        // Hard gate: do not insert items with no meaningful tags
        // (prevents irrelevant content from polluting executive actions feed)
        if (specialists.length === 0) {
          skipped++;
          continue;
        }

        const docType = inferDocumentType(item);

        // Additional gate: only persist to executive actions table if it is an execute action
        // or it contains at least one recognized specialist tag (not just generic news).
        const hasSpecialistSignal = specialists.some(
          (t) => t !== EXECUTE_ACTION_TAG,
        );
        if (!specialists.includes(EXECUTE_ACTION_TAG) && !hasSpecialistSignal) {
          skipped++;
          continue;
        }

        const checkResult = await pool.query(
          `SELECT 1 FROM alt.executive_actions_event WHERE row_hash = $1`,
          [rowHash],
        );

        if (checkResult.rows.length > 0) {
          skipped++;
          continue;
        }

        await pool.query(
          `INSERT INTO alt.executive_actions_event
           (source, headline, url, published_at, event_date, content, specialist_tags, row_hash, document_type)
           VALUES ($1, $2, $3, $4, $5::date, $6, $7, $8, $9)`,
          [
            `whitehouse_${item.sourceCategory}`,
            item.title,
            item.link,
            publishedAt,
            publishedAt,
            item.description || null,
            specialists,
            rowHash,
            docType,
          ],
        );
        inserted++;
      }

      return { inserted, skipped };
    });

    return {
      success: true,
      totalFetched: allItems.length,
      uniqueItems: uniqueItems.length,
      sourceCounts,
      ...result,
    };
  },
);
