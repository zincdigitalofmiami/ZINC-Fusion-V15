/**
 * EIA Biodiesel Production Monthly Ingestion
 *
 * Fetches biodiesel & renewable diesel production data from EIA API v2.
 * Source: https://api.eia.gov/v2/biofuels/biodiesel/production/
 *
 * Key metrics:
 * - Biodiesel production (million gallons)
 * - Renewable diesel production (million gallons)
 * - Feedstock soybean oil percentage (derived from inputs data)
 * - Capacity utilization percentage
 *
 * Schedule: 18th of each month (EIA releases ~15th)
 * Table: supply.eia_biodiesel_1m
 */

import { inngest } from "./client";
import { createHash } from "crypto";
import dbPool from "@/lib/db";

const EIA_API_KEY = process.env.EIA_API_KEY;

const pool = dbPool;

interface EIADataPoint {
  period: string;
  value: number | null;
  units: string;
  "series-description"?: string;
}

interface EIAResponse {
  response: {
    data: EIADataPoint[];
    total: number;
  };
}

function generateRowHash(reportMonth: string, biodiesel: number | null, renewable: number | null): string {
  const content = `${reportMonth}|${biodiesel ?? "null"}|${renewable ?? "null"}`;
  return createHash("sha256").update(content).digest("hex");
}

/**
 * Convert EIA period (YYYY-MM) to first-of-month date string
 */
function periodToDate(period: string): string {
  // EIA returns periods like "2025-12" - convert to "2025-12-01"
  return `${period}-01`;
}

