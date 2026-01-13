/**
 * White House Policy Ingestion (TARGETED URLs)
 * 
 * Hits SPECIFIC White House endpoints for trade/tariff policy:
 * 1. Trade Issues Page: https://www.whitehouse.gov/issues/trade/
 * 2. Executive Orders/Presidential Actions: https://www.whitehouse.gov/presidential-actions/
 * 3. Briefing Room RSS: https://www.whitehouse.gov/briefing-room/statements-releases/feed/
 * 
 * Routes to: tariff, trump_effect specialists
 * Table: raw.news_articles_event
 */

import { inngest } from "./client";
import { createHash } from "crypto";

// Database connection via fetch to API
const DATABASE_URL = process.env.DATABASE_URL || process.env.POSTGRES_URL;

interface WhiteHouseItem {
  title: string;
  link: string;
  pubDate?: string;
  description?: string;
  type: "trade" | "executive_order" | "press_release";
}

interface ParsedRSSItem {
  title?: string;
  link?: string;
  pubDate?: string;
  description?: string;
}

async function fetchAndParseRSS(url: string): Promise<ParsedRSSItem[]> {
  const response = await fetch(url, {
    headers: {
      "User-Agent": "Mozilla/5.0 (compatible; ZINC-FUSION/1.0)",
      "Accept": "application/rss+xml, application/xml, text/xml",
    },
  });

  if (!response.ok) {
    throw new Error(`RSS fetch failed: ${response.status}`);
  }

  const text = await response.text();
  const items: ParsedRSSItem[] = [];

  // Simple XML parsing for RSS items
  const itemMatches = text.match(/<item>[\s\S]*?<\/item>/g) || [];
  
  for (const itemXml of itemMatches) {
    const titleMatch = itemXml.match(/<title><!\[CDATA\[(.*?)\]\]><\/title>|<title>(.*?)<\/title>/);
    const linkMatch = itemXml.match(/<link>(.*?)<\/link>/);
    const pubDateMatch = itemXml.match(/<pubDate>(.*?)<\/pubDate>/);
    const descMatch = itemXml.match(/<description><!\[CDATA\[(.*?)\]\]><\/description>|<description>(.*?)<\/description>/s);

    items.push({
      title: titleMatch?.[1] || titleMatch?.[2] || "",
      link: linkMatch?.[1] || "",
      pubDate: pubDateMatch?.[1] || "",
      description: descMatch?.[1] || descMatch?.[2] || "",
    });
  }

  return items;
}

async function scrapePresidentialActions(): Promise<WhiteHouseItem[]> {
  const url = "https://www.whitehouse.gov/presidential-actions/";
  const response = await fetch(url, {
    headers: {
      "User-Agent": "Mozilla/5.0 (compatible; ZINC-FUSION/1.0)",
      "Accept": "text/html",
    },
  });

  if (!response.ok) {
    console.log(`Presidential actions fetch returned ${response.status}`);
    return [];
  }

  const html = await response.text();
  const items: WhiteHouseItem[] = [];

  // Find article links - look for executive order and proclamation patterns
  const articlePattern = /<a[^>]*href="(https:\/\/www\.whitehouse\.gov\/presidential-actions\/[^"]+)"[^>]*>([^<]+)<\/a>/gi;
  let match;
  
  while ((match = articlePattern.exec(html)) !== null) {
    const link = match[1];
    const title = match[2].trim();
    
    if (title && title.length > 10 && !title.includes("Read More")) {
      items.push({
        title,
        link,
        type: "executive_order",
      });
    }
  }

  return items.slice(0, 20); // Latest 20
}

async function scrapeTradePage(): Promise<WhiteHouseItem[]> {
  const url = "https://www.whitehouse.gov/issues/trade/";
  const response = await fetch(url, {
    headers: {
      "User-Agent": "Mozilla/5.0 (compatible; ZINC-FUSION/1.0)",
      "Accept": "text/html",
    },
  });

  if (!response.ok) {
    console.log(`Trade page fetch returned ${response.status}`);
    return [];
  }

  const html = await response.text();
  const items: WhiteHouseItem[] = [];

  // Find article/news links on trade page
  const articlePattern = /<a[^>]*href="(https:\/\/www\.whitehouse\.gov\/[^"]*(?:briefing-room|fact-sheet|statement)[^"]*)"[^>]*>([^<]+)<\/a>/gi;
  let match;

  while ((match = articlePattern.exec(html)) !== null) {
    const link = match[1];
    const title = match[2].trim();
    
    if (title && title.length > 10) {
      items.push({
        title,
        link,
        type: "trade",
      });
    }
  }

  return items.slice(0, 20);
}

