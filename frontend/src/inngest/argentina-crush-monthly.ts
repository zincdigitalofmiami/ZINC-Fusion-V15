/**
 * Argentina Soybean Crush - CRITICAL SUPPLY DATA
 *
 * Ciara-CEC (Argentine oil industry chamber) crush statistics
 * Argentina = #1 global exporter of soybean oil and meal
 *
 * CRITICAL FOR: crush specialist, substitutes specialist
 *
 * Sources:
 * - CIARA-CEC: https://www.ciaracec.com.ar/
 * - Argentina Ministry of Agriculture: https://www.magyp.gob.ar/
 * - USDA FAS Buenos Aires office
 *
 * Runs monthly after industry reports (typically mid-month)
 *
 * @author Claude (ZINC-FUSION-V15)
 * @date 2026-01-31
 */

import { inngest } from "./client";
import pool from "@/lib/db";
import { createHash } from "crypto";
import dbPool from "@/lib/db";

const pool = dbPool;

interface USDAPSDRecord {
  marketYear: string;
  attributeDescription: string;
  value: string;
}

/**
 * Fetch Argentina crush data from USDA PSD database
 * PROXY for CIARA-CEC using USDA FAS official estimates
 */
async function fetchArgentinaCrush(): Promise<USDAPSDRecord[]> {
  const USDA_API_KEY = process.env.USDA_API_KEY;
  if (!USDA_API_KEY) {
    throw new Error(
      "USDA_API_KEY not configured — set it in Vercel environment variables",
    );
  }
  const BASE_URL = "https://apps.fas.usda.gov/OpenData/api/psd";

  // Argentina soybean crush (country: AR, commodity: 2222)
  const params = new URLSearchParams({
    api_key: USDA_API_KEY,
    countryCode: "AR",
    commodityCode: "2222", // Soybeans
  });

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 30000);
  try {
    const response = await fetch(`${BASE_URL}/commodityDataByGeoLoc?${params}`, {
      signal: controller.signal
    });
    if (!response.ok) throw new Error(`USDA PSD error: ${response.status}`);

    const data = await response.json();
    return data.filter((d: USDAPSDRecord) => d.marketYear >= "2020/2021");
  } finally {
    clearTimeout(timeout);
  }
}

export const argentinaCrushMonthly = inngest.createFunction(
  {
    id: "argentina-crush-monthly",
    name: "Argentina Crush via USDA PSD (CRITICAL)",
    retries: 3,
    concurrency: [{ limit: 1 }],
  },
  { cron: "0 0 18 * *" }, // 18th of each month
  async ({ step, logger }) => {
    logger.info("🇦🇷 CRITICAL: Argentina crush via USDA PSD (CIARA proxy)");

    const data = await step.run("fetch-usda-psd", () => fetchArgentinaCrush());
    logger.info(`Fetched ${data.length} Argentina records`);

    const inserted = await step.run("upsert-argentina-data", async () => {
      const client = await pool.connect();
      let count = 0;
      try {
        for (const record of data) {
          const reportMonth = new Date(
            `${record.marketYear.split("/")[0]}-03-01`,
          );
          const rowHash = createHash("sha256")
            .update(`AR|${record.marketYear}|${record.attributeDescription}`)
            .digest("hex");

          const value = parseFloat(record.value);
          if (isNaN(value)) continue;

          // Crush = Beginning Stocks + Production + Imports - Exports - Ending Stocks
          const metric = record.attributeDescription;
          if (metric.includes("Crush")) {
            await client.query(
              `INSERT INTO supply.argentina_crush_1m
               (report_month, crush_volume_mt, source, row_hash, raw_payload)
               VALUES ($1, $2, 'USDA_PSD', $3, $4::jsonb)
               ON CONFLICT (report_month) DO UPDATE SET
                 crush_volume_mt = EXCLUDED.crush_volume_mt,
                 raw_payload = EXCLUDED.raw_payload`,
              [reportMonth, value * 1000, rowHash, JSON.stringify(record)],
            );
            count++;
          }
        }
        return count;
      } finally {
        client.release();
      }
    });

    logger.info(`Inserted ${inserted} Argentina crush records`);
    return { status: "success", inserted };
  },
);
