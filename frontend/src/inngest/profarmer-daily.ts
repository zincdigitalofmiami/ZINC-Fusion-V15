/**
 * ProFarmer Premium News Scraper (Headless Browser + CAPTCHA Solving)
 *
 * Scrapes 4 key reports from ProFarmer ($500/month subscription):
 * - Daily Advice Monitor (trading signals)
 * - First Thing Today (morning outlook)
 * - Washington/Ag Policy (policy news)
 * - After the Bell (closing summaries)
 *
 * Requires env vars:
 *   PROFARMER_USERNAME - ProFarmer login email
 *   PROFARMER_PASSWORD - ProFarmer password
 *   TWOCAPTCHA_API_KEY - 2captcha.com API key (for captcha solving)
 *
 * Schedule: Daily at 6 AM CT (after First Thing Today) and 5 PM CT (after After the Bell)
 */

import { inngest } from "./client";
import { createHash } from "crypto";
import { Pool, type PoolClient } from "pg";

// Dynamically import puppeteer to avoid bundling issues
async function getPuppeteer() {
  const puppeteer = await import("puppeteer-core");
  const chromium = await import("@sparticuz/chromium");
  return { puppeteer: puppeteer.default, chromium: chromium.default };
}

const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
  ssl: { rejectUnauthorized: false },
});

const PROFARMER_BASE = "https://www.profarmer.com";
const PROFARMER_LOGIN_URL = `${PROFARMER_BASE}/r/sign-in`;

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
 * Solve reCAPTCHA using 2captcha service
 */
async function solveCaptcha(siteKey: string, pageUrl: string): Promise<string> {
  const apiKey = process.env.TWOCAPTCHA_API_KEY;
  if (!apiKey) {
    throw new Error("TWOCAPTCHA_API_KEY not configured - cannot solve captcha");
  }

  // Submit captcha to 2captcha
  const submitUrl = `https://2captcha.com/in.php?key=${apiKey}&method=userrecaptcha&googlekey=${siteKey}&pageurl=${encodeURIComponent(pageUrl)}&json=1`;
  const submitRes = await fetch(submitUrl);
  const submitJson = await submitRes.json() as { status: number; request: string };
  
  if (submitJson.status !== 1) {
    throw new Error(`2captcha submit failed: ${submitJson.request}`);
  }
  
  const captchaId = submitJson.request;
  
  // Poll for result (max 120 seconds)
  for (let i = 0; i < 24; i++) {
    await new Promise(r => setTimeout(r, 5000)); // Wait 5 seconds
    
    const resultUrl = `https://2captcha.com/res.php?key=${apiKey}&action=get&id=${captchaId}&json=1`;
    const resultRes = await fetch(resultUrl);
    const resultJson = await resultRes.json() as { status: number; request: string };
    
    if (resultJson.status === 1) {
      return resultJson.request; // The solved captcha token
    }
    
    if (resultJson.request !== "CAPCHA_NOT_READY") {
      throw new Error(`2captcha solve failed: ${resultJson.request}`);
    }
  }
  
  throw new Error("2captcha timeout - captcha not solved in 120 seconds");
}

