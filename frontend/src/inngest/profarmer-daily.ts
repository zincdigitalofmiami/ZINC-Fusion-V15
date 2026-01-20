/**
 * ProFarmer Premium News Scraper
 *
 * Scrapes 4 key reports from ProFarmer ($500/month subscription):
 * - Daily Advice Monitor (trading signals)
 * - First Thing Today (morning outlook)
 * - Washington/Ag Policy (policy news)
 * - After the Bell (closing summaries)
 *
 * Requires env vars:
 *   PROFARMER_USER - ProFarmer login email
 *   PROFARMER_PASS - ProFarmer password
 *
 * Schedule: Daily at 6 AM CT (after First Thing Today) and 5 PM CT (after After the Bell)
 */

import { inngest } from "./client";
import { createHash } from "crypto";
import { Pool, type PoolClient } from "pg";

const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
  ssl: { rejectUnauthorized: false },
});

const PROFARMER_BASE = "https://www.profarmer.com";
const PROFARMER_LOGIN_URL = `${PROFARMER_BASE}/login`;

// Reports to scrape with their specialist tags
const REPORTS = [
  {
    slug: "daily-advice-monitor",
    name: "Daily Advice Monitor",
    url: `${PROFARMER_BASE}/daily-advice-monitor/`,
    specialists: ["crush", "china", "energy"],
    priority: "critical",
  },
  {
    slug: "first-thing-today",
    name: "First Thing Today",
    url: `${PROFARMER_BASE}/first-thing-today/`,
    specialists: ["crush", "china"],
    priority: "high",
  },
  {
    slug: "washington-ag-policy",
    name: "Washington/Ag Policy",
    url: `${PROFARMER_BASE}/washington-ag-policy/`,
    specialists: ["tariff", "biofuel", "trump_effect"],
    priority: "critical",
  },
  {
    slug: "after-the-bell",
    name: "After the Bell",
    url: `${PROFARMER_BASE}/after-the-bell/`,
    specialists: ["crush", "volatility"],
    priority: "high",
  },
];

function computeRowHash(url: string, title: string, pubDate: string): string {
  return createHash("sha256").update(`${url}|${title}|${pubDate}`).digest("hex");
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

interface ArticleData {
  url: string;
  title: string;
  content: string;
  pubDate: string;
  reportSlug: string;
  specialists: string[];
}

/**
 * Login to ProFarmer and return session cookies
 */
async function loginToProFarmer(): Promise<string> {
  const user = process.env.PROFARMER_USER;
  const pass = process.env.PROFARMER_PASS;

  if (!user || !pass) {
    throw new Error("PROFARMER_USER and PROFARMER_PASS environment variables required");
  }

  // First, get the login page to capture any CSRF token
  const loginPageRes = await fetch(PROFARMER_LOGIN_URL, {
    method: "GET",
    redirect: "manual",
  });

  // Extract cookies from initial request
  const initialCookies = loginPageRes.headers.getSetCookie?.() || [];

  // Attempt login - ProFarmer uses form-based auth
  const loginRes = await fetch(PROFARMER_LOGIN_URL, {
    method: "POST",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
      Cookie: initialCookies.join("; "),
    },
    body: new URLSearchParams({
      email: user,
      password: pass,
      remember: "1",
    }),
    redirect: "manual",
  });

  // Collect all session cookies
  const sessionCookies = loginRes.headers.getSetCookie?.() || [];
  const allCookies = [...initialCookies, ...sessionCookies];

  if (allCookies.length === 0) {
    throw new Error("ProFarmer login failed - no session cookies returned");
  }

  // Verify login succeeded by checking redirect or response
  const location = loginRes.headers.get("location");
  if (loginRes.status === 302 && location && !location.includes("login")) {
    // Successful login redirects away from login page
    return allCookies.join("; ");
  }

  // Check if we got a session cookie even without redirect
  const hasSession = allCookies.some(
    (c) => c.includes("session") || c.includes("auth") || c.includes("PHPSESSID")
  );

  if (hasSession) {
    return allCookies.join("; ");
  }

  throw new Error("ProFarmer login failed - invalid credentials or captcha required");
}

/**
 * Fetch a report page and extract articles
 */
