/**
 * EIA Biodiesel Production Monthly Ingestion
 *
 * Fetches biodiesel & renewable diesel production data from EIA API v2.
 * Source: https://api.eia.gov/v2/petroleum/sum/snd/
 *   - Biodiesel: product=EPOORDB, process=YNP, duoarea=NUS
 *   - Renewable diesel: product=EPOORDO, process=YNP, duoarea=NUS
 *
 * NOTE: The old /v2/biofuels/biodiesel/production/ endpoint was removed by EIA.
 * Replaced Feb 2026 with petroleum/sum/snd which has the same data under
 * different product codes. Values are in Thousand Barrels; converted to
 * Million Gallons (1 barrel = 42 gallons).
 *
 * Schedule: 18th of each month (EIA releases ~15th)
 * Table: supply.eia_biodiesel_1m
 */

import { inngest, DB_CONCURRENCY } from "./client";
import { createHash } from "crypto";
import dbPool from "@/lib/db";

const EIA_API_KEY = process.env.EIA_API_KEY;
const pool = dbPool;

// EIA petroleum/sum/snd product codes
const BIODIESEL_PRODUCT = "EPOORDB"; // Biofuels Plant Net Production of Biodiesel
const RENEWABLE_DIESEL_PRODUCT = "EPOORDO"; // Biofuels Plant Net Production of Renewable Diesel
const PRODUCTION_PROCESS = "YNP"; // Plant Net Production
const NATIONAL_AREA = "NUS"; // United States total
const KB_TO_MGAL = 42 / 1000; // Thousand Barrels → Million Gallons

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

export const eiaBiodieselMonthly = inngest.createFunction(
  {
    id: "eia-biodiesel-monthly",
    name: "EIA Biodiesel Production Monthly",
    retries: 2,
    concurrency: [DB_CONCURRENCY],
  },
  { cron: "0 10 18 * *" }, // 10 AM UTC on 18th of month
  async ({ step, logger }) => {
    if (!EIA_API_KEY) {
      throw new Error("EIA_API_KEY not configured - required for biodiesel data");
    }

    // Step 1: Fetch biodiesel + renewable diesel production in one call
    // Both products share the same petroleum/sum/snd endpoint
    type MonthlyRecord = {
      reportMonth: string;
      biodieselProductionMgal: number | null;
      renewableDieselProductionMgal: number | null;
    };

    const monthlyRecords = await step.run("fetch-production-data", async () => {
      const startDate = new Date();
      startDate.setMonth(startDate.getMonth() - 24);
      const startStr = `${startDate.getFullYear()}-${String(startDate.getMonth() + 1).padStart(2, "0")}`;

      // Fetch both biodiesel (EPOORDB) and renewable diesel (EPOORDO) national production
      const url = `https://api.eia.gov/v2/petroleum/sum/snd/data/?api_key=${EIA_API_KEY}&frequency=monthly&data[0]=value&facets[duoarea][]=${NATIONAL_AREA}&facets[process][]=${PRODUCTION_PROCESS}&start=${startStr}&length=500&sort[0][column]=period&sort[0][direction]=desc`;

      const response = await fetch(url);
      if (!response.ok) {
        const text = await response.text();
        throw new Error(`EIA petroleum/sum/snd API error: ${response.status} - ${text}`);
      }

      const json: PetroleumResponse = await response.json();
      const data = json.response.data;

      // Merge by period
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
        // Convert Thousand Barrels to Million Gallons
        const mgal = Math.round(point.value * KB_TO_MGAL * 100) / 100;

        if (point.product === BIODIESEL_PRODUCT) {
          record.biodieselProductionMgal = (record.biodieselProductionMgal ?? 0) + mgal;
        } else {
          record.renewableDieselProductionMgal = (record.renewableDieselProductionMgal ?? 0) + mgal;
        }
      }

      return Array.from(byPeriod.values());
    });

    logger.info(`Fetched ${monthlyRecords.length} monthly production records`);

    // Step 4: Upsert into database
    const result = await step.run("upsert-biodiesel-data", async () => {
      const client = await pool.connect();
      let inserted = 0;
      let updated = 0;
      let skipped = 0;

      try {
        for (const record of monthlyRecords) {
          const rowHash = generateRowHash(
            record.reportMonth,
            record.biodieselProductionMgal,
            record.renewableDieselProductionMgal
          );

          // Check if exists with same hash (no change)
          const existing = await client.query(
            `SELECT row_hash FROM supply.eia_biodiesel_1m WHERE report_month = $1`,
            [record.reportMonth]
          );

          if (existing.rows.length > 0 && existing.rows[0].row_hash === rowHash) {
            skipped++;
            continue;
          }

          // Upsert - ON CONFLICT to handle both insert and update
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
            ]
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
    });

    logger.info(`EIA Biodiesel: inserted=${result.inserted}, updated=${result.updated}, skipped=${result.skipped}`);

    return {
      status: "success",
      source: "EIA API v2 petroleum/sum/snd (EPOORDB+EPOORDO)",
      periodsProcessed: monthlyRecords.length,
      ...result,
    };
  }
);

