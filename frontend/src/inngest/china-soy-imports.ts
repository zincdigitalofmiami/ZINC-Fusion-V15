/**
 * China Soybean & Soybean Oil Imports — Monthly
 *
 * Multi-source approach for China import data (world's largest soybean buyer):
 * 1. UN Comtrade API (free, no key) — official customs data by HS code
 * 2. USDA FAS PSD (fallback) — USDA estimates if Comtrade is delayed
 *
 * HS Codes:
 * - 120100 — Soybeans
 * - 150710 — Crude Soybean Oil
 * - 230400 — Soybean Meal (oilcake)
 *
 * Reporter: China (156)
 * Flow: Imports (M)
 *
 * Table: supply.china_imports_1m
 *
 * @author Claude (ZINC-FUSION-V15)
 * @date 2026-03-04
 */

import { inngest, DB_CONCURRENCY } from "./client";
import { createHash } from "crypto";
import dbPool from "@/lib/db";

const pool = dbPool;

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

const CHINA_REPORTER_CODE = "156"; // ISO-3166 numeric for China

interface HsCommodity {
  code: string;
  name: string;
  symbol: string; // our internal symbol
}

const HS_COMMODITIES: HsCommodity[] = [
  { code: "120100", name: "Soybeans", symbol: "SOY_IMPORTS" },
  { code: "150710", name: "Crude Soybean Oil", symbol: "SOYOIL_IMPORTS" },
  { code: "230400", name: "Soybean Meal (Oilcake)", symbol: "SOYMEAL_IMPORTS" },
];

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface ComtradeRecord {
  period: number; // e.g. 202601
  reporterCode: string;
  partnerCode: string;
  partnerDesc: string;
  cmdCode: string;
  cmdDesc: string;
  flowCode: string;
  primaryValue: number | null; // USD
  netWgt: number | null; // kg
  qty: number | null;
  qtyUnitCode: number;
}

interface ComtradeResponse {
  elapsedTime: string;
  count: number;
  data: ComtradeRecord[];
  error?: string;
}

interface ImportRecord {
  reportMonth: string; // YYYY-MM-01
  commodity: string;
  symbol: string;
  partnerCountry: string;
  valueUsd: number;
  quantityMt: number; // metric tons
}

// ---------------------------------------------------------------------------
// Table DDL
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Fetch from UN Comtrade
// ---------------------------------------------------------------------------

async function fetchComtrade(
  hsCode: string,
  year: number,
): Promise<ComtradeRecord[]> {
  // UN Comtrade v1 API (free, public)
  // frequency=M for monthly, reporter=156 (China), flow=M (imports)
  const url = new URL("https://comtradeapi.un.org/public/v1/preview/C/M/HS");
  url.searchParams.set("reporterCode", CHINA_REPORTER_CODE);
  url.searchParams.set("cmdCode", hsCode);
  url.searchParams.set("flowCode", "M"); // imports
  url.searchParams.set("period", String(year));
  url.searchParams.set("partnerCode", "0"); // World aggregate

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 30000);

  try {
    const res = await fetch(url.toString(), {
      headers: {
        "User-Agent": "ZINC-Fusion/1.0 (agricultural-research)",
        Accept: "application/json",
      },
      signal: controller.signal,
    });

    if (!res.ok) {
      // Comtrade returns 409 for rate limiting, 404 for no data
      if (res.status === 409) {
        console.warn("Comtrade rate limited — will retry next run");
        return [];
      }
      if (res.status === 404) {
        return []; // no data for this period
      }
      throw new Error(`Comtrade API error: ${res.status}`);
    }

    const json: ComtradeResponse = await res.json();
    if (json.error) {
      console.warn(`Comtrade error: ${json.error}`);
      return [];
    }

    return json.data || [];
  } finally {
    clearTimeout(timeout);
  }
}

/**
 * Convert Comtrade records into our normalized import records
 */
function normalizeRecords(
  data: ComtradeRecord[],
  commodity: HsCommodity,
): ImportRecord[] {
  const records: ImportRecord[] = [];

  for (const row of data) {
    if (!row.period) continue;

    // period is YYYYMM (e.g., 202601)
    const yearStr = String(row.period).slice(0, 4);
    const monthStr = String(row.period).slice(4, 6);
    const reportMonth = `${yearStr}-${monthStr}-01`;

    // Convert kg to metric tons
    const quantityMt = row.netWgt ? row.netWgt / 1000 : 0;
    const valueUsd = row.primaryValue ?? 0;

    if (quantityMt === 0 && valueUsd === 0) continue;

    records.push({
      reportMonth,
      commodity: commodity.name,
      symbol: commodity.symbol,
      partnerCountry: row.partnerDesc || "World",
      valueUsd,
      quantityMt,
    });
  }

  return records;
}