async function fetchReportArticles(
  reportUrl: string,
  reportSlug: string,
  specialists: string[],
  cookies: string,
  maxArticles: number = 10
): Promise<ArticleData[]> {
  const res = await fetch(reportUrl, {
    headers: {
      Cookie: cookies,
      "User-Agent": "ZINC-Fusion/1.0 (Agricultural Intelligence)",
    },
  });

  if (!res.ok) {
    throw new Error(`Failed to fetch ${reportUrl}: ${res.status}`);
  }

  const html = await res.text();
  const articles: ArticleData[] = [];

  // Parse article links from the listing page
  // ProFarmer uses WordPress-style article listings
  const articlePattern = /<article[^>]*>[\s\S]*?<a[^>]*href="([^"]+)"[^>]*>[\s\S]*?<h[234][^>]*>([^<]+)<\/h[234]>[\s\S]*?<time[^>]*datetime="([^"]+)"[^>]*>/gi;

  let match;
  while ((match = articlePattern.exec(html)) !== null && articles.length < maxArticles) {
    const [, articleUrl, title, datetime] = match;

    // Only process articles from this report section
    if (!articleUrl.includes(reportSlug)) continue;

    // Fetch individual article content
    try {
      const articleRes = await fetch(articleUrl, {
        headers: { Cookie: cookies },
      });

      if (!articleRes.ok) continue;

      const articleHtml = await articleRes.text();

      // Extract article content
      const contentMatch = articleHtml.match(/<div[^>]*class="[^"]*entry-content[^"]*"[^>]*>([\s\S]*?)<\/div>/i);
      const content = contentMatch
        ? contentMatch[1]
            .replace(/<[^>]+>/g, " ") // Strip HTML tags
            .replace(/\s+/g, " ") // Normalize whitespace
            .trim()
            .slice(0, 5000) // Limit content length
        : "";

      articles.push({
        url: articleUrl,
        title: title.trim(),
        content,
        pubDate: datetime.split("T")[0], // YYYY-MM-DD
        reportSlug,
        specialists,
      });

      // Rate limit between article fetches
      await new Promise((r) => setTimeout(r, 200));
    } catch {
      // Skip articles that fail to fetch
      continue;
    }
  }

  return articles;
}

/**
 * Alternative parsing for paginated/archive pages
 */
async function fetchArchiveArticles(
  baseUrl: string,
  reportSlug: string,
  specialists: string[],
  cookies: string,
  pages: number = 1
): Promise<ArticleData[]> {
  const allArticles: ArticleData[] = [];

  for (let page = 1; page <= pages; page++) {
    const pageUrl = page === 1 ? baseUrl : `${baseUrl}page/${page}/`;

    try {
      const res = await fetch(pageUrl, {
        headers: {
          Cookie: cookies,
          "User-Agent": "ZINC-Fusion/1.0",
        },
      });

      if (!res.ok) break;

      const html = await res.text();

      // Look for article entries in various formats
      // Pattern 1: Standard WordPress
      const wpPattern = /<a[^>]*href="([^"]*profarmer\.com[^"]*)"[^>]*title="([^"]+)"[^>]*>/gi;

      // Pattern 2: Date-based listings
      const datePattern = /(\d{4}-\d{2}-\d{2})[^<]*<a[^>]*href="([^"]+)"[^>]*>([^<]+)</gi;

      let match;
      while ((match = wpPattern.exec(html)) !== null) {
        const [, url, title] = match;
        if (url.includes(reportSlug)) {
          // Extract date from URL if possible (ProFarmer uses /YYYY/MM/DD/ format)
          const dateMatch = url.match(/\/(\d{4})\/(\d{2})\/(\d{2})\//);
          const pubDate = dateMatch
            ? `${dateMatch[1]}-${dateMatch[2]}-${dateMatch[3]}`
            : new Date().toISOString().split("T")[0];

          allArticles.push({
            url,
            title: title.trim(),
            content: "", // Content fetched separately if needed
            pubDate,
            reportSlug,
            specialists,
          });
        }
      }

      // Rate limit between pages
      await new Promise((r) => setTimeout(r, 500));
    } catch {
      break;
    }
  }

  return allArticles;
}

export const profarmerDaily = inngest.createFunction(
  { id: "profarmer-daily", name: "ProFarmer Premium News Daily", retries: 2 },
  { cron: "0 12,23 * * 1-5" }, // 6 AM CT and 5 PM CT weekdays
  async ({ step, logger }) => {
    if (!process.env.DATABASE_URL) {
      throw new Error("DATABASE_URL not configured");
    }

    const client = await pool.connect();
    let runId: string | null = null;
    let attempted = 0;
    let inserted = 0;
    let skipped = 0;
    let quarantined = 0;

    try {
      runId = await step.run("create-ingest-run", () =>
        createIngestRun(client, "profarmer-daily")
      );
      logger.info(`Started ProFarmer ingest run: ${runId}`);

      // Step 1: Login to ProFarmer
      const cookies = await step.run("login", async () => {
        return await loginToProFarmer();
      });
      logger.info("Successfully logged into ProFarmer");

      // Step 2: Fetch articles from each report
      for (const report of REPORTS) {
        const articles = await step.run(`fetch-${report.slug}`, async () => {
          return await fetchReportArticles(
            report.url,
            report.slug,
            report.specialists,
            cookies,
            10 // Last 10 articles per report
          );
        });

        logger.info(`Fetched ${articles.length} articles from ${report.name}`);

        // Step 3: Insert articles
        for (const article of articles) {
          attempted++;

          const rowHash = computeRowHash(article.url, article.title, article.pubDate);

          // Check if already exists
          const existing = await client.query(
            `SELECT 1 FROM alt.news_1d WHERE row_hash = $1 LIMIT 1`,
            [rowHash]
          );

          if (existing.rows.length > 0) {
            skipped++;
            continue;
          }

          try {
            await client.query(
              `INSERT INTO alt.news_1d (
                 event_date, source, headline, content, url,
                 specialist_tags, raw_payload, row_hash, ingestion_batch_id
               ) VALUES ($1::date, $2, $3, $4, $5, $6, $7::jsonb, $8, $9)`,
              [
                article.pubDate,
                "profarmer",
                article.title,
                article.content,
                article.url,
                article.specialists,
                JSON.stringify({
                  report: report.name,
                  reportSlug: report.slug,
                  priority: report.priority,
                }),
                rowHash,
                runId,
              ]
            );
            inserted++;
          } catch (err) {
            quarantined++;
            logger.warn(`Failed to insert article: ${article.url} - ${err}`);
          }
        }
      }

      await step.run("complete", () =>
        updateIngestRun(client, runId!, "success", attempted, inserted, skipped, quarantined)
      );

      return {
        status: "success",
        runId,
        attempted,
        inserted,
        skipped,
        quarantined,
        reports: REPORTS.map((r) => r.name),
      };
    } catch (error) {
      const msg = error instanceof Error ? error.message : String(error);
      if (runId) {
        await updateIngestRun(client, runId, "failed", attempted, inserted, skipped, quarantined, msg);
      }
      throw error;
    } finally {
      client.release();
    }
  }
);

