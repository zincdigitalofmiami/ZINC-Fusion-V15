/**
 * EIA Biodiesel Production Weekly Ingestion
 *
 * Fetches weekly biodiesel & renewable diesel production data from EIA API v2.
 * Source: https://api.eia.gov/v2/petroleum/sum/wkly/
 *   - Biodiesel: product=EPOORDB, process=YNP, duoarea=NUS
 *   - Renewable diesel: product=EPOORDO, process=YNP, duoarea=NUS
 *
 * Values are in Thousand Barrels per Day (KBPD) — stored as-is (no unit
 * conversion unlike the monthly variant which converts KB → MGal).
 *
 * Schedule: 4 PM UTC on Wednesdays (EIA releases weekly data on Wednesdays)
 * Table: supply.eia_biodiesel_1w
 */

import {
  inngest,
  DB_CONCURRENCY,
  RETRIES,
  HTTP_TIMEOUT_MS,
} from "./client";
import { createHash } from "crypto";
import dbPool from "@/lib/db";

const EIA_API_KEY = process.env.EIA_API_KEY;
const pool = dbPool;

// EIA petroleum/sum/wkly product codes
const BIODIESEL_PRODUCT = "EPOORDB"; // Biofuels Plant Net Production of Biodiesel
const RENEWABLE_DIESEL_PRODUCT = "EPOORDO"; // Biofuels Plant Net Production of Renewable Diesel
const PRODUCTION_PROCESS = "YNP"; // Plant Net Production
const NATIONAL_AREA = "NUS"; // United States total

interface PetroleumDataPoint {
  period: string;
  product: string;
  process: string;
  duoarea: string;
  value: number | null;
  "series-description"?: string;
}

interface PetroleumResponse {
  response: {
    data: PetroleumDataPoint[];
    total: string;
  };
}

type WeeklyRecord = {
  weekEnding: string;
  biodieselProductionKbpd: number | null;
  renewableDieselProductionKbpd: number | null;
  totalBiofuelProductionKbpd: number | null;
};

function generateRowHash(
  weekEnding: string,
  biodiesel: number | null,
  renewable: number | null,
  total: number | null,
): string {
  const content = `${weekEnding}|${biodiesel ?? "null"}|${renewable ?? "null"}|${total ?? "null"}`;
  return createHash("sha256").update(content).digest("hex");
}

/**
 * Merge raw EIA data points into weekly records keyed by period (week-ending date).
 * Each period may have up to two data points (EPOORDB + EPOORDO).
 */
function mergeByWeek(data: PetroleumDataPoint[]): WeeklyRecord[] {
  const byPeriod = new Map<string, WeeklyRecord>();

  for (const point of data) {
    if (point.value === null || point.value === undefined) continue;
    if (point.product !== BIODIESEL_PRODUCT && point.product !== RENEWABLE_DIESEL_PRODUCT) continue;

    const weekKey = point.period; // e.g. "2026-02-21"
    if (!byPeriod.has(weekKey)) {
      byPeriod.set(weekKey, {
        weekEnding: weekKey,
        biodieselProductionKbpd: null,
        renewableDieselProductionKbpd: null,
        totalBiofuelProductionKbpd: null,
      });
    }

    const record = byPeriod.get(weekKey)!;
    const kbpd = Math.round(point.value * 1000) / 1000; // preserve precision

    if (point.product === BIODIESEL_PRODUCT) {
      record.biodieselProductionKbpd = (record.biodieselProductionKbpd ?? 0) + kbpd;
    } else {
      record.renewableDieselProductionKbpd = (record.renewableDieselProductionKbpd ?? 0) + kbpd;
    }
  }

  // Compute totals
  for (const record of byPeriod.values()) {
    const bio = record.biodieselProductionKbpd ?? 0;
    const ren = record.renewableDieselProductionKbpd ?? 0;
    record.totalBiofuelProductionKbpd =
      record.biodieselProductionKbpd !== null || record.renewableDieselProductionKbpd !== null
        ? Math.round((bio + ren) * 1000) / 1000
        : null;
  }

  return Array.from(byPeriod.values());
}

