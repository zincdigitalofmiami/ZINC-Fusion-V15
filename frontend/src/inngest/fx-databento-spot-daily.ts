/**
 * FX Spot (1D) from Databento CME Futures
 *
 * Fetches NZDUSD and USDZAR which are not available from FRED.
 * Uses CME FX futures continuous contracts and converts to spot-equivalent rates.
 *
 * Writes to: mkt.fx_1d (same as fx-spot-daily.ts)
 */

import { createHash } from "crypto";
import { type PoolClient } from "pg";
import { inngest } from "./client";
import { fetchDatabentoCsv, parseDatabentoOhlcvCsv } from "@/lib/databento";
import dbPool from "@/lib/db";

const pool = dbPool;

// Databento FX pairs not available from FRED
// Pair names use SLASH format per 20260118_fx_consolidation migration convention.
// Note: These are CME futures, close price used as spot proxy
const DATABENTO_PAIRS: Array<{
  pair: string;
  continuous: string;
  invert: boolean; // True if CME quotes XXX/USD but we want USD/XXX
}> = [
  { pair: "NZD/USD", continuous: "6N.c.0", invert: false },
  { pair: "ZAR/USD", continuous: "6Z.c.0", invert: true }, // CME: ZAR/USD -> inverted to USD/ZAR rate
];

function computeRowHash(pair: string, eventDate: string, rate: number): string {
  return createHash("sha256").update(`${pair}|${eventDate}|${rate}|databento`).digest("hex");
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

export const fxDatabentoSpotDaily = inngest.createFunction(
  { id: "fx-databento-spot-daily", name: "FX Spot (1D) via Databento", retries: 3 },
  { cron: "30 */8 * * *" }, // Every 8 hours at :30 (0:30, 8:30, 16:30 UTC) - offset from FRED job
  async ({ step, logger }) => {
    if (!process.env.DATABASE_URL) {
      throw new Error("DATABASE_URL not configured");
    }
    if (!process.env.DATABENTO_API_KEY) {
      throw new Error("DATABENTO_API_KEY not configured");
    }

    const client = await pool.connect();
    let runId: string | null = null;
    let attempted = 0;
    let inserted = 0;
    let skipped = 0;
    let quarantined = 0;

    try {
      runId = await step.run("create-ingest-run", () => createIngestRun(client, "fx-databento-spot-daily"));
      logger.info(`Started ingest run: ${runId}`);

      for (const { pair, continuous, invert } of DATABENTO_PAIRS) {
        await step.run(`pair-${pair}`, async () => {
          const maxDate = await getMaxDate(client, pair);
          // Databento starts 2010-06-06
          const startDate = maxDate ? addDays(maxDate, 1) : "2010-06-06";

          // Don't fetch if we're already current
          const today = new Date().toISOString().slice(0, 10);
          if (startDate >= today) {
            logger.info(`${pair}: already current (last: ${maxDate})`);
            return;
          }

          const endDate = today;

          logger.info(`${pair}: fetching from ${startDate} to ${endDate}`);

          try {
            const csv = await fetchDatabentoCsv({
              dataset: "GLBX.MDP3",
              schema: "ohlcv-1d",
              symbols: continuous,
              stype_in: "continuous",
              start: `${startDate}T00:00:00Z`,
              end: `${endDate}T00:00:00Z`,
              encoding: "csv",
              pretty_ts: "true",
              pretty_px: "true",
            });

            const bars = parseDatabentoOhlcvCsv(csv);
            logger.info(`${pair}: fetched ${bars.length} bars`);

            for (const bar of bars) {
              const eventDate = bar.tsEvent.toISOString().slice(0, 10);
              let rate = bar.close;

              // Invert if needed (convert from XXX/USD to USD/XXX)
              if (invert && rate > 0) {
                rate = 1.0 / rate;
              }

              if (!Number.isFinite(rate) || rate <= 0) {
                quarantined++;
                continue;
              }

              attempted++;

              const rowHash = computeRowHash(pair, eventDate, rate);

              try {
                await client.query(
                  `INSERT INTO mkt.fx_1d
                    (pair, event_date, rate, source, row_hash, ingested_at)
                   VALUES ($1, $2::date, $3, 'databento', $4, NOW())
                   ON CONFLICT (pair, event_date) DO UPDATE SET
                     rate = EXCLUDED.rate,
                     source = 'databento',
                     row_hash = EXCLUDED.row_hash,
                     ingested_at = NOW()`,
                  [pair, eventDate, rate, rowHash]
                );
                inserted++;
              } catch (err) {
                logger.warn(`Failed to insert ${pair} ${eventDate}: ${err}`);
                skipped++;
              }
            }
          } catch (err) {
            const msg = err instanceof Error ? err.message : String(err);
            logger.error(`Failed to fetch ${pair}: ${msg}`);
            // Continue with other pairs
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
