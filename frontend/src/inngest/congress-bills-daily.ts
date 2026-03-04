/**
 * Congress.gov Bills & Legislation Tracker
 *
 * INGESTION CONTRACT:
 * - Logs each run in ops.ingest_run
 * - Computes row_hash for idempotency
 * - Assigns specialist_tags based on bill content keywords
 * - Append-only inserts (no upserts)
 *
 * SOURCE: https://api.congress.gov/v3/
 * - Requires API key (CONGRESS_API_KEY env var)
 * - Free tier: 1,000 requests/hour
 * - Tracks bills with agriculture, trade, biofuel, energy keywords
 *
 * Specialist routing:
 * - tariff, trade, section 301/232 → tariff
 * - biofuel, RFS, RIN, renewable fuel, 45Z → biofuel
 * - soybean, agriculture, farm bill, USDA → crush
 * - china, trade agreement → china, tariff
 * - executive order, presidential → trump_effect
 * - fed, monetary, interest rate → fed
 *
 * @author Claude (ZINC-FUSION-V15)
 * @version 1.0.0
 * @date 2026-02-26
 */

import { inngest, DB_CONCURRENCY } from "./client";
import { createHash } from "crypto";
import { getIngestPool } from "@/lib/db";

const pool = getIngestPool();

// Keywords to search for bills relevant to ZL soybean oil forecasting
const BILL_SEARCH_QUERIES = [
  "soybean",
  "biofuel",
  "renewable fuel",
  "tariff",
  "trade",
  "agriculture",
  "USDA",
  "farm bill",
  "ethanol",
  "biodiesel",
  "RFS",
  "45Z",
  "LCFS",
  "carbon",
  "EPA",
];

interface TagRule {
  pattern: RegExp;
  tags: string[];
}

const TAG_RULES: TagRule[] = [
  { pattern: /\b(tariff|section\s*301|section\s*232|trade\s*war|import\s*dut)/i, tags: ["tariff"] },
  { pattern: /\b(trade\s*deal|trade\s*agreement|usmca|nafta)/i, tags: ["tariff", "trump_effect"] },
  { pattern: /\b(biofuel|biodiesel|renewable\s*fuel|rfs|rin\b|ethanol|45z|clean\s*fuel)/i, tags: ["biofuel"] },
  { pattern: /\b(soybean|soy\s*oil|crush|oilseed|canola)/i, tags: ["crush"] },
  { pattern: /\b(china|prc|beijing|chinese\s*import)/i, tags: ["china", "tariff"] },
  { pattern: /\b(executive\s*order|presidential|doge|government\s*efficiency)/i, tags: ["trump_effect"] },
  { pattern: /\b(epa|environment|emission|carbon|lcfs|clean\s*air)/i, tags: ["biofuel"] },
  { pattern: /\b(fed\b|federal\s*reserve|monetary|interest\s*rate)/i, tags: ["fed"] },
  { pattern: /\b(palm\s*oil|deforestation|import\s*ban)/i, tags: ["palm"] },
  { pattern: /\b(farm\s*bill|usda|agriculture|commodity\s*program)/i, tags: ["crush"] },
  { pattern: /\b(energy|petroleum|crude\s*oil|natural\s*gas)/i, tags: ["energy"] },
  { pattern: /\b(immigration|border|visa|h-1b)/i, tags: ["trump_effect"] },
];

function classifyBill(title: string, summary: string): string[] {
  const text = `${title} ${summary}`.toLowerCase();
  const tags = new Set<string>();

  for (const rule of TAG_RULES) {
    if (rule.pattern.test(text)) {
      for (const tag of rule.tags) tags.add(tag);
    }
  }

  // Default to tariff if trade-related but no specific match
  if (tags.size === 0 && /\b(trade|export|import|customs)\b/i.test(text)) {
    tags.add("tariff");
  }

  return Array.from(tags);
}