/**
 * Upsert weekly records into supply.eia_biodiesel_1w.
 * Returns counts of inserted / updated / skipped rows.
 */
async function upsertWeeklyRecords(
  records: WeeklyRecord[],
): Promise<{ inserted: number; updated: number; skipped: number }> {
  const client = await pool.connect();
  let inserted = 0;
  let updated = 0;
  let skipped = 0;

  try {
    for (const record of records) {
      const rowHash = generateRowHash(
        record.weekEnding,
        record.biodieselProductionKbpd,
        record.renewableDieselProductionKbpd,
        record.totalBiofuelProductionKbpd,
      );

      // Check if row exists with same hash (no change)
      const existing = await client.query(
        `SELECT row_hash FROM supply.eia_biodiesel_1w WHERE week_ending = $1`,
        [record.weekEnding],
      );

      if (existing.rows.length > 0 && existing.rows[0].row_hash === rowHash) {
        skipped++;
        continue;
      }

      await client.query(
        `INSERT INTO supply.eia_biodiesel_1w
          (week_ending, biodiesel_production_kbpd, renewable_diesel_production_kbpd,
           total_biofuel_production_kbpd, source, row_hash, ingested_at)
         VALUES ($1, $2, $3, $4, 'eia_weekly', $5, NOW())
         ON CONFLICT (week_ending) DO UPDATE SET
           biodiesel_production_kbpd = EXCLUDED.biodiesel_production_kbpd,
           renewable_diesel_production_kbpd = EXCLUDED.renewable_diesel_production_kbpd,
           total_biofuel_production_kbpd = EXCLUDED.total_biofuel_production_kbpd,
           row_hash = EXCLUDED.row_hash,
           ingested_at = NOW()`,
        [
          record.weekEnding,
          record.biodieselProductionKbpd,
          record.renewableDieselProductionKbpd,
          record.totalBiofuelProductionKbpd,
          rowHash,
        ],
      );

      if (existing.rows.length > 0) {
        updated++;
      } else {
        inserted++;
      }
    }
  } finally {
    client.release();
  }

  return { inserted, updated, skipped };
}

async function fetchPetroleumResponse(url: string): Promise<PetroleumResponse> {
  let response: Response;
  try {
    response = await fetch(url, {
      signal: AbortSignal.timeout(HTTP_TIMEOUT_MS.LONG),
    });
  } catch (error) {
    if (error instanceof Error && error.name === "AbortError") {
      throw new Error(
        `EIA petroleum/sum/wkly API timeout after ${HTTP_TIMEOUT_MS.LONG}ms`,
      );
    }
    throw error;
  }

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`EIA petroleum/sum/wkly API error: ${response.status} - ${text}`);
  }

  return (await response.json()) as PetroleumResponse;
}

// ---------------------------------------------------------------------------
// Scheduled weekly function (cron)
// ---------------------------------------------------------------------------

export const eiaBiodieselWeekly = inngest.createFunction(
  {
    id: "eia-biodiesel-weekly",
    name: "EIA Biodiesel Production Weekly",
    retries: RETRIES.CRON_INGEST,
    concurrency: [DB_CONCURRENCY],
  },
  { cron: "0 16 * * 3" }, // 4 PM UTC on Wednesdays
  async ({ step, logger }) => {
    if (!EIA_API_KEY) {
      logger.warn("EIA_API_KEY not configured — skipping weekly biodiesel ingestion");
      return { status: "skipped", reason: "EIA_API_KEY not set" };
    }

    // Step 1: Fetch last 52 weeks of biodiesel + renewable diesel production
    const weeklyRecords = await step.run("fetch-weekly-production", async () => {
      const startDate = new Date();
      startDate.setDate(startDate.getDate() - 52 * 7); // ~52 weeks back
      const startStr = startDate.toISOString().slice(0, 10); // YYYY-MM-DD

      const url =
        `https://api.eia.gov/v2/petroleum/sum/wkly/data/` +
        `?api_key=${EIA_API_KEY}` +
        `&frequency=weekly` +
        `&data[0]=value` +
        `&facets[duoarea][]=${NATIONAL_AREA}` +
        `&facets[process][]=${PRODUCTION_PROCESS}` +
        `&start=${startStr}` +
        `&length=5000` +
        `&sort[0][column]=period` +
        `&sort[0][direction]=desc`;

      const json = await fetchPetroleumResponse(url);
      return mergeByWeek(json.response.data);
    });

    logger.info(`Fetched ${weeklyRecords.length} weekly production records`);

    // Step 2: Upsert into database
    const result = await step.run("upsert-weekly-data", async () => {
      return upsertWeeklyRecords(weeklyRecords);
    });

    logger.info(
      `EIA Biodiesel Weekly: inserted=${result.inserted}, updated=${result.updated}, skipped=${result.skipped}`,
    );

    return {
      status: "success",
      source: "EIA API v2 petroleum/sum/wkly (EPOORDB+EPOORDO)",
      weeksProcessed: weeklyRecords.length,
      ...result,
    };
  },
);

