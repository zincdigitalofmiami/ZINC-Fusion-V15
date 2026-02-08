import { NextRequest, NextResponse } from "next/server";
import dbPool from "@/lib/db";

const pool = dbPool;

/**
 * GET /api/zl/price-1d?days=90
 * Fetch daily OHLCV bars for ZL from analytics.zl_price_1d
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
    const days = parseInt(searchParams.get("days") || "90", 10);

    // Clamp days to reasonable range
    const clampedDays = Math.max(7, Math.min(days, 3650)); // 1 week to 10 years

    // Query analytics.zl_price_1d — ZL-specific, freshest daily data
    const result = await pool.query(
      `SELECT
        event_date as timestamp,
        open,
        high,
        low,
        close,
        volume,
        COALESCE(source, 'databento') as source
      FROM analytics.zl_price_1d
      WHERE event_date >= CURRENT_DATE - $1::interval
        AND event_date <= CURRENT_DATE
        AND close IS NOT NULL
      ORDER BY event_date ASC`,
      [`${clampedDays} days`]
    );

    if (result.rows.length === 0) {
      return NextResponse.json(
        { error: "No daily data available", days: clampedDays },
        { status: 404 }
      );
    }

    return NextResponse.json({
      symbol: "ZL",
      interval: "1d",
      count: result.rows.length,
      days: clampedDays,
      data: result.rows,
    });
  } catch (error) {
    console.error("ZL price-1d API error:", error);
    return NextResponse.json(
      { error: "Failed to fetch ZL daily data" },
      { status: 500 }
    );
  }
}
