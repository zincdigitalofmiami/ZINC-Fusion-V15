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
 * Table: raw.news_articles_event
 */

import { inngest } from "./client";
import { createHash } from "crypto";

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
    executiveOrders: "https://www.whitehouse.gov/presidential-actions/executive-orders/",
    memoranda: "https://www.whitehouse.gov/presidential-actions/presidential-memoranda/",
    proclamations: "https://www.whitehouse.gov/presidential-actions/proclamations/",
    nominations: "https://www.whitehouse.gov/presidential-actions/nominations-appointments/",
  },
  
  // Policy Issues - CRITICAL for specialists
  issues: {
    trade: "https://www.whitehouse.gov/issues/trade/", // tariff specialist
    borderImmigration: "https://www.whitehouse.gov/issues/border-immigration/", // trump_effect / ICE
    economy: "https://www.whitehouse.gov/issues/economy/", // fed specialist
    energy: "https://www.whitehouse.gov/issues/economy/energy/", // energy specialist
    nationalSecurity: "https://www.whitehouse.gov/issues/national-security/", // trump_effect
    doge: "https://www.whitehouse.gov/issues/doge/", // trump_effect
    safeCommunities: "https://www.whitehouse.gov/issues/safe-communities/",
    techInnovation: "https://www.whitehouse.gov/issues/tech-innovation/",
    maha: "https://www.whitehouse.gov/issues/maha/", // health policy
    socialCauses: "https://www.whitehouse.gov/issues/social-causes/",
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
    statementsReleases: "https://www.whitehouse.gov/briefing-room/statements-releases/feed/",
  },
};

// Specialist routing rules
const SOURCE_TO_SPECIALISTS: Record<string, string[]> = {
  // Presidential Actions
  executiveOrders: ["trump_effect", "tariff"],
  memoranda: ["trump_effect"],
  proclamations: ["trump_effect"],
  nominations: ["trump_effect"],
  
  // Issues
  trade: ["tariff", "china"],
  borderImmigration: ["trump_effect"],
  economy: ["fed", "trump_effect"],
  energy: ["energy", "biofuel"],
  nationalSecurity: ["trump_effect", "china"],
  doge: ["trump_effect"],
  safeCommunities: ["trump_effect"],
  techInnovation: ["trump_effect"],
  maha: ["trump_effect"],
  socialCauses: ["trump_effect"],
  
  // News
  briefings: ["trump_effect", "tariff"],
  factSheets: ["trump_effect", "tariff"],
  remarks: ["trump_effect"],
  news: ["trump_effect"],
  articles: ["trump_effect"],
  
  // RSS
  statementsReleases: ["trump_effect", "tariff"],
};

