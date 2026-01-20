/**
 * Weather Features (1D) Daily Aggregation
 *
 * Purpose: Aggregate raw weather data (alt.weather_1d) into regional features (features.weather_1d)
 * Runs after NOAA weather ingestion completes.
 */

import { Pool, type PoolClient } from "pg";
import { inngest } from "./client";

const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
  ssl: { rejectUnauthorized: false },
});

const REGIONS = ["AR", "BR", "US"] as const;

interface RegionAggregates {
  trade_date: string;
  country: string;
  tavg_c: number | null;
  tmin_c: number | null;
  tmax_c: number | null;
  prcp_mm: number | null;
  snow_mm: number | null;
  rhav_pct: number | null;
  awnd_ms: number | null;
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

async function getLastFeatureDate(client: PoolClient): Promise<string> {
  const result = await client.query(
    `SELECT COALESCE(MAX(trade_date)::date::text, '2000-01-01') as max_date FROM features.weather_1d`
  );
  return result.rows[0].max_date;
}

async function aggregateWeatherByRegion(
  client: PoolClient,
  startDate: string
): Promise<RegionAggregates[]> {
  const result = await client.query(
    `SELECT
       event_date::date::text as trade_date,
       country,
       AVG(tavg_c) as tavg_c,
       AVG(tmin_c) as tmin_c,
       AVG(tmax_c) as tmax_c,
       SUM(prcp_mm) as prcp_mm,
       SUM(snow_mm) as snow_mm,
       AVG(rhav_pct) as rhav_pct,
       AVG(awnd_ms) as awnd_ms
     FROM alt.weather_1d
     WHERE event_date > $1::date
       AND country IN ('AR', 'BR', 'US')
     GROUP BY event_date, country
     ORDER BY event_date, country`,
    [startDate]
  );
  return result.rows;
}

function pivotToFeatureRow(
  tradeDate: string,
  regionData: Map<string, RegionAggregates>
): Record<string, unknown> {
  const row: Record<string, unknown> = { trade_date: tradeDate };

  for (const region of REGIONS) {
    const data = regionData.get(region);
    const r = region.toLowerCase();

    row[`wx_${r}_tavg_c`] = data?.tavg_c ?? null;
    row[`wx_${r}_tmin_c`] = data?.tmin_c ?? null;
    row[`wx_${r}_tmax_c`] = data?.tmax_c ?? null;
    row[`wx_${r}_prcp_mm`] = data?.prcp_mm ?? null;
    row[`wx_${r}_prcp_mm_total`] = data?.prcp_mm ?? null; // Will be cumulated in DB
    row[`wx_${r}_snow_mm`] = data?.snow_mm ?? null;
    row[`wx_${r}_rhav_pct`] = data?.rhav_pct ?? null;
    row[`wx_${r}_awnd_ms`] = data?.awnd_ms ?? null;
  }

  return row;
}

async function upsertFeatureRow(client: PoolClient, row: Record<string, unknown>): Promise<boolean> {
  const columns = Object.keys(row).filter((k) => row[k] !== undefined);
  const values = columns.map((k) => row[k]);
  const placeholders = columns.map((_, i) => `$${i + 1}`);

  const updateSet = columns
    .filter((c) => c !== "trade_date")
    .map((c) => `${c} = EXCLUDED.${c}`)
    .join(", ");

  await client.query(
    `INSERT INTO features.weather_1d (${columns.join(", ")})
     VALUES (${placeholders.join(", ")})
     ON CONFLICT (trade_date)
     DO UPDATE SET ${updateSet}`,
    values
  );

  return true;
}

export const weatherFeaturesDaily = inngest.createFunction(
  { id: "weather-features-daily", name: "Weather Features (1D) Aggregation", retries: 3 },
  { cron: "0 14 * * *" }, // 8AM CT daily (after NOAA update at 6AM CT)
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
      runId = await step.run("create-ingest-run", () =>
        createIngestRun(client, "weather-features-daily")
      );
      logger.info(`Started ingest run: ${runId}`);

      // Get last processed date
      const lastDate = await step.run("get-last-date", () => getLastFeatureDate(client));
      logger.info(`Last feature date: ${lastDate}`);

      // Aggregate new weather data
      const aggregates = await step.run("aggregate-weather", () =>
        aggregateWeatherByRegion(client, lastDate)
      );
      logger.info(`Fetched ${aggregates.length} region-day aggregates`);

      if (aggregates.length === 0) {
        await step.run("complete-no-data", () =>
          updateIngestRun(client, runId!, "success", 0, 0, 0, 0)
        );
        return { status: "success", message: "No new weather data" };
      }

      // Group by date
      const byDate = new Map<string, Map<string, RegionAggregates>>();
      for (const agg of aggregates) {
        if (!byDate.has(agg.trade_date)) {
          byDate.set(agg.trade_date, new Map());
        }
        byDate.get(agg.trade_date)!.set(agg.country, agg);
      }

      // Process each date
      await step.run("upsert-features", async () => {
        for (const [tradeDate, regionData] of byDate.entries()) {
          attempted++;
          try {
            const row = pivotToFeatureRow(tradeDate, regionData);
            await upsertFeatureRow(client, row);
            inserted++;
          } catch (err) {
            logger.warn(`Failed to upsert ${tradeDate}: ${err}`);
            quarantined++;
          }
        }
      });

      await step.run("complete", () =>
        updateIngestRun(client, runId!, "success", attempted, inserted, skipped, quarantined)
      );

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
