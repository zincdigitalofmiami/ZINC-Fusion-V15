/**
 * ProFarmer Premium News Scraper (Stealth Headless Browser)
 *
 * INGESTION CONTRACT:
 * - Logs each run in ops.ingest_run
 * - Computes row_hash for idempotency
 * - Append-only inserts (no upserts)
 *
 * Client pays $500/month for ProFarmer subscription.
 * Uses puppeteer-extra with stealth plugin to bypass bot detection.
 *
 * Scrapes 7 report sections:
 * - First Thing Today (morning outlook)
 * - Ahead of the Open (pre-market)
 * - Daily Advice Monitor (trading signals)
 * - Washington/Ag Policy (policy news)
 * - Pro Farmer Editors (editorial analysis)
 * - Crop Tour (field reports)
 * - After the Bell (closing summaries)
 *
 * NOTE: This file intentionally does NOT use step.run() for browser operations.
 * Puppeteer Browser/Page objects are NOT JSON-serializable, so wrapping them
 * in step.run() causes Inngest replay to deserialize dead objects.
 * DB connections are acquired fresh for each DB-touching phase to avoid
 * stale connections during long browser operations.
 *
 * Requires env vars:
 *   PROFARMER_USERNAME - ProFarmer login email
 *   PROFARMER_PASSWORD - ProFarmer password
 *
 * @author Claude (ZINC-FUSION-V15)
 * @version 1.1.0
 * @date 2026-02-16
 */

import { inngest, DB_CONCURRENCY } from "./client";
import { createHash } from "crypto";
import { type Page } from "puppeteer-core";

// Vercel/Next output tracing sometimes misses this transitive dependency used
// by puppeteer-extra/stealth via dynamic require(), causing runtime crashes.
import "is-plain-object";

import dbPool from "@/lib/db";

const pool = dbPool;

const PROFARMER_BASE = "https://www.profarmer.com";
const PROFARMER_LOGIN_URL = `${PROFARMER_BASE}/r/sign-in`;

const REPORTS = [
  {
    slug: "first-thing-today",
    name: "First Thing Today",
    url: `${PROFARMER_BASE}/topics/first-thing-today`,
    specialists: ["crush", "china"],
  },
  {
    slug: "ahead-of-the-open",
    name: "Ahead of the Open",
    url: `${PROFARMER_BASE}/topics/ahead-open`,
    specialists: ["crush", "china", "energy"],
  },
  {
    slug: "daily-advice-monitor",
    name: "Daily Advice Monitor",
    url: `${PROFARMER_BASE}/news/advice-monitor/pro-farmers-daily-advice-monitor`,
    specialists: ["crush", "china", "energy"],
  },
  {
    slug: "washington-ag-policy",
    name: "Washington/Ag Policy",
    url: `${PROFARMER_BASE}/news/policy-update`,
    specialists: ["tariff", "biofuel", "trump_effect"],
  },
  {
    slug: "pro-farmer-editors",
    name: "Pro Farmer Editors",
    url: `${PROFARMER_BASE}/topics/pro-farmer-editors`,
    specialists: ["crush", "china", "biofuel"],
  },
  {
    slug: "crop-tour",
    name: "Crop Tour",
    url: `${PROFARMER_BASE}/topics/pro-farmer-crop-tour`,
    specialists: ["crush", "china"],
  },
  {
    slug: "after-the-bell",
    name: "After the Bell",
    url: `${PROFARMER_BASE}/news/after-bell`,
    specialists: ["crush", "volatility"],
  },
];

function computeRowHash(url: string, title: string, pubDate: string): string {
  return createHash("sha256")
    .update(`${url}|${title}|${pubDate}`)
    .digest("hex");
}

// PoolClient helper functions removed — SQL inlined to prevent stale connections
// during long browser operations (30+ seconds of scraping).

interface ScrapedArticle {
  url: string;
  title: string;
  content: string;
  pubDate: string;
  author: string | null;
  reportSlug: string;
  specialists: string[];
}

type PuppeteerExtra = typeof import("puppeteer-extra").default;
let cachedPuppeteerExtra: PuppeteerExtra | null = null;

