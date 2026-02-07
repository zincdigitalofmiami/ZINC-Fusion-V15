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

import { inngest } from "./client";
import { fetchDatabentoCsv } from "@/lib/databento";
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
 * Parse Databento trades CSV and calculate daily VWAP
 */
function calculateVwapFromTrades(csv: string, symbol: string): DailyVwap[] {
  const lines = csv
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter((l) => l.length > 0 && !l.startsWith("#"));

  if (lines.length < 2) return [];

  const header = lines[0].split(",");
  const idx = {
    ts_event: header.indexOf("ts_event"),
    price: header.indexOf("price"),
    size: header.indexOf("size"),
  };

  if (idx.ts_event === -1 || idx.price === -1 || idx.size === -1) {
    throw new Error(`Trades CSV missing required columns for ${symbol}`);
  }

  // Accumulate trades by date
  const dailyData = new Map<string, { priceVolume: number; volume: number; count: number }>();

  for (let i = 1; i < lines.length; i++) {
    const parts = lines[i].split(",");
    if (parts.length < header.length) continue;

    // Parse timestamp
    const tsStr = parts[idx.ts_event]?.trim();
    if (!tsStr) continue;

    let ts: Date;
    if (/^\d+$/.test(tsStr)) {
      // Nanosecond timestamp
      const ms = Math.floor(Number(tsStr) / 1_000_000);
      ts = new Date(ms);
    } else {
      ts = new Date(tsStr);
    }
    if (isNaN(ts.getTime())) continue;

    const dateStr = ts.toISOString().split("T")[0];

    // Parse price (fixed-point scaled by 1e-9)
    const priceRaw = Number(parts[idx.price]);
    if (!Number.isFinite(priceRaw)) continue;
    const price = priceRaw > 1e6 ? priceRaw * 1e-9 : priceRaw; // Handle both formats

    // Parse size
    const size = Number(parts[idx.size]);
    if (!Number.isFinite(size) || size <= 0) continue;

    if (price <= 0) continue;

    // Accumulate VWAP components
    if (!dailyData.has(dateStr)) {
      dailyData.set(dateStr, { priceVolume: 0, volume: 0, count: 0 });
    }
    const day = dailyData.get(dateStr)!;
    day.priceVolume += price * size;
    day.volume += size;
    day.count += 1;
  }

  // Calculate VWAP for each day
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
 * Fetch trades for a symbol and date
 */
async function fetchTradesForDate(
  symbol: string,
  dataset: string,
  date: Date
): Promise<string> {
  // Trades data for full trading day
  const startDate = new Date(date);
  startDate.setUTCHours(0, 0, 0, 0);

  const endDate = new Date(date);
  endDate.setUTCHours(23, 59, 59, 999);

  const csv = await fetchDatabentoCsv({
    dataset,
    schema: "trades", // Trade executions
    symbols: symbol,
    stype_in: "raw_symbol",
    start: startDate.toISOString(),
    end: endDate.toISOString(),
    encoding: "csv",
    pretty_ts: "true",
    pretty_px: "true",
  });

  return csv;
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
      ]
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
      [symbol]
    );
    return result.rows[0]?.event_date ? new Date(result.rows[0].event_date) : null;
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

          logger.info(`Fetching trades for ${config.symbol} on ${latestDate.toISOString().split("T")[0]}`);

          // Fetch trades and calculate VWAP
          const tradesCsv = await fetchTradesForDate(config.symbol, config.dataset, latestDate);
          const vwapData = calculateVwapFromTrades(tradesCsv, config.symbol);

          if (vwapData.length === 0) {
            logger.warn(`No trades data for ${config.symbol} on ${latestDate.toISOString().split("T")[0]}`);
            results.push({ symbol: config.symbol, status: "no_data" });
            return;
          }

          // Update database
          const updated = await updateVwap(vwapData);

          const totalTrades = vwapData.reduce((sum, v) => sum + v.tradeCount, 0);
          logger.info(
            `✓ ${config.symbol}: ${updated} days updated, ${totalTrades.toLocaleString()} trades, ` +
            `avg VWAP $${(vwapData.reduce((sum, v) => sum + v.vwap, 0) / vwapData.length).toFixed(2)}`
          );

          results.push({ symbol: config.symbol, status: "success", updated });
        } catch (err) {
          const errorMsg = err instanceof Error ? err.message : String(err);
          logger.error(`Failed ${config.symbol}: ${errorMsg}`);
          results.push({ symbol: config.symbol, status: "error", error: errorMsg });
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
  }
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
  },
  { event: "etf/vwap-backfill.requested" },
  async ({ step, logger, event }) => {
    const targetSymbols = (event.data?.symbols as string[] | undefined) || 
      DATABENTO_ETF_SYMBOLS.map((s) => s.symbol);
    const daysBack = (event.data?.days as number | undefined) || 30; // Default: last 30 days

    logger.info(`VWAP Backfill: ${targetSymbols.length} symbols, last ${daysBack} days`);

    const symbolConfigs = DATABENTO_ETF_SYMBOLS.filter((s) => targetSymbols.includes(s.symbol));
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
          logger.info(`Backfilling VWAP for ${config.symbol} (${daysBack} days)`);

          // Fetch trades
          const tradesCsv = await fetchDatabentoCsv({
            dataset: config.dataset,
            schema: "trades",
            symbols: config.symbol,
            stype_in: "raw_symbol",
            start: startDate.toISOString(),
            end: endDate.toISOString(),
            encoding: "csv",
            pretty_ts: "true",
            pretty_px: "true",
          });

          // Calculate VWAP
          const vwapData = calculateVwapFromTrades(tradesCsv, config.symbol);

          if (vwapData.length === 0) {
            logger.warn(`No trades data for ${config.symbol}`);
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
          results.push({ symbol: config.symbol, status: "error", error: errorMsg });
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
  }
);
