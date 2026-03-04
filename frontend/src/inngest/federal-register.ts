/**
 * Federal Register Daily Data Ingestion
 *
 * INGESTION CONTRACT:
 * - Logs each run in ops.ingest_run
 * - Computes row_hash for idempotency
 * - Assigns specialist_tags per RAW_SOURCE_SPECIALIST_MAPPING.md
 * - Append-only inserts (no upserts)
 * - Quarantines invalid records to ops.quarantined_record
 *
 * SOURCE: https://www.federalregister.gov/api/v1/
 * - No API key required (public API)
 * - Rate limit: ~1000 requests/hour
 *
 * Document types fetched:
 * - RULE (Final rules)
 * - PRORULE (Proposed rules)
 * - NOTICE (Notices)
 * - PRESDOCU (Presidential documents - Executive Orders, Proclamations)
 *
 * Tag assignment logic (per RAW_SOURCE_SPECIALIST_MAPPING.md):
 * - section_301, section_232, tariff → tariff
 * - trade_deal, trade_agreement → tariff, trump_effect
 * - executive_order, presidential → trump_effect
 * - immigration, ice, deportation → trump_effect, legislation
 * - rfs, rin, biodiesel, renewable_fuel → biofuel
 * - china, prc (trade context) → china, tariff
 * - epa, environment, emissions → biofuel
 *
 * @author Claude (ZINC-FUSION-V15)
 * @version 1.2.0
 * @date 2026-02-16
 */

import { inngest, DB_CONCURRENCY } from "./client";
import { createHash } from "crypto";
import { classifySpecialists as classifyByKeywords } from "../lib/specialist-classifier";
import { getIngestPool } from "@/lib/db";

// Database connection pool
const pool = getIngestPool();

// =============================================================================
// TAG ASSIGNMENT RULES
// =============================================================================

interface TagRule {
  pattern: RegExp;
  tags: string[];
}

/**
 * Tag assignment rules based on RAW_SOURCE_SPECIALIST_MAPPING.md
 * Order matters - more specific patterns first
 */
