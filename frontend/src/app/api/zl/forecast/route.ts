import { NextRequest, NextResponse } from "next/server";
import { query } from "@/lib/db";

const CACHE_HEADERS = {
  "Cache-Control": "public, s-maxage=3600, stale-while-revalidate=3600",
};

interface ForecastPoint {
  horizon_days: number;
  as_of_date: string;
  forecast_date: string;
  price_p30: number | null;
  price_p50: number | null;
  price_p70: number | null;
  current_price: number | null;
}

/**
 * GET /api/zl/forecast
 * Fetch the latest Core Model forecasts for ZL across all horizons (5d, 21d, 63d, 126d)
 * Returns price quantiles (p30/p50/p70) for building forecast target zones
 */
export async function GET(_req: NextRequest) {
  try {
    // Query latest forecast per horizon from consolidated production_1d table
    const rows = await query<{
      horizon_days: number;
      as_of_date: string;
      forecast_date: string;
      price_p30: number | null;
      price_p50: number | null;
      price_p70: number | null;
      current_price: number | null;
    }>(`
      SELECT DISTINCT ON (horizon)
        horizon as horizon_days,
        as_of_date,
        forecast_date,
        price_p30::float,
        price_p50::float,
        price_p70::float,
        current_price::float
      FROM forecasts.production_1d
      WHERE horizon IN (5, 21, 63, 126)
      ORDER BY horizon, as_of_date DESC
    `);

    if (rows.length === 0) {
      return NextResponse.json(
        { error: "No forecast data available", forecasts: [] },
        { status: 404 },
      );
    }

    const forecasts: ForecastPoint[] = rows.map((row) => ({
      horizon_days: row.horizon_days,
      as_of_date: row.as_of_date,
      forecast_date: row.forecast_date,
      price_p30: row.price_p30,
      price_p50: row.price_p50,
      price_p70: row.price_p70,
      current_price: row.current_price,
    }));

    // Get the current price from the most recent forecast
    const currentPrice = forecasts[0]?.current_price ?? null;
    const asOfDate = forecasts[0]?.as_of_date ?? null;

    return NextResponse.json({
      symbol: "ZL",
      as_of_date: asOfDate,
      current_price: currentPrice,
      horizons: [5, 21, 63, 126],
      forecasts,
    }, { headers: CACHE_HEADERS });
  } catch (error) {
    console.error("ZL forecast API error:", error);
    return NextResponse.json(
      { error: "Failed to fetch ZL forecast data" },
      { status: 500 },
    );
  }
}
