/**
 * ProFarmer Premium News Scraper (Stealth Headless Browser)
 *
 * Client pays $500/month for ProFarmer subscription.
 * Uses puppeteer-extra with stealth plugin to bypass bot detection.
 *
 * Scrapes 4 key reports:
 * - Daily Advice Monitor (trading signals)
 * - First Thing Today (morning outlook)
 * - Washington/Ag Policy (policy news)
 * - After the Bell (closing summaries)
 *
 * Requires env vars:
 *   PROFARMER_USERNAME - ProFarmer login email
 *   PROFARMER_PASSWORD - ProFarmer password
 */

import { inngest } from "./client";
import { createHash } from "crypto";
import { type PoolClient } from "pg";
import dbPool from "@/lib/db";

const pool = dbPool;

const PROFARMER_BASE = "https://www.profarmer.com";
const PROFARMER_LOGIN_URL = `${PROFARMER_BASE}/r/sign-in`;

const REPORTS = [
  {
    slug: "daily-advice-monitor",
    name: "Daily Advice Monitor",
    url: `${PROFARMER_BASE}/daily-advice-monitor/`,
    specialists: ["crush", "china", "energy"],
  },
  {
    slug: "first-thing-today",
    name: "First Thing Today",
    url: `${PROFARMER_BASE}/first-thing-today/`,
    specialists: ["crush", "china"],
  },
  {
    slug: "washington-ag-policy",
    name: "Washington/Ag Policy",
    url: `${PROFARMER_BASE}/washington-ag-policy/`,
    specialists: ["tariff", "biofuel", "trump_effect"],
  },
  {
    slug: "after-the-bell",
    name: "After the Bell",
    url: `${PROFARMER_BASE}/after-the-bell/`,
    specialists: ["crush", "volatility"],
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

interface ScrapedArticle {
  url: string;
  title: string;
  content: string;
  pubDate: string;
  reportSlug: string;
  specialists: string[];
}

// ArticleData interface used for type documentation only
type _ArticleData = ScrapedArticle & {
  summary: string;
  topics: string[];
  subjects: string[];
  isTrumpRelated: boolean;
  metaDescription: string;
}
// Suppress unused warning - kept for documentation
void (0 as unknown as _ArticleData);

/**
 * Extract topics from ProFarmer content
 */
function extractTopics(title: string, content: string, reportSlug: string): string[] {
  const topicKeywords = [
    "corn", "soybeans", "wheat", "cattle", "hogs", "cotton",
    "exports", "imports", "trade", "tariff", "china", "brazil",
    "weather", "drought", "flooding", "planting", "harvest",
    "usda", "wasde", "crop report", "acreage", "yield",
    "biofuel", "ethanol", "biodiesel", "rin", "epa",
    "prices", "futures", "basis", "spreads", "crush"
  ];
  const topics = new Set<string>();
  const searchText = `${title} ${content}`.toLowerCase();

  for (const topic of topicKeywords) {
    if (searchText.includes(topic)) {
      topics.add(topic);
    }
  }
  topics.add(reportSlug.replace(/-/g, ' '));
  return Array.from(topics).slice(0, 10);
}

/**
 * Extract subjects (entities mentioned)
 */
function extractSubjects(title: string, content: string): string[] {
  const subjectPatterns = [
    "china", "brazil", "argentina", "mexico", "canada",
    "usda", "epa", "congress", "white house", "trump",
    "cargill", "adm", "bunge", "dreyfus",
    "cme", "cbot", "kcbt"
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
 * Check if content is Trump-related
 */
function checkTrumpRelated(title: string, content: string): boolean {
  const trumpKeywords = ["trump", "tariff", "trade war", "maga", "executive order"];
  const searchText = `${title} ${content}`.toLowerCase();
  return trumpKeywords.some(kw => searchText.includes(kw));
}

/**
 * Launch stealth browser and login to ProFarmer
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
async function launchStealthBrowser(): Promise<{ browser: any; page: any }> {
  const user = process.env.PROFARMER_USERNAME;
  const pass = process.env.PROFARMER_PASSWORD;

  if (!user || !pass) {
    throw new Error("PROFARMER_USERNAME and PROFARMER_PASSWORD required");
  }

  // Dynamic imports for serverless
  const puppeteerExtra = await import("puppeteer-extra");
  const StealthPlugin = await import("puppeteer-extra-plugin-stealth");
  const chromium = await import("@sparticuz/chromium");

  // Add stealth plugin to bypass bot detection
  puppeteerExtra.default.use(StealthPlugin.default());

  const browser = await puppeteerExtra.default.launch({
    args: [
      ...chromium.default.args,
      '--no-sandbox',
      '--disable-setuid-sandbox',
      '--disable-dev-shm-usage',
      '--disable-accelerated-2d-canvas',
      '--disable-gpu',
      '--window-size=1920,1080',
    ],
    defaultViewport: { width: 1920, height: 1080 },
    executablePath: await chromium.default.executablePath(),
    headless: true,
    ignoreHTTPSErrors: true,
  });

  const page = await browser.newPage();

  // Set realistic viewport and user agent
  await page.setViewport({ width: 1920, height: 1080 });
  await page.setUserAgent(
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
  );

  // Set extra headers to look more human
  await page.setExtraHTTPHeaders({
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept-Encoding': 'gzip, deflate, br',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
  });

  // Navigate to login page
  console.log('Navigating to ProFarmer login...');
  await page.goto(PROFARMER_LOGIN_URL, { 
    waitUntil: 'networkidle2', 
    timeout: 60000 
  });

  // Random delay to appear human
  await new Promise(r => setTimeout(r, 1000 + Math.random() * 2000));

  // Click on the email field in the main form (not header search)
  console.log('Finding and focusing email field...');
  const clicked = await page.evaluate(() => {
    const forms = document.querySelectorAll('form');
    for (const form of forms) {
      const emailInput = form.querySelector('input[type="email"]') as HTMLInputElement;
      const passInput = form.querySelector('input[type="password"]');
      if (emailInput && passInput) {
        emailInput.focus();
        emailInput.click();
        return true;
      }
    }
    return false;
  });
  
  if (!clicked) {
    throw new Error('Could not find login form');
  }

  // Type credentials using keyboard (more reliable than setting .value)
  console.log('Typing credentials...');
  await page.keyboard.type(user, { delay: 80 });
  await new Promise(r => setTimeout(r, 300));
  
  await page.keyboard.press('Tab');
  await new Promise(r => setTimeout(r, 300));
  
  await page.keyboard.type(pass, { delay: 80 });
  await new Promise(r => setTimeout(r, 500));

  // Submit with Enter key
  console.log('Submitting login...');
  await page.keyboard.press('Enter');
  
  // Wait for navigation
  await new Promise(r => setTimeout(r, 8000));

  // Check if login succeeded
  const currentUrl = page.url();
  console.log('Current URL after login:', currentUrl);
  
  if (currentUrl.includes('sign-in') || currentUrl.includes('login')) {
    // Check for error messages
    const errorText = await page.evaluate(() => {
      const errorEl = document.querySelector('.error, .alert-danger, [class*="error"]');
      return errorEl?.textContent || null;
    });
    
    if (errorText) {
      throw new Error(`Login failed: ${errorText}`);
    }
    
    // Maybe there's a captcha
    const hasCaptcha = await page.evaluate(() => {
      return !!document.querySelector('iframe[src*="recaptcha"], [class*="captcha"], #captcha');
    });
    
    if (hasCaptcha) {
      throw new Error('Login blocked by CAPTCHA - need TWOCAPTCHA_API_KEY');
    }
    
    throw new Error('Login failed - still on login page');
  }

  console.log('Login successful!');
  return { browser, page };
}

/**
 * Scrape articles from a report page
 */
async function scrapeReportArticles(
  page: import('puppeteer-core').Page,
  reportUrl: string,
  reportSlug: string,
  specialists: string[],
  maxArticles: number = 15
): Promise<ScrapedArticle[]> {
  console.log(`Scraping ${reportUrl}...`);
  await page.goto(reportUrl, { waitUntil: 'networkidle2', timeout: 60000 });
  await new Promise(r => setTimeout(r, 1000 + Math.random() * 1000));

  // Extract articles
  const articles = await page.evaluate((slug: string, specs: string[], max: number) => {
    const results: ScrapedArticle[] = [];
    
    // Try multiple selectors for article containers
    const selectors = [
      'article',
      '.post',
      '.entry',
      '[class*="article"]',
      '.content-item',
      '.news-item',
      '.list-item',
    ];
    
    let articleEls: Element[] = [];
    for (const sel of selectors) {
      const els = document.querySelectorAll(sel);
      if (els.length > 0) {
        articleEls = Array.from(els);
        break;
      }
    }
    
    // If no containers found, try finding links directly
    if (articleEls.length === 0) {
      const links = document.querySelectorAll('a[href*="profarmer.com"]');
      articleEls = Array.from(links).map(l => l.parentElement!).filter(Boolean);
    }

    for (const el of articleEls.slice(0, max)) {
      try {
        // Find link
        const linkEl = el.querySelector('a[href*="profarmer.com"]') as HTMLAnchorElement;
        if (!linkEl?.href) continue;
        
        // Skip navigation/menu links
        if (linkEl.href.includes('/r/') || linkEl.href.includes('sign-in')) continue;
        
        // Find title
        const titleEl = el.querySelector('h1, h2, h3, h4, .title, .entry-title, a');
        const title = titleEl?.textContent?.trim();
        if (!title || title.length < 10) continue;
        
        // Find date
        let pubDate = '';
        const dateEl = el.querySelector('time, .date, .published, [datetime]');
        if (dateEl) {
          pubDate = dateEl.getAttribute('datetime') || dateEl.textContent || '';
        }
        
        // Extract date from URL if not found
        if (!pubDate) {
          const urlMatch = linkEl.href.match(/\/(\d{4})\/(\d{2})\/(\d{2})\//);
          if (urlMatch) {
            pubDate = `${urlMatch[1]}-${urlMatch[2]}-${urlMatch[3]}`;
          }
        }

        // Extract date from title if still not found
        if (!pubDate) {
          const titleDateMatch = title.match(
            /(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2},\s+\d{4}/i
          );
          if (titleDateMatch) {
            const parsed = new Date(titleDateMatch[0]);
            if (!isNaN(parsed.getTime())) {
              pubDate = parsed.toISOString().split('T')[0];
            }
          }
        }

        // Parse date
        if (pubDate) {
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
        
        if (!pubDate) continue;
        
        // Get excerpt/content
        const contentEl = el.querySelector('.excerpt, .content, .entry-content, p');
        const content = contentEl?.textContent?.trim().slice(0, 2000) || '';
        
        results.push({
          url: linkEl.href,
          title,
          content,
          pubDate,
          reportSlug: slug,
          specialists: specs,
        });
      } catch {
        continue;
      }
    }
    
    return results;
  }, reportSlug, specialists, maxArticles);

  // Fetch full content for articles with short excerpts
  for (const article of articles.slice(0, 10)) {
    if (article.content.length < 500) {
      try {
        await page.goto(article.url, { waitUntil: 'networkidle2', timeout: 30000 });
        await new Promise(r => setTimeout(r, 500));
        
        const fullContent = await page.evaluate(() => {
          const selectors = [
            '.entry-content',
            '.article-content', 
            '.post-content',
            '.content',
            'article',
            'main',
          ];
          
          for (const sel of selectors) {
            const el = document.querySelector(sel);
            if (el?.textContent && el.textContent.length > 200) {
              return el.textContent.trim().slice(0, 8000);
            }
          }
          return '';
        });
        
        if (fullContent.length > article.content.length) {
          article.content = fullContent;
        }
      } catch {
        // Keep partial content
      }
    }
  }

  return articles;
}

export const profarmerDaily = inngest.createFunction(
  { id: "profarmer-daily", name: "ProFarmer Premium Scraper (Stealth)", retries: 2 },
  { cron: "0 */4 * * *" }, // Every 4 hours
  async ({ step, logger }) => {
    const client = await pool.connect();
    let runId: string | null = null;
    let attempted = 0;
    let inserted = 0;
    let skipped = 0;
    let quarantined = 0;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    let browser: any = null;

    try {
      runId = await step.run("create-ingest-run", () => createIngestRun(client, "profarmer-daily"));
      logger.info(`ProFarmer ingest run: ${runId}`);

      // Launch stealth browser and login
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      let page: any;
      try {
        const result = await step.run("login", async () => {
          return await launchStealthBrowser();
        });
        browser = result.browser;
        page = result.page;
        logger.info("ProFarmer login successful");
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        logger.error(`ProFarmer login failed: ${msg}`);
        await updateIngestRun(client, runId!, "login_failed", 0, 0, 0, 0, msg);
        return { status: "login_failed", error: msg };
      }

      // Scrape each report
      for (const report of REPORTS) {
        try {
          const articles = await step.run(`scrape-${report.slug}`, async () => {
            return await scrapeReportArticles(page, report.url, report.slug, report.specialists, 15);
          });

          logger.info(`${report.name}: ${articles.length} articles found`);

          for (const article of articles) {
            attempted++;
            const rowHash = computeRowHash(article.url, article.title, article.pubDate);

            const exists = await client.query(
              `SELECT 1 FROM alt.profarmer_news WHERE row_hash = $1 LIMIT 1`,
              [rowHash]
            );

            if (exists.rows.length > 0) {
              skipped++;
              continue;
            }

            // Compute metadata
            const topics = extractTopics(article.title, article.content, report.slug);
            const subjects = extractSubjects(article.title, article.content);
            const isTrumpRelated = checkTrumpRelated(article.title, article.content);
            const summary = article.content.slice(0, 500);
            const metaDescription = article.content.slice(0, 300);

            try {
              await client.query(
                `INSERT INTO alt.profarmer_news (
                   event_date, section, headline, content, url,
                   specialist_tags, summary, topics, subjects,
                   is_trump_related, meta_description, raw_payload, row_hash
                 ) VALUES ($1::date, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12::jsonb, $13)`,
                [
                  article.pubDate,
                  report.slug,
                  article.title,
                  article.content,
                  article.url,
                  article.specialists,
                  summary,
                  topics,
                  subjects,
                  isTrumpRelated,
                  metaDescription,
                  JSON.stringify({ report: report.name, slug: report.slug }),
                  rowHash,
                ]
              );
              inserted++;
              logger.info(`Inserted: ${article.title.slice(0, 50)}...`);
            } catch (err) {
              quarantined++;
              logger.warn(`Insert failed: ${err}`);
            }
          }
        } catch (err) {
          logger.warn(`Report ${report.name} failed: ${err}`);
        }
      }

      await updateIngestRun(client, runId!, "success", attempted, inserted, skipped, quarantined);
      
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
      if (browser) await browser.close();
      client.release();
    }
  }
);

export const profarmerBackfill = inngest.createFunction(
  { id: "profarmer-backfill", name: "ProFarmer 6-Month Backfill", retries: 1 },
  { event: "profarmer/backfill" },
  async ({ step, logger }) => {
    const client = await pool.connect();
    let runId: string | null = null;
    let attempted = 0;
    let inserted = 0;
    let skipped = 0;
    let quarantined = 0;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    let browser: any = null;

    try {
      runId = await step.run("create-run", () => createIngestRun(client, "profarmer-backfill"));

      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      let page: any;
      const result = await step.run("login", () => launchStealthBrowser());
      browser = result.browser;
      page = result.page;

      for (const report of REPORTS) {
        for (let pageNum = 1; pageNum <= 50; pageNum++) {
          const pageUrl = pageNum === 1 ? report.url : `${report.url}page/${pageNum}/`;
          
          try {
            const articles = await step.run(`${report.slug}-p${pageNum}`, async () => {
              return await scrapeReportArticles(page, pageUrl, report.slug, report.specialists, 20);
            });

            if (articles.length === 0) break;
            logger.info(`${report.name} p${pageNum}: ${articles.length} articles`);

            for (const article of articles) {
              attempted++;
              const rowHash = computeRowHash(article.url, article.title, article.pubDate);

              const exists = await client.query(
                `SELECT 1 FROM alt.profarmer_news WHERE row_hash = $1 LIMIT 1`,
                [rowHash]
              );

              if (exists.rows.length > 0) {
                skipped++;
                continue;
              }

              // Compute metadata
              const topics = extractTopics(article.title, article.content, report.slug);
              const subjects = extractSubjects(article.title, article.content);
              const isTrumpRelated = checkTrumpRelated(article.title, article.content);
              const summary = article.content.slice(0, 500);
              const metaDescription = article.content.slice(0, 300);

              try {
                await client.query(
                  `INSERT INTO alt.profarmer_news (
                     event_date, section, headline, content, url,
                     specialist_tags, summary, topics, subjects,
                     is_trump_related, meta_description, raw_payload, row_hash
                   ) VALUES ($1::date, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12::jsonb, $13)`,
                  [
                    article.pubDate,
                    report.slug,
                    article.title,
                    article.content,
                    article.url,
                    article.specialists,
                    summary,
                    topics,
                    subjects,
                    isTrumpRelated,
                    metaDescription,
                    JSON.stringify({ report: report.slug, backfill: true, page: pageNum }),
                    rowHash,
                  ]
                );
                inserted++;
              } catch {
                quarantined++;
              }
            }

            await new Promise(r => setTimeout(r, 2000));
          } catch {
            break;
          }
        }
      }

      await updateIngestRun(client, runId!, "success", attempted, inserted, skipped, quarantined);
      return { status: "success", attempted, inserted, skipped, quarantined };
    } catch (error) {
      const msg = error instanceof Error ? error.message : String(error);
      if (runId) await updateIngestRun(client, runId, "failed", attempted, inserted, skipped, quarantined, msg);
      throw error;
    } finally {
      if (browser) await browser.close();
      client.release();
    }
  }
);
