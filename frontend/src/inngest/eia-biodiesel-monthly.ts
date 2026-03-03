/**
 * EIA Biodiesel Production Monthly Ingestion
 *
 * PRIMARY SOURCE: EIA Monthly Energy Review CSV downloads (no API key needed)
 *   - Biodiesel:        Table 10.04A → series BDPRMUS (Million Gallons)
 *   - Renewable diesel:  Table 10.04B → series B1PRMUS (Million Gallons)
 *   https://www.eia.gov/totalenergy/data/browser/csv.php?tbl=T10.04A
 *   https://www.eia.gov/totalenergy/data/browser/csv.php?tbl=T10.04B
 *
 * FALLBACK: EIA API v2 petroleum/sum/snd (requires EIA_API_KEY)
 *   - api.eia.gov has been down since ~Mar 1 2026. CSV is the reliable path.
 *
 * Schedule: 18th of each month (EIA releases ~25th of prior month)
 * Table: supply.eia_biodiesel_1m
 */

import { inngest, DB_CONCURRENCY } from "./client";
import { createHash } from "crypto";
import dbPool from "@/lib/db";

const EIA_API_KEY = process.env.EIA_API_KEY;
const pool = dbPool;

// CSV download URLs — Monthly Energy Review, no API key required
const MER_BIODIESEL_CSV = "https://www.eia.gov/totalenergy/data/browser/csv.php?tbl=T10.04A";
const MER_RENEWABLE_CSV = "https://www.eia.gov/totalenergy/data/browser/csv.php?tbl=T10.04B";

// Series codes in the CSV
const BIODIESEL_MSN = "BDPRMUS";    // Biodiesel Production, Million Gallons
const RENEWABLE_MSN = "B1PRMUS";    // Renewable Diesel Fuel Production, Million Gallons

// EIA API v2 product codes (fallback)
const BIODIESEL_PRODUCT = "EPOORDB";
const RENEWABLE_DIESEL_PRODUCT = "EPOORDO";
const PRODUCTION_PROCESS = "YNP";
const NATIONAL_AREA = "NUS";
const KB_TO_MGAL = 42 / 1000;

type MonthlyRecord = {
  reportMonth: string;
  biodieselProductionMgal: number | null;
  renewableDieselProductionMgal: number | null;
};

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

function generateRowHash(reportMonth: string, biodiesel: number | null, renewable: number | null): string {
  const content = `${reportMonth}|${biodiesel ?? "null"}|${renewable ?? "null"}`;
  return createHash("sha256").update(content).digest("hex");
}

function periodToDate(period: string): string {
  return `${period}-01`;
}

// ─── CSV Parsing ────────────────────────────────────────────────────────────

function parseMerCsv(csvText: string, targetMsn: string): Map<string, number> {
  const results = new Map<string, number>();
  const lines = csvText.split("\n");

  for (let i = 1; i < lines.length; i++) {
    const line = lines[i].trim();
    if (!line) continue;

    // CSV format: "MSN","YYYYMM","Value","Column_Order","Description","Unit"
    const parts = line.split(",").map((s) => s.replace(/^"|"$/g, ""));
    const msn = parts[0];
    const yyyymm = parts[1];
    const valueStr = parts[2];

    if (msn !== targetMsn) continue;
    if (!yyyymm || yyyymm.length !== 6) continue;

    const month = parseInt(yyyymm.slice(4), 10);
    // Month 13 = annual total — skip
    if (month < 1 || month > 12) continue;

    if (valueStr === "Not Available" || valueStr === "NA" || !valueStr) continue;

    const value = parseFloat(valueStr);
    if (!Number.isFinite(value)) continue;

    // Convert YYYYMM → YYYY-MM
    const yearMonth = `${yyyymm.slice(0, 4)}-${yyyymm.slice(4, 6)}`;
    results.set(yearMonth, value);
  }

  return results;
}

