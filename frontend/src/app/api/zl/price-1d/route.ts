import { NextRequest, NextResponse } from "next/server";
import { query } from "@/lib/db";
const INTRADAY_SOURCE_TABLES = [
  { table: "price_5m", interval: "5m" },
  { table: "price_15m", interval: "15m" },
  { table: "price_1h", interval: "1h" },
] as const;

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

function toDateKey(value: string | Date): string {
  const dt = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(dt.getTime())) {
    return String(value).slice(0, 10);
  }
  return dt.toISOString().slice(0, 10);
}

async function getTodayLiveDailyRollup(): Promise<{
  bar: DailyBarRow | null;
  sourceTable: string | null;
  latestTs: string | null;
}> {
  for (const source of INTRADAY_SOURCE_TABLES) {
    try {
      // Table name is interpolated from a fixed allowlist only.
      const sql = `
        WITH today AS (
          SELECT timestamp, open, high, low, close, COALESCE(volume, 0) AS volume
          FROM analytics.${source.table}
          WHERE timestamp >= CURRENT_DATE::timestamptz
            AND timestamp < (CURRENT_DATE + INTERVAL '1 day')::timestamptz
            AND close IS NOT NULL
          ORDER BY timestamp ASC
        )
        SELECT
          CURRENT_DATE AS timestamp,
          (ARRAY_AGG(open ORDER BY timestamp ASC))[1] AS open,
          MAX(high) AS high,
          MIN(low) AS low,
          (ARRAY_AGG(close ORDER BY timestamp DESC))[1] AS close,
          SUM(volume)::bigint AS volume,
          $1::text AS source,
          MAX(timestamp) AS latest_ts,
          COUNT(*)::int AS bar_count
        FROM today
      `;

      const rows = await query<LiveDailyRollupRow>(sql, [
        `intraday_rollup_${source.interval}`,
      ]);
      const row = rows[0];
      if (!row || row.bar_count <= 0 || row.close == null) {
        continue;
      }

      return {
        bar: {
          timestamp: row.timestamp,
          open: row.open ?? row.close,
          high: row.high ?? row.close,
          low: row.low ?? row.close,
          close: row.close,
          volume: row.volume ?? 0,
          source: row.source,
        },
        sourceTable: `analytics.${source.table}`,
        latestTs: row.latest_ts ? new Date(row.latest_ts).toISOString() : null,
      };
    } catch {
      // Continue to lower-frequency fallback table.
    }
  }

  return { bar: null, sourceTable: null, latestTs: null };
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
      `SELECT
        event_date as timestamp,
        open,
        high,
        low,
        close,
        volume,
        COALESCE(source, 'databento') as source
      FROM analytics.price_1d
      WHERE event_date >= CURRENT_DATE - $1::interval
        AND event_date <= CURRENT_DATE
        AND close IS NOT NULL
      ORDER BY event_date ASC`,
      [`${clampedDays} days`],
    );

    const liveRollup = await getTodayLiveDailyRollup();
    let mergedRows = historicalRows;

    if (liveRollup.bar) {
      const liveDayKey = toDateKey(liveRollup.bar.timestamp);
      mergedRows = historicalRows.filter(
        (row) => toDateKey(row.timestamp) !== liveDayKey,
      );
      mergedRows.push(liveRollup.bar);
      mergedRows.sort((a, b) =>
        toDateKey(a.timestamp).localeCompare(toDateKey(b.timestamp)),
      );
    }

    if (mergedRows.length === 0) {
      return NextResponse.json(
        { error: "No daily data available", days: clampedDays },
        { status: 404 },
      );
    }

    return NextResponse.json({
      symbol: "ZL",
      interval: "1d",
      count: mergedRows.length,
      days: clampedDays,
      live_rollup: Boolean(liveRollup.bar),
      live_rollup_source_table: liveRollup.sourceTable,
      live_rollup_latest_intraday_ts: liveRollup.latestTs,
      data: mergedRows,
    });
  } catch (error) {
    console.error("ZL price-1d API error:", error);
    return NextResponse.json(
      { error: "Failed to fetch ZL daily data" },
      { status: 500 },
    );
  }
}
