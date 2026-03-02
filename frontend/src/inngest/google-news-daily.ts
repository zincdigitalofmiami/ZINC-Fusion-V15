/**
 * Google News RSS Daily — Fetches headlines for all 11 specialist buckets.
 *
 * Source: Google News RSS (free, no API key, ~20-100 articles per query).
 * URL: https://news.google.com/rss/search?q={encoded_query}&hl=en-US&gl=US&ceid=US:en
 *
 * This fills the news gap left by ProFarmer being dead since Feb 14, 2026.
 * Articles are tagged with specialist_tags and inserted into alt.policy_news_event
 * for cross-specialist routing via the Universal News Loader.
 *
 * Schedule: Daily at 13:00 UTC (8 AM CT, after morning headlines settle).
 */

import { inngest, DB_CONCURRENCY } from "./client";
import dbPool from "@/lib/db";
import {
	hashFields,
	createIngestRun,
	finalizeIngestRun,
	failIngestRun,
} from "./utils";

const pool = dbPool;
const JOB_NAME = "google-news-daily";
const SOURCE_NAME = "google_news";
const USER_AGENT = "Mozilla/5.0 (ZINC-Fusion/1.0)";
const GOOGLE_NEWS_RSS_BASE = "https://news.google.com/rss/search";

/** Search queries per specialist bucket (Big-11). */
const SPECIALIST_QUERIES: Record<string, string[]> = {
	crush: [
		"soybean crush margin",
		"soybean oil processing plant",
		"soy crush capacity expansion",
	],
	china: [
		"China soybean imports",
		"China soybean oil trade",
		"China US trade tariff agriculture",
	],
	substitutes: [
		"palm oil price global",
		"canola rapeseed oil market",
		"vegetable oil substitute demand",
	],
	fx: [
		"US dollar index DXY currency",
		"emerging market currency devaluation",
		"Brazilian real Chinese yuan exchange rate",
	],
	fed: [
		"Federal Reserve interest rate decision",
		"FOMC meeting minutes monetary policy",
		"US inflation economic outlook Fed",
	],
	tariff: [
		"US tariff trade war agriculture",
		"agricultural trade policy sanctions",
		"Trump tariff soybean oil",
	],
	energy: [
		"crude oil price OPEC supply",
		"renewable fuel standard mandate",
		"energy commodities market outlook",
	],
	biofuel: [
		"biodiesel renewable diesel production",
		"RIN credit price EPA biofuel",
		"sustainable aviation fuel SAF soybean oil",
	],
	palm: [
		"palm oil production Malaysia Indonesia",
		"MPOB palm oil stocks exports",
		"palm oil export ban Indonesia",
	],
	volatility: [
		"commodity market volatility VIX",
		"soybean oil futures volatility",
		"agricultural commodity risk",
	],
	trump_effect: [
		"Trump executive order trade",
		"Trump tariff policy 2026",
		"Trump administration trade agriculture energy",
	],
};

/** Cross-tag keywords for multi-specialist routing. */
const CROSS_TAG_KEYWORDS: Record<string, string[]> = {
	crush: ["crush", "soybean oil", "soy oil", "processing", "soy meal"],
	china: ["china", "chinese", "beijing", "xi jinping"],
	substitutes: ["palm oil", "canola", "rapeseed", "sunflower", "olive oil"],
	fx: ["dollar", "currency", "forex", "exchange rate", "yuan", "real"],
	fed: ["federal reserve", "fomc", "interest rate", "monetary policy", "inflation"],
	tariff: ["tariff", "trade war", "sanctions", "import duty", "trade policy"],
	energy: ["crude oil", "opec", "petroleum", "natural gas", "energy"],
	biofuel: ["biodiesel", "renewable diesel", "rin", "biofuel", "ethanol", "saf"],
	palm: ["palm oil", "mpob", "indonesia", "malaysia palm"],
	volatility: ["volatility", "vix", "risk", "market crash", "sell-off"],
	trump_effect: ["trump", "executive order", "presidential", "white house"],
};

