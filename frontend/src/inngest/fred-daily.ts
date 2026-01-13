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

interface FredSegmentConfig {
  segment: string;
  id: string;
  jobName: string;
  displayName: string;
  cron: string;
  series: FredSeriesConfig[];
  rateLimitMs?: number;
  fetchTimeoutMs?: number;
  fetchRetries?: number;
  fetchBackoffMs?: number;
  retries?: number;
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

const DEFAULT_FRED_RATE_LIMIT_MS = 500;
const DEFAULT_FRED_FETCH_TIMEOUT_MS = 15000;
const DEFAULT_FRED_FETCH_RETRIES = 2;
const DEFAULT_FRED_FETCH_BACKOFF_MS = 750;

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

const FRED_SEGMENT_CONFIGS: Record<string, FredSegmentConfig> = {
  fed: {
    segment: "fed",
    id: "fred-daily-fed",
    jobName: "fred-daily-fed",
    displayName: "FRED Daily - Fed",
    cron: "0 11 * * 1-5",
    series: FRED_FED_SERIES,
    rateLimitMs: 500,
    fetchTimeoutMs: 15000,
    fetchRetries: 2,
  },
  fx: {
    segment: "fx",
    id: "fred-daily-fx",
    jobName: "fred-daily-fx",
    displayName: "FRED Daily - FX",
    cron: "5 11 * * 1-5",
    series: FRED_FX_SERIES,
    rateLimitMs: 500,
    fetchTimeoutMs: 15000,
    fetchRetries: 2,
  },
  energy: {
    segment: "energy",
    id: "fred-daily-energy",
    jobName: "fred-daily-energy",
    displayName: "FRED Daily - Energy",
    cron: "10 11 * * 1-5",
    series: FRED_ENERGY_SERIES,
    rateLimitMs: 450,
    fetchTimeoutMs: 12000,
    fetchRetries: 2,
  },
  biofuel: {
    segment: "biofuel",
    id: "fred-daily-biofuel",
    jobName: "fred-daily-biofuel",
    displayName: "FRED Daily - Biofuel",
    cron: "15 11 * * 1-5",
    series: FRED_BIOFUEL_SERIES,
    rateLimitMs: 350,
    fetchTimeoutMs: 10000,
    fetchRetries: 2,
  },
  crush: {
    segment: "crush",
    id: "fred-daily-crush",
    jobName: "fred-daily-crush",
    displayName: "FRED Daily - Crush",
    cron: "20 11 * * 1-5",
    series: FRED_CRUSH_SERIES,
    rateLimitMs: 450,
    fetchTimeoutMs: 12000,
    fetchRetries: 2,
  },
  palm: {
    segment: "palm",
    id: "fred-daily-palm",
    jobName: "fred-daily-palm",
    displayName: "FRED Daily - Palm",
    cron: "25 11 * * 1-5",
    series: FRED_PALM_SERIES,
    rateLimitMs: 350,
    fetchTimeoutMs: 10000,
    fetchRetries: 2,
  },
  volatility: {
    segment: "volatility",
    id: "fred-daily-volatility",
    jobName: "fred-daily-volatility",
    displayName: "FRED Daily - Volatility",
    cron: "30 11 * * 1-5",
    series: FRED_VOLATILITY_SERIES,
    rateLimitMs: 400,
    fetchTimeoutMs: 12000,
    fetchRetries: 2,
  },
  trump_effect: {
    segment: "trump_effect",
    id: "fred-daily-trump-effect",
    jobName: "fred-daily-trump-effect",
    displayName: "FRED Daily - Trump Effect",
    cron: "35 11 * * 1-5",
    series: FRED_TRUMP_EFFECT_SERIES,
    rateLimitMs: 400,
    fetchTimeoutMs: 10000,
    fetchRetries: 2,
  },
  china: {
    segment: "china",
    id: "fred-daily-china",
    jobName: "fred-daily-china",
    displayName: "FRED Daily - China",
    cron: "40 11 * * 1-5",
    series: FRED_CHINA_SERIES,
    rateLimitMs: 400,
    fetchTimeoutMs: 12000,
    fetchRetries: 2,
  },
  general: {
    segment: "general",
    id: "fred-daily-general",
    jobName: "fred-daily-general",
    displayName: "FRED Daily - General",
    cron: "45 11 * * 1-5",
    series: FRED_GENERAL_SERIES,
    rateLimitMs: 350,
    fetchTimeoutMs: 10000,
    fetchRetries: 2,
  },
};

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

interface FredFetchOptions {
  timeoutMs: number;
  retries: number;
  backoffMs: number;
}

type FredFetchResult =
  | { status: "ok"; observation: FredObservation }
  | { status: "no_data" }
  | { status: "not_found" };

function isRetryableStatus(status: number): boolean {
  return status === 429 || (status >= 500 && status <= 599);
}

function isNotFoundResponse(status: number, bodyText: string): boolean {
  if (status === 404) return true;
  if (status !== 400) return false;
  const lowered = bodyText.toLowerCase();
  return lowered.includes("series") && lowered.includes("not");
}

function getRetryDelayMs(retryAfter: string | null, attempt: number, baseBackoffMs: number): number {
  const retryAfterSeconds = retryAfter ? Number(retryAfter) : Number.NaN;
  const baseDelay = Number.isFinite(retryAfterSeconds)
    ? retryAfterSeconds * 1000
    : baseBackoffMs * Math.pow(2, attempt);
  const jitter = Math.floor(Math.random() * 250);
  return baseDelay + jitter;
}

/**
 * Fetch latest observation from FRED API
 */
async function fetchFredSeries(
  seriesId: string,
  apiKey: string,
  options: FredFetchOptions
): Promise<FredFetchResult> {
  const url = `https://api.stlouisfed.org/fred/series/observations?series_id=${seriesId}&api_key=${apiKey}&file_type=json&sort_order=desc&limit=5`;
  let attempt = 0;

  while (true) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), options.timeoutMs);

    try {
      const response = await fetch(url, { signal: controller.signal });
      const bodyText = await response.text();

      if (!response.ok) {
        if (isNotFoundResponse(response.status, bodyText)) {
          return { status: "not_found" };
        }

        if (isRetryableStatus(response.status) && attempt < options.retries) {
          const delayMs = getRetryDelayMs(
            response.headers.get("retry-after"),
            attempt,
            options.backoffMs
          );
          attempt += 1;
          await sleep(delayMs);
          continue;
        }

        throw new Error(`FRED API error: ${response.status} ${response.statusText}`);
      }

      if (!bodyText) {
        return { status: "no_data" };
      }

      let json: FredApiResponse;
      try {
        json = JSON.parse(bodyText) as FredApiResponse;
      } catch (error) {
        throw new Error(
          `FRED API invalid JSON: ${error instanceof Error ? error.message : String(error)}`
        );
      }

      const observations = json.observations || [];

      // Find first valid observation (skip "." values)
      for (const obs of observations) {
        if (obs.value !== "." && obs.value !== "") {
          return { status: "ok", observation: obs };
        }
      }

      return { status: "no_data" };
    } catch (error) {
      const isAbort = error instanceof Error && error.name === "AbortError";
      if ((isAbort || error instanceof TypeError) && attempt < options.retries) {
        const delayMs = getRetryDelayMs(null, attempt, options.backoffMs);
        attempt += 1;
        await sleep(delayMs);
        continue;
      }
      throw error;
    } finally {
      clearTimeout(timeout);
    }
  }
}