async function fetchViaCsv(logger: { info: (msg: string) => void }): Promise<MonthlyRecord[]> {
  logger.info("[EIA CSV] Fetching biodiesel from MER Table 10.04A...");
  const [bioResp, renResp] = await Promise.all([
    fetch(MER_BIODIESEL_CSV),
    fetch(MER_RENEWABLE_CSV),
  ]);

  if (!bioResp.ok) throw new Error(`MER 10.04A download failed: ${bioResp.status}`);
  if (!renResp.ok) throw new Error(`MER 10.04B download failed: ${renResp.status}`);

  const bioCsv = await bioResp.text();
  const renCsv = await renResp.text();

  const bioData = parseMerCsv(bioCsv, BIODIESEL_MSN);
  const renData = parseMerCsv(renCsv, RENEWABLE_MSN);

  logger.info(`[EIA CSV] Parsed ${bioData.size} biodiesel months, ${renData.size} renewable diesel months`);

  // Merge by month
  const allMonths = new Set([...bioData.keys(), ...renData.keys()]);
  const records: MonthlyRecord[] = [];

  for (const ym of allMonths) {
    records.push({
      reportMonth: `${ym}-01`,
      biodieselProductionMgal: bioData.get(ym) ?? null,
      renewableDieselProductionMgal: renData.get(ym) ?? null,
    });
  }

  // Sort descending (newest first)
  records.sort((a, b) => b.reportMonth.localeCompare(a.reportMonth));

  return records;
}

// ─── API Fetch (fallback) ───────────────────────────────────────────────────

async function fetchViaApi(_logger: { info: (msg: string) => void }): Promise<MonthlyRecord[]> {
  if (!EIA_API_KEY) throw new Error("EIA_API_KEY not configured");

  const startDate = new Date();
  startDate.setMonth(startDate.getMonth() - 24);
  const startStr = `${startDate.getFullYear()}-${String(startDate.getMonth() + 1).padStart(2, "0")}`;

  const url = `https://api.eia.gov/v2/petroleum/sum/snd/data/?api_key=${EIA_API_KEY}&frequency=monthly&data[0]=value&facets[duoarea][]=${NATIONAL_AREA}&facets[process][]=${PRODUCTION_PROCESS}&start=${startStr}&length=500&sort[0][column]=period&sort[0][direction]=desc`;

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 15_000);

  try {
    const response = await fetch(url, { signal: controller.signal });
    if (!response.ok) {
      const text = await response.text();
      throw new Error(`EIA API error: ${response.status} - ${text}`);
    }

    const json: PetroleumResponse = await response.json();
    const data = json.response.data;

    const byPeriod = new Map<string, MonthlyRecord>();
    for (const point of data) {
      if (point.value === null || point.value === undefined) continue;
      if (point.product !== BIODIESEL_PRODUCT && point.product !== RENEWABLE_DIESEL_PRODUCT) continue;

      const monthKey = point.period;
      if (!byPeriod.has(monthKey)) {
        byPeriod.set(monthKey, {
          reportMonth: periodToDate(monthKey),
          biodieselProductionMgal: null,
          renewableDieselProductionMgal: null,
        });
      }

      const record = byPeriod.get(monthKey)!;
      const mgal = Math.round(point.value * KB_TO_MGAL * 100) / 100;

      if (point.product === BIODIESEL_PRODUCT) {
        record.biodieselProductionMgal = (record.biodieselProductionMgal ?? 0) + mgal;
      } else {
        record.renewableDieselProductionMgal = (record.renewableDieselProductionMgal ?? 0) + mgal;
      }
    }

    return Array.from(byPeriod.values());
  } finally {
    clearTimeout(timeout);
  }
}

// ─── Upsert Logic (shared) ─────────────────────────────────────────────────

