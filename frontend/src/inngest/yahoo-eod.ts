import { inngest } from "./client";
import { Pool } from "pg";

const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
  ssl: { rejectUnauthorized: false },
});

// Symbols to fetch daily from Yahoo Finance
const YAHOO_SYMBOLS = [
  // Soybean complex
  { yahoo: "ZL=F", db: "ZL", name: "Soybean Oil" },
  { yahoo: "ZS=F", db: "ZS", name: "Soybeans" },
  { yahoo: "ZM=F", db: "ZM", name: "Soybean Meal" },
  // Grains
  { yahoo: "ZC=F", db: "ZC", name: "Corn" },
  { yahoo: "ZW=F", db: "ZW", name: "Wheat" },
  { yahoo: "RS=F", db: "RS", name: "Canola" },
  // Energy
  { yahoo: "CL=F", db: "CL", name: "Crude Oil" },
  { yahoo: "NG=F", db: "NG", name: "Natural Gas" },
  { yahoo: "RB=F", db: "RB", name: "RBOB Gasoline" },
  { yahoo: "HO=F", db: "HO", name: "Heating Oil" },
  // Metals
  { yahoo: "GC=F", db: "GC", name: "Gold" },
  { yahoo: "SI=F", db: "SI", name: "Silver" },
  { yahoo: "HG=F", db: "HG", name: "Copper" },
  { yahoo: "PL=F", db: "PL", name: "Platinum" },
  { yahoo: "PA=F", db: "PA", name: "Palladium" },
  // Indices
  { yahoo: "DX-Y.NYB", db: "DX", name: "Dollar Index" },
  { yahoo: "^VIX", db: "VX", name: "VIX" },
  { yahoo: "^GVZ", db: "GVZ", name: "Gold VIX" },
  // Softs (no CPO on Yahoo - using Trading Economics)
  { yahoo: "CC=F", db: "CC", name: "Cocoa" },
  { yahoo: "KC=F", db: "KC", name: "Coffee" },
  { yahoo: "SB=F", db: "SB", name: "Sugar" },
];

interface YahooChartResult {
  meta: {
    symbol: string;
    regularMarketPrice: number;
  };
  timestamp?: number[];
  indicators?: {
    quote?: Array<{
      open?: (number | null)[];
      high?: (number | null)[];
      low?: (number | null)[];
      close?: (number | null)[];
      volume?: (number | null)[];
    }>;
  };
}

interface ParsedQuote {
  symbol: string;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number;
  volume: number;
}

/**
 * Fetch quote from Yahoo Finance v8 chart API (v7 quote API is now blocked)
 */
async function fetchYahooChart(symbol: string): Promise<ParsedQuote | null> {
  try {
    const res = await fetch(
      `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(symbol)}?interval=1d&range=2d`,
      { headers: { "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)" } }
    );

    if (!res.ok) return null;

    const json = await res.json();
    const result = json?.chart?.result?.[0] as YahooChartResult | undefined;
    if (!result) return null;

    const quote = result.indicators?.quote?.[0];
    const timestamps = result.timestamp;
    if (!quote || !timestamps || timestamps.length === 0) {
      // Use meta price as fallback
      return {
        symbol: result.meta.symbol,
        open: null,
        high: null,
        low: null,
        close: result.meta.regularMarketPrice,
        volume: 0,
      };
    }

    // Get the last valid data point
    let lastIdx = timestamps.length - 1;
    while (lastIdx >= 0 && quote.close?.[lastIdx] == null) {
      lastIdx--;
    }
    if (lastIdx < 0) {
      return {
        symbol: result.meta.symbol,
        open: null,
        high: null,
        low: null,
        close: result.meta.regularMarketPrice,
        volume: 0,
      };
    }

    return {
      symbol: result.meta.symbol,
      open: quote.open?.[lastIdx] ?? null,
      high: quote.high?.[lastIdx] ?? null,
      low: quote.low?.[lastIdx] ?? null,
      close: quote.close?.[lastIdx] ?? result.meta.regularMarketPrice,
      volume: quote.volume?.[lastIdx] ?? 0,
    };
  } catch {
    return null;
  }
}

