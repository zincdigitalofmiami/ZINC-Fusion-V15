/**
 * ZL 1-Minute Historical Backfill via Databento
 *
 * Two functions:
 *
 * zl1mBackfill      — event-driven (zl.backfill.1m), for manual or one-off triggers.
 *                     Accepts { startDate, endDate, daysBack } in event.data.
 *
 * zl1mScheduledBackfill — cron (daily 06:00 UTC), calls the refresh helper directly.
 *                         NO step.sendEvent hop — that was the source of duplicate
 *                         zl.backfill.1m events on cron retries (RR pattern fix).
 */

import { inngest, DB_CONCURRENCY } from "./client";
import { fetchDatabentoCsv, parseDatabentoOhlcvCsv } from "@/lib/databento";
import { refreshZl1mFromDatabento } from "@/lib/zl1m-refresh";
import dbPool from "@/lib/db";

const pool = dbPool;

const ZL_SYMBOL = "ZL.n.0";
const DATABENTO_DATASET = "GLBX.MDP3";

interface BackfillParams {
  startDate?: string;
  endDate?: string;
  daysBack?: number;
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
      `INSERT INTO analytics.price_1m
        (timestamp, open, high, low, close, volume, source, created_at)
       VALUES ($1, $2, $3, $4, $5, $6, 'databento_backfill', NOW())
       ON CONFLICT (symbol, timestamp) DO NOTHING`,
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
  const result = await client.query(
    `INSERT INTO analytics.price_5m (timestamp, open, high, low, close, volume, source, created_at)
     SELECT
       date_trunc('hour', timestamp) + INTERVAL '5 min' * FLOOR(EXTRACT(MINUTE FROM timestamp) / 5) AS bar_time,
       (ARRAY_AGG(open ORDER BY timestamp))[1] AS open,
       MAX(high) AS high,
       MIN(low) AS low,
       (ARRAY_AGG(close ORDER BY timestamp DESC))[1] AS close,
       SUM(COALESCE(volume, 0)) AS volume,
       'aggregated_backfill' AS source,
       NOW() AS created_at
     FROM analytics.price_1m
     WHERE timestamp >= $1 AND timestamp < $2
     GROUP BY bar_time
     HAVING COUNT(*) >= 3
     ON CONFLICT (symbol, timestamp) DO UPDATE SET
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

// ---------------------------------------------------------------------------
//  Manual / event-driven backfill (kept for on-demand use)
// ---------------------------------------------------------------------------
export const zl1mBackfill = inngest.createFunction(
  {
    id: "zl-1m-backfill",
    name: "ZL 1m/5m Historical Backfill",
    retries: 1,
    concurrency: [DB_CONCURRENCY, { limit: 1, scope: "fn" }], // one at a time globally
  },
  { event: "zl.backfill.1m" },
  async ({ event, step, logger }) => {
    const params = event.data as BackfillParams;

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
      endDate = new Date();
      startDate = new Date();
      startDate.setDate(startDate.getDate() - 7);
    }

    logger.info(`Backfilling ZL 1m from ${startDate.toISOString()} to ${endDate.toISOString()}`);

    const csvData = await step.run("fetch-databento-1m", async () => {
      const startStr = startDate.toISOString().split("T")[0];
      const endStr = endDate.toISOString().split("T")[0];
      return await fetchDatabentoCsv(
        {
          dataset: DATABENTO_DATASET,
          symbols: ZL_SYMBOL,
          schema: "ohlcv-1m",
          stype_in: "continuous",
          start: startStr,
          end: endStr,
          encoding: "csv",
          pretty_ts: "true",
          pretty_px: "true",
        },
        15_000
      );
    });

    if (!csvData || csvData.length === 0) {
      logger.warn("No data returned from Databento");
      return { status: "no_data" };
    }

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

    const aggregateResult = await step.run("aggregate-5m-bars", async () => {
      const client = await pool.connect();
      try {
        return await aggregate5mBars(client, startDate, endDate);
      } finally {
        client.release();
      }
    });

    logger.info(`Inserted ${insertResult.inserted} 1m bars, aggregated ${aggregateResult} 5m bars`);

    return {
      status: "success",
      bars1m: insertResult,
      bars5m: aggregateResult,
    };
  }
);

// ---------------------------------------------------------------------------
//  Scheduled gap-fill — calls refresh helper DIRECTLY (no event hop)
// ---------------------------------------------------------------------------
export const zl1mScheduledBackfill = inngest.createFunction(
  {
    id: "zl-1m-scheduled-backfill",
    name: "ZL 1m/5m Scheduled Gap Fill",
    retries: 0, // no retries — helper has its own gate; duplicate runs = wasted Databento calls
    concurrency: [DB_CONCURRENCY],
  },
  { cron: "0 6 * * *" },
  async ({ logger }) => {
    logger.info("Running scheduled ZL 1m gap fill via refresh helper (3-day lookback)");

    const result = await refreshZl1mFromDatabento({
      force: true,
      lookbackMinutes: 3 * 24 * 60,
    });

    if (result.skipped) {
      logger.info("Refresh gate blocked — already ran recently");
      return { status: "skipped" };
    }

    logger.info(`Gap fill complete: ${result.upserted1m} 1m bars, ${result.upserted5m} 5m bars`);
    return {
      status: "success",
      upserted1m: result.upserted1m,
      upserted5m: result.upserted5m,
    };
  }
);
