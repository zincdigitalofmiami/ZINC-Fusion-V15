/**
 * Open-Meteo Weather (1D) Bronze Ingestion
 *
 * Refreshes `alt.weather_1d` for Open-Meteo-backed station ids:
 * - `OM_*` (US soy belt cities)
 * - `OPENMETEO:*` (region-level codes)
 *
 * Notes:
 * - Insert-only, idempotent via (station_id, event_date) existence checks + row_hash.
 * - No synthetic data; quarantines when geocoding is ambiguous or missing.
 */

import { createHash } from "crypto";
import pool from "@/lib/db";
import type { PoolClient } from "pg";
import { inngest } from "./client";

const GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search";
const ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive";

const US_STATE_NAMES: Record<string, string> = {
  IA: "Iowa",
  IL: "Illinois",
  IN: "Indiana",
  MN: "Minnesota",
  MO: "Missouri",
  NE: "Nebraska",
};

const OPENMETEO_REGION_CAPITAL: Record<string, { name: string; country: string }> = {
  // Brazil
  BR_MG: { name: "Belo Horizonte", country: "BR" },
  BR_MS: { name: "Campo Grande", country: "BR" },
  BR_MT: { name: "Cuiabá", country: "BR" },
  BR_NE: { name: "Recife", country: "BR" },
  BR_PA: { name: "Belém", country: "BR" },
  BR_PR: { name: "Curitiba", country: "BR" },
  BR_RS: { name: "Porto Alegre", country: "BR" },
  BR_SP: { name: "São Paulo", country: "BR" },
  // Argentina
  AR_BA: { name: "Buenos Aires", country: "AR" },
  AR_CH: { name: "Resistencia", country: "AR" },
  AR_CO: { name: "Córdoba", country: "AR" },
  AR_CR: { name: "Corrientes", country: "AR" },
  AR_ER: { name: "Paraná", country: "AR" },
  AR_FO: { name: "Formosa", country: "AR" },
  AR_LP: { name: "Santa Rosa", country: "AR" },
  AR_MZ: { name: "Mendoza", country: "AR" },
  AR_SE: { name: "Santiago del Estero", country: "AR" },
  AR_SF: { name: "Santa Fe", country: "AR" },
};

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

function addDays(yyyyMmDd: string, days: number): string {
  const dt = new Date(`${yyyyMmDd}T00:00:00Z`);
  dt.setUTCDate(dt.getUTCDate() + days);
  return dt.toISOString().slice(0, 10);
}

async function eventStationExists(client: PoolClient, stationId: string, eventDate: string): Promise<boolean> {
  const r = await client.query(
    `SELECT 1 FROM alt.weather_1d WHERE station_id=$1 AND event_date=$2::date LIMIT 1`,
    [stationId, eventDate]
  );
  return r.rows.length > 0;
}

async function getStations(client: PoolClient): Promise<
  Array<{
    station_id: string;
    max_date: string | null;
    region: string | null;
    country: string | null;
  }>
> {
  const r = await client.query(
    `SELECT station_id,
            MAX(event_date)::date::text as max_date,
            MAX(region)::text as region,
            MAX(country)::text as country
     FROM alt.weather_1d
     WHERE station_id LIKE 'OM\\_%' OR station_id LIKE 'OPENMETEO:%'
     GROUP BY station_id
     ORDER BY station_id`
  );
  return r.rows;
}

function resolveGeocodeQuery(
  stationId: string
): { name: string; country: string; requireAdmin1?: string } | null {
  if (stationId.startsWith("OM_")) {
    const parts = stationId.split("_");
    if (parts.length < 3) return null;
    const stateCode = parts[1];
    const stateName = US_STATE_NAMES[stateCode];
    if (!stateName) return null;

    const cityRaw = parts.slice(2).join(" ");
    const cityName = cityRaw
      .split(" ")
      .map((t) => (t === "ST" ? "St" : t.charAt(0) + t.slice(1).toLowerCase()))
      .join(" ");

    return { name: cityName, country: "US", requireAdmin1: stateName };
  }

  if (stationId.startsWith("OPENMETEO:")) {
    const code = stationId.split(":", 2)[1] ?? "";
    const resolved = OPENMETEO_REGION_CAPITAL[code];
    if (!resolved) return null;
    return { name: resolved.name, country: resolved.country };
  }

  return null;
}

