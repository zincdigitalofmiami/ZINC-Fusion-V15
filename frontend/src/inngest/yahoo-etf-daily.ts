import { inngest } from "./client";
import { createHash } from "crypto";
import { Pool } from "pg";

const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
  ssl: { rejectUnauthorized: false },
});

const ETF_SYMBOLS = [
  // Energy
  { symbol: "XLE", name: "Energy Select SPDR", tags: ["energy", "biofuel"] },
  { symbol: "XOP", name: "Oil & Gas Exploration ETF", tags: ["energy"] },
  { symbol: "USO", name: "United States Oil Fund", tags: ["energy"] },
  { symbol: "UNG", name: "United States Natural Gas Fund", tags: ["energy"] },
  { symbol: "OIH", name: "Oil Services ETF", tags: ["energy"] },

  // China
  { symbol: "FXI", name: "China Large-Cap ETF", tags: ["china"] },
  { symbol: "KWEB", name: "China Internet ETF", tags: ["china"] },
  { symbol: "MCHI", name: "MSCI China ETF", tags: ["china"] },

  // Agriculture/Commodities
  { symbol: "DBA", name: "Agriculture Fund", tags: ["crush", "substitutes"] },
  { symbol: "CORN", name: "Corn Fund", tags: ["crush", "substitutes"] },
  { symbol: "WEAT", name: "Wheat Fund", tags: ["crush", "substitutes"] },
  { symbol: "SOYB", name: "Soybean Fund", tags: ["crush"] },

  // Biofuel/Clean Energy
  { symbol: "TAN", name: "Solar ETF", tags: ["biofuel"] },
  { symbol: "ICLN", name: "Clean Energy ETF", tags: ["biofuel"] },
  { symbol: "LIT", name: "Lithium & Battery ETF", tags: ["biofuel"] },

  // Rates/Macro
  { symbol: "TLT", name: "20+ Year Treasury ETF", tags: ["fed"] },
  { symbol: "IEF", name: "7-10 Year Treasury ETF", tags: ["fed"] },
  { symbol: "SPY", name: "S&P 500 ETF", tags: ["fed", "volatility"] },
  { symbol: "QQQ", name: "Nasdaq 100 ETF", tags: ["fed", "volatility"] },

  // Volatility
  { symbol: "VXX", name: "VIX Short-Term Futures ETN", tags: ["volatility"] },
  { symbol: "UVXY", name: "Ultra VIX Short-Term Futures ETF", tags: ["volatility"] },

  // FX/Metals
  { symbol: "UUP", name: "US Dollar Index Fund", tags: ["fx"] },
  { symbol: "GLD", name: "Gold ETF", tags: ["fx"] },
  { symbol: "SLV", name: "Silver ETF", tags: ["fx"] },

  // Palm Oil related
  { symbol: "PALM", name: "Palm Oil ETF", tags: ["palm", "substitutes"] },
];

interface YahooChartResult {
  meta: {
    symbol: string;
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
  eventDate: string;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number | null;
  volume: number | null;
}

function computeRowHash(symbol: string, date: string): string {
  return createHash("sha256").update(`${symbol}|${date}`).digest("hex");
}

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
    if (!quote || !timestamps || timestamps.length === 0) return null;

    let lastIdx = timestamps.length - 1;
    while (lastIdx >= 0 && quote.close?.[lastIdx] == null) {
      lastIdx--;
    }
    if (lastIdx < 0) return null;

    const eventDate = new Date(timestamps[lastIdx] * 1000)
      .toISOString()
      .slice(0, 10);

    return {
      symbol: result.meta.symbol,
      eventDate,
      open: quote.open?.[lastIdx] ?? null,
      high: quote.high?.[lastIdx] ?? null,
      low: quote.low?.[lastIdx] ?? null,
      close: quote.close?.[lastIdx] ?? null,
      volume: quote.volume?.[lastIdx] ?? null,
    };
  } catch {
    return null;
  }
}

export const yahooEtfDaily = inngest.createFunction(
  { id: "yahoo-etf-daily", name: "Yahoo ETF Daily Prices" },
  { cron: "0 11 * * 1-5" },
  async ({ step, logger }) => {
    if (!process.env.DATABASE_URL) {
      throw new Error("DATABASE_URL not configured");
    }

    const quotes = await step.run("fetch-yahoo-etf-quotes", async () => {
      const fetched: ParsedQuote[] = [];
      for (const config of ETF_SYMBOLS) {
        const quote = await fetchYahooChart(config.symbol);
        if (quote) {
          fetched.push({ ...quote, symbol: config.symbol });
        }
        await new Promise((r) => setTimeout(r, 100));
      }
      return fetched;
    });

    logger.info(`Fetched ${quotes.length}/${ETF_SYMBOLS.length} ETF quotes from Yahoo`);

    const results: { symbol: string; status: string }[] = [];

    for (const config of ETF_SYMBOLS) {
      const quote = quotes.find((q) => q.symbol === config.symbol);
      if (!quote || !quote.eventDate) {
        results.push({ symbol: config.symbol, status: "not_found" });
        continue;
      }

      const rowHash = computeRowHash(config.symbol, quote.eventDate);

      await step.run(`insert-${config.symbol}`, async () => {
        const client = await pool.connect();
        try {
          await client.query(
            `INSERT INTO mkt.etf_1d (
               symbol, event_date, open, high, low, close, volume,
               source, row_hash, specialist_tags
             ) VALUES ($1, $2::date, $3, $4, $5, $6, $7, $8, $9, $10)
             ON CONFLICT (symbol, event_date) DO UPDATE SET
               open = EXCLUDED.open,
               high = EXCLUDED.high,
               low = EXCLUDED.low,
               close = EXCLUDED.close,
               volume = EXCLUDED.volume,
               source = EXCLUDED.source,
               row_hash = EXCLUDED.row_hash,
               specialist_tags = EXCLUDED.specialist_tags
             WHERE mkt.etf_1d.source IN ('yahoo', 'barchart')`,
            [
              config.symbol,
              quote.eventDate,
              quote.open,
              quote.high,
              quote.low,
              quote.close,
              quote.volume,
              "yahoo",
              rowHash,
              config.tags,
            ]
          );
          results.push({ symbol: config.symbol, status: "success" });
        } catch (err) {
          logger.warn(`Failed to insert ${config.symbol}: ${err}`);
          results.push({ symbol: config.symbol, status: "error" });
        } finally {
          client.release();
        }
      });
    }

    return {
      status: "success",
      fetched: quotes.length,
      results,
    };
  }
);
