/**
 * NOAA Weather (1D) Bronze Ingestion
 *
 * Refreshes `raw.weather_noaa_1d` using NOAA CDO API (GHCN-Daily).
 * Pulls only incremental dates per station (no synthetic data, no schema creation).
 */

import { createHash } from "crypto";
import { Pool, type PoolClient } from "pg";
import { inngest } from "./client";

const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
  ssl: { rejectUnauthorized: false },
});

const NOAA_API_TOKEN = process.env.NOAA_API_TOKEN || process.env.NOAA_TOKEN;
const NOAA_BASE_URL = "https://www.ncei.noaa.gov/cdo-web/api/v2/data";

const DATATYPES = ["TMAX", "TMIN", "TAVG", "PRCP", "SNOW", "AWND", "SNWD", "EVAP", "RHAV", "WSFG"] as const;

const SCALE: Record<(typeof DATATYPES)[number], number> = {
  TMAX: 0.1,
  TMIN: 0.1,
  TAVG: 0.1,
  PRCP: 0.1,
  EVAP: 0.1,
  AWND: 0.1,
  WSFG: 0.1,
  SNOW: 1.0,
  SNWD: 1.0,
  RHAV: 1.0,
};

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function addDays(yyyyMmDd: string, days: number): string {
  const dt = new Date(`${yyyyMmDd}T00:00:00Z`);
  dt.setUTCDate(dt.getUTCDate() + days);
  return dt.toISOString().slice(0, 10);
}

function computeRowHash(stationId: string, eventDate: string, payload: Record<string, unknown>): string {
  return createHash("sha256")
    .update(`${stationId}|${eventDate}|${JSON.stringify(payload)}`)
    .digest("hex");
}

async function createIngestRun(client: PoolClient, jobName: string): Promise<string> {
  const result = await client.query(
    `INSERT INTO ops.ingest_run (job_name, status, started_at) VALUES ($1, 'running', NOW()) RETURNING id`,
    [jobName]
  );
  return result.rows[0].id;
}

async function updateIngestRun(
  client: PoolClient,
  runId: string,
  status: string,
  attempted: number,
  inserted: number,
  skipped: number,
  quarantined: number,
  errorMessage?: string
): Promise<void> {
  await client.query(
    `UPDATE ops.ingest_run SET status=$2, completed_at=NOW(),
     rows_attempted=$3, rows_inserted=$4, rows_skipped=$5, rows_quarantined=$6, error_message=$7 WHERE id=$1`,
    [runId, status, attempted, inserted, skipped, quarantined, errorMessage]
  );
}

async function eventStationExists(client: PoolClient, stationId: string, eventDate: string): Promise<boolean> {
  const r = await client.query(
    `SELECT 1 FROM raw.weather_noaa_1d WHERE station_id=$1 AND event_date=$2::date LIMIT 1`,
    [stationId, eventDate]
  );
  return r.rows.length > 0;
}

async function getStations(client: PoolClient): Promise<
  Array<{ station_id: string; max_date: string | null; region: string | null; country: string | null; specialist_bucket: string | null }>
> {
  const r = await client.query(
    `SELECT station_id,
            MAX(event_date)::date::text as max_date,
            MAX(region)::text as region,
            MAX(country)::text as country,
            MAX(specialist_bucket)::text as specialist_bucket
     FROM raw.weather_noaa_1d
     GROUP BY station_id
     ORDER BY station_id`
  );
  return r.rows;
}

async function fetchNoaaStation(
  stationId: string,
  startDate: string,
  endDate: string
): Promise<Array<{ date: string; datatype: string; value: number }>> {
  if (!NOAA_API_TOKEN) {
    throw new Error("NOAA_API_TOKEN not configured");
  }

  const headers = { token: NOAA_API_TOKEN, "User-Agent": "ZINC-Fusion/1.0" };

  const all: Array<{ date: string; datatype: string; value: number }> = [];
  let offset = 1;
  const limit = 1000;

  while (true) {
    const url = new URL(NOAA_BASE_URL);
    url.searchParams.set("datasetid", "GHCND");
    // `stationId` must be a valid NOAA station id (typically already prefixed with `GHCND:`).
    url.searchParams.set("stationid", stationId);
    url.searchParams.set("startdate", startDate);
    url.searchParams.set("enddate", endDate);
    url.searchParams.set("datatypeid", DATATYPES.join(","));
    url.searchParams.set("units", "metric");
    url.searchParams.set("limit", String(limit));
    url.searchParams.set("offset", String(offset));

    const res = await fetch(url.toString(), { headers });
    if (res.status === 429) {
      // NOAA rate limit; wait and retry this page.
      await sleep(60_000);
      continue;
    }
    if (!res.ok) {
      throw new Error(`NOAA fetch failed for ${stationId}: ${res.status}`);
    }

    const json = (await res.json()) as {
      results?: Array<{ date: string; datatype: string; value: number }>;
      metadata?: { resultset?: { count?: number } };
    };

    const results = json.results ?? [];
    all.push(...results);

    const total = json.metadata?.resultset?.count ?? results.length;
    if (offset + limit > total) break;

    offset += limit;
    await sleep(250);
  }

  return all;
}

