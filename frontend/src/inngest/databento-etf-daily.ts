/**
 * Databento ETF Daily Ingestion - FULL INSTITUTIONAL GRADE
 *
 * Fetches ALL available data from Databento US Equities datasets:
 * - ohlcv-1d: Daily OHLCV bars
 * - statistics: Auction data, indicative prices, session stats (includes VWAP)
 *
 * Datasets:
 * - ARCX.PILLAR (NYSE Arca) - Most ETFs
 * - XNAS.ITCH (Nasdaq) - QQQ, TLT, IEF, ICLN, SBLK
 *
 * ETF Categories (Institutional Use Cases for ZL Forecasting):
 *
 * 1. CHINA COMPLEX (FXI, KWEB, MCHI) - China demand/stress signals
 * 2. PRECIOUS METALS (GLD, SLV) - Inflation/volatility regime
 * 3. SHIPPING (BDRY, SBLK) - Physical soy flow signals
 * 4. ENERGY (XLE, XOP, USO, UNG, OIH) - Biodiesel economics
 * 5. TREASURIES (TLT, IEF) - Carry trade cost basis
 * 6. BROAD MARKET (SPY, QQQ) - Risk regime confirmation
 * 7. AG COMMODITIES (DBA, SOYB, CORN, WEAT) - Sector momentum
 * 8. DOLLAR (UUP) - FX regime cross-check
 * 9. GREEN ENERGY (ICLN, TAN, LIT) - Biofuel policy sentiment
 *
 * @author Claude (ZINC-FUSION-V15)
 * @date 2026-02-03
 */

import { inngest, DB_CONCURRENCY } from "./client";
import { fetchDatabentoCsv, parseDatabentoOhlcvCsv } from "@/lib/databento";
import { createHash } from "crypto";
import dbPool from "@/lib/db";

const pool = dbPool;

// ETF symbols with their Databento dataset and specialist tags
// ARCX.PILLAR = NYSE Arca (most ETFs), XNAS.ITCH = Nasdaq
const DATABENTO_ETF_SYMBOLS = [
  // China Complex - CRITICAL for China specialist
  { symbol: "FXI", dataset: "ARCX.PILLAR", name: "iShares China Large-Cap", tags: ["china", "tariff", "trump_effect"] },
  { symbol: "KWEB", dataset: "ARCX.PILLAR", name: "KraneShares China Internet", tags: ["china"] },
  { symbol: "MCHI", dataset: "ARCX.PILLAR", name: "iShares MSCI China", tags: ["china"] },

  // Precious Metals - Volatility regime / inflation
  { symbol: "GLD", dataset: "ARCX.PILLAR", name: "SPDR Gold", tags: ["volatility", "fed"] },
  { symbol: "SLV", dataset: "ARCX.PILLAR", name: "iShares Silver", tags: ["volatility", "energy"] },

  // Shipping - Physical soy flows (CRITICAL for China specialist)
  { symbol: "BDRY", dataset: "ARCX.PILLAR", name: "Breakwave Dry Bulk Shipping", tags: ["china", "crush"] },
  { symbol: "SBLK", dataset: "XNAS.ITCH", name: "Star Bulk Carriers", tags: ["china", "crush"] },

  // Energy - Biodiesel economics
  { symbol: "XLE", dataset: "ARCX.PILLAR", name: "Energy Select Sector SPDR", tags: ["energy", "biofuel"] },
  { symbol: "XOP", dataset: "ARCX.PILLAR", name: "SPDR Oil & Gas Exploration", tags: ["energy"] },
  { symbol: "USO", dataset: "ARCX.PILLAR", name: "United States Oil Fund", tags: ["energy", "biofuel"] },
  { symbol: "UNG", dataset: "ARCX.PILLAR", name: "United States Natural Gas", tags: ["energy", "crush"] },
  { symbol: "OIH", dataset: "ARCX.PILLAR", name: "VanEck Oil Services", tags: ["energy"] },

  // Treasuries - Carry trade cost
  { symbol: "TLT", dataset: "XNAS.ITCH", name: "iShares 20+ Year Treasury", tags: ["fed", "volatility"] },
  { symbol: "IEF", dataset: "XNAS.ITCH", name: "iShares 7-10 Year Treasury", tags: ["fed"] },

  // Broad Market - Regime confirmation
  { symbol: "SPY", dataset: "ARCX.PILLAR", name: "SPDR S&P 500", tags: ["volatility", "fed"] },
  { symbol: "QQQ", dataset: "XNAS.ITCH", name: "Invesco QQQ (Nasdaq 100)", tags: ["volatility"] },

  // Ag Commodities - Sector momentum (cross-validation with futures)
  { symbol: "DBA", dataset: "ARCX.PILLAR", name: "Invesco DB Agriculture", tags: ["crush", "substitutes"] },
  { symbol: "SOYB", dataset: "ARCX.PILLAR", name: "Teucrium Soybean", tags: ["crush"] },
  { symbol: "CORN", dataset: "ARCX.PILLAR", name: "Teucrium Corn", tags: ["crush", "biofuel"] },
  { symbol: "WEAT", dataset: "ARCX.PILLAR", name: "Teucrium Wheat", tags: ["crush", "substitutes"] },

  // Dollar - FX regime
  { symbol: "UUP", dataset: "ARCX.PILLAR", name: "Invesco DB US Dollar", tags: ["fx", "china"] },

  // Green Energy - Biofuel policy sentiment
  { symbol: "ICLN", dataset: "XNAS.ITCH", name: "iShares Global Clean Energy", tags: ["biofuel", "energy"] },
  { symbol: "TAN", dataset: "ARCX.PILLAR", name: "Invesco Solar", tags: ["biofuel", "energy"] },
  { symbol: "LIT", dataset: "ARCX.PILLAR", name: "Global X Lithium & Battery", tags: ["biofuel", "energy"] },
];