async function getPuppeteerExtra(): Promise<PuppeteerExtra> {
  if (cachedPuppeteerExtra) {
    return cachedPuppeteerExtra;
  }

  const [{ default: puppeteerExtra }, { default: StealthPlugin }] =
    await Promise.all([
      import("puppeteer-extra"),
      import("puppeteer-extra-plugin-stealth"),
    ]);

  puppeteerExtra.use(StealthPlugin());
  cachedPuppeteerExtra = puppeteerExtra;
  return cachedPuppeteerExtra;
}


/**
 * Extract topics from ProFarmer content
 */
function extractTopics(
  title: string,
  content: string,
  reportSlug: string,
): string[] {
  const topicKeywords = [
    "corn",
    "soybeans",
    "wheat",
    "cattle",
    "hogs",
    "cotton",
    "exports",
    "imports",
    "trade",
    "tariff",
    "china",
    "brazil",
    "weather",
    "drought",
    "flooding",
    "planting",
    "harvest",
    "usda",
    "wasde",
    "crop report",
    "acreage",
    "yield",
    "biofuel",
    "ethanol",
    "biodiesel",
    "rin",
    "epa",
    "prices",
    "futures",
    "basis",
    "spreads",
    "crush",
  ];
  const topics = new Set<string>();
  const searchText = `${title} ${content}`.toLowerCase();

  for (const topic of topicKeywords) {
    if (searchText.includes(topic)) {
      topics.add(topic);
    }
  }
  topics.add(reportSlug.replace(/-/g, " "));
  return Array.from(topics).slice(0, 10);
}

/**
 * Extract subjects (entities mentioned)
 */
function extractSubjects(title: string, content: string): string[] {
  const subjectPatterns = [
    "china",
    "brazil",
    "argentina",
    "mexico",
    "canada",
    "usda",
    "epa",
    "congress",
    "white house",
    "trump",
    "cargill",
    "adm",
    "bunge",
    "dreyfus",
    "cme",
    "cbot",
    "kcbt",
  ];
  const subjects = new Set<string>();
  const searchText = `${title} ${content}`.toLowerCase();

  for (const subject of subjectPatterns) {
    if (searchText.includes(subject)) {
      subjects.add(subject);
    }
  }
  return Array.from(subjects).slice(0, 10);
}