function generateRowHash(item: WhiteHouseItem): string {
  const content = `${item.title}|${item.link}`;
  return createHash("sha256").update(content).digest("hex");
}

function classifySpecialist(item: WhiteHouseItem): string[] {
  const text = `${item.title} ${item.description || ""}`.toLowerCase();
  const specialists: string[] = [];

  // Tariff specialist keywords
  if (
    text.includes("tariff") ||
    text.includes("trade") ||
    text.includes("import") ||
    text.includes("export") ||
    text.includes("customs") ||
    text.includes("china") ||
    text.includes("agriculture") ||
    text.includes("soybean") ||
    item.type === "trade"
  ) {
    specialists.push("tariff");
  }

  // Trump effect specialist - all executive orders + policy announcements
  if (
    item.type === "executive_order" ||
    text.includes("executive order") ||
    text.includes("proclamation") ||
    text.includes("memorandum") ||
    text.includes("emergency") ||
    text.includes("national security")
  ) {
    specialists.push("trump_effect");
  }

  // Energy specialist
  if (
    text.includes("energy") ||
    text.includes("oil") ||
    text.includes("petroleum") ||
    text.includes("lng") ||
    text.includes("fuel")
  ) {
    specialists.push("energy");
  }

  // Biofuel specialist
  if (
    text.includes("biofuel") ||
    text.includes("biodiesel") ||
    text.includes("renewable fuel") ||
    text.includes("ethanol") ||
    text.includes("rfs")
  ) {
    specialists.push("biofuel");
  }

  // Default to trump_effect if no other match
  if (specialists.length === 0) {
    specialists.push("trump_effect");
  }

  return specialists;
}

export const whitehouseDaily = inngest.createFunction(
  {
    id: "whitehouse-policy-daily",
    name: "White House Policy Ingestion (Trade + EOs)",
  },
  { cron: "0 8,14,20 * * *" }, // 8am, 2pm, 8pm daily
  async ({ step }) => {
    // Step 1: Fetch RSS feed
    const rssItems = await step.run("fetch-briefing-rss", async () => {
      try {
        const items = await fetchAndParseRSS(
          "https://www.whitehouse.gov/briefing-room/statements-releases/feed/"
        );
        return items.map((item) => ({
          title: item.title || "",
          link: item.link || "",
          pubDate: item.pubDate,
          description: item.description,
          type: "press_release" as const,
        }));
      } catch (error) {
        console.error("RSS fetch error:", error);
        return [];
      }
    });

    // Step 2: Scrape Presidential Actions (Executive Orders)
    const eoItems = await step.run("scrape-presidential-actions", async () => {
      try {
        return await scrapePresidentialActions();
      } catch (error) {
        console.error("Presidential actions scrape error:", error);
        return [];
      }
    });

    // Step 3: Scrape Trade Issues page
    const tradeItems = await step.run("scrape-trade-page", async () => {
      try {
        return await scrapeTradePage();
      } catch (error) {
        console.error("Trade page scrape error:", error);
        return [];
      }
    });

    // Combine all items
    const allItems: WhiteHouseItem[] = [...rssItems, ...eoItems, ...tradeItems];

    // Deduplicate by link
    const seen = new Set<string>();
    const uniqueItems = allItems.filter((item) => {
      if (seen.has(item.link)) return false;
      seen.add(item.link);
      return true;
    });

    // Step 4: Insert into database
    const result = await step.run("insert-articles", async () => {
      if (!DATABASE_URL) {
        throw new Error("DATABASE_URL not configured");
      }

      // Use pg for direct connection
      const { Pool } = await import("pg");
      const pool = new Pool({ connectionString: DATABASE_URL });

      let inserted = 0;
      let skipped = 0;

      try {
        for (const item of uniqueItems) {
          const rowHash = generateRowHash(item);
          const specialists = classifySpecialist(item);
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
              `whitehouse_${item.type}`,
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

      return { inserted, skipped, total: uniqueItems.length };
    });

    return {
      success: true,
      sources: {
        rss: rssItems.length,
        executiveOrders: eoItems.length,
        tradePage: tradeItems.length,
      },
      ...result,
    };
  }
);
