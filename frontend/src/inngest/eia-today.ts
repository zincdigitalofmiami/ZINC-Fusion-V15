/**
 * EIA Petroleum Prices Ingestion (ACTUAL DATA via API v2)
 * 
 * Hits EIA API v2 for REAL petroleum spot prices:
 * - EPCBRENT: Brent Crude Oil ($/BBL)
 * - EPCWTI: WTI Crude Oil ($/BBL)
 * - EPD2DXL0: No.2 Diesel Retail ($/GAL)
 * - EPMRU: Regular Gasoline ($/GAL)
 * - EPMPU: Premium Gasoline ($/GAL)
 * 
 * API: https://api.eia.gov/v2/petroleum/pri/spt/data/
 * Routes to: energy specialist
 * Table: econ.rates_1d (reusing FRED pattern)
 */

import { inngest } from "./client";
import { createHash } from "crypto";
import pool from "@/lib/db";

const EIA_API_KEY = process.env.EIA_API_KEY;
const DATABASE_URL = process.env.DATABASE_URL || process.env.POSTGRES_URL;

interface EIADataPoint {
  period: string;
  product: string;
  "product-name": string;
  value: number;
  units: string;
}

interface EIAResponse {
  response: {
    data: EIADataPoint[];
    total: number;
  };
}

// Map EIA product codes to our series naming
const PRODUCT_MAPPING: Record<string, { seriesId: string; description: string }> = {
  EPCBRENT: { seriesId: "EIA_BRENT_SPOT", description: "Brent Crude Oil Spot Price" },
  EPCWTI: { seriesId: "EIA_WTI_SPOT", description: "WTI Crude Oil Spot Price" },
  EPD2DXL0: { seriesId: "EIA_DIESEL_SPOT", description: "No.2 Diesel Spot Price" },
  EPMRU: { seriesId: "EIA_GASOLINE_REG_SPOT", description: "Regular Gasoline Spot Price" },
  EPMPU: { seriesId: "EIA_GASOLINE_PREM_SPOT", description: "Premium Gasoline Spot Price" },
};

function generateRowHash(seriesId: string, date: string, value: number): string {
  const content = `${seriesId}|${date}|${value}`;
  return createHash("sha256").update(content).digest("hex");
}

export const eiaDaily = inngest.createFunction(
  {
    id: "eia-petroleum-daily",
    name: "EIA Petroleum Spot Prices (API v2)",
    concurrency: [{ limit: 1 }],
  },
  { cron: "0 */8 * * *" }, // Every 8 hours (0:00, 8:00, 16:00 UTC)
  async ({ step }) => {
    if (!EIA_API_KEY) {
      throw new Error("EIA_API_KEY not configured");
    }

    // Step 1: Fetch petroleum spot prices from EIA API v2
    const eiaData = await step.run("fetch-eia-petroleum", async () => {
      // Get last 30 days of data
      const startDate = new Date();
      startDate.setDate(startDate.getDate() - 30);
      const startStr = startDate.toISOString().split("T")[0];

      const url = new URL("https://api.eia.gov/v2/petroleum/pri/spt/data/");
      url.searchParams.set("api_key", EIA_API_KEY);
      url.searchParams.set("frequency", "daily");
      url.searchParams.set("data[0]", "value");
      url.searchParams.set("start", startStr);
      url.searchParams.set("length", "500"); // Enough for 30 days * 5 products

      const response = await fetch(url.toString());
      
      if (!response.ok) {
        const text = await response.text();
        throw new Error(`EIA API error: ${response.status} - ${text}`);
      }

      const json: EIAResponse = await response.json();
      return json.response.data;
    });

    // Step 2: Filter to our target products
    const targetProducts = Object.keys(PRODUCT_MAPPING);
    const filteredData = eiaData.filter((d) => targetProducts.includes(d.product));

    // Step 3: Insert into database
    const result = await step.run("insert-eia-prices", async () => {
      if (!DATABASE_URL) {
        throw new Error("DATABASE_URL not configured");
      }

      let inserted = 0;
      let skipped = 0;

      try {
        for (const dataPoint of filteredData) {
          const mapping = PRODUCT_MAPPING[dataPoint.product];
          if (!mapping) continue;

          const rowHash = generateRowHash(
            mapping.seriesId,
            dataPoint.period,
            dataPoint.value
          );

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
              mapping.seriesId,
              dataPoint.period,
              dataPoint.value,
              "eia_api",
              rowHash,
            ]
          );
          inserted++;
        }
      } finally {
        // Shared pool - do not close
      }

      return { inserted, skipped, total: filteredData.length };
    });

    // Build summary by product
    const byProduct: Record<string, number> = {};
    for (const d of filteredData) {
      const name = PRODUCT_MAPPING[d.product]?.seriesId || d.product;
      byProduct[name] = (byProduct[name] || 0) + 1;
    }

    return {
      success: true,
      source: "EIA API v2 petroleum/pri/spt",
      products: byProduct,
      ...result,
    };
  }
);
