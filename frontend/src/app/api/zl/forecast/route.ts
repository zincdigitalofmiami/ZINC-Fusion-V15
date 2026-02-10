import { NextRequest, NextResponse } from "next/server";
import dbPool from "@/lib/db";

const pool = dbPool;

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
 * Returns price quantiles (p30/p50/p70) for building forecast fan/cone
 */
export async function GET(_req: NextRequest) {
  try {
    // Query latest forecast from each horizon table
    const result = await pool.query(`
      WITH latest_5d AS (
        SELECT
          5 as horizon_days,
          as_of_date,
          forecast_date,
          price_p30::float,
          price_p50::float,
          price_p70::float,
          current_price::float
        FROM forecasts.production_5d_1d
        ORDER BY as_of_date DESC
        LIMIT 1
      ),
      latest_21d AS (
        SELECT
          21 as horizon_days,
          as_of_date,
          forecast_date,
          price_p30::float,
          price_p50::float,
          price_p70::float,
          current_price::float
        FROM forecasts.production_21d_1d
        ORDER BY as_of_date DESC
        LIMIT 1
      ),
      latest_63d AS (
        SELECT
          63 as horizon_days,
          as_of_date,
          forecast_date,
          price_p30::float,
          price_p50::float,
          price_p70::float,
          current_price::float
        FROM forecasts.production_63d_1d
        ORDER BY as_of_date DESC
        LIMIT 1
      ),
      latest_126d AS (
        SELECT
          126 as horizon_days,
          as_of_date,
          forecast_date,
          price_p30::float,
          price_p50::float,
          price_p70::float,
          current_price::float
        FROM forecasts.production_126d_1d
        ORDER BY as_of_date DESC
        LIMIT 1
      )
      SELECT * FROM latest_5d
      UNION ALL SELECT * FROM latest_21d
      UNION ALL SELECT * FROM latest_63d
      UNION ALL SELECT * FROM latest_126d
      ORDER BY horizon_days ASC
    `);

    if (result.rows.length === 0) {
      return NextResponse.json(
        { error: "No forecast data available", forecasts: [] },
        { status: 404 }
      );
    }

    const forecasts: ForecastPoint[] = result.rows.map(row => ({
      horizon_days: row.horizon_days,
      as_of_date: row.as_of_date,
      forecast_date: row.forecast_date,
      price_p30: row.price_p30,
      price_p50: row.price_p50,
      price_p70: row.price_p70,
      current_price: row.current_price,
    }));

    // Get the current price from the most recent forecast
    const currentPrice = forecasts[0]?.current_price || null;
    const asOfDate = forecasts[0]?.as_of_date || null;

    return NextResponse.json({
      symbol: "ZL",
      as_of_date: asOfDate,
      current_price: currentPrice,
      horizons: [5, 21, 63, 126],
      forecasts,
    });
  } catch (error) {
    console.error("ZL forecast API error:", error);
    return NextResponse.json(
      { error: "Failed to fetch ZL forecast data" },
      { status: 500 }
    );
  }
}