export const eiaBiodieselMonthly = inngest.createFunction(
  {
    id: "eia-biodiesel-monthly",
    name: "EIA Biodiesel Production Monthly",
    retries: 2,
  },
  { cron: "0 10 18 * *" }, // 10 AM UTC on 18th of month
  async ({ step, logger }) => {
    if (!EIA_API_KEY) {
      throw new Error("EIA_API_KEY not configured - required for biodiesel data");
    }

    // Step 1: Fetch biodiesel production data
    const biodieselData = await step.run("fetch-biodiesel-production", async () => {
      // Get last 24 months of data
      const startDate = new Date();
      startDate.setMonth(startDate.getMonth() - 24);
      const startStr = `${startDate.getFullYear()}-${String(startDate.getMonth() + 1).padStart(2, "0")}`;

      const url = new URL("https://api.eia.gov/v2/biofuels/biodiesel/production/data/");
      url.searchParams.set("api_key", EIA_API_KEY);
      url.searchParams.set("frequency", "monthly");
      url.searchParams.set("data[0]", "value");
      url.searchParams.set("start", startStr);
      url.searchParams.set("sort[0][column]", "period");
      url.searchParams.set("sort[0][direction]", "desc");
      url.searchParams.set("length", "100");

      const response = await fetch(url.toString());

      if (!response.ok) {
        const text = await response.text();
        throw new Error(`EIA Biodiesel API error: ${response.status} - ${text}`);
      }

      const json: EIAResponse = await response.json();
      return json.response.data;
    });

    // Step 2: Fetch renewable diesel production data
    const renewableDieselData = await step.run("fetch-renewable-diesel", async () => {
      const startDate = new Date();
      startDate.setMonth(startDate.getMonth() - 24);
      const startStr = `${startDate.getFullYear()}-${String(startDate.getMonth() + 1).padStart(2, "0")}`;

      // Renewable diesel is under a different facet in EIA data
      // Using the broader biofuels endpoint filtered for renewable diesel
      const url = new URL("https://api.eia.gov/v2/biofuels/biodiesel/production/data/");
      url.searchParams.set("api_key", EIA_API_KEY!);
      url.searchParams.set("frequency", "monthly");
      url.searchParams.set("data[0]", "value");
      url.searchParams.set("start", startStr);
      // Filter for renewable diesel specifically
      url.searchParams.set("facets[process][]", "RNW");
      url.searchParams.set("length", "100");

      try {
        const response = await fetch(url.toString());
        if (!response.ok) {
          // Renewable diesel endpoint may not be available - continue without it
          return [];
        }
        const json: EIAResponse = await response.json();
        return json.response.data;
      } catch {
        // If renewable diesel data is unavailable, continue with biodiesel only
        return [];
      }
    });

    logger.info(`Fetched ${biodieselData.length} biodiesel records, ${renewableDieselData.length} renewable diesel records`);

    // Step 3: Merge and prepare data by period
    type MonthlyRecord = {
      reportMonth: string;
      biodieselProductionMgal: number | null;
      renewableDieselProductionMgal: number | null;
    };

    const monthlyRecords = await step.run("merge-monthly-data", async () => {
      const byPeriod = new Map<string, MonthlyRecord>();

      // Process biodiesel data
      for (const point of biodieselData) {
        if (point.value === null || point.value === undefined) continue;

        const monthKey = point.period; // YYYY-MM format
        if (!byPeriod.has(monthKey)) {
          byPeriod.set(monthKey, {
            reportMonth: periodToDate(monthKey),
            biodieselProductionMgal: null,
            renewableDieselProductionMgal: null,
          });
        }

        const record = byPeriod.get(monthKey)!;
        // Accumulate if multiple series exist for same period
        record.biodieselProductionMgal = (record.biodieselProductionMgal ?? 0) + point.value;
      }

      // Process renewable diesel data
      for (const point of renewableDieselData) {
        if (point.value === null || point.value === undefined) continue;

        const monthKey = point.period;
        if (!byPeriod.has(monthKey)) {
          byPeriod.set(monthKey, {
            reportMonth: periodToDate(monthKey),
            biodieselProductionMgal: null,
            renewableDieselProductionMgal: null,
          });
        }

        const record = byPeriod.get(monthKey)!;
        record.renewableDieselProductionMgal = (record.renewableDieselProductionMgal ?? 0) + point.value;
      }

      return Array.from(byPeriod.values());
    });

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
      source: "EIA API v2 biofuels/biodiesel/production",
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
    concurrency: { limit: 1 },
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

    // Step 2: Fetch all biodiesel production data for range
    const biodieselData = await step.run("fetch-biodiesel-production-backfill", async () => {
      const startStr = `${startYear}-01`;
      const endStr = `${endYear}-12`;

      const url = new URL("https://api.eia.gov/v2/biofuels/biodiesel/production/data/");
      url.searchParams.set("api_key", EIA_API_KEY!);
      url.searchParams.set("frequency", "monthly");
      url.searchParams.set("data[0]", "value");
      url.searchParams.set("start", startStr);
      url.searchParams.set("end", endStr);
      url.searchParams.set("sort[0][column]", "period");
      url.searchParams.set("sort[0][direction]", "asc");
      url.searchParams.set("length", "5000"); // Get all records

      const response = await fetch(url.toString());

      if (!response.ok) {
        const text = await response.text();
        throw new Error(`EIA Biodiesel API error: ${response.status} - ${text}`);
      }

      const json: EIAResponse = await response.json();
      return json.response.data;
    });

    // Step 3: Fetch renewable diesel data for range
    const renewableDieselData = await step.run("fetch-renewable-diesel-backfill", async () => {
      const startStr = `${startYear}-01`;
      const endStr = `${endYear}-12`;

      const url = new URL("https://api.eia.gov/v2/biofuels/biodiesel/production/data/");
      url.searchParams.set("api_key", EIA_API_KEY!);
      url.searchParams.set("frequency", "monthly");
      url.searchParams.set("data[0]", "value");
      url.searchParams.set("start", startStr);
      url.searchParams.set("end", endStr);
      url.searchParams.set("facets[process][]", "RNW");
      url.searchParams.set("length", "5000");

      try {
        const response = await fetch(url.toString());
        if (!response.ok) {
          return [];
        }
        const json: EIAResponse = await response.json();
        return json.response.data;
      } catch {
        return [];
      }
    });

    logger.info(`Backfill fetched: ${biodieselData.length} biodiesel, ${renewableDieselData.length} renewable diesel`);

    // Step 4: Merge and prepare data
    type MonthlyRecord = {
      reportMonth: string;
      biodieselProductionMgal: number | null;
      renewableDieselProductionMgal: number | null;
    };

    const monthlyRecords = await step.run("merge-backfill-data", async () => {
      const byPeriod = new Map<string, MonthlyRecord>();

      for (const point of biodieselData) {
        if (point.value === null || point.value === undefined) continue;

        const monthKey = point.period;
        if (!byPeriod.has(monthKey)) {
          byPeriod.set(monthKey, {
            reportMonth: periodToDate(monthKey),
            biodieselProductionMgal: null,
            renewableDieselProductionMgal: null,
          });
        }

        const record = byPeriod.get(monthKey)!;
        record.biodieselProductionMgal = (record.biodieselProductionMgal ?? 0) + point.value;
      }

      for (const point of renewableDieselData) {
        if (point.value === null || point.value === undefined) continue;

        const monthKey = point.period;
        if (!byPeriod.has(monthKey)) {
          byPeriod.set(monthKey, {
            reportMonth: periodToDate(monthKey),
            biodieselProductionMgal: null,
            renewableDieselProductionMgal: null,
          });
        }

        const record = byPeriod.get(monthKey)!;
        record.renewableDieselProductionMgal = (record.renewableDieselProductionMgal ?? 0) + point.value;
      }

      return Array.from(byPeriod.values());
    });

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
      source: "EIA API v2 biofuels/biodiesel/production",
      range: { startYear, endYear },
      periodsProcessed: monthlyRecords.length,
      ...result,
    };
  }
);
