/**
 * ZL 1h write-throttle refresh helper.
 *
 * Fetches ZL 1-hour bars from Databento and upserts to analytics.price_1h,
 * gated by a per-worker minimum interval so even frequent callers (SSE poll
 * every 15 s) won't hammer writes more often than once per 90 s.
 *
 * Modeled after the MES 15m refresh pattern:
 *   force: true  → always fetch + upsert (used on SSE connect)
 *   force: false → respect the gate (used on subsequent polls)
 */
import {
  fetchDatabentoCsv,
  parseDatabentoOhlcvCsv,
  type DatabentoOhlcvBar,
} from "./databento";
import dbPool from "./db";

// ---------------------------------------------------------------------------
//  Tunable caps (match MES pattern)
// ---------------------------------------------------------------------------
export const DEFAULT_LOOKBACK_MINUTES = 18 * 60; // 18 hours
export const DEFAULT_MIN_REFRESH_INTERVAL_MS = 90_000; // 90-second gate
export const MAX_CANDLES_TO_UPSERT = 160;

// ---------------------------------------------------------------------------
//  Per-worker gate (each Vercel Lambda gets its own cold-start value)
// ---------------------------------------------------------------------------
let lastRefreshAt = 0;

// ---------------------------------------------------------------------------
//  Public API
// ---------------------------------------------------------------------------
export interface RefreshResult {
  skipped: boolean;
  upserted: number;
  bars: DatabentoOhlcvBar[];
}

export async function refreshZl1hFromDatabento(opts: {
  force?: boolean;
  lookbackMinutes?: number;
  minRefreshIntervalMs?: number;
}): Promise<RefreshResult> {
  const force = opts.force ?? false;
  const lookback = opts.lookbackMinutes ?? DEFAULT_LOOKBACK_MINUTES;
  const gate = opts.minRefreshIntervalMs ?? DEFAULT_MIN_REFRESH_INTERVAL_MS;

  // Gate check
  if (!force && Date.now() - lastRefreshAt < gate) {
    return { skipped: true, upserted: 0, bars: [] };
  }

  // Compute time window
  const now = new Date();
  const start = new Date(now.getTime() - lookback * 60_000);

  const csv = await fetchDatabentoCsv(
    {
      dataset: "GLBX.MDP3",
      schema: "ohlcv-1h",
      symbols: "ZL.n.0",
      stype_in: "continuous",
      start: start.toISOString(),
      end: now.toISOString(),
      encoding: "csv",
      pretty_ts: "true",
      pretty_px: "true",
    },
    10_000, // 10 s timeout (longer than default 5 s for SSE context)
  );

  const allBars = parseDatabentoOhlcvCsv(csv);
  const toUpsert = allBars.slice(-MAX_CANDLES_TO_UPSERT);

  if (toUpsert.length === 0) {
    lastRefreshAt = Date.now();
    return { skipped: false, upserted: 0, bars: [] };
  }

  // Upsert to analytics.price_1h — same ON CONFLICT as zl-1h.ts
  const client = await dbPool.connect();
  let count = 0;
  try {
    for (const bar of toUpsert) {
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
        [bar.tsEvent, bar.open, bar.high, bar.low, bar.close, bar.volume ?? 0],
      );
      count++;
    }

    // Keep latest_price current as fallback when live 1m feed is down
    const newest = toUpsert[toUpsert.length - 1];
    await client.query(
      `UPDATE analytics.latest_price
       SET price = $1, timestamp = $2, updated_at = NOW()
       WHERE id = 1 AND (timestamp IS NULL OR timestamp < $2)`,
      [newest.close, newest.tsEvent],
    );
  } finally {
    client.release();
  }

  lastRefreshAt = Date.now();
  return { skipped: false, upserted: count, bars: toUpsert };
}
