/**
 * Databento Statistics Daily (Open Interest) Ingestion
 *
 * Fetches open interest statistics from Databento GLBX.MDP3 dataset.
 * Uses stat_type=9 (open interest) from statistics schema.
 *
 * Upserts open_interest into mkt.futures_1d, creating stub rows if OHLCV job failed.
 * Always fetches last 5 days for robustness (handles timing edge cases).
 */

import { inngest, DB_CONCURRENCY } from "./client";
import {
  fetchDatabentoCsv,
  parseDatabentoStatisticsCsv,
} from "@/lib/databento";
import dbPool from "@/lib/db";

const pool = dbPool;

// All GLBX.MDP3 symbols — mirrors databento-futures-daily.ts
// Crush uses .n.0 (OI-ranked), everything else uses .c.0 (calendar)
const DATABENTO_SYMBOLS = [
  // ── Soybean complex (Crush) — OI-ranked ──
  { continuous: "ZL.n.0", canonical: "ZL", name: "Soybean Oil" },
  { continuous: "ZS.n.0", canonical: "ZS", name: "Soybeans" },
  { continuous: "ZM.n.0", canonical: "ZM", name: "Soybean Meal" },
  // ── Grains ──
  { continuous: "ZC.c.0", canonical: "ZC", name: "Corn" },
  { continuous: "ZW.c.0", canonical: "ZW", name: "Wheat" },
  { continuous: "KE.c.0", canonical: "KE", name: "KC HRW Wheat" },
  { continuous: "ZR.c.0", canonical: "ZR", name: "Rough Rice" },
  { continuous: "ZO.c.0", canonical: "ZO", name: "Oats" },
  // ── Mini Grains ──
  { continuous: "XC.c.0", canonical: "XC", name: "Mini Corn" },
  { continuous: "XW.c.0", canonical: "XW", name: "Mini Wheat" },
  { continuous: "XK.c.0", canonical: "XK", name: "Mini Soybeans" },
  // ── Energy ──
  { continuous: "CL.c.0", canonical: "CL", name: "Crude Oil" },
  { continuous: "NG.c.0", canonical: "NG", name: "Natural Gas" },
  { continuous: "HO.c.0", canonical: "HO", name: "Heating Oil" },
  { continuous: "RB.c.0", canonical: "RB", name: "RBOB Gasoline" },
  { continuous: "BZ.c.0", canonical: "BZ", name: "Brent Crude" },
  // ── E-mini / Micro Energy ──
  { continuous: "QM.c.0", canonical: "QM", name: "E-mini Crude Oil" },
  { continuous: "QG.c.0", canonical: "QG", name: "E-mini Natural Gas" },
  { continuous: "QH.c.0", canonical: "QH", name: "E-mini Heating Oil" },
  { continuous: "QU.c.0", canonical: "QU", name: "E-mini Gasoline" },
  { continuous: "MCL.c.0", canonical: "MCL", name: "Micro Crude Oil" },
  // ── Metals (COMEX/NYMEX) ──
  { continuous: "GC.c.0", canonical: "GC", name: "Gold" },
  { continuous: "SI.c.0", canonical: "SI", name: "Silver" },
  { continuous: "HG.c.0", canonical: "HG", name: "Copper" },
  { continuous: "PL.c.0", canonical: "PL", name: "Platinum" },
  { continuous: "PA.c.0", canonical: "PA", name: "Palladium" },
  { continuous: "ALI.c.0", canonical: "ALI", name: "Aluminum" },
  // ── Micro Metals ──
  { continuous: "MGC.c.0", canonical: "MGC", name: "Micro Gold" },
  { continuous: "QI.c.0", canonical: "QI", name: "E-mini Silver" },
  { continuous: "QO.c.0", canonical: "QO", name: "E-mini Gold" },
  // ── Equity Indices ──
  { continuous: "ES.c.0", canonical: "ES", name: "E-mini S&P 500" },
  { continuous: "NQ.c.0", canonical: "NQ", name: "E-mini Nasdaq 100" },
  { continuous: "YM.c.0", canonical: "YM", name: "Mini Dow" },
  { continuous: "RTY.c.0", canonical: "RTY", name: "E-mini Russell 2000" },
  { continuous: "EMD.c.0", canonical: "EMD", name: "E-mini S&P MidCap 400" },
  { continuous: "NIY.c.0", canonical: "NIY", name: "Nikkei 225 Yen" },
  // ── Micro Indices ──
  { continuous: "MES.c.0", canonical: "MES", name: "Micro E-mini S&P 500" },
  { continuous: "MNQ.c.0", canonical: "MNQ", name: "Micro E-mini Nasdaq 100" },
  { continuous: "MYM.c.0", canonical: "MYM", name: "Micro E-mini Dow" },
  {
    continuous: "M2K.c.0",
    canonical: "M2K",
    name: "Micro E-mini Russell 2000",
  },
  // ── Treasury Futures ──
  { continuous: "ZN.c.0", canonical: "ZN", name: "10-Year Treasury" },
  { continuous: "ZB.c.0", canonical: "ZB", name: "30-Year Treasury" },
  { continuous: "ZF.c.0", canonical: "ZF", name: "5-Year Treasury" },
  { continuous: "ZT.c.0", canonical: "ZT", name: "2-Year Treasury" },
  { continuous: "UB.c.0", canonical: "UB", name: "Ultra T-Bond" },
  { continuous: "TN.c.0", canonical: "TN", name: "Ultra 10-Year" },
  { continuous: "TT.c.0", canonical: "TT", name: "TN Ultra 10-Year Note" },
  // ── Micro Treasuries ──
  { continuous: "10Y.c.0", canonical: "10Y", name: "Micro 10-Year Yield" },
  { continuous: "2YY.c.0", canonical: "2YY", name: "Micro 2-Year Yield" },
  { continuous: "30Y.c.0", canonical: "30Y", name: "Micro 30-Year Yield" },
  { continuous: "5YY.c.0", canonical: "5YY", name: "Micro 5-Year Yield" },
  // ── FX Futures ──
  { continuous: "6E.c.0", canonical: "6E", name: "Euro FX" },
  { continuous: "6J.c.0", canonical: "6J", name: "Japanese Yen" },
  { continuous: "6B.c.0", canonical: "6B", name: "British Pound" },
  { continuous: "6C.c.0", canonical: "6C", name: "Canadian Dollar" },
  { continuous: "6A.c.0", canonical: "6A", name: "Australian Dollar" },
  { continuous: "6S.c.0", canonical: "6S", name: "Swiss Franc" },
  { continuous: "6N.c.0", canonical: "6N", name: "New Zealand Dollar" },
  { continuous: "6M.c.0", canonical: "6M", name: "Mexican Peso" },
  { continuous: "6L.c.0", canonical: "6L", name: "Brazilian Real" },
  { continuous: "6Z.c.0", canonical: "6Z", name: "South African Rand" },
  { continuous: "6R.c.0", canonical: "6R", name: "Russian Ruble" },
  // ── Micro FX ──
  { continuous: "M6E.c.0", canonical: "M6E", name: "Micro Euro FX" },
  { continuous: "M6A.c.0", canonical: "M6A", name: "Micro AUD/USD" },
  { continuous: "M6B.c.0", canonical: "M6B", name: "Micro GBP/USD" },
  // ── Rates ──
  { continuous: "ZQ.c.0", canonical: "ZQ", name: "30-Day Fed Funds" },
  { continuous: "GE.c.0", canonical: "GE", name: "Eurodollar" },
  { continuous: "SR1.c.0", canonical: "SR1", name: "1-Month SOFR" },
  { continuous: "SR3.c.0", canonical: "SR3", name: "3-Month SOFR" },
  // ── Livestock ──
  { continuous: "HE.c.0", canonical: "HE", name: "Lean Hogs" },
  { continuous: "LE.c.0", canonical: "LE", name: "Live Cattle" },
  { continuous: "GF.c.0", canonical: "GF", name: "Feeder Cattle" },
  // ── Dairy ──
  { continuous: "DY.c.0", canonical: "DY", name: "Dry Whey" },
  { continuous: "DC.c.0", canonical: "DC", name: "Milk Class III" },
  // ── Crypto ──
  { continuous: "BTC.c.0", canonical: "BTC", name: "Bitcoin" },
  { continuous: "ETH.c.0", canonical: "ETH", name: "Ether" },
  { continuous: "MBT.c.0", canonical: "MBT", name: "Micro Bitcoin" },
  { continuous: "MET.c.0", canonical: "MET", name: "Micro Ether" },
  // ── Other ──
  { continuous: "LBR.c.0", canonical: "LBR", name: "Lumber" },
];