const TAG_RULES: TagRule[] = [
  // Trade-specific (TARIFF specialist)
  { pattern: /section[\s_-]?301/i, tags: ["tariff"] },
  { pattern: /section[\s_-]?232/i, tags: ["tariff"] },
  { pattern: /tariff[\s_-]?(rate|schedule|exclusion|list)/i, tags: ["tariff"] },
  { pattern: /anti[\s_-]?dumping/i, tags: ["tariff"] },
  { pattern: /countervailing[\s_-]?dut/i, tags: ["tariff"] },
  { pattern: /trade[\s_-]?(deal|agreement|negotiation)/i, tags: ["tariff", "trump_effect"] },
  { pattern: /usmca|nafta/i, tags: ["tariff", "trump_effect"] },

  // China-specific (CHINA + TARIFF)
  { pattern: /\bchina\b|\bprc\b|chinese/i, tags: ["china", "tariff"] },
  { pattern: /cofco|sinograin/i, tags: ["china"] },

  // Presidential/Regime (TRUMP_EFFECT specialist)
  { pattern: /executive[\s_-]?order/i, tags: ["trump_effect"] },
  { pattern: /presidential[\s_-]?(action|memorandum|proclamation|determination)/i, tags: ["trump_effect"] },
  { pattern: /doge|government[\s_-]?efficiency/i, tags: ["trump_effect"] },

  // Immigration (TRUMP_EFFECT)
  { pattern: /immigration|ice[\s_-]enforcement|deportation|visa|border[\s_-]?(security|control)/i, tags: ["trump_effect"] },

  // Biofuel (BIOFUEL specialist)
  { pattern: /renewable[\s_-]?fuel[\s_-]?standard|rfs/i, tags: ["biofuel"] },
  { pattern: /\brin\b|renewable[\s_-]?identification[\s_-]?number/i, tags: ["biofuel"] },
  { pattern: /biodiesel|renewable[\s_-]?diesel/i, tags: ["biofuel"] },
  // 45Z Clean Fuel Production Credit - specific tracking
  { pattern: /\b45z\b|section[\s_-]?45z/i, tags: ["biofuel", "45z_credit"] },
  { pattern: /clean[\s_-]?fuel[\s_-]?production[\s_-]?credit/i, tags: ["biofuel", "45z_credit"] },
  { pattern: /sustainable[\s_-]?aviation[\s_-]?fuel|saf[\s_-]?credit/i, tags: ["biofuel", "45z_credit"] },
  { pattern: /carbon[\s_-]?intensity[\s_-]?score|greet[\s_-]?model/i, tags: ["biofuel", "45z_credit"] },
  { pattern: /lcfs|low[\s_-]?carbon[\s_-]?fuel[\s_-]?standard/i, tags: ["biofuel"] },
  { pattern: /clean[\s_-]?fuel/i, tags: ["biofuel"] },
  { pattern: /epa.*fuel|fuel.*epa/i, tags: ["biofuel"] },
  { pattern: /blending[\s_-]?mandate|blender/i, tags: ["biofuel"] },
  { pattern: /feedstock[\s_-]?restriction|domestic[\s_-]?feedstock/i, tags: ["biofuel", "45z_credit"] },

  // Energy (ENERGY specialist)
  { pattern: /petroleum|crude[\s_-]?oil|refiner/i, tags: ["energy"] },
  { pattern: /natural[\s_-]?gas|lng/i, tags: ["energy"] },
  { pattern: /opec|oil[\s_-]?export/i, tags: ["energy"] },

  // Agriculture (CRUSH specialist)
  { pattern: /soybean|soy[\s_-]?oil|soy[\s_-]?meal/i, tags: ["crush"] },
  { pattern: /usda|department[\s_-]?of[\s_-]?agriculture/i, tags: ["crush"] },
  { pattern: /grain|corn|wheat/i, tags: ["crush", "substitutes"] },

  // Monetary policy (FED specialist)
  { pattern: /federal[\s_-]?reserve|fomc|monetary[\s_-]?policy/i, tags: ["fed"] },
  { pattern: /interest[\s_-]?rate|treasury[\s_-]?yield/i, tags: ["fed"] },

  // Sanctions (TARIFF + CHINA)
  { pattern: /sanctions|ofac|export[\s_-]?control/i, tags: ["tariff", "china"] },

];

/**
 * Assign specialist tags based on document content
 *
 * Uses hybrid approach:
 * 1. Document-specific TAG_RULES (regex patterns for Federal Register context)
 * 2. Shared keyword classifier for general specialist detection
 */
function assignTags(title: string, abstract: string, docType: string, agencies: string[]): string[] {
  const content = `${title} ${abstract} ${agencies.join(" ")}`;
  const contentLower = content.toLowerCase();
  const tags = new Set<string>();

  // Presidential documents always get trump_effect
  if (docType === "PRESDOCU") {
    tags.add("trump_effect");
  }

  // Apply document-specific TAG_RULES (regex patterns)
  for (const rule of TAG_RULES) {
    if (rule.pattern.test(contentLower)) {
      rule.tags.forEach(tag => tags.add(tag));
      // Don't break - accumulate all matching tags
    }
  }

  // Also apply shared keyword classifier for broader coverage
  const keywordTags = classifyByKeywords(content);
  for (const tag of keywordTags) {
    if (tag !== "general") {
      tags.add(tag);
    }
  }

  return Array.from(tags);
}

// =============================================================================
// BRONZE HELPER FUNCTIONS
// =============================================================================

/**
 * Compute SHA256 hash of document for idempotency
 */
function computeRowHash(documentNumber: string, pubDate: string): string {
  const payload = `${documentNumber}|${pubDate}`;
  return createHash("sha256").update(payload).digest("hex");
}

// PoolClient helper functions removed — SQL inlined inside step.run() closures
// to prevent stale connections across Inngest durable execution boundaries.

// =============================================================================
// FEDERAL REGISTER API TYPES
// =============================================================================

interface FedRegDocument {
  document_number: string;
  type: string;
  title: string;
  abstract: string | null;
  agencies: { name: string }[];
  publication_date: string;
  effective_on: string | null;
  html_url: string;
}