/**
 * Launch headless browser and login to ProFarmer
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
async function loginWithBrowser(): Promise<{ browser: any; page: any }> {
  const user = process.env.PROFARMER_USERNAME;
  const pass = process.env.PROFARMER_PASSWORD;

  if (!user || !pass) {
    throw new Error("PROFARMER_USERNAME and PROFARMER_PASSWORD environment variables required");
  }

  const { puppeteer, chromium } = await getPuppeteer();

  // Launch browser with Vercel-compatible chromium
  const browser = await puppeteer.launch({
    args: chromium.args,
    defaultViewport: { width: 1920, height: 1080 },
    executablePath: await chromium.executablePath(),
    headless: true,
  });

  const page = await browser.newPage();
  
  // Set realistic user agent
  await page.setUserAgent(
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
  );

  // Navigate to login page
  await page.goto(PROFARMER_LOGIN_URL, { waitUntil: "networkidle2", timeout: 30000 });
  
  // Check for reCAPTCHA
  const recaptchaFrame = await page.$('iframe[src*="recaptcha"]');
  const recaptchaSiteKey = await page.evaluate(() => {
    const el = document.querySelector('[data-sitekey]');
    return el?.getAttribute('data-sitekey') || null;
  });

  if (recaptchaFrame && recaptchaSiteKey) {
    console.log("reCAPTCHA detected, solving with 2captcha...");
    const captchaToken = await solveCaptcha(recaptchaSiteKey, PROFARMER_LOGIN_URL);
    
    // Inject the captcha token
    await page.evaluate((token: string) => {
      const textarea = document.querySelector('#g-recaptcha-response') as HTMLTextAreaElement;
      if (textarea) {
        textarea.value = token;
        textarea.style.display = 'block';
      }
    }, captchaToken);
  }

  // Fill in credentials
  await page.waitForSelector('input[name="email"], input[type="email"]', { timeout: 10000 });
  await page.type('input[name="email"], input[type="email"]', user, { delay: 50 });
  await page.type('input[name="password"], input[type="password"]', pass, { delay: 50 });
  
  // Click login button
  const loginButton = await page.$('button[type="submit"], input[type="submit"]');
  if (loginButton) {
    await Promise.all([
      page.waitForNavigation({ waitUntil: "networkidle2", timeout: 30000 }),
      loginButton.click(),
    ]);
  }

  // Verify login succeeded
  const currentUrl = page.url();
  if (currentUrl.includes("sign-in") || currentUrl.includes("login")) {
    await browser.close();
    throw new Error("ProFarmer login failed - still on login page after submit");
  }

  return { browser, page };
}

/**
 * Scrape articles from a report page using Puppeteer
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
async function scrapeReportArticles(
  page: any,
  reportUrl: string,
  reportSlug: string,
  specialists: string[],
  maxArticles: number = 10
): Promise<ArticleData[]> {
  await page.goto(reportUrl, { waitUntil: "networkidle2", timeout: 30000 });
  
  // Extract article data from the page
  const articles = await page.evaluate((slug: string, specs: string[], max: number) => {
    const results: Array<{
      url: string;
      title: string;
      content: string;
      pubDate: string;
      reportSlug: string;
      specialists: string[];
    }> = [];
    
    // Find article elements (common WordPress patterns)
    const articleEls = document.querySelectorAll('article, .post, .entry, [class*="article"]');
    
    for (const el of Array.from(articleEls).slice(0, max)) {
      const linkEl = el.querySelector('a[href*="profarmer.com"]') as HTMLAnchorElement | null;
      const titleEl = el.querySelector('h1, h2, h3, h4, .title, .entry-title');
      const dateEl = el.querySelector('time, .date, .published, [datetime]');
      const contentEl = el.querySelector('.content, .excerpt, .entry-content, p');
      
      if (!linkEl?.href || !titleEl?.textContent) continue;
      
      // Extract date
      let pubDate = '';
      if (dateEl) {
        pubDate = dateEl.getAttribute('datetime') || dateEl.textContent || '';
        const dateMatch = pubDate.match(/(\d{4})-(\d{2})-(\d{2})/);
        if (dateMatch) {
          pubDate = dateMatch[0];
        } else {
          const parsed = new Date(pubDate);
          if (!isNaN(parsed.getTime())) {
            pubDate = parsed.toISOString().split('T')[0];
          }
        }
      }
      
      if (!pubDate) {
        const urlDateMatch = linkEl.href.match(/\/(\d{4})\/(\d{2})\/(\d{2})\//);
        if (urlDateMatch) {
          pubDate = `${urlDateMatch[1]}-${urlDateMatch[2]}-${urlDateMatch[3]}`;
        } else {
          pubDate = new Date().toISOString().split('T')[0];
        }
      }
      
      results.push({
        url: linkEl.href,
        title: titleEl.textContent.trim(),
        content: contentEl?.textContent?.trim().slice(0, 2000) || '',
        pubDate,
        reportSlug: slug,
        specialists: specs,
      });
    }
    
    return results;
  }, reportSlug, specialists, maxArticles);

  // Fetch full content for each article
  for (const article of articles) {
    if (article.content.length < 500 && article.url) {
      try {
        await page.goto(article.url, { waitUntil: "networkidle2", timeout: 15000 });
        const fullContent = await page.evaluate(() => {
          const contentEl = document.querySelector('.entry-content, .article-content, .post-content, article');
          return contentEl?.textContent?.trim().slice(0, 5000) || '';
        });
        if (fullContent.length > article.content.length) {
          article.content = fullContent;
        }
        await new Promise(r => setTimeout(r, 500)); // Rate limit
      } catch {
        // Keep partial content
      }
    }
  }

  return articles;
}

export const profarmerDaily = inngest.createFunction(
  { id: "profarmer-daily", name: "ProFarmer Premium News Daily (Headless)", retries: 1 },
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
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    let browser: any = null;

    try {
      runId = await step.run("create-ingest-run", () =>
        createIngestRun(client, "profarmer-daily")
      );
      logger.info(`Started ProFarmer ingest run: ${runId}`);

      if (!process.env.PROFARMER_USERNAME || !process.env.PROFARMER_PASSWORD) {
        const msg = "PROFARMER_USERNAME and PROFARMER_PASSWORD environment variables required";
        await updateIngestRun(client, runId!, "blocked_credentials", attempted, inserted, skipped, quarantined, msg);
        return { status: "blocked_credentials", runId, error: msg };
      }

      // Step 1: Login with headless browser
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      let page: any;
      try {
        const result = await step.run("login-browser", async () => {
          return await loginWithBrowser();
        });
        browser = result.browser;
        page = result.page;
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        await updateIngestRun(client, runId!, "login_failed", attempted, inserted, skipped, quarantined, msg);
        return { status: "login_failed", runId, error: msg };
      }
      logger.info("Successfully logged into ProFarmer via headless browser");

      // Step 2: Scrape articles from each report
      for (const report of REPORTS) {
        const articles = await step.run(`scrape-${report.slug}`, async () => {
          return await scrapeReportArticles(
            page,
            report.url,
            report.slug,
            report.specialists,
            10
          );
        });

        logger.info(`Scraped ${articles.length} articles from ${report.name}`);

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
                  scrapeMethod: "puppeteer",
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
      if (browser) {
        await browser.close();
      }
      client.release();
    }
  }
);

/**
 * Manual backfill function - fetches last 6 months of articles
 */
