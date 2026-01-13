/**
 * FRED Daily Bronze Ingestion
 * 
 * BRONZE CONTRACT COMPLIANT:
 * - Logs each run in ops.ingest_run
 * - Computes row_hash for idempotency
 * - Assigns specialist_tags per MAPPING doc
 * - Append-only inserts (no upserts)
 * - Quarantines invalid records to ops.quarantined_record
 * 
 * @author Claude (ZINC-FUSION-V15)
 * @version 2.0.0 - Bronze Contract
 * @date 2026-01-11
 */

import { inngest } from "./client";
import { Pool, type PoolClient } from "pg";
import { createHash } from "crypto";

// Database connection pool
const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
  ssl: { rejectUnauthorized: false },
});

// =============================================================================
// FRED SERIES CONFIGURATION WITH SPECIALIST TAGS
// =============================================================================

interface FredSeriesConfig {
  id: string;
  name: string;
  tags: string[];
}

interface FredSegment {
  name: string;
  series: FredSeriesConfig[];
}

type FredIngestResult = { series: string; status: string; value?: number; tags?: string[] };

interface FredSegmentSummary {
  attempted: number;
  inserted: number;
  skipped: number;
  quarantined: number;
  results: FredIngestResult[];
}

/**
 * Comprehensive FRED series list grouped by specialist bucket.
 * Source: RAW_SOURCE_SPECIALIST_MAPPING.md (LOCKED)
 */
const FRED_FED_SERIES: FredSeriesConfig[] = [
  { id: "DFF", name: "Fed Funds Effective Rate", tags: ["fed"] },
  { id: "DGS1MO", name: "1-Month Treasury", tags: ["fed"] },
  { id: "DGS3MO", name: "3-Month Treasury", tags: ["fed"] },
  { id: "DGS6MO", name: "6-Month Treasury", tags: ["fed"] },
  { id: "DGS1", name: "1-Year Treasury", tags: ["fed"] },
  { id: "DGS2", name: "2-Year Treasury", tags: ["fed"] },
  { id: "DGS5", name: "5-Year Treasury", tags: ["fed"] },
  { id: "DGS7", name: "7-Year Treasury", tags: ["fed"] },
  { id: "DGS10", name: "10-Year Treasury", tags: ["fed"] },
  { id: "DGS20", name: "20-Year Treasury", tags: ["fed"] },
  { id: "DGS30", name: "30-Year Treasury", tags: ["fed"] },
  { id: "T10Y2Y", name: "10Y-2Y Spread (Yield Curve)", tags: ["fed"] },
  { id: "T10Y3M", name: "10Y-3M Spread", tags: ["fed"] },
  { id: "T10YIE", name: "10Y Breakeven Inflation", tags: ["fed"] },
  { id: "SOFR", name: "SOFR Rate", tags: ["fed"] },
  { id: "DPRIME", name: "Prime Rate", tags: ["fed"] },
  { id: "MORTGAGE30US", name: "30-Year Mortgage Rate", tags: ["fed"] },
  { id: "WALCL", name: "Fed Total Assets", tags: ["fed"] },
  { id: "WRESBAL", name: "Reserve Balances", tags: ["fed"] },
  { id: "RRPONTSYD", name: "Reverse Repo", tags: ["fed"] },
  { id: "CPIAUCSL", name: "CPI All Urban", tags: ["fed"] },
  { id: "CPILFESL", name: "Core CPI", tags: ["fed"] },
  { id: "PCEPI", name: "PCE Price Index", tags: ["fed"] },
  { id: "PCEPILFE", name: "Core PCE", tags: ["fed"] },
  { id: "UNRATE", name: "Unemployment Rate", tags: ["fed"] },
  { id: "PAYEMS", name: "Nonfarm Payrolls", tags: ["fed"] },
  { id: "ICSA", name: "Initial Jobless Claims", tags: ["fed"] },
  { id: "CCSA", name: "Continued Claims", tags: ["fed"] },
];