interface FedRegApiResponse {
  count: number;
  results: FedRegDocument[];
  next_page_url: string | null;
}

// =============================================================================
// FEDERAL REGISTER API FETCH
// =============================================================================

/**
 * Fetch recent documents from Federal Register API
 * Fetches last 7 days of documents to catch any missed
 */
async function fetchRecentDocuments(): Promise<FedRegDocument[]> {
  const documents: FedRegDocument[] = [];

  // Calculate date range (last 7 days)
  const endDate = new Date();
  const startDate = new Date();
  startDate.setDate(startDate.getDate() - 7);

  const formatDate = (d: Date) => d.toISOString().split("T")[0];

  // Build URL with filters
  const baseUrl = "https://www.federalregister.gov/api/v1/documents.json";
  const params = new URLSearchParams({
    "per_page": "100",
    "order": "newest",
    "conditions[publication_date][gte]": formatDate(startDate),
    "conditions[publication_date][lte]": formatDate(endDate),
  });

  // Add document types
  ["RULE", "PRORULE", "NOTICE", "PRESDOCU"].forEach(type => {
    params.append("conditions[type][]", type);
  });

  // Fetch with pagination and timeout
  let url: string | null = `${baseUrl}?${params.toString()}`;
  let pageCount = 0;
  const maxPages = 3; // Reduced from 10 to prevent timeouts

  while (url && pageCount < maxPages) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 10000); // 10s per page

    try {
      const response = await fetch(url, { signal: controller.signal });
      clearTimeout(timeout);

      if (!response.ok) {
        throw new Error(`Federal Register API error: ${response.status} ${response.statusText}`);
      }

      const json: FedRegApiResponse = await response.json();
      documents.push(...json.results);

      url = json.next_page_url;
      pageCount++;

      // Rate limit: wait 100ms between requests
      if (url) {
        await new Promise(resolve => setTimeout(resolve, 100));
      }
    } catch (err) {
      clearTimeout(timeout);
      if (err instanceof Error && err.name === 'AbortError') {
        // Timeout on one page, return what we have so far
        console.warn(`Federal Register fetch timed out on page ${pageCount + 1}, returning ${documents.length} docs`);
        break;
      }
      throw err;
    }
  }

  return documents;
}

// =============================================================================
// MAIN INNGEST FUNCTION
// =============================================================================

/**
 * Federal Register Daily Data Ingestion
 *
 * Runs daily at 11:00 AM UTC (5AM CT) Mon-Fri.
 * Ingests recent Federal Register documents with ingestion contract compliance.
 */