interface SymbolResult {
  symbol: string;
  status: "success" | "error" | "no_data";
  rowsUpserted?: number;
  error?: string;
}

/**
 * Upsert open interest into mkt.futures_1d
 * Creates stub row if missing, updates if exists
 */
async function upsertOpenInterest(
  symbol: string,
  eventDate: Date,
  openInterest: number,
): Promise<void> {
  const client = await pool.connect();
  try {
    // Databento is the sole source — always upsert
    await client.query(
      `INSERT INTO mkt.futures_1d
        (event_date, symbol, open_interest, source, ingested_at)
       VALUES ($1, $2, $3, 'databento', NOW())
       ON CONFLICT (event_date, symbol) DO UPDATE SET
         open_interest = EXCLUDED.open_interest,
         source = 'databento',
         ingested_at = NOW()`,
      [eventDate, symbol, openInterest],
    );
  } finally {
    client.release();
  }
}

// Split 84 symbols into batches for resilience — each batch is a separate
// step.run() so Inngest can retry individual batches on failure.
const BATCH_SIZE = 21;
function chunkArray<T>(arr: T[], size: number): T[][] {
  const chunks: T[][] = [];
  for (let i = 0; i < arr.length; i += size) {
    chunks.push(arr.slice(i, i + size));
  }
  return chunks;
}

