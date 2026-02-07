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

import { inngest, DB_CONCURRENCY } from "./client";
import { createHash } from "crypto";
import pool from "@/lib/db";

const USDA_API_KEY = process.env.USDA_API_KEY;

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
    concurrency: [{ limit: 1 }],
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
      let inserted = 0;
      let skipped = 0;
      let invalid = 0;

      for (const dataPoint of allData) {
        const value = parseNASSValue(dataPoint.Value);
        if (value === null) {
          invalid++;
          continue;
        }
      } finally {
        // Shared pool - do not close
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