const FRED_FX_SERIES: FredSeriesConfig[] = [
  { id: "DEXBZUS", name: "USD/BRL (Brazil)", tags: ["fx"] },
  { id: "DEXCHUS", name: "USD/CNY (China)", tags: ["fx", "china"] },
  { id: "DEXUSEU", name: "USD/EUR", tags: ["fx"] },
  { id: "DEXUSUK", name: "USD/GBP", tags: ["fx"] },
  { id: "DEXJPUS", name: "USD/JPY", tags: ["fx"] },
  { id: "DEXCAUS", name: "USD/CAD", tags: ["fx"] },
  { id: "DEXMXUS", name: "USD/MXN", tags: ["fx"] },
  { id: "DEXKOUS", name: "USD/KRW (Korea)", tags: ["fx"] },
  { id: "DEXINUS", name: "USD/INR (India)", tags: ["fx"] },
  { id: "DEXMAUS", name: "USD/MYR (Malaysia)", tags: ["fx", "palm"] },
  { id: "DEXSFUS", name: "USD/SGD (Singapore)", tags: ["fx"] },
  { id: "DEXTHUS", name: "USD/THB (Thailand)", tags: ["fx"] },
  { id: "DEXHKUS", name: "USD/HKD (Hong Kong)", tags: ["fx"] },
  { id: "DEXTAUS", name: "USD/TWD (Taiwan)", tags: ["fx"] },
  { id: "DEXUSAL", name: "USD/AUD", tags: ["fx"] },
  { id: "DEXNOUS", name: "USD/NOK", tags: ["fx"] },
  { id: "DEXSZUS", name: "USD/CHF", tags: ["fx"] },
  { id: "DEXSIUS", name: "USD/SEK", tags: ["fx"] },
  { id: "DTWEXBGS", name: "Trade-Weighted USD (Broad)", tags: ["fx"] },
  { id: "DTWEXAFEGS", name: "USD vs Advanced FX", tags: ["fx"] },
  { id: "DTWEXEMEGS", name: "USD vs EM FX", tags: ["fx"] },
];

const FRED_ENERGY_SERIES: FredSeriesConfig[] = [
  { id: "DCOILWTICO", name: "WTI Crude Oil", tags: ["energy"] },
  { id: "DCOILBRENTEU", name: "Brent Crude Oil", tags: ["energy"] },
  { id: "DHHNGSP", name: "Henry Hub Natural Gas", tags: ["energy"] },
  { id: "DDFUELUSGULF", name: "Diesel Gulf Coast", tags: ["energy", "biofuel"] },
  { id: "DGASUSGULF", name: "Gasoline Gulf Coast", tags: ["energy", "biofuel"] },
  { id: "DJFUELUSGULF", name: "Jet Fuel Gulf Coast", tags: ["energy"] },
  { id: "DPROPANEMBTX", name: "Propane Prices: Mont Belvieu, Texas", tags: ["energy"] },
];

const FRED_BIOFUEL_SERIES: FredSeriesConfig[] = [
  { id: "GASREGW", name: "US Regular Gas Price", tags: ["biofuel", "energy"] },
  { id: "GASDESW", name: "US Diesel Price", tags: ["biofuel", "energy"] },
];

const FRED_CRUSH_SERIES: FredSeriesConfig[] = [
  { id: "PSOILUSDM", name: "Soybean Oil Price (World Bank)", tags: ["crush"] },
  { id: "PSOYBUSDM", name: "Soybeans Price (World Bank)", tags: ["crush"] },
  { id: "PMAIZMTUSDM", name: "Global price of Corn", tags: ["crush", "substitutes"] },
  { id: "PWHEAMTUSDM", name: "Wheat Price", tags: ["substitutes"] },
  { id: "PBARLUSDM", name: "Barley Price", tags: ["substitutes"] },
];

const FRED_PALM_SERIES: FredSeriesConfig[] = [
  { id: "PPOILUSDM", name: "Global price of Palm Oil", tags: ["palm"] },
  { id: "PROILUSDM", name: "Global price of Rapeseed Oil (proxy for palm kernel)", tags: ["palm", "substitutes"] },
];

const FRED_VOLATILITY_SERIES: FredSeriesConfig[] = [
  { id: "VIXCLS", name: "VIX Index", tags: ["volatility"] },
  { id: "STLFSI4", name: "St. Louis Financial Stress", tags: ["volatility"] },
  { id: "NFCI", name: "Chicago Fed Financial Conditions", tags: ["volatility"] },
  { id: "BAMLH0A0HYM2", name: "High Yield OAS", tags: ["volatility"] },
  { id: "BAMLC0A0CM", name: "Corporate OAS", tags: ["volatility"] },
];

