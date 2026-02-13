/**
 * Databento Futures Daily OHLCV Ingestion
 *
 * Fetches continuous contract OHLCV data from Databento GLBX.MDP3 dataset.
 * Uses open-interest-ranked (.n.0) for Crush-relevant symbols (ZL/ZS/ZM) to ensure
 * price/volume/OI all refer to the same contract.
 *
 * Incremental ingestion: checks MAX(event_date) and fetches only new data.
 * Handles "no new rows" gracefully (API returns empty if data not yet posted).
 */

import { inngest, DB_CONCURRENCY } from "./client";
import { fetchDatabentoCsv, parseDatabentoOhlcvCsv } from "@/lib/databento";
import { createHash } from "crypto";
import dbPool from "@/lib/db";

const pool = dbPool;

// All GLBX.MDP3 (CME Globex, CBOT, COMEX, NYMEX) symbols present in mkt.futures_1d.
// Crush-relevant use .n.0 (OI-ranked), everything else uses .c.0 (calendar).
// Matches the full 84-symbol correlation universe + micro/mini contracts.
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
  { continuous: "M2K.c.0", canonical: "M2K", name: "Micro E-mini Russell 2000" },
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
  status: "success" | "error" | "no_data" | "skipped";
  rowsInserted?: number;
  error?: string;
}

/**
 * Get maximum event_date for a symbol from Databento-sourced rows
 */
async function getMaxEventDate(symbol: string): Promise<Date | null> {
  const client = await pool.connect();
  try {
    const result = await client.query(
      `SELECT MAX(event_date) as max_date
       FROM mkt.futures_1d
       WHERE symbol = $1 AND source = 'databento'`,
      [symbol]
    );
    const maxDate = result.rows[0]?.max_date;
    return maxDate ? new Date(maxDate) : null;
  } finally {
    client.release();
  }
}

/**
 * Compute row_hash for idempotency
 */
function computeRowHash(
  symbol: string,
  eventDate: Date,
  open: number | null,
  high: number | null,
  low: number | null,
  close: number,
  volume: number
): string {
  const dateStr = eventDate.toISOString().split("T")[0];
  const hashInput = `${symbol}|${dateStr}|${open ?? ""}|${high ?? ""}|${low ?? ""}|${close}|${volume}`;
  return createHash("sha256").update(hashInput).digest("hex");
}

/**
 * Upsert OHLCV row into mkt.futures_1d
 */
async function upsertOhlcvRow(
  symbol: string,
  eventDate: Date,
  open: number | null,
  high: number | null,
  low: number | null,
  close: number,
  volume: number,
  rowHash: string
): Promise<void> {
  const client = await pool.connect();
  try {
    // Only update if existing row is from Databento or NULL (don't overwrite Yahoo)
    await client.query(
      `INSERT INTO mkt.futures_1d
        (event_date, symbol, open, high, low, close, volume, source, ingested_at, row_hash)
       VALUES ($1, $2, $3, $4, $5, $6, $7, 'databento', NOW(), $8)
       ON CONFLICT (event_date, symbol) DO UPDATE SET
         open = COALESCE(EXCLUDED.open, mkt.futures_1d.open),
         high = COALESCE(EXCLUDED.high, mkt.futures_1d.high),
         low = COALESCE(EXCLUDED.low, mkt.futures_1d.low),
         close = EXCLUDED.close,
         volume = COALESCE(EXCLUDED.volume, mkt.futures_1d.volume),
         source = CASE
           WHEN mkt.futures_1d.source = 'databento' OR mkt.futures_1d.source IS NULL
           THEN EXCLUDED.source
           ELSE mkt.futures_1d.source
         END,
         ingested_at = NOW(),
         row_hash = EXCLUDED.row_hash
       WHERE mkt.futures_1d.source = 'databento' OR mkt.futures_1d.source IS NULL`,
      [eventDate, symbol, open, high, low, close, volume, rowHash]
    );
  } finally {
    client.release();
  }
}

export const databentoFuturesDaily = inngest.createFunction(
  {
    id: "databento-futures-daily",
    name: "Databento Futures Daily OHLCV",
    retries: 3,
    concurrency: [DB_CONCURRENCY],
  },
  { cron: "TZ=America/Chicago 0 6 * * *" }, // Daily at 06:00 CT
  async ({ step, logger }) => {
    const results = await step.run("fetch-all-symbols-batch", async () => {
      const batchedResults: SymbolResult[] = [];

      for (const config of DATABENTO_SYMBOLS) {
        try {
          // Get incremental window: start = max_date + 1 day, end = today
          // No T-1 offset: job runs 06:00 CT, ~13h after CME close — yesterday's data is available
          const maxDate = await getMaxEventDate(config.canonical);
          const endDate = new Date();
          endDate.setUTCHours(0, 0, 0, 0);

          let startDate: Date;
          if (maxDate) {
            startDate = new Date(maxDate);
            startDate.setUTCDate(startDate.getUTCDate() + 1);
          } else {
            // No existing data: fetch last 30 days
            startDate = new Date(endDate);
            startDate.setUTCDate(startDate.getUTCDate() - 30);
          }

          // Ensure start < end
          if (startDate >= endDate) {
            logger.info(`No new data window for ${config.canonical} (max_date=${maxDate?.toISOString()})`);
            batchedResults.push({
              symbol: config.canonical,
              status: "skipped",
            });
            continue;
          }

          logger.info(
            `Fetching ${config.canonical} (${config.continuous}) from ${startDate.toISOString()} to ${endDate.toISOString()}`
          );

          const csv = await fetchDatabentoCsv({
            dataset: "GLBX.MDP3",
            schema: "ohlcv-1d",
            symbols: config.continuous,
            stype_in: "continuous",
            start: startDate.toISOString(),
            end: endDate.toISOString(),
            encoding: "csv",
            pretty_ts: "true",
            pretty_px: "true",
          });

          const bars = parseDatabentoOhlcvCsv(csv);
          if (bars.length === 0) {
            logger.info(`No bars returned for ${config.canonical}`);
            batchedResults.push({
              symbol: config.canonical,
              status: "no_data",
            });
            continue;
          }

          // Insert each bar
          let inserted = 0;
          for (const bar of bars) {
            const eventDate = new Date(Date.UTC(
              bar.tsEvent.getUTCFullYear(),
              bar.tsEvent.getUTCMonth(),
              bar.tsEvent.getUTCDate()
            ));

            const rowHash = computeRowHash(
              config.canonical,
              eventDate,
              bar.open,
              bar.high,
              bar.low,
              bar.close,
              bar.volume
            );

            await upsertOhlcvRow(
              config.canonical,
              eventDate,
              bar.open,
              bar.high,
              bar.low,
              bar.close,
              bar.volume,
              rowHash
            );
            inserted++;
          }

          logger.info(`Inserted ${inserted} rows for ${config.canonical}`);
          batchedResults.push({
            symbol: config.canonical,
            status: "success",
            rowsInserted: inserted,
          });
        } catch (err) {
          const errorMsg = err instanceof Error ? err.message : String(err);
          logger.error(`Failed to fetch/insert ${config.canonical}: ${errorMsg}`);
          batchedResults.push({
            symbol: config.canonical,
            status: "error",
            error: errorMsg,
          });
        }
      }

      return batchedResults;
    });

    return {
      status: "complete",
      timestamp: new Date().toISOString(),
      results,
      successCount: results.filter((r) => r.status === "success").length,
      errorCount: results.filter((r) => r.status === "error").length,
      skippedCount: results.filter((r) => r.status === "skipped" || r.status === "no_data").length,
    };
  }
);
