/**
 * FX Spot (1D) Data Ingestion via FRED
 *
 * INGESTION CONTRACT:
 * - Logs each run in ops.ingest_run
 * - Computes row_hash for idempotency
 * - Append-only inserts (no upserts)
 *
 * Purpose: keep `mkt.fx_1d` fresh for Core/Specialists.
 * Zero tolerance: no synthetic data; fail loudly on missing config.
 *
 * @author Claude (ZINC-FUSION-V15)
 * @version 1.1.0
 * @date 2026-02-16
 */

import { createHash } from "crypto";
import { inngest, DB_CONCURRENCY } from "./client";
import dbPool from "@/lib/db";

const pool = dbPool;

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

// PoolClient helper functions removed — SQL inlined inside step.run() closures
// to prevent stale connections across Inngest durable execution boundaries.

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
  { id: "fx-spot-daily", name: "FX Spot (1D) via FRED", retries: 3, concurrency: [DB_CONCURRENCY, { limit: 1 }] },
  { cron: "0 9 * * *" }, // Daily at 09:00 UTC
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
          ["fx-spot-daily"]
        );
        return result.rows[0].id as string;
      } finally {
        client.release();
      }
    });

    logger.info(`Started ingest run: ${runId}`);

    // ── Step 2: process each FX pair ──
    // Each step.run returns per-pair counters so we can aggregate after.
    const pairResults: { pair: string; attempted: number; inserted: number; skipped: number; quarantined: number }[] = [];

    for (const { pair, seriesId } of PAIRS) {
      const outcome = await step.run(`pair-${pair}`, async () => {
        let pAttempted = 0, pInserted = 0, pSkipped = 0, pQuarantined = 0;

        // Fetch from FRED API (no DB connection needed yet)
        const client = await pool.connect();
        try {
          const maxDateResult = await client.query(
            `SELECT MAX(event_date)::date::text as max_date FROM mkt.fx_1d WHERE pair=$1`,
            [pair]
          );
          const maxDate = maxDateResult.rows[0]?.max_date ?? null;
          const startDate = maxDate ? addDays(maxDate, 1) : "2000-01-01";

          const observations = await fetchFredObservations(seriesId, startDate);

          for (const obs of observations) {
            const eventDate = obs.date;
            const value = obs.value;

            if (!eventDate || value === "." || value === "") {
              pSkipped++;
              continue;
            }

            const rate = Number(value);
            if (!Number.isFinite(rate)) {
              pQuarantined++;
              continue;
            }

            pAttempted++;

            const exists = await client.query(
              `SELECT 1 FROM mkt.fx_1d WHERE event_date=$1::date AND pair=$2 LIMIT 1`,
              [eventDate, pair]
            );
            if (exists.rows.length > 0) {
              pSkipped++;
              continue;
            }

            const rowHash = computeRowHash(pair, eventDate, rate, seriesId);
            await client.query(
              `INSERT INTO mkt.fx_1d (pair, event_date, rate, source, row_hash) VALUES ($1, $2::date, $3, $4, $5)`,
              [pair, eventDate, rate, "FRED", rowHash]
            );
            pInserted++;
          }
        } finally {
          client.release();
        }

        return { pair, attempted: pAttempted, inserted: pInserted, skipped: pSkipped, quarantined: pQuarantined };
      });

      pairResults.push(outcome);
      logger.info(`${outcome.pair}: +${outcome.inserted} inserted, ${outcome.skipped} skipped`);
    }

    // Aggregate counters
    let attempted = 0, inserted = 0, skipped = 0, quarantined = 0;
    for (const r of pairResults) {
      attempted += r.attempted;
      inserted += r.inserted;
      skipped += r.skipped;
      quarantined += r.quarantined;
    }

    // ── Step 3: finalize ingest run ──
    await step.run("complete-ingest-run", async () => {
      const client = await pool.connect();
      try {
        await client.query(
          `UPDATE ops.ingest_run SET status=$2, completed_at=NOW(),
           rows_attempted=$3, rows_inserted=$4, rows_skipped=$5, rows_quarantined=$6 WHERE id=$1`,
          [runId, "success", attempted, inserted, skipped, quarantined]
        );
      } finally {
        client.release();
      }
    });

    logger.info(`Completed: ${inserted} inserted, ${skipped} skipped across ${PAIRS.length} pairs`);

    return { status: "success", runId, attempted, inserted, skipped, quarantined };
  }
);
