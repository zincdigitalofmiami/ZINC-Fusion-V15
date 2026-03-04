/**
 * EIA Biodiesel Production Weekly Ingestion
 *
 * PRIMARY: EIA API v2 → petroleum/sum/wkly (EPOORDB + EPOORDO)
 * FALLBACK: EIA Monthly Energy Review CSV Table 10.04A + 10.04B
 *           (monthly data stored with first-of-month as week_ending, tagged source='eia_mer_csv')
 *
 * Values are in Thousand Barrels per Day (KBPD).
 *
 * Schedule: 4 PM UTC on Wednesdays (EIA releases weekly data on Wednesdays)
 * Table: supply.eia_biodiesel_1w
 */

import { inngest, DB_CONCURRENCY } from "./client";
import { createHash } from "crypto";
import { getIngestPool } from "@/lib/db";

const EIA_API_KEY = process.env.EIA_API_KEY;
const pool = getIngestPool();

// EIA petroleum/sum/wkly product codes
const BIODIESEL_PRODUCT = "EPOORDB";
const RENEWABLE_DIESEL_PRODUCT = "EPOORDO";
const PRODUCTION_PROCESS = "YNP";
const NATIONAL_AREA = "NUS";

// MER CSV fallback URLs (same as eia-biodiesel-monthly.ts)
const MER_CSV_10_04A = "https://www.eia.gov/totalenergy/data/browser/csv.php?tbl=T10.04A";
const MER_CSV_10_04B = "https://www.eia.gov/totalenergy/data/browser/csv.php?tbl=T10.04B";

// NOTE: Table schema is managed by Prisma (supply.eia_biodiesel_1w).
// The previous CREATE TABLE IF NOT EXISTS block was removed to prevent
// schema drift — Prisma is the single source of truth.

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

// ---------------------------------------------------------------------------
// CSV Fallback: fetch monthly MER data, convert to WeeklyRecord format
// Monthly values stored with first-of-month date, tagged source='eia_mer_csv'
// ---------------------------------------------------------------------------

interface MerCsvRow { MSN: string; YYYYMM: string; Value: string }

