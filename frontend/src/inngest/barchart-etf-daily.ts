/**
 * Barchart ETF Daily Price Ingestion
 *
 * Fetches daily ETF prices from Barchart for specialist-relevant funds:
 * - Energy: XLE, XOP, USO, UNG, OIH
 * - China: FXI, KWEB, MCHI
 * - Ag/Commodities: DBA, CORN, WEAT, SOYB
 * - Biofuel/Clean Energy: TAN, ICLN, LIT
 * - Rates/Macro: TLT, IEF, SPY, QQQ
 * - Volatility: VXX
 * - FX: UUP, GLD
 *
 * Schedule: Daily at 6 PM CT (after market close)
 */

import { inngest } from "./client";
import { createHash } from "crypto";
import { Pool } from "pg";

const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
  ssl: { rejectUnauthorized: false },
});

// ETFs to fetch with their specialist tags
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

const BARCHART_QUOTE_URL = "https://www.barchart.com/proxies/core-api/v1/quotes/get";
const SEED_URL = "https://www.barchart.com/etfs-funds/quotes/SPY/overview";

type BarchartQuote = {
  symbol: string;
  lastPrice: number;
  open: number;
  high: number;
  low: number;
  previousClose: number;
  volume: number;
  tradeTime: string;
};

function getSetCookieHeaders(res: Response): string[] {
  const headersAny = res.headers as unknown as { getSetCookie?: () => string[] };
  if (typeof headersAny.getSetCookie === "function") {
    return headersAny.getSetCookie();
  }
  const raw = res.headers.get("set-cookie");
  return raw ? [raw] : [];
}

function parseCookieKV(setCookie: string): { name: string; value: string } | null {
  const first = setCookie.split(";")[0] ?? "";
  const idx = first.indexOf("=");
  if (idx <= 0) return null;
  const name = first.slice(0, idx).trim();
  const value = first.slice(idx + 1).trim();
  if (!name || !value) return null;
  return { name, value };
}

async function fetchBarchartQuotes(symbols: string[]): Promise<BarchartQuote[]> {
  // Bootstrap session from public page to get CSRF token
  const seed = await fetch(SEED_URL, {
    headers: { "User-Agent": "ZINC-Fusion/1.0" },
  });

  if (!seed.ok) {
    throw new Error(`Barchart seed page fetch failed: ${seed.status}`);
  }

  const cookies = new Map<string, string>();
  for (const h of getSetCookieHeaders(seed)) {
    const kv = parseCookieKV(h);
    if (kv) cookies.set(kv.name, kv.value);
  }

  const xsrf = cookies.get("XSRF-TOKEN");
  if (!xsrf) {
    throw new Error("Barchart seed did not return XSRF-TOKEN cookie");
  }

  const cookieHeader = Array.from(cookies.entries())
    .map(([k, v]) => `${k}=${v}`)
    .join("; ");

  // Fetch quotes
  const apiUrl = new URL(BARCHART_QUOTE_URL);
  apiUrl.searchParams.set("symbols", symbols.join(","));
  apiUrl.searchParams.set("fields", "symbol,lastPrice,open,high,low,previousClose,volume,tradeTime");
  apiUrl.searchParams.set("raw", "1");

  const res = await fetch(apiUrl.toString(), {
    headers: {
      "User-Agent": "ZINC-Fusion/1.0",
      "X-Requested-With": "XMLHttpRequest",
      "X-XSRF-TOKEN": decodeURIComponent(xsrf),
      Cookie: cookieHeader,
      Accept: "application/json",
    },
  });

  if (!res.ok) {
    throw new Error(`Barchart API failed: ${res.status}`);
  }

  const json = await res.json();
  return (json.data || []) as BarchartQuote[];
}

function computeRowHash(symbol: string, date: string): string {
  return createHash("sha256").update(`${symbol}|${date}`).digest("hex");
}

export const barchartEtfDaily = inngest.createFunction(
  { id: "barchart-etf-daily", name: "Barchart ETF Daily Prices", retries: 2 },
  { cron: "0 0 * * 1-5" }, // 6 PM CT weekdays (UTC 0)
  async ({ step, logger }) => {
    if (!process.env.DATABASE_URL) {
      throw new Error("DATABASE_URL not configured");
    }

    const client = await pool.connect();
    let inserted = 0;
    let skipped = 0;

    try {
      const symbols = ETF_SYMBOLS.map((e) => e.symbol);

      // Fetch all quotes in batches
      const quotes = await step.run("fetch-quotes", async () => {
        return await fetchBarchartQuotes(symbols);
      });

      logger.info(`Fetched ${quotes.length} ETF quotes from Barchart`);

      // Insert each quote
      for (const quote of quotes) {
        const etfConfig = ETF_SYMBOLS.find((e) => e.symbol === quote.symbol);
        if (!etfConfig) continue;

        // Parse trade date from tradeTime
        const tradeDate = quote.tradeTime
          ? quote.tradeTime.split("T")[0]
          : new Date().toISOString().split("T")[0];

        const rowHash = computeRowHash(quote.symbol, tradeDate);

        // Check if exists
        const existing = await client.query(
          `SELECT 1 FROM mkt.etf_1d WHERE row_hash = $1 LIMIT 1`,
          [rowHash]
        );

        if (existing.rows.length > 0) {
          skipped++;
          continue;
        }

        try {
          await client.query(
            `INSERT INTO mkt.etf_1d (
               symbol, event_date, open, high, low, close, volume,
               source, row_hash, specialist_tags
             ) VALUES ($1, $2::date, $3, $4, $5, $6, $7, $8, $9, $10)`,
            [
              quote.symbol,
              tradeDate,
              quote.open || null,
              quote.high || null,
              quote.low || null,
              quote.lastPrice || null,
              quote.volume || null,
              "barchart",
              rowHash,
              etfConfig.tags,
            ]
          );
          inserted++;
        } catch (err) {
          logger.warn(`Failed to insert ${quote.symbol}: ${err}`);
        }
      }

      return {
        status: "success",
        fetched: quotes.length,
        inserted,
        skipped,
      };
    } finally {
      client.release();
    }
  }
);