/**
 * Launch browser and login to ProFarmer.
 *
 * Uses the proven keyboard-based login flow from the working JS scrapers
 * (scripts/_deprecated/scrape_profarmer_final.js). Key details:
 *  - evaluate() focus/click on the email input ensures correct field state
 *    before typing begins (page.type(selector) can target stale/hidden elements).
 *  - Tab between fields triggers blur → validation → focus cycle.
 *  - 8s post-login wait allows auth redirect + cookie settlement.
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
async function launchProFarmerBrowser(): Promise<{ browser: any; page: any }> {
  const user = process.env.PROFARMER_USERNAME;
  const pass = process.env.PROFARMER_PASSWORD;

  console.log(
    `[profarmer] browser-launch preflight hasUser=${Boolean(user)} hasPass=${Boolean(pass)} node=${process.version} region=${process.env.VERCEL_REGION ?? "n/a"}`,
  );

  if (!user || !pass) {
    throw new Error("PROFARMER_USERNAME and PROFARMER_PASSWORD required");
  }

  // Dynamic import for serverless chromium path resolution.
  const chromium = await import("@sparticuz/chromium");
  const puppeteerExtra = await getPuppeteerExtra();

  const browser = await puppeteerExtra.launch({
    args: [
      ...chromium.default.args,
      "--no-sandbox",
      "--disable-setuid-sandbox",
      "--disable-dev-shm-usage",
      "--disable-accelerated-2d-canvas",
      "--disable-gpu",
      "--window-size=1920,1080",
    ],
    defaultViewport: { width: 1920, height: 1080 },
    executablePath: await chromium.default.executablePath(),
    headless: true,
  });

  const page = await browser.newPage();

  // Set realistic viewport and user agent
  await page.setViewport({ width: 1920, height: 1080 });
  await page.setUserAgent(
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
  );

  // Set extra headers to look more human
  await page.setExtraHTTPHeaders({
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    Accept:
      "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    Connection: "keep-alive",
    "Upgrade-Insecure-Requests": "1",
  });

  // Navigate to login page
  console.log("[profarmer] navigating to login page...");
  await page.goto(PROFARMER_LOGIN_URL, {
    waitUntil: "networkidle2",
    timeout: 60000,
  });

  // Wait for SPA hydration before interacting with the form
  await new Promise((r) => setTimeout(r, 1500));

  // Focus the email input inside the login form (proven pattern from working JS scrapers)
  const foundForm = await page.evaluate(() => {
    const forms = document.querySelectorAll("form");
    for (const form of forms) {
      const emailInput = form.querySelector(
        'input[type="email"]',
      ) as HTMLInputElement | null;
      if (emailInput && form.querySelector('input[type="password"]')) {
        emailInput.focus();
        emailInput.click();
        return true;
      }
    }
    return false;
  });

  if (!foundForm) {
    throw new Error("Could not find login form with email + password fields");
  }

  // Keyboard-based login: fires real KeyDown/KeyPress/KeyUp events
  await page.keyboard.type(user, { delay: 80 });
  await new Promise((r) => setTimeout(r, 500));
  await page.keyboard.press("Tab");
  await new Promise((r) => setTimeout(r, 500));
  await page.keyboard.type(pass, { delay: 80 });
  await new Promise((r) => setTimeout(r, 500));
  await page.keyboard.press("Enter");

  // Wait for auth redirect to complete (8s matches working scripts)
  await new Promise((r) => setTimeout(r, 8000));

  // Check if login succeeded
  const currentUrl = page.url();
  console.log("[profarmer] post-login URL:", currentUrl);

  if (currentUrl.includes("sign-in") || currentUrl.includes("login")) {
    const hasCaptcha = await page.evaluate(() => {
      return !!document.querySelector(
        'iframe[src*="recaptcha"], [class*="captcha"], #captcha, .g-recaptcha',
      );
    });

    if (hasCaptcha) {
      throw new Error("Login blocked by CAPTCHA");
    }

    const errorText = await page.evaluate(() => {
      const errorEl = document.querySelector(
        '.error, .alert-danger, [class*="error"]',
      );
      return errorEl?.textContent?.trim() || null;
    });

    throw new Error(
      `Login failed - still on login page${errorText ? `: ${errorText}` : ""}`,
    );
  }

  console.log("[profarmer] login successful!");
  return { browser, page };
}

/**
 * Scrape article links from a report listing page.
 *
 * Uses the `a[href*="/news/"]` selector proven in the working JS scrapers
 * instead of generic article/post container selectors.
 */
