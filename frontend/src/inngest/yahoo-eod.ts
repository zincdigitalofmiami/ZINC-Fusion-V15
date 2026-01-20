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

interface YahooQuote {
  symbol: string;
  regularMarketOpen: number;
  regularMarketHigh: number;
  regularMarketLow: number;
  regularMarketPrice: number;
  regularMarketVolume: number;
}

/**
 * Fetch end-of-day prices from Yahoo Finance for multiple symbols
 * Runs daily at 6:00 PM ET (after market close)
 */
export const yahooEod = inngest.createFunction(
  { id: "yahoo-eod", name: "Yahoo EOD Prices" },
  { cron: "0 11 * * 1-5" }, // 5AM CT = 11AM UTC, Mon-Fri
  async ({ step }) => {
    const results: { symbol: string; status: string; close?: number }[] = [];

    // Step 1: Fetch all quotes from Yahoo
    const quotes = await step.run("fetch-yahoo-quotes", async () => {
      const symbols = YAHOO_SYMBOLS.map((s) => s.yahoo).join(",");
      const res = await fetch(
        `https://query1.finance.yahoo.com/v7/finance/quote?symbols=${encodeURIComponent(symbols)}`
      );
      const json = await res.json();
      return json.quoteResponse?.result as YahooQuote[] | undefined;
    });

    if (!quotes || quotes.length === 0) {
      return { status: "error", message: "No quotes returned from Yahoo" };
    }

    // Step 2: Insert each quote into the database
    for (const config of YAHOO_SYMBOLS) {
      const quote = quotes.find(
        (q) => q.symbol === config.yahoo || q.symbol === config.yahoo.replace("=F", "")
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
               open = EXCLUDED.open,
               high = EXCLUDED.high,
               low = EXCLUDED.low,
               close = EXCLUDED.close,
               volume = EXCLUDED.volume,
               source = EXCLUDED.source,
               ingested_at = EXCLUDED.ingested_at`,
            [
              config.db,
              quote.regularMarketOpen,
              quote.regularMarketHigh,
              quote.regularMarketLow,
              quote.regularMarketPrice,
              quote.regularMarketVolume || 0,
            ]
          );
          results.push({
            symbol: config.db,
            status: "success",
            close: quote.regularMarketPrice,
          });
        } catch {
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