/**
 * Fetch end-of-day prices from Yahoo Finance for multiple symbols
 * Runs daily at 6:00 PM ET (after market close)
 * Note: Uses v8 chart API since v7 quote API is now blocked
 */
export const yahooEod = inngest.createFunction(
  { id: "yahoo-eod", name: "Yahoo EOD Prices" },
  { cron: "0 11 * * 1-5" }, // 5AM CT = 11AM UTC, Mon-Fri
  async ({ step, logger }) => {
    const results: { symbol: string; status: string; close?: number }[] = [];

    // Fetch quotes individually using v8 chart API (v7 quote API is blocked)
    const quotes = await step.run("fetch-yahoo-quotes", async () => {
      const fetchedQuotes: ParsedQuote[] = [];

      for (const config of YAHOO_SYMBOLS) {
        const quote = await fetchYahooChart(config.yahoo);
        if (quote) {
          fetchedQuotes.push({ ...quote, symbol: config.yahoo });
        }
        // Rate limit to avoid being blocked
        await new Promise((r) => setTimeout(r, 100));
      }

      return fetchedQuotes;
    });

    logger.info(`Fetched ${quotes.length}/${YAHOO_SYMBOLS.length} quotes from Yahoo`);

    if (quotes.length === 0) {
      return { status: "error", message: "No quotes returned from Yahoo" };
    }

    // Step 2: Insert each quote into the database
    for (const config of YAHOO_SYMBOLS) {
      const quote = quotes.find(
        (q) => q.symbol === config.yahoo || q.symbol === config.yahoo.replace("=F", "") || q.symbol === config.yahoo.replace("^", "")
      );

      if (!quote) {
        results.push({ symbol: config.db, status: "not_found" });
        continue;
      }

      await step.run(`insert-${config.db}`, async () => {
        const client = await pool.connect();
        try {
          await client.query(
            `INSERT INTO mkt.futures_1d
              (event_date, symbol, open, high, low, close, volume, source, ingested_at)
             VALUES (CURRENT_DATE, $1, $2, $3, $4, $5, $6, 'yahoo_eod', NOW())
             ON CONFLICT (event_date, symbol) DO UPDATE SET
               open = COALESCE(EXCLUDED.open, mkt.futures_1d.open),
               high = COALESCE(EXCLUDED.high, mkt.futures_1d.high),
               low = COALESCE(EXCLUDED.low, mkt.futures_1d.low),
               close = EXCLUDED.close,
               volume = EXCLUDED.volume,
               source = EXCLUDED.source,
               ingested_at = NOW()`,
            [
              config.db,
              quote.open,
              quote.high,
              quote.low,
              quote.close,
              quote.volume || 0,
            ]
          );
          results.push({
            symbol: config.db,
            status: "success",
            close: quote.close,
          });
        } catch (err) {
          logger.warn(`Failed to insert ${config.db}: ${err}`);
          results.push({
            symbol: config.db,
            status: "error",
          });
        } finally {
          client.release();
        }
      });
    }

    // Step 3: Sync ZL to analytics.zl_price_1d for dashboard charts
    await step.run("sync-zl-analytics", async () => {
      const client = await pool.connect();
      try {
        await client.query(`
          INSERT INTO analytics.zl_price_1d (event_date, open, high, low, close, volume, source, created_at)
          SELECT event_date, open, high, low, close, volume, source, ingested_at
          FROM mkt.futures_1d
          WHERE symbol = 'ZL' AND event_date = CURRENT_DATE
          ON CONFLICT (event_date) DO UPDATE SET
            open = EXCLUDED.open,
            high = EXCLUDED.high,
            low = EXCLUDED.low,
            close = EXCLUDED.close,
            volume = EXCLUDED.volume,
            source = EXCLUDED.source
        `);
      } finally {
        client.release();
      }
    });

    return {
      status: "complete",
      date: new Date().toISOString().split("T")[0],
      results,
      successCount: results.filter((r) => r.status === "success").length,
      errorCount: results.filter((r) => r.status !== "success").length,
    };
  }
);