async function scrapeReportArticles(
  page: Page,
  reportUrl: string,
  reportSlug: string,
  specialists: string[],
  maxArticles: number = 15,
): Promise<ScrapedArticle[]> {
  console.log(`[profarmer] scraping ${reportUrl}...`);
  await page.goto(reportUrl, { waitUntil: "networkidle2", timeout: 60000 });
  await new Promise((r) => setTimeout(r, 500 + Math.random() * 500));

  // Extract article links from listing page (proven selector from working scripts)
  const articleLinks = await page.evaluate(
    (max: number) => {
      const results: Array<{ url: string; title: string }> = [];
      const links = document.querySelectorAll('a[href*="/news/"]');
      const seen = new Set<string>();

      for (const a of links) {
        const href = (a as HTMLAnchorElement).href;
        const pathParts = href
          .replace("https://www.profarmer.com", "")
          .split("/")
          .filter(Boolean);
        if (pathParts.length < 3) continue;
        if (href.includes("/r/") || href.includes("subscribe")) continue;
        if (seen.has(href)) continue;

        const title = a.textContent?.trim();
        if (!title || title.length < 15) continue;

        seen.add(href);
        results.push({ url: href, title });
        if (results.length >= max) break;
      }
      return results;
    },
    maxArticles,
  );

  // Visit each article page to get full content, date, and author
  const articles: ScrapedArticle[] = [];

  for (const link of articleLinks) {
    try {
      await page.goto(link.url, {
        waitUntil: "networkidle2",
        timeout: 20000,
      });
      await new Promise((r) => setTimeout(r, 300));

      const pageData = await page.evaluate(() => {
        // Date: meta tag → JSON-LD → .Page-datePublished (ProFarmer-specific)
        let date = "";
        const metaDate = document.querySelector(
          'meta[property="article:published_time"]',
        );
        if (metaDate) {
          date = metaDate.getAttribute("content") || "";
        }

        if (!date) {
          const scripts = document.querySelectorAll(
            'script[type="application/ld+json"]',
          );
          for (const s of scripts) {
            try {
              const json = JSON.parse(s.textContent || "");
              if (json.datePublished) {
                date = json.datePublished;
                break;
              }
            } catch {
              /* skip invalid JSON-LD */
            }
          }
        }

        if (!date) {
          const dateEl = document.querySelector(".Page-datePublished");
          if (dateEl) date = dateEl.textContent?.trim() || "";
        }

        // Author: .Page-authorName → .byline → [rel="author"]
        let author = "";
        const authorEl = document.querySelector(
          '.Page-authorName a, .byline a, [rel="author"]',
        );
        if (authorEl) author = authorEl.textContent?.trim() || "";

        // Content: ProFarmer-specific selectors → generic fallbacks
        let content = "";
        const contentSelectors = [
          ".Page-articleBody",
          ".RichTextArticleBody",
          ".RichTextBody",
          ".Page-content",
          "article",
        ];
        for (const sel of contentSelectors) {
          const el = document.querySelector(sel);
          if (el?.textContent && el.textContent.length > 100) {
            content = el.textContent.trim().slice(0, 50000);
            break;
          }
        }

        return { date, content, author };
      });

      // Parse date into YYYY-MM-DD
      let pubDate = "";
      if (pageData.date) {
        let parsed = new Date(pageData.date);
        if (isNaN(parsed.getTime())) {
          // Natural language fallback: "January 30, 2026 06:15 AM"
          const match = pageData.date.match(/(\w+)\s+(\d+),?\s+(\d{4})/);
          if (match) {
            parsed = new Date(`${match[1]} ${match[2]}, ${match[3]}`);
          }
        }
        if (!isNaN(parsed.getTime())) {
          pubDate = parsed.toISOString().split("T")[0];
        }
      }

      if (!pubDate || !pageData.content || pageData.content.length < 100) {
        continue;
      }

      articles.push({
        url: link.url,
        title: link.title,
        content: pageData.content,
        pubDate,
        author: pageData.author || null,
        reportSlug,
        specialists,
      });
    } catch {
      // Skip articles that fail to load
    }
  }

  return articles;
}

