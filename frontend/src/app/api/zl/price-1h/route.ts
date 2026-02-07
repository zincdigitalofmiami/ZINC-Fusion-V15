import { NextRequest, NextResponse } from "next/server";
import dbPool from "@/lib/db";

const pool = dbPool;

/**
 * GET /api/zl/price-1h?hours=168
 * Fetch 1-hour OHLCV bars for ZL from analytics.zl_price_1h
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

    const query = `
      SELECT 
        timestamp,
        open,
        high,
        low,
        close,
        volume,
        source,
        created_at
      FROM analytics.zl_price_1h
      WHERE timestamp >= NOW() - INTERVAL '${clampedHours} hours'
      ORDER BY timestamp ASC
    `;

    const result = await pool.query(query);

    if (result.rows.length === 0) {
      return NextResponse.json(
        { error: "No 1h data available", hours: clampedHours },
        { status: 404 }
      );
    }

    return NextResponse.json({
      symbol: "ZL",
      interval: "1h",
      hours: clampedHours,
      count: result.rows.length,
      earliest: result.rows[0]?.timestamp,
      latest: result.rows[result.rows.length - 1]?.timestamp,
      data: result.rows,
    });
  } catch (error) {
    console.error("Error fetching ZL 1h data:", error);
    return NextResponse.json(
      { error: "Failed to fetch ZL 1h data" },
      { status: 500 }
    );
  }
}
