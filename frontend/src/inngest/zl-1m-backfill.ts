/**
 * ZL 1-Minute Historical Backfill via Databento
 *
 * Three functions:
 *
 * zl1mBackfill      — event-driven (zl.backfill.1m), for manual or one-off triggers.
 *                     Accepts { startDate, endDate, daysBack } in event.data.
 *
 * zl1mScheduledBackfill — cron (daily 06:00 UTC), calls the refresh helper directly.
 *                         NO step.sendEvent hop — that was the source of duplicate
 *                         zl.backfill.1m events on cron retries (RR pattern fix).
 *
 * zl1mIntradayRefresh — cron (every 3 minutes during futures session window),
 *                       managed in-repo path that keeps chart-serving 1m/latest
 *                       tables fresh in production.
 */

import { inngest, DB_CONCURRENCY, RETRIES } from "./client";
import {
  fetchDatabentoCsvWithAvailableEndRetry,
  parseDatabentoOhlcvCsv,
} from "@/lib/databento";
import { refreshZl1mFromDatabento } from "@/lib/zl1m-refresh";
import dbPool from "@/lib/db";

const pool = dbPool;

const ZL_SYMBOL = "ZL.n.0";
const DATABENTO_DATASET = "GLBX.MDP3";
const ZL_SESSION_OPEN_MINUTES = 19 * 60;
const ZL_SESSION_CLOSE_MINUTES = 13 * 60 + 20;
const STALE_THRESHOLD_SECONDS = 5 * 60;
export const ZL_1M_INTRADAY_REFRESH_CRON = "TZ=America/Chicago */3 * * * *";
export const ZL_1M_SCHEDULED_GAP_FILL_LOOKBACK_MINUTES = 3 * 24 * 60;
export const ZL_1M_SCHEDULED_GAP_FILL_MAX_BARS = 3 * 24 * 60;

interface BackfillParams {
  startDate?: string;
  endDate?: string;
  daysBack?: number;
}

export type Zl1mIntradayRefreshStatus =
  | "success"
  | "stale"
  | "skipped_outside_session"
  | "skipped_gate";

export function isWithinZlManagedSessionWindow(now = new Date()): boolean {
  const local = new Date(
    now.toLocaleString("en-US", { timeZone: "America/Chicago" }),
  );
  const day = local.getDay(); // 0=Sun ... 6=Sat
  const minutes = local.getHours() * 60 + local.getMinutes();

  if (day === 6) return false; // Saturday
  if (day === 0) return minutes >= ZL_SESSION_OPEN_MINUTES; // Sunday opens 19:00 CT
  if (day >= 1 && day <= 4) {
    // Monday-Thursday: open overnight until 13:20, then re-open at 19:00.
    return minutes <= ZL_SESSION_CLOSE_MINUTES || minutes >= ZL_SESSION_OPEN_MINUTES;
  }
  // Friday: open only through 13:20 CT.
  return minutes <= ZL_SESSION_CLOSE_MINUTES;
}

export async function runZl1mIntradayRefresh(
  refreshFn: typeof refreshZl1mFromDatabento = refreshZl1mFromDatabento,
  now = new Date(),
): Promise<{
  status: Zl1mIntradayRefreshStatus;
  upserted1m: number;
  latestBar: string | null;
  age_seconds: number | null;
}> {
  if (!isWithinZlManagedSessionWindow(now)) {
    return {
      status: "skipped_outside_session",
      upserted1m: 0,
      latestBar: null,
      age_seconds: null,
    };
  }

  const result = await refreshFn({
    force: true,
    lookbackMinutes: 12 * 60,
    endLagMinutes: 2,
    maxBarsToUpsert: 720,
  });

  if (result.skipped) {
    return {
      status: "skipped_gate",
      upserted1m: 0,
      latestBar: null,
      age_seconds: null,
    };
  }

  const latestBarDate = result.bars[result.bars.length - 1]?.tsEvent ?? null;
  const latestBarIso = latestBarDate ? latestBarDate.toISOString() : null;
  const ageSeconds = latestBarDate
    ? Math.max(0, Math.round((now.getTime() - latestBarDate.getTime()) / 1000))
    : null;
  const isStale = ageSeconds != null && ageSeconds > STALE_THRESHOLD_SECONDS;

  return {
    status: isStale ? "stale" : "success",
    upserted1m: result.upserted1m,
    latestBar: latestBarIso,
    age_seconds: ageSeconds,
  };
}

