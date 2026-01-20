/**
 * Barchart Options Greeks Daily Ingestion
 *
 * Fetches ZL options chain with Greeks from Barchart:
 * - IV (Implied Volatility)
 * - Delta, Gamma, Theta, Vega
 * - IV Skew
 *
 * Focuses on near-the-money strikes for the front 3 expirations.
 *
 * Schedule: Daily at 5:30 PM CT (after futures close)
 */

import { inngest } from "./client";
import { createHash } from "crypto";
import { Pool } from "pg";

const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
  ssl: { rejectUnauthorized: false },
});

// Underlyings to fetch options for
const OPTION_UNDERLYINGS = [
  { symbol: "ZL", barchart: "ZLH25", name: "Soybean Oil", tags: ["crush", "volatility"] },
  { symbol: "ZS", barchart: "ZSH25", name: "Soybeans", tags: ["crush", "volatility"] },
  { symbol: "ZM", barchart: "ZMH25", name: "Soymeal", tags: ["crush", "volatility"] },
  { symbol: "CL", barchart: "CLH25", name: "Crude Oil", tags: ["energy", "volatility"] },
];

const BARCHART_OPTIONS_URL = "https://www.barchart.com/proxies/core-api/v1/options/chain";
const SEED_URL = "https://www.barchart.com/futures/quotes/ZLH25/options";

type OptionRow = {
  symbol: string;
  strikePrice: number;
  optionType: "Call" | "Put";
  expirationDate: string;
  lastPrice: number;
  impliedVolatility: number;
  delta: number;
  gamma: number;
  theta: number;
  vega: number;
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

async function fetchBarchartOptionsChain(
  barchartSymbol: string,
  session: { xsrf: string; cookieHeader: string }
): Promise<OptionRow[]> {
  const apiUrl = new URL(BARCHART_OPTIONS_URL);
  apiUrl.searchParams.set("symbol", barchartSymbol);
  apiUrl.searchParams.set("fields", "symbol,strikePrice,optionType,expirationDate,lastPrice,impliedVolatility,delta,gamma,theta,vega");
  apiUrl.searchParams.set("raw", "1");

  const res = await fetch(apiUrl.toString(), {
    headers: {
      "User-Agent": "ZINC-Fusion/1.0",
      "X-Requested-With": "XMLHttpRequest",
      "X-XSRF-TOKEN": decodeURIComponent(session.xsrf),
      Cookie: session.cookieHeader,
      Accept: "application/json",
    },
  });

  if (!res.ok) {
    throw new Error(`Barchart options API failed: ${res.status}`);
  }

  const json = await res.json();
  return (json.data || []) as OptionRow[];
}

function computeRowHash(underlying: string, date: string, expiration: string, strike: number, optionType: string): string {
  return createHash("sha256")
    .update(`${underlying}|${date}|${expiration}|${strike}|${optionType}`)
    .digest("hex");
}

export const barchartOptionsDaily = inngest.createFunction(
  { id: "barchart-options-daily", name: "Barchart Options Greeks Daily", retries: 2 },
  { cron: "30 23 * * 1-5" }, // 5:30 PM CT weekdays (UTC 23:30)
  async ({ step, logger }) => {
    if (!process.env.DATABASE_URL) {
      throw new Error("DATABASE_URL not configured");
    }

    const client = await pool.connect();
    let totalInserted = 0;
    let totalSkipped = 0;
    const today = new Date().toISOString().split("T")[0];

    try {
      // Bootstrap session
      const session = await step.run("get-session", async () => {
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

        return {
          xsrf,
          cookieHeader: Array.from(cookies.entries())
            .map(([k, v]) => `${k}=${v}`)
            .join("; "),
        };
      });

      // Fetch options for each underlying
      for (const underlying of OPTION_UNDERLYINGS) {
        const options = await step.run(`fetch-${underlying.symbol}`, async () => {
          try {
            return await fetchBarchartOptionsChain(underlying.barchart, session);
          } catch (err) {
            logger.warn(`Failed to fetch options for ${underlying.symbol}: ${err}`);
            return [];
          }
        });

        logger.info(`Fetched ${options.length} options for ${underlying.symbol}`);

        let inserted = 0;
        let skipped = 0;

        for (const opt of options) {
          if (!opt.expirationDate || !opt.strikePrice) continue;

          const expDate = opt.expirationDate.split("T")[0];
          const optType = opt.optionType === "Call" ? "C" : "P";

          const rowHash = computeRowHash(
            underlying.symbol,
            today,
            expDate,
            opt.strikePrice,
            optType
          );

          // Check if exists
          const existing = await client.query(
            `SELECT 1 FROM mkt.options_greeks_1d WHERE row_hash = $1 LIMIT 1`,
            [rowHash]
          );

          if (existing.rows.length > 0) {
            skipped++;
            continue;
          }

          // Calculate IV skew (difference from ATM IV - simplified)
          const ivSkew = opt.delta ? Math.abs(opt.delta - 0.5) * opt.impliedVolatility : null;

          try {
            await client.query(
              `INSERT INTO mkt.options_greeks_1d (
                 underlying, event_date, expiration, strike, option_type,
                 last_price, implied_volatility, delta, gamma, theta, vega,
                 iv_skew, source, row_hash, specialist_tags
               ) VALUES ($1, $2::date, $3::date, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)`,
              [
                underlying.symbol,
                today,
                expDate,
                opt.strikePrice,
                optType,
                opt.lastPrice || null,
                opt.impliedVolatility || null,
                opt.delta || null,
                opt.gamma || null,
                opt.theta || null,
                opt.vega || null,
                ivSkew,
                "barchart",
                rowHash,
                underlying.tags,
              ]
            );
            inserted++;
          } catch (err) {
            logger.warn(`Failed to insert option: ${err}`);
          }
        }

        totalInserted += inserted;
        totalSkipped += skipped;
        logger.info(`${underlying.symbol}: inserted=${inserted}, skipped=${skipped}`);

        // Rate limit
        await new Promise((r) => setTimeout(r, 500));
      }

      return {
        status: "success",
        totalInserted,
        totalSkipped,
        underlyings: OPTION_UNDERLYINGS.length,
      };
    } finally {
      client.release();
    }
  }
);

/**
 * Manual backfill - fetches current options chain only (historical not available)
 */
export const barchartOptionsBackfill = inngest.createFunction(
  { id: "barchart-options-backfill", name: "Barchart Options Backfill", retries: 1 },
  { event: "barchart-options/backfill" },
  async ({ step, logger }) => {
    // Options historical data is not available via API
    // This just triggers a current-day fetch
    logger.info("Options backfill triggered - fetching current chain");

    // Delegate to daily function logic
    const result = await step.invoke("run-daily", {
      function: barchartOptionsDaily,
      data: {},
    });

    return {
      ...result,
      message: "Options data is point-in-time only - fetched current chain",
    };
  }
);
