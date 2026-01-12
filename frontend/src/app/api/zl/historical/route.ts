import { NextRequest, NextResponse } from "next/server";
import { Pool } from "pg";

const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
  ssl: { rejectUnauthorized: false },
});

/**
 * GET /api/zl/historical?days=180
 * Fetch daily OHLCV bars for ZL from raw.market_futures_1d
 * 
 * Query params:
 * - days: number of days back (default 180 = 6 months)
 * 
 * Returns clean daily candlesticks for dashboard chart
 */
export async function GET(req: NextRequest) {
  try {
    const { searchParams } = new URL(req.url);
    const days = parseInt(searchParams.get("days") || "180", 10);

    // Clamp days to reasonable range (30 days to 2 years)
    const clampedDays = Math.max(30, Math.min(days, 730));

    const query = `
      SELECT 
        event_date,
        symbol,
        open,
        high,
        low,
        close,
        volume,
        source,
        knowledge_time
      FROM raw.market_futures_1d
      WHERE symbol = 'ZL'
        AND event_date >= CURRENT_DATE - INTERVAL '${clampedDays} days'
      ORDER BY event_date ASC
    `;

    const result = await pool.query(query);

    if (result.rows.length === 0) {
      return NextResponse.json(
        { error: "No daily ZL data available", days: clampedDays },
        { status: 404 }
      );
    }

    return NextResponse.json({
      symbol: "ZL",
      interval: "1d",
      days: clampedDays,
      count: result.rows.length,
      earliest: result.rows[0]?.event_date,
      latest: result.rows[result.rows.length - 1]?.event_date,
      data: result.rows,
    });
  } catch (error) {
    console.error("Error fetching ZL daily historical data:", error);
    return NextResponse.json(
      { error: "Failed to fetch ZL daily data" },
      { status: 500 }
    );
  }
}