const FRED_TRUMP_EFFECT_SERIES: FredSeriesConfig[] = [
  { id: "USEPUINDXD", name: "US Policy Uncertainty (Daily)", tags: ["trump_effect", "volatility"] },
  { id: "USEPUINDXM", name: "US Policy Uncertainty (Monthly)", tags: ["trump_effect", "volatility"] },
  { id: "EPUTRADE", name: "Trade Policy Uncertainty", tags: ["tariff"] },
];

const FRED_CHINA_SERIES: FredSeriesConfig[] = [
  { id: "CHNPRINTO01IXPYM", name: "China Industrial Production", tags: ["china"] },
  { id: "CHNGDPNQDSMEI", name: "China Real GDP", tags: ["china"] },
  { id: "XTEXVA01CNM667S", name: "China Exports Value", tags: ["china", "tariff"] },
  { id: "XTIMVA01CNM667S", name: "China Imports Value", tags: ["china", "tariff"] },
];

const FRED_GENERAL_SERIES: FredSeriesConfig[] = [
  { id: "INDPRO", name: "Industrial Production", tags: ["general"] },
  { id: "UMCSENT", name: "Consumer Sentiment", tags: ["general"] },
  { id: "FRGSHPUSM649NCIS", name: "Cass Freight Index", tags: ["general"] },
];

const FRED_CONFIG_SEGMENTS: FredSegment[] = [
  { name: "fed", series: FRED_FED_SERIES },
  { name: "fx", series: FRED_FX_SERIES },
  { name: "energy", series: FRED_ENERGY_SERIES },
  { name: "biofuel", series: FRED_BIOFUEL_SERIES },
  { name: "crush", series: FRED_CRUSH_SERIES },
  { name: "palm", series: FRED_PALM_SERIES },
  { name: "volatility", series: FRED_VOLATILITY_SERIES },
  { name: "trump_effect", series: FRED_TRUMP_EFFECT_SERIES },
  { name: "china", series: FRED_CHINA_SERIES },
  { name: "general", series: FRED_GENERAL_SERIES },
];

const FRED_SEGMENT_ORDER = FRED_CONFIG_SEGMENTS.map((segment) => segment.name);

const TAG_TO_SEGMENT: Record<string, string> = {
  fed: "fed",
  fx: "fx",
  energy: "energy",
  biofuel: "biofuel",
  crush: "crush",
  substitutes: "crush",
  palm: "palm",
  volatility: "volatility",
  trump_effect: "trump_effect",
  tariff: "trump_effect",
  china: "china",
  general: "general",
};

const FRED_RATE_LIMIT_MS = 500;

const CONFIG_SERIES_INDEX: Record<string, { series: FredSeriesConfig; segment: string }> = {};
for (const segment of FRED_CONFIG_SEGMENTS) {
  for (const series of segment.series) {
    CONFIG_SERIES_INDEX[series.id] = { series, segment: segment.name };
  }
}

function normalizeTags(tags: unknown): string[] | null {
  if (!tags) return null;
  if (Array.isArray(tags)) {
    return tags.map((tag) => String(tag).trim()).filter(Boolean);
  }
  if (typeof tags === "string") {
    return tags
      .replace(/[{}]/g, "")
      .split(",")
      .map((tag) => tag.trim())
      .filter(Boolean);
  }
  return null;
}

async function fetchDbSeriesIds(client: PoolClient): Promise<string[]> {
  const result = await client.query(
    `SELECT DISTINCT series_id
     FROM raw.fred_observations_1d
     ORDER BY series_id`
  );
  return result.rows.map((row) => row.series_id);
}

async function fetchDbSeriesTags(client: PoolClient): Promise<Record<string, string[]>> {
  const result = await client.query(
    `SELECT DISTINCT ON (series_id) series_id, specialist_tags
     FROM raw.fred_observations_1d
     WHERE specialist_tags IS NOT NULL
     ORDER BY series_id, event_date DESC, knowledge_time DESC`
  );
  const tagsMap: Record<string, string[]> = {};
  for (const row of result.rows) {
    const normalized = normalizeTags(row.specialist_tags);
    if (normalized && normalized.length > 0) {
      tagsMap[row.series_id] = normalized;
    }
  }
  return tagsMap;
}

function selectSegment(tags: string[]): string {
  for (const tag of tags) {
    const mapped = TAG_TO_SEGMENT[tag];
    if (mapped) return mapped;
  }
  return "general";
}

