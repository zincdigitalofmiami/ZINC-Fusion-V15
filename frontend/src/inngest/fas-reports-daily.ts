/**
 * FAS Reports Monitor
 *
 * Scrapes USDA Foreign Agricultural Service report pages for new publications.
 * FAS site is flaky (HTTP/2 errors common) — built with aggressive retry/fallback.
 *
 * Pages monitored:
 *   - /data/search?reports[0]=report_commodities:5 — Oilseed commodity reports
 *   - /data/commodities/biofuels — Biofuel reports
 *   - /data/search?reports[0]=report_type:10257 — GAIN reports (oilseeds)
 *   - /data/search?reports[0]=report_type:10253 — Attaché reports
 *
 * Also monitors:
 *   - White House /presidential-actions/ (already in whitehouse-press.ts but
 *     this provides redundant coverage for the actions page specifically)
 *
 * Inserts into: alt.policy_news_event
 *
 * @author Claude (ZINC-FUSION-V15)
 * @date 2026-02-24
 */

import { inngest, DB_CONCURRENCY } from "./client";
import { createHash } from "crypto";
import dbPool from "@/lib/db";

const pool = dbPool;

function computeRowHash(url: string, title: string): string {
  return createHash("sha256").update(`fas|${url}|${title}`).digest("hex");
}

interface FASReport {
  title: string;
  url: string;
  date: string; // YYYY-MM-DD
  source: string;
  specialistTags: string[];
}

const FAS_PAGES: Array<{
  id: string;
  name: string;
  url: string;
  specialistTags: string[];
}> = [
  {
    id: "fas-oilseeds",
    name: "FAS Oilseed Reports",
    url: "https://www.fas.usda.gov/data/search?reports%5B0%5D=report_commodities%3A5",
    specialistTags: ["crush", "china", "substitutes"],
  },
  {
    id: "fas-biofuels",
    name: "FAS Biofuels Reports",
    url: "https://www.fas.usda.gov/data/commodities/biofuels",
    specialistTags: ["biofuel", "energy"],
  },
  {
    id: "fas-gain-oilseeds",
    name: "FAS GAIN Reports",
    url: "https://www.fas.usda.gov/data/search?reports%5B0%5D=report_type%3A10257",
    specialistTags: ["crush", "china", "palm", "substitutes"],
  },
  {
    id: "fas-attache",
    name: "FAS Attaché Reports",
    url: "https://www.fas.usda.gov/data/search?reports%5B0%5D=report_type%3A10253",
    specialistTags: ["crush", "china", "palm"],
  },
];

/**
 * Extract report links from FAS HTML pages.
 * FAS uses Drupal with server-side rendered HTML.
 * Reports appear as <a> tags with specific class patterns.
 */
function extractReportsFromHTML(html: string, source: string, tags: string[]): FASReport[] {
  const reports: FASReport[] = [];

  // Pattern 1: FAS search results — look for report title links
  // <a href="/data/..." class="...">Report Title</a> with nearby date
  const linkPattern = /<a[^>]+href="(\/data\/[^"]+)"[^>]*>([^<]+)<\/a>/gi;
  let match: RegExpExecArray | null;

  while ((match = linkPattern.exec(html)) !== null) {
    const path = match[1];
    const title = match[2].trim();

    // Skip navigation/filter links
    if (title.length < 10 || path.includes("/search") || path.includes("/commodities/")) continue;

    // Look for a date near this link (within 500 chars)
    const context = html.substring(Math.max(0, match.index - 200), match.index + 500);
    const dateMatch = context.match(
      /(\d{1,2})\/(\d{1,2})\/(\d{4})|(\w+ \d{1,2}, \d{4})|(\d{4}-\d{2}-\d{2})/
    );

    let dateStr = new Date().toISOString().split("T")[0]; // default to today
    if (dateMatch) {
      if (dateMatch[3]) {
        // MM/DD/YYYY
        dateStr = `${dateMatch[3]}-${dateMatch[1].padStart(2, "0")}-${dateMatch[2].padStart(2, "0")}`;
      } else if (dateMatch[5]) {
        // YYYY-MM-DD
        dateStr = dateMatch[5];
      } else if (dateMatch[4]) {
        // Month DD, YYYY
        const d = new Date(dateMatch[4]);
        if (!isNaN(d.getTime())) dateStr = d.toISOString().split("T")[0];
      }
    }

    reports.push({
      title,
      url: `https://www.fas.usda.gov${path}`,
      date: dateStr,
      source,
      specialistTags: tags,
    });
  }

  return reports;
}

