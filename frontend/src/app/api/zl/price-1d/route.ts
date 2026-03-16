import { NextRequest, NextResponse } from "next/server";
import { query } from "@/lib/db";
import { zlSessionContextCte } from "@/lib/zl-session";

const CACHE_HEADERS = {
  "Cache-Control": "public, s-maxage=60, stale-while-revalidate=300",
};
const LIVE_THRESHOLD_SECONDS = 5 * 60;

type DailyBarRow = {
  timestamp: string | Date;
  open: number | string;
  high: number | string;
  low: number | string;
  close: number | string;
  volume: number | string;
  source: string;
};

type LiveDailyRollupRow = {
  timestamp: Date | string;
  open: number | string | null;
  high: number | string | null;
  low: number | string | null;
  close: number | string | null;
  volume: number | string | null;
  source: string;
  latest_ts: Date | string | null;
  bar_count: number;
};

type RollupAttempt = {
  status: "ok" | "empty" | "error";
  bar: DailyBarRow | null;
  sourceTable: string | null;
  latestTs: string | null;
  error: string | null;
};

type LiveRollupState = "live" | "stale" | "fallback" | "none";

function toDateKey(value: string | Date): string {
  const dt = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(dt.getTime())) {
    return String(value).slice(0, 10);
  }
  return dt.toISOString().slice(0, 10);
}

/**
 * Fallback: synthesize today's bar from analytics.latest_price when the 1m
 * feed is empty (live feed down, market pre-open, etc.). Prevents the chart
 * from showing yesterday's close as the rightmost bar when we have a more
 * recent price in the singleton latest_price row.
 */
async function getSessionFromLatestPrice(): Promise<{
  status: "ok" | "empty" | "error";
  bar: DailyBarRow | null;
  latestTs: string | null;
  error: string | null;
}> {
  try {
    const rows = await query<{
      trade_date: string;
      price: number;
      timestamp: string | null;
      updated_at: string;
    }>(
      `WITH ${zlSessionContextCte()}
       SELECT
         sb.trade_date::text AS trade_date,
         lp.price,
         lp.timestamp::text,
         lp.updated_at::text
       FROM analytics.latest_price lp
       CROSS JOIN session_bounds sb
       WHERE lp.id = 1
         AND lp.price IS NOT NULL
         AND COALESCE(lp.timestamp, lp.updated_at) >= sb.session_start_utc
         AND COALESCE(lp.timestamp, lp.updated_at) <= sb.session_cutoff_utc`,
    );
    if (!rows.length || !rows[0].price) {
      return { status: "empty", bar: null, latestTs: null, error: null };
    }
    const r = rows[0];
    const p = parseFloat(String(r.price));
    return {
      bar: {
        timestamp: r.trade_date,
        open: p, high: p, low: p, close: p, volume: 0,
        source: "latest_price_fallback",
      },
      latestTs: r.timestamp ?? r.updated_at ?? null,
      status: "ok",
      error: null,
    };
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    console.error("ZL price-1d latest_price fallback failed:", message);
    return {
      status: "error",
      bar: null,
      latestTs: null,
      error: message,
    };
  }
}

async function getSessionLiveDailyRollup(): Promise<RollupAttempt> {
  try {
    const rows = await query<LiveDailyRollupRow>(
      `WITH ${zlSessionContextCte()}
        , session_bars AS (
          SELECT timestamp, open, high, low, close, COALESCE(volume, 0) AS volume
          FROM analytics.price_1m
          CROSS JOIN session_bounds sb
          WHERE timestamp >= sb.session_start_utc
            AND timestamp <= sb.session_cutoff_utc
            AND close IS NOT NULL
          ORDER BY timestamp ASC
        )
        SELECT
          sb.trade_date AS timestamp,
          (ARRAY_AGG(session_bars.open ORDER BY session_bars.timestamp ASC))[1] AS open,
          MAX(session_bars.high) AS high,
          MIN(session_bars.low) AS low,
          (ARRAY_AGG(session_bars.close ORDER BY session_bars.timestamp DESC))[1] AS close,
          SUM(session_bars.volume)::bigint AS volume,
          'intraday_rollup_1m'::text AS source,
          MAX(session_bars.timestamp) AS latest_ts,
          COUNT(session_bars.timestamp)::int AS bar_count
        FROM session_bars
        CROSS JOIN session_bounds sb
        GROUP BY sb.trade_date
      `,
    );
    const row = rows[0];
    if (!row || row.bar_count <= 0 || row.close == null) {
      return {
        status: "empty",
        bar: null,
        sourceTable: null,
        latestTs: null,
        error: null,
      };
    }

    return {
      status: "ok",
      bar: {
        timestamp: row.timestamp,
        open: row.open ?? row.close,
        high: row.high ?? row.close,
        low: row.low ?? row.close,
        close: row.close,
        volume: row.volume ?? 0,
        source: row.source,
      },
      sourceTable: "analytics.price_1m",
      latestTs: row.latest_ts ? new Date(row.latest_ts).toISOString() : null,
      error: null,
    };
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    console.error("ZL price-1d intraday rollup failed:", message);
    return {
      status: "error",
      bar: null,
      sourceTable: null,
      latestTs: null,
      error: message,
    };
  }
}

