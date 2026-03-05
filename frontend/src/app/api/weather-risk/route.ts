import { NextResponse } from "next/server";
import { query } from "@/lib/db";

export const dynamic = "force-dynamic";

interface LatestDateRow {
  latest_date: string | null;
}

interface RegionRow {
  region: string;
  stations: number;
  avg_precip_mm: number | null;
  avg_temp_c: number | null;
}

interface StationRow {
  station_id: string;
  region: string;
  precip_mm: number | null;
  snow_mm: number | null;
  temp_c: number | null;
}

export async function GET() {
  try {
    const latestRows = await query<LatestDateRow>(`
      SELECT MAX(event_date)::text AS latest_date
      FROM alt.weather_1d
    `);

    const asOfDate = latestRows[0]?.latest_date ?? null;

    if (!asOfDate) {
      return NextResponse.json(
        {
          asOfDate: null,
          stationCount: 0,
          regions: [],
          stations: [],
        },
        { headers: { "Cache-Control": "no-store" } },
      );
    }

    const [regionRows, stationRows] = await Promise.all([
      query<RegionRow>(
        `
          SELECT
            COALESCE(region, 'Unknown') AS region,
            COUNT(*)::int AS stations,
            AVG(prcp_mm)::float8 AS avg_precip_mm,
            AVG(tavg_c)::float8 AS avg_temp_c
          FROM alt.weather_1d
          WHERE event_date = $1::date
          GROUP BY 1
          ORDER BY stations DESC, region ASC
        `,
        [asOfDate],
      ),
      query<StationRow>(
        `
          SELECT
            station_id,
            COALESCE(region, 'Unknown') AS region,
            prcp_mm::float8 AS precip_mm,
            snow_mm::float8 AS snow_mm,
            tavg_c::float8 AS temp_c
          FROM alt.weather_1d
          WHERE event_date = $1::date
          ORDER BY region ASC, station_id ASC
          LIMIT 80
        `,
        [asOfDate],
      ),
    ]);

    return NextResponse.json(
      {
        asOfDate,
        stationCount: stationRows.length,
        regions: regionRows.map((r) => ({
          region: r.region,
          stations: r.stations,
          avgPrecipMm: r.avg_precip_mm,
          avgTempC: r.avg_temp_c,
        })),
        stations: stationRows.map((s) => ({
          stationId: s.station_id,
          region: s.region,
          precipMm: s.precip_mm,
          snowMm: s.snow_mm,
          tempC: s.temp_c,
        })),
      },
      { headers: { "Cache-Control": "no-store" } },
    );
  } catch (error) {
    console.error("[weather-risk] failed:", error);
    return NextResponse.json(
      {
        error: "Failed to fetch weather risk data",
        details: String(error),
      },
      { status: 500, headers: { "Cache-Control": "no-store" } },
    );
  }
}
