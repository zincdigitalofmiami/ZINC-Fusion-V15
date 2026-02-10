/**
 * Databento ETF VWAP Daily Calculator
 *
 * Calculates true VWAP (Volume Weighted Average Price) from intraday trades.
 * Runs after daily ETF OHLCV ingestion to populate VWAP column.
 *
 * VWAP Formula: sum(price * volume) / sum(volume) per trading day
 *
 * Data Source: Databento trades schema
 * - ARCX.PILLAR (NYSE Arca) - Most ETFs
 * - XNAS.ITCH (Nasdaq) - QQQ, TLT, IEF, ICLN, SBLK
 *
 * Why trades instead of statistics?
 * Databento statistics schema does not include VWAP (stat_type=13) for these
 * ETF datasets. Only available stat types are 1, 11, 16 (opening, closing, uncrossing).
 * Per Databento docs, VWAP must be calculated from trades or ohlcv-1m.
 *
 * Schedule: Runs nightly after ETF OHLCV ingestion (8:30 PM ET)
 *
 * @author Claude (ZINC-FUSION-V15)
 * @date 2026-02-03
 */

import { inngest, DB_CONCURRENCY } from "./client";
import {
  fetchDatabentoCsv,
  parseDatabentoOhlcvCsv,
  type DatabentoOhlcvBar,
} from "@/lib/databento";
import dbPool from "@/lib/db";

const pool = dbPool;

// ETF symbols with their Databento datasets
const DATABENTO_ETF_SYMBOLS = [
  // China Complex
  { symbol: "FXI", dataset: "ARCX.PILLAR" },
  { symbol: "KWEB", dataset: "ARCX.PILLAR" },
  { symbol: "MCHI", dataset: "ARCX.PILLAR" },

  // Precious Metals
  { symbol: "GLD", dataset: "ARCX.PILLAR" },
  { symbol: "SLV", dataset: "ARCX.PILLAR" },

  // Shipping
  { symbol: "BDRY", dataset: "ARCX.PILLAR" },
  { symbol: "SBLK", dataset: "XNAS.ITCH" },

  // Energy
  { symbol: "XLE", dataset: "ARCX.PILLAR" },
  { symbol: "XOP", dataset: "ARCX.PILLAR" },
  { symbol: "USO", dataset: "ARCX.PILLAR" },
  { symbol: "UNG", dataset: "ARCX.PILLAR" },
  { symbol: "OIH", dataset: "ARCX.PILLAR" },

  // Treasuries
  { symbol: "TLT", dataset: "XNAS.ITCH" },
  { symbol: "IEF", dataset: "XNAS.ITCH" },

  // Broad Market
  { symbol: "SPY", dataset: "ARCX.PILLAR" },
  { symbol: "QQQ", dataset: "XNAS.ITCH" },

  // Ag Commodities
  { symbol: "DBA", dataset: "ARCX.PILLAR" },
  { symbol: "SOYB", dataset: "ARCX.PILLAR" },
  { symbol: "CORN", dataset: "ARCX.PILLAR" },
  { symbol: "WEAT", dataset: "ARCX.PILLAR" },

  // Dollar
  { symbol: "UUP", dataset: "ARCX.PILLAR" },

  // Green Energy
  { symbol: "ICLN", dataset: "XNAS.ITCH" },
  { symbol: "TAN", dataset: "ARCX.PILLAR" },
  { symbol: "LIT", dataset: "ARCX.PILLAR" },
];

interface DailyVwap {
  symbol: string;
  eventDate: Date;
  vwap: number;
  tradeCount: number;
  totalVolume: number;
}

/**
 * Calculate daily VWAP from 1-minute OHLCV bars.
 * Uses typical price = (high + low + close) / 3 weighted by volume.
 *
 * Why ohlcv-1m instead of trades?
 * SPY has tens of millions of trades/day (hundreds of MB), but only ~390
 * 1-minute bars. Same VWAP accuracy, orders of magnitude less data.
 */