function buildDynamicSegments(
  dbSeriesIds: string[],
  dbTags: Record<string, string[]>
): { segments: FredSegment[]; missingTags: string[]; totalSeries: number } {
  const allSeriesIds = new Set<string>([...Object.keys(CONFIG_SERIES_INDEX), ...dbSeriesIds]);
  const segmentMap: Record<string, FredSeriesConfig[]> = {};
  for (const name of FRED_SEGMENT_ORDER) {
    segmentMap[name] = [];
  }
  const missingTags: string[] = [];

  for (const seriesId of Array.from(allSeriesIds).sort()) {
    const config = CONFIG_SERIES_INDEX[seriesId];
    if (config) {
      segmentMap[config.segment].push(config.series);
      continue;
    }

    const tags = dbTags[seriesId];
    if (!tags || tags.length === 0) {
      missingTags.push(seriesId);
      continue;
    }

    const segmentName = selectSegment(tags);
    segmentMap[segmentName].push({ id: seriesId, name: seriesId, tags });
  }

  const segments = FRED_SEGMENT_ORDER
    .map((name) => ({ name, series: segmentMap[name] }))
    .filter((segment) => segment.series.length > 0);

  return {
    segments,
    missingTags,
    totalSeries: allSeriesIds.size,
  };
}

// =============================================================================
// BRONZE HELPER FUNCTIONS
// =============================================================================

/**
 * Compute SHA256 hash of observation payload for idempotency
 */
function computeRowHash(seriesId: string, date: string, value: number): string {
  const payload = `${seriesId}|${date}|${value}`;
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
    `SELECT 1 FROM raw.fred_observations_1d WHERE row_hash = $1 LIMIT 1`,
    [rowHash]
  );
  return result.rows.length > 0;
}

/**
 * Check for existing observation with different value (revision detection)
 */
async function getLatestRevision(
  client: PoolClient,
  seriesId: string,
  eventDate: string
): Promise<{ value: number; revisionNo: number } | null> {
  const result = await client.query(
    `SELECT value, revision_no 
     FROM raw.fred_observations_1d 
     WHERE series_id = $1 AND event_date = $2
     ORDER BY revision_no DESC
     LIMIT 1`,
    [seriesId, eventDate]
  );
  if (result.rows.length === 0) return null;
  return {
    value: parseFloat(result.rows[0].value),
    revisionNo: parseInt(result.rows[0].revision_no),
  };
}

// =============================================================================
// FRED API FETCH
// =============================================================================

interface FredObservation {
  date: string;
  value: string;
}

interface FredApiResponse {
  observations?: FredObservation[];
}

/**
 * Fetch latest observation from FRED API
 */
async function fetchFredSeries(
  seriesId: string,
  apiKey: string
): Promise<FredObservation | null> {
  const url = `https://api.stlouisfed.org/fred/series/observations?series_id=${seriesId}&api_key=${apiKey}&file_type=json&sort_order=desc&limit=5`;

  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`FRED API error: ${response.status} ${response.statusText}`);
  }

  const json: FredApiResponse = await response.json();
  const observations = json.observations || [];

  // Find first valid observation (skip "." values)
  for (const obs of observations) {
    if (obs.value !== "." && obs.value !== "") {
      return obs;
    }
  }

  return null;
}

// =============================================================================
// SEGMENTED INGEST HELPERS
// =============================================================================

