/**
 * Databento Futures Daily OHLCV Ingestion
 *
 * Fetches continuous contract OHLCV data from Databento GLBX.MDP3 dataset.
 * Uses open-interest-ranked (.n.0) for Crush-relevant symbols (ZL/ZS/ZM) to ensure
 * price/volume/OI all refer to the same contract.
 *
 * Incremental ingestion: checks MAX(event_date) and fetches only new data.
 * Handles "no new rows" gracefully (historical API may lag by 24h).
 */

import { inngest, DB_CONCURRENCY } from "./client";
import { fetchDatabentoCsv, parseDatabentoOhlcvCsv } from "@/lib/databento";
import { createHash } from "crypto";
import dbPool from "@/lib/db";

const pool = dbPool;

// Symbols to fetch from GLBX.MDP3 (CME Globex, COMEX, NYMEX)
// Crush-relevant use .n.0 (open-interest-ranked), Energy/Metals use .c.0 (calendar)
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
  { cron: "TZ=America/Chicago 0 */8 * * *" }, // Every 8 hours (0:00, 8:00, 16:00 CT)
  async ({ step, logger }) => {
    const results: SymbolResult[] = [];

    for (const config of DATABENTO_SYMBOLS) {
      await step.run(`fetch-${config.canonical}`, async () => {
        try {
          // Get incremental window: start = max_date + 1 day, end = now minus 24h
          const maxDate = await getMaxEventDate(config.canonical);
          const endDate = new Date();
          endDate.setUTCDate(endDate.getUTCDate() - 1); // Subtract 24h for historical API lag
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
            results.push({
              symbol: config.canonical,
              status: "skipped",
            });
            return;
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
            results.push({
              symbol: config.canonical,
              status: "no_data",
            });
            return;
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
          results.push({
            symbol: config.canonical,
            status: "success",
            rowsInserted: inserted,
          });
        } catch (err) {
          const errorMsg = err instanceof Error ? err.message : String(err);
          logger.error(`Failed to fetch/insert ${config.canonical}: ${errorMsg}`);
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
      skippedCount: results.filter((r) => r.status === "skipped" || r.status === "no_data").length,
    };
  }
);