function calculateVwapFromBars(
  bars: DatabentoOhlcvBar[],
  symbol: string,
): DailyVwap[] {
  const dailyData = new Map<
    string,
    { priceVolume: number; volume: number; count: number }
  >();

  for (const bar of bars) {
    const dateStr = bar.tsEvent.toISOString().split("T")[0];
    const typicalPrice = (bar.high + bar.low + bar.close) / 3;
    if (typicalPrice <= 0 || bar.volume <= 0) continue;

    if (!dailyData.has(dateStr)) {
      dailyData.set(dateStr, { priceVolume: 0, volume: 0, count: 0 });
    }
    const day = dailyData.get(dateStr)!;
    day.priceVolume += typicalPrice * bar.volume;
    day.volume += bar.volume;
    day.count += 1;
  }

  const results: DailyVwap[] = [];
  for (const [dateStr, data] of dailyData.entries()) {
    if (data.volume > 0) {
      results.push({
        symbol,
        eventDate: new Date(dateStr + "T00:00:00Z"),
        vwap: data.priceVolume / data.volume,
        tradeCount: data.count,
        totalVolume: data.volume,
      });
    }
  }

  results.sort((a, b) => a.eventDate.getTime() - b.eventDate.getTime());
  return results;
}

/**
 * Fetch 1-minute OHLCV bars for a symbol and date.
 * ~390 bars/day vs tens of millions of trades — avoids timeout and memory issues.
 */
async function fetchOhlcv1mForDate(
  symbol: string,
  dataset: string,
  date: Date,
): Promise<DatabentoOhlcvBar[]> {
  const startDate = new Date(date);
  startDate.setUTCHours(0, 0, 0, 0);

  const endDate = new Date(date);
  endDate.setUTCHours(23, 59, 59, 999);

  const csv = await fetchDatabentoCsv(
    {
      dataset,
      schema: "ohlcv-1m",
      symbols: symbol,
      stype_in: "raw_symbol",
      start: startDate.toISOString(),
      end: endDate.toISOString(),
      encoding: "csv",
      pretty_ts: "true",
      pretty_px: "true",
    },
    60_000, // 60s timeout (1min bars are small)
  );

  return parseDatabentoOhlcvCsv(csv);
}

/**
 * Update VWAP in database
 */
async function updateVwap(vwapData: DailyVwap[]): Promise<number> {
  if (vwapData.length === 0) return 0;

  const client = await pool.connect();
  try {
    // Batch update using unnest
    const result = await client.query(
      `
      UPDATE mkt.etf_1d AS e
      SET vwap = v.vwap
      FROM (
        SELECT * FROM UNNEST(
          $1::float[],
          $2::varchar[],
          $3::date[]
        ) AS t(vwap, symbol, event_date)
      ) AS v
      WHERE e.symbol = v.symbol AND e.event_date = v.event_date
      `,
      [
        vwapData.map((v) => v.vwap),
        vwapData.map((v) => v.symbol),
        vwapData.map((v) => v.eventDate.toISOString().split("T")[0]),
      ],
    );

    return result.rowCount || 0;
  } finally {
    client.release();
  }
}

/**
 * Get latest trading date that needs VWAP
 */
async function getLatestDateNeedingVwap(symbol: string): Promise<Date | null> {
  const client = await pool.connect();
  try {
    const result = await client.query(
      `SELECT event_date
       FROM mkt.etf_1d
       WHERE symbol = $1 AND vwap IS NULL
       ORDER BY event_date DESC
       LIMIT 1`,
      [symbol],
    );
    return result.rows[0]?.event_date
      ? new Date(result.rows[0].event_date)
      : null;
  } finally {
    client.release();
  }
}

/**
 * Daily VWAP calculation (incremental)
 * Runs after daily ETF OHLCV ingestion
 */