function computeRowHash(billNumber: string, congress: string): string {
  return createHash("sha256")
    .update(`congress.gov|${congress}|${billNumber}`)
    .digest("hex");
}

interface CongressBill {
  number: string;
  title: string;
  type: string;
  congress: number;
  url: string;
  introducedDate: string;
  latestAction?: { text: string; actionDate: string };
  policyArea?: { name: string };
  sponsors?: Array<{ fullName: string; party: string; state: string }>;
}

export const congressBillsDaily = inngest.createFunction(
  {
    id: "congress-bills-daily",
    name: "Congress.gov Bills Tracker",
    retries: 3,
    concurrency: [DB_CONCURRENCY, { limit: 1 }],
  },
  { cron: "0 14 * * *" }, // Daily at 14:00 UTC (9 AM ET, after Congress session starts)
  async ({ step, logger }) => {
    const apiKey = process.env.CONGRESS_API_KEY;
    if (!apiKey) {
      logger.warn("CONGRESS_API_KEY not set — skipping congress bills ingestion");
      return { status: "skipped", reason: "no_api_key" };
    }

    // ── Step 1: create ingest run ──
    const runId = await step.run("create-ingest-run", async () => {
      const client = await pool.connect();
      try {
        const result = await client.query(
          `INSERT INTO ops.ingest_run (job_name, status, started_at) VALUES ($1, 'running', NOW()) RETURNING id`,
          ["congress-bills-daily"],
        );
        return result.rows[0].id as string;
      } finally {
        client.release();
      }
    });
    logger.info(`Congress bills ingest run: ${runId}`);

    // ── Step 2: fetch recent bills from Congress API ──
    const allBills = await step.run("fetch-bills", async () => {
      const bills: CongressBill[] = [];
      const seenNumbers = new Set<string>();

      // Search for bills updated in the last 7 days across relevant queries
      const fromDate = new Date();
      fromDate.setDate(fromDate.getDate() - 7);
      const fromDateStr = fromDate.toISOString().split("T")[0];

      for (const query of BILL_SEARCH_QUERIES.slice(0, 8)) { // Limit queries to avoid rate limits
        const url = `https://api.congress.gov/v3/bill?format=json&limit=25&fromDateTime=${fromDateStr}T00:00:00Z&sort=updateDate+desc&api_key=${apiKey}`;

        try {
          const controller = new AbortController();
          const timeout = setTimeout(() => controller.abort(), 15000);
          const response = await fetch(url, {
            headers: { Accept: "application/json" },
            signal: controller.signal,
          });
          clearTimeout(timeout);

          if (!response.ok) {
            logger.warn(`Congress API error for query "${query}": ${response.status}`);
            continue;
          }

          const data = (await response.json()) as {
            bills?: Array<{
              number: number;
              title: string;
              type: string;
              congress: number;
              url: string;
              introducedDate: string;
              latestAction?: { text: string; actionDate: string };
              policyArea?: { name: string };
            }>;
          };

          for (const bill of data.bills || []) {
            const billKey = `${bill.type}${bill.number}-${bill.congress}`;
            if (seenNumbers.has(billKey)) continue;

            // Filter: only keep bills relevant to our domain
            const titleLower = (bill.title || "").toLowerCase();
            const policyArea = (bill.policyArea?.name || "").toLowerCase();
            const actionText = (bill.latestAction?.text || "").toLowerCase();
            const combined = `${titleLower} ${policyArea} ${actionText}`;

            const isRelevant = BILL_SEARCH_QUERIES.some((q) =>
              combined.includes(q.toLowerCase()),
            );

            if (!isRelevant) continue;

            seenNumbers.add(billKey);
            bills.push({
              number: String(bill.number),
              title: bill.title,
              type: bill.type,
              congress: bill.congress,
              url: bill.url,
              introducedDate: bill.introducedDate,
              latestAction: bill.latestAction,
              policyArea: bill.policyArea,
            });
          }

          // Rate limit: 400ms between requests
          await new Promise((r) => setTimeout(r, 400));
        } catch (err) {
          logger.warn(`Congress API fetch error for "${query}": ${err}`);
        }
      }

      return bills;
    });

    logger.info(`Found ${allBills.length} relevant bills`);

    // ── Step 3: insert bills into alt.legislation_1d ──
    let rowsAttempted = 0;
    let rowsInserted = 0;
    let rowsSkipped = 0;
    let rowsQuarantined = 0;

    if (allBills.length > 0) {
      const result = await step.run("insert-bills", async () => {
        let attempted = 0, inserted = 0, skipped = 0, quarantined = 0;
        const client = await pool.connect();
        try {
          for (const bill of allBills) {
            attempted++;
            const rowHash = computeRowHash(
              `${bill.type}${bill.number}`,
              String(bill.congress),
            );

            const exists = await client.query(
              `SELECT 1 FROM alt.legislation_1d WHERE row_hash = $1 LIMIT 1`,
              [rowHash],
            );

            if (exists.rows.length > 0) {
              skipped++;
              continue;
            }

            const eventDate = bill.latestAction?.actionDate || bill.introducedDate;
            if (!eventDate) {
              quarantined++;
              continue;
            }

            const tags = classifyBill(
              bill.title,
              bill.latestAction?.text || "",
            );

            if (tags.length === 0) {
              skipped++;
              continue;
            }

            try {
              await client.query(
                `INSERT INTO alt.legislation_1d (
                   event_date, headline, content, url,
                   source, specialist_tags, raw_payload, row_hash
                 ) VALUES ($1::date, $2, $3, $4, $5, $6, $7::jsonb, $8)`,
                [
                  eventDate,
                  `[${bill.type}${bill.number}] ${bill.title}`.slice(0, 500),
                  `${bill.title}\n\nLatest Action (${bill.latestAction?.actionDate || "N/A"}): ${bill.latestAction?.text || "N/A"}\n\nPolicy Area: ${bill.policyArea?.name || "N/A"}\nCongress: ${bill.congress}th\nIntroduced: ${bill.introducedDate}`,
                  `https://www.congress.gov/bill/${bill.congress}th-congress/${bill.type.toLowerCase() === "hr" ? "house-bill" : "senate-bill"}/${bill.number}`,
                  "congress.gov",
                  tags,
                  JSON.stringify({
                    billType: bill.type,
                    billNumber: bill.number,
                    congress: bill.congress,
                    policyArea: bill.policyArea?.name,
                    latestAction: bill.latestAction,
                    source: "congress.gov",
                  }),
                  rowHash,
                ],
              );
              inserted++;
            } catch (err) {
              quarantined++;
              logger.warn(`Insert failed for ${bill.type}${bill.number}: ${err}`);
            }
          }
        } finally {
          client.release();
        }
        return { attempted, inserted, skipped, quarantined };
      });

      rowsAttempted = result.attempted;
      rowsInserted = result.inserted;
      rowsSkipped = result.skipped;
      rowsQuarantined = result.quarantined;
    }

    // ── Step 4: finalize ingest run ──
    await step.run("complete", async () => {
      const client = await pool.connect();
      try {
        await client.query(
          `UPDATE ops.ingest_run SET status=$2, completed_at=NOW(),
           rows_attempted=$3, rows_inserted=$4, rows_skipped=$5, rows_quarantined=$6 WHERE id=$1`,
          [runId, "success", rowsAttempted, rowsInserted, rowsSkipped, rowsQuarantined],
        );
      } finally {
        client.release();
      }
    });

    logger.info(
      `Congress bills: ${rowsInserted} inserted, ${rowsSkipped} skipped, ${rowsQuarantined} quarantined`,
    );
    return {
      status: "success",
      runId,
      attempted: rowsAttempted,
      inserted: rowsInserted,
      skipped: rowsSkipped,
      quarantined: rowsQuarantined,
    };
  },
);