export async function runZl1mScheduledBackfill(
  refreshFn: typeof refreshZl1mFromDatabento = refreshZl1mFromDatabento,
): Promise<{
  status: "success" | "skipped";
  upserted1m?: number;
}> {
  const result = await refreshFn({
    force: true,
    lookbackMinutes: ZL_1M_SCHEDULED_GAP_FILL_LOOKBACK_MINUTES,
    maxBarsToUpsert: ZL_1M_SCHEDULED_GAP_FILL_MAX_BARS,
  });

  if (result.skipped) {
    return { status: "skipped" };
  }

  return {
    status: "success",
    upserted1m: result.upserted1m,
  };
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

// ---------------------------------------------------------------------------
//  Manual / event-driven backfill (kept for on-demand use)
// ---------------------------------------------------------------------------
export const zl1mBackfill = inngest.createFunction(
  {
    id: "zl-1m-backfill",
    name: "ZL 1m Historical Backfill",
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

    const startStr = startDate.toISOString().split("T")[0];
    const endStr = endDate.toISOString().split("T")[0];

    const fetchResult = await step.run("fetch-databento-1m", async () => {
      return await fetchDatabentoCsvWithAvailableEndRetry(
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

    if (fetchResult.effectiveEnd && fetchResult.effectiveEnd !== endStr) {
      logger.info(`Databento clamped manual ZL 1m backfill end to ${fetchResult.effectiveEnd}`);
    }

    const csvData = fetchResult.csv;

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

    logger.info(`Inserted ${insertResult.inserted} 1m bars`);

    return {
      status: "success",
      bars1m: insertResult,
    };
  }
);

// ---------------------------------------------------------------------------
//  Scheduled gap-fill — calls refresh helper DIRECTLY (no event hop)
// ---------------------------------------------------------------------------
export const zl1mScheduledBackfill = inngest.createFunction(
  {
    id: "zl-1m-scheduled-backfill",
    name: "ZL 1m Scheduled Gap Fill",
    retries: 0, // no retries — helper has its own gate; duplicate runs = wasted Databento calls
    concurrency: [DB_CONCURRENCY],
  },
  { cron: "0 6 * * *" },
  async ({ logger }) => {
    logger.info("Running scheduled ZL 1m gap fill via refresh helper (3-day lookback)");

    const result = await runZl1mScheduledBackfill();
    if (result.status === "skipped") {
      logger.info("Refresh gate blocked — already ran recently");
      return result;
    }

    logger.info(`Gap fill complete: ${result.upserted1m} 1m bars`);
    return result;
  }
);

// ---------------------------------------------------------------------------
//  Managed intraday refresher (primary freshness path)
// ---------------------------------------------------------------------------
export const zl1mIntradayRefresh = inngest.createFunction(
  {
    id: "zl-1m-intraday-refresh",
    name: "ZL 1m Managed Intraday Refresh",
    retries: RETRIES.CRON_INGEST,
    concurrency: [DB_CONCURRENCY],
  },
  { cron: ZL_1M_INTRADAY_REFRESH_CRON },
  async ({ logger }) => {
    const result = await runZl1mIntradayRefresh();

    if (result.status === "success") {
      logger.info(
        {
          upserted1m: result.upserted1m,
          latestBar: result.latestBar,
          age_seconds: result.age_seconds,
        },
        "Managed intraday refresh completed",
      );
    } else if (result.status === "stale") {
      logger.warn(
        {
          upserted1m: result.upserted1m,
          latestBar: result.latestBar,
          age_seconds: result.age_seconds,
        },
        "Managed intraday refresh completed but latest 1m bar is stale",
      );
    } else {
      logger.info({ status: result.status }, "Managed intraday refresh skipped");
    }

    return result;
  },
);
