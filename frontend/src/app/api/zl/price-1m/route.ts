import { NextRequest, NextResponse } from "next/server";
import { query } from "@/lib/db";

/**
 * GET /api/zl/price-1m?minutes=60
 * Fetch 1-minute OHLCV bars for ZL from analytics.price_1m
 *
 * Query params:
 * - minutes: number of minutes back (default 60 = 1 hour)
 */
export async function GET(req: NextRequest) {
  try {
    const { searchParams } = new URL(req.url);
    const minutes = parseInt(searchParams.get("minutes") || "60", 10);

    // Clamp minutes to reasonable range (1 hour to 7 days)
    const clampedMinutes = Math.max(60, Math.min(minutes, 10080));

    const rows = await query<{
      timestamp: string;
      open: number;
      high: number;
      low: number;
      close: number;
      volume: number;
      previous_close: number | null;
      change: number | null;
      change_percent: number | null;
      day_high: number | null;
      day_low: number | null;
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
        previous_close,
        change,
        change_percent,
        day_high,
        day_low,
        source,
        created_at
      FROM analytics.price_1m
      WHERE timestamp >= NOW() - $1::interval
      ORDER BY timestamp ASC`,
      [`${clampedMinutes} minutes`],
    );

    if (rows.length === 0) {
      return NextResponse.json(
        { error: "No 1m data available", minutes: clampedMinutes },
        { status: 404 }
      );
    }

    return NextResponse.json(
      {
        symbol: "ZL",
        interval: "1m",
        minutes: clampedMinutes,
        count: rows.length,
        earliest: rows[0]?.timestamp,
        latest: rows[rows.length - 1]?.timestamp,
        data: rows,
      },
      { headers: { "Cache-Control": "no-store, max-age=0" } },
    );
  } catch (error) {
    console.error("Error fetching ZL 1m data:", error);
    return NextResponse.json(
      { error: "Failed to fetch ZL 1m data" },
      { status: 500 }
    );
  }
}
