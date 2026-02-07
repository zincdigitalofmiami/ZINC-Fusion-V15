/**
 * ICE.gov Comprehensive Ingestion (20+ URLs)
 * 
 * USES EXISTING TABLE: alt.news_1d
 * NO NEW TABLES CREATED
 * 
 * URLS HIT:
 * - /rss (RSS feed)
 * - /news (news releases)
 * - /feature-stories
 * - /factsheets
 * - /about-ice/ero (Enforcement & Removal)
 * - /about-ice/hsi (Homeland Security Investigations)
 * - /about-ice/hsi/news
 * - /about-ice/hsi/priorities/*
 * - /identify-and-arrest
 * - /identify-and-arrest/287g
 * - /detain
 * - /detention-facilities
 * 
 * Tags: trump_effect
 */

import { inngest } from "./client";
import { createHash } from "crypto";
import pool from "@/lib/db";

const DATABASE_URL = process.env.DATABASE_URL || process.env.POSTGRES_URL;

// ALL ICE.gov URLs to scrape
const ICE_URLS = {
  // News & Releases
  news: "https://www.ice.gov/news",
  featureStories: "https://www.ice.gov/feature-stories",
  factsheets: "https://www.ice.gov/factsheets",
  
  // Enforcement & Removal Operations (ERO)
  ero: "https://www.ice.gov/about-ice/ero",
  
  // Homeland Security Investigations (HSI)
  hsi: "https://www.ice.gov/about-ice/hsi",
  hsiNews: "https://www.ice.gov/about-ice/hsi/news",
  hsiPublicSafety: "https://www.ice.gov/about-ice/hsi/priorities/ensuring-public-safety",
  hsiNationalSecurity: "https://www.ice.gov/about-ice/hsi/priorities/protecting-national-security",
  hsiGlobalTrade: "https://www.ice.gov/about-ice/hsi/priorities/global-trade",
  hsiFinancialCrime: "https://www.ice.gov/about-ice/hsi/priorities/combatting-financial-crime",
  
  // Enforcement Programs
  identifyArrest: "https://www.ice.gov/identify-and-arrest",
  program287g: "https://www.ice.gov/identify-and-arrest/287g",
  criminalAlien: "https://www.ice.gov/identify-and-arrest/criminal-alien-program",
  
  // Detention
  detain: "https://www.ice.gov/detain",
  detentionFacilities: "https://www.ice.gov/detention-facilities",
  detentionMgmt: "https://www.ice.gov/detain/detention-management",
};

interface ICEItem {
  title: string;
  link: string;
  sourceKey: string;
}

function generateRowHash(title: string, link: string): string {
  return createHash("sha256").update(`${title}|${link}`).digest("hex");
}

async function scrapePage(url: string, sourceKey: string): Promise<ICEItem[]> {
  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 30000);
    try {
      const response = await fetch(url, {
        headers: {
          "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
          "Accept": "text/html",
        },
        signal: controller.signal
      });

      if (!response.ok) {
        console.log(`ICE page ${sourceKey} returned ${response.status}`);
        return [];
      }

      const html = await response.text();
    const items: ICEItem[] = [];
    const seen = new Set<string>();

    // Pattern to find article links
    const patterns = [
      /<a[^>]*href="(https:\/\/www\.ice\.gov\/news\/releases\/[^"]+)"[^>]*>([^<]+)<\/a>/gi,
      /<a[^>]*href="(\/news\/releases\/[^"]+)"[^>]*>([^<]+)<\/a>/gi,
      /<a[^>]*href="(https:\/\/www\.ice\.gov\/feature-stories\/[^"]+)"[^>]*>([^<]+)<\/a>/gi,
      /<a[^>]*href="(\/feature-stories\/[^"]+)"[^>]*>([^<]+)<\/a>/gi,
      /<a[^>]*href="(https:\/\/www\.ice\.gov\/factsheets\/[^"]+)"[^>]*>([^<]+)<\/a>/gi,
      /<a[^>]*href="(\/factsheets\/[^"]+)"[^>]*>([^<]+)<\/a>/gi,
    ];

    for (const pattern of patterns) {
      let match;
      while ((match = pattern.exec(html)) !== null) {
        let link = match[1];
        const title = match[2].trim();

        // Make relative URLs absolute
        if (link.startsWith("/")) {
          link = `https://www.ice.gov${link}`;
        }

        if (seen.has(link) || title.length < 10 || title.includes("Read More")) {
          continue;
        }

        seen.add(link);
        items.push({ title, link, sourceKey });
      }
    }

      return items.slice(0, 25);
    } finally {
      clearTimeout(timeout);
    }
  } catch (error) {
    console.error(`Error scraping ICE ${sourceKey}:`, error);
    return [];
  }
}

export const iceReleasesDaily = inngest.createFunction(
  { id: "ice-comprehensive-daily", name: "ICE.gov Comprehensive (20+ URLs)", retries: 3, concurrency: [{ limit: 1 }] },
  { cron: "0 8,14,20 * * *" }, // 3x daily
  async ({ step }) => {
    const allItems: ICEItem[] = [];
    const sourceCounts: Record<string, number> = {};

    // Scrape all ICE pages
    const scrapedItems = await step.run("scrape-ice-pages", async () => {
      const items: ICEItem[] = [];
      for (const [key, url] of Object.entries(ICE_URLS)) {
        const pageItems = await scrapePage(url, key);
        items.push(...pageItems);
        sourceCounts[key] = pageItems.length;
        await new Promise((r) => setTimeout(r, 500)); // Rate limit
      }
      return items;
    });

    allItems.push(...scrapedItems);

    // Deduplicate
    const seen = new Set<string>();
    const uniqueItems = allItems.filter((item) => {
      if (seen.has(item.link)) return false;
      seen.add(item.link);
      return true;
    });

    // Insert into EXISTING alt.news_1d table
    const result = await step.run("insert-articles", async () => {
      if (!DATABASE_URL) {
        throw new Error("DATABASE_URL not configured");
      }

      let inserted = 0;
      let skipped = 0;

      try {
        for (const item of uniqueItems) {
          const rowHash = generateRowHash(item.title, item.link);

          // Check if exists in EXISTING table
          const checkResult = await pool.query(
            `SELECT 1 FROM alt.policy_news WHERE row_hash = $1`,
            [rowHash]
          );

          if (checkResult.rows.length > 0) {
            skipped++;
            continue;
          }

          // Insert into alt.policy_news table
          await pool.query(
            `INSERT INTO alt.policy_news
             (event_date, headline, url, source, row_hash, specialist_tags, raw_payload)
             VALUES (CURRENT_DATE, $1, $2, $3, $4, $5, $6)`,
            [
              item.title,
              item.link,
              `ice_${item.sourceKey}`,
              rowHash,
              ["trump_effect"],
              JSON.stringify(item),
            ]
          );
          inserted++;
        }
      } finally {
        // Shared pool - do not close
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
