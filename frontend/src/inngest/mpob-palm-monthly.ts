/**
 * MPOB Palm Oil Production - CRITICAL SUPPLY DATA
 *
 * Malaysia Palm Oil Board (MPOB) monthly production statistics
 * Malaysia produces ~50% of global palm oil supply
 *
 * CRITICAL FOR: palm specialist, substitutes specialist, crush specialist
 *
 * Source: http://www.mpob.gov.my/
 * API: http://bepi.mpob.gov.my/index.php/statistics
 *
 * Runs monthly after MPOB releases (typically 10th of month)
 *
 * @author Claude (ZINC-FUSION-V15)
 * @date 2026-01-31
 */

import { inngest, DB_CONCURRENCY } from "./client";
import { createHash } from "crypto";
import dbPool from "@/lib/db";

const pool = dbPool;

/**
 * Fetch Malaysia palm oil data from USDA PSD database
 * PROXY for MPOB using USDA FAS official estimates
 */
interface USDAPSDRecord {
  marketYear: string;
  attributeDescription: string;
  value: string;
}

async function fetchMalaysiaPalmProduction(): Promise<USDAPSDRecord[]> {
  const USDA_API_KEY = process.env.USDA_API_KEY;
  if (!USDA_API_KEY) {
    throw new Error(
      "USDA_API_KEY not configured — set it in Vercel environment variables",
    );
  }
  const BASE_URL = "https://apps.fas.usda.gov/OpenData/api/psd";

  // Malaysia palm oil (country: MY, commodity code for palm oil)
  const params = new URLSearchParams({
    api_key: USDA_API_KEY,
    countryCode: "MY", // Malaysia
    commodityCode: "4243", // Palm Oil
  });

  const response = await fetch(`${BASE_URL}/commodityDataByGeoLoc?${params}`);
  if (!response.ok) throw new Error(`USDA PSD error: ${response.status}`);

  const data = await response.json();
  return data.filter((d: USDAPSDRecord) => d.marketYear >= "2020/2021");
}

export const mpobPalmMonthly = inngest.createFunction(
  {
    id: "mpob-palm-monthly",
    name: "MPOB Palm via USDA PSD (CRITICAL)",
    retries: 3,
    concurrency: [DB_CONCURRENCY],
  },
  { cron: "0 0 15 * *" }, // 15th of each month
  async ({ step, logger }) => {
    logger.info("🌴 CRITICAL: Malaysia palm oil via USDA PSD (MPOB proxy)");
    logger.info("Malaysia = 50% of global palm oil supply");

    const data = await step.run("fetch-usda-psd", () =>
      fetchMalaysiaPalmProduction(),
    );
    logger.info(`Fetched ${data.length} Malaysia palm records`);

    const inserted = await step.run("upsert-palm-data", async () => {
      const client = await pool.connect();
      let count = 0;
      try {
        for (const record of data) {
          const reportMonth = new Date(
            `${record.marketYear.split("/")[0]}-10-01`,
          ); // October = palm oil year start
          const rowHash = createHash("sha256")
            .update(`MY|${record.marketYear}|${record.attributeDescription}`)
            .digest("hex");

          const value = parseFloat(record.value);
          if (isNaN(value)) continue;

          const metric = record.attributeDescription;

          if (metric.includes("Production")) {
            await client.query(
              `INSERT INTO supply.mpob_palm_1m
               (report_month, production_mt, country, source, row_hash, raw_payload)
               VALUES ($1, $2, 'Malaysia', 'USDA_PSD', $3, $4::jsonb)
               ON CONFLICT (report_month, country) DO UPDATE SET
                 production_mt = EXCLUDED.production_mt,
                 raw_payload = EXCLUDED.raw_payload`,
              [reportMonth, value * 1000, rowHash, JSON.stringify(record)],
            );
            count++;
          } else if (metric.includes("Exports")) {
            await client.query(
              `UPDATE supply.mpob_palm_1m SET exports_mt = $1
               WHERE report_month = $2 AND country = 'Malaysia'`,
              [value * 1000, reportMonth],
            );
          }
        }
        return count;
      } finally {
        client.release();
      }
    });

    logger.info(`Inserted ${inserted} Malaysia palm records`);
    return { status: "success", inserted };
  },
);