interface RssArticle {
	headline: string;
	url: string | null;
	publishedAt: string; // ISO string
	eventDate: string; // YYYY-MM-DD
	pubSource: string;
}

interface PreparedRow {
	eventDate: string;
	publishedAt: string;
	headline: string;
	url: string | null;
	source: string;
	specialistTags: string[];
	rowHash: string;
}

/**
 * Parse Google News RSS XML using simple regex (no XML parser needed in edge runtime).
 */
function parseRssXml(xml: string): RssArticle[] {
	const articles: RssArticle[] = [];
	const itemRegex = /<item>([\s\S]*?)<\/item>/g;
	let match: RegExpExecArray | null;

	while ((match = itemRegex.exec(xml)) !== null) {
		const item = match[1];

		const titleMatch = /<title>([\s\S]*?)<\/title>/.exec(item);
		const linkMatch = /<link>([\s\S]*?)<\/link>/.exec(item);
		const pubDateMatch = /<pubDate>([\s\S]*?)<\/pubDate>/.exec(item);
		const sourceMatch = /<source[^>]*>([\s\S]*?)<\/source>/.exec(item);

		if (!titleMatch || !titleMatch[1].trim()) continue;

		const headline = titleMatch[1].trim()
			.replace(/&amp;/g, "&")
			.replace(/&lt;/g, "<")
			.replace(/&gt;/g, ">")
			.replace(/&quot;/g, '"')
			.replace(/&#39;/g, "'");

		const url = linkMatch?.[1]?.trim() || null;
		const pubSource = sourceMatch?.[1]?.trim() || "Google News";

		// Parse RFC 2822 date: "Sat, 01 Mar 2026 14:30:00 GMT"
		let publishedAt: string;
		let eventDate: string;
		try {
			if (pubDateMatch?.[1]) {
				const d = new Date(pubDateMatch[1].trim());
				if (!isNaN(d.getTime())) {
					publishedAt = d.toISOString();
					eventDate = publishedAt.slice(0, 10);
				} else {
					throw new Error("Invalid date");
				}
			} else {
				throw new Error("No date");
			}
		} catch {
			const now = new Date();
			publishedAt = now.toISOString();
			eventDate = publishedAt.slice(0, 10);
		}

		articles.push({ headline, url, publishedAt, eventDate, pubSource });
	}

	return articles;
}

/**
 * Compute specialist tags for an article based on headline content.
 */
function computeSpecialistTags(headline: string, primaryBucket: string): string[] {
	const tags = new Set<string>([primaryBucket]);
	const headlineLower = headline.toLowerCase();

	for (const [bucket, keywords] of Object.entries(CROSS_TAG_KEYWORDS)) {
		if (bucket === primaryBucket) continue;
		for (const kw of keywords) {
			if (headlineLower.includes(kw)) {
				tags.add(bucket);
				break;
			}
		}
	}

	return Array.from(tags).sort();
}

async function fetchRss(query: string): Promise<RssArticle[]> {
	const url = `${GOOGLE_NEWS_RSS_BASE}?q=${encodeURIComponent(query)}&hl=en-US&gl=US&ceid=US:en`;
	try {
		const res = await fetch(url, {
			headers: { "User-Agent": USER_AGENT },
			signal: AbortSignal.timeout(15000),
		});
		if (!res.ok) return [];
		const xml = await res.text();
		return parseRssXml(xml);
	} catch {
		return [];
	}
}

export const googleNewsDaily = inngest.createFunction(
	{
		id: "google-news-daily",
		name: "Google News Daily (11 Specialists)",
		retries: 2,
		concurrency: [DB_CONCURRENCY],
	},
	{ cron: "0 13 * * *" }, // Daily at 13:00 UTC (8 AM CT)
	async ({ step, logger }) => {
		const runId = await step.run("create-ingest-run", async () => {
			return createIngestRun(pool, JOB_NAME);
		});

		try {
			const buckets = Object.keys(SPECIALIST_QUERIES);
			let totalInserted = 0;
			let totalSkipped = 0;
			let totalAttempted = 0;

			for (const bucket of buckets) {
				const queries = SPECIALIST_QUERIES[bucket];

				// Fetch all queries for this bucket
				const articles = await step.run(`fetch-${bucket}`, async () => {
					const allArticles: RssArticle[] = [];
					for (const query of queries) {
						const raw = await fetchRss(query);
						allArticles.push(...raw);
						// Rate limit: small delay between requests
						await new Promise((r) => setTimeout(r, 500));
					}
					logger.info(`${bucket}: fetched ${allArticles.length} articles from ${queries.length} queries`);
					return allArticles;
				});

				if (articles.length === 0) continue;

				// Prepare rows with dedup within bucket
				const seenHashes = new Set<string>();
				const preparedRows: PreparedRow[] = [];

				for (const article of articles) {
					const tags = computeSpecialistTags(article.headline, bucket);
					const rowHash = hashFields(
						article.headline,
						article.eventDate,
						article.pubSource,
					);

					if (seenHashes.has(rowHash)) continue;
					seenHashes.add(rowHash);

					preparedRows.push({
						eventDate: article.eventDate,
						publishedAt: article.publishedAt,
						headline: article.headline,
						url: article.url,
						source: `${SOURCE_NAME}/${article.pubSource}`,
						specialistTags: tags,
						rowHash,
					});
				}

				totalAttempted += preparedRows.length;

				// Insert with dedup against DB
				const result = await step.run(`insert-${bucket}`, async () => {
					const client = await pool.connect();
					let inserted = 0;
					let skipped = 0;
					try {
						// Batch insert
						const batchSize = 100;
						for (let i = 0; i < preparedRows.length; i += batchSize) {
							const batch = preparedRows.slice(i, i + batchSize);
							const values: string[] = [];
							const params: (string | string[] | null)[] = [];

							for (let r = 0; r < batch.length; r++) {
								const base = r * 7;
								values.push(
									`($${base + 1}, $${base + 2}::timestamptz, $${base + 3}, $${base + 4}, $${base + 5}, $${base + 6}::text[], $${base + 7})`,
								);
								params.push(
									batch[r].eventDate,
									batch[r].publishedAt,
									batch[r].headline,
									batch[r].url,
									batch[r].source,
									batch[r].specialistTags,
									batch[r].rowHash,
								);
							}

							const res = await client.query(
								`INSERT INTO alt.policy_news_event
								 (event_date, published_at, headline, url, source, specialist_tags, row_hash)
								 VALUES ${values.join(",")}
								 ON CONFLICT (row_hash) WHERE row_hash IS NOT NULL DO NOTHING`,
								params,
							);
							inserted += res.rowCount ?? 0;
							skipped += batch.length - (res.rowCount ?? 0);
						}
					} finally {
						client.release();
					}
					return { inserted, skipped };
				});

				totalInserted += result.inserted;
				totalSkipped += result.skipped;
				logger.info(`${bucket}: ${result.inserted} new, ${result.skipped} dupes`);
			}

			await step.run("finalize-ingest-run", async () => {
				await finalizeIngestRun(pool, runId, {
					status: "success",
					rowsAttempted: totalAttempted,
					rowsInserted: totalInserted,
					rowsSkipped: totalSkipped,
				});
			});

			logger.info(`Google News Daily: ${totalInserted} inserted, ${totalSkipped} skipped across ${buckets.length} buckets`);
			return { status: "success", inserted: totalInserted, skipped: totalSkipped };
		} catch (err) {
			await step.run("fail-ingest-run", async () => {
				await failIngestRun(pool, runId, err);
			});
			throw err;
		}
	},
);
