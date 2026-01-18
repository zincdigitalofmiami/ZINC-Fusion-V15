import { NextRequest, NextResponse } from "next/server";
import { Pool } from "pg";

const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
  ssl: { rejectUnauthorized: false },
});

/**
 * GET /api/zl/price-1d?days=90
 * Fetch daily OHLCV bars for ZL from mkt.futures_1d
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

    const query = `
      SELECT 
        event_date as timestamp,
        open,
        high,
        low,
        close,
        volume,
        source
      FROM mkt.futures_1d
      WHERE symbol = 'ZL'
        AND event_date >= CURRENT_DATE - INTERVAL '${clampedDays} days'
        AND event_date <= CURRENT_DATE
      ORDER BY event_date ASC
    `;

    const result = await pool.query(query);

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
