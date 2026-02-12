import { NextResponse } from "next/server";
import dbPool from "@/lib/db";

const pool = dbPool;

/**
 * GET /api/zl/forecast-targets
 *
 * Returns the latest Core Model forecasts shaped for the
 * ForecastTargetsPrimitive chart overlay.
 *
 * Data sources (all real — no placeholders):
 *   - forecasts.production_1d        → price_p30/p50/p70 per horizon (OOF targets)
 *   - training.model_runs_event      → MAE per horizon (model accuracy)
 */
export async function GET() {
  try {
    // 1) Latest production forecast per horizon
    const forecastResult = await pool.query(`
      SELECT DISTINCT ON (horizon)
        horizon                  AS horizon_days,
        as_of_date,
        forecast_date,
        price_p30::float,
        price_p50::float,
        price_p70::float,
        current_price::float,
        model_version
      FROM forecasts.production_1d
      WHERE horizon IN (5, 21, 63, 126)
        AND forecast_date >= CURRENT_DATE
        AND price_p30 IS NOT NULL
        AND price_p50 IS NOT NULL
        AND price_p70 IS NOT NULL
      ORDER BY horizon, as_of_date DESC
    `);

    if (forecastResult.rows.length === 0) {
      return NextResponse.json({ symbol: "ZL", targets: [] });
    }

    // 2) Latest MAE per horizon from model_runs (best-effort — non-fatal)
    const maeByHorizon: Record<number, number> = {};
    try {
      const maeResult = await pool.query(`
        SELECT DISTINCT ON (horizon_days)
          horizon_days,
          mae
        FROM training.model_runs_event
        WHERE mae IS NOT NULL
          AND status = 'promoted'
          AND horizon_days IN (5, 21, 63, 126)
        ORDER BY horizon_days, created_at DESC
      `);
      for (const row of maeResult.rows) {
        maeByHorizon[row.horizon_days] = parseFloat(row.mae);
      }
    } catch {
      console.warn(
        "[forecast-targets] Could not fetch MAE from model_runs_event",
      );
    }

    // 3) Build the response with all real data
    const asOfDates = forecastResult.rows.map((row: { as_of_date: string }) =>
      String(row.as_of_date),
    );
    const asOfDateMin = [...asOfDates].sort()[0];
    const asOfDateMax = [...asOfDates].sort()[asOfDates.length - 1];
    const mixedVintage = new Set(asOfDates).size > 1;
    // Use current_price from the row with the latest as_of_date (not rows[0],
    // which is ordered by horizon first and may not be the freshest vintage).
    const latestRow = forecastResult.rows.reduce(
      (
        best: { as_of_date: string; current_price: number },
        r: { as_of_date: string; current_price: number },
      ) => (String(r.as_of_date) > String(best.as_of_date) ? r : best),
      forecastResult.rows[0],
    );
    const currentPrice = parseFloat(String(latestRow.current_price));

    const targets = forecastResult.rows.map(
      (row: {
        horizon_days: number;
        as_of_date: string;
        forecast_date: string;
        price_p30: number;
        price_p50: number;
        price_p70: number;
        current_price: number;
        model_version: string | null;
      }) => {
        const h = row.horizon_days;

        return {
          id: `tp-${h}d`,
          kind: "TP" as const,
          label: `${h}d`,
          horizonDays: h,
          asOfDate: row.as_of_date,
          forecastDate: row.forecast_date,
          oofPrice: row.price_p50,
          priceLow: row.price_p30,
          priceHigh: row.price_p70,
          mae: maeByHorizon[h] ?? null,
          modelVersion: row.model_version,
        };
      },
    );

    return NextResponse.json({
      symbol: "ZL",
      asOfDate: asOfDateMax,
      asOfDateMin,
      asOfDateMax,
      mixedVintage,
      currentPrice,
      targets,
    });
  } catch (error) {
    console.error("ZL forecast-targets API error:", error);
    return NextResponse.json(
      { error: "Failed to fetch forecast targets" },
      { status: 500 },
    );
  }
}
