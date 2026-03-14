import { inngest, DB_CONCURRENCY } from "./client";
import {
  fetchDatabentoCsvWithAvailableEndRetry,
  parseDatabentoOhlcvCsv,
} from "../lib/databento";
import dbPool from "@/lib/db";
import { randomUUID } from "crypto";

const pool = dbPool;

interface DatabentoDailyQuote {
  eventDate: Date;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number;
  volume: number;
}

async function fetchDatabentoDailyZl(): Promise<DatabentoDailyQuote | null> {
  // No T-1 offset: job runs 06:05 CT, ~13h after CME close — yesterday's bar is available
  const end = new Date();
  end.setUTCHours(0, 0, 0, 0);
  const start = new Date(end.getTime() - 5 * 24 * 60 * 60 * 1000);

  const { csv } = await fetchDatabentoCsvWithAvailableEndRetry({
    dataset: "GLBX.MDP3",
    schema: "ohlcv-1d",
    symbols: "ZL.n.0",
    stype_in: "continuous",
    start: start.toISOString(),
    end: end.toISOString(),
    encoding: "csv",
    pretty_ts: "true",
    pretty_px: "true",
  }, 15_000);

  const bars = parseDatabentoOhlcvCsv(csv);
  if (!bars.length) return null;

  const last = bars[bars.length - 1];
  return {
    eventDate: new Date(Date.UTC(
      last.tsEvent.getUTCFullYear(),
      last.tsEvent.getUTCMonth(),
      last.tsEvent.getUTCDate()
    )),
    open: last.open,
    high: last.high,
    low: last.low,
    close: last.close,
    volume: last.volume ?? 0,
  };
}

/**
 * ZL daily bars for analytics.price_1d (Databento only)
 */
export const zlDaily = inngest.createFunction(
  { id: "zl-daily", name: "ZL Daily (Databento)", retries: 3, concurrency: [DB_CONCURRENCY] },
  { cron: "TZ=America/Chicago 5 6 * * *" }, // Daily at 06:05 CT
  async ({ step, logger, attempt }) => {
    const zlQuote = await step.run("fetch-databento-zl", async () => {
      logger.info(`ZL daily fetch attempt ${attempt}, requesting Databento ohlcv-1d`);
      return await fetchDatabentoDailyZl();
    });

    if (!zlQuote) {
      // Log the no_data event so it's visible in ops.ingest_run queries.
      // Without this, a Databento outage silently produces a gap in analytics.price_1d.
      await step.run("log-no-data", async () => {
        const client = await pool.connect();
        try {
          await client.query(
            `INSERT INTO ops.ingest_run
               (id, job_name, status, rows_inserted, error_message, started_at, completed_at)
             VALUES ($1, 'zl-daily', 'success', 0, 'Databento returned no bars', NOW(), NOW())`,
            [randomUUID()],
          );
        } finally {
          client.release();
        }
      });
      logger.warn("ZL daily: Databento returned no bars — analytics.price_1d not updated");
      return { status: "no_data", symbol: "ZL" };
    }

    await step.run("upsert-zl-analytics", async () => {
      const client = await pool.connect();
      try {
        // Batch settlement is always authoritative at 06:05 CT (well after CME close).
        // No WHERE clause — prior WHERE source <> 'databento_live' prevented the batch
        // from correcting bars that were previously marked live, causing stale daily closes.
        await client.query(
          `INSERT INTO analytics.price_1d
            (event_date, open, high, low, close, volume, source, created_at)
           VALUES ($1, $2, $3, $4, $5, $6, 'databento', NOW())
           ON CONFLICT (symbol, event_date) DO UPDATE SET
             open = EXCLUDED.open,
             high = EXCLUDED.high,
             low = EXCLUDED.low,
             close = EXCLUDED.close,
             volume = EXCLUDED.volume,
             source = EXCLUDED.source`,
          [
            zlQuote.eventDate,
            zlQuote.open,
            zlQuote.high,
            zlQuote.low,
            zlQuote.close,
            zlQuote.volume || 0,
          ]
        );

        // Keep latest_price current as batch fallback when live 1m feed is down
        await client.query(
          `UPDATE analytics.latest_price
           SET price = $1, timestamp = $2, updated_at = NOW()
           WHERE id = 1 AND (timestamp IS NULL OR timestamp < $2)`,
          [zlQuote.close, zlQuote.eventDate]
        );
      } finally {
        client.release();
      }
    });

    return {
      status: "success",
      symbol: "ZL",
      eventDate: new Date(zlQuote.eventDate).toISOString().split("T")[0],
      close: zlQuote.close,
    };
  }
);