function computeAgeSeconds(value: string | null): number | null {
  if (!value) return null;
  const ts = new Date(value);
  if (Number.isNaN(ts.getTime())) return null;
  return Math.max(0, Math.round((Date.now() - ts.getTime()) / 1000));
}

function computeLiveRollupState(
  sourceTable: string | null,
  latestTs: string | null,
): {
  state: LiveRollupState;
  degraded: boolean;
  ageSeconds: number | null;
} {
  if (!sourceTable) {
    return { state: "none", degraded: true, ageSeconds: null };
  }

  const ageSeconds = computeAgeSeconds(latestTs);
  if (sourceTable !== "analytics.price_1m") {
    return { state: "fallback", degraded: true, ageSeconds };
  }

  if (ageSeconds == null || ageSeconds > LIVE_THRESHOLD_SECONDS) {
    return { state: "stale", degraded: true, ageSeconds };
  }

  return { state: "live", degraded: false, ageSeconds };
}

/**
 * GET /api/zl/price-1d?days=90
 * Fetch daily OHLCV bars for ZL from analytics.price_1d
 *
 * This is the ZL-specific daily table, updated by Inngest zl-live-1d and zl-daily.
 * NOT the 100+ symbol mkt.futures_1d basket.
 *
 * Query params:
 * - days: number of days back (default 90)
 */
export async function GET(req: NextRequest) {
  try {
    const { searchParams } = new URL(req.url);
    const requestedDays = parseInt(searchParams.get("days") || "90", 10);

    // Clamp days to reasonable range
    const clampedDays = Number.isFinite(requestedDays)
      ? Math.max(7, Math.min(requestedDays, 3650))
      : 90;

    // Query analytics.price_1d — ZL-specific, freshest daily data
    const historicalRows = await query<DailyBarRow>(
      `WITH ${zlSessionContextCte()}
       SELECT
        event_date as timestamp,
        open,
        high,
        low,
        close,
        volume,
        COALESCE(source, 'databento') as source
      FROM analytics.price_1d
      CROSS JOIN session_bounds sb
      WHERE event_date >= sb.trade_date - $1::interval
        AND event_date <= sb.trade_date
        AND close IS NOT NULL
      ORDER BY event_date ASC`,
      [`${clampedDays} days`],
    );

    // Try current/last futures-session 1m rollup first, then fall back to latest_price.
    const intradayRollup = await getSessionLiveDailyRollup();
    let activeRollupBar: DailyBarRow | null = null;
    let activeSourceTable: string | null = null;
    let activeLatestTs: string | null = null;
    let liveRollupError: string | null = intradayRollup.error;

    if (intradayRollup.status === "ok") {
      activeRollupBar = intradayRollup.bar;
      activeSourceTable = intradayRollup.sourceTable;
      activeLatestTs = intradayRollup.latestTs;
    } else {
      const lpFallback = await getSessionFromLatestPrice();
      if (lpFallback.status === "ok" && lpFallback.bar) {
        activeRollupBar   = lpFallback.bar;
        activeSourceTable = "analytics.latest_price";
        activeLatestTs    = lpFallback.latestTs;
      }
      if (!liveRollupError && lpFallback.error) {
        liveRollupError = lpFallback.error;
      }
    }

    let mergedRows = historicalRows;

    if (activeRollupBar) {
      const liveDayKey = toDateKey(activeRollupBar.timestamp);
      mergedRows = historicalRows.filter(
        (row) => toDateKey(row.timestamp) !== liveDayKey,
      );
      mergedRows.push(activeRollupBar);
      mergedRows.sort((a, b) =>
        toDateKey(a.timestamp).localeCompare(toDateKey(b.timestamp)),
      );
    }

    if (mergedRows.length === 0) {
      return NextResponse.json(
        { error: "No daily data available", days: clampedDays },
        { status: 404, headers: { "Cache-Control": "no-store, max-age=0" } },
      );
    }

    // PostgreSQL DECIMAL columns come back as strings — coerce to numbers
    const numericRows = mergedRows.map((row) => ({
      ...row,
      timestamp: toDateKey(row.timestamp),
      open: parseFloat(String(row.open)),
      high: parseFloat(String(row.high)),
      low: parseFloat(String(row.low)),
      close: parseFloat(String(row.close)),
      volume: parseFloat(String(row.volume)),
    }));
    const rollupState = computeLiveRollupState(activeSourceTable, activeLatestTs);

    return NextResponse.json(
      {
        symbol: "ZL",
        interval: "1d",
        count: numericRows.length,
        days: clampedDays,
        live_rollup: Boolean(activeRollupBar),
        live_rollup_source_table: activeSourceTable,
        live_rollup_latest_intraday_ts: activeLatestTs,
        live_rollup_state: rollupState.state,
        live_rollup_degraded: rollupState.degraded,
        live_rollup_age_seconds: rollupState.ageSeconds,
        live_rollup_error: liveRollupError,
        data: numericRows,
      },
      { headers: CACHE_HEADERS },
    );
  } catch (error) {
    console.error("ZL price-1d API error:", error);
    return NextResponse.json(
      { error: "Failed to fetch ZL daily data" },
      { status: 500 },
    );
  }
}