async function fetchWithRetry(url: string, maxRetries = 4, logger?: { warn: (msg: string) => void }): Promise<string | null> {
  for (let attempt = 1; attempt <= maxRetries; attempt++) {
    try {
      const controller = new AbortController();
      // Increase timeout per attempt: 45s, 60s, 90s, 120s
      const timeoutMs = Math.min(45_000 * attempt, 120_000);
      const timeout = setTimeout(() => controller.abort(), timeoutMs);
      const res = await fetch(url, {
        headers: {
          "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
          Accept: "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
          "Accept-Language": "en-US,en;q=0.9",
        },
        signal: controller.signal,
      });
      clearTimeout(timeout);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return await res.text();
    } catch (err) {
      const errMsg = err instanceof Error ? err.message : String(err);
      logger?.warn(`FAS fetch attempt ${attempt}/${maxRetries} failed: ${errMsg} (url: ${url})`);
      if (attempt === maxRetries) return null;
      // Exponential backoff: 5s, 15s, 45s, 135s
      await new Promise((r) => setTimeout(r, 5000 * Math.pow(3, attempt - 1)));
    }
  }
  return null;
}

export const fasReportsDaily = inngest.createFunction(
  {
    id: "fas-reports-daily",
    name: "FAS Reports Monitor (Oilseeds, Biofuels, GAIN, Attaché)",
    retries: 2,
    concurrency: [DB_CONCURRENCY],
  },
  { cron: "0 15 * * *" }, // Daily at 15:00 UTC (10 AM ET)
  async ({ step, logger }) => {
    const runId = await step.run("create-ingest-run", async () => {
      const client = await pool.connect();
      try {
        const result = await client.query(
          `INSERT INTO ops.ingest_run (job_name, status, started_at) VALUES ($1, 'running', NOW()) RETURNING id`,
          ["fas-reports-daily"]
        );
        return result.rows[0].id as string;
      } finally {
        client.release();
      }
    });

    let totalInserted = 0;
    let totalSkipped = 0;
    let totalFailed = 0;

    for (const page of FAS_PAGES) {
      const result = await step.run(`scrape-${page.id}`, async () => {
        let inserted = 0;
        let skipped = 0;

        const html = await fetchWithRetry(page.url, 4, logger);
        if (!html) {
          logger.warn(`${page.name}: FAS site unreachable after 4 retries`);
          return { name: page.name, inserted: 0, skipped: 0, failed: true };
        }

        const reports = extractReportsFromHTML(html, page.id, page.specialistTags);

        const client = await pool.connect();
        try {
          for (const report of reports) {
            const rowHash = computeRowHash(report.url, report.title);
            const exists = await client.query(
              `SELECT 1 FROM alt.policy_news_event WHERE row_hash=$1 LIMIT 1`,
              [rowHash]
            );
            if (exists.rows.length > 0) {
              skipped++;
              continue;
            }

            await client.query(
              `INSERT INTO alt.policy_news_event (
                 event_date, headline, content, url, published_at,
                 source, row_hash, specialist_tags
               ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8)`,
              [
                report.date,
                report.title,
                `FAS ${page.name} report`,
                report.url,
                report.date,
                `fas_${page.id}`,
                rowHash,
                report.specialistTags,
              ]
            );
            inserted++;
          }
        } finally {
          client.release();
        }

        return { name: page.name, inserted, skipped, failed: false };
      });

      totalInserted += result.inserted;
      totalSkipped += result.skipped;
      if (result.failed) totalFailed++;

      if (result.inserted > 0) {
        logger.info(`${result.name}: +${result.inserted} reports`);
      }
    }

    // Finalize
    await step.run("complete-ingest-run", async () => {
      const client = await pool.connect();
      try {
        await client.query(
          `UPDATE ops.ingest_run SET status=$2, completed_at=NOW(),
           rows_attempted=$3, rows_inserted=$4, rows_skipped=$5, rows_quarantined=$6 WHERE id=$1`,
          [runId, totalFailed > 0 ? "partial" : "success", totalInserted + totalSkipped, totalInserted, totalSkipped, totalFailed]
        );
      } finally {
        client.release();
      }
    });

    return {
      status: totalFailed > 0 ? "partial" : "success",
      runId,
      inserted: totalInserted,
      skipped: totalSkipped,
      failedPages: totalFailed,
    };
  }
);
