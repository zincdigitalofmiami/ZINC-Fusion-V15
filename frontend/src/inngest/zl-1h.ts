import { inngest, DB_CONCURRENCY } from "./client";
import { fetchDatabentoCsv, parseDatabentoOhlcvCsv } from "../lib/databento";
import dbPool from "@/lib/db";

const pool = dbPool;

/**
 * Fetch ZL 1-hour bars from Databento and write to analytics.price_1h
 * Runs every hour
 */
export const zl1h = inngest.createFunction(
  { id: "zl-1h", name: "ZL 1h Bars", concurrency: [DB_CONCURRENCY] },
  { cron: "5 * * * *" }, // Every hour at :05 (staggered from zl-15m to avoid DB contention)
  async ({ step, logger }) => {
    const endStr = await step.run("compute-end-time", async () => {
      const d = new Date(Date.now() - 24 * 60 * 60 * 1000);
      return d.toISOString();
    });
    const end = new Date(endStr);

    const startStr = await step.run("compute-start-time", async () => {
      const client = await pool.connect();
      try {
        const result = await client.query<{ ts: Date | null }>(
          `SELECT MAX(timestamp) AS ts FROM analytics.price_1h`
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
      try {
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
      } catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        logger.warn(`Databento 1h fetch failed; skipping this run: ${message}`);
        return [];
      }
    });

    if (!bars || bars.length === 0) {
      return { status: "no_data", message: "No hourly bars returned" };
    }

    // Step 2: Upsert bars to analytics.price_1h
    const inserted = await step.run("upsert-bars", async () => {
      const client = await pool.connect();
      let count = 0;
      try {
        for (const bar of bars) {
          await client.query(
            `INSERT INTO analytics.price_1h
              (timestamp, open, high, low, close, volume, source, created_at)
             VALUES ($1, $2, $3, $4, $5, $6, 'databento', NOW())
             ON CONFLICT (symbol, timestamp) DO UPDATE SET
               open = EXCLUDED.open,
               high = EXCLUDED.high,
               low = EXCLUDED.low,
               close = EXCLUDED.close,
               volume = EXCLUDED.volume,
               source = EXCLUDED.source
             WHERE analytics.price_1h.source IS NULL
                OR analytics.price_1h.source <> 'databento_live'`,
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

        // Keep latest_price current from hourly bars when live 1m feed is down
        if (bars.length > 0) {
          const newest = bars[bars.length - 1];
          await client.query(
            `UPDATE analytics.latest_price
             SET price = $1, timestamp = $2, updated_at = NOW()
             WHERE id = 1 AND (timestamp IS NULL OR timestamp < $2)`,
            [newest.close, newest.eventTime]
          );
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
