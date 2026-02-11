import { NextRequest, NextResponse } from "next/server";
import dbPool from "@/lib/db";

const pool = dbPool;

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
      FROM analytics.price_1m
      WHERE timestamp >= NOW() - INTERVAL '${clampedMinutes} minutes'
      ORDER BY timestamp ASC
    `;

    const result = await pool.query(query);

    if (result.rows.length === 0) {
      return NextResponse.json(
        { error: "No 1m data available", minutes: clampedMinutes },
        { status: 404 }
      );
    }

    return NextResponse.json({
      symbol: "ZL",
      interval: "1m",
      minutes: clampedMinutes,
      count: result.rows.length,
      earliest: result.rows[0]?.timestamp,
      latest: result.rows[result.rows.length - 1]?.timestamp,
      data: result.rows,
    });
  } catch (error) {
    console.error("Error fetching ZL 1m data:", error);
    return NextResponse.json(
      { error: "Failed to fetch ZL 1m data" },
      { status: 500 }
    );
  }
}
