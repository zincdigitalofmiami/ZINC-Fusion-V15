import { inngest, DB_CONCURRENCY } from "./client";
import dbPool from "@/lib/db";

const pool = dbPool;

/**
 * CPO Data Sources (in order of preference):
 * 1. Investing.com API (primary) - unofficial, can be flaky
 * 2. Trading Economics (backup) - requires API key
 */

interface CpoData {
  source: string;
  eventDate: string;
  open?: number;
  high?: number;
  low?: number;
  close: number;
}

async function fetchFromInvestingCom(): Promise<CpoData | null> {
  const url = "https://api.investing.com/api/financialdata/8849/historical/chart/?interval=P1D&pointscount=2";

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 15000);
  let res: Response;
  try {
    res = await fetch(url, {
      headers: {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
        "Accept": "application/json",
        "Domain-Id": "www",
      },
      signal: controller.signal,
    });
  } catch (err) {
    clearTimeout(timeout);
    if (err instanceof Error && err.name === "AbortError") {
      console.warn("Investing.com API timed out after 15s");
      return null;
    }
    console.warn(`Investing.com fetch error: ${err}`);
    return null;
  }
  clearTimeout(timeout);

  if (!res.ok) {
    console.warn(`Investing.com API error: ${res.status}`);
    return null;
  }

  // Guard against Cloudflare challenge pages returning HTML
  const ct = res.headers.get("content-type") ?? "";
  if (!ct.includes("json")) {
    console.warn("Investing.com returned non-JSON (likely Cloudflare challenge)");
    return null;
  }

  const json = await res.json();
  if (!json?.data || json.data.length === 0) {
    return null;
  }

  const latestCandle = json.data[json.data.length - 1];
  const [timestamp, open, high, low, close] = latestCandle;
  if (![open, high, low, close].every((v) => Number.isFinite(Number(v)))) {
    return null;
  }
  const eventDate = new Date(timestamp).toISOString().split("T")[0];

  return {
    source: "investing_com",
    eventDate,
    open: Number(open),
    high: Number(high),
    low: Number(low),
    close: Number(close),
  };
}

async function fetchFromTradingEconomics(apiKey: string): Promise<CpoData | null> {
  const url = `https://api.tradingeconomics.com/markets/commodity/palm%20oil?c=${apiKey}`;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 15000);
  try {
    const res = await fetch(url, { signal: controller.signal });
    if (!res.ok) {
      console.warn(`Trading Economics API error: ${res.status}`);
      return null;
    }
    const data = await res.json();
    if (!Array.isArray(data) || data.length === 0) return null;
    const last = Number(data[0]?.Last);
    if (!Number.isFinite(last) || last <= 0) return null;
    const eventDate = new Date().toISOString().split("T")[0];
    return {
      source: "trading_economics",
      eventDate,
      close: last,
    };
  } catch (err) {
    if (err instanceof Error && err.name === "AbortError") {
      console.warn("Trading Economics API timed out after 15s");
      return null;
    }
    console.warn(`Trading Economics fetch error: ${err}`);
    return null;
  } finally {
    clearTimeout(timeout);
  }
}

/**
 * Primary CPO ingestion
 * Uses Investing.com as the only primary source.
 */
export const cpoPalmOilDaily = inngest.createFunction(
  { id: "cpo-palm-oil-daily", name: "CPO Palm Oil Daily", retries: 3, concurrency: [DB_CONCURRENCY] },
  { cron: "0 6 * * *" }, // Daily at 06:00 UTC
  async ({ step, logger }) => {
    // Try to fetch CPO data from multiple sources
    const data = await step.run("fetch-cpo-price", async () => {
      logger.info("Attempting Investing.com...");
      const result = await fetchFromInvestingCom();
      if (result) {
        logger.info(`Got CPO from Investing.com: ${result.close}`);
        return result;
      }

      const teKey = process.env.TRADING_ECONOMICS_API_KEY;
      if (!teKey) {
        logger.warn("Investing.com unavailable and TRADING_ECONOMICS_API_KEY not configured");
        return null;
      }

      logger.info("Investing.com unavailable; falling back to Trading Economics...");
      const fallback = await fetchFromTradingEconomics(teKey);
      if (fallback) {
        logger.info(`Got CPO from Trading Economics: ${fallback.close}`);
        return fallback;
      }

      logger.warn("Both CPO sources unavailable for this run");
      return null;
    });

    if (!data) {
      return { status: "upstream_unavailable", inserted: 0 };
    }

    // Insert the data
    const result = await step.run("insert-cpo-data", async () => {
      const client = await pool.connect();
      try {
        await client.query(
          `INSERT INTO mkt.futures_1d
            (event_date, symbol, open, high, low, close, source, ingested_at)
           VALUES ($1, 'CPO', $2, $3, $4, $5, $6, NOW())
           ON CONFLICT (event_date, symbol) DO UPDATE SET
             open = COALESCE(EXCLUDED.open, mkt.futures_1d.open),
             high = COALESCE(EXCLUDED.high, mkt.futures_1d.high),
             low = COALESCE(EXCLUDED.low, mkt.futures_1d.low),
             close = EXCLUDED.close,
             source = EXCLUDED.source,
             ingested_at = NOW()`,
          [data.eventDate, data.open, data.high, data.low, data.close, data.source]
        );

        return {
          status: "success",
          source: data.source,
          date: data.eventDate,
          close: data.close,
        };
      } finally {
        client.release();
      }
    });

    logger.info("CPO daily update complete", result);
    return result;
  }
);

/**
 * Backup: Fetch from Trading Economics if API key is available
 * Runs 2 hours after primary to fill any gaps
 */
export const cpoTradingEconomics = inngest.createFunction(
  { id: "cpo-trading-economics", name: "CPO Trading Economics", concurrency: [DB_CONCURRENCY] },
  { cron: "30 6 * * *" }, // Daily at 06:30 UTC (backup)
  async ({ step, logger }) => {
    const apiKey = process.env.TRADING_ECONOMICS_API_KEY;

    if (!apiKey) {
      logger.info("Trading Economics API key not configured, skipping");
      return { status: "skipped", reason: "no_api_key" };
    }

    // Check if we already have data for today
    const existingData = await step.run("check-existing", async () => {
      const client = await pool.connect();
      try {
        const today = new Date().toISOString().split("T")[0];
        const result = await client.query(
          `SELECT close FROM mkt.futures_1d WHERE event_date = $1 AND symbol = 'CPO'`,
          [today]
        );
        return result.rows.length > 0 ? result.rows[0].close : null;
      } finally {
        client.release();
      }
    });

    if (existingData !== null) {
      logger.info(`CPO already has data for today (close=${existingData}), skipping Trading Economics`);
      return { status: "skipped", reason: "already_have_data", existingClose: existingData };
    }

    const data = await step.run("fetch-te-palm-oil", async () => fetchFromTradingEconomics(apiKey));

    const result = await step.run("insert-te-data", async () => {
      const client = await pool.connect();
      try {
        if (!data) {
          return { status: "no_data" };
        }

        await client.query(
          `INSERT INTO mkt.futures_1d
            (event_date, symbol, close, source, ingested_at)
           VALUES ($1, 'CPO', $2, 'trading_economics', NOW())
           ON CONFLICT (event_date, symbol) DO UPDATE SET
             close = EXCLUDED.close,
             source = EXCLUDED.source,
             ingested_at = NOW()`,
          [data.eventDate, data.close]
        );

        return {
          status: "success",
          date: data.eventDate,
          close: data.close,
        };
      } finally {
        client.release();
      }
    });

    logger.info("CPO Trading Economics update complete", result);
    return result;
  }
);
