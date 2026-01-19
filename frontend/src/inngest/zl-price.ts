import { inngest } from "./client";
import { Pool } from "pg";

const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
  ssl: { rejectUnauthorized: false },
});

/**
 * Fetch ZL price from Yahoo and write to analytics.zl_live
 * Runs every 5 minutes for tight freshness requirement
 */
export const zlPrice = inngest.createFunction(
  { id: "zl-price", name: "ZL Price Update" },
  { cron: "*/15 * * * *" }, // Every 15 min - avoids Yahoo rate limits
  async ({ step }) => {
    // Step 1: Fetch from Yahoo v8 chart API
    // Note: v8 uses chartPreviousClose (not previousClose)
    // Open comes from indicators.quote[0].open (last element is today)
    const data = await step.run("fetch-yahoo", async () => {
      const res = await fetch(
        "https://query1.finance.yahoo.com/v8/finance/chart/ZL=F?interval=1d&range=5d"
      );
      const json = await res.json();
      const result = json.chart?.result?.[0];

      if (!result) {
        throw new Error("No chart data returned from Yahoo");
      }

      const meta = result.meta;
      const ohlc = result.indicators?.quote?.[0] ?? {};

      // Get today's open from the last element of the open array
      const openArray = ohlc.open ?? [];
      const todayOpen = openArray.length > 0 ? openArray[openArray.length - 1] : meta.regularMarketPrice;

      return {
        price: meta.regularMarketPrice,
        previousClose: meta.chartPreviousClose, // v8 uses chartPreviousClose
        dayHigh: meta.regularMarketDayHigh ?? meta.regularMarketPrice,
        dayLow: meta.regularMarketDayLow ?? meta.regularMarketPrice,
        dayOpen: todayOpen ?? meta.regularMarketPrice,
        volume: meta.regularMarketVolume ?? 0,
      };
    });

    // Step 2: Calculate change
    const change = data.price - data.previousClose;
    const changePct = (change / data.previousClose) * 100;

    // Step 3: Write to analytics.zl_live
    await step.run("write-db", async () => {
      const client = await pool.connect();
      try {
        await client.query(
          `UPDATE analytics.zl_live SET
            price = $1,
            previous_close = $2,
            change = $3,
            change_pct = $4,
            day_high = $5,
            day_low = $6,
            day_open = $7,
            volume = $8,
            timestamp = NOW(),
            source = 'yahoo',
            updated_at = NOW()
          WHERE id = 1`,
          [
            data.price,
            data.previousClose,
            change,
            changePct,
            data.dayHigh,
            data.dayLow,
            data.dayOpen,
            data.volume,
          ]
        );
      } finally {
        client.release();
      }
    });

    return { 
      symbol: "ZL", 
      price: data.price, 
      change: changePct.toFixed(2) + "%",
      updatedAt: new Date().toISOString()
    };
  }
);