/**
 * Manual backfill function - uses Barchart historical API
 */
export const barchartEtfBackfill = inngest.createFunction(
  { id: "barchart-etf-backfill", name: "Barchart ETF 1-Year Backfill", retries: 1 },
  { event: "barchart-etf/backfill" },
  async ({ step, logger }) => {
    if (!process.env.DATABASE_URL) {
      throw new Error("DATABASE_URL not configured");
    }

    const client = await pool.connect();
    let totalInserted = 0;

    try {
      // Bootstrap session
      const session = await step.run("get-session", async () => {
        const seed = await fetch(SEED_URL, {
          headers: { "User-Agent": "ZINC-Fusion/1.0" },
        });

        const cookies = new Map<string, string>();
        for (const h of getSetCookieHeaders(seed)) {
          const kv = parseCookieKV(h);
          if (kv) cookies.set(kv.name, kv.value);
        }

        const xsrf = cookies.get("XSRF-TOKEN");
        if (!xsrf) throw new Error("No XSRF token");

        return {
          xsrf,
          cookieHeader: Array.from(cookies.entries())
            .map(([k, v]) => `${k}=${v}`)
            .join("; "),
        };
      });

      // Fetch historical data for each symbol
      for (const etf of ETF_SYMBOLS) {
        const history = await step.run(`fetch-${etf.symbol}`, async () => {
          const histUrl = new URL("https://www.barchart.com/proxies/core-api/v1/historical/get");
          histUrl.searchParams.set("symbol", etf.symbol);
          histUrl.searchParams.set("type", "daily");
          histUrl.searchParams.set("startDate", getDateMinusYears(1));
          histUrl.searchParams.set("endDate", new Date().toISOString().split("T")[0]);
          histUrl.searchParams.set("raw", "1");

          const res = await fetch(histUrl.toString(), {
            headers: {
              "User-Agent": "ZINC-Fusion/1.0",
              "X-Requested-With": "XMLHttpRequest",
              "X-XSRF-TOKEN": decodeURIComponent(session.xsrf),
              Cookie: session.cookieHeader,
              Accept: "application/json",
            },
          });

          if (!res.ok) {
            logger.warn(`Failed to fetch history for ${etf.symbol}: ${res.status}`);
            return [];
          }

          const json = await res.json();
          return json.data || [];
        });

        logger.info(`Fetched ${history.length} days for ${etf.symbol}`);

        let inserted = 0;
        for (const bar of history) {
          const tradeDate = bar.tradingDay || bar.tradeTime?.split("T")[0];
          if (!tradeDate) continue;

          const rowHash = computeRowHash(etf.symbol, tradeDate);

          const existing = await client.query(
            `SELECT 1 FROM mkt.etf_1d WHERE row_hash = $1 LIMIT 1`,
            [rowHash]
          );

          if (existing.rows.length > 0) continue;

          try {
            await client.query(
              `INSERT INTO mkt.etf_1d (
                 symbol, event_date, open, high, low, close, volume,
                 source, row_hash, specialist_tags
               ) VALUES ($1, $2::date, $3, $4, $5, $6, $7, $8, $9, $10)`,
              [
                etf.symbol,
                tradeDate,
                bar.open || null,
                bar.high || null,
                bar.low || null,
                bar.close || bar.lastPrice || null,
                bar.volume || null,
                "barchart",
                rowHash,
                etf.tags,
              ]
            );
            inserted++;
          } catch {
            // Skip duplicates
          }
        }

        totalInserted += inserted;
        logger.info(`Inserted ${inserted} rows for ${etf.symbol}`);

        // Rate limit
        await new Promise((r) => setTimeout(r, 500));
      }

      return {
        status: "success",
        totalInserted,
        symbols: ETF_SYMBOLS.length,
      };
    } finally {
      client.release();
    }
  }
);

function getDateMinusYears(years: number): string {
  const d = new Date();
  d.setFullYear(d.getFullYear() - years);
  return d.toISOString().split("T")[0];
}