/**
 * Manual backfill function - fetches last 6 months of articles
 */
export const profarmerBackfill = inngest.createFunction(
  { id: "profarmer-backfill", name: "ProFarmer 6-Month Backfill", retries: 1 },
  { event: "profarmer/backfill" }, // Triggered manually
  async ({ step, logger }) => {
    if (!process.env.DATABASE_URL) {
      throw new Error("DATABASE_URL not configured");
    }

    const client = await pool.connect();
    let runId: string | null = null;
    let attempted = 0;
    let inserted = 0;
    let skipped = 0;
    let quarantined = 0;

    try {
      runId = await step.run("create-ingest-run", () =>
        createIngestRun(client, "profarmer-backfill")
      );
      logger.info(`Started ProFarmer backfill run: ${runId}`);

      // Login
      const cookies = await step.run("login", async () => {
        return await loginToProFarmer();
      });

      // For backfill, fetch more pages from archives
      const BACKFILL_PAGES = 30; // ~6 months of daily content

      for (const report of REPORTS) {
        const articles = await step.run(`backfill-${report.slug}`, async () => {
          return await fetchArchiveArticles(
            report.url,
            report.slug,
            report.specialists,
            cookies,
            BACKFILL_PAGES
          );
        });

        logger.info(`Backfill: ${articles.length} articles from ${report.name}`);

        // Fetch content for each article and insert
        for (const article of articles) {
          attempted++;

          // Fetch full content if not already present
          if (!article.content && article.url) {
            try {
              const res = await fetch(article.url, {
                headers: { Cookie: cookies },
              });
              if (res.ok) {
                const html = await res.text();
                const contentMatch = html.match(
                  /<div[^>]*class="[^"]*entry-content[^"]*"[^>]*>([\s\S]*?)<\/div>/i
                );
                article.content = contentMatch
                  ? contentMatch[1]
                      .replace(/<[^>]+>/g, " ")
                      .replace(/\s+/g, " ")
                      .trim()
                      .slice(0, 5000)
                  : "";
              }
              // Rate limit
              await new Promise((r) => setTimeout(r, 300));
            } catch {
              // Continue without content
            }
          }

          const rowHash = computeRowHash(article.url, article.title, article.pubDate);

          const existing = await client.query(
            `SELECT 1 FROM alt.news_1d WHERE row_hash = $1 LIMIT 1`,
            [rowHash]
          );

          if (existing.rows.length > 0) {
            skipped++;
            continue;
          }

          try {
            await client.query(
              `INSERT INTO alt.news_1d (
                 event_date, source, headline, content, url,
                 specialist_tags, raw_payload, row_hash, ingestion_batch_id
               ) VALUES ($1::date, $2, $3, $4, $5, $6, $7::jsonb, $8, $9)`,
              [
                article.pubDate,
                "profarmer",
                article.title,
                article.content,
                article.url,
                article.specialists,
                JSON.stringify({ report: report.slug, backfill: true }),
                rowHash,
                runId,
              ]
            );
            inserted++;
          } catch (err) {
            quarantined++;
            logger.warn(`Backfill insert failed: ${article.url}`);
          }
        }
      }

      await step.run("complete", () =>
        updateIngestRun(client, runId!, "success", attempted, inserted, skipped, quarantined)
      );

      return {
        status: "success",
        runId,
        attempted,
        inserted,
        skipped,
        quarantined,
      };
    } catch (error) {
      const msg = error instanceof Error ? error.message : String(error);
      if (runId) {
        await updateIngestRun(client, runId, "failed", attempted, inserted, skipped, quarantined, msg);
      }
      throw error;
    } finally {
      client.release();
    }
  }
);
