import { inngest, DB_CONCURRENCY } from "./client";
import { fetchDatabentoCsv, parseDatabentoOhlcvCsv } from "../lib/databento";
import dbPool from "@/lib/db";

const pool = dbPool;

/**
 * Fetch ZL 1-hour bars from Databento and write to analytics.zl_price_1h
 * Runs every hour
 */
export const zl1h = inngest.createFunction(
  { id: "zl-1h", name: "ZL 1h Bars", concurrency: [DB_CONCURRENCY] },
  { cron: "0 * * * *" }, // Every hour on the hour
  async ({ step }) => {
    const endStr = await step.run("compute-end-time", async () => {
      const d = new Date(Date.now() - 24 * 60 * 60 * 1000);
      return d.toISOString();
    });
    const end = new Date(endStr);

    const startStr = await step.run("compute-start-time", async () => {
      const client = await pool.connect();
      try {
        const result = await client.query<{ ts: Date | null }>(
          `SELECT MAX(timestamp) AS ts FROM analytics.zl_price_1h`
        );
        const lastTs = result.rows[0]?.ts ? new Date(result.rows[0].ts) : null;
        const bufferMs = 12 * 60 * 60 * 1000;
        const defaultWindowMs = 14 * 24 * 60 * 60 * 1000;
        const endDate = new Date(endStr);
        const base = lastTs ? lastTs.getTime() - bufferMs : endDate.getTime() - defaultWindowMs;
        const d = new Date(Math.max(0, base));
        return d.toISOString();
      } finally {
        client.release();
      }
    });
    const start = new Date(startStr);

    if (start >= end) {
      return { status: "no_data", message: "No new historical window available" };
    }

    // Step 1: Fetch 1h bars from Databento
    const bars = await step.run("fetch-databento-1h", async () => {
      const csv = await fetchDatabentoCsv({
        dataset: "GLBX.MDP3",
        schema: "ohlcv-1h",
        symbols: "ZL.n.0",  // OI-ranked for consistency with daily jobs
        stype_in: "continuous",
        start: startStr,
        end: endStr,
        encoding: "csv",
        pretty_ts: "true",
        pretty_px: "true",
      });

      const parsed = parseDatabentoOhlcvCsv(csv);
      return parsed.map((bar) => ({
        eventTime: bar.tsEvent,
        open: bar.open,
        high: bar.high,
        low: bar.low,
        close: bar.close,
        volume: bar.volume ?? 0,
      }));
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
             VALUES ($1, $2, $3, $4, $5, $6, 'databento', NOW())
             ON CONFLICT (timestamp) DO UPDATE SET
               open = EXCLUDED.open,
               high = EXCLUDED.high,
               low = EXCLUDED.low,
               close = EXCLUDED.close,
               volume = EXCLUDED.volume,
               source = EXCLUDED.source
             WHERE analytics.zl_price_1h.source IS NULL
                OR analytics.zl_price_1h.source <> 'databento_live'`,
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