export const profarmerDaily = inngest.createFunction(
  {
    id: "profarmer-daily",
    name: "ProFarmer Premium Scraper",
    retries: 2,
    concurrency: [DB_CONCURRENCY, { limit: 1 }],
  },
  { cron: "TZ=America/Chicago 0 7 * * 1-5" }, // Weekdays 7 AM CT
  async ({ logger }) => {
    // ── Phase 1: create ingest run (quick DB touch, release immediately) ──
    let runId: string;
    {
      const client = await pool.connect();
      try {
        const result = await client.query(
          `INSERT INTO ops.ingest_run (job_name, status, started_at) VALUES ($1, 'running', NOW()) RETURNING id`,
          ["profarmer-daily"],
        );
        runId = result.rows[0].id as string;
      } finally {
        client.release();
      }
    }
    logger.info(`ProFarmer ingest run: ${runId}`);

    // ── Phase 2: browser scraping (NO DB connection held during this) ──
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    let browser: any = null;
    let allArticles: ScrapedArticle[] = [];

    try {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      let page: any;
      try {
        const result = await launchProFarmerBrowser();
        browser = result.browser;
        page = result.page;
        logger.info("ProFarmer login successful");
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        logger.error(
          `[profarmer] login failed runId=${runId} node=${process.version} region=${process.env.VERCEL_REGION ?? "n/a"} msg=${msg}`,
        );
        // Update ingest run with fresh connection
        const client = await pool.connect();
        try {
          await client.query(
            `UPDATE ops.ingest_run SET status=$2, completed_at=NOW(),
             rows_attempted=$3, rows_inserted=$4, rows_skipped=$5, rows_quarantined=$6, error_message=$7 WHERE id=$1`,
            [runId, "login_failed", 0, 0, 0, 0, msg],
          );
        } finally {
          client.release();
        }
        return { status: "login_failed", error: msg };
      }

      // Scrape each report (all browser work, no DB)
      for (const report of REPORTS) {
        try {
          const articles = await scrapeReportArticles(
            page,
            report.url,
            report.slug,
            report.specialists,
            15,
          );
          logger.info(`${report.name}: ${articles.length} articles found`);
          allArticles.push(...articles);
        } catch (err) {
          logger.warn(`Report ${report.name} failed: ${err}`);
        }
      }
    } finally {
      if (browser) await browser.close();
    }

    // ── Phase 3: DB inserts (fresh connection, browser is closed) ──
    let attempted = 0;
    let inserted = 0;
    let skipped = 0;
    let quarantined = 0;

    const client = await pool.connect();
    try {
      for (const article of allArticles) {
        attempted++;
        const rowHash = computeRowHash(
          article.url,
          article.title,
          article.pubDate,
        );

        // Dedup by row_hash OR url (handles cross-scheme hashes from legacy scrapers)
        const exists = await client.query(
          `SELECT 1 FROM alt.profarmer_news_event WHERE row_hash = $1 OR url = $2 LIMIT 1`,
          [rowHash, article.url],
        );

        if (exists.rows.length > 0) {
          skipped++;
          continue;
        }

        // Compute metadata
        const report = REPORTS.find(r => r.slug === article.reportSlug);
        const topics = extractTopics(
          article.title,
          article.content,
          article.reportSlug,
        );
        const subjects = extractSubjects(article.title, article.content);
        const summary = article.content.slice(0, 500);
        const metaDescription = article.content.slice(0, 300);

        try {
          await client.query(
            `INSERT INTO alt.profarmer_news_event (
               event_date, section, headline, content, url, author,
               specialist_tags, summary, topics, subjects,
               meta_description, raw_payload, row_hash
             ) VALUES ($1::date, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12::jsonb, $13)`,
            [
              article.pubDate,
              report?.name ?? article.reportSlug,
              article.title,
              article.content,
              article.url,
              article.author,
              article.specialists,
              summary,
              topics,
              subjects,
              metaDescription,
              JSON.stringify({ report: report?.name ?? article.reportSlug, slug: article.reportSlug }),
              rowHash,
            ],
          );
          inserted++;
          logger.info(`Inserted: ${article.title.slice(0, 50)}...`);
        } catch (err) {
          quarantined++;
          logger.warn(`Insert failed: ${err}`);
        }
      }

      // Finalize ingest run
      await client.query(
        `UPDATE ops.ingest_run SET status=$2, completed_at=NOW(),
         rows_attempted=$3, rows_inserted=$4, rows_skipped=$5, rows_quarantined=$6 WHERE id=$1`,
        [runId, "success", attempted, inserted, skipped, quarantined],
      );
    } catch (error) {
      const msg = error instanceof Error ? error.message : String(error);
      await client.query(
        `UPDATE ops.ingest_run SET status=$2, completed_at=NOW(),
         rows_attempted=$3, rows_inserted=$4, rows_skipped=$5, rows_quarantined=$6, error_message=$7 WHERE id=$1`,
        [runId, "failed", attempted, inserted, skipped, quarantined, msg],
      );
      throw error;
    } finally {
      client.release();
    }

    return {
      status: "success",
      runId,
      attempted,
      inserted,
      skipped,
      quarantined,
    };
  },
);