function toNoaaStationId(stationId: string): string | null {
  // Legacy/non-NOAA sources are stored in the same table; this job only handles NOAA CDO (GHCN-Daily).
  if (stationId.startsWith("OM_")) return null;
  if (stationId.startsWith("OPENMETEO:")) return null;

  if (stationId.startsWith("GHCND:")) return stationId;

  // Unknown namespaced identifiers (e.g., OPENMETEO:*) are not NOAA station ids.
  if (stationId.includes(":")) return null;

  // Treat bare station ids (e.g., USW00014933) as NOAA and prefix.
  return `GHCND:${stationId}`;
}

export const noaaWeatherDaily = inngest.createFunction(
  { id: "noaa-weather-daily", name: "NOAA Weather (1D)", retries: 3 },
  { cron: "0 13 * * 1-5" }, // 7AM CT weekdays
  async ({ step, logger }) => {
    if (!process.env.DATABASE_URL) {
      throw new Error("DATABASE_URL not configured");
    }

    const client = await pool.connect();
    let runId: string | null = null;
    let attempted = 0;
    let inserted = 0;
    let skipped = 0;
    let quarantined = 0;

    try {
      runId = await step.run("create-ingest-run", () => createIngestRun(client, "noaa-weather-daily"));
      logger.info(`Started ingest run: ${runId}`);

      const stations = await step.run("load-stations", () => getStations(client));
      const stationsNoaa = stations
        .map((s) => ({ ...s, noaa_station_id: toNoaaStationId(s.station_id) }))
        .filter((s) => s.noaa_station_id !== null) as Array<
        (typeof stations)[number] & { noaa_station_id: string }
      >;
      logger.info(`Stations: ${stations.length} total, ${stationsNoaa.length} NOAA`);

      const today = new Date().toISOString().slice(0, 10);
      const endDate = addDays(today, -1); // avoid same-day partials

      for (const station of stationsNoaa) {
        await step.run(`station-${station.station_id}`, async () => {
          const startDate = station.max_date ? addDays(station.max_date, 1) : addDays(endDate, -30);
          if (startDate > endDate) return;

          const rows = await fetchNoaaStation(station.noaa_station_id, startDate, endDate);
          if (rows.length === 0) return;

          // Group by YYYY-MM-DD
          const byDate = new Map<string, Record<string, number>>();
          for (const r of rows) {
            const d = String(r.date).slice(0, 10);
            const dt = r.datatype as (typeof DATATYPES)[number];
            if (!DATATYPES.includes(dt)) continue;
            const scaled = Number(r.value) * SCALE[dt];
            if (!Number.isFinite(scaled)) continue;
            const rec = byDate.get(d) ?? {};
            rec[dt] = scaled;
            byDate.set(d, rec);
          }

          for (const [eventDate, values] of byDate.entries()) {
            attempted++;
            if (await eventStationExists(client, station.station_id, eventDate)) {
              skipped++;
              continue;
            }

            const payload = {
              station_id: station.station_id,
              event_date: eventDate,
              ...values,
            };
            const rowHash = computeRowHash(station.station_id, eventDate, payload);
            const tags = station.specialist_bucket ? [station.specialist_bucket] : [];

            await client.query(
              `INSERT INTO raw.weather_noaa_1d
                (station_id, event_date,
                 tavg_c, tmin_c, tmax_c, prcp_mm, snow_mm, awnd_ms, snwd_mm, evap_mm, rhav_pct, wsfg_ms,
                 region, country, specialist_bucket,
                 source, source_url, raw_payload, ingestion_batch_id, row_hash, specialist_tags, ingested_at)
               VALUES ($1, $2::date,
                       $3, $4, $5, $6, $7, $8, $9, $10, $11, $12,
                       $13, $14, $15,
                       $16, $17, $18::jsonb, $19, $20, $21, NOW())`,
              [
                station.station_id,
                eventDate,
                values.TAVG ?? null,
                values.TMIN ?? null,
                values.TMAX ?? null,
                values.PRCP ?? null,
                values.SNOW ?? null,
                values.AWND ?? null,
                values.SNWD ?? null,
                values.EVAP ?? null,
                values.RHAV ?? null,
                values.WSFG ?? null,
                station.region,
                station.country,
                station.specialist_bucket,
                "noaa_cdo_api",
                NOAA_BASE_URL,
                JSON.stringify(payload),
                runId,
                rowHash,
                tags,
              ]
            );
            inserted++;
          }
        });
      }

      await step.run("complete", () => updateIngestRun(client, runId!, "success", attempted, inserted, skipped, quarantined));
      return { status: "success", runId, attempted, inserted, skipped, quarantined };
    } catch (error) {
      const msg = error instanceof Error ? error.message : String(error);
      if (runId) {
        await updateIngestRun(client, runId, "failed", attempted, inserted, skipped, quarantined, msg);
      }
      throw error;
    } finally {
      client.release();
    }
  }
);