interface SymbolResult {
  symbol: string;
  status: "success" | "error" | "no_data" | "skipped";
  ohlcvRows?: number;
  statsRows?: number;
  error?: string;
}

/**
 * Parse Databento ETF statistics CSV
 * ETF statistics include: opening/closing prices, session high/low, auction data
 * Different from futures - no open_interest for ETFs
 */
interface EtfStatistics {
  tsEvent: Date;
  openingPrice: number | null;
  closingPrice: number | null;
  sessionHigh: number | null;
  sessionLow: number | null;
  indicativeOpen: number | null;
  indicativeClose: number | null;
  vwap: number | null;
  auctionImbalance: number | null;
}

function parseEtfStatisticsCsv(csv: string): Map<string, EtfStatistics> {
  const map = new Map<string, EtfStatistics>();

  const lines = csv
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter((l) => l.length > 0 && !l.startsWith("#"));

  if (lines.length < 2) return map;

  const header = lines[0].split(",");
  const idx = {
    ts_event: header.indexOf("ts_event"),
    stat_type: header.indexOf("stat_type"),
    price: header.indexOf("price"),
    quantity: header.indexOf("quantity"),
  };

  if (idx.ts_event === -1 || idx.stat_type === -1) return map;

  // Stat type mapping for equities (different from futures)
  // 1=opening_price, 3=settlement/close, 4=session_low, 5=session_high
  // 2=indicative_open, 11=close_stat, 13=vwap
  const STAT_TYPES: Record<number, keyof EtfStatistics> = {
    1: "openingPrice",
    2: "indicativeOpen",
    3: "closingPrice",
    4: "sessionLow",
    5: "sessionHigh",
    11: "indicativeClose",
    13: "vwap",
  };

  for (let i = 1; i < lines.length; i++) {
    const parts = lines[i].split(",");
    if (parts.length < header.length) continue;

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
    const statType = Number(parts[idx.stat_type]);

    if (!Number.isFinite(statType) || !STAT_TYPES[statType]) continue;

    if (!map.has(dateStr)) {
      map.set(dateStr, {
        tsEvent: ts,
        openingPrice: null,
        closingPrice: null,
        sessionHigh: null,
        sessionLow: null,
        indicativeOpen: null,
        indicativeClose: null,
        vwap: null,
        auctionImbalance: null,
      });
    }

    const rec = map.get(dateStr)!;
    const field = STAT_TYPES[statType];

    // Price field (scaled by 1e-9 for fixed-point)
    if (idx.price >= 0) {
      const priceStr = parts[idx.price]?.trim();
      if (priceStr) {
        const p = Number(priceStr) * 1e-9;
        if (Number.isFinite(p) && p > 0) {
          // Use type-safe assignment
          switch (field) {
            case "openingPrice": rec.openingPrice = p; break;
            case "closingPrice": rec.closingPrice = p; break;
            case "sessionHigh": rec.sessionHigh = p; break;
            case "sessionLow": rec.sessionLow = p; break;
            case "indicativeOpen": rec.indicativeOpen = p; break;
            case "indicativeClose": rec.indicativeClose = p; break;
            case "vwap": rec.vwap = p; break;
          }
        }
      }
    }
  }

  return map;
}

