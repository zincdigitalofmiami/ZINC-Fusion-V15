/**
 * ZL 1-Minute Historical Backfill via Databento
 *
 * Backfills analytics.zl_price_1m and analytics.zl_price_5m from Databento historical API.
 * Triggered manually or on schedule to fill gaps.
 *
 * Uses Databento's timeseries.get_range API with ohlcv-1m schema.
 */

import { inngest } from "./client";
import { fetchDatabentoCsv, parseDatabentoOhlcvCsv } from "@/lib/databento";
import dbPool from "@/lib/db";

const pool = dbPool;

// ZL continuous contract (OI-ranked for crush commodities)
const ZL_SYMBOL = "ZL.n.0";
const DATABENTO_DATASET = "GLBX.MDP3";

interface BackfillParams {
  startDate?: string; // ISO date string, e.g. "2026-01-01"
  endDate?: string;   // ISO date string, e.g. "2026-02-01"
  daysBack?: number;  // Alternative: backfill last N days
}

async function getMinTimestamp(): Promise<Date | null> {
  const client = await pool.connect();
  try {
    const result = await client.query(
      `SELECT MIN(timestamp) AS min_ts FROM analytics.zl_price_1m`
    );
    return result.rows[0]?.min_ts ? new Date(result.rows[0].min_ts) : null;
  } finally {
    client.release();
  }
}

async function getMaxTimestamp(): Promise<Date | null> {
  const client = await pool.connect();
  try {
    const result = await client.query(
      `SELECT MAX(timestamp) AS max_ts FROM analytics.zl_price_1m`
    );
    return result.rows[0]?.max_ts ? new Date(result.rows[0].max_ts) : null;
  } finally {
    client.release();
  }
}

async function insert1mBar(
  client: import("pg").PoolClient,
  bar: {
    timestamp: Date;
    open: number;
    high: number;
    low: number;
    close: number;
    volume: number;
  }
): Promise<boolean> {
  try {
    await client.query(
      `INSERT INTO analytics.zl_price_1m
        (timestamp, open, high, low, close, volume, source, created_at)
       VALUES ($1, $2, $3, $4, $5, $6, 'databento_backfill', NOW())
       ON CONFLICT (timestamp) DO NOTHING`,
      [bar.timestamp, bar.open, bar.high, bar.low, bar.close, bar.volume]
    );
    return true;
  } catch {
    return false;
  }
}

async function aggregate5mBars(
  client: import("pg").PoolClient,
  startTime: Date,
  endTime: Date
): Promise<number> {
  // Aggregate all 1m bars into 5m bars for the given range
  const result = await client.query(
    `INSERT INTO analytics.zl_price_5m (timestamp, open, high, low, close, volume, source, created_at)
     SELECT
       date_trunc('hour', timestamp) + INTERVAL '5 min' * FLOOR(EXTRACT(MINUTE FROM timestamp) / 5) AS bar_time,
       (ARRAY_AGG(open ORDER BY timestamp))[1] AS open,
       MAX(high) AS high,
       MIN(low) AS low,
       (ARRAY_AGG(close ORDER BY timestamp DESC))[1] AS close,
       SUM(COALESCE(volume, 0)) AS volume,
       'aggregated_backfill' AS source,
       NOW() AS created_at
     FROM analytics.zl_price_1m
     WHERE timestamp >= $1 AND timestamp < $2
     GROUP BY bar_time
     HAVING COUNT(*) >= 3
     ON CONFLICT (timestamp) DO UPDATE SET
       open = EXCLUDED.open,
       high = EXCLUDED.high,
       low = EXCLUDED.low,
       close = EXCLUDED.close,
       volume = EXCLUDED.volume,
       source = EXCLUDED.source`,
    [startTime, endTime]
  );
  return result.rowCount ?? 0;
}