async function geocodeStrict(
  name: string,
  country: string,
  requireAdmin1?: string
): Promise<{ latitude: number; longitude: number; label: string }> {
  const url = new URL(GEOCODE_URL);
  url.searchParams.set("name", name);
  url.searchParams.set("count", "10");
  url.searchParams.set("language", "en");
  url.searchParams.set("format", "json");
  url.searchParams.set("country", country);

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 30000);
  try {
    const res = await fetch(url.toString(), {
      headers: { "User-Agent": "ZINC-Fusion/1.0" },
      signal: controller.signal
    });
    if (!res.ok) {
      throw new Error(`Open-Meteo geocoding failed (${country}/${name}): ${res.status}`);
    }

  const json = (await res.json()) as {
    results?: Array<{ name?: string; admin1?: string; latitude?: number; longitude?: number; country_code?: string }>;
  };
  const results = json.results ?? [];
  if (results.length === 0) {
    throw new Error(`Open-Meteo geocoding returned 0 results (${country}/${name})`);
  }

  const pick = requireAdmin1
    ? results.find((r) => (r.admin1 ?? "").toLowerCase() === requireAdmin1.toLowerCase())
    : results[0];

  if (!pick) {
    throw new Error(`Open-Meteo geocoding ambiguous: no admin1=${requireAdmin1} match for ${country}/${name}`);
  }

  const latitude = Number(pick.latitude);
  const longitude = Number(pick.longitude);
  if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) {
    throw new Error(`Open-Meteo geocoding returned invalid lat/lon for ${country}/${name}`);
  }

    const labelParts = [pick.name ?? name];
    if (pick.admin1) labelParts.push(pick.admin1);
    if (pick.country_code) labelParts.push(pick.country_code);
    return { latitude, longitude, label: labelParts.join(", ") };
  } finally {
    clearTimeout(timeout);
  }
}

async function fetchDailyArchive(
  latitude: number,
  longitude: number,
  startDate: string,
  endDate: string
): Promise<{
  time: string[];
  tmax: Array<number | null>;
  tmin: Array<number | null>;
  tmean: Array<number | null>;
  prcp: Array<number | null>;
  snowMm: Array<number | null>;
  sourceUrl: string;
  raw: unknown;
}> {
  const url = new URL(ARCHIVE_URL);
  url.searchParams.set("latitude", String(latitude));
  url.searchParams.set("longitude", String(longitude));
  url.searchParams.set("start_date", startDate);
  url.searchParams.set("end_date", endDate);
  url.searchParams.set(
    "daily",
    "temperature_2m_max,temperature_2m_min,temperature_2m_mean,precipitation_sum,snowfall_sum"
  );
  url.searchParams.set("timezone", "UTC");

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 30000);
  try {
    const res = await fetch(url.toString(), {
      headers: { "User-Agent": "ZINC-Fusion/1.0" },
      signal: controller.signal
    });
    if (!res.ok) {
      throw new Error(`Open-Meteo archive failed: ${res.status}`);
    }

  const json = (await res.json()) as {
    daily?: {
      time?: string[];
      temperature_2m_max?: Array<number | null>;
      temperature_2m_min?: Array<number | null>;
      temperature_2m_mean?: Array<number | null>;
      precipitation_sum?: Array<number | null>;
      snowfall_sum?: Array<number | null>;
    };
    daily_units?: { snowfall_sum?: string };
  };

  const daily = json.daily ?? {};
  const time = (daily.time ?? []).map((t) => String(t));
  const tmax = daily.temperature_2m_max ?? [];
  const tmin = daily.temperature_2m_min ?? [];
  const tmean = daily.temperature_2m_mean ?? [];
  const prcp = daily.precipitation_sum ?? [];
  const snow = daily.snowfall_sum ?? [];

  const snowUnit = json.daily_units?.snowfall_sum ?? "cm";
  const snowMm = snow.map((v) => {
    if (v === null || v === undefined) return null;
    const n = Number(v);
    if (!Number.isFinite(n)) return null;
    if (snowUnit === "cm") return n * 10.0;
    if (snowUnit === "mm") return n;
    return null;
  });

    return { time, tmax, tmin, tmean, prcp, snowMm, sourceUrl: url.toString(), raw: json };
  } finally {
    clearTimeout(timeout);
  }
}

