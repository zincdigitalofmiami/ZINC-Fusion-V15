/**
 * FX Spot (1D) Data Ingestion via FRED
 *
 * Purpose: keep `mkt.fx_1d` fresh for Core/Specialists.
 * Zero tolerance: no synthetic data; fail loudly on missing config.
 */

import { createHash } from "crypto";
import pool from "@/lib/db";
import type { PoolClient } from "pg";
import { inngest } from "./client";

const FRED_API_KEY = process.env.FRED_API_KEY;

// Authoritative 21 FRED FX pairs for mkt.fx_1d
// Pair names use SLASH format established by 20260118_fx_consolidation migration.
// Note: NZDUSD comes from Databento (no FRED series)
const PAIRS: Array<{ pair: string; seriesId: string }> = [
  // Major pairs (slash format per migration convention)
  { pair: "AUD/USD", seriesId: "DEXUSAL" },
  { pair: "EUR/USD", seriesId: "DEXUSEU" },
  { pair: "GBP/USD", seriesId: "DEXUSUK" },
  { pair: "BRL/USD", seriesId: "DEXBZUS" },
  { pair: "CAD/USD", seriesId: "DEXCAUS" },
  { pair: "CHF/USD", seriesId: "DEXSZUS" },
  { pair: "CNY/USD", seriesId: "DEXCHUS" },
  { pair: "USD/JPY", seriesId: "DEXJPUS" },
  { pair: "KRW/USD", seriesId: "DEXKOUS" },
  { pair: "MXN/USD", seriesId: "DEXMXUS" },
  { pair: "SGD/USD", seriesId: "DEXSIUS" },
  // Extended pairs
  { pair: "HKD/USD", seriesId: "DEXHKUS" },
  { pair: "INR/USD", seriesId: "DEXINUS" },
  { pair: "MYR/USD", seriesId: "DEXMAUS" },
  { pair: "NOK/USD", seriesId: "DEXNOUS" },
  { pair: "SEK/USD", seriesId: "DEXSDUS" },
  { pair: "THB/USD", seriesId: "DEXTHUS" },
  { pair: "TWD/USD", seriesId: "DEXTAUS" },
  // DXY indices (Fed trade-weighted dollar)
  { pair: "DXY_BROAD", seriesId: "DTWEXBGS" },
  { pair: "DXY_AFE", seriesId: "DTWEXAFEGS" },
  { pair: "DXY_EME", seriesId: "DTWEXEMEGS" },
];

function computeRowHash(pair: string, eventDate: string, rate: number, seriesId: string): string {
  return createHash("sha256").update(`${pair}|${eventDate}|${rate}|${seriesId}`).digest("hex");
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

async function eventPairExists(client: PoolClient, eventDate: string, pair: string): Promise<boolean> {
  const r = await client.query(
    `SELECT 1 FROM mkt.fx_1d WHERE event_date=$1::date AND pair=$2 LIMIT 1`,
    [eventDate, pair]
  );
  return r.rows.length > 0;
}

async function getMaxDate(client: PoolClient, pair: string): Promise<string | null> {
  const r = await client.query(
    `SELECT MAX(event_date)::date::text as max_date FROM mkt.fx_1d WHERE pair=$1`,
    [pair]
  );
  return r.rows[0]?.max_date ?? null;
}

function addDays(yyyyMmDd: string, days: number): string {
  const dt = new Date(`${yyyyMmDd}T00:00:00Z`);
  dt.setUTCDate(dt.getUTCDate() + days);
  return dt.toISOString().slice(0, 10);
}

async function fetchFredObservations(seriesId: string, startDate: string): Promise<
  Array<{ date: string; value: string }>
> {
  if (!FRED_API_KEY) {
    throw new Error("FRED_API_KEY not configured");
  }

  const url = new URL("https://api.stlouisfed.org/fred/series/observations");
  url.searchParams.set("series_id", seriesId);
  url.searchParams.set("api_key", FRED_API_KEY);
  url.searchParams.set("file_type", "json");
  url.searchParams.set("observation_start", startDate);
  url.searchParams.set("sort_order", "asc");

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 15000); // 15s timeout

  try {
    const res = await fetch(url.toString(), {
      headers: { "User-Agent": "ZINC-Fusion/1.0" },
      signal: controller.signal,
    });
    clearTimeout(timeout);

    if (!res.ok) {
      throw new Error(`FRED fetch failed for ${seriesId}: ${res.status}`);
    }

    const json = (await res.json()) as { observations?: Array<{ date: string; value: string }> };
    return json.observations ?? [];
  } catch (err) {
    clearTimeout(timeout);
    if (err instanceof Error && err.name === 'AbortError') {
      throw new Error(`FRED fetch timed out for ${seriesId} after 15s`);
    }
    throw err;
  }
}

export const fxSpotDaily = inngest.createFunction(
  { id: "fx-spot-daily", name: "FX Spot (1D) via FRED", retries: 3, concurrency: [{ limit: 1 }] },
  { cron: "0 */8 * * *" }, // Every 8 hours (0:00, 8:00, 16:00 UTC)
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
      runId = await step.run("create-ingest-run", () => createIngestRun(client, "fx-spot-daily"));
      logger.info(`Started ingest run: ${runId}`);

      for (const { pair, seriesId } of PAIRS) {
        await step.run(`pair-${pair}`, async () => {
          const maxDate = await getMaxDate(client, pair);
          const startDate = maxDate ? addDays(maxDate, 1) : "2000-01-01";

          const observations = await fetchFredObservations(seriesId, startDate);
          logger.info(`${pair}: fetched ${observations.length} obs from ${startDate}`);

          for (const obs of observations) {
            const eventDate = obs.date;
            const value = obs.value;

            if (!eventDate || value === "." || value === "") {
              skipped++;
              continue;
            }

            const rate = Number(value);
            if (!Number.isFinite(rate)) {
              quarantined++;
              continue;
            }

            attempted++;

            if (await eventPairExists(client, eventDate, pair)) {
              skipped++;
              continue;
            }

            const rowHash = computeRowHash(pair, eventDate, rate, seriesId);
            await client.query(
              `INSERT INTO mkt.fx_1d
                (pair, event_date, rate, source, row_hash)
               VALUES ($1, $2::date, $3, $4, $5)`,
              [
                pair,
                eventDate,
                rate,
                "FRED",
                rowHash,
              ]
            );
            inserted++;
          }
        });
      }

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
