import { inngest } from "./client";
import { Pool } from "pg";

const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
  ssl: { rejectUnauthorized: false },
});

/**
 * Fetch ZL 15-minute bars from Yahoo and write to analytics.zl_price_15m
 * Runs every 15 minutes
 */
export const zl15m = inngest.createFunction(
  { id: "zl-15m", name: "ZL 15m Bars" },
  { cron: "*/15 * * * *" }, // Every 15 min
  async ({ step }) => {
    // Step 1: Fetch 15m bars from Yahoo v8 chart API
    const bars = await step.run("fetch-yahoo-15m", async () => {
      const res = await fetch(
        "https://query1.finance.yahoo.com/v8/finance/chart/ZL=F?interval=15m&range=1d"
      );
      const json = await res.json();
      const result = json.chart?.result?.[0];

      if (!result) {
        throw new Error("No chart data returned from Yahoo");
      }

      const timestamps = result.timestamp ?? [];
      const ohlc = result.indicators?.quote?.[0] ?? {};
      const meta = result.meta;

      // Build array of bars
      const barsData: Array<{
        timestamp: Date;
        open: number;
        high: number;
        low: number;
        close: number;
        volume: number;
        previousClose: number;
        dayHigh: number;
        dayLow: number;
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
            timestamp: new Date(ts * 1000),
            open,
            high,
            low,
            close,
            volume: volume ?? 0,
            previousClose: meta.chartPreviousClose ?? meta.previousClose ?? close,
            dayHigh: meta.regularMarketDayHigh ?? high,
            dayLow: meta.regularMarketDayLow ?? low,
          });
        }
      }

      return barsData;
    });

    if (!bars || bars.length === 0) {
      return { status: "no_data", message: "No 15m bars returned" };
    }

    // Step 2: Upsert bars to analytics.zl_price_15m
    const inserted = await step.run("upsert-bars", async () => {
      const client = await pool.connect();
      let count = 0;
      try {
        for (const bar of bars) {
          const change = bar.close - bar.previousClose;
          const changePct = (change / bar.previousClose) * 100;

          await client.query(
            `INSERT INTO analytics.zl_price_15m
              (timestamp, open, high, low, close, volume, previous_close, change, change_percent, day_high, day_low, source, created_at)
             VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, 'yahoo', NOW())
             ON CONFLICT (timestamp) DO UPDATE SET
               open = EXCLUDED.open,
               high = EXCLUDED.high,
               low = EXCLUDED.low,
               close = EXCLUDED.close,
               volume = EXCLUDED.volume,
               previous_close = EXCLUDED.previous_close,
               change = EXCLUDED.change,
               change_percent = EXCLUDED.change_percent,
               day_high = EXCLUDED.day_high,
               day_low = EXCLUDED.day_low,
               source = EXCLUDED.source`,
            [
              bar.timestamp,
              bar.open,
              bar.high,
              bar.low,
              bar.close,
              bar.volume,
              bar.previousClose,
              change,
              changePct,
              bar.dayHigh,
              bar.dayLow,
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
      latestBar: lastBar ? new Date(lastBar.timestamp).toISOString() : null,
    };
  }
);