// ---------------------------------------------------------------------------
// Manual backfill (event-triggered)
// ---------------------------------------------------------------------------

interface WeeklyBackfillParams {
  startYear?: number;
}

export const eiaBiodieselWeeklyBackfill = inngest.createFunction(
  {
    id: "eia-biodiesel-weekly-backfill",
    name: "EIA Biodiesel Weekly Historical Backfill",
    retries: RETRIES.EVENT_INGEST,
    concurrency: [DB_CONCURRENCY, { limit: 1 }],
  },
  { event: "eia.biodiesel.weekly.backfill" },
  async ({ event, step, logger }) => {
    if (!EIA_API_KEY) {
      logger.warn("EIA_API_KEY not configured — skipping weekly biodiesel backfill");
      return { status: "skipped", reason: "EIA_API_KEY not set" };
    }

    const params = event.data as WeeklyBackfillParams;
    const startYear = params.startYear ?? 2010;
    const endYear = new Date().getFullYear();

    logger.info(`EIA Biodiesel Weekly Backfill: ${startYear} to ${endYear}`);

    // Step 1: Check existing data
    const existingRange = await step.run("check-existing-weekly-data", async () => {
      const client = await pool.connect();
      try {
        const result = await client.query(`
          SELECT MIN(week_ending) as min_date, MAX(week_ending) as max_date, COUNT(*) as count
          FROM supply.eia_biodiesel_1w
        `);
        return result.rows[0];
      } finally {
        client.release();
      }
    });

    logger.info(
      `Existing weekly data: ${existingRange.count} rows, ${existingRange.min_date} to ${existingRange.max_date}`,
    );

    // Step 2: Fetch full history
    const weeklyRecords = await step.run("fetch-weekly-backfill", async () => {
      const startStr = `${startYear}-01-01`;
      const endStr = `${endYear}-12-31`;

      const url =
        `https://api.eia.gov/v2/petroleum/sum/wkly/data/` +
        `?api_key=${EIA_API_KEY}` +
        `&frequency=weekly` +
        `&data[0]=value` +
        `&facets[duoarea][]=${NATIONAL_AREA}` +
        `&facets[process][]=${PRODUCTION_PROCESS}` +
        `&start=${startStr}` +
        `&end=${endStr}` +
        `&length=5000` +
        `&sort[0][column]=period` +
        `&sort[0][direction]=asc`;

      const json = await fetchPetroleumResponse(url);
      return mergeByWeek(json.response.data);
    });

    logger.info(`Backfill fetched: ${weeklyRecords.length} weekly records`);

    // Step 3: Upsert into database
    const result = await step.run("upsert-weekly-backfill-data", async () => {
      return upsertWeeklyRecords(weeklyRecords);
    });

    logger.info(
      `EIA Biodiesel Weekly Backfill: inserted=${result.inserted}, updated=${result.updated}, skipped=${result.skipped}`,
    );

    return {
      status: "success",
      source: "EIA API v2 petroleum/sum/wkly (EPOORDB+EPOORDO)",
      range: { startYear, endYear },
      weeksProcessed: weeklyRecords.length,
      ...result,
    };
  },
);