function parseMerCsv(text: string): MerCsvRow[] {
  const lines = text.split("\n");
  if (lines.length < 2) return [];
  const header = lines[0].replace(/"/g, "").split(",");
  const msnIdx = header.indexOf("MSN");
  const dateIdx = header.indexOf("YYYYMM");
  const valIdx = header.indexOf("Value");
  if (msnIdx < 0 || dateIdx < 0 || valIdx < 0) return [];

  const rows: MerCsvRow[] = [];
  for (let i = 1; i < lines.length; i++) {
    const cols = lines[i].replace(/"/g, "").split(",");
    if (cols.length <= Math.max(msnIdx, dateIdx, valIdx)) continue;
    const ym = cols[dateIdx].trim();
    if (!/^\d{6}$/.test(ym) || ym.endsWith("13")) continue; // skip annual totals
    rows.push({ MSN: cols[msnIdx].trim(), YYYYMM: ym, Value: cols[valIdx].trim() });
  }
  return rows;
}

/** Million gallons per month → Thousand barrels per day (approximate) */
function mgalToKbpd(mgal: number, yyyymm: string): number {
  const year = parseInt(yyyymm.slice(0, 4));
  const month = parseInt(yyyymm.slice(4, 6));
  const daysInMonth = new Date(year, month, 0).getDate();
  // 1 gallon = 1/42 barrel, so 1M gallons = 1_000_000/42 barrels = ~23,809.5 barrels
  const kbbl = (mgal * 1_000_000) / 42 / 1000; // thousand barrels total in month
  return Math.round((kbbl / daysInMonth) * 1000) / 1000;
}

async function fetchMerCsvFallback(): Promise<WeeklyRecord[]> {
  // Fetch both CSV tables
  const [resp10A, resp10B] = await Promise.all([
    fetch(MER_CSV_10_04A),
    fetch(MER_CSV_10_04B),
  ]);

  if (!resp10A.ok) throw new Error(`MER 10.04A CSV: ${resp10A.status}`);
  if (!resp10B.ok) throw new Error(`MER 10.04B CSV: ${resp10B.status}`);

  const csv10A = parseMerCsv(await resp10A.text());
  const csv10B = parseMerCsv(await resp10B.text());

  // BDPRMUS = Biodiesel Production (Million Gallons) from 10.04A
  // B1PRMUS = Renewable Diesel Production (Million Gallons) from 10.04B
  const biodieselByMonth = new Map<string, number>();
  const renewableByMonth = new Map<string, number>();

  for (const row of csv10A) {
    if (row.MSN !== "BDPRMUS") continue;
    const val = parseFloat(row.Value);
    if (!Number.isFinite(val) || val <= 0) continue;
    biodieselByMonth.set(row.YYYYMM, val);
  }

  for (const row of csv10B) {
    if (row.MSN !== "B1PRMUS") continue;
    const val = parseFloat(row.Value);
    if (!Number.isFinite(val) || val <= 0) continue;
    renewableByMonth.set(row.YYYYMM, val);
  }

  // Merge into WeeklyRecord using first-of-month as date
  const allMonths = new Set([...biodieselByMonth.keys(), ...renewableByMonth.keys()]);
  const records: WeeklyRecord[] = [];

  for (const ym of allMonths) {
    const year = ym.slice(0, 4);
    const month = ym.slice(4, 6);
    const weekEnding = `${year}-${month}-01`;

    const bioMgal = biodieselByMonth.get(ym) ?? null;
    const renMgal = renewableByMonth.get(ym) ?? null;

    const bioKbpd = bioMgal !== null ? mgalToKbpd(bioMgal, ym) : null;
    const renKbpd = renMgal !== null ? mgalToKbpd(renMgal, ym) : null;

    const total =
      bioKbpd !== null || renKbpd !== null
        ? Math.round(((bioKbpd ?? 0) + (renKbpd ?? 0)) * 1000) / 1000
        : null;

    records.push({
      weekEnding,
      biodieselProductionKbpd: bioKbpd,
      renewableDieselProductionKbpd: renKbpd,
      totalBiofuelProductionKbpd: total,
    });
  }

  return records;
}

/**
 * Upsert weekly records into supply.eia_biodiesel_1w.
 * Returns counts of inserted / updated / skipped rows.
 */
async function upsertWeeklyRecords(
  records: WeeklyRecord[],
  source: string = "eia_weekly",
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
         VALUES ($1, $2, $3, $4, $6, $5, NOW())
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
          source,
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

// ---------------------------------------------------------------------------
// Scheduled weekly function (cron)
// ---------------------------------------------------------------------------

export const eiaBiodieselWeekly = inngest.createFunction(
  {
    id: "eia-biodiesel-weekly",
    name: "EIA Biodiesel Production Weekly",
    retries: 2,
    concurrency: [DB_CONCURRENCY],
  },
  { cron: "0 16 * * 3" }, // 4 PM UTC on Wednesdays
  async ({ step, logger }) => {
    let weeklyRecords: WeeklyRecord[] = [];
    let source = "unknown";

    // Step 1: Try EIA API first (may be down)
    if (EIA_API_KEY) {
      try {
        weeklyRecords = await step.run("fetch-weekly-api", async () => {
          const startDate = new Date();
          startDate.setDate(startDate.getDate() - 52 * 7);
          const startStr = startDate.toISOString().slice(0, 10);

          const controller = new AbortController();
          const timeout = setTimeout(() => controller.abort(), 15_000);

          const url =
            `https://api.eia.gov/v2/petroleum/sum/wkly/data/` +
            `?api_key=${EIA_API_KEY}` +
            `&frequency=weekly&data[0]=value` +
            `&facets[duoarea][]=${NATIONAL_AREA}` +
            `&facets[process][]=${PRODUCTION_PROCESS}` +
            `&start=${startStr}&length=5000` +
            `&sort[0][column]=period&sort[0][direction]=desc`;

          try {
            const response = await fetch(url, { signal: controller.signal });
            clearTimeout(timeout);
            if (!response.ok) throw new Error(`API ${response.status}`);
            const json: PetroleumResponse = await response.json();
            return mergeByWeek(json.response.data);
          } catch (err) {
            clearTimeout(timeout);
            throw err;
          }
        });
        source = "eia_api";
        logger.info(`EIA API: ${weeklyRecords.length} weekly records`);
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        logger.warn(`EIA API failed (will use CSV fallback): ${msg}`);
      }
    }

    // Step 2: CSV fallback if API failed or returned nothing
    if (weeklyRecords.length === 0) {
      weeklyRecords = await step.run("fetch-weekly-csv-fallback", async () => {
        return fetchMerCsvFallback();
      });
      source = "eia_mer_csv";
      logger.info(`MER CSV fallback: ${weeklyRecords.length} monthly records converted to weekly format`);
    }

    if (weeklyRecords.length === 0) {
      return { status: "no_data", source: "none" };
    }

    // Step 3: Upsert into database
    const result = await step.run("upsert-weekly-data", async () => {
      return upsertWeeklyRecords(weeklyRecords, source);
    });

    logger.info(
      `EIA Biodiesel Weekly: source=${source}, inserted=${result.inserted}, updated=${result.updated}, skipped=${result.skipped}`,
    );

    return { status: "success", source, weeksProcessed: weeklyRecords.length, ...result };
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
    retries: 2,
    concurrency: [DB_CONCURRENCY, { limit: 1 }],
  },
  { event: "eia.biodiesel.weekly.backfill" },
  async ({ event, step, logger }) => {
    const params = event.data as WeeklyBackfillParams;
    const startYear = params.startYear ?? 2001;

    let weeklyRecords: WeeklyRecord[] = [];
    let source = "unknown";

    // Step 1: Try EIA API first
    if (EIA_API_KEY) {
      try {
        weeklyRecords = await step.run("fetch-weekly-backfill-api", async () => {
          const controller = new AbortController();
          const timeout = setTimeout(() => controller.abort(), 15_000);
          const url =
            `https://api.eia.gov/v2/petroleum/sum/wkly/data/` +
            `?api_key=${EIA_API_KEY}&frequency=weekly&data[0]=value` +
            `&facets[duoarea][]=${NATIONAL_AREA}&facets[process][]=${PRODUCTION_PROCESS}` +
            `&start=${startYear}-01-01&end=${new Date().getFullYear()}-12-31` +
            `&length=5000&sort[0][column]=period&sort[0][direction]=asc`;

          try {
            const response = await fetch(url, { signal: controller.signal });
            clearTimeout(timeout);
            if (!response.ok) throw new Error(`API ${response.status}`);
            const json: PetroleumResponse = await response.json();
            return mergeByWeek(json.response.data);
          } catch (err) { clearTimeout(timeout); throw err; }
        });
        source = "eia_api";
        logger.info(`API backfill: ${weeklyRecords.length} records`);
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        logger.warn(`EIA API backfill failed (will use CSV): ${msg}`);
      }
    }

    // Step 2: CSV fallback
    if (weeklyRecords.length === 0) {
      weeklyRecords = await step.run("fetch-weekly-backfill-csv", async () => {
        return fetchMerCsvFallback();
      });
      source = "eia_mer_csv";
      logger.info(`MER CSV backfill: ${weeklyRecords.length} monthly records`);
    }

    // Step 3: Upsert
    const result = await step.run("upsert-weekly-backfill-data", async () => {
      return upsertWeeklyRecords(weeklyRecords, source);
    });

    logger.info(`Backfill: source=${source}, inserted=${result.inserted}, updated=${result.updated}, skipped=${result.skipped}`);

    return { status: "success", source, weeksProcessed: weeklyRecords.length, ...result };
  },
);