export const federalRegisterDaily = inngest.createFunction(
  {
    id: "federal-register-daily",
    name: "Federal Register Daily Data Ingestion",
    retries: 1,
    concurrency: [DB_CONCURRENCY, { limit: 1 }],
  },
  { cron: "15 3 * * *" }, // Daily at 03:15 UTC
  async ({ step, logger }) => {
    // ── Step 1: create ingest run ──
    const runId = await step.run("create-ingest-run", async () => {
      const client = await pool.connect();
      try {
        const result = await client.query(
          `INSERT INTO ops.ingest_run (job_name, status, started_at) VALUES ($1, 'running', NOW()) RETURNING id`,
          ["federal-register-daily"]
        );
        return result.rows[0].id as string;
      } finally {
        client.release();
      }
    });

    logger.info(`Started ingest run: ${runId}`);

    // ── Step 2: fetch documents from Federal Register API ──
    const documents = await step.run("fetch-documents", async () => {
      return await fetchRecentDocuments();
    });

    logger.info(`Fetched ${documents.length} documents from Federal Register`);

    // ── Step 3: process all documents in one batched step ──
    // One connection for the entire batch is fine — this is a single step.run().
    const outcomes = await step.run("ingest-documents-batch", async () => {
      const client = await pool.connect();
      try {
        const batchedResults: { docNumber: string; status: string; tags?: string[] }[] = [];

        for (const doc of documents) {
          try {
            if (!doc.document_number || !doc.publication_date) {
              await client.query(
                `INSERT INTO ops.quarantined_record (ingest_run_id, source_table, raw_payload, validation_errors, severity) VALUES ($1, $2, $3, $4, $5)`,
                [runId, "alt.legislation_1d", JSON.stringify(doc), ["Missing required fields: document_number or publication_date"], "error"]
              );
              batchedResults.push({ docNumber: doc.document_number || "UNKNOWN", status: "quarantined_missing_fields" });
              continue;
            }

            const rowHash = computeRowHash(doc.document_number, doc.publication_date);

            const exists = await client.query(`SELECT 1 FROM alt.legislation_1d WHERE row_hash = $1 LIMIT 1`, [rowHash]);
            if (exists.rows.length > 0) {
              batchedResults.push({ docNumber: doc.document_number, status: "skipped_duplicate" });
              continue;
            }

            const agencies = doc.agencies?.map(a => a.name) || [];
            const tags = assignTags(doc.title || "", doc.abstract || "", doc.type, agencies);

            await client.query(
              `INSERT INTO alt.legislation_1d (
                 event_date, document_number, document_type, title, agency,
                 source, url, raw_payload, ingestion_batch_id, row_hash, specialist_tags
               ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)`,
              [
                doc.publication_date, doc.document_number, doc.type, doc.title,
                agencies.join(', '), "federal_register_api", doc.html_url,
                JSON.stringify(doc), runId, rowHash, tags,
              ]
            );

            batchedResults.push({ docNumber: doc.document_number, status: "inserted", tags });
          } catch (error) {
            const errorMsg = error instanceof Error ? error.message : String(error);
            await client.query(
              `INSERT INTO ops.quarantined_record (ingest_run_id, source_table, raw_payload, validation_errors, severity) VALUES ($1, $2, $3, $4, $5)`,
              [runId, "alt.legislation_1d", JSON.stringify(doc), ["Insert error: " + errorMsg], "error"]
            );
            batchedResults.push({ docNumber: doc.document_number || "UNKNOWN", status: "error" });
          }
        }

        return batchedResults;
      } finally {
        client.release();
      }
    });

    // Tally counters from batched outcomes
    let rowsAttempted = 0, rowsInserted = 0, rowsSkipped = 0, rowsQuarantined = 0;
    const results: { docNumber: string; status: string; tags?: string[] }[] = [];

    for (const outcome of outcomes) {
      rowsAttempted++;
      results.push(outcome);
      if (outcome.status === "inserted") rowsInserted++;
      else if (outcome.status === "skipped_duplicate") rowsSkipped++;
      else rowsQuarantined++;
    }

    // ── Step 4: finalize ingest run ──
    await step.run("complete-ingest-run", async () => {
      const client = await pool.connect();
      try {
        await client.query(
          `UPDATE ops.ingest_run SET status=$2, completed_at=NOW(),
           rows_attempted=$3, rows_inserted=$4, rows_skipped=$5, rows_quarantined=$6 WHERE id=$1`,
          [runId, "success", rowsAttempted, rowsInserted, rowsSkipped, rowsQuarantined]
        );
      } finally {
        client.release();
      }
    });

    logger.info(`Completed ingest run: ${runId}`);
    logger.info(`  Attempted: ${rowsAttempted}, Inserted: ${rowsInserted}, Skipped: ${rowsSkipped}, Quarantined: ${rowsQuarantined}`);

    const tagCounts: Record<string, number> = {};
    results.filter(r => r.tags).forEach(r => r.tags!.forEach(tag => {
      tagCounts[tag] = (tagCounts[tag] || 0) + 1;
    }));
    logger.info(`Tag distribution: ${JSON.stringify(tagCounts)}`);

    return {
      status: "success",
      runId,
      date: new Date().toISOString().split("T")[0],
      summary: { attempted: rowsAttempted, inserted: rowsInserted, skipped: rowsSkipped, quarantined: rowsQuarantined },
      tagDistribution: tagCounts,
      sampleResults: results.slice(0, 10),
    };
  }
);