async function upsertRecords(
  records: MonthlyRecord[],
): Promise<{ inserted: number; updated: number; skipped: number }> {
  const client = await pool.connect();
  let inserted = 0;
  let updated = 0;
  let skipped = 0;

  try {
    for (const record of records) {
      const rowHash = generateRowHash(
        record.reportMonth,
        record.biodieselProductionMgal,
        record.renewableDieselProductionMgal,
      );

      const existing = await client.query(
        `SELECT row_hash FROM supply.eia_biodiesel_1m WHERE report_month = $1`,
        [record.reportMonth],
      );

      if (existing.rows.length > 0 && existing.rows[0].row_hash === rowHash) {
        skipped++;
        continue;
      }

      await client.query(
        `INSERT INTO supply.eia_biodiesel_1m
          (report_month, biodiesel_production_mgal, renewable_diesel_production_mgal,
           feedstock_soybean_oil_pct, capacity_utilization_pct, ingested_at, row_hash)
         VALUES ($1, $2, $3, NULL, NULL, NOW(), $4)
         ON CONFLICT (report_month) DO UPDATE SET
           biodiesel_production_mgal = EXCLUDED.biodiesel_production_mgal,
           renewable_diesel_production_mgal = EXCLUDED.renewable_diesel_production_mgal,
           ingested_at = NOW(),
           row_hash = EXCLUDED.row_hash`,
        [
          record.reportMonth,
          record.biodieselProductionMgal,
          record.renewableDieselProductionMgal,
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

// ─── Inngest Functions ──────────────────────────────────────────────────────

export const eiaBiodieselMonthly = inngest.createFunction(
  {
    id: "eia-biodiesel-monthly",
    name: "EIA Biodiesel Production Monthly",
    retries: 2,
    concurrency: [DB_CONCURRENCY],
  },
  { cron: "0 10 18 * *" },
  async ({ step, logger }) => {
    // Step 1: Fetch data — CSV primary, API fallback
    const { monthlyRecords, source } = await step.run("fetch-production-data", async () => {
      // Try CSV first (no API key needed, works even when api.eia.gov is down)
      try {
        const records = await fetchViaCsv(logger);
        if (records.length > 0) {
          return { monthlyRecords: records, source: "EIA MER CSV (T10.04A + T10.04B)" };
        }
        logger.info("[EIA] CSV returned 0 records, trying API fallback...");
      } catch (csvErr) {
        logger.info(`[EIA] CSV failed: ${csvErr instanceof Error ? csvErr.message : csvErr}, trying API...`);
      }

      // Fallback to API
      try {
        const records = await fetchViaApi(logger);
        return { monthlyRecords: records, source: "EIA API v2 petroleum/sum/snd" };
      } catch (apiErr) {
        throw new Error(
          `Both EIA data sources failed. CSV: see above. API: ${apiErr instanceof Error ? apiErr.message : apiErr}`,
        );
      }
    });

    logger.info(`Fetched ${monthlyRecords.length} monthly records via ${source}`);

    // Step 2: Upsert into database
    const result = await step.run("upsert-biodiesel-data", async () => {
      return upsertRecords(monthlyRecords);
    });

    logger.info(`EIA Biodiesel: inserted=${result.inserted}, updated=${result.updated}, skipped=${result.skipped}`);

    return {
      status: "success",
      source,
      periodsProcessed: monthlyRecords.length,
      ...result,
    };
  },
);

/**
 * EIA Biodiesel Backfill — uses CSV (full history from 2001)
 *
 * Event payload:
 * - startYear?: number (default 2001)
 * - endYear?: number (default current year)
 */
interface BackfillParams {
  startYear?: number;
  endYear?: number;
}

export const eiaBiodieselBackfill = inngest.createFunction(
  {
    id: "eia-biodiesel-backfill",
    name: "EIA Biodiesel Historical Backfill",
    retries: 2,
    concurrency: [DB_CONCURRENCY, { limit: 1 }],
  },
  { event: "eia.biodiesel.backfill" },
  async ({ event, step, logger }) => {
    const params = event.data as BackfillParams;
    const startYear = params.startYear ?? 2001;
    const endYear = params.endYear ?? new Date().getFullYear();

    logger.info(`EIA Biodiesel Backfill: ${startYear} to ${endYear}`);

    // Step 1: Check existing data
    const existingRange = await step.run("check-existing-data", async () => {
      const client = await pool.connect();
      try {
        const result = await client.query(`
          SELECT MIN(report_month) as min_date, MAX(report_month) as max_date, COUNT(*) as count
          FROM supply.eia_biodiesel_1m
        `);
        return result.rows[0];
      } finally {
        client.release();
      }
    });

    logger.info(`Existing data: ${existingRange.count} rows, ${existingRange.min_date} to ${existingRange.max_date}`);

    // Step 2: Fetch all records via CSV
    const monthlyRecords = await step.run("fetch-production-backfill", async () => {
      const records = await fetchViaCsv(logger);
      // Filter to requested range
      return records.filter((r) => {
        const year = parseInt(r.reportMonth.slice(0, 4), 10);
        return year >= startYear && year <= endYear;
      });
    });

    logger.info(`Backfill fetched: ${monthlyRecords.length} monthly records`);

    // Step 3: Upsert into database
    const result = await step.run("upsert-backfill-data", async () => {
      return upsertRecords(monthlyRecords);
    });

    logger.info(`EIA Biodiesel Backfill: inserted=${result.inserted}, updated=${result.updated}, skipped=${result.skipped}`);

    return {
      status: "success",
      source: "EIA MER CSV (T10.04A + T10.04B)",
      range: { startYear, endYear },
      periodsProcessed: monthlyRecords.length,
      ...result,
    };
  },
);
