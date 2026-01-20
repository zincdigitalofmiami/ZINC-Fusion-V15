/**
 * USDA/NASS Crush & Price Data Ingestion (ACTUAL DATA via QuickStats API)
 * 
 * Hits NASS QuickStats API for REAL soybean data:
 * - CRUSHED: Monthly soybean crush volumes by state/region
 * - PRICE RECEIVED: Monthly soybean prices received by farmers
 * - PRODUCTION: Annual/seasonal production estimates
 * 
 * API: https://quickstats.nass.usda.gov/api/api_GET
 * Routes to: crush specialist
 * Table: econ.rates_1d (reusing FRED pattern for time series)
 */

import { inngest } from "./client";
import { createHash } from "crypto";

const USDA_API_KEY = process.env.USDA_API_KEY;
const DATABASE_URL = process.env.DATABASE_URL || process.env.POSTGRES_URL;

interface NASSDataPoint {
  commodity_desc: string;
  statisticcat_desc: string;
  unit_desc: string;
  year: number;
  reference_period_desc: string;
  state_name: string;
  Value: string;
  CV?: string;
}

interface NASSResponse {
  data: NASSDataPoint[];
}

// Month abbreviations to numbers
const MONTH_MAP: Record<string, string> = {
  JAN: "01",
  FEB: "02",
  MAR: "03",
  APR: "04",
  MAY: "05",
  JUN: "06",
  JUL: "07",
  AUG: "08",
  SEP: "09",
  OCT: "10",
  NOV: "11",
  DEC: "12",
};

function parseNASSValue(valueStr: string): number | null {
  // NASS returns values with commas like "6,376,635"
  const cleaned = valueStr.replace(/,/g, "").trim();
  if (cleaned === "(D)" || cleaned === "(NA)" || cleaned === "") {
    return null;
  }
  const num = parseFloat(cleaned);
  return isNaN(num) ? null : num;
}

function buildSeriesId(stat: string, state: string): string {
  const stateCode = state === "US TOTAL" ? "US" : state.replace(/\s+/g, "_").toUpperCase();
  return `NASS_SOYBEANS_${stat.replace(/\s+/g, "_").toUpperCase()}_${stateCode}`;
}

function buildObservationDate(year: number, period: string): string | null {
  const monthNum = MONTH_MAP[period.toUpperCase()];
  if (!monthNum) {
    // Could be annual - return year end
    if (period === "YEAR") {
      return `${year}-12-31`;
    }
    return null;
  }
  // Return last day of month
  const lastDay = new Date(year, parseInt(monthNum), 0).getDate();
  return `${year}-${monthNum}-${String(lastDay).padStart(2, "0")}`;
}

function generateRowHash(seriesId: string, date: string, value: number): string {
  const content = `${seriesId}|${date}|${value}`;
  return createHash("sha256").update(content).digest("hex");
}

async function fetchNASSData(
  apiKey: string,
  statistic: string,
  years: number[]
): Promise<NASSDataPoint[]> {
  const allData: NASSDataPoint[] = [];

  for (const year of years) {
    const url = new URL("https://quickstats.nass.usda.gov/api/api_GET");
    url.searchParams.set("key", apiKey);
    url.searchParams.set("commodity_desc", "SOYBEANS");
    url.searchParams.set("statisticcat_desc", statistic);
    url.searchParams.set("year", year.toString());
    url.searchParams.set("format", "JSON");

    const response = await fetch(url.toString());

    if (!response.ok) {
      console.error(`NASS API error for ${statistic} ${year}: ${response.status}`);
      continue;
    }

    const json: NASSResponse = await response.json();
    if (json.data) {
      allData.push(...json.data);
    }
  }

  return allData;
}

export const usdaDaily = inngest.createFunction(
  {
    id: "nass-crush-weekly",
    name: "NASS Soybean Crush & Prices (QuickStats API)",
  },
  { cron: "0 10 * * 1" }, // Mondays at 10am (NASS releases data monthly)
  async ({ step }) => {
    if (!USDA_API_KEY) {
      throw new Error("USDA_API_KEY not configured");
    }

    const currentYear = new Date().getFullYear();
    const years = [currentYear - 1, currentYear]; // Last 2 years

    // Step 1: Fetch CRUSHED data (soybean crush volumes)
    const crushData = await step.run("fetch-nass-crushed", async () => {
      return await fetchNASSData(USDA_API_KEY, "CRUSHED", years);
    });

    // Step 2: Fetch PRICE RECEIVED data
    const priceData = await step.run("fetch-nass-prices", async () => {
      return await fetchNASSData(USDA_API_KEY, "PRICE RECEIVED", years);
    });

    // Combine all data
    const allData = [...crushData, ...priceData];

    // Step 3: Insert into database
    const result = await step.run("insert-nass-data", async () => {
      if (!DATABASE_URL) {
        throw new Error("DATABASE_URL not configured");
      }

      const { Pool } = await import("pg");
      const pool = new Pool({ connectionString: DATABASE_URL });

      let inserted = 0;
      let skipped = 0;
      let invalid = 0;

      try {
        for (const dataPoint of allData) {
          const value = parseNASSValue(dataPoint.Value);
          if (value === null) {
            invalid++;
            continue;
          }

          const obsDate = buildObservationDate(
            dataPoint.year,
            dataPoint.reference_period_desc
          );
          if (!obsDate) {
            invalid++;
            continue;
          }

          const seriesId = buildSeriesId(
            dataPoint.statisticcat_desc,
            dataPoint.state_name
          );

          const rowHash = generateRowHash(seriesId, obsDate, value);

          // Check if exists
          const checkResult = await pool.query(
            `SELECT 1 FROM econ.rates_1d WHERE row_hash = $1`,
            [rowHash]
          );

          if (checkResult.rows.length > 0) {
            skipped++;
            continue;
          }

          // Insert into unified rates table
          await pool.query(
            `INSERT INTO econ.rates_1d
             (series_id, event_date, value, source, row_hash)
             VALUES ($1, $2, $3, $4, $5)`,
            [
              seriesId,
              obsDate,
              value,
              "usda_nass_api",
              rowHash,
            ]
          );
          inserted++;
        }
      } finally {
        await pool.end();
      }

      return { inserted, skipped, invalid, total: allData.length };
    });

    // Build summary
    const byStatistic: Record<string, number> = {};
    for (const d of allData) {
      const key = d.statisticcat_desc;
      byStatistic[key] = (byStatistic[key] || 0) + 1;
    }

    return {
      success: true,
      source: "NASS QuickStats API",
      years,
      statistics: byStatistic,
      crushRecords: crushData.length,
      priceRecords: priceData.length,
      ...result,
    };
  }
);
