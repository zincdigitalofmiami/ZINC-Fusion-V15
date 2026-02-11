import { NextRequest, NextResponse } from "next/server";
import dbPool from "@/lib/db";

const pool = dbPool;

/**
 * GET /api/zl/price-5m?hours=24
 * Fetch 5-minute OHLCV bars for ZL from analytics.price_5m
 *
 * Query params:
 * - hours: number of hours back (default 24 = 1 day)
 */
export async function GET(req: NextRequest) {
  try {
    const { searchParams } = new URL(req.url);
    const hours = parseInt(searchParams.get("hours") || "24", 10);

    // Clamp hours to reasonable range (1 hour to 30 days)
    const clampedHours = Math.max(1, Math.min(hours, 720));

    const query = `
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
      FROM analytics.price_5m
      WHERE timestamp >= NOW() - INTERVAL '${clampedHours} hours'
      ORDER BY timestamp ASC
    `;

    const result = await pool.query(query);

    if (result.rows.length === 0) {
      return NextResponse.json(
        { error: "No 5m data available", hours: clampedHours },
        { status: 404 }
      );
    }

    return NextResponse.json({
      symbol: "ZL",
      interval: "5m",
      hours: clampedHours,
      count: result.rows.length,
      earliest: result.rows[0]?.timestamp,
      latest: result.rows[result.rows.length - 1]?.timestamp,
      data: result.rows,
    });
  } catch (error) {
    console.error("Error fetching ZL 5m data:", error);
    return NextResponse.json(
      { error: "Failed to fetch ZL 5m data" },
      { status: 500 }
    );
  }
}