export const profarmerBackfill = inngest.createFunction(
  { id: "profarmer-backfill", name: "ProFarmer 6-Month Backfill (Headless)", retries: 1 },
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
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    let browser: any = null;

    try {
      runId = await step.run("create-ingest-run", () =>
        createIngestRun(client, "profarmer-backfill")
      );
      logger.info(`Started ProFarmer backfill run: ${runId}`);

      if (!process.env.PROFARMER_USERNAME || !process.env.PROFARMER_PASSWORD) {
        const msg = "PROFARMER_USERNAME and PROFARMER_PASSWORD environment variables required";
        await updateIngestRun(client, runId!, "blocked_credentials", attempted, inserted, skipped, quarantined, msg);
        return { status: "blocked_credentials", runId, error: msg };
      }

      // Login with headless browser
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      let page: any;
      try {
        const result = await step.run("login-browser", async () => {
          return await loginWithBrowser();
        });
        browser = result.browser;
        page = result.page;
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        await updateIngestRun(client, runId!, "login_failed", attempted, inserted, skipped, quarantined, msg);
        return { status: "login_failed", runId, error: msg };
      }

      // For backfill, paginate through archives
      for (const report of REPORTS) {
        for (let pageNum = 1; pageNum <= 30; pageNum++) {
          const pageUrl = pageNum === 1 ? report.url : `${report.url}page/${pageNum}/`;
          
          const articles = await step.run(`backfill-${report.slug}-p${pageNum}`, async () => {
            try {
              return await scrapeReportArticles(page, pageUrl, report.slug, report.specialists, 20);
            } catch {
              return []; // End of pagination
            }
          });

          if (articles.length === 0) break; // No more pages

          logger.info(`Backfill: ${articles.length} articles from ${report.name} page ${pageNum}`);

          for (const article of articles) {
            attempted++;

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
                  JSON.stringify({ report: report.slug, backfill: true, page: pageNum }),
                  rowHash,
                  runId,
                ]
              );
              inserted++;
            } catch {
              quarantined++;
            }
          }

          // Rate limit between pages
          await new Promise((r) => setTimeout(r, 2000));
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
      if (browser) {
        await browser.close();
      }
      client.release();
    }
  }
);
