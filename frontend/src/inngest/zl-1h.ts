import { inngest } from "./client";
import { Pool } from "pg";

const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
  ssl: { rejectUnauthorized: false },
});

/**
 * Fetch ZL 1-hour bars from Yahoo and write to analytics.zl_price_1h
 * Runs every hour
 */
export const zl1h = inngest.createFunction(
  { id: "zl-1h", name: "ZL 1h Bars" },
  { cron: "0 * * * *" }, // Every hour on the hour
  async ({ step }) => {
    // Step 1: Fetch 1h bars from Yahoo v8 chart API
    const bars = await step.run("fetch-yahoo-1h", async () => {
      const res = await fetch(
        "https://query1.finance.yahoo.com/v8/finance/chart/ZL=F?interval=1h&range=5d"
      );
      const json = await res.json();
      const result = json.chart?.result?.[0];

      if (!result) {
        throw new Error("No chart data returned from Yahoo");
      }

      const timestamps = result.timestamp ?? [];
      const ohlc = result.indicators?.quote?.[0] ?? {};

      // Build array of bars
      const barsData: Array<{
        eventTime: Date;
        open: number;
        high: number;
        low: number;
        close: number;
        volume: number;
      }> = [];

      for (let i = 0; i < timestamps.length; i++) {
        const ts = timestamps[i];
        const open = ohlc.open?.[i];
        const high = ohlc.high?.[i];
        const low = ohlc.low?.[i];
        const close = ohlc.close?.[i];
        const volume = ohlc.volume?.[i];

        // Skip bars with null values
        if (ts && open != null && high != null && low != null && close != null) {
          barsData.push({
            eventTime: new Date(ts * 1000),
            open,
            high,
            low,
            close,
            volume: volume ?? 0,
          });
        }
      }

      return barsData;
    });

    if (!bars || bars.length === 0) {
      return { status: "no_data", message: "No hourly bars returned" };
    }

    // Step 2: Upsert bars to analytics.zl_price_1h
    const inserted = await step.run("upsert-bars", async () => {
      const client = await pool.connect();
      let count = 0;
      try {
        for (const bar of bars) {
          await client.query(
            `INSERT INTO analytics.zl_price_1h
              (timestamp, open, high, low, close, volume, source, created_at)
             VALUES ($1, $2, $3, $4, $5, $6, 'yahoo', NOW())
             ON CONFLICT (timestamp) DO UPDATE SET
               open = EXCLUDED.open,
               high = EXCLUDED.high,
               low = EXCLUDED.low,
               close = EXCLUDED.close,
               volume = EXCLUDED.volume,
               source = EXCLUDED.source`,
            [
              bar.eventTime,
              bar.open,
              bar.high,
              bar.low,
              bar.close,
              bar.volume,
            ]
          );
          count++;
        }
      } finally {
        client.release();
      }
      return count;
    });

    const lastBar = bars[bars.length - 1];
    return {
      status: "success",
      symbol: "ZL",
      barsProcessed: inserted,
      latestBar: lastBar ? new Date(lastBar.eventTime).toISOString() : null,
    };
  }
);
