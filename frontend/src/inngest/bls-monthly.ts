/**
 * BLS (Bureau of Labor Statistics) Monthly Data Ingestion
 *
 * Fetches Producer Price Index (PPI), Consumer Price Index (CPI),
 * and employment data relevant to soybean oil and biofuels.
 *
 * Source: https://api.bls.gov/publicAPI/v2/timeseries/data/
 * Rate limits (unregistered): 10 series, 25 queries/24h
 * Rate limits (registered): 50 series, 500 queries/24h
 *
 * Key series for soybean oil / biofuels / food processing:
 * - WPU06210102    Soybean Oil WPI
 * - PCU311224311224 Soybean & Other Oilseed Processing PPI
 * - WPU0621        Fats & Oils WPI
 * - PCU324191324191 Petroleum Refining PPI (biofuel ref)
 * - CUSR0000SEFR01  CPI Fats & Oils
 * - CES3231100001   Food Manufacturing Employment
 * - WPU0613        Animal Fats & Oils WPI (tallow/UCO proxy)
 *
 * Table: econ.bls_1m
 *
 * @author Claude (ZINC-FUSION-V15)
 * @date 2026-03-04
 */

import { inngest, DB_CONCURRENCY } from "./client";
import { createHash } from "crypto";
import dbPool from "@/lib/db";

const pool = dbPool;

// ---------------------------------------------------------------------------
// BLS Series Configuration
// ---------------------------------------------------------------------------

interface BlsSeriesConfig {
  id: string;
  name: string;
  tags: string[];
}

const BLS_SERIES: BlsSeriesConfig[] = [
  // Soybean oil & fats PPI
  { id: "WPU06210102", name: "WPI Soybean Oil", tags: ["crush", "biofuel"] },
  { id: "WPU0621", name: "WPI Fats & Oils", tags: ["crush", "biofuel", "palm"] },
  { id: "WPU0613", name: "WPI Animal Fats & Oils", tags: ["biofuel"] },
  // Oilseed processing PPI
  { id: "PCU311224311224", name: "PPI Oilseed Processing", tags: ["crush"] },
  // Petroleum refining (biofuel reference)
  { id: "PCU324191324191", name: "PPI Petroleum Refining", tags: ["biofuel", "energy"] },
  // CPI fats & oils (consumer demand)
  { id: "CUSR0000SEFR01", name: "CPI Fats & Oils", tags: ["crush", "fed"] },
  // Food manufacturing employment
  { id: "CES3231100001", name: "Food Manufacturing Employment", tags: ["crush", "fed"] },
  // Vegetable oil mills PPI
  { id: "PCU311223311223", name: "PPI Vegetable Oil Mills", tags: ["crush", "biofuel"] },
];

// ---------------------------------------------------------------------------
// BLS API Types
// ---------------------------------------------------------------------------

interface BlsApiResponse {
  status: string;
  responseTime: number;
  message: string[];
  Results: {
    series: BlsApiSeries[];
  };
}

interface BlsApiSeries {
  seriesID: string;
  data: BlsDataPoint[];
}

interface BlsDataPoint {
  year: string;
  period: string;
  periodName: string;
  value: string;
  footnotes: { code?: string; text?: string }[];
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function blsPeriodToDate(year: string, period: string): string | null {
  // period = "M01" through "M12" for monthly, "M13" = annual average
  if (!period.startsWith("M") || period === "M13") return null;
  const month = parseInt(period.slice(1), 10);
  if (month < 1 || month > 12) return null;
  return `${year}-${String(month).padStart(2, "0")}-01`;
}

function computeRowHash(seriesId: string, date: string, value: string): string {
  return createHash("sha256")
    .update(`${seriesId}|${date}|${value}`)
    .digest("hex");
}

// ---------------------------------------------------------------------------
// Fetch from BLS API
// ---------------------------------------------------------------------------

async function fetchBlsSeries(
  seriesIds: string[],
  startYear: number,
  endYear: number,
  apiKey?: string,
): Promise<BlsApiSeries[]> {
  const body: Record<string, unknown> = {
    seriesid: seriesIds,
    startyear: String(startYear),
    endyear: String(endYear),
  };

  if (apiKey) {
    body.registrationkey = apiKey;
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 30000);

  try {
    const res = await fetch("https://api.bls.gov/publicAPI/v2/timeseries/data/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: controller.signal,
    });

    if (!res.ok) {
      throw new Error(`BLS API error: ${res.status} ${res.statusText}`);
    }

    const json: BlsApiResponse = await res.json();

    if (json.status !== "REQUEST_SUCCEEDED") {
      throw new Error(`BLS API status: ${json.status} — ${json.message.join("; ")}`);
    }

    return json.Results.series;
  } finally {
    clearTimeout(timeout);
  }
}

