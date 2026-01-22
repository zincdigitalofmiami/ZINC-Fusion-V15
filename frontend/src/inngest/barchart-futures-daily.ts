/**
 * Barchart Futures Daily Price Ingestion
 *
 * Fetches daily OHLCV data from Barchart for soft commodities:
 * - CT (Cotton)
 * - OJ (Orange Juice)
 * - LBR (Lumber)
 *
 * Note: RS (Canola) moved to yahoo-eod.ts. CPO handled by cpo-daily.ts.
 *
 * Uses Barchart's core-api proxy (same method as barchart-zl-news.ts)
 */

import { inngest } from "./client";
import { Pool } from "pg";

const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
  ssl: { rejectUnauthorized: false },
});

// Symbols to fetch from Barchart (use continuous contract notation).
// Yahoo is preferred when available.
const BARCHART_SYMBOLS = [
  { barchart: "CT*0", db: "CT", name: "Cotton" },
  { barchart: "OJ*0", db: "OJ", name: "Orange Juice" },
  { barchart: "LBR*0", db: "LBR", name: "Lumber" },
];

const BARCHART_QUOTE_URL = "https://www.barchart.com/proxies/core-api/v1/quotes/get";
// Use CT (Cotton) for session bootstrap - must be a symbol we actually fetch
const SEED_URL = "https://www.barchart.com/futures/quotes/CT*0/overview";

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

function parseBarchartNumber(value: unknown): number | null {
  if (typeof value === "number") return Number.isFinite(value) ? value : null;
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  if (!trimmed) return null;
  const cleaned = trimmed.replace(/,/g, "").replace(/[^0-9.+-]/g, "");
  if (!cleaned) return null;
  const parsed = Number(cleaned);
  return Number.isFinite(parsed) ? parsed : null;
}

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
    throw new Error(`Barchart quote API failed: ${res.status}`);
  }

  const json = await res.json();

  // Parse response - format: { data: { quote: [...] } } or { data: [...] }
  const data = json?.data;
  if (!data) return [];

  const quotes = Array.isArray(data) ? data : (data.quote || data.quotes || []);

  return quotes.map((q: Record<string, unknown>) => ({
    symbol: String(q.symbol || ""),
    lastPrice: parseBarchartNumber(q.lastPrice) ?? 0,
    open: parseBarchartNumber(q.open) ?? parseBarchartNumber(q.lastPrice) ?? 0,
    high: parseBarchartNumber(q.high) ?? parseBarchartNumber(q.lastPrice) ?? 0,
    low: parseBarchartNumber(q.low) ?? parseBarchartNumber(q.lastPrice) ?? 0,
    previousClose: parseBarchartNumber(q.previousClose) ?? 0,
    volume: parseBarchartNumber(q.volume) ?? 0,
    tradeTime: String(q.tradeTime || ""),
  }));
}

/**
 * Barchart Futures Daily Pull
 * Runs at 5:00 PM CT (after CME close, 11 PM UTC)
 */
export const barchartFuturesDaily = inngest.createFunction(
  { id: "barchart-futures-daily", name: "Barchart Futures Daily", retries: 3 },
  { cron: "0 23 * * 1-5" }, // 11 PM UTC = 5 PM CT, Mon-Fri
  async ({ step, logger }) => {
    const results: { symbol: string; status: string; close?: number }[] = [];

    // Fetch all quotes from Barchart
    const quotes = await step.run("fetch-barchart-quotes", async () => {
      const symbols = BARCHART_SYMBOLS.map((s) => s.barchart);
      return fetchBarchartQuotes(symbols);
    });

    logger.info(`Fetched ${quotes.length} quotes from Barchart`);

    // Insert each quote into the database
    for (const config of BARCHART_SYMBOLS) {
      const quote = quotes.find(
        (q) => q.symbol === config.barchart ||
               q.symbol === config.barchart.replace("*0", "") ||
               q.symbol.startsWith(config.db)
      );

      if (!quote || quote.lastPrice === 0) {
        results.push({ symbol: config.db, status: "not_found" });
        continue;
      }

      await step.run(`insert-${config.db}`, async () => {
        const client = await pool.connect();
        try {
          // Parse trade time to get event date
          let eventDate = new Date().toISOString().split("T")[0];
          if (quote.tradeTime) {
            try {
              const parsed = new Date(quote.tradeTime);
              if (!isNaN(parsed.getTime())) {
                eventDate = parsed.toISOString().split("T")[0];
              }
            } catch {
              // Use today's date if parsing fails
            }
          }

          await client.query(
            `INSERT INTO mkt.futures_1d
              (event_date, symbol, open, high, low, close, volume, source, ingested_at)
             VALUES ($1, $2, $3, $4, $5, $6, $7, 'barchart_api', NOW())
             ON CONFLICT (event_date, symbol) DO UPDATE SET
               open = EXCLUDED.open,
               high = EXCLUDED.high,
               low = EXCLUDED.low,
               close = EXCLUDED.close,
               volume = EXCLUDED.volume,
               source = EXCLUDED.source,
               ingested_at = NOW()`,
            [
              eventDate,
              config.db,
              quote.open,
              quote.high,
              quote.low,
              quote.lastPrice,
              quote.volume,
            ]
          );

          results.push({
            symbol: config.db,
            status: "success",
            close: quote.lastPrice,
          });
        } finally {
          client.release();
        }
      });
    }

    logger.info("Barchart futures daily complete", { results });
    return { status: "success", results };
  }
);

/**
 * Manual trigger for testing
 */
export const barchartFuturesManual = inngest.createFunction(
  { id: "barchart-futures-manual", name: "Barchart Futures Manual" },
  { event: "barchart/futures.fetch" },
  async ({ step, logger }) => {
    const quotes = await step.run("fetch-quotes", async () => {
      const symbols = BARCHART_SYMBOLS.map((s) => s.barchart);
      return fetchBarchartQuotes(symbols);
    });

    logger.info(`Manual fetch got ${quotes.length} quotes`);
    return { quotes };
  }
);