/**
 * EIA Biodiesel Backfill Function
 *
 * Triggered manually to backfill historical data.
 * EIA API v2 typically provides data back to ~2010.
 *
 * Event payload:
 * - startYear?: number (default 2010)
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
    if (!EIA_API_KEY) {
      throw new Error("EIA_API_KEY not configured");
    }

    const params = event.data as BackfillParams;
    const startYear = params.startYear ?? 2010;
    const endYear = params.endYear ?? new Date().getFullYear();

    logger.info(`EIA Biodiesel Backfill: ${startYear} to ${endYear}`);

    // Step 1: Check existing data to avoid duplicate pulls
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

    // Step 2: Fetch biodiesel + renewable diesel production in one call
    // Uses petroleum/sum/snd (replaces dead biofuels/biodiesel/production endpoint)
    type MonthlyRecord = {
      reportMonth: string;
      biodieselProductionMgal: number | null;
      renewableDieselProductionMgal: number | null;
    };

    const monthlyRecords = await step.run("fetch-production-backfill", async () => {
      const startStr = `${startYear}-01`;
      const endStr = `${endYear}-12`;

      const url = `https://api.eia.gov/v2/petroleum/sum/snd/data/?api_key=${EIA_API_KEY}&frequency=monthly&data[0]=value&facets[duoarea][]=${NATIONAL_AREA}&facets[process][]=${PRODUCTION_PROCESS}&start=${startStr}&end=${endStr}&length=5000&sort[0][column]=period&sort[0][direction]=asc`;

      const response = await fetch(url);
      if (!response.ok) {
        const text = await response.text();
        throw new Error(`EIA petroleum/sum/snd API error: ${response.status} - ${text}`);
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
    });

    logger.info(`Backfill fetched: ${monthlyRecords.length} monthly records`);

    // Step 5: Upsert into database
    const result = await step.run("upsert-backfill-data", async () => {
      const client = await pool.connect();
      let inserted = 0;
      let updated = 0;
      let skipped = 0;

      try {
        for (const record of monthlyRecords) {
          const rowHash = generateRowHash(
            record.reportMonth,
            record.biodieselProductionMgal,
            record.renewableDieselProductionMgal
          );

          const existing = await client.query(
            `SELECT row_hash FROM supply.eia_biodiesel_1m WHERE report_month = $1`,
            [record.reportMonth]
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
            ]
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
    });

    logger.info(`EIA Biodiesel Backfill: inserted=${result.inserted}, updated=${result.updated}, skipped=${result.skipped}`);

    return {
      status: "success",
      source: "EIA API v2 petroleum/sum/snd (EPOORDB+EPOORDO)",
      range: { startYear, endYear },
      periodsProcessed: monthlyRecords.length,
      ...result,
    };
  }
);