async function fetchAndParseRSS(url: string): Promise<WhiteHouseItem[]> {
  const response = await fetch(url, {
    headers: {
      "User-Agent": "Mozilla/5.0 (compatible; ZINC-FUSION/1.0)",
      "Accept": "application/rss+xml, application/xml, text/xml",
    },
  });

  if (!response.ok) {
    console.log(`RSS fetch failed: ${response.status} for ${url}`);
    return [];
  }

  const text = await response.text();
  const items: WhiteHouseItem[] = [];
  const itemMatches = text.match(/<item>[\s\S]*?<\/item>/g) || [];
  
  for (const itemXml of itemMatches.slice(0, 25)) {
    const titleMatch = itemXml.match(/<title><!\[CDATA\[(.*?)\]\]><\/title>|<title>(.*?)<\/title>/);
    const linkMatch = itemXml.match(/<link>(.*?)<\/link>/);
    const pubDateMatch = itemXml.match(/<pubDate>(.*?)<\/pubDate>/);
    const descMatch = itemXml.match(/<description><!\[CDATA\[([\s\S]*?)\]\]><\/description>|<description>([\s\S]*?)<\/description>/);

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

async function scrapePage(url: string, sourceKey: string): Promise<WhiteHouseItem[]> {
  try {
    const response = await fetch(url, {
      headers: {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml",
      },
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
  // Start with source-based classification
  const baseSpecialists = SOURCE_TO_SPECIALISTS[item.sourceCategory] || ["trump_effect"];
  const specialists = new Set<string>(baseSpecialists);
  
  const text = `${item.title} ${item.description || ""}`.toLowerCase();
  
  // Keyword-based additions
  if (text.includes("tariff") || text.includes("trade") || text.includes("import") || text.includes("export")) {
    specialists.add("tariff");
  }
  if (text.includes("china") || text.includes("chinese") || text.includes("beijing")) {
    specialists.add("china");
  }
  if (text.includes("oil") || text.includes("energy") || text.includes("petroleum") || text.includes("lng")) {
    specialists.add("energy");
  }
  if (text.includes("biofuel") || text.includes("biodiesel") || text.includes("renewable fuel") || text.includes("ethanol")) {
    specialists.add("biofuel");
  }
  if (text.includes("soybean") || text.includes("agriculture") || text.includes("farm") || text.includes("crop")) {
    specialists.add("crush");
  }
  if (text.includes("brazil") || text.includes("argentina")) {
    specialists.add("crush");
    specialists.add("fx");
  }
  if (text.includes("currency") || text.includes("dollar") || text.includes("exchange rate")) {
    specialists.add("fx");
  }
  if (text.includes("fed") || text.includes("interest rate") || text.includes("inflation") || text.includes("monetary")) {
    specialists.add("fed");
  }
  if (text.includes("ice") || text.includes("immigration") || text.includes("border") || text.includes("deportation")) {
    specialists.add("trump_effect");
  }
  if (text.includes("lawsuit") || text.includes("court") || text.includes("legal") || text.includes("judge")) {
    specialists.add("trump_effect");
  }
  
  return Array.from(specialists);
}

export const whitehouseDaily = inngest.createFunction(
  {
    id: "whitehouse-comprehensive-daily",
    name: "White House Comprehensive (20+ URLs)",
  },
  { cron: "0 7,11,15,19 * * *" }, // 4x daily
  async ({ step }) => {
    const allItems: WhiteHouseItem[] = [];
    const sourceCounts: Record<string, number> = {};

    // Step 1: Fetch RSS
    const rssItems = await step.run("fetch-rss-feed", async () => {
      const items = await fetchAndParseRSS(WHITEHOUSE_SOURCES.rss.statementsReleases);
      return items;
    });
    allItems.push(...rssItems);
    sourceCounts["rss_statementsReleases"] = rssItems.length;

    // Step 2: Scrape Presidential Actions (most important)
    const presActionsItems = await step.run("scrape-presidential-actions", async () => {
      const items: WhiteHouseItem[] = [];
      for (const [key, url] of Object.entries(WHITEHOUSE_SOURCES.presidentialActions)) {
        const pageItems = await scrapePage(url, key);
        items.push(...pageItems);
        // Small delay between requests
        await new Promise((r) => setTimeout(r, 500));
      }
      return items;
    });
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

      const { Pool } = await import("pg");
      const pool = new Pool({ connectionString: DATABASE_URL });

      let inserted = 0;
      let skipped = 0;

      try {
        for (const item of uniqueItems) {
          const rowHash = generateRowHash(item);
          const specialists = classifySpecialists(item);
          const publishedAt = item.pubDate ? new Date(item.pubDate) : new Date();

          // Check if exists
          const checkResult = await pool.query(
            `SELECT 1 FROM raw.news_articles_event WHERE row_hash = $1`,
            [rowHash]
          );

          if (checkResult.rows.length > 0) {
            skipped++;
            continue;
          }

          // Insert
          await pool.query(
            `INSERT INTO raw.news_articles_event 
             (source_id, title, url, published_at, content_snippet, specialist_tags, row_hash, ingested_at)
             VALUES ($1, $2, $3, $4, $5, $6, $7, NOW())`,
            [
              `whitehouse_${item.sourceCategory}`,
              item.title,
              item.link,
              publishedAt,
              item.description || null,
              specialists,
              rowHash,
            ]
          );
          inserted++;
        }
      } finally {
        await pool.end();
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
  }
);