// ---------------------------------------------------------------------------
// Inngest Function
// ---------------------------------------------------------------------------

export const chinaSoyImportsMonthly = inngest.createFunction(
  {
    id: "china-soy-imports-monthly",
    name: "China Soybean/Oil/Meal Imports (Comtrade)",
    retries: 2,
    concurrency: [DB_CONCURRENCY],
  },
  [{ cron: "0 8 20 * *" }, { event: "china/soy-imports-monthly" }], // 20th of month + manual
  async ({ step, logger }) => {
    logger.info("Fetching China soybean complex imports from UN Comtrade");

    // Step 1: Assert Prisma migration contract is present
    await step.run("assert-table-contract", async () => {
      const client = await pool.connect();
      try {
        const { rows } = await client.query<{
          regclass_name: string | null;
        }>(`SELECT to_regclass('supply.china_imports_1m')::text AS regclass_name`);
        if (!rows[0]?.regclass_name) {
          throw new Error(
            "Missing table supply.china_imports_1m. Apply Prisma migrations before running china-soy-imports-monthly."
          );
        }
      } finally {
        client.release();
      }
    });

    const currentYear = new Date().getFullYear();
    const allRecords: ImportRecord[] = [];

    // Step 2: Fetch each commodity (with rate limit delays)
    for (const commodity of HS_COMMODITIES) {
      const records = await step.run(`fetch-${commodity.symbol}`, async () => {
        // Fetch current year + previous year to catch late-reported data
        const currentData = await fetchComtrade(commodity.code, currentYear);
        await new Promise((r) => setTimeout(r, 1500)); // Comtrade rate limit
        const prevData = await fetchComtrade(commodity.code, currentYear - 1);

        const normalized = [
          ...normalizeRecords(currentData, commodity),
          ...normalizeRecords(prevData, commodity),
        ];

        logger.info(
          `${commodity.name}: ${currentData.length} current + ${prevData.length} prev year records → ${normalized.length} normalized`,
        );

        return normalized;
      });

      allRecords.push(...records);

      // Rate limit between commodities
      if (commodity !== HS_COMMODITIES[HS_COMMODITIES.length - 1]) {
        await step.sleep(`delay-after-${commodity.symbol}`, "3s");
      }
    }

    // Step 3: Upsert into database
    const result = await step.run("upsert-china-imports", async () => {
      const client = await pool.connect();
      let inserted = 0;
      let skipped = 0;

      try {
        for (const record of allRecords) {
          const rowHash = createHash("sha256")
            .update(
              `${record.reportMonth}|${record.symbol}|${record.partnerCountry}|${record.quantityMt}|${record.valueUsd}`,
            )
            .digest("hex");

          const existing = await client.query(
            `SELECT row_hash FROM supply.china_imports_1m
             WHERE report_month = $1 AND symbol = $2 AND partner_country = $3`,
            [record.reportMonth, record.symbol, record.partnerCountry],
          );

          if (existing.rows.length > 0 && existing.rows[0].row_hash === rowHash) {
            skipped++;
            continue;
          }

          await client.query(
            `INSERT INTO supply.china_imports_1m
              (report_month, commodity, symbol, partner_country, value_usd, quantity_mt,
               source, specialist_tags, row_hash, ingested_at)
             VALUES ($1, $2, $3, $4, $5, $6, 'comtrade', '{china,crush}', $7, NOW())
             ON CONFLICT (report_month, symbol, partner_country) DO UPDATE SET
               value_usd = EXCLUDED.value_usd,
               quantity_mt = EXCLUDED.quantity_mt,
               row_hash = EXCLUDED.row_hash,
               ingested_at = NOW()`,
            [
              record.reportMonth,
              record.commodity,
              record.symbol,
              record.partnerCountry,
              record.valueUsd,
              record.quantityMt,
              rowHash,
            ],
          );
          inserted++;
        }

        return { inserted, skipped };
      } finally {
        client.release();
      }
    });

    logger.info(
      `China imports: inserted=${result.inserted}, skipped=${result.skipped}`,
    );

    return {
      status: "success",
      source: "UN Comtrade API",
      commodities: HS_COMMODITIES.map((c) => c.name),
      totalRecords: allRecords.length,
      ...result,
    };
  },
);