export const zl1mBackfill = inngest.createFunction(
  {
    id: "zl-1m-backfill",
    name: "ZL 1m/5m Historical Backfill",
    retries: 2,
    concurrency: { limit: 1 }, // Only one backfill at a time
  },
  { event: "zl.backfill.1m" },
  async ({ event, step, logger }) => {
    const params = event.data as BackfillParams;

    // Determine date range
    let startDate: Date;
    let endDate: Date;

    if (params.startDate && params.endDate) {
      startDate = new Date(params.startDate);
      endDate = new Date(params.endDate);
    } else if (params.daysBack) {
      endDate = new Date();
      startDate = new Date();
      startDate.setDate(startDate.getDate() - params.daysBack);
    } else {
      // Default: last 7 days
      endDate = new Date();
      startDate = new Date();
      startDate.setDate(startDate.getDate() - 7);
    }

    logger.info(`Backfilling ZL 1m from ${startDate.toISOString()} to ${endDate.toISOString()}`);

    // Step 1: Check current data range
    const [minTs, maxTs] = await step.run("check-existing-range", async () => {
      const min = await getMinTimestamp();
      const max = await getMaxTimestamp();
      return [min?.toISOString() ?? null, max?.toISOString() ?? null];
    });

    logger.info(`Existing data range: ${minTs ?? "none"} to ${maxTs ?? "none"}`);

    // Step 2: Fetch 1m data from Databento
    const csvData = await step.run("fetch-databento-1m", async () => {
      const startStr = startDate.toISOString().split("T")[0];
      const endStr = endDate.toISOString().split("T")[0];

      return await fetchDatabentoCsv({
        dataset: DATABENTO_DATASET,
        symbols: ZL_SYMBOL,
        schema: "ohlcv-1m",
        start: startStr,
        end: endStr,
      });
    });

    if (!csvData || csvData.length === 0) {
      logger.warn("No data returned from Databento");
      return { status: "no_data", startDate: startDate.toISOString(), endDate: endDate.toISOString() };
    }

    // Step 3: Parse and insert 1m bars
    const insertResult = await step.run("insert-1m-bars", async () => {
      const bars = parseDatabentoOhlcvCsv(csvData);
      const client = await pool.connect();
      let inserted = 0;
      let skipped = 0;

      try {
        for (const bar of bars) {
          const success = await insert1mBar(client, {
            timestamp: bar.tsEvent,
            open: bar.open,
            high: bar.high,
            low: bar.low,
            close: bar.close,
            volume: bar.volume,
          });
          if (success) inserted++;
          else skipped++;
        }
      } finally {
        client.release();
      }

      return { total: bars.length, inserted, skipped };
    });

    logger.info(`Inserted ${insertResult.inserted} 1m bars, skipped ${insertResult.skipped}`);

    // Step 4: Aggregate to 5m bars
    const aggregateResult = await step.run("aggregate-5m-bars", async () => {
      const client = await pool.connect();
      try {
        return await aggregate5mBars(client, startDate, endDate);
      } finally {
        client.release();
      }
    });

    logger.info(`Aggregated ${aggregateResult} 5m bars`);

    return {
      status: "success",
      startDate: startDate.toISOString(),
      endDate: endDate.toISOString(),
      bars1m: insertResult,
      bars5m: aggregateResult,
    };
  }
);

// Scheduled backfill to fill any gaps (runs daily at 6 AM UTC)
export const zl1mScheduledBackfill = inngest.createFunction(
  {
    id: "zl-1m-scheduled-backfill",
    name: "ZL 1m/5m Scheduled Gap Fill",
    retries: 2,
  },
  { cron: "0 6 * * *" }, // Daily at 6 AM UTC
  async ({ step, logger }) => {
    // Backfill last 3 days to catch any gaps
    logger.info("Running scheduled ZL 1m backfill for last 3 days");

    await step.sendEvent("trigger-backfill", {
      name: "zl.backfill.1m",
      data: { daysBack: 3 },
    });

    return { status: "triggered", daysBack: 3 };
  }
);