/**
 * Get maximum event_date for an ETF from Databento-sourced rows
 */
async function getMaxEventDate(symbol: string): Promise<Date | null> {
  const client = await pool.connect();
  try {
    const result = await client.query(
      `SELECT MAX(event_date) as max_date
       FROM mkt.etf_1d
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
 * Upsert full ETF row into mkt.etf_1d with OHLCV + statistics
 */
async function upsertEtfRow(
  symbol: string,
  eventDate: Date,
  open: number | null,
  high: number | null,
  low: number | null,
  close: number,
  volume: number,
  rowHash: string,
  specialistTags: string[],
  stats?: EtfStatistics
): Promise<void> {
  const client = await pool.connect();
  try {
    // Databento takes precedence - full upsert with OHLCV + statistics
    await client.query(
      `INSERT INTO mkt.etf_1d
        (symbol, event_date, open, high, low, close, volume, source, row_hash, specialist_tags, created_at,
         opening_price, closing_price, session_high, session_low, indicative_open, indicative_close, vwap)
       VALUES ($1, $2, $3, $4, $5, $6, $7, 'databento', $8, $9, NOW(),
               $10, $11, $12, $13, $14, $15, $16)
       ON CONFLICT (symbol, event_date) DO UPDATE SET
         open = EXCLUDED.open,
         high = EXCLUDED.high,
         low = EXCLUDED.low,
         close = EXCLUDED.close,
         volume = EXCLUDED.volume,
         source = EXCLUDED.source,
         row_hash = EXCLUDED.row_hash,
         specialist_tags = EXCLUDED.specialist_tags,
         opening_price = COALESCE(EXCLUDED.opening_price, mkt.etf_1d.opening_price),
         closing_price = COALESCE(EXCLUDED.closing_price, mkt.etf_1d.closing_price),
         session_high = COALESCE(EXCLUDED.session_high, mkt.etf_1d.session_high),
         session_low = COALESCE(EXCLUDED.session_low, mkt.etf_1d.session_low),
         indicative_open = COALESCE(EXCLUDED.indicative_open, mkt.etf_1d.indicative_open),
         indicative_close = COALESCE(EXCLUDED.indicative_close, mkt.etf_1d.indicative_close),
         vwap = COALESCE(EXCLUDED.vwap, mkt.etf_1d.vwap)`,
      [
        symbol, eventDate, open, high, low, close, volume, rowHash, specialistTags,
        stats?.openingPrice ?? null,
        stats?.closingPrice ?? null,
        stats?.sessionHigh ?? null,
        stats?.sessionLow ?? null,
        stats?.indicativeOpen ?? null,
        stats?.indicativeClose ?? null,
        stats?.vwap ?? null,
      ]
    );
  } finally {
    client.release();
  }
}

/**
 * Fetch OHLCV data for a symbol
 */
async function fetchOhlcv(
  symbol: string,
  dataset: string,
  startDate: Date,
  endDate: Date
): Promise<ReturnType<typeof parseDatabentoOhlcvCsv>> {
  const csv = await fetchDatabentoCsv({
    dataset,
    schema: "ohlcv-1d",
    symbols: symbol,
    stype_in: "raw_symbol",
    start: startDate.toISOString(),
    end: endDate.toISOString(),
    encoding: "csv",
    pretty_ts: "true",
    pretty_px: "true",
  });
  return parseDatabentoOhlcvCsv(csv);
}

/**
 * Fetch statistics data for a symbol (auction prices, session stats)
 */
async function fetchStatistics(
  symbol: string,
  dataset: string,
  startDate: Date,
  endDate: Date
): Promise<Map<string, EtfStatistics>> {
  try {
    const csv = await fetchDatabentoCsv({
      dataset,
      schema: "statistics",
      symbols: symbol,
      stype_in: "raw_symbol",
      start: startDate.toISOString(),
      end: endDate.toISOString(),
      encoding: "csv",
      pretty_ts: "true",
      pretty_px: "true",
    });
    return parseEtfStatisticsCsv(csv);
  } catch {
    // Statistics may not be available for all symbols/dates
    return new Map();
  }
}

export const databentoEtfDaily = inngest.createFunction(
  {
    id: "databento-etf-daily",
    name: "Databento ETF Daily (OHLCV + Statistics)",
    retries: 3,
    concurrency: [DB_CONCURRENCY],
  },
  { cron: "TZ=America/New_York 0 20 * * 1-5" }, // 8 PM ET on weekdays (after market close)
  async ({ step, logger }) => {
    const results: SymbolResult[] = [];

    for (const config of DATABENTO_ETF_SYMBOLS) {
      await step.run(`fetch-${config.symbol}`, async () => {
        try {
          // Get incremental window
          const maxDate = await getMaxEventDate(config.symbol);
          const endDate = new Date();
          endDate.setUTCHours(0, 0, 0, 0);

          let startDate: Date;
          if (maxDate) {
            startDate = new Date(maxDate);
            startDate.setUTCDate(startDate.getUTCDate() + 1);
          } else {
            // No existing Databento data: fetch last 30 days
            startDate = new Date(endDate);
            startDate.setUTCDate(startDate.getUTCDate() - 30);
          }

          if (startDate >= endDate) {
            logger.info(`No new data window for ${config.symbol}`);
            results.push({ symbol: config.symbol, status: "skipped" });
            return;
          }

          logger.info(
            `Fetching ${config.symbol} from ${config.dataset}: ${startDate.toISOString()} to ${endDate.toISOString()}`
          );

          // Fetch OHLCV and Statistics in parallel
          const [ohlcvBars, statsMap] = await Promise.all([
            fetchOhlcv(config.symbol, config.dataset, startDate, endDate),
            fetchStatistics(config.symbol, config.dataset, startDate, endDate),
          ]);

          if (ohlcvBars.length === 0) {
            logger.info(`No OHLCV data for ${config.symbol}`);
            results.push({ symbol: config.symbol, status: "no_data" });
            return;
          }

          // Insert each bar with statistics if available
          let inserted = 0;
          for (const bar of ohlcvBars) {
            const eventDate = new Date(Date.UTC(
              bar.tsEvent.getUTCFullYear(),
              bar.tsEvent.getUTCMonth(),
              bar.tsEvent.getUTCDate()
            ));
            const dateStr = eventDate.toISOString().split("T")[0];
            const stats = statsMap.get(dateStr);

            const rowHash = computeRowHash(
              config.symbol,
              eventDate,
              bar.open,
              bar.high,
              bar.low,
              bar.close,
              bar.volume
            );

            await upsertEtfRow(
              config.symbol,
              eventDate,
              bar.open,
              bar.high,
              bar.low,
              bar.close,
              bar.volume,
              rowHash,
              config.tags,
              stats
            );
            inserted++;
          }

          logger.info(`Inserted ${inserted} rows for ${config.symbol} (stats: ${statsMap.size} days)`);
          results.push({
            symbol: config.symbol,
            status: "success",
            ohlcvRows: inserted,
            statsRows: statsMap.size,
          });
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
 * Historical backfill - fetches 10 years of data for all ETFs
 * Triggered via: inngest.send({ name: "etf/backfill.requested", data: { symbols?: string[] } })
 */
export const databentoEtfBackfill = inngest.createFunction(
  {
    id: "databento-etf-backfill",
    name: "Databento ETF Historical Backfill (10yr)",
    retries: 1,
    concurrency: [DB_CONCURRENCY],
  },
  { event: "etf/backfill.requested" },
  async ({ step, logger, event }) => {
    const results: SymbolResult[] = [];

    // Allow targeting specific symbols
    const targetSymbols = event.data?.symbols as string[] | undefined;
    const symbolsToFetch = targetSymbols
      ? DATABENTO_ETF_SYMBOLS.filter((s) => targetSymbols.includes(s.symbol))
      : DATABENTO_ETF_SYMBOLS;

    // 10 year backfill
    const endDate = new Date();
    endDate.setUTCHours(0, 0, 0, 0);
    const startDate = new Date(endDate);
    startDate.setUTCFullYear(startDate.getUTCFullYear() - 10);

    logger.info(`ETF Backfill: ${symbolsToFetch.length} symbols, ${startDate.toISOString()} to ${endDate.toISOString()}`);

    for (const config of symbolsToFetch) {
      await step.run(`backfill-${config.symbol}`, async () => {
        try {
          logger.info(`Backfilling ${config.symbol} from ${config.dataset}`);

          // Fetch OHLCV and Statistics
          const [ohlcvBars, statsMap] = await Promise.all([
            fetchOhlcv(config.symbol, config.dataset, startDate, endDate),
            fetchStatistics(config.symbol, config.dataset, startDate, endDate),
          ]);

          if (ohlcvBars.length === 0) {
            logger.warn(`No historical data for ${config.symbol}`);
            results.push({ symbol: config.symbol, status: "no_data" });
            return;
          }

          // Batch insert
          let inserted = 0;
          for (const bar of ohlcvBars) {
            const eventDate = new Date(Date.UTC(
              bar.tsEvent.getUTCFullYear(),
              bar.tsEvent.getUTCMonth(),
              bar.tsEvent.getUTCDate()
            ));
            const dateStr = eventDate.toISOString().split("T")[0];
            const stats = statsMap.get(dateStr);

            const rowHash = computeRowHash(
              config.symbol,
              eventDate,
              bar.open,
              bar.high,
              bar.low,
              bar.close,
              bar.volume
            );

            await upsertEtfRow(
              config.symbol,
              eventDate,
              bar.open,
              bar.high,
              bar.low,
              bar.close,
              bar.volume,
              rowHash,
              config.tags,
              stats
            );
            inserted++;
          }

          const range = `${ohlcvBars[0]?.tsEvent.toISOString().split("T")[0]} to ${ohlcvBars[ohlcvBars.length - 1]?.tsEvent.toISOString().split("T")[0]}`;
          logger.info(`Backfilled ${inserted} rows for ${config.symbol} (${range})`);
          results.push({
            symbol: config.symbol,
            status: "success",
            ohlcvRows: inserted,
            statsRows: statsMap.size,
          });
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
