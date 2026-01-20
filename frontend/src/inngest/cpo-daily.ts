import { inngest } from "./client";
import { Pool } from "pg";

const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
  ssl: { rejectUnauthorized: false },
});

/**
 * Fetch daily CPO (Crude Palm Oil) prices from Investing.com
 * CPO is traded on Bursa Malaysia and not available on Yahoo Finance
 * Runs daily at 10:00 AM UTC (after Asian market close)
 */
export const cpoPalmOilDaily = inngest.createFunction(
  { id: "cpo-palm-oil-daily", name: "CPO Palm Oil Daily" },
  { cron: "0 10 * * 1-5" }, // 10AM UTC, Mon-Fri (after Asian markets)
  async ({ step, logger }) => {
    // Fetch CPO price from Investing.com API endpoint
    const data = await step.run("fetch-cpo-price", async () => {
      // Use the Investing.com commodity endpoint
      const url = "https://api.investing.com/api/financialdata/8849/historical/chart/?interval=P1D&pointscount=2";

      const res = await fetch(url, {
        headers: {
          "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
          "Accept": "application/json",
          "Domain-Id": "www",
        },
      });

      if (!res.ok) {
        throw new Error(`Investing.com API error: ${res.status}`);
      }

      const json = await res.json();
      return json;
    });

    // Parse and insert the data
    const result = await step.run("insert-cpo-data", async () => {
      const client = await pool.connect();
      try {
        // Investing.com returns OHLC data in the format:
        // { data: [[timestamp, open, high, low, close, volume], ...] }
        if (!data?.data || data.data.length === 0) {
          return { status: "no_data" };
        }

        const latestCandle = data.data[data.data.length - 1];
        const [timestamp, open, high, low, close] = latestCandle;
        const eventDate = new Date(timestamp).toISOString().split("T")[0];

        await client.query(
          `INSERT INTO mkt.futures_1d
            (event_date, symbol, open, high, low, close, source, ingested_at)
           VALUES ($1, 'CPO', $2, $3, $4, $5, 'investing_com', NOW())
           ON CONFLICT (event_date, symbol) DO UPDATE SET
             open = EXCLUDED.open,
             high = EXCLUDED.high,
             low = EXCLUDED.low,
             close = EXCLUDED.close,
             source = EXCLUDED.source,
             ingested_at = NOW()`,
          [eventDate, open, high, low, close]
        );

        return {
          status: "success",
          date: eventDate,
          close: close,
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
 * Alternative: Fetch from Trading Economics if API key is available
 */
export const cpoTradingEconomics = inngest.createFunction(
  { id: "cpo-trading-economics", name: "CPO Trading Economics" },
  { cron: "0 12 * * 1-5" }, // Noon UTC as backup
  async ({ step, logger }) => {
    const apiKey = process.env.TRADING_ECONOMICS_API_KEY;

    if (!apiKey) {
      logger.info("Trading Economics API key not configured, skipping");
      return { status: "skipped", reason: "no_api_key" };
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
