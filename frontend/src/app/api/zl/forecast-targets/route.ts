import { NextResponse } from "next/server";
import { query } from "@/lib/db";

const CACHE_HEADERS = {
  "Cache-Control": "public, s-maxage=3600, stale-while-revalidate=3600",
};

/**
 * GET /api/zl/forecast-targets
 *
 * Returns the latest Core Model probabilistic zones shaped for the
 * ForecastTargetsPrimitive chart overlay.
 *
 * Data sources (all real, direct):
 *   - forecasts.production_1d        → Monte Carlo quantile zones (price_p30/p50/p70)
 *   - training.model_runs_event      → MAE per horizon (error envelope language)
 */

interface ForecastRow {
  horizon_days: number;
  as_of_date: string;
  forecast_date: string;
  price_p30: number;
  price_p50: number;
  price_p70: number;
  prob_enter_zone: number | null;
  current_price: number;
  model_version: string | null;
}

function toTargetInput(
  row: ForecastRow,
  currentPrice: number,
  maeByHorizon: Record<number, number>,
) {
  const h = row.horizon_days;
  const direction = row.price_p50 >= currentPrice ? "TP" : "SL";
  const rankKey = `${h}-${row.as_of_date}`;

  return {
    rankKey,
    kind: direction as "TP" | "SL",
    horizonLabel: `${h}d`,
    horizonDays: h,
    asOfDate: row.as_of_date,
    forecastDate: row.forecast_date,
    oofPrice: row.price_p50,
    priceLow: row.price_p30,
    priceHigh: row.price_p70,
    mae: maeByHorizon[h] ?? null,
    probabilityMethod: "MC" as const,
    probabilityZone: "P30-P70" as const,
    coveragePct:
      row.prob_enter_zone != null
        ? Math.round(row.prob_enter_zone * 100)
        : null,
    modelVersion: row.model_version,
  };
}

function assignRankLabels(
  targetInputs: ReturnType<typeof toTargetInput>[],
): Map<string, string> {
  const tpZones = targetInputs
    .filter((z) => z.kind === "TP")
    .sort((a, b) => a.oofPrice - b.oofPrice);
  const slZones = targetInputs
    .filter((z) => z.kind === "SL")
    .sort((a, b) => b.oofPrice - a.oofPrice);

  const labelByKey = new Map<string, string>();
  for (let i = 0; i < tpZones.length; i++) {
    labelByKey.set(tpZones[i].rankKey, `TP${i + 1}`);
  }
  for (let i = 0; i < slZones.length; i++) {
    labelByKey.set(slZones[i].rankKey, `SL${i + 1}`);
  }
  return labelByKey;
}

export async function GET() {
  try {
    // 1) Latest production forecast per horizon
    const forecastRows = await query<ForecastRow>(`
      SELECT DISTINCT ON (horizon)
        horizon                  AS horizon_days,
        as_of_date,
        forecast_date,
        price_p30::float,
        price_p50::float,
        price_p70::float,
        prob_enter_zone::float,
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

    if (forecastRows.length === 0) {
      return NextResponse.json(
        { symbol: "ZL", targets: [] },
        { headers: CACHE_HEADERS }
      );
    }

    // 2) Latest MAE per horizon from model_runs (best-effort — non-fatal)
    const maeByHorizon: Record<number, number> = {};
    try {
      const maeRows = await query<{ horizon_days: number; mae: string }>(`
        SELECT DISTINCT ON (horizon_days)
          horizon_days,
          mae
        FROM training.model_runs_event
        WHERE mae IS NOT NULL
          AND status = 'promoted'
          AND horizon_days IN (5, 21, 63, 126)
        ORDER BY horizon_days, created_at DESC
      `);
      for (const row of maeRows) {
        maeByHorizon[row.horizon_days] = parseFloat(row.mae);
      }
    } catch {
      console.warn(
        "[forecast-targets] Could not fetch MAE from model_runs_event",
      );
    }

    // 3) Build response
    const asOfDates = forecastRows.map((row) => String(row.as_of_date));
    const asOfDateMin = [...asOfDates].sort()[0];
    const asOfDateMax = [...asOfDates].sort()[asOfDates.length - 1];
    const mixedVintage = new Set(asOfDates).size > 1;
    const latestRow = forecastRows.reduce(
      (best: ForecastRow, r: ForecastRow) =>
        String(r.as_of_date) > String(best.as_of_date) ? r : best,
      forecastRows[0],
    );
    const currentPrice = parseFloat(String(latestRow.current_price));

    const targetInputs = forecastRows.map((row) =>
      toTargetInput(row, currentPrice, maeByHorizon),
    );

    const labelByKey = assignRankLabels(targetInputs);

    const targets = targetInputs.map((z) => ({
      id: `${z.kind.toLowerCase()}-${z.horizonDays}d-${z.asOfDate}`,
      kind: z.kind,
      label: labelByKey.get(z.rankKey) ?? z.kind,
      horizonLabel: z.horizonLabel,
      horizonDays: z.horizonDays,
      asOfDate: z.asOfDate,
      forecastDate: z.forecastDate,
      oofPrice: z.oofPrice,
      priceLow: z.priceLow,
      priceHigh: z.priceHigh,
      mae: z.mae,
      probabilityMethod: z.probabilityMethod,
      probabilityZone: z.probabilityZone,
      coveragePct: z.coveragePct,
      modelVersion: z.modelVersion,
    }));

    return NextResponse.json({
      symbol: "ZL",
      asOfDate: asOfDateMax,
      asOfDateMin,
      asOfDateMax,
      mixedVintage,
      currentPrice,
      targets,
    }, { headers: CACHE_HEADERS });
  } catch (error) {
    console.error("ZL forecast-targets API error:", error);
    return NextResponse.json(
      { error: "Failed to fetch forecast targets" },
      { status: 500 },
    );
  }
}