export const openmeteoWeatherDaily = inngest.createFunction(
  { id: "openmeteo-weather-daily", name: "Open-Meteo Weather (1D)", retries: 3, concurrency: [{ limit: 1 }] },
  { cron: "10 */8 * * *" }, // Every 8 hours at :10
  async ({ step, logger }) => {
    if (!process.env.DATABASE_URL) throw new Error("DATABASE_URL not configured");

    const client = await pool.connect();
    let runId: string | null = null;
    let attempted = 0;
    let inserted = 0;
    let skipped = 0;
    let quarantined = 0;

    try {
      runId = await step.run("create-ingest-run", () => createIngestRun(client, "openmeteo-weather-daily"));
      logger.info(`Started ingest run: ${runId}`);

      const stations = await step.run("load-stations", () => getStations(client));
      logger.info(`Stations: ${stations.length}`);

      const today = new Date().toISOString().slice(0, 10);
      const endDate = addDays(today, -1); // avoid same-day partials

      for (const station of stations) {
        await step.run(`station-${station.station_id}`, async () => {
          const startDate = station.max_date ? addDays(station.max_date, 1) : addDays(endDate, -30);
          if (startDate > endDate) return;

          const q = resolveGeocodeQuery(station.station_id);
          if (!q) {
            quarantined++;
            return;
          }

          const geo = await geocodeStrict(q.name, q.country, q.requireAdmin1);
          const archive = await fetchDailyArchive(geo.latitude, geo.longitude, startDate, endDate);

          const n = archive.time.length;
          if (n === 0) return;

          for (let i = 0; i < n; i++) {
            const eventDate = archive.time[i];
            if (!eventDate) continue;

            attempted++;
            if (await eventStationExists(client, station.station_id, eventDate)) {
              skipped++;
              continue;
            }

            const tmax = archive.tmax[i] ?? null;
            const tmin = archive.tmin[i] ?? null;
            const tavg = archive.tmean[i] ?? null;
            const prcp = archive.prcp[i] ?? null;
            const snowMm = archive.snowMm[i] ?? null;

            const payload = {
              station_id: station.station_id,
              event_date: eventDate,
              latitude: geo.latitude,
              longitude: geo.longitude,
              geocode_label: geo.label,
              temperature_2m_max_c: tmax,
              temperature_2m_min_c: tmin,
              temperature_2m_mean_c: tavg,
              precipitation_sum_mm: prcp,
              snowfall_sum_mm: snowMm,
              source: "openmeteo_archive",
              source_url: archive.sourceUrl,
            };

            const rowHash = computeRowHash(station.station_id, eventDate, payload);

            await client.query(
              `INSERT INTO alt.weather_1d
                (station_id, event_date,
                 tavg_c, tmin_c, tmax_c, prcp_mm, snow_mm,
                 region, country,
                 source, raw_payload, ingestion_batch_id, row_hash)
               VALUES ($1, $2::date,
                       $3, $4, $5, $6, $7,
                       $8, $9,
                       $10, $11::jsonb, $12, $13)`,
              [
                station.station_id,
                eventDate,
                tavg,
                tmin,
                tmax,
                prcp,
                snowMm,
                station.region,
                station.country,
                "openmeteo_archive",
                JSON.stringify(payload),
                runId,
                rowHash,
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

