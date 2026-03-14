/**
 * ZL 1m write-throttle refresh helper.
 *
 * Uses a per-worker refresh gate to avoid duplicate Databento pulls:
 *   force: true  → always fetch + upsert (used on SSE connect or manual trigger)
 *   force: false → respect 90s per-worker gate
 *
 * Called directly by the scheduled cron — NO step.sendEvent hop — which was
 * the source of duplicate zl.backfill.1m events when the cron retried.
 */
import {
  fetchDatabentoCsvWithAvailableEndRetry,
  parseDatabentoOhlcvCsv,
  type DatabentoOhlcvBar,
} from "./databento";
import dbPool from "./db";

// ---------------------------------------------------------------------------
//  Caps
// ---------------------------------------------------------------------------
export const DEFAULT_LOOKBACK_MINUTES = 3 * 24 * 60; // 3 days
export const DEFAULT_MIN_REFRESH_INTERVAL_MS = 90_000; // 90-second gate
export const MAX_BARS_TO_UPSERT = 500; // 1m bars = ~8h of trading at a clip

// ---------------------------------------------------------------------------
//  Per-worker gate
// ---------------------------------------------------------------------------
let lastRefreshAt = 0;

// ---------------------------------------------------------------------------
//  Public API
// ---------------------------------------------------------------------------
export interface Zl1mRefreshResult {
  skipped: boolean;
  upserted1m: number;
  bars: DatabentoOhlcvBar[];
}

export async function refreshZl1mFromDatabento(opts: {
  force?: boolean;
  lookbackMinutes?: number;
  minRefreshIntervalMs?: number;
}): Promise<Zl1mRefreshResult> {
  const force = opts.force ?? false;
  const lookback = opts.lookbackMinutes ?? DEFAULT_LOOKBACK_MINUTES;
  const gate = opts.minRefreshIntervalMs ?? DEFAULT_MIN_REFRESH_INTERVAL_MS;

  if (!force && Date.now() - lastRefreshAt < gate) {
    return { skipped: true, upserted1m: 0, bars: [] };
  }

  const now = new Date();
  const start = new Date(now.getTime() - lookback * 60_000);
  // Databento GLBX.MDP3 data can lag enough that a simple wall-clock offset
  // still overshoots the published range around UTC day boundaries.
  // Start with a 30-minute offset, then retry against the vendor-reported
  // available_end if Databento returns a 422 range error.
  const end = new Date(now.getTime() - 30 * 60_000);

  const { csv } = await fetchDatabentoCsvWithAvailableEndRetry(
    {
      dataset: "GLBX.MDP3",
      schema: "ohlcv-1m",
      symbols: "ZL.n.0",
      stype_in: "continuous",
      start: start.toISOString(),
      end: end.toISOString(),
      encoding: "csv",
      pretty_ts: "true",
      pretty_px: "true",
    },
    15_000, // 15s timeout — 1m bars over 3 days is a larger payload
  );

  const allBars = parseDatabentoOhlcvCsv(csv);
  const toUpsert = allBars.slice(-MAX_BARS_TO_UPSERT);

  if (toUpsert.length === 0) {
    lastRefreshAt = Date.now();
    return { skipped: false, upserted1m: 0, bars: [] };
  }

  const client = await dbPool.connect();
  let count1m = 0;
  try {
    // Upsert 1m bars
    for (const bar of toUpsert) {
      await client.query(
        `INSERT INTO analytics.price_1m
           (symbol, timestamp, open, high, low, close, volume, source, created_at)
         VALUES ('ZL', $1, $2, $3, $4, $5, $6, 'databento_backfill', NOW())
         ON CONFLICT (symbol, timestamp) DO NOTHING`,
        [bar.tsEvent, bar.open, bar.high, bar.low, bar.close, bar.volume ?? 0],
      );
      count1m++;
    }

    // Keep latest_price current
    const newest = toUpsert[toUpsert.length - 1];
    await client.query(
      `UPDATE analytics.latest_price
       SET price = $1, timestamp = $2, updated_at = NOW()
       WHERE id = 1 AND (timestamp IS NULL OR timestamp < $2)`,
      [newest.close, newest.tsEvent],
    );

    lastRefreshAt = Date.now();
    return {
      skipped: false,
      upserted1m: count1m,
      bars: toUpsert,
    };
  } finally {
    client.release();
  }
}