async function fetchStatsBatch(
  batch: typeof DATABENTO_SYMBOLS,
  logger: { info: (msg: string) => void; error: (msg: string) => void; warn?: (msg: string) => void },
): Promise<SymbolResult[]> {
  const batchResults: SymbolResult[] = [];

  for (const config of batch) {
    try {
      const endDate = new Date();
      endDate.setUTCHours(0, 0, 0, 0);

      const startDate = new Date(endDate);
      startDate.setUTCDate(startDate.getUTCDate() - 5);

      logger.info(
        `Fetching OI stats for ${config.canonical} (${config.continuous}) from ${startDate.toISOString()} to ${endDate.toISOString()}`,
      );

      const csv = await fetchDatabentoCsv({
        dataset: "GLBX.MDP3",
        schema: "statistics",
        symbols: config.continuous,
        stype_in: "continuous",
        start: startDate.toISOString(),
        end: endDate.toISOString(),
        encoding: "csv",
        pretty_ts: "true",
        pretty_px: "true",
      });

      const bars = parseDatabentoStatisticsCsv(csv);
      if (bars.length === 0) {
        logger.info(`No OI stats returned for ${config.canonical}`);
        batchResults.push({ symbol: config.canonical, status: "no_data" });
        continue;
      }

      let upserted = 0;
      for (const bar of bars) {
        const eventDate = new Date(
          Date.UTC(
            bar.tsEvent.getUTCFullYear(),
            bar.tsEvent.getUTCMonth(),
            bar.tsEvent.getUTCDate(),
          ),
        );

        await upsertOpenInterest(
          config.canonical,
          eventDate,
          bar.openInterest,
        );
        upserted++;
      }

      logger.info(`Upserted ${upserted} OI rows for ${config.canonical}`);
      batchResults.push({
        symbol: config.canonical,
        status: "success",
        rowsUpserted: upserted,
      });
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : String(err);
      logger.error(
        `Failed to fetch/upsert OI stats for ${config.canonical}: ${errorMsg}`,
      );
      batchResults.push({
        symbol: config.canonical,
        status: "error",
        error: errorMsg,
      });
    }
  }

  return batchResults;
}

export const databentoStatisticsDaily = inngest.createFunction(
  {
    id: "databento-statistics-daily",
    name: "Databento Statistics Daily (Open Interest)",
    retries: 3,
    concurrency: [DB_CONCURRENCY],
  },
  { cron: "TZ=America/Chicago 0 4 * * *" }, // Daily at 04:00 CT — runs overnight after options @ 02:00
  async ({ step, logger }) => {
    const batches = chunkArray(DATABENTO_SYMBOLS, BATCH_SIZE);
    const allResults: SymbolResult[] = [];

    for (let i = 0; i < batches.length; i++) {
      const batchSymbols = batches[i].map((s) => s.canonical).join(",");
      const results = await step.run(
        `fetch-stats-batch-${i + 1}-of-${batches.length}`,
        async () => fetchStatsBatch(batches[i], logger),
      );
      allResults.push(...results);
      logger.info(`Batch ${i + 1}/${batches.length} done (${batchSymbols})`);
    }

    return {
      status: "complete",
      timestamp: new Date().toISOString(),
      results: allResults,
      successCount: allResults.filter((r) => r.status === "success").length,
      errorCount: allResults.filter((r) => r.status === "error").length,
      noDataCount: allResults.filter((r) => r.status === "no_data").length,
    };
  },
);
