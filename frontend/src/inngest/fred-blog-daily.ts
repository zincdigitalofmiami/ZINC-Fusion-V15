/**
 * FRED Blog Scraper
 *
 * Scrapes FRED Blog (fredblog.stlouisfed.org) articles and stores in alt.econ_news
 * Federal Reserve economic research and analysis.
 * Runs every 4 hours to capture new posts.
 *
 * @author Claude (ZINC-FUSION-V15)
 * @date 2026-01-31
 */

import { inngest } from "./client";
import { createHash } from "crypto";
import { Pool, type PoolClient } from "pg";

const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
  ssl: { rejectUnauthorized: false },
});

// Base URL kept for documentation - feed URL used for scraping
void "https://fredblog.stlouisfed.org/";
const FRED_BLOG_FEED = "https://fredblog.stlouisfed.org/feed/";

interface FredBlogArticle {
  articleId: string;
  title: string;
  content: string;
  summary: string;
  metaDescription: string;
  url: string;
  author: string;
  eventDate: string | null;
  publishedAt: string | null;
  categories: string[];
  topics: string[];
  subjects: string[];
  isTrumpRelated: boolean;
}

function mapCategoriesToSpecialists(categories: string[]): string[] {
  const mapping: Record<string, string[]> = {
    "monetary policy": ["fed"],
    "interest rates": ["fed"],
    "inflation": ["fed", "energy"],
    "employment": ["fed"],
    "gdp": ["fed", "crush"],
    "trade": ["tariff", "china"],
    "china": ["china", "tariff"],
    "oil": ["energy", "biofuel"],
    "energy": ["energy", "biofuel"],
    "agriculture": ["crush", "biofuel"],
    "commodities": ["crush", "energy"],
    "exchange rates": ["fx"],
    "currency": ["fx"],
    "financial markets": ["volatility", "fed"],
    "recession": ["volatility", "fed"],
  };

  const tags = new Set<string>();
  for (const cat of categories) {
    const lower = cat.toLowerCase();
    for (const [keyword, specialists] of Object.entries(mapping)) {
      if (lower.includes(keyword)) {
        specialists.forEach(s => tags.add(s));
      }
    }
  }

  // Default tags if none matched
  if (tags.size === 0) {
    tags.add("fed");
  }

  return Array.from(tags);
}

/**
 * Extract topics from categories (economic topics)
 */
function extractTopics(categories: string[], title: string, content: string): string[] {
  const topicKeywords = [
    "inflation", "employment", "gdp", "trade", "monetary policy",
    "interest rates", "recession", "housing", "manufacturing",
    "consumer spending", "labor market", "fiscal policy", "debt",
    "banking", "credit", "stock market", "bonds", "commodities",
    "oil", "energy", "agriculture", "technology", "healthcare"
  ];

  const topics = new Set<string>();
  const searchText = `${title} ${categories.join(' ')} ${content}`.toLowerCase();

  for (const topic of topicKeywords) {
    if (searchText.includes(topic)) {
      topics.add(topic);
    }
  }

  // Also add categories as topics
  categories.forEach(c => topics.add(c.toLowerCase()));

  return Array.from(topics).slice(0, 10); // Limit to 10 topics
}

/**
 * Extract subjects (entities/regions mentioned)
 */