export const databentoEtfVwapDaily = inngest.createFunction(
  {
    id: "databento-etf-vwap-daily",
    name: "Databento ETF VWAP Daily (from Trades)",
    retries: 3,
    concurrency: [DB_CONCURRENCY],
  },
  { cron: "TZ=America/New_York 30 20 * * 1-5" }, // 8:30 PM ET (30min after OHLCV)
  async ({ step, logger }) => {
    const results: Array<{
      symbol: string;
      status: "success" | "error" | "no_data" | "skipped";
      updated?: number;
      error?: string;
    }> = [];

    for (const config of DATABENTO_ETF_SYMBOLS) {
      await step.run(`vwap-${config.symbol}`, async () => {
        try {
          // Get latest date that needs VWAP
          const latestDate = await getLatestDateNeedingVwap(config.symbol);

          if (!latestDate) {
            logger.info(`${config.symbol}: No missing VWAP dates`);
            results.push({ symbol: config.symbol, status: "skipped" });
            return;
          }

          logger.info(
            `Fetching 1m bars for ${config.symbol} on ${latestDate.toISOString().split("T")[0]}`,
          );

          // Fetch 1-minute OHLCV bars and calculate VWAP
          const bars = await fetchOhlcv1mForDate(
            config.symbol,
            config.dataset,
            latestDate,
          );
          const vwapData = calculateVwapFromBars(bars, config.symbol);

          if (vwapData.length === 0) {
            logger.warn(
              `No 1m bar data for ${config.symbol} on ${latestDate.toISOString().split("T")[0]}`,
            );
            results.push({ symbol: config.symbol, status: "no_data" });
            return;
          }

          // Update database
          const updated = await updateVwap(vwapData);

          const totalTrades = vwapData.reduce(
            (sum, v) => sum + v.tradeCount,
            0,
          );
          logger.info(
            `✓ ${config.symbol}: ${updated} days updated, ${totalTrades.toLocaleString()} trades, ` +
              `avg VWAP $${(vwapData.reduce((sum, v) => sum + v.vwap, 0) / vwapData.length).toFixed(2)}`,
          );

          results.push({ symbol: config.symbol, status: "success", updated });
        } catch (err) {
          const errorMsg = err instanceof Error ? err.message : String(err);
          logger.error(`Failed ${config.symbol}: ${errorMsg}`);
          results.push({
            symbol: config.symbol,
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
    };
  },
);

/**
 * Manual VWAP backfill trigger
 * Triggered via: inngest.send({ name: "etf/vwap-backfill.requested", data: { symbols?: string[], days?: number } })
 */
export const databentoEtfVwapBackfill = inngest.createFunction(
  {
    id: "databento-etf-vwap-backfill",
    name: "Databento ETF VWAP Backfill",
    retries: 1,
    concurrency: [DB_CONCURRENCY],
  },
  { event: "etf/vwap-backfill.requested" },
  async ({ step, logger, event }) => {
    const targetSymbols =
      (event.data?.symbols as string[] | undefined) ||
      DATABENTO_ETF_SYMBOLS.map((s) => s.symbol);
    const daysBack = (event.data?.days as number | undefined) || 30; // Default: last 30 days

    logger.info(
      `VWAP Backfill: ${targetSymbols.length} symbols, last ${daysBack} days`,
    );

    const symbolConfigs = DATABENTO_ETF_SYMBOLS.filter((s) =>
      targetSymbols.includes(s.symbol),
    );
    const results: Array<{
      symbol: string;
      status: "success" | "error" | "no_data";
      updated?: number;
      error?: string;
    }> = [];

    // Date range
    const endDate = new Date();
    const startDate = new Date();
    startDate.setUTCDate(startDate.getUTCDate() - daysBack);

    for (const config of symbolConfigs) {
      await step.run(`backfill-${config.symbol}`, async () => {
        try {
          logger.info(
            `Backfilling VWAP for ${config.symbol} (${daysBack} days)`,
          );

          // Fetch 1-minute OHLCV bars (much smaller than tick trades)
          const csv = await fetchDatabentoCsv(
            {
              dataset: config.dataset,
              schema: "ohlcv-1m",
              symbols: config.symbol,
              stype_in: "raw_symbol",
              start: startDate.toISOString(),
              end: endDate.toISOString(),
              encoding: "csv",
              pretty_ts: "true",
              pretty_px: "true",
            },
            300_000, // 5 min timeout for multi-day backfill
          );

          // Calculate VWAP from 1-minute bars
          const bars = parseDatabentoOhlcvCsv(csv);
          const vwapData = calculateVwapFromBars(bars, config.symbol);

          if (vwapData.length === 0) {
            logger.warn(`No 1m bar data for ${config.symbol}`);
            results.push({ symbol: config.symbol, status: "no_data" });
            return;
          }

          // Update database
          const updated = await updateVwap(vwapData);

          logger.info(`✓ ${config.symbol}: ${updated} days updated`);
          results.push({ symbol: config.symbol, status: "success", updated });
        } catch (err) {
          const errorMsg = err instanceof Error ? err.message : String(err);
          logger.error(`Backfill failed for ${config.symbol}: ${errorMsg}`);
          results.push({
            symbol: config.symbol,
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
    };
  },
);
