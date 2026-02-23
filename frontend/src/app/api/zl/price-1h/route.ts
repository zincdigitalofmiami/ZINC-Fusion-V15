import { NextRequest, NextResponse } from "next/server";
import { query } from "@/lib/db";

/**
 * GET /api/zl/price-1h?hours=168
 * Fetch 1-hour OHLCV bars for ZL from analytics.price_1h
 *
 * This is the ZL-specific 1h table, written by Inngest zl-1h and zlLive1m aggregation.
 * NOT the multi-symbol mkt.futures_1h basket.
 *
 * Query params:
 * - hours: number of hours back (default 168 = 7 days)
 */
export async function GET(req: NextRequest) {
  try {
    const { searchParams } = new URL(req.url);
    const hours = parseInt(searchParams.get("hours") || "168", 10);

    // Clamp hours to reasonable range
    const clampedHours = Math.max(24, Math.min(hours, 8760)); // 1 day to 1 year

    const rows = await query<{
      timestamp: string;
      open: number;
      high: number;
      low: number;
      close: number;
      volume: number;
      source: string;
      created_at: string;
    }>(
      `SELECT
        timestamp,
        open,
        high,
        low,
        close,
        volume,
        source,
        created_at
      FROM analytics.price_1h
      WHERE timestamp >= NOW() - $1::interval
        AND close IS NOT NULL
      ORDER BY timestamp ASC`,
      [`${clampedHours} hours`],
    );

    if (rows.length === 0) {
      return NextResponse.json(
        { error: "No 1h data available", hours: clampedHours },
        { status: 404 },
      );
    }

    // PostgreSQL DECIMAL columns come back as strings — coerce to numbers
    const numericRows = rows.map((row) => ({
      ...row,
      open: parseFloat(String(row.open)),
      high: parseFloat(String(row.high)),
      low: parseFloat(String(row.low)),
      close: parseFloat(String(row.close)),
      volume: parseFloat(String(row.volume)),
    }));

    return NextResponse.json(
      {
        symbol: "ZL",
        interval: "1h",
        hours: clampedHours,
        count: numericRows.length,
        earliest: numericRows[0]?.timestamp,
        latest: numericRows[numericRows.length - 1]?.timestamp,
        data: numericRows,
      },
      { headers: { "Cache-Control": "no-store, max-age=0" } },
    );
  } catch (error) {
    console.error("Error fetching ZL 1h data:", error);
    return NextResponse.json(
      { error: "Failed to fetch ZL 1h data" },
      { status: 500 },
    );
  }
}
