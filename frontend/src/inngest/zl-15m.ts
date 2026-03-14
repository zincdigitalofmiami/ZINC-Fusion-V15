import { inngest, DB_CONCURRENCY, RETRIES } from "./client";
import { fetchDatabentoCsv, parseDatabentoOhlcvCsv } from "../lib/databento";
import dbPool from "@/lib/db";

const pool = dbPool;

/**
 * Fetch ZL 15-minute bars from Databento and write to analytics.price_15m
 * Runs every 15 minutes
 */
export const zl15m = inngest.createFunction(
  {
    id: "zl-15m",
    name: "ZL 15m Bars",
    retries: RETRIES.CRON_INGEST,
    concurrency: [DB_CONCURRENCY],
  },
  { cron: "10,25,40,55 * * * *" }, // Every 15 min at :10/:25/:40/:55 (staggered from zl-1h at :05)
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
          `SELECT MAX(timestamp) AS ts FROM analytics.price_15m`
        );
        const lastTs: Date | null = result.rows[0]?.ts ? new Date(result.rows[0].ts) : null;
        const bufferMs = 6 * 60 * 60 * 1000;
        const defaultWindowMs = 7 * 24 * 60 * 60 * 1000;
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

    // Step 1: Fetch 1m bars from Databento and aggregate to 15m
    const bars = await step.run("fetch-databento-1m", async () => {
      const csv = await fetchDatabentoCsv({
        dataset: "GLBX.MDP3",
        schema: "ohlcv-1m",
        symbols: "ZL.n.0",  // OI-ranked for consistency with daily jobs
        stype_in: "continuous",
        start: startStr,
        end: endStr,
        encoding: "csv",
        pretty_ts: "true",
        pretty_px: "true",
      });

      const rawBars = parseDatabentoOhlcvCsv(csv);
      if (!rawBars.length) return [];

      const dayStats = new Map<string, { high: number; low: number; lastClose: number }>();
      for (const bar of rawBars) {
        const dayKey = bar.tsEvent.toISOString().slice(0, 10);
        const existing = dayStats.get(dayKey);
        if (!existing) {
          dayStats.set(dayKey, { high: bar.high, low: bar.low, lastClose: bar.close });
        } else {
          existing.high = Math.max(existing.high, bar.high);
          existing.low = Math.min(existing.low, bar.low);
          existing.lastClose = bar.close;
        }
      }

      const dayKeys = Array.from(dayStats.keys()).sort();
      const prevCloseByDay = new Map<string, number | null>();
      for (let i = 0; i < dayKeys.length; i++) {
        const key = dayKeys[i];
        if (i === 0) {
          prevCloseByDay.set(key, null);
        } else {
          const prevKey = dayKeys[i - 1];
          prevCloseByDay.set(key, dayStats.get(prevKey)?.lastClose ?? null);
        }
      }

      const bucketMs = 15 * 60 * 1000;
      const buckets = new Map<number, {
        timestamp: Date;
        open: number;
        high: number;
        low: number;
        close: number;
        volume: number;
        dayKey: string;
      }>();

      for (const bar of rawBars) {
        const ts = bar.tsEvent.getTime();
        const bucket = Math.floor(ts / bucketMs) * bucketMs;
        const dayKey = bar.tsEvent.toISOString().slice(0, 10);
        const existing = buckets.get(bucket);
        if (!existing) {
          buckets.set(bucket, {
            timestamp: new Date(bucket),
            open: bar.open,
            high: bar.high,
            low: bar.low,
            close: bar.close,
            volume: bar.volume ?? 0,
            dayKey,
          });
        } else {
          existing.high = Math.max(existing.high, bar.high);
          existing.low = Math.min(existing.low, bar.low);
          existing.close = bar.close;
          existing.volume += bar.volume ?? 0;
        }
      }

      const barsData: Array<{
        timestamp: Date;
        open: number;
        high: number;
        low: number;
        close: number;
        volume: number;
        previousClose: number | null;
        dayHigh: number | null;
        dayLow: number | null;
      }> = [];

      const sortedBuckets = Array.from(buckets.values()).sort(
        (a, b) => a.timestamp.getTime() - b.timestamp.getTime()
      );

      for (const bucket of sortedBuckets) {
        const stats = dayStats.get(bucket.dayKey);
        barsData.push({
          timestamp: bucket.timestamp,
          open: bucket.open,
          high: bucket.high,
          low: bucket.low,
          close: bucket.close,
          volume: bucket.volume,
          previousClose: prevCloseByDay.get(bucket.dayKey) ?? null,
          dayHigh: stats?.high ?? null,
          dayLow: stats?.low ?? null,
        });
      }

      return barsData;
    });

    if (!bars || bars.length === 0) {
      return { status: "no_data", message: "No 15m bars returned" };
    }

    // Step 2: Upsert bars to analytics.price_15m
    const inserted = await step.run("upsert-bars", async () => {
      const client = await pool.connect();
      let count = 0;
      try {
        for (const bar of bars) {
          const previousClose = bar.previousClose ?? null;
          const change = previousClose != null ? bar.close - previousClose : null;
          const changePct = previousClose != null ? (change! / previousClose) * 100 : null;

          await client.query(
            `INSERT INTO analytics.price_15m
              (timestamp, open, high, low, close, volume, previous_close, change, change_percent, day_high, day_low, source, created_at)
             VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, 'databento', NOW())
             ON CONFLICT (symbol, timestamp) DO UPDATE SET
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
               source = EXCLUDED.source
             WHERE analytics.price_15m.source IS NULL
                OR analytics.price_15m.source <> 'databento_live'`,
            [
              bar.timestamp,
              bar.open,
              bar.high,
              bar.low,
              bar.close,
              bar.volume,
              previousClose,
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
