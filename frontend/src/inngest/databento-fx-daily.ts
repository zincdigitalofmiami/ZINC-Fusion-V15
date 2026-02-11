/**
 * Databento FX Futures Daily Ingestion
 *
 * Fetches daily OHLCV + open interest for CME FX futures:
 * - 6E (EUR/USD), 6J (USD/JPY), 6B (GBP/USD), 6A (AUD/USD)
 * - 6C (CAD/USD), 6M (MXN/USD), 6N (NZD/USD), 6S (CHF/USD)
 *
 * Trump Effect specialist uses these for policy/tariff impact on FX pairs.
 *
 * Writes to: mkt.futures_1d (source='databento')
 *
 * @author Agent3
 * @date 2026-01-30
 */

import { inngest, DB_CONCURRENCY } from "./client";
import { fetchDatabentoCsv, parseDatabentoOhlcvCsv, parseDatabentoStatisticsCsv } from "@/lib/databento";
import { createHash } from "crypto";
import dbPool from "@/lib/db";

const pool = dbPool;

// FX Futures symbols - continuous front month (calendar roll)
const FX_SYMBOLS = [
  // Major USD pairs
  { continuous: "6E.c.0", canonical: "6E", name: "EUR/USD", pair: "EURUSD" },
  { continuous: "6J.c.0", canonical: "6J", name: "USD/JPY", pair: "USDJPY" },
  { continuous: "6B.c.0", canonical: "6B", name: "GBP/USD", pair: "GBPUSD" },
  { continuous: "6A.c.0", canonical: "6A", name: "AUD/USD", pair: "AUDUSD" },
  { continuous: "6C.c.0", canonical: "6C", name: "USD/CAD", pair: "USDCAD" },
  // Emerging market pairs
  { continuous: "6M.c.0", canonical: "6M", name: "MXN/USD", pair: "USDMXN" },
  // Other majors
  { continuous: "6N.c.0", canonical: "6N", name: "NZD/USD", pair: "NZDUSD" },
  { continuous: "6S.c.0", canonical: "6S", name: "USD/CHF", pair: "USDCHF" },
  // Dollar Index
  { continuous: "DX.c.0", canonical: "DX", name: "US Dollar Index", pair: "DXY" },
];

interface SymbolResult {
  symbol: string;
  status: "success" | "error" | "no_data";
  ohlcvRows?: number;
  oiRows?: number;
  error?: string;
}

function computeRowHash(
  symbol: string,
  eventDate: Date,
  open: number,
  high: number,
  low: number,
  close: number,
  volume: number
): string {
  const key = `${symbol}|${eventDate.toISOString().split("T")[0]}|${open}|${high}|${low}|${close}|${volume}`;
  return createHash("md5").update(key).digest("hex");
}

/**
 * Upsert FX futures OHLCV into mkt.futures_1d
 */
async function upsertFxOhlcv(
  symbol: string,
  eventDate: Date,
  open: number,
  high: number,
  low: number,
  close: number,
  volume: number
): Promise<void> {
  const client = await pool.connect();
  const rowHash = computeRowHash(symbol, eventDate, open, high, low, close, volume);

  try {
    await client.query(
      `INSERT INTO mkt.futures_1d
        (event_date, symbol, open, high, low, close, volume, source, ingested_at, row_hash)
       VALUES ($1, $2, $3, $4, $5, $6, $7, 'databento', NOW(), $8)
       ON CONFLICT (event_date, symbol) DO UPDATE SET
         open = EXCLUDED.open,
         high = EXCLUDED.high,
         low = EXCLUDED.low,
         close = EXCLUDED.close,
         volume = EXCLUDED.volume,
         source = 'databento',
         ingested_at = NOW(),
         row_hash = EXCLUDED.row_hash
       WHERE mkt.futures_1d.source = 'databento' OR mkt.futures_1d.source IS NULL`,
      [eventDate, symbol, open, high, low, close, volume, rowHash]
    );
  } finally {
    client.release();
  }
}

/**
 * Upsert FX futures open interest into mkt.futures_1d
 */
async function upsertFxOpenInterest(
  symbol: string,
  eventDate: Date,
  openInterest: number
): Promise<void> {
  const client = await pool.connect();
  try {
    await client.query(
      `INSERT INTO mkt.futures_1d
        (event_date, symbol, open_interest, source, ingested_at)
       VALUES ($1, $2, $3, 'databento', NOW())
       ON CONFLICT (event_date, symbol) DO UPDATE SET
         open_interest = EXCLUDED.open_interest,
         source = CASE
           WHEN mkt.futures_1d.source = 'databento' OR mkt.futures_1d.source IS NULL
           THEN 'databento'
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

export const databentoFxDaily = inngest.createFunction(
  {
    id: "databento-fx-daily",
    name: "Databento FX Futures Daily (OHLCV + OI)",
    retries: 3,
    concurrency: [DB_CONCURRENCY],
  },
  { cron: "TZ=America/Chicago 15 6 * * *" }, // Daily at 06:15 CT
  async ({ step, logger }) => {
    const results: SymbolResult[] = [];

    for (const config of FX_SYMBOLS) {
      await step.run(`fetch-fx-${config.canonical}`, async () => {
        try {
          // Fetch last 5 days for robustness
          const endDate = new Date();
          endDate.setUTCDate(endDate.getUTCDate() - 1);
          endDate.setUTCHours(0, 0, 0, 0);

          const startDate = new Date(endDate);
          startDate.setUTCDate(startDate.getUTCDate() - 5);

          logger.info(
            `Fetching FX OHLCV for ${config.canonical} (${config.continuous}) from ${startDate.toISOString()} to ${endDate.toISOString()}`
          );

          // 1. Fetch OHLCV
          const ohlcvCsv = await fetchDatabentoCsv({
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

          const bars = parseDatabentoOhlcvCsv(ohlcvCsv);
          let ohlcvUpserted = 0;

          for (const bar of bars) {
            const eventDate = new Date(Date.UTC(
              bar.tsEvent.getUTCFullYear(),
              bar.tsEvent.getUTCMonth(),
              bar.tsEvent.getUTCDate()
            ));

            await upsertFxOhlcv(
              config.canonical,
              eventDate,
              bar.open,
              bar.high,
              bar.low,
              bar.close,
              bar.volume
            );
            ohlcvUpserted++;
          }

          logger.info(`Upserted ${ohlcvUpserted} OHLCV rows for ${config.canonical}`);

          // 2. Fetch statistics (open interest)
          const statsCsv = await fetchDatabentoCsv({
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

          const statsBars = parseDatabentoStatisticsCsv(statsCsv);
          let oiUpserted = 0;

          for (const bar of statsBars) {
            const eventDate = new Date(Date.UTC(
              bar.tsEvent.getUTCFullYear(),
              bar.tsEvent.getUTCMonth(),
              bar.tsEvent.getUTCDate()
            ));

            await upsertFxOpenInterest(config.canonical, eventDate, bar.openInterest);
            oiUpserted++;
          }

          logger.info(`Upserted ${oiUpserted} OI rows for ${config.canonical}`);

          results.push({
            symbol: config.canonical,
            status: ohlcvUpserted > 0 || oiUpserted > 0 ? "success" : "no_data",
            ohlcvRows: ohlcvUpserted,
            oiRows: oiUpserted,
          });
        } catch (err) {
          const errorMsg = err instanceof Error ? err.message : String(err);
          logger.error(`Failed to fetch FX data for ${config.canonical}: ${errorMsg}`);
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
