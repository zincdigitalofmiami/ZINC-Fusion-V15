/**
 * Federal Register Daily Bronze Ingestion
 * 
 * BRONZE CONTRACT COMPLIANT:
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
 * @version 1.0.0 - Bronze Contract
 * @date 2026-01-11
 */

import { inngest } from "./client";
import { Pool, type PoolClient } from "pg";
import { createHash } from "crypto";
import { classifySpecialists as classifyByKeywords } from "../lib/specialist-classifier";

// Database connection pool
const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
  ssl: { rejectUnauthorized: false },
});

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
  
  // Immigration (TRUMP_EFFECT + LEGISLATION)
  { pattern: /immigration|ice[\s_-]enforcement|deportation|visa|border[\s_-]?(security|control)/i, tags: ["trump_effect", "legislation"] },
  
  // Biofuel (BIOFUEL specialist)
  { pattern: /renewable[\s_-]?fuel[\s_-]?standard|rfs/i, tags: ["biofuel"] },
  { pattern: /\brin\b|renewable[\s_-]?identification[\s_-]?number/i, tags: ["biofuel"] },
  { pattern: /biodiesel|renewable[\s_-]?diesel/i, tags: ["biofuel"] },
  { pattern: /\b45z\b|lcfs|clean[\s_-]?fuel/i, tags: ["biofuel"] },
  { pattern: /epa.*fuel|fuel.*epa/i, tags: ["biofuel"] },
  { pattern: /blending[\s_-]?mandate|blender/i, tags: ["biofuel"] },
  
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
  
  // Default - all Federal Register docs are legislation
  { pattern: /.*/, tags: ["legislation"] },
];

/**
 * Assign specialist tags based on document content
 *
 * Uses hybrid approach:
 * 1. Document-specific TAG_RULES (regex patterns for Federal Register context)
 * 2. Shared keyword classifier for general specialist detection
 * 3. "legislation" always added for Federal Register documents
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

  // All Federal Register docs get "legislation" as document-type tag
  // Note: "legislation" is NOT a Big-11 specialist, it's a document category
  tags.add("legislation");

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

/**
 * Create a new ingest run record
 */
async function createIngestRun(client: PoolClient, jobName: string): Promise<string> {
  const result = await client.query(
    `INSERT INTO ops.ingest_run (job_name, status, started_at)
     VALUES ($1, 'running', NOW())
     RETURNING id`,
    [jobName]
  );
  return result.rows[0].id;
}

/**
 * Update ingest run with final counts
 */
async function updateIngestRun(
  client: PoolClient,
  runId: string,
  status: string,
  rowsAttempted: number,
  rowsInserted: number,
  rowsSkipped: number,
  rowsQuarantined: number,
  errorMessage?: string
): Promise<void> {
  await client.query(
    `UPDATE ops.ingest_run
     SET status = $2,
         completed_at = NOW(),
         rows_attempted = $3,
         rows_inserted = $4,
         rows_skipped = $5,
         rows_quarantined = $6,
         error_message = $7
     WHERE id = $1`,
    [runId, status, rowsAttempted, rowsInserted, rowsSkipped, rowsQuarantined, errorMessage]
  );
}

/**
 * Quarantine an invalid record
 */
async function quarantineRecord(
  client: PoolClient,
  runId: string,
  sourceTable: string,
  payload: object,
  errors: string[],
  severity: string = "error"
): Promise<void> {
  await client.query(
    `INSERT INTO ops.quarantined_record 
       (ingest_run_id, source_table, raw_payload, validation_errors, severity)
     VALUES ($1, $2, $3, $4, $5)`,
    [runId, sourceTable, JSON.stringify(payload), errors, severity]
  );
}

/**
 * Check if row hash already exists in database
 */
async function hashExists(client: PoolClient, rowHash: string): Promise<boolean> {
  const result = await client.query(
    `SELECT 1 FROM alt.legislation_1d WHERE row_hash = $1 LIMIT 1`,
    [rowHash]
  );
  return result.rows.length > 0;
}

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
  
  // Fetch with pagination
  let url: string | null = `${baseUrl}?${params.toString()}`;
  let pageCount = 0;
  const maxPages = 10; // Safety limit
  
  while (url && pageCount < maxPages) {
    const response = await fetch(url);
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
  }
  
  return documents;
}

// =============================================================================
// MAIN INNGEST FUNCTION
// =============================================================================

/**
 * Federal Register Daily Bronze Ingestion
 * 
 * Runs daily at 11:00 AM UTC (5AM CT) Mon-Fri.
 * Ingests recent Federal Register documents with Bronze contract compliance.
 */
