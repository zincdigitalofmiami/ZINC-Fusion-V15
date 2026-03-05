/**
 * USDA FAS GATS (Global Agricultural Trade System) — Monthly
 *
 * Fetches US soybean complex trade data from USDA FAS GATS.
 * GATS provides detailed import/export data by commodity and country.
 *
 * Multi-source approach:
 * 1. USDA FAS GATS API (primary) — apps.fas.usda.gov/gats
 * 2. Census Bureau trade data (fallback) — api.census.gov
 *
 * HS Codes (US exports):
 * - 1201 — Soybeans
 * - 1507 — Soybean Oil
 * - 2304 — Soybean Meal
 *
 * CRITICAL FOR: tariff specialist, china specialist, crush specialist
 *
 * Table: supply.fas_gats_1m
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

interface TradeHSCode {
  code: string;
  description: string;
  symbol: string;
}

const TRADE_HS_CODES: TradeHSCode[] = [
  { code: "1201", description: "Soybeans", symbol: "SOY_EXPORT" },
  { code: "1507", description: "Soybean Oil", symbol: "SOYOIL_EXPORT" },
  { code: "2304", description: "Soybean Meal/Oilcake", symbol: "SOYMEAL_EXPORT" },
];

// Top trading partners for soybean complex
const KEY_PARTNERS = ["China", "Mexico", "EU", "Japan", "Korea", "Indonesia", "Egypt"];

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface GATSRecord {
  reportMonth: string; // YYYY-MM-01
  commodity: string;
  symbol: string;
  partnerCountry: string;
  valueUsd: number;
  quantityMt: number;
  flow: "export" | "import";
}

// ---------------------------------------------------------------------------
// Table DDL
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Source 1: USDA FAS GATS Website Scrape
// ---------------------------------------------------------------------------

async function fetchGATSData(hsCode: TradeHSCode): Promise<GATSRecord[]> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 30000);

  try {
    const currentYear = new Date().getFullYear();
    const url = `https://apps.fas.usda.gov/gats/ExpressQuery1.aspx?CmdtyCode=${hsCode.code}&Reporter=United%20States&Partner=All&Year=${currentYear}&Month=All`;

    const res = await fetch(url, {
      headers: {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        Accept: "text/html,application/xhtml+xml",
      },
      signal: controller.signal,
    });

    if (!res.ok) {
      console.warn(`GATS returned ${res.status} for HS ${hsCode.code}`);
      return [];
    }

    const html = await res.text();
    return parseGATSPage(html, hsCode);
  } catch (err) {
    console.warn(`GATS fetch failed for ${hsCode.code}: ${err}`);
    return [];
  } finally {
    clearTimeout(timeout);
  }
}

function parseGATSPage(html: string, hsCode: TradeHSCode): GATSRecord[] {
  const records: GATSRecord[] = [];

  const rowPattern = /<tr[^>]*>([\s\S]*?)<\/tr>/gi;
  let rowMatch;

  while ((rowMatch = rowPattern.exec(html)) !== null) {
    const rowHtml = rowMatch[1];
    const cellPattern = /<td[^>]*>([\s\S]*?)<\/td>/gi;
    const cells: string[] = [];
    let cellMatch;

    while ((cellMatch = cellPattern.exec(rowHtml)) !== null) {
      cells.push(cellMatch[1].replace(/<[^>]+>/g, "").trim());
    }

    if (cells.length < 4) continue;

    const country = cells[0];
    const periodStr = cells[1];
    const valueStr = cells[2];
    const qtyStr = cells[3];

    const monthMatch = periodStr?.match(
      /(?:(\w{3})\s+(\d{4}))|(?:(\d{4})-(\d{2}))/,
    );
    if (!monthMatch) continue;

    let reportMonth: string;
    if (monthMatch[1] && monthMatch[2]) {
      const monthNames: Record<string, string> = {
        Jan: "01", Feb: "02", Mar: "03", Apr: "04",
        May: "05", Jun: "06", Jul: "07", Aug: "08",
        Sep: "09", Oct: "10", Nov: "11", Dec: "12",
      };
      const mm = monthNames[monthMatch[1]];
      if (!mm) continue;
      reportMonth = `${monthMatch[2]}-${mm}-01`;
    } else {
      reportMonth = `${monthMatch[3]}-${monthMatch[4]}-01`;
    }

    const valueUsd = parseFloat((valueStr || "0").replace(/[,$]/g, "")) * 1000;
    const quantityMt = parseFloat((qtyStr || "0").replace(/,/g, ""));

    if (!isFinite(valueUsd) && !isFinite(quantityMt)) continue;
    if (valueUsd === 0 && quantityMt === 0) continue;

    records.push({
      reportMonth,
      commodity: hsCode.description,
      symbol: hsCode.symbol,
      partnerCountry: country || "World",
      valueUsd: isFinite(valueUsd) ? valueUsd : 0,
      quantityMt: isFinite(quantityMt) ? quantityMt : 0,
      flow: "export",
    });
  }

  return records;
}

// ---------------------------------------------------------------------------
// Source 2: Census Bureau Trade Data (Fallback)
// ---------------------------------------------------------------------------

async function fetchCensusFallback(hsCode: TradeHSCode): Promise<GATSRecord[]> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 20000);

  try {
    const currentYear = new Date().getFullYear();
    const url = `https://api.census.gov/data/timeseries/intltrade/exports/hs?get=CTY_CODE,CTY_NAME,ALL_VAL_MO,QTY_1_MO&COMM_LVL=HS4&I_COMMODITY=${hsCode.code}&time=${currentYear}`;

    const res = await fetch(url, {
      headers: {
        "User-Agent": "ZINC-Fusion/1.0 (agricultural-research)",
        Accept: "application/json",
      },
      signal: controller.signal,
    });

    if (!res.ok) {
      console.warn(`Census API returned ${res.status} for HS ${hsCode.code}`);
      return [];
    }

    const data: string[][] = await res.json();
    if (!Array.isArray(data) || data.length < 2) return [];

    const headers = data[0];
    const rows = data.slice(1);

    const records: GATSRecord[] = [];

    for (const row of rows) {
      const obj: Record<string, string> = {};
      headers.forEach((h, i) => {
        obj[h] = row[i] || "";
      });

      const timeMatch = (obj.time || "").match(/(\d{4})-(\d{2})/);
      if (!timeMatch) continue;

      const reportMonth = `${timeMatch[1]}-${timeMatch[2]}-01`;
      const valueUsd = parseFloat(obj.ALL_VAL_MO || "0");
      const quantityKg = parseFloat(obj.QTY_1_MO || "0");
      const quantityMt = quantityKg / 1000;

      if (valueUsd === 0 && quantityMt === 0) continue;

      records.push({
        reportMonth,
        commodity: hsCode.description,
        symbol: hsCode.symbol,
        partnerCountry: obj.CTY_NAME || "Unknown",
        valueUsd: isFinite(valueUsd) ? valueUsd : 0,
        quantityMt: isFinite(quantityMt) ? quantityMt : 0,
        flow: "export",
      });
    }

    return records;
  } catch (err) {
    console.warn(`Census fallback failed for ${hsCode.code}: ${err}`);
    return [];
  } finally {
    clearTimeout(timeout);
  }
}

// ---------------------------------------------------------------------------
// Inngest Function
// ---------------------------------------------------------------------------

export const fasGatsTradeMonthly = inngest.createFunction(
  {
    id: "fas-gats-trade-monthly",
    name: "FAS GATS Soybean Complex Trade",
    retries: 2,
    concurrency: [DB_CONCURRENCY],
  },
  [{ cron: "0 10 25 * *" }, { event: "fas/gats-trade-monthly" }],
  async ({ step, logger }) => {
    logger.info("Fetching US soybean complex trade data (FAS GATS + Census)");

    // Step 1: Assert Prisma migration contract is present
    await step.run("assert-table-contract", async () => {
      const client = await pool.connect();
      try {
        const { rows } = await client.query<{
          regclass_name: string | null;
        }>(`SELECT to_regclass('supply.fas_gats_1m')::text AS regclass_name`);
        if (!rows[0]?.regclass_name) {
          throw new Error(
            "Missing table supply.fas_gats_1m. Apply Prisma migrations before running fas-gats-trade-monthly."
          );
        }
      } finally {
        client.release();
      }
    });

    const allRecords: GATSRecord[] = [];

    // Step 2: Fetch each commodity
    for (const hsCode of TRADE_HS_CODES) {
      const records = await step.run(`fetch-${hsCode.symbol}`, async () => {
        // Try GATS first
        let data = await fetchGATSData(hsCode);

        if (data.length === 0) {
          // Fallback to Census Bureau
          logger.info(`GATS returned 0 for ${hsCode.code}, trying Census fallback`);
          data = await fetchCensusFallback(hsCode);
        }

        logger.info(`${hsCode.description}: ${data.length} trade records`);
        return data;
      });

      allRecords.push(...records);

      // Rate limit between commodities
      if (hsCode !== TRADE_HS_CODES[TRADE_HS_CODES.length - 1]) {
        await step.sleep(`delay-after-${hsCode.symbol}`, "2s");
      }
    }

    // Step 3: Upsert
    const result = await step.run("upsert-trade-data", async () => {
      const client = await pool.connect();
      let inserted = 0;
      let skipped = 0;

      try {
        for (const record of allRecords) {
          const rowHash = createHash("sha256")
            .update(
              `${record.reportMonth}|${record.symbol}|${record.partnerCountry}|${record.flow}|${record.quantityMt}|${record.valueUsd}`,
            )
            .digest("hex");

          const prev = await client.query(
            `SELECT row_hash FROM supply.fas_gats_1m
             WHERE report_month = $1 AND symbol = $2 AND partner_country = $3 AND flow = $4`,
            [record.reportMonth, record.symbol, record.partnerCountry, record.flow],
          );

          if (prev.rows.length > 0 && prev.rows[0].row_hash === rowHash) {
            skipped++;
            continue;
          }

          await client.query(
            `INSERT INTO supply.fas_gats_1m
              (report_month, commodity, symbol, partner_country, value_usd, quantity_mt,
               flow, source, specialist_tags, row_hash, ingested_at)
             VALUES ($1, $2, $3, $4, $5, $6, $7, 'fas_gats', '{tariff,china,crush}', $8, NOW())
             ON CONFLICT (report_month, symbol, partner_country, flow) DO UPDATE SET
               value_usd = $5,
               quantity_mt = $6,
               commodity = $2,
               row_hash = $8,
               ingested_at = NOW()`,
            [
              record.reportMonth,
              record.commodity,
              record.symbol,
              record.partnerCountry,
              record.valueUsd,
              record.quantityMt,
              record.flow,
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
      `FAS GATS: inserted=${result.inserted}, skipped=${result.skipped}`,
    );

    return {
      status: "success",
      source: "FAS GATS + Census Bureau",
      commodities: TRADE_HS_CODES.map((c) => c.description),
      totalRecords: allRecords.length,
      keyPartners: KEY_PARTNERS,
      ...result,
    };
  },
);
