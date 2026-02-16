/**
 * NOAA Weather (1D) Data Ingestion
 *
 * INGESTION CONTRACT:
 * - Logs each run in ops.ingest_run
 * - Computes row_hash for idempotency
 * - Append-only inserts (no upserts)
 *
 * Refreshes `alt.weather_1d` using NOAA CDO API (GHCN-Daily).
 * Pulls only incremental dates per station (no synthetic data, no schema creation).
 *
 * @author Claude (ZINC-FUSION-V15)
 * @version 1.1.0
 * @date 2026-02-16
 */

import { createHash } from "crypto";
import { inngest, DB_CONCURRENCY } from "./client";
import dbPool from "@/lib/db";

const pool = dbPool;

const NOAA_API_TOKEN = process.env.NOAA_API_TOKEN || process.env.NOAA_TOKEN;
const NOAA_BASE_URL = "https://www.ncei.noaa.gov/cdo-web/api/v2/data";
const NOAA_REQUEST_TIMEOUT_MS = 20_000;
const NOAA_MAX_429_RETRIES = 5;

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

// PoolClient helper functions removed — SQL inlined inside step.run() closures
// to prevent stale connections across Inngest durable execution boundaries.

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
  let rateLimitRetries = 0;

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

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), NOAA_REQUEST_TIMEOUT_MS);
    let res: Response;
    try {
      res = await fetch(url.toString(), { headers, signal: controller.signal });
    } catch (err) {
      if (err instanceof Error && err.name === "AbortError") {
        throw new Error(`NOAA request timeout for ${stationId} after ${NOAA_REQUEST_TIMEOUT_MS}ms`);
      }
      throw err;
    } finally {
      clearTimeout(timeout);
    }

    if (res.status === 429) {
      // NOAA rate limit; bounded retries to avoid hanging indefinitely.
      rateLimitRetries += 1;
      if (rateLimitRetries > NOAA_MAX_429_RETRIES) {
        throw new Error(`NOAA rate limit exceeded for ${stationId}: ${NOAA_MAX_429_RETRIES} retries`);
      }
      await sleep(Math.min(60_000, 5000 * rateLimitRetries));
      continue;
    }
    rateLimitRetries = 0;

    if (!res.ok) {
      // 400 errors often indicate invalid station ID or station no longer reporting
      // Don't throw - return empty array so other stations can continue
      if (res.status === 400 || res.status === 404) {
        console.warn(`NOAA station ${stationId} returned ${res.status} - station may be inactive`);
        return [];
      }
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
  { id: "noaa-weather-daily", name: "NOAA Weather (1D)", retries: 1, concurrency: [DB_CONCURRENCY, { limit: 1 }] },
  { cron: "30 11 * * *" }, // Daily at 11:30 UTC
  async ({ step, logger }) => {
    if (!process.env.DATABASE_URL) {
      throw new Error("DATABASE_URL not configured");
    }

    // ── Step 1: create ingest run ──
    const runId = await step.run("create-ingest-run", async () => {
      const client = await pool.connect();
      try {
        const result = await client.query(
          `INSERT INTO ops.ingest_run (job_name, status, started_at) VALUES ($1, 'running', NOW()) RETURNING id`,
          ["noaa-weather-daily"]
        );
        return result.rows[0].id as string;
      } finally {
        client.release();
      }
    });

    logger.info(`Started ingest run: ${runId}`);

    // ── Step 2: load station list ──
    const stations = await step.run("load-stations", async () => {
      const client = await pool.connect();
      try {
        const r = await client.query(
          `SELECT station_id,
                  MAX(event_date)::date::text as max_date,
                  MAX(region)::text as region,
                  MAX(country)::text as country
           FROM alt.weather_1d
           GROUP BY station_id
           ORDER BY station_id`
        );
        return r.rows as Array<{ station_id: string; max_date: string | null; region: string | null; country: string | null }>;
      } finally {
        client.release();
      }
    });

    const stationsNoaa = stations
      .map((s) => ({ ...s, noaa_station_id: toNoaaStationId(s.station_id) }))
      .filter((s) => s.noaa_station_id !== null) as Array<
      (typeof stations)[number] & { noaa_station_id: string }
    >;
    logger.info(`Stations: ${stations.length} total, ${stationsNoaa.length} NOAA`);

    const today = new Date().toISOString().slice(0, 10);
    const endDate = addDays(today, -1); // avoid same-day partials

    // ── Step 3: fetch from NOAA API + insert (batched in one step) ──
    // One connection for the entire batch is fine — this is a single step.run().
    const batchSummary = await step.run("ingest-stations-batch", async () => {
      let attemptedLocal = 0;
      let insertedLocal = 0;
      let skippedLocal = 0;
      let quarantinedLocal = 0;
      const stationErrorsLocal: string[] = [];

      const client = await pool.connect();
      try {
        for (const station of stationsNoaa) {
          const startDate = station.max_date ? addDays(station.max_date, 1) : addDays(endDate, -30);
          if (startDate > endDate) continue;

          let rows: Array<{ date: string; datatype: string; value: number }>;
          try {
            rows = await fetchNoaaStation(station.noaa_station_id, startDate, endDate);
          } catch (err) {
            // Log but don't fail the entire job for one station
            const msg = err instanceof Error ? err.message : String(err);
            stationErrorsLocal.push(`${station.station_id}: ${msg}`);
            quarantinedLocal++;
            continue;
          }
          if (rows.length === 0) continue;

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
            attemptedLocal++;

            const exists = await client.query(
              `SELECT 1 FROM alt.weather_1d WHERE station_id=$1 AND event_date=$2::date LIMIT 1`,
              [station.station_id, eventDate]
            );
            if (exists.rows.length > 0) {
              skippedLocal++;
              continue;
            }

            const payload = {
              station_id: station.station_id,
              event_date: eventDate,
              ...values,
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
                values.TAVG ?? null,
                values.TMIN ?? null,
                values.TMAX ?? null,
                values.PRCP ?? null,
                values.SNOW ?? null,
                station.region,
                station.country,
                "noaa_cdo_api",
                JSON.stringify(payload),
                runId,
                rowHash,
              ]
            );
            insertedLocal++;
          }
        }
      } finally {
        client.release();
      }

      return {
        attempted: attemptedLocal,
        inserted: insertedLocal,
        skipped: skippedLocal,
        quarantined: quarantinedLocal,
        stationErrors: stationErrorsLocal,
      };
    });

    // ── Step 4: finalize ingest run ──
    await step.run("complete-ingest-run", async () => {
      const client = await pool.connect();
      try {
        await client.query(
          `UPDATE ops.ingest_run SET status=$2, completed_at=NOW(),
           rows_attempted=$3, rows_inserted=$4, rows_skipped=$5, rows_quarantined=$6 WHERE id=$1`,
          [runId, "success", batchSummary.attempted, batchSummary.inserted, batchSummary.skipped, batchSummary.quarantined]
        );
      } finally {
        client.release();
      }
    });

    // Log any station errors for debugging (but don't fail the job)
    if (batchSummary.stationErrors.length > 0) {
      logger.warn(`Station errors (${batchSummary.stationErrors.length}): ${batchSummary.stationErrors.slice(0, 5).join("; ")}`);
    }

    logger.info(`Completed: ${batchSummary.inserted} inserted, ${batchSummary.skipped} skipped`);

    return {
      status: "success",
      runId,
      attempted: batchSummary.attempted,
      inserted: batchSummary.inserted,
      skipped: batchSummary.skipped,
      quarantined: batchSummary.quarantined,
      stationErrors: batchSummary.stationErrors.length,
    };
  }
);