export const federalRegisterDaily = inngest.createFunction(
  { 
    id: "federal-register-daily", 
    name: "Federal Register Daily Bronze Ingestion",
    retries: 3,
  },
  { cron: "0 11 * * 1-5" }, // 5AM CT = 11AM UTC, Mon-Fri
  async ({ step, logger }) => {
    // Get database client
    const client = await pool.connect();
    let runId: string | null = null;

    // Counters
    let rowsAttempted = 0;
    let rowsInserted = 0;
    let rowsSkipped = 0;
    let rowsQuarantined = 0;
    const results: { docNumber: string; status: string; tags?: string[] }[] = [];

    try {
      // Step 1: Create ingest run record
      runId = await step.run("create-ingest-run", async () => {
        return await createIngestRun(client, "federal-register-daily");
      });

      logger.info(`Started ingest run: ${runId}`);

      // Step 2: Fetch documents from Federal Register API
      const documents = await step.run("fetch-documents", async () => {
        return await fetchRecentDocuments();
      });

      logger.info(`Fetched ${documents.length} documents from Federal Register`);

      // Step 3: Process each document
      for (const doc of documents) {
        const outcome = await step.run(`ingest-${doc.document_number}`, async () => {
          try {
            // Validate required fields
            if (!doc.document_number || !doc.publication_date) {
              await quarantineRecord(
                client,
                runId!,
                "alt.legislation_1d",
                doc,
                ["Missing required fields: document_number or publication_date"],
                "error"
              );
              return { docNumber: doc.document_number || "UNKNOWN", status: "quarantined_missing_fields" as const };
            }

            // Compute row hash for idempotency
            const rowHash = computeRowHash(doc.document_number, doc.publication_date);

            // Check if exact same data already exists (skip duplicate)
            if (await hashExists(client, rowHash)) {
              return { docNumber: doc.document_number, status: "skipped_duplicate" as const };
            }

            // Extract agencies
            const agencies = doc.agencies?.map(a => a.name) || [];

            // Assign specialist tags
            const tags = assignTags(
              doc.title || "",
              doc.abstract || "",
              doc.type,
              agencies
            );

            // Insert new document (append-only)
            await client.query(
              `INSERT INTO alt.legislation_1d (
                 event_date,
                 document_number,
                 document_type,
                 title,
                 agency,
                 source,
                 url,
                 raw_payload,
                 ingestion_batch_id,
                 row_hash,
                 specialist_tags
               ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)`,
              [
                doc.publication_date,      // event_date
                doc.document_number,       // document_number
                doc.type,                  // document_type
                doc.title,                 // title
                agencies.join(', '),       // agency (string, not array)
                "federal_register_api",    // source
                doc.html_url,              // url
                JSON.stringify(doc),       // raw_payload
                runId,                     // ingestion_batch_id
                rowHash,                   // row_hash
                tags,                      // specialist_tags
              ]
            );

            return { docNumber: doc.document_number, status: "inserted" as const, tags };

          } catch (error) {
            const errorMsg = error instanceof Error ? error.message : String(error);
            
            await quarantineRecord(
              client,
              runId!,
              "alt.legislation_1d",
              doc,
              ["Insert error: " + errorMsg],
              "error"
            );

            return { docNumber: doc.document_number || "UNKNOWN", status: "error" as const };
          }
        });

        rowsAttempted++;
        results.push(outcome);
        if (outcome.status === "inserted") {
          rowsInserted++;
        } else if (outcome.status === "skipped_duplicate") {
          rowsSkipped++;
        } else {
          rowsQuarantined++;
        }
      }

      // Step 4: Update ingest run with final counts
      await step.run("complete-ingest-run", async () => {
        await updateIngestRun(
          client,
          runId!,
          "success",
          rowsAttempted,
          rowsInserted,
          rowsSkipped,
          rowsQuarantined
        );
      });

      logger.info(`Completed ingest run: ${runId}`);
      logger.info(`  Attempted: ${rowsAttempted}`);
      logger.info(`  Inserted: ${rowsInserted}`);
      logger.info(`  Skipped: ${rowsSkipped}`);
      logger.info(`  Quarantined: ${rowsQuarantined}`);

      // Log tag distribution
      const tagCounts: Record<string, number> = {};
      results
        .filter(r => r.tags)
        .forEach(r => r.tags!.forEach(tag => {
          tagCounts[tag] = (tagCounts[tag] || 0) + 1;
        }));
      logger.info(`Tag distribution: ${JSON.stringify(tagCounts)}`);

      return {
        status: "success",
        runId,
        date: new Date().toISOString().split("T")[0],
        summary: {
          attempted: rowsAttempted,
          inserted: rowsInserted,
          skipped: rowsSkipped,
          quarantined: rowsQuarantined,
        },
        tagDistribution: tagCounts,
        sampleResults: results.slice(0, 10),
      };

    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error);
      
      // Update ingest run as failed
      if (runId) {
        await updateIngestRun(
          client,
          runId,
          "failed",
          rowsAttempted,
          rowsInserted,
          rowsSkipped,
          rowsQuarantined,
          errorMsg
        );
      }

      logger.error(`Ingest run failed: ${errorMsg}`);

      return {
        status: "failed",
        runId,
        error: errorMsg,
        summary: {
          attempted: rowsAttempted,
          inserted: rowsInserted,
          skipped: rowsSkipped,
          quarantined: rowsQuarantined,
        },
      };

    } finally {
      client.release();
    }
  }
);