async function ingestFredSegment(
  client: PoolClient,
  runId: string,
  apiKey: string,
  seriesList: FredSeriesConfig[]
): Promise<FredSegmentSummary> {
  const results: FredIngestResult[] = [];
  let attempted = 0;
  let inserted = 0;
  let skipped = 0;
  let quarantined = 0;

  for (const series of seriesList) {
    attempted++;

    try {
      const obs = await fetchFredSeries(series.id, apiKey);

      if (!obs) {
        results.push({ series: series.id, status: "no_data" });
        skipped++;
        continue;
      }

      const value = parseFloat(obs.value);

      if (isNaN(value)) {
        await quarantineRecord(
          client,
          runId,
          "raw.fred_observations_1d",
          { series_id: series.id, date: obs.date, raw_value: obs.value },
          ["Invalid numeric value: " + obs.value],
          "error"
        );
        results.push({ series: series.id, status: "quarantined_invalid_value" });
        quarantined++;
        continue;
      }

      const rowHash = computeRowHash(series.id, obs.date, value);

      if (await hashExists(client, rowHash)) {
        results.push({ series: series.id, status: "skipped_duplicate" });
        skipped++;
        continue;
      }

      const existing = await getLatestRevision(client, series.id, obs.date);
      let revisionNo = 1;
      if (existing && existing.value !== value) {
        revisionNo = existing.revisionNo + 1;
      }

      await client.query(
        `INSERT INTO raw.fred_observations_1d (
           series_id,
           value,
           event_date,
           knowledge_time,
           revision_no,
           is_preliminary,
           validation_status,
           source,
           source_url,
           ingestion_batch_id,
           row_hash,
           specialist_tags
         ) VALUES ($1, $2, $3, NOW(), $4, $5, $6, $7, $8, $9, $10, $11)`,
        [
          series.id,
          value,
          obs.date,
          revisionNo,
          false,
          "validated",
          "fred_api",
          `https://fred.stlouisfed.org/series/${series.id}`,
          runId,
          rowHash,
          series.tags,
        ]
      );

      results.push({
        series: series.id,
        status: revisionNo > 1 ? "inserted_revision" : "inserted",
        value,
        tags: series.tags,
      });
      inserted++;

    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error);

      await quarantineRecord(
        client,
        runId,
        "raw.fred_observations_1d",
        { series_id: series.id, error: errorMsg },
        ["Fetch/insert error: " + errorMsg],
        "error"
      );

      results.push({ series: series.id, status: "error" });
      quarantined++;
    }

    await new Promise((resolve) => setTimeout(resolve, FRED_RATE_LIMIT_MS));
  }

  return {
    results,
    attempted,
    inserted,
    skipped,
    quarantined,
  };
}

// =============================================================================
// MAIN INNGEST FUNCTION
// =============================================================================

/**
 * FRED Daily Bronze Ingestion
 * 
 * Runs daily at 10:00 AM ET (3PM UTC) after FRED updates.
 * Ingests all configured FRED series plus any series already present in raw.fred_observations_1d.
 */
export const fredDaily = inngest.createFunction(
  { 
    id: "fred-daily", 
    name: "FRED Daily Bronze Ingestion",
    retries: 3,
  },
  { cron: "0 11 * * 1-5" }, // 5AM CT = 11AM UTC, Mon-Fri
  async ({ step, logger }) => {
    const apiKey = process.env.FRED_API_KEY;
    if (!apiKey) {
      return { status: "error", message: "FRED_API_KEY not configured" };
    }

    // Get database client
    const client = await pool.connect();
    let runId: string | null = null;

    // Counters
    let rowsAttempted = 0;
    let rowsInserted = 0;
    let rowsSkipped = 0;
    let rowsQuarantined = 0;
    let results: FredIngestResult[] = [];

    try {
      // Step 1: Create ingest run record
      runId = await step.run("create-ingest-run", async () => {
        return await createIngestRun(client, "fred-daily");
      });

      logger.info(`Started ingest run: ${runId}`);

      const seriesIndex = await step.run("load-series-index", async () => {
        const dbSeriesIds = await fetchDbSeriesIds(client);
        const dbTags = await fetchDbSeriesTags(client);
        return buildDynamicSegments(dbSeriesIds, dbTags);
      });

      logger.info(
        `Loaded ${seriesIndex.totalSeries} series across ${seriesIndex.segments.length} segments`
      );
      if (seriesIndex.missingTags.length > 0) {
        logger.warn(
          `Series missing tags (skipped): ${seriesIndex.missingTags.join(", ")}`
        );
      }

      // Step 2: Fetch and process FRED series in segmented batches
      for (const segment of seriesIndex.segments) {
        const segmentSummary = await step.run(`fetch-${segment.name}`, async () => {
          return await ingestFredSegment(client, runId!, apiKey, segment.series);
        });

        rowsAttempted += segmentSummary.attempted;
        rowsInserted += segmentSummary.inserted;
        rowsSkipped += segmentSummary.skipped;
        rowsQuarantined += segmentSummary.quarantined;
        results.push(...segmentSummary.results);

        logger.info(
          `Segment ${segment.name}: attempted=${segmentSummary.attempted}, inserted=${segmentSummary.inserted}, skipped=${segmentSummary.skipped}, quarantined=${segmentSummary.quarantined}`
        );
      }

      // Step 3: Update ingest run with final counts
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
        results,
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
