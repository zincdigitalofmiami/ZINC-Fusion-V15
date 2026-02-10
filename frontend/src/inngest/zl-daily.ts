import { inngest, DB_CONCURRENCY } from "./client";
import { fetchDatabentoCsv, parseDatabentoOhlcvCsv } from "../lib/databento";
import dbPool from "@/lib/db";

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
  // Subtract 1 day — Databento historical API lags ~24h for daily bars
  const end = new Date();
  end.setUTCDate(end.getUTCDate() - 1);
  end.setUTCHours(0, 0, 0, 0);
  const start = new Date(end.getTime() - 5 * 24 * 60 * 60 * 1000);

  const csv = await fetchDatabentoCsv({
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
 * ZL daily bars for analytics.zl_price_1d (Databento only)
 */
export const zlDaily = inngest.createFunction(
  { id: "zl-daily", name: "ZL Daily (Databento)", retries: 3, concurrency: [DB_CONCURRENCY] },
  { cron: "TZ=America/Chicago 5 */8 * * *" }, // Every 8 hours at :05 (0:05, 8:05, 16:05 CT)
  async ({ step, logger, attempt }) => {
    const zlQuote = await step.run("fetch-databento-zl", async () => {
      logger.info(`ZL daily fetch attempt ${attempt}, requesting Databento ohlcv-1d`);
      return await fetchDatabentoDailyZl();
    });

    if (!zlQuote) {
      return { status: "no_data", symbol: "ZL" };
    }

    await step.run("upsert-zl-analytics", async () => {
      const client = await pool.connect();
      try {
        await client.query(
          `INSERT INTO analytics.zl_price_1d
            (event_date, open, high, low, close, volume, source, created_at)
           VALUES ($1, $2, $3, $4, $5, $6, 'databento', NOW())
           ON CONFLICT (event_date) DO UPDATE SET
             open = EXCLUDED.open,
             high = EXCLUDED.high,
             low = EXCLUDED.low,
             close = EXCLUDED.close,
             volume = EXCLUDED.volume,
             source = EXCLUDED.source
           WHERE analytics.zl_price_1d.source IS NULL
              OR analytics.zl_price_1d.source <> 'databento_live'`,
          [
            zlQuote.eventDate,
            zlQuote.open,
            zlQuote.high,
            zlQuote.low,
            zlQuote.close,
            zlQuote.volume || 0,
          ]
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
