/**
 * CONAB Brazil Production - CRITICAL SUPPLY DATA
 * 
 * Companhia Nacional de Abastecimento (CONAB) official crop forecasts
 * Brazil = #1 global soybean producer
 * 
 * CRITICAL FOR: crush specialist, china specialist, substitutes specialist
 * 
 * Source: https://www.conab.gov.br/
 * Reports: Monthly crop production surveys (Acompanhamento da Safra)
 * 
 * Runs monthly after CONAB releases (typically 8th of month)
 * 
 * @author Claude (ZINC-FUSION-V15)
 * @date 2026-01-31
 */

import { inngest } from "./client";
import pool from "@/lib/db";
import { createHash } from "crypto";

interface USDAPSDRecord {
  marketYear: string;
  attributeDescription: string;
  value: string;
}

/**
 * Fetch Brazil production data from USDA PSD database
 * This is a PROXY for CONAB data using USDA FAS official estimates
 */
async function fetchBrazilProduction(): Promise<USDAPSDRecord[]> {
  const USDA_API_KEY = process.env.USDA_API_KEY;
  const BASE_URL = "https://apps.fas.usda.gov/OpenData/api/psd";

  // Fetch Brazil soybean data (country code: BR, commodity code: 2222 for soybeans)
  const params = new URLSearchParams({
    api_key: USDA_API_KEY || "",
    countryCode: "BR",
    commodityCode: "2222", // Soybeans
  });

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 30000);
  try {
    const response = await fetch(`${BASE_URL}/commodityDataByGeoLoc?${params}`, {
      signal: controller.signal
    });
    if (!response.ok) throw new Error(`USDA PSD API error: ${response.status}`);

    const data = await response.json();
    return data.filter((d: USDAPSDRecord) => d.marketYear >= "2020/2021"); // Last 5 years
  } finally {
    clearTimeout(timeout);
  }
}

export const conabProductionMonthly = inngest.createFunction(
  {
    id: "conab-production-monthly",
    name: "Brazil Production via USDA PSD (CRITICAL)",
    retries: 3,
    concurrency: [{ limit: 1 }],
  },
  { cron: "0 0 12 * *" }, // 12th of each month
  async ({ step, logger }) => {
    logger.info("🇧🇷 CRITICAL: Brazil soybean production via USDA PSD (CONAB proxy)");
    
    const client = await pool.connect();
    let inserted = 0;
    
    try {
      const data = await step.run("fetch-usda-psd", () => fetchBrazilProduction());
      logger.info(`Fetched ${data.length} Brazil production records`);
      
      for (const record of data) {
        const reportMonth = new Date(`${record.marketYear.split('/')[0]}-07-01`); // July = marketing year start
        const rowHash = createHash("sha256")
          .update(`BR|${record.marketYear}|${record.attributeDescription}`)
          .digest("hex");
        
        const value = parseFloat(record.value);
        if (isNaN(value)) continue;
        
        // Map USDA attributes to CONAB-style fields
        const metric = record.attributeDescription;
        if (metric.includes("Production")) {
          await client.query(
            `INSERT INTO supply.conab_production_1m 
             (report_month, crop_year, commodity, production_mt, source, row_hash, raw_payload)
             VALUES ($1, $2, 'Soybeans', $3, 'USDA_PSD', $4, $5::jsonb)
             ON CONFLICT (report_month, crop_year, commodity) DO UPDATE SET
               production_mt = EXCLUDED.production_mt,
               raw_payload = EXCLUDED.raw_payload`,
            [reportMonth, record.marketYear, value * 1000, rowHash, JSON.stringify(record)]
          );
          inserted++;
        }
      }
      
      logger.info(`Inserted ${inserted} Brazil production records`);
      return { status: "success", inserted };
      
    } finally {
      client.release();
    }
  }
);
