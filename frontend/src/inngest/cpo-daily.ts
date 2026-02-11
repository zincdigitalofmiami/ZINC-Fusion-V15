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

  const res = await fetch(url, {
    headers: {
      "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
      "Accept": "application/json",
      "Domain-Id": "www",
    },
  });

  if (!res.ok) {
    console.warn(`Investing.com API error: ${res.status}`);
    return null;
  }

  const json = await res.json();
  if (!json?.data || json.data.length === 0) {
    return null;
  }

  const latestCandle = json.data[json.data.length - 1];
  const [timestamp, open, high, low, close] = latestCandle;
  const eventDate = new Date(timestamp).toISOString().split("T")[0];

  return { source: "investing_com", eventDate, open, high, low, close };
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

      throw new Error("CPO primary source failed (Investing.com)");
    });

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

    const data = await step.run("fetch-te-palm-oil", async () => {
      const url = `https://api.tradingeconomics.com/markets/commodity/palm%20oil?c=${apiKey}`;
      const res = await fetch(url);

      if (!res.ok) {
        throw new Error(`Trading Economics API error: ${res.status}`);
      }

      return res.json();
    });

    const result = await step.run("insert-te-data", async () => {
      const client = await pool.connect();
      try {
        if (!data || data.length === 0) {
          return { status: "no_data" };
        }

        const palmOil = data[0];
        const eventDate = new Date().toISOString().split("T")[0];

        await client.query(
          `INSERT INTO mkt.futures_1d
            (event_date, symbol, close, source, ingested_at)
           VALUES ($1, 'CPO', $2, 'trading_economics', NOW())
           ON CONFLICT (event_date, symbol) DO UPDATE SET
             close = EXCLUDED.close,
             source = EXCLUDED.source,
             ingested_at = NOW()`,
          [eventDate, palmOil.Last]
        );

        return {
          status: "success",
          date: eventDate,
          close: palmOil.Last,
        };
      } finally {
        client.release();
      }
    });

    logger.info("CPO Trading Economics update complete", result);
    return result;
  }
);