// ---------------------------------------------------------------------------
// Inngest Function
// ---------------------------------------------------------------------------

export const blsMonthly = inngest.createFunction(
  {
    id: "bls-monthly",
    name: "BLS PPI/CPI/Employment Monthly",
    retries: 3,
    concurrency: [DB_CONCURRENCY],
  },
  [{ cron: "0 14 15 * *" }, { event: "bls/monthly" }], // 15th of each month + manual
  async ({ step, logger }) => {
    const apiKey = process.env.BLS_API_KEY; // optional, increases rate limits
    const currentYear = new Date().getFullYear();
    // Fetch last 2 years to catch revisions
    const startYear = currentYear - 1;

    // Step 1: Fetch from BLS API (split into batches of 10 for unregistered)
    const batchSize = apiKey ? 25 : 10;
    const allSeries: BlsApiSeries[] = [];

    for (let i = 0; i < BLS_SERIES.length; i += batchSize) {
      const batch = BLS_SERIES.slice(i, i + batchSize);
      const batchIds = batch.map((s) => s.id);
      const batchName = `fetch-bls-batch-${Math.floor(i / batchSize)}`;

      const result = await step.run(batchName, async () => {
        return fetchBlsSeries(batchIds, startYear, currentYear, apiKey);
      });

      allSeries.push(...result);

      // Rate limit: small delay between batches
      if (i + batchSize < BLS_SERIES.length) {
        await step.sleep("rate-limit-delay", "2s");
      }
    }

    logger.info(`Fetched ${allSeries.length} BLS series`);

    // Step 2: Upsert into database
    const result = await step.run("upsert-bls-data", async () => {
      const client = await pool.connect();
      let inserted = 0;
      let skipped = 0;

      try {
        // Build lookup for series metadata
        const seriesLookup = new Map(BLS_SERIES.map((s) => [s.id, s]));

        for (const series of allSeries) {
          const config = seriesLookup.get(series.seriesID);
          if (!config) continue;

          for (const point of series.data) {
            const eventDate = blsPeriodToDate(point.year, point.period);
            if (!eventDate) continue;

            const value = parseFloat(point.value);
            if (!Number.isFinite(value)) continue;

            const rowHash = computeRowHash(series.seriesID, eventDate, point.value);

            // Check if already exists with same hash
            const existing = await client.query(
              `SELECT row_hash FROM econ.bls_1m WHERE series_id = $1 AND event_date = $2`,
              [series.seriesID, eventDate],
            );

            if (existing.rows.length > 0 && existing.rows[0].row_hash === rowHash) {
              skipped++;
              continue;
            }

            await client.query(
              `INSERT INTO econ.bls_1m
                (series_id, event_date, value, series_name, specialist_tags, source, row_hash, ingested_at)
               VALUES ($1, $2, $3, $4, $5, 'bls_api', $6, NOW())
               ON CONFLICT (series_id, event_date) DO UPDATE SET
                 value = EXCLUDED.value,
                 row_hash = EXCLUDED.row_hash,
                 ingested_at = NOW()`,
              [series.seriesID, eventDate, value, config.name, config.tags, rowHash],
            );
            inserted++;
          }
        }

        return { inserted, skipped };
      } finally {
        client.release();
      }
    });

    logger.info(`BLS Monthly: inserted=${result.inserted}, skipped=${result.skipped}`);

    return {
      status: "success",
      source: "BLS API v2",
      seriesFetched: allSeries.length,
      ...result,
    };
  },
);