function extractSubjects(title: string, content: string, categories: string[]): string[] {
  const subjectPatterns = [
    "united states", "china", "europe", "eu", "japan", "brazil",
    "federal reserve", "fed", "treasury", "congress", "white house",
    "opec", "imf", "world bank", "ecb", "boj",
    "s&p 500", "dow jones", "nasdaq", "nyse",
    "oil", "gold", "copper", "corn", "soybeans", "wheat"
  ];

  const subjects = new Set<string>();
  const searchText = `${title} ${content} ${categories.join(' ')}`.toLowerCase();

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
  const trumpKeywords = [
    "trump", "tariff", "trade war", "maga", "america first",
    "executive order", "trump administration"
  ];
  const searchText = `${title} ${content}`.toLowerCase();
  return trumpKeywords.some(kw => searchText.includes(kw));
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

/**
 * Parse RSS feed to extract articles
 */
async function fetchFredBlogFeed(): Promise<FredBlogArticle[]> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 30000);

  try {
    const response = await fetch(FRED_BLOG_FEED, {
      signal: controller.signal,
      headers: {
        'User-Agent': 'Mozilla/5.0 (compatible; ZincFusion/1.0)',
        'Accept': 'application/rss+xml, application/xml, text/xml',
      },
    });

    if (!response.ok) {
      throw new Error(`FRED Blog feed error: ${response.status}`);
    }

    const xml = await response.text();
    const articles: FredBlogArticle[] = [];

    // Simple RSS parsing (items between <item> tags)
    const itemRegex = /<item>([\s\S]*?)<\/item>/g;
    let match;

    while ((match = itemRegex.exec(xml)) !== null) {
      const itemXml = match[1];

      const getTag = (tag: string): string => {
        const tagMatch = itemXml.match(new RegExp(`<${tag}[^>]*>([\\s\\S]*?)<\\/${tag}>`));
        if (tagMatch) {
          return tagMatch[1]
            .replace(/<!\[CDATA\[/g, '')
            .replace(/\]\]>/g, '')
            .trim();
        }
        return '';
      };

      const title = getTag('title');
      const link = getTag('link');
      const pubDate = getTag('pubDate');
      const description = getTag('description');
      const contentEncoded = getTag('content:encoded') || getTag('content');
      const creator = getTag('dc:creator') || getTag('author');

      // Extract categories
      const categoryMatches = itemXml.match(/<category[^>]*>([^<]+)<\/category>/g) || [];
      const categories = categoryMatches.map(c =>
        c.replace(/<\/?category[^>]*>/g, '').trim()
      );

      if (title && link) {
        // Generate article ID from URL
        const urlParts = link.split('/').filter(Boolean);
        const articleId = urlParts[urlParts.length - 1] || createHash('md5').update(link).digest('hex').slice(0, 16);

        // Parse date/time from RSS
        let eventDate: string | null = null;
        let publishedAt: string | null = null;
        if (pubDate) {
          const parsed = new Date(pubDate);
          if (!isNaN(parsed.getTime())) {
            publishedAt = parsed.toISOString();
            eventDate = publishedAt.split('T')[0];
          }
        }

        const fullContent = contentEncoded || description;
        const summary = description.slice(0, 500);
        const metaDescription = description.slice(0, 300);
        const topics = extractTopics(categories, title, fullContent);
        const subjects = extractSubjects(title, fullContent, categories);
        const isTrumpRelated = checkTrumpRelated(title, fullContent);

        articles.push({
          articleId,
          title,
          content: fullContent,
          summary,
          metaDescription,
          url: link,
          author: creator,
          eventDate,
          publishedAt,
          categories,
          topics,
          subjects,
          isTrumpRelated,
        });
      }
    }

    return articles;
  } finally {
    clearTimeout(timeout);
  }
}

export const fredBlogDaily = inngest.createFunction(
  { id: "fred-blog-daily", name: "FRED Blog Scraper", retries: 3 },
  { cron: "0 */4 * * *" }, // Every 4 hours
  async ({ step, logger }) => {
    const client = await pool.connect();
    let runId: string | null = null;
    let attempted = 0;
    let inserted = 0;
    let skipped = 0;
    let quarantined = 0;

    try {
      runId = await step.run("create-ingest-run", () => createIngestRun(client, "fred-blog-daily"));
      logger.info(`FRED Blog ingest run: ${runId}`);

      const articles = await step.run("fetch-feed", async () => {
        return await fetchFredBlogFeed();
      });

      logger.info(`FRED Blog: ${articles.length} articles found in feed`);

      for (const article of articles) {
        attempted++;
        if (!article.eventDate) {
          quarantined++;
          logger.warn(`Missing event_date for article: ${article.title}`);
          continue;
        }

        // Check for duplicate
        const exists = await client.query(
          `SELECT 1 FROM alt.econ_news WHERE url = $1 LIMIT 1`,
          [article.url]
        );

        if (exists.rows.length > 0) {
          skipped++;
          continue;
        }

        const specialistTags = mapCategoriesToSpecialists(article.categories);

        try {
          await client.query(
            `INSERT INTO alt.econ_news (
               article_id, event_date, published_at, headline, summary, content,
               source, url, author, specialist_tags, raw_payload,
               topics, subjects, meta_description
             ) VALUES ($1, $2::date, $3::timestamptz, $4, $5, $6, $7, $8, $9, $10, $11::jsonb, $12, $13, $14)`,
            [
              article.articleId,
              article.eventDate,
              article.publishedAt,
              article.title,
              article.summary,
              article.content,
              "fred_blog",
              article.url,
              article.author,
              specialistTags,
              JSON.stringify({ 
                categories: article.categories,
                summary: article.summary
              }),
              article.topics,
              article.subjects,
              article.metaDescription,
            ]
          );
          inserted++;
          logger.info(`Inserted: ${article.title.slice(0, 50)}...`);
        } catch (err) {
          quarantined++;
          logger.warn(`Insert failed for ${article.title}: ${err}`);
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
      logger.error(`FRED Blog ingest failed: ${msg}`);
      throw error;
    } finally {
      client.release();
    }
  }
);