export const profarmerBackfill = inngest.createFunction(
  { id: "profarmer-backfill", name: "ProFarmer 6-Month Backfill", retries: 1, concurrency: [DB_CONCURRENCY, { limit: 1 }] },
  { event: "profarmer/backfill" },
  async ({ logger }) => {
    // ── Phase 1: create ingest run ──
    let runId: string;
    {
      const client = await pool.connect();
      try {
        const result = await client.query(
          `INSERT INTO ops.ingest_run (job_name, status, started_at) VALUES ($1, 'running', NOW()) RETURNING id`,
          ["profarmer-backfill"],
        );
        runId = result.rows[0].id as string;
      } finally {
        client.release();
      }
    }

    // ── Phase 2: browser scraping (NO DB connection held) ──
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    let browser: any = null;
    const allArticles: Array<ScrapedArticle & { reportName: string; pageNum: number }> = [];

    try {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      let page: any;
      const result = await launchProFarmerBrowser();
      browser = result.browser;
      page = result.page;

      for (const report of REPORTS) {
        for (let pageNum = 1; pageNum <= 50; pageNum++) {
          const pageUrl =
            pageNum === 1 ? report.url : `${report.url}?page=${pageNum}`;

          try {
            const articles = await scrapeReportArticles(
              page,
              pageUrl,
              report.slug,
              report.specialists,
              20,
            );

            if (articles.length === 0) break;
            logger.info(
              `${report.name} p${pageNum}: ${articles.length} articles`,
            );

            for (const article of articles) {
              allArticles.push({ ...article, reportName: report.name, pageNum });
            }

            await new Promise((r) => setTimeout(r, 2000));
          } catch {
            break;
          }
        }
      }
    } finally {
      if (browser) await browser.close();
    }

    // ── Phase 3: DB inserts (fresh connection, browser is closed) ──
    let attempted = 0;
    let inserted = 0;
    let skipped = 0;
    let quarantined = 0;

    const client = await pool.connect();
    try {
      for (const article of allArticles) {
        attempted++;
        const rowHash = computeRowHash(
          article.url,
          article.title,
          article.pubDate,
        );

        const exists = await client.query(
          `SELECT 1 FROM alt.profarmer_news_event WHERE row_hash = $1 OR url = $2 LIMIT 1`,
          [rowHash, article.url],
        );

        if (exists.rows.length > 0) {
          skipped++;
          continue;
        }

        const topics = extractTopics(
          article.title,
          article.content,
          article.reportSlug,
        );
        const subjects = extractSubjects(article.title, article.content);
        const summary = article.content.slice(0, 500);
        const metaDescription = article.content.slice(0, 300);

        try {
          await client.query(
            `INSERT INTO alt.profarmer_news_event (
               event_date, section, headline, content, url, author,
               specialist_tags, summary, topics, subjects,
               meta_description, raw_payload, row_hash
             ) VALUES ($1::date, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12::jsonb, $13)`,
            [
              article.pubDate,
              article.reportName,
              article.title,
              article.content,
              article.url,
              article.author,
              article.specialists,
              summary,
              topics,
              subjects,
              metaDescription,
              JSON.stringify({
                report: article.reportName,
                slug: article.reportSlug,
                backfill: true,
                page: article.pageNum,
              }),
              rowHash,
            ],
          );
          inserted++;
        } catch {
          quarantined++;
        }
      }

      await client.query(
        `UPDATE ops.ingest_run SET status=$2, completed_at=NOW(),
         rows_attempted=$3, rows_inserted=$4, rows_skipped=$5, rows_quarantined=$6 WHERE id=$1`,
        [runId, "success", attempted, inserted, skipped, quarantined],
      );
    } catch (error) {
      const msg = error instanceof Error ? error.message : String(error);
      await client.query(
        `UPDATE ops.ingest_run SET status=$2, completed_at=NOW(),
         rows_attempted=$3, rows_inserted=$4, rows_skipped=$5, rows_quarantined=$6, error_message=$7 WHERE id=$1`,
        [runId, "failed", attempted, inserted, skipped, quarantined, msg],
      );
      throw error;
    } finally {
      client.release();
    }

    return { status: "success", runId, attempted, inserted, skipped, quarantined };
  },
);
