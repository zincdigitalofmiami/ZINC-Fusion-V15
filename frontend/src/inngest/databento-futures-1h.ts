/**
 * Databento Futures 1h OHLCV Ingestion
 *
 * Keeps mkt.futures_1h current for ZL-critical symbols + MES + ES.
 * Runs every 8 hours with a small overlap buffer.
 */

import { inngest, DB_CONCURRENCY } from "./client";
import { fetchDatabentoCsv, parseDatabentoOhlcvCsv } from "@/lib/databento";
import { createHash } from "crypto";
import dbPool from "@/lib/db";

const pool = dbPool;

const SYMBOLS = [
  { continuous: "ZL.n.0", canonical: "ZL", name: "Soybean Oil" },
  { continuous: "ZS.n.0", canonical: "ZS", name: "Soybeans" },
  { continuous: "ZM.n.0", canonical: "ZM", name: "Soybean Meal" },
  { continuous: "ZC.c.0", canonical: "ZC", name: "Corn" },
  { continuous: "ZW.c.0", canonical: "ZW", name: "Wheat" },
  { continuous: "6B.c.0", canonical: "6B", name: "GBP/USD" },
  { continuous: "6J.c.0", canonical: "6J", name: "USD/JPY" },
  { continuous: "6L.c.0", canonical: "6L", name: "BRL/USD" },
  { continuous: "6M.c.0", canonical: "6M", name: "MXN/USD" },
  { continuous: "MES.c.0", canonical: "MES", name: "Micro E-mini S&P" },
  { continuous: "ES.c.0", canonical: "ES", name: "E-mini S&P 500" },
];

const BUFFER_HOURS = 48;
const END_LAG_HOURS = 1;
const DEFAULT_LOOKBACK_DAYS = 5;

async function getMaxEventTime(symbol: string): Promise<Date | null> {
  const client = await pool.connect();
  try {
    const result = await client.query(
      `SELECT MAX(event_time) AS max_time
       FROM mkt.futures_1h
       WHERE symbol = $1`,
      [symbol]
    );
    const maxTime = result.rows[0]?.max_time;
    return maxTime ? new Date(maxTime) : null;
  } finally {
    client.release();
  }
}

function computeRowHash(
  symbol: string,
  eventTime: Date,
  open: number | null,
  high: number | null,
  low: number | null,
  close: number | null,
  volume: number | null
): string {
  const key = `${symbol}|${eventTime.toISOString()}|${open ?? ""}|${high ?? ""}|${low ?? ""}|${close ?? ""}|${volume ?? ""}`;
  return createHash("sha256").update(key).digest("hex");
}

async function upsertBars(
  symbol: string,
  bars: { eventTime: Date; open: number; high: number; low: number; close: number; volume: number }[]
): Promise<number> {
  if (bars.length === 0) return 0;
  const client = await pool.connect();
  let written = 0;
  try {
    for (const bar of bars) {
      const rowHash = computeRowHash(
        symbol,
        bar.eventTime,
        bar.open,
        bar.high,
        bar.low,
        bar.close,
        bar.volume
      );

      await client.query(
        `INSERT INTO mkt.futures_1h
          (symbol, event_time, open, high, low, close, volume, source, ingested_at, knowledge_time, row_hash)
         VALUES ($1, $2, $3, $4, $5, $6, $7, 'databento', NOW(), NOW(), $8)
         ON CONFLICT (symbol, event_time) DO UPDATE SET
           open = EXCLUDED.open,
           high = EXCLUDED.high,
           low = EXCLUDED.low,
           close = EXCLUDED.close,
           volume = EXCLUDED.volume,
           source = 'databento',
           ingested_at = NOW(),
           knowledge_time = NOW(),
           row_hash = EXCLUDED.row_hash`,
        [symbol, bar.eventTime, bar.open, bar.high, bar.low, bar.close, bar.volume, rowHash]
      );
      written++;
    }
  } finally {
    client.release();
  }
  return written;
}

export const databentoFutures1h = inngest.createFunction(
  {
    id: "databento-futures-1h",
    name: "Databento Futures 1h OHLCV",
    retries: 3,
    concurrency: [DB_CONCURRENCY],
  },
  { cron: "TZ=America/Chicago 30 */8 * * *" },
  async ({ step, logger }) => {
    const results: { symbol: string; status: string; rows?: number; error?: string }[] = [];

    for (const config of SYMBOLS) {
      await step.run(`fetch-1h-${config.canonical}`, async () => {
        try {
          const maxTime = await getMaxEventTime(config.canonical);
          const end = new Date(Date.now() - END_LAG_HOURS * 60 * 60 * 1000);
          const start = maxTime
            ? new Date(maxTime.getTime() - BUFFER_HOURS * 60 * 60 * 1000)
            : new Date(end.getTime() - DEFAULT_LOOKBACK_DAYS * 24 * 60 * 60 * 1000);

          if (start >= end) {
            results.push({ symbol: config.canonical, status: "skipped" });
            return;
          }

          logger.info(
            `Fetching 1h ${config.canonical} (${config.continuous}) from ${start.toISOString()} to ${end.toISOString()}`
          );

          const csv = await fetchDatabentoCsv({
            dataset: "GLBX.MDP3",
            schema: "ohlcv-1h",
            symbols: config.continuous,
            stype_in: "continuous",
            start: start.toISOString(),
            end: end.toISOString(),
            encoding: "csv",
            pretty_ts: "true",
            pretty_px: "true",
          });

          const parsed = parseDatabentoOhlcvCsv(csv);
          const bars = parsed.map((bar) => ({
            eventTime: bar.tsEvent,
            open: bar.open,
            high: bar.high,
            low: bar.low,
            close: bar.close,
            volume: bar.volume ?? 0,
          }));

          if (bars.length === 0) {
            results.push({ symbol: config.canonical, status: "no_data" });
            return;
          }

          const written = await upsertBars(config.canonical, bars);
          results.push({ symbol: config.canonical, status: "success", rows: written });
        } catch (err) {
          const message = err instanceof Error ? err.message : String(err);
          results.push({ symbol: config.canonical, status: "error", error: message });
        }
      });
    }

    return { status: "complete", results };
  }
);
