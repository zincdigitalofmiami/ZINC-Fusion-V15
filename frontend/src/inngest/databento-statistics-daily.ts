/**
 * Databento Statistics Daily (Open Interest) Ingestion
 * 
 * Fetches open interest statistics from Databento GLBX.MDP3 dataset.
 * Uses stat_type=9 (open interest) from statistics schema.
 * 
 * Upserts open_interest into mkt.futures_1d, creating stub rows if OHLCV job failed.
 * Always fetches last 5 days for robustness (handles timing edge cases).
 */

import { inngest } from "./client";
import pool from "@/lib/db";
import { fetchDatabentoCsv, parseDatabentoStatisticsCsv } from "@/lib/databento";

// Symbols to fetch: match OHLCV function (Crush uses .n.0, Energy/Metals use .c.0)
// Top 50 CME symbols per Databento catalog
const DATABENTO_SYMBOLS = [
  // Soybean complex (Crush) - OI-ranked
  { continuous: "ZL.n.0", canonical: "ZL", name: "Soybean Oil" },
  { continuous: "ZS.n.0", canonical: "ZS", name: "Soybeans" },
  { continuous: "ZM.n.0", canonical: "ZM", name: "Soybean Meal" },
  // Grains - calendar-ranked
  { continuous: "ZC.c.0", canonical: "ZC", name: "Corn" },
  { continuous: "ZW.c.0", canonical: "ZW", name: "Wheat" },
  // Energy - calendar-ranked
  { continuous: "CL.c.0", canonical: "CL", name: "Crude Oil" },
  { continuous: "NG.c.0", canonical: "NG", name: "Natural Gas" },
  { continuous: "HO.c.0", canonical: "HO", name: "Heating Oil" },
  { continuous: "RB.c.0", canonical: "RB", name: "RBOB Gasoline" },
  { continuous: "BZ.c.0", canonical: "BZ", name: "Brent Crude" },
  // Metals (COMEX/NYMEX) - calendar-ranked
  { continuous: "GC.c.0", canonical: "GC", name: "Gold" },
  { continuous: "SI.c.0", canonical: "SI", name: "Silver" },
  { continuous: "HG.c.0", canonical: "HG", name: "Copper" },
  { continuous: "PL.c.0", canonical: "PL", name: "Platinum" },
  { continuous: "PA.c.0", canonical: "PA", name: "Palladium" },
  // Equity Indices - calendar-ranked
  { continuous: "ES.c.0", canonical: "ES", name: "E-mini S&P 500" },
  { continuous: "NQ.c.0", canonical: "NQ", name: "E-mini Nasdaq 100" },
  { continuous: "YM.c.0", canonical: "YM", name: "Mini Dow" },
  { continuous: "RTY.c.0", canonical: "RTY", name: "E-mini Russell 2000" },
  // Treasury Futures - calendar-ranked
  { continuous: "ZN.c.0", canonical: "ZN", name: "10-Year Treasury" },
  { continuous: "ZB.c.0", canonical: "ZB", name: "30-Year Treasury" },
  { continuous: "ZF.c.0", canonical: "ZF", name: "5-Year Treasury" },
  { continuous: "ZT.c.0", canonical: "ZT", name: "2-Year Treasury" },
  // Livestock - calendar-ranked
  { continuous: "HE.c.0", canonical: "HE", name: "Lean Hogs" },
  { continuous: "LE.c.0", canonical: "LE", name: "Live Cattle" },
  { continuous: "GF.c.0", canonical: "GF", name: "Feeder Cattle" },
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
  openInterest: number
): Promise<void> {
  const client = await pool.connect();
  try {
    // Upsert: insert stub if missing, update if exists (but don't overwrite Yahoo rows)
    await client.query(
      `INSERT INTO mkt.futures_1d
        (event_date, symbol, open_interest, source, ingested_at)
       VALUES ($1, $2, $3, 'databento', NOW())
       ON CONFLICT (event_date, symbol) DO UPDATE SET
         open_interest = EXCLUDED.open_interest,
         source = CASE 
           WHEN mkt.futures_1d.source = 'databento' OR mkt.futures_1d.source IS NULL 
           THEN EXCLUDED.source 
           ELSE mkt.futures_1d.source 
         END,
         ingested_at = NOW()
       WHERE mkt.futures_1d.source = 'databento' OR mkt.futures_1d.source IS NULL`,
      [eventDate, symbol, openInterest]
    );
  } finally {
    client.release();
  }
}

export const databentoStatisticsDaily = inngest.createFunction(
  {
    id: "databento-statistics-daily",
    name: "Databento Statistics Daily (Open Interest)",
    retries: 3,
    concurrency: [{ limit: 1 }],
  },
  { cron: "TZ=America/Chicago 30 */8 * * *" }, // Every 8 hours at :30 (0:30, 8:30, 16:30 CT)
  async ({ step, logger }) => {
    const results: SymbolResult[] = [];

    for (const config of DATABENTO_SYMBOLS) {
      await step.run(`fetch-stats-${config.canonical}`, async () => {
        try {
          // Always fetch last 5 days for robustness (handles timing edge cases)
          const endDate = new Date();
          endDate.setUTCDate(endDate.getUTCDate() - 1); // Subtract 24h for historical API lag
          endDate.setUTCHours(0, 0, 0, 0);

          const startDate = new Date(endDate);
          startDate.setUTCDate(startDate.getUTCDate() - 5); // Last 5 days

          logger.info(
            `Fetching OI stats for ${config.canonical} (${config.continuous}) from ${startDate.toISOString()} to ${endDate.toISOString()}`
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
            results.push({
              symbol: config.canonical,
              status: "no_data",
            });
            return;
          }

          // Upsert each bar
          let upserted = 0;
          for (const bar of bars) {
            const eventDate = new Date(Date.UTC(
              bar.tsEvent.getUTCFullYear(),
              bar.tsEvent.getUTCMonth(),
              bar.tsEvent.getUTCDate()
            ));

            await upsertOpenInterest(config.canonical, eventDate, bar.openInterest);
            upserted++;
          }

          logger.info(`Upserted ${upserted} OI rows for ${config.canonical}`);
          results.push({
            symbol: config.canonical,
            status: "success",
            rowsUpserted: upserted,
          });
        } catch (err) {
          const errorMsg = err instanceof Error ? err.message : String(err);
          logger.error(`Failed to fetch/upsert OI stats for ${config.canonical}: ${errorMsg}`);
          results.push({
            symbol: config.canonical,
            status: "error",
            error: errorMsg,
          });
        }
      });
    }

    return {
      status: "complete",
      timestamp: new Date().toISOString(),
      results,
      successCount: results.filter((r) => r.status === "success").length,
      errorCount: results.filter((r) => r.status === "error").length,
      noDataCount: results.filter((r) => r.status === "no_data").length,
    };
  }
);
