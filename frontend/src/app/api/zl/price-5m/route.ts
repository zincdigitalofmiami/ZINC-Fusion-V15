import { NextRequest, NextResponse } from "next/server";
import dbPool from "@/lib/db";

const pool = dbPool;
type IntervalLabel = "5m" | "15m" | "1h";

type SourceTable = {
  table: "price_5m" | "price_15m" | "price_1h";
  interval: IntervalLabel;
  barsPerHour: number;
};

const SOURCE_TABLES: SourceTable[] = [
  { table: "price_5m", interval: "5m", barsPerHour: 12 },
  { table: "price_15m", interval: "15m", barsPerHour: 4 },
  { table: "price_1h", interval: "1h", barsPerHour: 1 },
];

type QueryMode = "window" | "latest";

function buildSelectSql(table: SourceTable["table"], whereClause: string) {
  // Table name is interpolated from a fixed allowlist only.
  return `
    SELECT
      timestamp,
      open,
      high,
      low,
      close,
      volume,
      previous_close,
      change,
      change_percent,
      day_high,
      day_low,
      source,
      created_at
    FROM analytics.${table}
    ${whereClause}
  `;
}

async function queryBars(
  source: SourceTable,
  hours: number,
): Promise<{ rows: unknown[]; mode: QueryMode }> {
  const windowSql = buildSelectSql(
    source.table,
    "WHERE timestamp >= NOW() - ($1::int * INTERVAL '1 hour') ORDER BY timestamp ASC",
  );
  const windowResult = await pool.query(windowSql, [hours]);
  if (windowResult.rows.length > 0) {
    return { rows: windowResult.rows, mode: "window" };
  }

  // Market-close safety: return latest bars if requested window is empty.
  const fallbackLimit = Math.max(
    24,
    Math.min(5000, Math.ceil(hours * source.barsPerHour)),
  );
  const latestSql = buildSelectSql(
    source.table,
    "ORDER BY timestamp DESC LIMIT $1",
  );
  const latestResult = await pool.query(latestSql, [fallbackLimit]);
  return { rows: latestResult.rows.reverse(), mode: "latest" };
}

/**
 * GET /api/zl/price-5m?hours=24
 * Fetch ZL intraday bars, preferring 5m and gracefully degrading to 15m/1h.
 *
 * Query params:
 * - hours: number of hours back (default 24 = 1 day)
 */
export async function GET(req: NextRequest) {
  try {
    const { searchParams } = new URL(req.url);
    const requestedHours = parseInt(searchParams.get("hours") || "24", 10);

    // Clamp hours to reasonable range (1 hour to 30 days)
    const clampedHours = Number.isFinite(requestedHours)
      ? Math.max(1, Math.min(requestedHours, 720))
      : 24;

    const sourceErrors: string[] = [];

    for (const source of SOURCE_TABLES) {
      try {
        const { rows, mode } = await queryBars(source, clampedHours);
        if (rows.length === 0) {
          continue;
        }

        return NextResponse.json({
          symbol: "ZL",
          interval: source.interval,
          requested_interval: "5m",
          source_table: `analytics.${source.table}`,
          window_mode: mode,
          fallback_used: source.table !== "price_5m" || mode === "latest",
          hours: clampedHours,
          count: rows.length,
          earliest: (rows[0] as { timestamp?: string })?.timestamp,
          latest: (rows[rows.length - 1] as { timestamp?: string })?.timestamp,
          data: rows,
        });
      } catch (error) {
        // Keep trying lower-frequency fallback tables.
        const message =
          error instanceof Error ? error.message : "unknown query error";
        sourceErrors.push(`${source.table}: ${message}`);
      }
    }

    console.error("No ZL intraday data available", {
      requestedInterval: "5m",
      checkedTables: SOURCE_TABLES.map((s) => `analytics.${s.table}`),
      sourceErrors,
    });

    return NextResponse.json(
      {
        error: "No intraday data available",
        requested_interval: "5m",
        checked_tables: SOURCE_TABLES.map((s) => `analytics.${s.table}`),
      },
      { status: 404 },
    );
  } catch (error) {
    console.error("Error fetching ZL 5m data:", error);
    return NextResponse.json(
      { error: "Failed to fetch ZL 5m data" },
      { status: 500 },
    );
  }
}