// =============================================================================
// SEGMENTED INGEST HELPERS
// =============================================================================

async function ingestFredSegment(
  client: PoolClient,
  runId: string,
  apiKey: string,
  seriesList: FredSeriesConfig[],
  options: FredFetchOptions & { rateLimitMs: number }
): Promise<FredSegmentSummary> {
  const results: FredIngestResult[] = [];
  let attempted = 0;
  let inserted = 0;
  let skipped = 0;
  let quarantined = 0;

  for (const series of seriesList) {
    attempted++;

    try {
      const fetchResult = await fetchFredSeries(series.id, apiKey, options);

      if (fetchResult.status === "not_found") {
        results.push({ series: series.id, status: "not_found" });
        skipped++;
        continue;
      }

      if (fetchResult.status === "no_data") {
        results.push({ series: series.id, status: "no_data" });
        skipped++;
        continue;
      }

      const obs = fetchResult.observation;
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

    await sleep(options.rateLimitMs);
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
// MAIN INNGEST FUNCTIONS (SEGMENTED)
// =============================================================================

function createFredSegmentJob(config: FredSegmentConfig) {
  return inngest.createFunction(
    {
      id: config.id,
      name: config.displayName,
      retries: config.retries ?? 3,
    },
    { cron: config.cron },
    async ({ step, logger }) => {
      const apiKey = process.env.FRED_API_KEY;
      if (!apiKey) {
        return { status: "error", message: "FRED_API_KEY not configured" };
      }

      const client = await pool.connect();
      let runId: string | null = null;

      let rowsAttempted = 0;
      let rowsInserted = 0;
      let rowsSkipped = 0;
      let rowsQuarantined = 0;
      let results: FredIngestResult[] = [];

      try {
        runId = await step.run("create-ingest-run", async () => {
          return await createIngestRun(client, config.jobName);
        });

        logger.info(`Started ingest run: ${runId} (${config.segment})`);

        const segmentSummary = await step.run(`fetch-${config.segment}`, async () => {
          const rateLimitMs = config.rateLimitMs ?? DEFAULT_FRED_RATE_LIMIT_MS;
          const timeoutMs = config.fetchTimeoutMs ?? DEFAULT_FRED_FETCH_TIMEOUT_MS;
          const retries = config.fetchRetries ?? DEFAULT_FRED_FETCH_RETRIES;
          const backoffMs = config.fetchBackoffMs ?? DEFAULT_FRED_FETCH_BACKOFF_MS;
          return await ingestFredSegment(
            client,
            runId!,
            apiKey,
            config.series,
            {
              rateLimitMs,
              timeoutMs,
              retries,
              backoffMs,
            }
          );
        });

        rowsAttempted = segmentSummary.attempted;
        rowsInserted = segmentSummary.inserted;
        rowsSkipped = segmentSummary.skipped;
        rowsQuarantined = segmentSummary.quarantined;
        results = segmentSummary.results;

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
          segment: config.segment,
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
          segment: config.segment,
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
}

export const fredDailyFed = createFredSegmentJob(FRED_SEGMENT_CONFIGS.fed);
export const fredDailyFx = createFredSegmentJob(FRED_SEGMENT_CONFIGS.fx);
export const fredDailyEnergy = createFredSegmentJob(FRED_SEGMENT_CONFIGS.energy);
export const fredDailyBiofuel = createFredSegmentJob(FRED_SEGMENT_CONFIGS.biofuel);
export const fredDailyCrush = createFredSegmentJob(FRED_SEGMENT_CONFIGS.crush);
export const fredDailyPalm = createFredSegmentJob(FRED_SEGMENT_CONFIGS.palm);
export const fredDailyVolatility = createFredSegmentJob(FRED_SEGMENT_CONFIGS.volatility);
export const fredDailyTrumpEffect = createFredSegmentJob(FRED_SEGMENT_CONFIGS.trump_effect);
export const fredDailyChina = createFredSegmentJob(FRED_SEGMENT_CONFIGS.china);
export const fredDailyGeneral = createFredSegmentJob(FRED_SEGMENT_CONFIGS.general);
